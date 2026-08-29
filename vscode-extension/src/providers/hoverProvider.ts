import * as vscode from "vscode";
import { DocFinderClient, SymbolDocResult } from "../client/docfinderClient";

export class DocFinderHoverProvider implements vscode.HoverProvider {
  constructor(private client: DocFinderClient) {}

  public async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position,
    token: vscode.CancellationToken
  ): Promise<vscode.Hover | null> {
    const config = vscode.workspace.getConfiguration("docfinder");
    if (!config.get<boolean>("enableHover", true)) {
      return null;
    }

    const wordRange = document.getWordRangeAtPosition(position);
    if (!wordRange) {
      return null;
    }

    try {
      const result: SymbolDocResult = await this.client.resolveAtPosition(
        document.uri.fsPath,
        position.line + 1, // 1-indexed line for Python AST
        position.character,
        document.getText()
      );

      if (token.isCancellationRequested || !result.found || !result.docUrl) {
        return null;
      }

      const md = new vscode.MarkdownString();
      md.isTrusted = true;
      md.supportHtml = true;

      const sourceLabel = this.formatSourceType(result.docType || "");
      const commandArgs = encodeURIComponent(
        JSON.stringify([result.docUrl, result.symbol])
      );
      const sideTabUri = vscode.Uri.parse(`command:docfinder.openDocBeside?${commandArgs}`);

      md.appendMarkdown(`### 📦 **${result.packageName}** \`(${result.version || "latest"})\`\n\n`);
      md.appendMarkdown(`\`${result.symbol}\` &nbsp; • &nbsp; _${sourceLabel}_\n\n`);
      md.appendMarkdown(`---\n\n`);
      md.appendMarkdown(`[📖 **Open in Side Tab ➔**](${sideTabUri}) &nbsp; | &nbsp; [🌐 **External Browser ↗**](${result.docUrl})\n\n`);

      const hoverRange = result.range
        ? new vscode.Range(
            result.range.startLine - 1,
            result.range.startCol,
            result.range.endLine - 1,
            result.range.endCol
          )
        : wordRange;

      return new vscode.Hover(md, hoverRange);
    } catch (error) {
      return null;
    }
  }

  private formatSourceType(docType: string): string {
    switch (docType) {
      case "provider_rule":
        return "Official Cloud / SDK Reference";
      case "intersphinx":
        return "ReadTheDocs / Intersphinx Anchor";
      case "stdlib":
        return "Python Standard Library";
      case "pypi_metadata":
        return "PyPI Package Docs";
      default:
        return "Documentation Source";
    }
  }
}
