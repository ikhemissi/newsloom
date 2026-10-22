from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "name", ["newsloom_core", "newsloom_ingestion", "newsloom_enrichment", "newsloom_mcp"]
)
def test_workspace_packages_import(name: str) -> None:
    assert import_module(name).__doc__
