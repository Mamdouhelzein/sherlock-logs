"""Fetch only the author's trusted v1 artifact, pinned before deserialization."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

BASE = (
    "https://github.com/Mamdouhelzein/sherlock-logs/releases/download/shadow-model-v1"
)
HASHES = {
    "model.joblib": "027e70e789fd5e28bb9e0a1caf589b922f891a6e04749708f2096b3174ed23a5",
    "experiment.json": "6b17c9845971e32654cb61ee56439d9a6c27a9814ee11cd0ccef5ff430501043",
    "feature_schema.json": "dd9f8abd2369e7a3bc226df8a6ad444312b370396d7f211aa390c06da9287b32",
}


def fetch(output=Path("/models")):
    output.mkdir(parents=True, exist_ok=False)
    for name in (*HASHES, "metadata.json"):
        with urlopen(f"{BASE}/{name}", timeout=60) as response:
            body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError("Model release file exceeds size limit")
        if name in HASHES and hashlib.sha256(body).hexdigest() != HASHES[name]:
            raise ValueError("Model release checksum mismatch")
        if name == "metadata.json" and json.loads(body)["sha256"] != HASHES:
            raise ValueError("Model release metadata mismatch")
        (output / name).write_bytes(body)


if __name__ == "__main__":
    fetch()
