"""Smoke test: the package must be importable."""


def test_package_imports() -> None:
    import validator

    assert hasattr(validator, "__version__")
    assert validator.__version__ == "0.0.0"
