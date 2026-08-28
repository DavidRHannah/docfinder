# PyDocFinder

PyDocFinder scans a Python project and creates a list of documentation for the packages and symbols it uses. It is useful when you are new to a codebase or need a quick view of its dependencies.

## What it does

- Reads dependencies from `pyproject.toml` and `requirements.txt`.
- Scans Python files for imports, classes, functions, and other used symbols.
- Finds documentation links for packages and symbols when available.
- Prints a summary in the terminal and creates optional reports:
  - `DOCUMENTATION_MAP.md` - a markdown report
  - `doc_catalog.html` - a searchable HTML report

DocFinder supports standard-library links, Sphinx documentation inventories, common cloud libraries, and PyPI project metadata as a fallback.

## Requirements

- Python 3.9 or later

## Install

From this repository:

```bash
pip install -e .
```

For development tools such as tests and linting:

```bash
pip install -e ".[dev]"
```

## Use

Scan the current directory:

```bash
docfinder
```

Scan another project:

```bash
docfinder /path/to/project
```

Save reports in a separate directory:

```bash
docfinder /path/to/project --output-dir ./reports
```

By default, reports are written to the project being scanned. You can turn off either report format:

```bash
docfinder --no-md
docfinder --no-html
```

Run `docfinder --help` to see all command-line options.

## Project layout

```text
src/docfinder/
├── cli.py        # Command-line entry point
├── manifest.py   # Dependency discovery
├── scanner.py    # Python source-code scanning
├── resolver.py   # Documentation-link lookup
└── reporters/    # Terminal, Markdown, and HTML reports

tests/            # Automated tests
examples/         # Example reports
```

## License

MIT
