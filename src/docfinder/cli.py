from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

from docfinder import __version__
from docfinder.catalog import build_package_reports
from docfinder.manifest import ManifestParser
from docfinder.models import PackageReport
from docfinder.reporters.html import generate_html_report
from docfinder.reporters.markdown import generate_markdown_report
from docfinder.reporters.terminal import print_terminal_report
from docfinder.resolver import DocResolverEngine
from docfinder.scanner import ASTProjectScanner
from docfinder.server import DocFinderServer


def run_scan(
    target_dir: Path,
    generate_md: bool = True,
    generate_html: bool = True,
    output_dir: Path | None = None,
    offline: bool = False,
) -> List[PackageReport]:
    target_dir = target_dir.resolve()
    out_dir = (output_dir or target_dir).resolve()

    print(f"[DocFinder v{__version__}] Scanning codebase at: {target_dir}")

    # 1. Parse dependencies
    manifest_parser = ManifestParser(target_dir)
    declared_pkgs = manifest_parser.parse()
    print(f"Found {len(declared_pkgs)} declared packages in manifest.")

    # 2. Scan ASTs
    ast_scanner = ASTProjectScanner(target_dir)
    symbol_usages = ast_scanner.scan()
    print(f"Extracted {len(symbol_usages)} unique symbols from codebase.")

    # 3. Resolve Documentation
    doc_resolver = DocResolverEngine(offline=offline)
    package_reports: Dict[str, PackageReport] = build_package_reports(
        target_dir, declared_pkgs, manifest_parser, doc_resolver, symbol_usages
    )
    reports_list = list(package_reports.values())

    # 4. Generate Reports
    print_terminal_report(reports_list)

    out_dir.mkdir(parents=True, exist_ok=True)

    if generate_md:
        md_file = out_dir / "DOCUMENTATION_MAP.md"
        generate_markdown_report(reports_list, md_file)
        print(f"Markdown report generated: {md_file}")

    if generate_html:
        html_file = out_dir / "doc_catalog.html"
        generate_html_report(reports_list, html_file)
        print(f"HTML interactive report generated: {html_file}")

    return reports_list


def main():
    parser = argparse.ArgumentParser(
        prog="docfinder",
        description="DocFinder: Automatically discover documentation for libraries, classes, and methods used in a Python codebase.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target project directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--server",
        "--daemon",
        dest="server_mode",
        action="store_true",
        help="Run in JSON-RPC daemon server mode for IDE / VS Code extension integration",
    )
    parser.add_argument(
        "--no-md",
        action="store_true",
        help="Disable Markdown report generation",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Disable HTML report generation",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save generated report files",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip all network lookups (Intersphinx and PyPI) and resolve from built-in rules only",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()
    target_path = Path(args.path).resolve()

    if args.server_mode:
        # The catalog is built lazily: the client's `initialize` request drives
        # the first scan, so the daemon is responsive to stdin immediately.
        server = DocFinderServer(target_path, offline=args.offline)
        server.serve_forever()
        return

    output_path = Path(args.output_dir) if args.output_dir else None

    run_scan(
        target_dir=target_path,
        generate_md=not args.no_md,
        generate_html=not args.no_html,
        output_dir=output_path,
        offline=args.offline,
    )


if __name__ == "__main__":
    main()
