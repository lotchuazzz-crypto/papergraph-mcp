"""A version bump must update the actual CI consumer entrypoint too."""
import importlib.util
from importlib.metadata import version
from pathlib import Path


def test_installed_ci_smoke_targets_the_current_package_version():
    path = Path(__file__).parents[1] / 'scripts/smoke_installed_reference_quality.py'
    spec = importlib.util.spec_from_file_location('installed_smoke_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.EXPECTED_VERSION == version('papergraph-mcp')
