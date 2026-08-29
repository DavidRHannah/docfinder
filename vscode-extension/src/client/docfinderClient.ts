import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as readline from "readline";
import * as vscode from "vscode";

export interface SymbolDocResult {
  found: boolean;
  symbol?: string;
  packageName?: string;
  version?: string;
  docUrl?: string;
  docType?: string;
  range?: {
    startLine: number;
    startCol: number;
    endLine: number;
    endCol: number;
  };
  error?: string;
}

export interface CatalogLocation {
  file: string;
  line: number;
  snippet: string;
}

export interface CatalogSymbol {
  symbol: string;
  docUrl: string;
  usageCount: number;
  locations: CatalogLocation[];
}

export interface CatalogPackage {
  packageName: string;
  importName: string;
  version: string;
  docUrl: string;
  docType: string;
  symbolCount: number;
  symbols: CatalogSymbol[];
}

export interface CatalogResult {
  packages: CatalogPackage[];
}

export class DocFinderClient implements vscode.Disposable {
  private process: cp.ChildProcess | null = null;
  private nextId = 1;
  private pendingRequests = new Map<
    number,
    { resolve: (value: any) => void; reject: (reason?: any) => void; timer: NodeJS.Timeout }
  >();
  private outputChannel: vscode.OutputChannel;
  private isReady = false;
  private startPromise: Promise<boolean> | null = null;
  private startupErrorShown = false;
  private disposed = false;

  constructor(private workspaceRoot: string) {
    this.outputChannel = vscode.window.createOutputChannel("DocFinder Language Client");
  }

  /**
   * Starts the daemon. Concurrent callers share a single start attempt so that
   * a hover, the tree view and a command cannot each spawn their own daemon.
   */
  public async start(): Promise<boolean> {
    if (this.isReady) {
      return true;
    }
    if (!this.startPromise) {
      this.startPromise = this.doStart().finally(() => {
        this.startPromise = null;
      });
    }
    return this.startPromise;
  }

  private async doStart(): Promise<boolean> {
    if (this.disposed) {
      return false;
    }

    const pythonPath = await this.getPythonPath();
    this.outputChannel.appendLine(`[DocFinder] Starting Python daemon using: ${pythonPath}`);

    const args = ["-m", "docfinder.cli", "--server", this.workspaceRoot];

    try {
      const child = cp.spawn(pythonPath, args, {
        cwd: this.workspaceRoot,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });
      this.process = child;

      // A failed spawn (bad interpreter path) reports asynchronously via "error".
      // Without this listener Node turns it into an uncaught extension-host exception.
      child.on("error", (err) => {
        this.outputChannel.appendLine(`[DocFinder] Failed to spawn "${pythonPath}": ${err.message}`);
        this.handleDaemonGone(new Error(`Could not start "${pythonPath}": ${err.message}`));
        this.reportStartupFailure(pythonPath);
      });

      let stderrTail = "";
      child.stderr?.on("data", (data) => {
        const text = data.toString();
        stderrTail = (stderrTail + text).slice(-2000);
        this.outputChannel.appendLine(`[stderr] ${text.trimEnd()}`);
      });

      const rl = readline.createInterface({ input: child.stdout!, terminal: false });
      rl.on("line", (line) => {
        if (!line.trim()) return;
        try {
          this.handleResponse(JSON.parse(line));
        } catch {
          this.outputChannel.appendLine(`[Error] Invalid JSON from server: ${line}`);
        }
      });

      child.on("exit", (code, signal) => {
        this.outputChannel.appendLine(`[DocFinder] Daemon exited with code ${code}, signal ${signal}`);
        rl.close();
        this.handleDaemonGone(new Error(`DocFinder daemon exited (code ${code})`));
        if (code !== 0 && /No module named/.test(stderrTail)) {
          this.reportStartupFailure(pythonPath, "the docfinder package is not installed for it");
        }
      });

      const initResp = await this.sendRequest(
        "initialize",
        { workspaceRoot: this.workspaceRoot },
        this.getScanTimeout()
      );
      this.isReady = true;
      this.outputChannel.appendLine(`[DocFinder] Initialized successfully: ${JSON.stringify(initResp)}`);
      return true;
    } catch (error: any) {
      this.outputChannel.appendLine(`[DocFinder] Failed to start daemon: ${error?.message || error}`);
      return false;
    }
  }

  /** Fails every in-flight request instead of letting each one wait for its timeout. */
  private handleDaemonGone(reason: Error) {
    this.isReady = false;
    this.process = null;
    for (const { reject, timer } of this.pendingRequests.values()) {
      clearTimeout(timer);
      reject(reason);
    }
    this.pendingRequests.clear();
  }

  private reportStartupFailure(pythonPath: string, detail?: string) {
    if (this.startupErrorShown || this.disposed) {
      return;
    }
    this.startupErrorShown = true;
    const because = detail ? ` because ${detail}` : "";
    vscode.window
      .showErrorMessage(
        `DocFinder could not start its Python daemon with "${pythonPath}"${because}. ` +
          `Install it with "pip install docfinder", or set "docfinder.pythonPath".`,
        "Show Log",
        "Open Settings"
      )
      .then((choice) => {
        if (choice === "Show Log") {
          this.outputChannel.show();
        } else if (choice === "Open Settings") {
          vscode.commands.executeCommand("workbench.action.openSettings", "docfinder.pythonPath");
        }
      });
  }

  public async resolveAtPosition(
    filePath: string,
    line: number,
    character: number,
    content?: string
  ): Promise<SymbolDocResult> {
    if (!(await this.start())) {
      return { found: false, error: "DocFinder daemon not running" };
    }
    return this.sendRequest("resolveAtPosition", { filePath, line, character, content });
  }

  public async getWorkspaceCatalog(): Promise<CatalogResult> {
    if (!(await this.start())) {
      return { packages: [] };
    }
    return this.sendRequest("getWorkspaceCatalog", {}, this.getScanTimeout());
  }

  public async refreshCatalog(): Promise<any> {
    if (!(await this.start())) {
      return { status: "error" };
    }
    return this.sendRequest("refreshCatalog", {}, this.getScanTimeout());
  }

  /**
   * Whole-workspace scans resolve documentation over the network, so they get a
   * far more generous budget than a single hover lookup.
   */
  private getScanTimeout(): number {
    const configured = vscode.workspace
      .getConfiguration("docfinder")
      .get<number>("scanTimeoutSeconds", 120);
    return Math.max(10, configured) * 1000;
  }

  private sendRequest<T = any>(method: string, params: any, timeoutMs = 6000): Promise<T> {
    return new Promise((resolve, reject) => {
      if (!this.process || !this.process.stdin) {
        return reject(new Error("Process not running"));
      }

      const id = this.nextId++;
      const req = { jsonrpc: "2.0", id, method, params };

      const timer = setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error(`Request timeout for method: ${method}`));
        }
      }, timeoutMs);

      this.pendingRequests.set(id, { resolve, reject, timer });
      this.process.stdin.write(JSON.stringify(req) + "\n");
    });
  }

  private handleResponse(resp: any) {
    const id = resp.id;
    const pending = typeof id === "number" ? this.pendingRequests.get(id) : undefined;
    if (!pending) {
      return;
    }
    clearTimeout(pending.timer);
    this.pendingRequests.delete(id);

    if (resp.error) {
      pending.reject(new Error(resp.error.message || "Server Error"));
    } else {
      pending.resolve(resp.result);
    }
  }

  /** The interpreter this client would use, for callers that shell out themselves. */
  public resolveInterpreter(): Promise<string> {
    return this.getPythonPath();
  }

  /**
   * Resolution order: the docfinder.pythonPath setting, the interpreter selected
   * in the Python extension, a virtualenv in the workspace, then PATH.
   */
  private async getPythonPath(): Promise<string> {
    const configured = vscode.workspace.getConfiguration("docfinder").get<string>("pythonPath");
    if (configured && configured.trim()) {
      return configured.trim();
    }

    const fromPythonExtension = await this.getPythonExtensionInterpreter();
    if (fromPythonExtension) {
      return fromPythonExtension;
    }

    const isWindows = process.platform === "win32";
    const binDir = isWindows ? "Scripts" : "bin";
    const exeName = isWindows ? "python.exe" : "python";
    for (const venvDir of [".venv", "venv", "env"]) {
      const candidate = path.join(this.workspaceRoot, venvDir, binDir, exeName);
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }

    return isWindows ? "python" : "python3";
  }

  private async getPythonExtensionInterpreter(): Promise<string | undefined> {
    try {
      const pythonExt = vscode.extensions.getExtension<any>("ms-python.python");
      if (!pythonExt) {
        return undefined;
      }
      if (!pythonExt.isActive) {
        await pythonExt.activate();
      }

      const uri = vscode.Uri.file(this.workspaceRoot);
      const api = pythonExt.exports;

      // Modern environments API.
      const env = api?.environments?.getActiveEnvironmentPath?.(uri);
      if (env?.path && fs.existsSync(env.path)) {
        return env.path;
      }

      // Legacy settings API.
      const legacy = api?.settings?.getExecutionDetails?.(uri)?.execCommand;
      if (Array.isArray(legacy) && legacy.length > 0 && legacy[0]) {
        return legacy[0];
      }
    } catch (err: any) {
      this.outputChannel.appendLine(`[DocFinder] Python extension lookup failed: ${err?.message || err}`);
    }
    return undefined;
  }

  public dispose() {
    this.disposed = true;
    const child = this.process;
    this.handleDaemonGone(new Error("DocFinder client disposed"));
    if (child) {
      child.kill();
    }
    this.outputChannel.dispose();
  }
}
