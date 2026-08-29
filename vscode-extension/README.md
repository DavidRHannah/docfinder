# DocFinder for VS Code

Find documentation for Python packages and symbols without leaving VS Code.

## Features

- Hover over a Python symbol to view its documentation link.
- Browse packages, symbols, and code locations in the DocFinder sidebar.
- Open documentation for the symbol at your cursor.
- View a searchable documentation catalog inside VS Code.
- Create Markdown and HTML documentation reports for the open workspace.

## Commands

Open the Command Palette with `Ctrl+Shift+P` on Windows or Linux, or `Cmd+Shift+P` on macOS. Then run one of these commands:

- `DocFinder: Open Documentation for Symbol at Cursor`
- `DocFinder: Refresh Workspace Documentation Catalog`
- `DocFinder: Open Interactive Documentation Catalog`
- `DocFinder: Generate Markdown and HTML Documentation Reports`

You can also right-click in a Python editor and select **Open Documentation for Symbol at Cursor**.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `docfinder.enableHover` | `true` | Show documentation links when you hover over Python symbols. |
| `docfinder.pythonPath` | Empty | Path to the Python interpreter DocFinder should use. |
| `docfinder.autoScanOnOpen` | `true` | Scan the workspace when you open a Python project. |

## Build and install

Install the extension dependencies:

```bash
cd vscode-extension
npm install
```

Create a `.vsix` extension package:

```bash
npx @vscode/vsce package
```

In VS Code, choose **Extensions: Install from VSIX...** from the Command Palette and select the generated file.

## Development

Compile the extension once:

```bash
npm run compile
```

Or recompile whenever files change:

```bash
npm run watch
```
