import * as vscode from "vscode";
import { CatalogPackage, DocFinderClient } from "../client/docfinderClient";

export class CatalogWebviewPanel {
  public static currentPanel: CatalogWebviewPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private disposables: vscode.Disposable[] = [];

  public static async createOrShow(client: DocFinderClient) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    if (CatalogWebviewPanel.currentPanel) {
      CatalogWebviewPanel.currentPanel.panel.reveal(column);
      await CatalogWebviewPanel.currentPanel.update(client);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      "docfinderCatalog",
      "DocFinder: Documentation Catalog",
      column || vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    CatalogWebviewPanel.currentPanel = new CatalogWebviewPanel(panel, client);
  }

  private constructor(panel: vscode.WebviewPanel, client: DocFinderClient) {
    this.panel = panel;
    this.update(client);

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
  }

  public async update(client: DocFinderClient) {
    this.panel.webview.html = "<h3>Loading DocFinder Documentation Catalog...</h3>";
    try {
      const catalog = await client.getWorkspaceCatalog();
      this.panel.webview.html = this.getHtmlContent(catalog.packages || []);
    } catch (err) {
      this.panel.webview.html = `<h3>Error loading catalog: ${CatalogWebviewPanel.escape(err)}</h3>`;
    }
  }

  /** Symbol names and doc URLs come from scanned source and package metadata. */
  private static escape(value: unknown): string {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  private getHtmlContent(packages: CatalogPackage[]): string {
    const esc = CatalogWebviewPanel.escape;
    const cards = packages.map((pkg) => {
      const symRows = pkg.symbols
        .map((s) => {
          const locs = s.locations
            .slice(0, 4)
            .map((l) => `<code>${esc(l.file)}:${esc(l.line)}</code>`)
            .join("<br>");
          const more =
            s.locations.length > 4
              ? `<br><small class="text-secondary">+${s.locations.length - 4} more</small>`
              : "";
          return `
            <tr>
              <td><span class="symbol-name">${esc(s.symbol)}</span></td>
              <td><span class="badge badge-count">${esc(s.usageCount)}</span></td>
              <td><a href="${esc(s.docUrl)}" target="_blank">Open Documentation ↗</a></td>
              <td><small>${locs}${more}</small></td>
            </tr>
          `;
        })
        .join("");

      return `
        <div class="card pkg-card mb-4">
          <div class="card-header d-flex justify-content-between align-items-center">
            <div>
              <h5 class="mb-0 fw-bold">📦 ${esc(pkg.packageName)} <span class="badge badge-pkg">${esc(pkg.version)}</span></h5>
              <small class="text-secondary">Source: ${esc(pkg.docType)}</small>
            </div>
            <div>
              <a href="${esc(pkg.docUrl)}" target="_blank" class="btn btn-sm btn-outline-info">Package Docs ↗</a>
            </div>
          </div>
          <div class="card-body p-0">
            <table class="table table-dark table-hover mb-0">
              <thead>
                <tr>
                  <th style="width: 30%">Symbol</th>
                  <th style="width: 10%">Usages</th>
                  <th style="width: 30%">Doc Link</th>
                  <th style="width: 30%">Locations</th>
                </tr>
              </thead>
              <tbody>
                ${symRows || '<tr><td colspan="4" class="text-center text-secondary py-3">No direct symbol usages.</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>
      `;
    });

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>DocFinder Documentation Catalog</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: var(--vscode-editor-background, #0f172a); color: var(--vscode-editor-foreground, #e2e8f0); font-family: var(--vscode-font-family, sans-serif); padding: 1.5rem; }
    .card { background-color: var(--vscode-sideBar-background, #1e293b); border: 1px solid var(--vscode-widget-border, #334155); }
    .card-header { background-color: transparent; border-bottom: 1px solid var(--vscode-widget-border, #334155); }
    .badge-pkg { background-color: #0ea5e9; color: white; }
    .badge-count { background-color: #3b82f6; }
    a { color: var(--vscode-textLink-foreground, #38bdf8); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .table { color: var(--vscode-editor-foreground, #cbd5e1); }
    .table-dark { background-color: transparent; }
    .search-box { background-color: var(--vscode-input-background, #1e293b); border: 1px solid var(--vscode-input-border, #475569); color: var(--vscode-input-foreground, #f8fafc); }
    .search-box:focus { background-color: var(--vscode-input-background, #1e293b); border-color: #38bdf8; color: #fff; box-shadow: none; }
    code { color: #f43f5e; background-color: rgba(0,0,0,0.2); padding: 2px 4px; border-radius: 4px; }
    .symbol-name { color: #4ade80; font-weight: 600; }
  </style>
</head>
<body>
  <div class="container-fluid">
    <div class="d-flex justify-content-between align-items-center mb-4 pb-3 border-bottom border-secondary">
      <div>
        <h2 class="h4 mb-0 fw-bold">🔍 DocFinder Documentation Catalog</h2>
        <small class="text-secondary">Explore all active library dependencies and symbols</small>
      </div>
      <div class="w-25">
        <input type="text" id="searchInput" class="form-control search-box" placeholder="Filter symbols, packages...">
      </div>
    </div>
    <div id="cardsContainer">
      ${cards.join("\n")}
    </div>
  </div>
  <script>
    document.getElementById('searchInput').addEventListener('input', function(e) {
      const term = e.target.value.toLowerCase();
      document.querySelectorAll('.pkg-card').forEach(card => {
        const text = card.textContent.toLowerCase();
        card.style.display = text.includes(term) ? '' : 'none';
      });
    });
  </script>
</body>
</html>`;
  }

  public dispose() {
    CatalogWebviewPanel.currentPanel = undefined;
    this.panel.dispose();
    while (this.disposables.length) {
      const x = this.disposables.pop();
      if (x) x.dispose();
    }
  }
}
