from __future__ import annotations

import kdaf


def test_import_kdaf_exposes_package_metadata() -> None:
    metadata = kdaf.package_metadata()

    assert kdaf.__version__ == "0.2.0"
    assert metadata.name == "kdaf"
    assert metadata.version
