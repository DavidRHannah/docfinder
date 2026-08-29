from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

from docfinder.manifest import ManifestParser
from docfinder.models import PackageReport, SymbolUsage
from docfinder.resolver import DocResolverEngine
from docfinder.scanner import ASTProjectScanner


def find_local_module_names(root_dir: Path) -> Set[str]:
    """Top-level module names that belong to the scanned project itself.

    These are first-party imports, so they must not be resolved against PyPI.
    Both flat and `src/` layouts are covered.
    """
    names: Set[str] = set()
    search_roots = [root_dir]
    for layout_dir in ("src", "lib"):
        candidate = root_dir / layout_dir
        if candidate.is_dir():
            search_roots.append(candidate)

    for search_root in search_roots:
        try:
            entries = list(search_root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.name in ASTProjectScanner.DEFAULT_EXCLUDES:
                continue
            if entry.is_dir():
                if any(entry.glob("*.py")):
                    names.add(entry.name)
            elif entry.suffix == ".py":
                names.add(entry.stem)
    return names


def build_package_reports(
    root_dir: Path,
    declared_pkgs: Dict[str, str],
    manifest_parser: ManifestParser,
    resolver: DocResolverEngine,
    symbol_usages: Dict[str, List[SymbolUsage]],
) -> Dict[str, PackageReport]:
    """Builds the {import_name: PackageReport} catalog shared by the CLI and the daemon."""
    reports: Dict[str, PackageReport] = {}

    for dist_name, version_spec in declared_pkgs.items():
        import_name = manifest_parser.get_import_name(dist_name)
        doc_url, doc_type = resolver.resolve_symbol(import_name, dist_name, import_name)
        reports[import_name] = PackageReport(
            dist_name=dist_name,
            import_name=import_name,
            version_spec=version_spec,
            doc_url=doc_url,
            doc_source_type=doc_type,
        )

    local_modules = find_local_module_names(root_dir)

    for symbol, usages in symbol_usages.items():
        top_module = symbol.split(".")[0]
        report = reports.get(top_module)

        if report is None:
            # Undeclared import: either first-party code (skipped) or a
            # transitive/implicit third-party package worth cataloguing.
            if top_module in local_modules:
                continue
            doc_url, doc_type = resolver.resolve_symbol(top_module, top_module, top_module)
            report = PackageReport(
                dist_name=top_module,
                import_name=top_module,
                version_spec="imported",
                doc_url=doc_url,
                doc_source_type=doc_type,
            )
            reports[top_module] = report

        report.used_symbols[symbol].extend(usages)
        symbol_url, _ = resolver.resolve_symbol(top_module, report.dist_name, symbol)
        report.symbol_doc_links[symbol] = symbol_url

    return reports
