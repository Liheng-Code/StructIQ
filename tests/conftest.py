import sys
from pathlib import Path

import pytest

from structiq.core.config import find_soffice

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))  # shared made-up fixtures


def pytest_collection_modifyitems(config, items):
    """Skip tests marked requires_soffice when LibreOffice cannot be found."""
    if find_soffice():
        return
    skip = pytest.mark.skip(reason="LibreOffice not found (set tools.libreoffice in config/paths.yaml)")
    for item in items:
        if "requires_soffice" in item.keywords:
            item.add_marker(skip)
