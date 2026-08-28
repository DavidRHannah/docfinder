from __future__ import annotations

import json
import sys
import urllib.request
import zlib
from typing import Any, Dict, Optional, Set, Tuple


class IntersphinxInventory:
    """Parses Sphinx objects.inv files to map symbols to exact documentation anchors."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + "/"
        self.inv_url = self.base_url + "objects.inv"
        self.items: Dict[str, str] = {}  # symbol -> full_url
        self.loaded = False

    def load(self, timeout: float = 4.0) -> bool:
        try:
            req = urllib.request.Request(self.inv_url, headers={"User-Agent": "DocFinder/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read()

            lines = content.split(b"\n")
            if len(lines) < 5 or not lines[0].startswith(b"# Sphinx inventory"):
                return False

            decompressed = zlib.decompress(b"\n".join(lines[4:]))
            text = decompressed.decode("utf-8", errors="ignore")

            for line in text.splitlines():
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[0]
                    uri = parts[3]
                    if uri.endswith("$"):
                        uri = uri[:-1] + name
                    self.items[name] = self.base_url + uri

            self.loaded = True
            return True
        except Exception:
            return False

    def resolve(self, symbol: str) -> Optional[str]:
        if symbol in self.items:
            return self.items[symbol]
        parts = symbol.split(".")
        for i in range(len(parts) - 1, 0, -1):
            parent = ".".join(parts[:i])
            if parent in self.items:
                return self.items[parent]
        return None


class DocResolverEngine:
    """Resolves symbols to documentation URLs via Intersphinx, Provider Rules, and PyPI."""

    KNOWN_INVENTORIES = {
        "stix2": "https://stix2.readthedocs.io/en/latest/",
        "trafilatura": "https://trafilatura.readthedocs.io/en/latest/",
        "feedparser": "https://feedparser.readthedocs.io/en/latest/",
        "httpx": "https://www.python-httpx.org/",
        "pytest": "https://docs.pytest.org/en/latest/",
        "pydantic": "https://docs.pydantic.dev/latest/",
        "requests": "https://requests.readthedocs.io/en/latest/",
        "neo4j": "https://neo4j.com/docs/api/python-driver/current/",
        "mkdocs": "https://www.mkdocs.org/",
        "python": "https://docs.python.org/3/",
    }

    STDLIB_MODULES: Set[str] = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else {
        "os", "sys", "re", "json", "typing", "collections", "datetime", "functools",
        "dataclasses", "pathlib", "hashlib", "time", "uuid", "zlib", "unittest",
        "urllib", "ast", "subprocess", "threading", "copy", "difflib", "email",
        "gzip", "importlib", "inspect", "itertools", "logging", "types", "argparse",
        "decimal", "concurrent"
    }

    def __init__(self):
        self.inventories: Dict[str, IntersphinxInventory] = {}
        self.pypi_cache: Dict[str, Dict[str, Any]] = {}

    def get_inventory(self, pkg_name: str) -> Optional[IntersphinxInventory]:
        if pkg_name in self.inventories:
            return self.inventories[pkg_name]
        if pkg_name in self.KNOWN_INVENTORIES:
            inv = IntersphinxInventory(self.KNOWN_INVENTORIES[pkg_name])
            if inv.load():
                self.inventories[pkg_name] = inv
                return inv
        return None

    def resolve_symbol(self, top_module: str, dist_name: str, symbol: str) -> Tuple[str, str]:
        """Returns (doc_url, doc_type)."""

        # 1. Python Standard Library
        if top_module in self.STDLIB_MODULES:
            parts = symbol.split(".")
            mod = parts[0]
            if len(parts) == 1:
                return f"https://docs.python.org/3/library/{mod}.html", "stdlib"
            return f"https://docs.python.org/3/library/{mod}.html#{symbol}", "stdlib"

        # 2. AWS CDK Custom Rule
        if top_module == "aws_cdk":
            return self._resolve_aws_cdk(symbol)

        # 3. Constructs Custom Rule
        if top_module == "constructs":
            parts = symbol.split(".")
            cls_name = parts[-1] if len(parts) > 1 else ""
            if cls_name and cls_name != "constructs":
                return f"https://docs.aws.amazon.com/cdk/api/v2/python/constructs/{cls_name}.html", "provider_rule"
            return "https://docs.aws.amazon.com/cdk/api/v2/python/constructs.html", "provider_rule"

        # 4. Boto3 Custom Rule
        if top_module == "boto3":
            return "https://boto3.amazonaws.com/v1/documentation/api/latest/index.html", "provider_rule"

        # 5. Anthropic SDK Rule
        if top_module == "anthropic":
            return "https://docs.anthropic.com/en/api/client-sdks#python", "provider_rule"

        # 6. Intersphinx lookup
        inv = self.get_inventory(top_module)
        if inv and inv.loaded:
            match = inv.resolve(symbol)
            if match:
                return match, "intersphinx"

        # 7. Neo4j Custom Rule
        if top_module == "neo4j":
            return "https://neo4j.com/docs/api/python-driver/current/", "provider_rule"

        # 8. PyPI Metadata lookup
        pypi_info = self._get_pypi_metadata(dist_name or top_module)
        if pypi_info:
            urls = pypi_info.get("info", {}).get("project_urls") or {}
            doc_url = (
                urls.get("Documentation")
                or urls.get("documentation")
                or urls.get("Docs")
                or urls.get("Homepage")
                or urls.get("homepage")
                or urls.get("Source")
                or pypi_info.get("info", {}).get("home_page")
                or pypi_info.get("info", {}).get("project_url")
                or f"https://pypi.org/project/{dist_name}/"
            )
            return doc_url, "pypi_metadata"

        # 9. Generic Fallback
        return f"https://pypi.org/project/{dist_name or top_module}/", "fallback"

    def _resolve_aws_cdk(self, symbol: str) -> Tuple[str, str]:
        parts = symbol.split(".")
        if len(parts) == 1:
            return "https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.html", "provider_rule"
        if len(parts) == 2:
            return f"https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk/{parts[1]}.html", "provider_rule"
        if len(parts) >= 3:
            submod = parts[1]
            cls_name = parts[2]
            return f"https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.{submod}/{cls_name}.html", "provider_rule"
        return f"https://docs.aws.amazon.com/cdk/api/v2/python/{symbol}.html", "provider_rule"

    def _get_pypi_metadata(self, pkg_name: str) -> Optional[Dict[str, Any]]:
        if pkg_name in self.pypi_cache:
            return self.pypi_cache[pkg_name]
        try:
            url = f"https://pypi.org/pypi/{pkg_name}/json"
            req = urllib.request.Request(url, headers={"User-Agent": "DocFinder/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode())
                self.pypi_cache[pkg_name] = data
                return data
        except Exception:
            return None
