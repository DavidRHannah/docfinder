from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SymbolUsage:
    symbol: str
    file_path: str
    line_number: int
    context_snippet: str = ""


@dataclass
class PackageReport:
    dist_name: str
    import_name: str
    version_spec: str
    doc_url: str
    doc_source_type: str  # "intersphinx", "provider_rule", "pypi_metadata", "stdlib", "fallback"
    used_symbols: Dict[str, List[SymbolUsage]] = field(default_factory=lambda: defaultdict(list))
    symbol_doc_links: Dict[str, str] = field(default_factory=dict)
