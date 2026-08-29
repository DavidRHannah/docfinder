import tempfile
import unittest
from pathlib import Path

from docfinder.catalog import build_package_reports, find_local_module_names
from docfinder.manifest import ManifestParser
from docfinder.models import SymbolUsage
from docfinder.resolver import DocResolverEngine


class TestFindLocalModuleNames(unittest.TestCase):
    def test_detects_flat_and_src_layouts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "src" / "mypkg").mkdir(parents=True)
            (root / "src" / "mypkg" / "__init__.py").touch()
            (root / "tests").mkdir()
            (root / "tests" / "test_x.py").touch()
            (root / "scripts").mkdir()  # no .py files -> not a module
            (root / "conftest.py").touch()
            (root / ".venv" / "lib").mkdir(parents=True)
            (root / ".venv" / "lib" / "x.py").touch()

            names = find_local_module_names(root)
            self.assertIn("mypkg", names)
            self.assertIn("tests", names)
            self.assertIn("conftest", names)
            self.assertNotIn("scripts", names)
            self.assertNotIn(".venv", names)


class TestBuildPackageReports(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        (self.root / "myapp").mkdir()
        (self.root / "myapp" / "__init__.py").touch()
        (self.root / "requirements.txt").write_text("aws-cdk-lib==2.260.0\n")

        self.parser = ManifestParser(self.root)
        # offline: these assertions must not depend on network availability.
        self.resolver = DocResolverEngine(offline=True)

    def _usage(self, symbol: str) -> SymbolUsage:
        return SymbolUsage(symbol=symbol, file_path="app.py", line_number=1)

    def test_first_party_imports_are_not_catalogued(self):
        usages = {
            "myapp.helpers.run": [self._usage("myapp.helpers.run")],
            "aws_cdk.Stack": [self._usage("aws_cdk.Stack")],
            "json.loads": [self._usage("json.loads")],
        }
        reports = build_package_reports(
            self.root, self.parser.parse(), self.parser, self.resolver, usages
        )
        self.assertNotIn("myapp", reports)
        self.assertIn("aws_cdk", reports)
        self.assertIn("json", reports)

    def test_declared_package_keeps_dist_name_and_version(self):
        usages = {"aws_cdk.Stack": [self._usage("aws_cdk.Stack")]}
        reports = build_package_reports(
            self.root, self.parser.parse(), self.parser, self.resolver, usages
        )
        report = reports["aws_cdk"]
        self.assertEqual(report.dist_name, "aws-cdk-lib")
        self.assertEqual(report.version_spec, "==2.260.0")
        self.assertEqual(list(report.used_symbols), ["aws_cdk.Stack"])
        self.assertIn(
            "aws_cdk/Stack.html", report.symbol_doc_links["aws_cdk.Stack"]
        )

    def test_undeclared_third_party_import_is_catalogued(self):
        usages = {"stix2.MemoryStore": [self._usage("stix2.MemoryStore")]}
        reports = build_package_reports(
            self.root, self.parser.parse(), self.parser, self.resolver, usages
        )
        self.assertEqual(reports["stix2"].version_spec, "imported")


if __name__ == "__main__":
    unittest.main()
