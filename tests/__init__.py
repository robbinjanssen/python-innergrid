"""Tests for the Innergrid client."""

import json
from pathlib import Path
from typing import Any


def load_fixture(name: str) -> str:
    """Load a JSON fixture with the payload of a message."""
    return (Path(__file__).parent / "fixtures" / name).read_text()


def load_json(name: str) -> Any:
    """Load a JSON fixture as data."""
    return json.loads(load_fixture(name))
