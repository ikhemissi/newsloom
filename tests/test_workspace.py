from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "name",
    [
        "newsloom_agent",
        "newsloom_core",
        "newsloom_ingestion",
        "newsloom_enrichment",
        "newsloom_mcp",
        "newsloom_platform",
    ],
)
def test_workspace_packages_import(name: str) -> None:
    assert import_module(name).__doc__
