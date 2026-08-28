from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from docfinder.models import SymbolUsage


class CodeUsageVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, root_dir: Path, source_lines: List[str]):
        self.file_path = file_path
        self.rel_path = str(file_path.relative_to(root_dir))
        self.source_lines = source_lines
        self.import_aliases: Dict[str, str] = {}  # alias -> canonical module or symbol
        self.imported_modules: Set[str] = set()
        self.used_symbols: List[Tuple[str, int]] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            self.import_aliases[asname] = name
            self.imported_modules.add(name.split(".")[0])
            self.used_symbols.append((name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        if node.level == 0:
            self.imported_modules.add(mod.split(".")[0])
            for alias in node.names:
                full_name = f"{mod}.{alias.name}" if mod else alias.name
                asname = alias.asname or alias.name
                self.import_aliases[asname] = full_name
                self.used_symbols.append((full_name, node.lineno))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            if node.id in self.import_aliases:
                canonical = self.import_aliases[node.id]
                self.used_symbols.append((canonical, node.lineno))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        chain = self._resolve_attribute_chain(node)
        if chain:
            base_id = chain[0]
            if base_id in self.import_aliases:
                resolved_base = self.import_aliases[base_id]
                full_symbol = ".".join([resolved_base] + chain[1:])
                self.used_symbols.append((full_symbol, node.lineno))
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


class ASTProjectScanner:
    DEFAULT_EXCLUDES = {
        ".git", ".venv", "venv", "__pycache__", ".ruff_cache",
        ".pytest_cache", "site", "build", "dist", "node_modules",
        ".mypy_cache", ".eggs", ".tox"
    }

    def __init__(self, root_dir: Path, exclude_dirs: Optional[Set[str]] = None):
        self.root_dir = root_dir
        self.exclude_dirs = exclude_dirs or self.DEFAULT_EXCLUDES

    def scan(self) -> Dict[str, List[SymbolUsage]]:
        """Scans project and returns {canonical_symbol: [SymbolUsage]}."""
        symbol_map: Dict[str, List[SymbolUsage]] = defaultdict(list)

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs and not d.startswith(".")]
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            source = f.read()
                            lines = source.splitlines()

                        tree = ast.parse(source, filename=str(file_path))
                        visitor = CodeUsageVisitor(file_path, self.root_dir, lines)
                        visitor.visit(tree)

                        for sym, lineno in visitor.used_symbols:
                            snippet = lines[lineno - 1].strip() if 1 <= lineno <= len(lines) else ""
                            symbol_map[sym].append(
                                SymbolUsage(
                                    symbol=sym,
                                    file_path=visitor.rel_path,
                                    line_number=lineno,
                                    context_snippet=snippet,
                                )
                            )
                    except Exception:
                        continue

        return symbol_map
