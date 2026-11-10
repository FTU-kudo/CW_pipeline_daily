"""Fail-closed guard for publishing source-derived market data.

Broker/API permission is separate from the Vnstock package license. This project
must not emit source-derived payloads under the public ``docs/`` tree unless a
current, explicit written-authorization record is available for every source.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from . import config

DEFAULT_MANIFEST = config.ROOT / "output" / "legal" / "data-redistribution-authorization.json"
REQUIRED_TRUE = ("public_display", "public_redistribution", "derived_data_redistribution")
REQUIRED_TEXT = ("source", "data_owner", "exchange", "written_approval_reference", "terms_url")


class PublicationNotAuthorized(RuntimeError):
    """Raised when an output path is public but rights evidence is absent/invalid."""


def manifest_path() -> Path:
    return Path(os.environ.get("CW_DATA_RIGHTS_MANIFEST", str(DEFAULT_MANIFEST))).expanduser()


def validate_manifest(path: Path | None = None, *, today: date | None = None,
                      source: str | None = None) -> dict:
    """Load and validate the local authorization record; never infer approval."""
    path = Path(path) if path else manifest_path()
    today = today or date.today()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublicationNotAuthorized(
            f"No written data-publication authorization record at {path}. "
            "Keep provider-derived data local/private; do not publish to GitHub Pages."
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationNotAuthorized(f"Cannot read authorization record {path}: {exc}") from exc

    missing = [key for key in REQUIRED_TEXT if not str(manifest.get(key, "")).strip()]
    missing += [key for key in REQUIRED_TRUE if manifest.get(key) is not True]
    if missing:
        raise PublicationNotAuthorized(
            "Authorization record is incomplete; missing/false: " + ", ".join(missing)
        )
    try:
        valid_until = date.fromisoformat(str(manifest["valid_until"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicationNotAuthorized("Authorization record needs valid_until as YYYY-MM-DD") from exc
    if valid_until < today:
        raise PublicationNotAuthorized(f"Data-publication authorization expired on {valid_until}")
    if source and str(manifest["source"]).strip().lower() != source.strip().lower():
        raise PublicationNotAuthorized(
            f"Authorization is for source {manifest['source']!r}, not configured source {source!r}"
        )
    return manifest


def assert_private_data_path(path: Path, *, repo_root: Path | None = None) -> None:
    """Ingestion/cache roots must never be placed under the public Pages tree."""
    repo_root = Path(repo_root or config.ROOT).resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    candidate = candidate.resolve()
    public_root = (repo_root / "docs").resolve()
    try:
        candidate.relative_to(public_root)
    except ValueError:
        return
    raise PublicationNotAuthorized(
        f"Refusing to place private source data under the public docs tree: {candidate}"
    )


def assert_public_output_allowed(out_dir: Path, *, repo_root: Path | None = None) -> None:
    """Block generated data under the Pages tree unless authorization is current."""
    repo_root = Path(repo_root or config.ROOT).resolve()
    destination = Path(out_dir).expanduser()
    if not destination.is_absolute():
        destination = repo_root / destination
    destination = destination.resolve()
    public_root = (repo_root / "docs").resolve()
    try:
        destination.relative_to(public_root)
    except ValueError:
        return
    source = os.environ.get("VNSTOCK_SOURCE", "").strip()
    if not source:
        raise PublicationNotAuthorized(
            "VNSTOCK_SOURCE is unset; public data builds require an explicitly authorized source."
        )
    validate_manifest(source=source)
