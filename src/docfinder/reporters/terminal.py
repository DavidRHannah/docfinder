from __future__ import annotations

from typing import List

from docfinder.models import PackageReport


def print_terminal_report(packages: List[PackageReport]) -> None:
    print("\n" + "=" * 90)
    print(" DOCFINDER: CODEBASE DOCUMENTATION DIRECTORY & SYMBOL USAGE")
    print("=" * 90)

    total_symbols = sum(len(p.used_symbols) for p in packages)
    total_usages = sum(sum(len(usages) for usages in p.used_symbols.values()) for p in packages)

    print(f"Total Packages: {len(packages)} | Total Unique Symbols: {total_symbols} | Code Usages: {total_usages}\n")

    for pkg in sorted(packages, key=lambda p: (len(p.used_symbols) == 0, p.dist_name)):
        usage_count = sum(len(u) for u in pkg.used_symbols.values())
        print(f"┌─ \033[1;36m{pkg.dist_name}\033[0m ({pkg.version_spec})")
        print(f"│  Main Docs: \033[4;34m{pkg.doc_url}\033[0m [{pkg.doc_source_type}]")
        print(f"│  Active Symbols Used: {len(pkg.used_symbols)} ({usage_count} call-sites)")

        if pkg.used_symbols:
            print("│  Symbols & Reference Links:")
            for sym, usages in sorted(pkg.used_symbols.items(), key=lambda x: len(x[1]), reverse=True):
                doc_link = pkg.symbol_doc_links.get(sym, pkg.doc_url)
                files_str = ", ".join(f"{u.file_path}:{u.line_number}" for u in usages[:3])
                if len(usages) > 3:
                    files_str += f" (+{len(usages)-3} more)"

                print(f"│    • \033[1;32m{sym}\033[0m ({len(usages)}x)")
                print(f"│      ↳ Doc: \033[0;34m{doc_link}\033[0m")
                print(f"│      ↳ Used at: \033[0;37m{files_str}\033[0m")
        print("└" + "─" * 89)
