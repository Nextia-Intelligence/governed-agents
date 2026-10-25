import pytest

from bluekite import shop


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh shop in a temporary folder, for every test."""
    monkeypatch.setenv("BLUEKITE_HOME", str(tmp_path))
    shop.reset()
    connection = shop.connect()
    yield connection
    connection.close()
