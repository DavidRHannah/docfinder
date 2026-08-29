from __future__ import annotations

from html import escape
from pathlib import Path
from typing import List

from docfinder.models import PackageReport

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DocFinder - Codebase Documentation Catalog</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f172a; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 10px; margin-bottom: 1.5rem; }
        .badge-pkg { background-color: #0ea5e9; color: white; }
        .badge-count { background-color: #3b82f6; }
        a { color: #38bdf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .table { color: #cbd5e1; }
        .table-dark { background-color: #1e293b; border-color: #334155; }
        .search-box { background-color: #1e293b; border: 1px solid #475569; color: #f8fafc; }
        .search-box:focus { background-color: #1e293b; border-color: #38bdf8; color: #fff; box-shadow: none; }
        code { color: #f43f5e; background-color: #0f172a; padding: 2px 6px; border-radius: 4px; }
        .symbol-code { color: #4ade80; font-weight: 600; }
    </style>
</head>
<body class="p-4">
    <div class="container-fluid max-w-7xl">
        <header class="d-flex justify-content-between align-items-center mb-4 pb-3 border-bottom border-secondary">
            <div>
                <h1 class="h3 fw-bold text-white mb-1">DocFinder Catalog</h1>
                <p class="text-secondary mb-0">Interactive index of libraries, symbols, and direct documentation links.</p>
            </div>
            <div class="w-25">
                <input type="text" id="searchInput" class="form-control search-box" placeholder="Filter symbols, packages, or files...">
            </div>
        </header>

        <div id="cardsContainer">
            __CARDS_HTML__
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
</html>"""


def generate_html_report(packages: List[PackageReport], output_path: Path) -> None:
    cards = []
    for pkg in sorted(packages, key=lambda p: (len(p.used_symbols) == 0, p.dist_name)):
        sym_rows = []
        for sym, usages in sorted(pkg.used_symbols.items(), key=lambda x: len(x[1]), reverse=True):
            doc_link = pkg.symbol_doc_links.get(sym, pkg.doc_url)
            locs = "<br>".join(
                f"<code>{escape(u.file_path)}:{u.line_number}</code>" for u in usages[:5]
            )
            if len(usages) > 5:
                locs += f"<br><small class='text-muted'>+{len(usages)-5} more</small>"

            sym_rows.append(f"""
            <tr>
                <td><span class="symbol-code">{escape(sym)}</span></td>
                <td><span class="badge badge-count">{len(usages)}</span></td>
                <td><a href="{escape(doc_link, quote=True)}" target="_blank" rel="noopener">Open Official Docs ↗</a></td>
                <td><small>{locs}</small></td>
            </tr>
            """)

        rows_html = "".join(sym_rows) if sym_rows else "<tr><td colspan='4' class='text-muted text-center py-3'>Declared dependency, but no direct symbol calls detected in scanned source files.</td></tr>"

        cards.append(f"""
        <div class="card pkg-card shadow-sm">
            <div class="card-header bg-transparent border-bottom border-secondary d-flex justify-content-between align-items-center py-3">
                <div>
                    <h4 class="h5 mb-1 text-white fw-bold">{escape(pkg.dist_name)} <span class="badge badge-pkg fs-6">{escape(pkg.version_spec)}</span></h4>
                    <small class="text-secondary">Import root: <code>{escape(pkg.import_name)}</code> | Source: {escape(pkg.doc_source_type)}</small>
                </div>
                <div>
                    <a href="{escape(pkg.doc_url, quote=True)}" target="_blank" rel="noopener" class="btn btn-sm btn-outline-info">Main Package Docs ↗</a>
                </div>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-dark table-hover mb-0 align-middle">
                        <thead>
                            <tr class="text-secondary text-uppercase fs-7">
                                <th style="width: 30%">Symbol / Class</th>
                                <th style="width: 10%">Usages</th>
                                <th style="width: 30%">Direct Documentation Link</th>
                                <th style="width: 30%">Code Locations</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        """)

    html = HTML_TEMPLATE.replace("__CARDS_HTML__", "\n".join(cards))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
