"""Deterministic industrial-incident staging bytes; no source data in git."""
from __future__ import annotations
from contextlib import contextmanager
import csv
import gzip
import io
from pathlib import Path

@contextmanager
def gzip_csv_writer(path):
    """Stable gzip header (mtime=0, empty file name), sorted fixed-width headers."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as binary:
        with gzip.GzipFile(filename="", fileobj=binary, mode="wb", mtime=0, compresslevel=6) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as text:
                yield text
