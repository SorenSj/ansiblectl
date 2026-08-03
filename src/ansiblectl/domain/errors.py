"""Typed failures that can cross layer boundaries safely."""


class DomainError(Exception):
    """Base class for expected failures caused by invalid domain operations."""
