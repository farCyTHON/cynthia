"""Tests for the package version exposed by `cynthia --version`."""
from __future__ import annotations

import re

from typer.testing import CliRunner

import cynthia
from cynthia.cli import app, get_version

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

runner = CliRunner()


def test_get_version_returns_non_empty_string():
    version = get_version()
    assert isinstance(version, str)
    assert version.strip() != ""


def test_get_version_is_semantic():
    assert SEMVER.match(get_version())


def test_get_version_reads_package_dunder():
    assert get_version() == cynthia.__version__


def test_version_flag_prints_name_and_tagline():
    for flag in ("--version", "-v"):
        result = runner.invoke(app, [flag])
        assert result.exit_code == 0
        assert f"CYNTHIA {get_version()}" in result.output
        assert "AI-native developer intelligence CLI" in result.output
