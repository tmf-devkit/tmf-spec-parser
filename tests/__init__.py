"""Tests for the __init__ module."""

from tmf_spec_parser import __author__, __version__


def test_version_string():
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_author():
    assert __author__ == "Manoj Chavan"
