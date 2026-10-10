from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def test_qt_entrypoint_syntax():
    ast.parse((ROOT/'cropwater_rs_qt.py').read_text(encoding='utf-8'))

def test_legacy_scientific_entrypoint_preserved():
    assert (ROOT/'cropwater_rs.py').is_file()

def test_qt_dependency_and_migration_notes():
    assert 'PySide6' in (ROOT/'requirements-qt.txt').read_text()
    assert 'presentation-only' in (ROOT/'BETA2_2_QT_MIGRATION.md').read_text()
