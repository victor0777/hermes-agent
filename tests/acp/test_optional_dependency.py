import importlib.util

import pytest


def test_acp_optional_dependency_available_or_skipped():
    if importlib.util.find_spec("acp") is None:
        pytest.skip("agent-client-protocol optional dependency is not installed")
