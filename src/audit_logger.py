"""File-backed USA 9OS coupling validator with tamper-evident audit logging."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


REQUIRED_9OS = (
    "booking",
    "pms",
    "channel_manager",
    "revenue_management",
    "crm",
    "housekeeping",
    "payments",
    "accounting",
    "analytics",
)

USA_COUNTRY_CODES = {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}


@dataclass(frozen=True)
class CouplingValidationResult:
    property_id: str
    country: str
    accepted: bool
    classification: str
    coverage_ratio: float
    coupled_systems: tuple[str, ...]
    missing_systems: tuple[str, ...]
    failed_systems: tuple[str, ...]
    evidence_hash: str
    audit_entry_hash: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["coupled_systems"] = list(self.coupled_systems)
        data["missing_systems"] = list(self.missing_systems)
        data["failed_systems"] = list(self.failed_systems)
        return data


class AuditLogger:
    def __init__(self, audit_path: Optional[Path] = None, secret: Optional[str] = None):
        if audit_path is None:
            audit_path = Path.home() / ".df-state" / "df-usa-9os-coupling-audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path = audit_path
        self.secret = secret or os.environ.get(
            "DF_USA_9OS_COUPLING_AUDIT_SECRET", "skeleton-default-secret"
        )
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.audit_path.exists():
            return "GENESIS"
        try:
            with self.audit_path.open(encoding="utf-8") as handle:
                lines = [line for line in handle if line.strip()]
            if not lines:
                return "GENESIS"
            return json.loads(lines[-1]).get("entry_hash", "GENESIS")
        except (json.JSONDecodeError, OSError):
            return "GENESIS"

    def _signable_payload(self, entry: dict) -> bytes:
        unsigned = {
            key: value
            for key, value in entry.items()
            if key not in {"hmac_sha256", "entry_hash"}
        }
        return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def append(self, event: dict) -> str:
        entry = {
            "ts": time.time(),
            "iso_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "prev_hash": self._last_hash,
        }
        sig = hmac.new(self.secret.encode(), self._signable_payload(entry), hashlib.sha256)
        entry["hmac_sha256"] = sig.hexdigest()
        entry["entry_hash"] = hashlib.sha256(
            (entry["hmac_sha256"] + self._last_hash).encode("utf-8")
        ).hexdigest()
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        self._last_hash = entry["entry_hash"]
        return entry["entry_hash"]

    def verify_chain(self) -> dict:
        if not self.audit_path.exists():
            return {"valid": True, "entries_verified": 0, "first_corrupted": None}

        prev = "GENESIS"
        count = 0
        with self.audit_path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return {"valid": False, "entries_verified": count, "first_corrupted": index}

                expected_sig = hmac.new(
                    self.secret.encode(),
                    self._signable_payload(entry),
                    hashlib.sha256,
                ).hexdigest()
                expected_hash = hashlib.sha256((expected_sig + prev).encode("utf-8")).hexdigest()
                if (
                    entry.get("prev_hash") != prev
                    or entry.get("hmac_sha256") != expected_sig
                    or entry.get("entry_hash") != expected_hash
                ):
                    return {"valid": False, "entries_verified": count, "first_corrupted": index}
                prev = expected_hash
                count += 1
        return {"valid": True, "entries_verified": count, "first_corrupted": None}


class USANineOSCouplingValidator:
    def __init__(self, audit_logger: AuditLogger):
        self.audit_logger = audit_logger

    def validate_file(self, evidence_path: Path) -> CouplingValidationResult:
        payload = self._load_evidence(evidence_path)
        raw_bytes = evidence_path.read_bytes()
        evidence_hash = hashlib.sha256(raw_bytes).hexdigest()

        systems = self._systems_by_name(payload.get("systems", []))
        country = str(payload.get("country", "")).strip()
        property_id = str(payload.get("property_id", "")).strip()
        coupled = tuple(name for name in REQUIRED_9OS if self._is_coupled(systems.get(name)))
        missing = tuple(name for name in REQUIRED_9OS if name not in systems)
        failed = tuple(
            name
            for name in REQUIRED_9OS
            if name in systems and not self._is_coupled(systems[name])
        )
        coverage_ratio = len(coupled) / len(REQUIRED_9OS)
        is_usa = country.upper() in USA_COUNTRY_CODES
        accepted = bool(property_id) and is_usa and coverage_ratio == 1.0
        classification = "usa_9os_coupled" if accepted else "rejected_coupling_gap"

        audit_hash = self.audit_logger.append(
            {
                "mission": "df-usa-9os-coupling-validator",
                "property_id": property_id,
                "evidence_hash": evidence_hash,
                "accepted": accepted,
                "classification": classification,
                "coverage_ratio": coverage_ratio,
                "missing_systems": list(missing),
                "failed_systems": list(failed),
            }
        )
        return CouplingValidationResult(
            property_id=property_id,
            country=country,
            accepted=accepted,
            classification=classification,
            coverage_ratio=coverage_ratio,
            coupled_systems=coupled,
            missing_systems=missing,
            failed_systems=failed,
            evidence_hash=evidence_hash,
            audit_entry_hash=audit_hash,
        )

    def _load_evidence(self, evidence_path: Path) -> dict:
        if not evidence_path.exists():
            raise FileNotFoundError(evidence_path)
        with evidence_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("evidence root must be a JSON object")
        return payload

    def _systems_by_name(self, systems: object) -> dict[str, dict]:
        if not isinstance(systems, list):
            raise ValueError("systems must be a list")
        indexed = {}
        for system in systems:
            if not isinstance(system, dict):
                raise ValueError("each system must be an object")
            name = str(system.get("name", "")).strip().lower()
            if name:
                indexed[name] = system
        return indexed

    def _is_coupled(self, system: Optional[dict]) -> bool:
        if not system:
            return False
        return (
            str(system.get("status", "")).lower() == "active"
            and str(system.get("integration", "")).lower() == "nine_os_api"
            and bool(system.get("last_successful_event_id"))
        )


def validate_usa_9os_coupling(evidence_path: Path, audit_path: Path, secret: str) -> dict:
    logger = AuditLogger(audit_path=audit_path, secret=secret)
    return USANineOSCouplingValidator(logger).validate_file(evidence_path).to_dict()
