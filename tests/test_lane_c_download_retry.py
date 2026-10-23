"""Official-source streaming retries must never accept partial publisher files."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from probe_lane_c_sources import download


class FakeResponse:
    url = "https://nrc.uscg.mil/FOIAFiles/CY25.xlsx"

    def __init__(self, chunks, fail=False):
        self.chunks = chunks
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, _):
        yield from self.chunks
        if self.fail:
            raise requests.exceptions.ConnectionError("official stream reset")


class FakeSession:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, *args, **kwargs):
        assert kwargs["stream"] is True
        assert args[0].startswith("https://nrc.uscg.mil/")
        return self.response


def test_interrupted_original_download_removes_partial_and_retries_exact_bytes():
    original = b"SECOND-COMPLETE-PUBLISHER-RESPONSE" * 80
    first = FakeSession(FakeResponse([b"untrusted-partial" * 90], fail=True))
    second = FakeSession(FakeResponse([original]))
    with tempfile.TemporaryDirectory() as tmp, patch(
        "probe_lane_c_sources.requests.Session", side_effect=[first,second]
    ) as session, patch("probe_lane_c_sources.sleep", return_value=None) as backoff:
        output = Path(tmp)/"publisher.xlsx"
        size, digest = download("https://nrc.uscg.mil/FOIAFiles/CY25.xlsx", 100000, output)
        assert size == len(original)
        assert digest == hashlib.sha256(original).hexdigest()
        assert output.read_bytes() == original
        assert session.call_count == 2
        assert backoff.call_count == 1


def test_three_failures_leave_no_partial_source_or_success_receipt():
    incomplete = FakeSession(FakeResponse([b"x"*2048], fail=True))
    with tempfile.TemporaryDirectory() as tmp, patch(
        "probe_lane_c_sources.requests.Session", return_value=incomplete
    ) as session, patch("probe_lane_c_sources.sleep", return_value=None):
        output = Path(tmp)/"publisher.xlsx"
        with pytest.raises(requests.exceptions.ConnectionError):
            download("https://nrc.uscg.mil/FOIAFiles/CY25.xlsx", 100000, output)
        assert session.call_count == 3
        assert not output.exists()


def test_oversized_publisher_file_fails_closed_without_retry_or_partial_file():
    response = FakeSession(FakeResponse([b"x"*2048]))
    with tempfile.TemporaryDirectory() as tmp, patch(
        "probe_lane_c_sources.requests.Session", return_value=response
    ) as session:
        output = Path(tmp)/"publisher.xlsx"
        with pytest.raises(ValueError, match="safety limit"):
            download("https://nrc.uscg.mil/FOIAFiles/CY25.xlsx", 1024, output)
        assert session.call_count == 1
        assert not output.exists()
