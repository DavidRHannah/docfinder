from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Tuple

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

try:
    from importlib.metadata import packages_distributions
except ImportError:
    packages_distributions = lambda: {}  # type: ignore


class ManifestParser:
    """Discovers declared dependencies from pyproject.toml or requirements.txt."""

    COMMON_OVERRIDES = {
        "aws-cdk-lib": "aws_cdk",
        "pyyaml": "yaml",
        "scikit-learn": "sklearn",
        "beautifulsoup4": "bs4",
        "opencv-python": "cv2",
        "pillow": "PIL",
        "python-dateutil": "dateutil",
        "typing-extensions": "typing_extensions",
        "mkdocstrings-python": "mkdocstrings_python",
        "pydantic-core": "pydantic_core",
    }

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.pkg_dist_map = self._build_dist_to_import_map()

    @staticmethod
    def _normalize(dist_name: str) -> str:
        """PEP 503 style normalisation so `Typing_Extensions` and `typing-extensions` match."""
        return re.sub(r"[-_.]+", "-", dist_name).lower()

    def _build_dist_to_import_map(self) -> Dict[str, str]:
        mapping = {}
        try:
            dist_to_pkgs = packages_distributions()
            for pkg, dists in dist_to_pkgs.items():
                for dist in dists:
                    mapping[self._normalize(dist)] = pkg
        except Exception:
            pass

        for k, v in self.COMMON_OVERRIDES.items():
            mapping[self._normalize(k)] = v
        return mapping

    def parse(self) -> Dict[str, str]:
        """Returns dict of {dist_name: version_spec}."""
        packages: Dict[str, str] = {}
        pyproject_path = self.root_dir / "pyproject.toml"
        reqs_path = self.root_dir / "requirements.txt"

        if pyproject_path.exists() and tomllib:
            try:
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)

                # [project.dependencies]
                deps = data.get("project", {}).get("dependencies", [])
                for dep in deps:
                    name, ver = self._parse_dep_line(dep)
                    if name:
                        packages[name] = ver

                # [project.optional-dependencies]
                opt_deps = data.get("project", {}).get("optional-dependencies", {})
                for group, dep_list in opt_deps.items():
                    for dep in dep_list:
                        name, ver = self._parse_dep_line(dep)
                        if name and name not in packages:
                            packages[name] = ver

                # [tool.poetry.dependencies]
                poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                for name, ver in poetry_deps.items():
                    if name.lower() != "python":
                        packages[name] = str(ver)
            except Exception as e:
                print(f"[Warning] Failed parsing pyproject.toml: {e}", file=sys.stderr)

        if reqs_path.exists() and not packages:
            try:
                with open(reqs_path, "r", encoding="utf-8") as f:
                    for line in f:
                        name, ver = self._parse_dep_line(line)
                        if name:
                            packages.setdefault(name, ver)
            except Exception as e:
                print(f"[Warning] Failed parsing requirements.txt: {e}", file=sys.stderr)

        return packages

    def _parse_dep_line(self, line: str) -> Tuple[str, str]:
        """Parses one requirement line into (dist_name, version_spec).

        Returns ("", "") for anything that is not a plain named requirement:
        comments, pip options (`-r`, `-e`, `--hash`), and URL/VCS requirements.
        """
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            return "", ""

        # Drop environment markers ("requests>=2 ; python_version < '3.9'").
        line = line.split(";", 1)[0].strip()
        if not line or "://" in line:
            return "", ""

        # Drop extras ("uvicorn[standard]>=0.20").
        line = re.sub(r"\[.*?\]", "", line).strip()

        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_\-\.]*)(.*)$", line)
        if not match:
            return "", ""

        name = match.group(1).strip()
        spec = match.group(2).strip() or "latest"
        return name, spec

    def get_import_name(self, dist_name: str) -> str:
        clean = self._normalize(dist_name)
        if clean in self.pkg_dist_map:
            return self.pkg_dist_map[clean]
        return dist_name.replace("-", "_")
