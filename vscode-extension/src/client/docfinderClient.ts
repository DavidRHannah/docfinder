import * as cp from "child_process";
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

  constructor(private workspaceRoot: string) {
    this.outputChannel = vscode.window.createOutputChannel("DocFinder Language Client");
  }

  public async start(): Promise<boolean> {
    const pythonPath = this.getPythonPath();
    this.outputChannel.appendLine(`[DocFinder] Starting Python daemon using: ${pythonPath}`);

    const args = ["-m", "docfinder.cli", "--server", this.workspaceRoot];

    try {
      this.process = cp.spawn(pythonPath, args, {
        cwd: this.workspaceRoot,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });

      if (!this.process.pid) {
        throw new Error("Failed to spawn Python process.");
      }

      this.process.stderr?.on("data", (data) => {
        this.outputChannel.appendLine(`[stderr] ${data.toString()}`);
      });

      const rl = readline.createInterface({
        input: this.process.stdout!,
        terminal: false,
      });

      rl.on("line", (line) => {
        if (!line.trim()) return;
        try {
          const resp = JSON.parse(line);
          this.handleResponse(resp);
        } catch (err) {
          this.outputChannel.appendLine(`[Error] Invalid JSON from server: ${line}`);
        }
      });

      this.process.on("exit", (code, signal) => {
        this.outputChannel.appendLine(`[DocFinder] Daemon exited with code ${code}, signal ${signal}`);
        this.isReady = false;
        this.process = null;
      });

      // Initialize workspace
      const initResp = await this.sendRequest("initialize", { workspaceRoot: this.workspaceRoot });
      this.isReady = true;
      this.outputChannel.appendLine(`[DocFinder] Initialized successfully: ${JSON.stringify(initResp)}`);
      return true;
    } catch (error: any) {
      this.outputChannel.appendLine(`[DocFinder] Failed to start daemon: ${error?.message || error}`);
      return false;
    }
  }

  public async resolveAtPosition(
    filePath: string,
    line: number,
    character: number,
    content?: string
  ): Promise<SymbolDocResult> {
    if (!this.isReady && !(await this.start())) {
      return { found: false, error: "DocFinder daemon not running" };
    }
    return this.sendRequest("resolveAtPosition", {
      filePath,
      line,
      character,
      content,
    });
  }

  public async getWorkspaceCatalog(): Promise<CatalogResult> {
    if (!this.isReady && !(await this.start())) {
      return { packages: [] };
    }
    return this.sendRequest("getWorkspaceCatalog", {});
  }

  public async refreshCatalog(): Promise<any> {
    if (!this.isReady && !(await this.start())) {
      return { status: "error" };
    }
    return this.sendRequest("refreshCatalog", {});
  }

  private sendRequest<T = any>(method: string, params: any, timeoutMs = 6000): Promise<T> {
    return new Promise((resolve, reject) => {
      if (!this.process || !this.process.stdin) {
        return reject(new Error("Process not running"));
      }

      const id = this.nextId++;
      const req = {
        jsonrpc: "2.0",
        id,
        method,
        params,
      };

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
    if (id && this.pendingRequests.has(id)) {
      const { resolve, reject, timer } = this.pendingRequests.get(id)!;
      clearTimeout(timer);
      this.pendingRequests.delete(id);

      if (resp.error) {
        reject(new Error(resp.error.message || "Server Error"));
      } else {
        resolve(resp.result);
      }
    }
  }

  private getPythonPath(): string {
    const config = vscode.workspace.getConfiguration("docfinder");
    const customPath = config.get<string>("pythonPath");
    if (customPath && customPath.trim()) {
      return customPath.trim();
    }

    // Auto-detect standard .venv in workspace root
    const venvPython = path.join(this.workspaceRoot, ".venv", "bin", "python");
    if (vscode.workspace.fs) {
      return venvPython;
    }
    return "python3";
  }

  public dispose() {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this.outputChannel.dispose();
  }
}
