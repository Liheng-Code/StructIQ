import shutil

import pytest

from structiq.core.config import tool_path


def _soffice():
    return tool_path("libreoffice") or shutil.which("soffice") or shutil.which("libreoffice")


def pytest_collection_modifyitems(config, items):
    """Skip tests marked requires_soffice when LibreOffice cannot be found."""
    if _soffice():
        return
    skip = pytest.mark.skip(reason="LibreOffice not found (set tools.libreoffice in config/paths.yaml)")
    for item in items:
        if "requires_soffice" in item.keywords:
            item.add_marker(skip)
