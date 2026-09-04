from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit_logger import REQUIRED_9OS, AuditLogger, validate_usa_9os_coupling


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _coupled_systems() -> list[dict]:
    return [
        {
            "name": name,
            "status": "active",
            "integration": "nine_os_api",
            "last_successful_event_id": f"evt-{name}",
        }
        for name in REQUIRED_9OS
    ]


def test_usa_9os_coupling_validator_discriminates_adversarial_file_input(tmp_path):
    accepted_evidence = tmp_path / "accepted.json"
    adversarial_evidence = tmp_path / "adversarial.json"
    audit_path = tmp_path / "audit.jsonl"

    _write_json(
        accepted_evidence,
        {
            "property_id": "CAPE-CORAL-PILOT-01",
            "country": "US",
            "systems": _coupled_systems(),
        },
    )
    adversarial_systems = _coupled_systems()
    adversarial_systems = [
        system for system in adversarial_systems if system["name"] != "analytics"
    ]
    adversarial_systems[0] = {
        **adversarial_systems[0],
        "integration": "manual_csv_export",
    }
    _write_json(
        adversarial_evidence,
        {
            "property_id": "CAPE-CORAL-PILOT-01",
            "country": "CA",
            "systems": adversarial_systems,
        },
    )

    accepted = validate_usa_9os_coupling(
        accepted_evidence, audit_path=audit_path, secret="test-secret"
    )
    adversarial = validate_usa_9os_coupling(
        adversarial_evidence, audit_path=audit_path, secret="test-secret"
    )

    assert accepted["accepted"] is True
    assert adversarial["accepted"] is False
    assert accepted["classification"] != adversarial["classification"]
    assert accepted["coverage_ratio"] > adversarial["coverage_ratio"]
    assert accepted["missing_systems"] == []
    assert adversarial["missing_systems"] == ["analytics"]
    assert adversarial["failed_systems"] == ["booking"]
    assert accepted["evidence_hash"] != adversarial["evidence_hash"]

    verification = AuditLogger(audit_path=audit_path, secret="test-secret").verify_chain()
    assert verification == {
        "valid": True,
        "entries_verified": 2,
        "first_corrupted": None,
    }
