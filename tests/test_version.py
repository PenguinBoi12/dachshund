import dachshund


def test_version__expect_a_non_empty_string() -> None:
    assert isinstance(dachshund.__version__, str)
    assert dachshund.__version__
