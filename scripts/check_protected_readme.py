#!/usr/bin/env python3
"""Fail when the protected KDAF README changes without an explicit baseline update."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROTECTED_README_SHA256 = "ac3a2e5bc7e4997647b871342b763b4870cfe421b0531e523ca9e45440842843"


def main() -> int:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    actual = hashlib.sha256(readme.read_bytes()).hexdigest()
    if actual != PROTECTED_README_SHA256:
        raise SystemExit(
            "README.md differs from the protected research/evidence baseline. "
            "Move the change to a separately approved review or deliberately update the baseline. "
            f"Expected {PROTECTED_README_SHA256}, received {actual}."
        )
    print(f"Protected README verified: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
