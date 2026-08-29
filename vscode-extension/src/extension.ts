import * as vscode from "vscode";
import { DocFinderClient } from "./client/docfinderClient";
import { DocFinderHoverProvider } from "./providers/hoverProvider";
import { CatalogWebviewPanel } from "./views/catalogWebview";
import { DocBrowser } from "./views/docBrowserPanel";
import { DocFinderTreeProvider } from "./views/docTreeProvider";

let client: DocFinderClient | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
    return;
  }

  const rootPath = workspaceFolders[0].uri.fsPath;
  client = new DocFinderClient(rootPath);

  const autoScan = vscode.workspace.getConfiguration("docfinder").get<boolean>("autoScanOnOpen", true);
  if (autoScan) {
    client.start().catch(() => {});
  }

  // 1. Register Hover Provider
  const hoverProvider = new DocFinderHoverProvider(client);
  context.subscriptions.push(
    vscode.languages.registerHoverProvider({ language: "python", scheme: "file" }, hoverProvider)
  );

  // 2. Register Sidebar TreeView
  const treeProvider = new DocFinderTreeProvider(client, rootPath);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("docfinder-tree", treeProvider)
  );

  // 3. Register Commands
  context.subscriptions.push(
    vscode.commands.registerCommand("docfinder.refreshCatalog", async () => {
      if (client) {
        await client.refreshCatalog();
        treeProvider.refresh();
        vscode.window.showInformationMessage("DocFinder: Documentation catalog refreshed.");
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("docfinder.openWebview", async () => {
      if (client) {
        await CatalogWebviewPanel.createOrShow(client);
      }
    })
  );

  function extractDocArgs(arg0?: any, arg1?: any): { url?: string; title?: string } {
    if (!arg0) return {};

    // If arg0 is a string (e.g. "https://..." or JSON string)
    if (typeof arg0 === "string") {
      const trimmed = arg0.trim();
      if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
        try {
          const parsed = JSON.parse(trimmed);
          if (Array.isArray(parsed) && parsed.length > 0) {
            return extractDocArgs(parsed[0], parsed[1]);
          }
          if (typeof parsed === "object" && parsed !== null) {
            return { url: parsed.url, title: parsed.title };
          }
        } catch {}
      }
      if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
        return { url: trimmed, title: typeof arg1 === "string" ? arg1 : undefined };
      }
    }

    // If arg0 is an array
    if (Array.isArray(arg0) && arg0.length > 0) {
      return extractDocArgs(arg0[0], arg0[1]);
    }

    // If arg0 is an object { url: "...", title: "..." }
    if (typeof arg0 === "object" && arg0 !== null) {
      if (arg0.url) {
        return { url: String(arg0.url).trim(), title: arg0.title ? String(arg0.title) : undefined };
      }
    }

    return {};
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("docfinder.openDocBeside", async (arg0?: any, arg1?: any) => {
      let { url, title } = extractDocArgs(arg0, arg1);

      if (!url && vscode.window.activeTextEditor && client) {
        const editor = vscode.window.activeTextEditor;
        const pos = editor.selection.active;
        const res = await client.resolveAtPosition(
          editor.document.uri.fsPath,
          pos.line + 1,
          pos.character,
          editor.document.getText()
        );
        if (res && res.found && res.docUrl) {
          url = res.docUrl;
          title = res.symbol;
        }
      }

      if (url) {
        await DocBrowser.openBeside(url, title);
      } else {
        vscode.window.showInformationMessage("DocFinder: No documentation link found for symbol.");
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("docfinder.openDocInTab", async (arg0?: any, arg1?: any) => {
      const { url, title } = extractDocArgs(arg0, arg1);
      if (url) {
        await DocBrowser.open(url, title, vscode.ViewColumn.Active);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("docfinder.openDocAtCursor", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "python" || !client) {
        return;
      }

      const pos = editor.selection.active;
      const res = await client.resolveAtPosition(
        editor.document.uri.fsPath,
        pos.line + 1,
        pos.character,
        editor.document.getText()
      );

      if (res && res.found && res.docUrl) {
        vscode.env.openExternal(vscode.Uri.parse(res.docUrl));
      } else {
        vscode.window.showInformationMessage("DocFinder: No documentation link found for symbol under cursor.");
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("docfinder.scanWorkspace", async () => {
      // Run through the same interpreter as the daemon: the `docfinder` script
      // is not necessarily on the terminal's PATH.
      const python = client ? await client.resolveInterpreter() : "python3";
      const terminal = vscode.window.createTerminal("DocFinder Scan");
      terminal.show();
      terminal.sendText(`"${python}" -m docfinder.cli "${rootPath}"`);
    })
  );

  context.subscriptions.push(client);
}

export function deactivate() {
  if (client) {
    client.dispose();
  }
}
