from __future__ import annotations

import gzip
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"

os.environ.setdefault("SEC_USER_AGENT", "DocFlow tests ci@example.com")
os.environ.setdefault("LLM_PROVIDER", "fake")


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    from core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def fixture_doc(name_prefix: str) -> bytes:
    path = next(FIXTURES.rglob(f"{name_prefix}*.htm.gz"))
    return gzip.decompress(path.read_bytes())


@pytest.fixture(scope="session")
def aapl_text() -> str:
    from processing.parse import html_to_text

    return html_to_text(fixture_doc("aapl-20250927"))


@pytest.fixture(scope="session")
def msft_text() -> str:
    from processing.parse import html_to_text

    return html_to_text(fixture_doc("msft-20250630"))
