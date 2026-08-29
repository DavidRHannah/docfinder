import ast
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from docfinder import resolver as resolver_module
from docfinder.resolver import DocResolverEngine
from docfinder.scanner import CodeUsageVisitor


class TestDocFinder(unittest.TestCase):
    def test_code_usage_visitor_extracts_aliases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sample_code = """
import boto3
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_dynamodb as dynamodb
from stix2 import MemoryStore

class MyStack(Stack):
    def __init__(self):
        self.table = dynamodb.Table()
        self.store = MemoryStore()
        CfnOutput(self, "Output")
"""
            file_path = tmp_path / "sample.py"
            file_path.write_text(sample_code)

            lines = sample_code.splitlines()
            tree = ast.parse(sample_code)
            visitor = CodeUsageVisitor(file_path, tmp_path, lines)
            visitor.visit(tree)

            symbols = [s[0] for s in visitor.used_symbols]
            self.assertIn("aws_cdk.CfnOutput", symbols)
            self.assertIn("aws_cdk.Stack", symbols)
            self.assertIn("aws_cdk.aws_dynamodb.Table", symbols)
            self.assertIn("stix2.MemoryStore", symbols)
            self.assertIn("boto3", symbols)

    def test_resolver_cdk_routing(self):
        resolver = DocResolverEngine()
        url, doc_type = resolver.resolve_symbol("aws_cdk", "aws-cdk-lib", "aws_cdk.CfnOutput")
        self.assertIn("docs.aws.amazon.com/cdk/api/v2/python/aws_cdk/CfnOutput.html", url)
        self.assertEqual(doc_type, "provider_rule")

    def test_resolver_stdlib_routing(self):
        resolver = DocResolverEngine()
        url, doc_type = resolver.resolve_symbol("json", "json", "json.loads")
        self.assertEqual(url, "https://docs.python.org/3/library/json.html#json.loads")
        self.assertEqual(doc_type, "stdlib")

    def test_inventory_parses_multi_word_names_and_prefers_py_domain(self):
        entries = "\n".join(
            [
                "pytest py:module 0 index.html#module-$ -",
                "pytest vs python -m pytest std:label -1 explanation/pythonpath.html#pytest-vs -",
                "pytest.raises py:function 1 reference/reference.html#$ -",
            ]
        ).encode()
        payload = (
            b"# Sphinx inventory version 2\n"
            b"# Project: pytest\n"
            b"# Version: 8.0\n"
            b"# The remainder of this file is compressed using zlib.\n"
            + zlib.compress(entries)
        )

        inv = resolver_module.IntersphinxInventory("https://docs.pytest.org/en/latest/")
        with mock.patch.object(resolver_module.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = payload
            self.assertTrue(inv.load())

        # A space-separated std:label must not hijack the "pytest" module entry.
        self.assertEqual(
            inv.resolve("pytest"), "https://docs.pytest.org/en/latest/index.html#module-pytest"
        )
        self.assertEqual(
            inv.resolve("pytest.raises"),
            "https://docs.pytest.org/en/latest/reference/reference.html#pytest.raises",
        )

    def test_offline_resolver_makes_no_network_calls(self):
        resolver = DocResolverEngine(offline=True)
        with mock.patch.object(resolver_module.urllib.request, "urlopen") as urlopen:
            url, doc_type = resolver.resolve_symbol("requests", "requests", "requests.get")
        urlopen.assert_not_called()
        self.assertEqual(doc_type, "fallback")
        self.assertEqual(url, "https://pypi.org/project/requests/")

    def test_failed_lookups_are_cached_per_package(self):
        """A failing network must cost one attempt per package, not one per symbol."""
        resolver = DocResolverEngine()
        with mock.patch.object(
            resolver_module.urllib.request, "urlopen", side_effect=OSError("network unreachable")
        ) as urlopen:
            for i in range(10):
                resolver.resolve_symbol("requests", "requests", f"requests.get{i}")
        # One Intersphinx inventory attempt plus one PyPI metadata attempt.
        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
