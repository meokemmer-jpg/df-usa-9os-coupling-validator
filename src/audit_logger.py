"""Audit-Logger HMAC-SHA256 [CRUX-MK]."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Optional


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
            with open(self.audit_path) as f:
                lines = f.readlines()
            if not lines:
                return "GENESIS"
            return json.loads(lines[-1]).get("entry_hash", "GENESIS")
        except (json.JSONDecodeError, KeyError, OSError):
            return "GENESIS"

    def append(self, event: dict) -> str:
        entry = {
            "ts": time.time(),
            "iso_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "prev_hash": self._last_hash,
        }
        payload = json.dumps(entry, sort_keys=True).encode()
        sig = hmac.new(self.secret.encode(), payload, hashlib.sha256).hexdigest()
        entry["hmac_sha256"] = sig
        entry["entry_hash"] = hashlib.sha256((sig + self._last_hash).encode()).hexdigest()
        with open(self.audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._last_hash = entry["entry_hash"]
        return entry["entry_hash"]

    def verify_chain(self) -> dict:
        if not self.audit_path.exists():
            return {"valid": True, "entries_verified": 0, "first_corrupted": None}
        prev = "GENESIS"
        count = 0
        with open(self.audit_path) as f:
            for i, line in enumerate(f):
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    return {"valid": False, "entries_verified": count, "first_corrupted": i}
                if e.get("prev_hash") != prev:
                    return {"valid": False, "entries_verified": count, "first_corrupted": i}
                prev = e.get("entry_hash", "")
                count += 1
        return {"valid": True, "entries_verified": count, "first_corrupted": None}
