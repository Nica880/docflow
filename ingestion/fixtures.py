"""Offline EDGAR: serve recorded responses from disk through an httpx transport.

Layout: ``<root>/<host>/<url path>`` (optionally ``.gz``). Used by CI and the offline demo so the
pipeline runs end to end without touching sec.gov. ``scripts/record_fixtures.py`` creates them.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx


def fixture_path(root: Path, url: httpx.URL | str) -> Path:
    u = httpx.URL(str(url))
    rel = u.path.lstrip("/") or "index"
    return root / u.host / rel


class FixtureTransport(httpx.BaseTransport):
    def __init__(self, root: Path) -> None:
        self.root = root

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = fixture_path(self.root, request.url)
        for candidate in (path, path.with_name(path.name + ".gz")):
            if candidate.is_file():
                data = candidate.read_bytes()
                if candidate.suffix == ".gz":
                    data = gzip.decompress(data)
                ctype = "application/json" if path.suffix == ".json" else "text/html"
                return httpx.Response(200, content=data, headers={"Content-Type": ctype})
        return httpx.Response(
            404, content=json.dumps({"error": f"no fixture for {request.url}"}).encode()
        )
