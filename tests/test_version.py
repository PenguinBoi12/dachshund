import dachshund


def test_version_is_exposed() -> None:
    assert isinstance(dachshund.__version__, str)
    assert dachshund.__version__
