import ast
import tempfile
import unittest
from pathlib import Path

from docfinder.models import SymbolUsage
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


if __name__ == "__main__":
    unittest.main()
