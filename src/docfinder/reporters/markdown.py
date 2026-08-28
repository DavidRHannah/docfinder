from __future__ import annotations

from pathlib import Path
from typing import List

from docfinder.models import PackageReport


def generate_markdown_report(packages: List[PackageReport], output_path: Path) -> None:
    md = [
        "# Codebase Documentation Catalog\n",
        "> Generated automatically by [DocFinder](https://github.com/DavidRHannah/docfinder)\n",
        "| Package | Version | Symbols Detected | Primary Documentation |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for pkg in sorted(packages, key=lambda p: p.dist_name):
        sym_count = len(pkg.used_symbols)
        md.append(f"| **`{pkg.dist_name}`** | `{pkg.version_spec}` | {sym_count} symbols | [{pkg.doc_url}]({pkg.doc_url}) |")

    md.append("\n## Detailed Symbol Usage & Direct Documentation Links\n")

    for pkg in sorted(packages, key=lambda p: p.dist_name):
        if not pkg.used_symbols:
            continue
        md.append(f"### {pkg.dist_name} (`{pkg.version_spec}`)")
        md.append(f"- **Package Documentation**: [{pkg.doc_url}]({pkg.doc_url})")
        md.append("\n| Symbol | Occurrences | Documentation Link | Sample Code Locations |")
        md.append("| :--- | :--- | :--- | :--- |")

        for sym, usages in sorted(pkg.used_symbols.items(), key=lambda x: len(x[1]), reverse=True):
            doc_link = pkg.symbol_doc_links.get(sym, pkg.doc_url)
            locs = ", ".join(f"`{u.file_path}:{u.line_number}`" for u in usages[:3])
            if len(usages) > 3:
                locs += f" *(+{len(usages)-3} more)*"
            md.append(f"| `{sym}` | {len(usages)} | [Documentation Link]({doc_link}) | {locs} |")
        md.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
