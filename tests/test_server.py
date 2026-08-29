import tempfile
import unittest
from pathlib import Path

from docfinder.server import DocFinderServer


class TestDocFinderServer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)

        # Create dummy pyproject.toml
        pyproject = self.workspace / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "aws-cdk-lib==2.260.0",
    "stix2==3.0.1",
]
""")
        # Create dummy python file
        sample = self.workspace / "stack.py"
        sample.write_text("""
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_dynamodb as dynamodb
import stix2

class MyStack(Stack):
    def __init__(self):
        self.table = dynamodb.Table()
        self.store = stix2.MemoryStore()
        CfnOutput(self, "Arn")
""")
        self.server = DocFinderServer(self.workspace)
        self.server.initialize()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_initialize(self):
        self.assertTrue(self.server.is_initialized)
        self.assertIn("aws-cdk-lib", self.server.declared_pkgs)
        self.assertIn("stix2", self.server.declared_pkgs)

    def test_resolve_at_position_cfn_output(self):
        # Line 10: "        CfnOutput(self, "Arn")"
        resp = self.server.resolve_at_position(
            file_path=str(self.workspace / "stack.py"),
            line=10,
            character=12,
        )
        self.assertTrue(resp.get("found"))
        self.assertEqual(resp.get("symbol"), "aws_cdk.CfnOutput")
        self.assertEqual(resp.get("packageName"), "aws-cdk-lib")
        self.assertIn("docs.aws.amazon.com/cdk/api/v2/python/aws_cdk/CfnOutput.html", resp.get("docUrl", ""))

    def test_resolve_at_position_dynamodb_table(self):
        # Line 8: "        self.table = dynamodb.Table()"
        resp = self.server.resolve_at_position(
            file_path=str(self.workspace / "stack.py"),
            line=8,
            character=28,
        )
        self.assertTrue(resp.get("found"))
        self.assertEqual(resp.get("symbol"), "aws_cdk.aws_dynamodb.Table")
        self.assertIn("docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_dynamodb/Table.html", resp.get("docUrl", ""))

    def test_json_rpc_handler(self):
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resolveAtPosition",
            "params": {
                "filePath": str(self.workspace / "stack.py"),
                "line": 10,
                "character": 12,
            },
        }
        res = self.server.handle_request(req)
        self.assertEqual(res.get("id"), 1)
        self.assertTrue(res.get("result", {}).get("found"))
        self.assertEqual(res.get("result", {}).get("symbol"), "aws_cdk.CfnOutput")

    def test_resolve_at_position_line_fallback(self):
        """Cursor on an alias that is not an AST node (here: inside a comment)."""
        sample = self.workspace / "commented.py"
        sample.write_text("import stix2\n\n# stix2 is used below\n")
        resp = self.server.resolve_at_position(
            file_path=str(sample),
            line=3,
            character=4,
        )
        self.assertIsNone(resp.get("error"))
        self.assertTrue(resp.get("found"))
        self.assertEqual(resp.get("symbol"), "stix2")

    def test_resolve_at_position_on_blank_area_is_not_found(self):
        resp = self.server.resolve_at_position(
            file_path=str(self.workspace / "stack.py"),
            line=6,
            character=0,
        )
        self.assertFalse(resp.get("found"))

    def test_refresh_catalog_picks_up_manifest_changes(self):
        (self.workspace / "pyproject.toml").write_text("""
[project]
name = "demo"
version = "0.1.0"
dependencies = ["stix2==3.0.1"]
""")
        self.server.refresh_catalog()
        self.assertNotIn("aws-cdk-lib", self.server.declared_pkgs)
        self.assertIn("stix2", self.server.declared_pkgs)

    def test_get_workspace_catalog(self):
        catalog = self.server.get_workspace_catalog()
        packages = catalog.get("packages", [])
        pkg_names = [p["packageName"] for p in packages]
        self.assertIn("aws-cdk-lib", pkg_names)
        self.assertIn("stix2", pkg_names)


if __name__ == "__main__":
    unittest.main()
