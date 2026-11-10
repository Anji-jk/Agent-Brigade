import importlib

import pytest


@pytest.mark.parametrize("name", ["core", "pipeline", "backend"])
def test_package_imports(name):
    assert importlib.import_module(name) is not None
