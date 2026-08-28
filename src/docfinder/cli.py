from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List

from docfinder import __version__
from docfinder.manifest import ManifestParser
from docfinder.models import PackageReport
from docfinder.reporters.html import generate_html_report
from docfinder.reporters.markdown import generate_markdown_report
from docfinder.reporters.terminal import print_terminal_report
from docfinder.resolver import DocResolverEngine
from docfinder.scanner import ASTProjectScanner


def run_scan(
    target_dir: Path,
    generate_md: bool = True,
    generate_html: bool = True,
    output_dir: Path | None = None,
) -> List[PackageReport]:
    target_dir = target_dir.resolve()
    out_dir = (output_dir or target_dir).resolve()

    print(f"[PyDocFinder v{__version__}] Scanning codebase at: {target_dir}")

    # 1. Parse dependencies
    manifest_parser = ManifestParser(target_dir)
    declared_pkgs = manifest_parser.parse()
    print(f"Found {len(declared_pkgs)} declared packages in manifest.")

    # 2. Scan ASTs
    ast_scanner = ASTProjectScanner(target_dir)
    symbol_usages = ast_scanner.scan()
    print(f"Extracted symbol usage from codebase.")

    # 3. Resolve Documentation
    doc_resolver = DocResolverEngine()
    package_reports: Dict[str, PackageReport] = {}

    for dist_name, ver in declared_pkgs.items():
        imp_name = manifest_parser.get_import_name(dist_name)
        main_url, doc_type = doc_resolver.resolve_symbol(imp_name, dist_name, imp_name)
        package_reports[imp_name] = PackageReport(
            dist_name=dist_name,
            import_name=imp_name,
            version_spec=ver,
            doc_url=main_url,
            doc_source_type=doc_type,
        )

    # Attach symbol usages
    for sym, usages in symbol_usages.items():
        top_mod = sym.split(".")[0]
        if top_mod in package_reports:
            report = package_reports[top_mod]
            report.used_symbols[sym].extend(usages)
            doc_link, _ = doc_resolver.resolve_symbol(top_mod, report.dist_name, sym)
            report.symbol_doc_links[sym] = doc_link

    # Also detect non-declared third party or stdlib packages if heavily used
    imported_tops = {sym.split(".")[0] for sym in symbol_usages.keys()}
    ignore_roots = {"src", "infra", "tests", "config", "scripts", "docfinder"}
    for top_mod in imported_tops:
        if top_mod not in package_reports and top_mod not in ignore_roots:
            main_url, doc_type = doc_resolver.resolve_symbol(top_mod, top_mod, top_mod)
            report = PackageReport(
                dist_name=top_mod,
                import_name=top_mod,
                version_spec="imported",
                doc_url=main_url,
                doc_source_type=doc_type,
            )
            for sym, usages in symbol_usages.items():
                if sym.split(".")[0] == top_mod:
                    report.used_symbols[sym].extend(usages)
                    doc_link, _ = doc_resolver.resolve_symbol(top_mod, top_mod, sym)
                    report.symbol_doc_links[sym] = doc_link
            package_reports[top_mod] = report

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
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()
    target_path = Path(args.path)
    output_path = Path(args.output_dir) if args.output_dir else None

    run_scan(
        target_dir=target_path,
        generate_md=not args.no_md,
        generate_html=not args.no_html,
        output_dir=output_path,
    )


if __name__ == "__main__":
    main()
