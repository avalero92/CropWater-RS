"""Baseline metadata serializer and opt-in input integrity fingerprint."""
import hashlib
from pathlib import Path

def sha256_file(path, chunk_size=1024*1024):
    """Compute an input fingerprint without modifying the original metadata schema."""
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

def metadata_text(metadata):
    """Render the original per-parameter summary format."""
    return [f"{k}: {v}" for k,v in metadata.items()]
