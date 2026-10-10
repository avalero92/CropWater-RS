"""Beta 1 packaging consistency checks; scientific baselines remain frozen."""
import json
import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_distribution_version_matches_app_version():
    source = (ROOT / 'cropwater_rs.py').read_text(encoding='utf-8')
    app_version = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', source, re.M).group(1)
    packaging = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    metadata = json.loads((ROOT / 'config/software_metadata.template.json').read_text(encoding='utf-8'))
    assert packaging['project']['version'] == app_version
    assert metadata['version'] == app_version
    assert f'Version {app_version}' in metadata['preferred_citation']


def test_required_runtime_dependencies_declared():
    packaging = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    deps = packaging['project']['dependencies']
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    assert set(deps) == set(requirements)
