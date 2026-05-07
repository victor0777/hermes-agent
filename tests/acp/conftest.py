import importlib.util

_HAS_ACP = importlib.util.find_spec("acp") is not None


def pytest_ignore_collect(collection_path, config):
    if _HAS_ACP:
        return False
    return (
        collection_path.name.startswith("test_")
        and collection_path.name != "test_optional_dependency.py"
        and collection_path.suffix == ".py"
    )
