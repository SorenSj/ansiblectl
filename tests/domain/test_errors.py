"""Domain unit tests."""

from ansiblectl.domain.errors import DomainError


def test_domain_error_is_an_expected_exception() -> None:
    assert isinstance(DomainError("invalid workspace"), Exception)
