"""Embed the source identity in wheels and preserve it through source archives."""
import importlib.util
import json
from pathlib import Path
import tempfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == 'editable':
            return
        source = Path(self.root) / 'src' / 'papergraph' / 'build_identity.py'
        spec = importlib.util.spec_from_file_location('papergraph_build_identity', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        identity = module.build_source_identity(Path(self.root))
        self._temporary = tempfile.TemporaryDirectory(prefix='papergraph-build-identity-')
        manifest = Path(self._temporary.name) / '_build_info.json'
        manifest.write_text(json.dumps(identity, sort_keys=True) + '\n', encoding='utf-8')
        destination = 'papergraph/_build_info.json' if self.target_name == 'wheel' else 'src/papergraph/_build_info.json'
        build_data['force_include'][str(manifest)] = destination

    def finalize(self, version, build_data, artifact_path):
        if hasattr(self, '_temporary'):
            self._temporary.cleanup()
