import * as vscode from "vscode";

export class DocBrowser {
  /**
   * Opens the given documentation URL in a VS Code tab beside the active editor.
   */
  public static async openBeside(url: string, title?: string): Promise<void> {
    await DocBrowser.open(url, title, vscode.ViewColumn.Beside);
  }

  /**
   * Opens the given documentation URL in a specified ViewColumn.
   */
  public static async open(
    url: string,
    title?: string,
    viewColumn: vscode.ViewColumn = vscode.ViewColumn.Beside
  ): Promise<void> {
    if (!url || typeof url !== "string") {
      vscode.window.showWarningMessage("DocFinder: No valid documentation URL provided.");
      return;
    }

    const cleanUrl = url.trim();
    if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
      vscode.window.showWarningMessage(`DocFinder: Invalid URL: ${cleanUrl}`);
      return;
    }

    try {
      // In VS Code, simpleBrowser.show expects string URL as 1st arg or options as 2nd arg
      await vscode.commands.executeCommand("simpleBrowser.show", cleanUrl, {
        viewColumn,
        preserveFocus: false,
      });
    } catch (err) {
      // Fallback to custom Webview Panel if simpleBrowser is unavailable
      DocBrowser.openFallbackWebview(cleanUrl, title || "DocFinder Documentation", viewColumn);
    }
  }

  private static openFallbackWebview(url: string, title: string, viewColumn: vscode.ViewColumn) {
    const panel = vscode.window.createWebviewPanel(
      "docfinderBrowser",
      title,
      viewColumn,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    panel.webview.html = `<!DOCTYPE html>
<html lang="en" style="height: 100%; margin: 0; padding: 0;">
<head>
  <meta charset="UTF-8">
  <title>${title}</title>
  <style>
    body, html { height: 100%; margin: 0; padding: 0; overflow: hidden; background: #1e1e1e; font-family: sans-serif; }
    .toolbar { height: 36px; background: #252526; display: flex; align-items: center; padding: 0 12px; gap: 8px; border-bottom: 1px solid #3c3c3c; }
    .toolbar a { color: #38bdf8; text-decoration: none; font-size: 12px; }
    .toolbar a:hover { text-decoration: underline; }
    iframe { width: 100%; height: calc(100% - 36px); border: none; }
  </style>
</head>
<body>
  <div class="toolbar">
    <span style="color: #9cdcfe; font-size: 13px; font-weight: bold;">📖 ${title}</span>
    <span style="flex: 1;"></span>
    <a href="${url}" target="_blank">Open in External Browser ↗</a>
  </div>
  <iframe src="${url}"></iframe>
</body>
</html>`;
  }
}
