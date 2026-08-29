import tempfile
import unittest
from pathlib import Path

from docfinder.manifest import ManifestParser


class TestManifestParser(unittest.TestCase):
    def _parser_for(self, filename: str, content: str) -> ManifestParser:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        root = Path(self.tmpdir.name)
        (root / filename).write_text(content)
        return ManifestParser(root)

    def test_requirements_ignores_options_and_urls(self):
        parser = self._parser_for(
            "requirements.txt",
            "\n".join(
                [
                    "# a comment",
                    "-r base.txt",
                    "-e .",
                    "--hash=sha256:abc",
                    "git+https://github.com/x/y.git#egg=y",
                    "https://example.com/pkg-1.0.tar.gz",
                    "requests>=2.0  # inline comment",
                    "uvicorn[standard]>=0.20",
                    "boto3",
                    "typing-extensions; python_version < '3.10'",
                ]
            ),
        )
        self.assertEqual(
            parser.parse(),
            {
                "requests": ">=2.0",
                "uvicorn": ">=0.20",
                "boto3": "latest",
                "typing-extensions": "latest",
            },
        )

    def test_pyproject_dependencies(self):
        parser = self._parser_for(
            "pyproject.toml",
            """
[project]
name = "demo"
dependencies = ["requests>=2.0", "aws-cdk-lib==2.260.0"]

[project.optional-dependencies]
dev = ["pytest>=7.0"]
""",
        )
        packages = parser.parse()
        self.assertEqual(packages["requests"], ">=2.0")
        self.assertEqual(packages["aws-cdk-lib"], "==2.260.0")
        self.assertEqual(packages["pytest"], ">=7.0")

    def test_import_name_normalisation_is_pep503(self):
        parser = self._parser_for("requirements.txt", "pyyaml\n")
        # Underscores, hyphens and case must all resolve to the same import name.
        for spelling in ("aws-cdk-lib", "aws_cdk_lib", "AWS-CDK-Lib"):
            self.assertEqual(parser.get_import_name(spelling), "aws_cdk")
        for spelling in ("pyyaml", "PyYAML"):
            self.assertEqual(parser.get_import_name(spelling), "yaml")

    def test_unknown_dist_falls_back_to_underscored_name(self):
        parser = self._parser_for("requirements.txt", "\n")
        self.assertEqual(parser.get_import_name("some-unknown-pkg"), "some_unknown_pkg")


if __name__ == "__main__":
    unittest.main()
