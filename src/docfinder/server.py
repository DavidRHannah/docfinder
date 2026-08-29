from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docfinder.manifest import ManifestParser
from docfinder.models import PackageReport, SymbolUsage
from docfinder.resolver import DocResolverEngine
from docfinder.scanner import ASTProjectScanner, CodeUsageVisitor


class PositionSymbolFinder(ast.NodeVisitor):
    """Locates the exact canonical symbol at a specific line and column in a Python AST."""

    def __init__(self, target_line: int, target_col: int, import_aliases: Dict[str, str]):
        self.target_line = target_line
        self.target_col = target_col
        self.import_aliases = import_aliases
        self.candidates: List[Tuple[str, Tuple[int, int, int, int], int]] = []  # (symbol, range, depth)

    @property
    def matched_symbol(self) -> Optional[str]:
        if not self.candidates:
            return None
        # Sort candidates by depth (most specific attribute chain first)
        best = max(self.candidates, key=lambda c: (c[2], len(c[0])))
        return best[0]

    @property
    def matched_range(self) -> Optional[Tuple[int, int, int, int]]:
        if not self.candidates:
            return None
        best = max(self.candidates, key=lambda c: (c[2], len(c[0])))
        return best[1]

    def visit_Name(self, node: ast.Name):
        if node.lineno == self.target_line:
            col_offset = getattr(node, "col_offset", 0)
            end_col = getattr(node, "end_col_offset", col_offset + len(node.id))
            if col_offset <= self.target_col <= end_col:
                if node.id in self.import_aliases:
                    canonical = self.import_aliases[node.id]
                    self.candidates.append((canonical, (node.lineno, col_offset, node.lineno, end_col), 1))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.lineno == self.target_line:
            col_offset = getattr(node, "col_offset", 0)
            end_col = getattr(node, "end_col_offset", col_offset + len(node.attr))
            if col_offset <= self.target_col <= end_col:
                chain = self._resolve_attribute_chain(node)
                if chain and chain[0] in self.import_aliases:
                    resolved_base = self.import_aliases[chain[0]]
                    full_symbol = ".".join([resolved_base] + chain[1:])
                    self.candidates.append((full_symbol, (node.lineno, col_offset, node.lineno, end_col), len(chain)))
        self.generic_visit(node)

    def _resolve_attribute_chain(self, node: ast.AST) -> Optional[List[str]]:
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            return list(reversed(parts))
        return None


class DocFinderServer:
    """JSON-RPC 2.0 Server for VS Code Extension Integration."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root.resolve() if workspace_root else Path.cwd().resolve()
        self.manifest_parser = ManifestParser(self.workspace_root)
        self.doc_resolver = DocResolverEngine()
        self.declared_pkgs: Dict[str, str] = {}
        self.package_reports: Dict[str, PackageReport] = {}
        self.is_initialized = False

    def initialize(self, workspace_root: Optional[str] = None) -> Dict[str, Any]:
        if workspace_root:
            self.workspace_root = Path(workspace_root).resolve()
            self.manifest_parser = ManifestParser(self.workspace_root)

        self.declared_pkgs = self.manifest_parser.parse()
        self.refresh_catalog()
        self.is_initialized = True
        return {
            "status": "initialized",
            "workspaceRoot": str(self.workspace_root),
            "declaredPackagesCount": len(self.declared_pkgs),
        }

    def refresh_catalog(self) -> Dict[str, Any]:
        ast_scanner = ASTProjectScanner(self.workspace_root)
        symbol_usages = ast_scanner.scan()

        package_reports: Dict[str, PackageReport] = {}
        for dist_name, ver in self.declared_pkgs.items():
            imp_name = self.manifest_parser.get_import_name(dist_name)
            main_url, doc_type = self.doc_resolver.resolve_symbol(imp_name, dist_name, imp_name)
            package_reports[imp_name] = PackageReport(
                dist_name=dist_name,
                import_name=imp_name,
                version_spec=ver,
                doc_url=main_url,
                doc_source_type=doc_type,
            )

        for sym, usages in symbol_usages.items():
            top_mod = sym.split(".")[0]
            if top_mod in package_reports:
                report = package_reports[top_mod]
                report.used_symbols[sym].extend(usages)
                doc_link, _ = self.doc_resolver.resolve_symbol(top_mod, report.dist_name, sym)
                report.symbol_doc_links[sym] = doc_link

        imported_tops = {sym.split(".")[0] for sym in symbol_usages.keys()}
        ignore_roots = {"src", "infra", "tests", "config", "scripts", "docfinder"}
        for top_mod in imported_tops:
            if top_mod not in package_reports and top_mod not in ignore_roots:
                main_url, doc_type = self.doc_resolver.resolve_symbol(top_mod, top_mod, top_mod)
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
                        doc_link, _ = self.doc_resolver.resolve_symbol(top_mod, top_mod, sym)
                        report.symbol_doc_links[sym] = doc_link
                package_reports[top_mod] = report

        self.package_reports = package_reports
        return {"status": "ok", "packagesCount": len(package_reports)}

    def resolve_at_position(
        self,
        file_path: str,
        line: int,
        character: int,
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolves symbol documentation at a specific file position."""
        target_path = Path(file_path)
        if not content:
            if target_path.exists():
                try:
                    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception as e:
                    return {"found": False, "error": str(e)}
            else:
                return {"found": False, "error": "File not found"}

        try:
            lines = content.splitlines()
            tree = ast.parse(content, filename=str(target_path))

            # First extract aliases
            visitor = CodeUsageVisitor(target_path, self.workspace_root, lines)
            visitor.visit(tree)

            # Then find symbol at target position
            pos_finder = PositionSymbolFinder(line, character, visitor.import_aliases)
            pos_finder.visit(tree)

            if not pos_finder.matched_symbol:
                # Fallback: check if the line has a known symbol matching word under cursor
                matched = self._fallback_line_match(lines, line, character, visitor.import_aliases)
                if matched:
                    sym, rng = matched
                    pos_finder.matched_symbol = sym
                    pos_finder.matched_range = rng

            if pos_finder.matched_symbol:
                sym = pos_finder.matched_symbol
                top_mod = sym.split(".")[0]
                dist_name = top_mod
                version_spec = "latest"

                if top_mod in self.package_reports:
                    dist_name = self.package_reports[top_mod].dist_name
                    version_spec = self.package_reports[top_mod].version_spec
                elif top_mod in self.doc_resolver.STDLIB_MODULES:
                    version_spec = "stdlib"

                doc_url, doc_type = self.doc_resolver.resolve_symbol(top_mod, dist_name, sym)

                return {
                    "found": True,
                    "symbol": sym,
                    "packageName": dist_name,
                    "version": version_spec,
                    "docUrl": doc_url,
                    "docType": doc_type,
                    "range": {
                        "startLine": pos_finder.matched_range[0] if pos_finder.matched_range else line,
                        "startCol": pos_finder.matched_range[1] if pos_finder.matched_range else character,
                        "endLine": pos_finder.matched_range[2] if pos_finder.matched_range else line,
                        "endCol": pos_finder.matched_range[3] if pos_finder.matched_range else character,
                    },
                }

        except Exception as e:
            return {"found": False, "error": str(e)}

        return {"found": False}

    def _fallback_line_match(
        self,
        lines: List[str],
        line: int,
        col: int,
        import_aliases: Dict[str, str],
    ) -> Optional[Tuple[str, Tuple[int, int, int, int]]]:
        if 1 <= line <= len(lines):
            line_str = lines[line - 1]
            for alias, canonical in import_aliases.items():
                idx = 0
                while True:
                    found_idx = line_str.find(alias, idx)
                    if found_idx == -1:
                        break
                    end_idx = found_idx + len(alias)
                    if found_idx <= col <= end_idx:
                        return canonical, (line, found_idx, line, end_idx)
                    idx = end_idx
        return None

    def get_workspace_catalog(self) -> Dict[str, Any]:
        """Returns structured data for the Sidebar TreeView and Webview."""
        packages = []
        for pkg in sorted(self.package_reports.values(), key=lambda p: (len(p.used_symbols) == 0, p.dist_name)):
            symbols = []
            for sym, usages in sorted(pkg.used_symbols.items(), key=lambda x: len(x[1]), reverse=True):
                doc_link = pkg.symbol_doc_links.get(sym, pkg.doc_url)
                symbols.append({
                    "symbol": sym,
                    "docUrl": doc_link,
                    "usageCount": len(usages),
                    "locations": [
                        {"file": u.file_path, "line": u.line_number, "snippet": u.context_snippet}
                        for u in usages
                    ],
                })
            packages.append({
                "packageName": pkg.dist_name,
                "importName": pkg.import_name,
                "version": pkg.version_spec,
                "docUrl": pkg.doc_url,
                "docType": pkg.doc_source_type,
                "symbolCount": len(pkg.used_symbols),
                "symbols": symbols,
            })
        return {"packages": packages}

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method == "initialize":
                result = self.initialize(params.get("workspaceRoot"))
            elif method == "resolveAtPosition":
                result = self.resolve_at_position(
                    file_path=params.get("filePath", ""),
                    line=int(params.get("line", 1)),
                    character=int(params.get("character", 0)),
                    content=params.get("content"),
                )
            elif method == "getWorkspaceCatalog":
                result = self.get_workspace_catalog()
            elif method == "refreshCatalog":
                result = self.refresh_catalog()
            elif method == "ping":
                result = {"pong": True}
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def serve_forever(self):
        """Standard I/O JSON Lines loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
