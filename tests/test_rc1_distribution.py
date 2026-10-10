from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
class TestRC1Distribution(unittest.TestCase):
    def test_qt_entry_point_exists(self):
        self.assertTrue((ROOT / 'cropwater_rs_qt.py').is_file())
    def test_windows_builder_targets_qt(self):
        content = (ROOT / 'build_windows_rc1.bat').read_text(encoding='utf-8')
        self.assertIn('cropwater_rs_qt.py', content)
        self.assertIn('--onedir', content)
        self.assertIn('--collect-all rasterio', content)
    def test_legacy_builder_not_overwritten(self):
        self.assertTrue((ROOT / 'build_windows.bat').exists())
    def test_rc1_documented_limitations(self):
        self.assertIn('Windows executable is **not** included', (ROOT / 'RC1_RELEASE_NOTES.md').read_text(encoding='utf-8'))
if __name__ == '__main__': unittest.main()
