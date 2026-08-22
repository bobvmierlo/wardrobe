"""Shared test setup.

The app reads its settings (and opens the SQLite database) at import time and
seeds an admin on startup, so the environment must point at a throwaway data
directory *before* ``app`` is imported anywhere. Setting it here in conftest —
which pytest loads before collecting tests — guarantees that ordering.
"""

import os
import tempfile

os.environ.setdefault("WARDROBE_DATA_DIR", tempfile.mkdtemp(prefix="wardrobe-test-"))
os.environ.setdefault("WARDROBE_SECRET_KEY", "test-secret")
os.environ.setdefault("WARDROBE_ADMIN_USERNAME", "admin")
os.environ.setdefault("WARDROBE_ADMIN_PASSWORD", "changeme")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
