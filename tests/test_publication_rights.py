from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from cwintel.rights import (
    PublicationNotAuthorized,
    assert_private_data_path,
    assert_public_output_allowed,
    validate_manifest,
)


def approved_record(**overrides):
    record = {
        "source": "ssi",
        "data_owner": "Provider name",
        "exchange": "Exchange name",
        "written_approval_reference": "approval-reference-held-offline",
        "terms_url": "https://example.invalid/terms",
        "public_display": True,
        "public_redistribution": True,
        "derived_data_redistribution": True,
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
    }
    record.update(overrides)
    return record


def test_missing_authorization_fails_closed(tmp_path):
    with pytest.raises(PublicationNotAuthorized, match="No written"):
        validate_manifest(tmp_path / "missing.json")


def test_valid_authorization_is_source_scoped(tmp_path):
    path = tmp_path / "rights.json"
    path.write_text(json.dumps(approved_record()), encoding="utf-8")
    assert validate_manifest(path, source="SSI")["source"] == "ssi"
    with pytest.raises(PublicationNotAuthorized, match="not configured source"):
        validate_manifest(path, source="tcbs")


def test_expired_or_incomplete_authorization_is_rejected(tmp_path):
    path = tmp_path / "rights.json"
    path.write_text(json.dumps(approved_record(valid_until="2000-01-01")), encoding="utf-8")
    with pytest.raises(PublicationNotAuthorized, match="expired"):
        validate_manifest(path)
    path.write_text(json.dumps(approved_record(public_redistribution=False)), encoding="utf-8")
    with pytest.raises(PublicationNotAuthorized, match="public_redistribution"):
        validate_manifest(path)


def test_non_public_output_does_not_need_rights(tmp_path):
    repo = tmp_path / "repo"
    assert_public_output_allowed(repo / "output" / "private-data", repo_root=repo)
    assert_private_data_path(repo / "output" / "private-data", repo_root=repo)


def test_ingestion_cannot_write_under_public_docs(tmp_path):
    repo = tmp_path / "repo"
    with pytest.raises(PublicationNotAuthorized, match="Refusing to place private source data"):
        assert_private_data_path(repo / "docs" / "data", repo_root=repo)


def test_public_output_requires_source_and_rights(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    monkeypatch.delenv("VNSTOCK_SOURCE", raising=False)
    with pytest.raises(PublicationNotAuthorized, match="VNSTOCK_SOURCE is unset"):
        assert_public_output_allowed(repo / "docs" / "data", repo_root=repo)

    rights = tmp_path / "rights.json"
    rights.write_text(json.dumps(approved_record()), encoding="utf-8")
    monkeypatch.setenv("VNSTOCK_SOURCE", "ssi")
    monkeypatch.setenv("CW_DATA_RIGHTS_MANIFEST", str(rights))
    assert_public_output_allowed(repo / "docs" / "data", repo_root=repo)
