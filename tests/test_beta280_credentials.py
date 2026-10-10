from qt_credentials import parse_credentials
import pytest

def test_plain_credentials():
    assert parse_credentials('CLIENT_ID=abc\nCLIENT_SECRET=xyz') == ('abc','xyz')

def test_env_credentials():
    assert parse_credentials('# comment\nexport CDSE_CLIENT_ID="abc"\nCDSE_CLIENT_SECRET=xyz') == ('abc','xyz')

def test_missing_credentials():
    with pytest.raises(ValueError):parse_credentials('CLIENT_ID=abc')
