"""Construct concrete application dependencies at the CLI boundary."""

from ansiblectl import __version__
from ansiblectl.application.status import DefaultStatusService, StatusService


def build_status_service() -> StatusService:
    """Create the status use case and its dependencies for a CLI invocation."""

    return DefaultStatusService(version=__version__)
