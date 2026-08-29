import * as path from "path";
import * as vscode from "vscode";
import {
  CatalogLocation,
  CatalogPackage,
  CatalogSymbol,
  DocFinderClient,
} from "../client/docfinderClient";

export type DocTreeItem = PackageTreeItem | SymbolTreeItem | LocationTreeItem;

export class DocFinderTreeProvider implements vscode.TreeDataProvider<DocTreeItem> {
  private _onDidChangeTreeData: vscode.EventEmitter<DocTreeItem | undefined | void> =
    new vscode.EventEmitter<DocTreeItem | undefined | void>();
  readonly onDidChangeTreeData: vscode.Event<DocTreeItem | undefined | void> =
    this._onDidChangeTreeData.event;

  private cachedPackages: CatalogPackage[] = [];

  constructor(private client: DocFinderClient, private workspaceRoot: string) {}

  public refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  public getTreeItem(element: DocTreeItem): vscode.TreeItem {
    return element;
  }

  public async getChildren(element?: DocTreeItem): Promise<DocTreeItem[]> {
    if (!element) {
      // Root level: Packages
      try {
        const catalog = await this.client.getWorkspaceCatalog();
        this.cachedPackages = catalog.packages || [];
        return this.cachedPackages.map((pkg) => new PackageTreeItem(pkg));
      } catch (err) {
        return [];
      }
    }

    if (element instanceof PackageTreeItem) {
      // Second level: Symbols within package
      return element.pkg.symbols.map((sym) => new SymbolTreeItem(sym, element.pkg));
    }

    if (element instanceof SymbolTreeItem) {
      // Third level: Locations in code
      return element.symbol.locations.map(
        (loc) => new LocationTreeItem(loc, element.symbol, this.workspaceRoot)
      );
    }

    return [];
  }
}

export class PackageTreeItem extends vscode.TreeItem {
  constructor(public readonly pkg: CatalogPackage) {
    super(
      `${pkg.packageName} (${pkg.version})`,
      pkg.symbols.length > 0
        ? vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );

    this.description = `${pkg.symbolCount} symbols`;
    this.tooltip = `${pkg.packageName} (${pkg.version})\nMain Docs: ${pkg.docUrl}\nSource: ${pkg.docType}`;
    this.iconPath = new vscode.ThemeIcon("package");
    this.contextValue = "package";
  }
}

export class SymbolTreeItem extends vscode.TreeItem {
  constructor(public readonly symbol: CatalogSymbol, public readonly parentPkg: CatalogPackage) {
    super(
      symbol.symbol,
      symbol.locations.length > 0
        ? vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );

    this.description = `${symbol.usageCount} usages`;
    this.tooltip = `${symbol.symbol}\nDoc: ${symbol.docUrl}\nClick to open documentation`;
    this.iconPath = new vscode.ThemeIcon("symbol-class");
    this.contextValue = "symbol";

    this.command = {
      command: "docfinder.openDocBeside",
      title: "Open Documentation in Side Tab",
      arguments: [{ url: symbol.docUrl, title: symbol.symbol }],
    };
  }
}

export class LocationTreeItem extends vscode.TreeItem {
  constructor(
    public readonly location: CatalogLocation,
    public readonly parentSymbol: CatalogSymbol,
    private workspaceRoot: string
  ) {
    super(
      `${location.file}:${location.line}`,
      vscode.TreeItemCollapsibleState.None
    );

    this.description = location.snippet ? `"${location.snippet}"` : "";
    this.tooltip = `Jump to ${location.file}:${location.line}\n${location.snippet}`;
    this.iconPath = new vscode.ThemeIcon("go-to-file");
    this.contextValue = "location";

    const fileUri = vscode.Uri.file(path.join(this.workspaceRoot, location.file));
    this.command = {
      command: "vscode.open",
      title: "Open File",
      arguments: [
        fileUri,
        {
          selection: new vscode.Range(
            location.line - 1,
            0,
            location.line - 1,
            location.snippet.length
          ),
        },
      ],
    };
  }
}
