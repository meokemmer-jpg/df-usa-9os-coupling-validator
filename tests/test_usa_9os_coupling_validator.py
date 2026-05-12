"""Tests fuer DF-USA-9OS-Coupling-Validator [CRUX-MK]. 10 Tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.usa_9os_coupling_validator_main import (
    USACouplingValidator,
    USACouplingStatus,
)
from src.audit_logger import AuditLogger
from src.adapter_orchestrator import main as orchestrator_main


# ============== Main: 6 Tests ==============

def test_register_coupling_healthy():
    """Test 1: Register Coupling → healthy."""
    v = USACouplingValidator(sandbox_mode=True)
    s = v.register_coupling("CAPE-CORAL-PILOT-01", "2026-05-12")
    assert s.status == USACouplingStatus.HEALTHY


def test_profit_calculation_correct():
    """Test 2: Profit korrekt: Revenue + Savings - 9OS-Cost."""
    v = USACouplingValidator(sandbox_mode=True)
    snap = v.compute_profit(
        "H1", "a", "b",
        direct_revenue_usd=10000.0,
        avoided_ota_commission_usd=1800.0,
        nine_os_cost_usd=600.0,
    )
    # 10000 + 1800 - 600 = 11200
    assert snap.profit_usd == 11200.0


def test_profit_negative_input_raises():
    """Test 3: Negative inputs raise."""
    v = USACouplingValidator(sandbox_mode=True)
    with pytest.raises(ValueError):
        v.compute_profit("H1", "a", "b", -100.0, 0.0, 0.0)


def test_guarantee_met_when_profit_above_threshold():
    """Test 4: Profit >= threshold → guarantee_met=True."""
    v = USACouplingValidator(sandbox_mode=True)
    check = v.check_guarantee("H1", "a", "b", 1200.0, 600.0, 100)
    # threshold = 600 * 1.5 = 900, profit 1200 >= 900 → MET
    assert check.guarantee_met is True
    assert check.refund_eligible is False


def test_guarantee_refund_eligible_after_90_days():
    """Test 5: Profit < threshold + >=90 Tage → refund_eligible."""
    v = USACouplingValidator(sandbox_mode=True)
    check = v.check_guarantee("H1", "a", "b", 500.0, 600.0, 100)
    assert check.guarantee_met is False
    assert check.refund_eligible is True
    assert check.refund_usd > 0


def test_guarantee_not_eligible_before_90_days():
    """Test 6: < 90 Tage → NICHT refund_eligible."""
    v = USACouplingValidator(sandbox_mode=True)
    check = v.check_guarantee("H1", "a", "b", 100.0, 600.0, 60)
    assert check.refund_eligible is False
    assert check.refund_usd == 0.0


# ============== Orchestrator: 4 Tests ==============

def test_trigger_refund_blocked_without_phronesis():
    """Test 7: K_0-CRITICAL: Refund-Trigger ohne PHRONESIS_TICKET blocked."""
    v = USACouplingValidator(sandbox_mode=True)
    check = v.check_guarantee("H1", "a", "b", 100.0, 600.0, 100)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PHRONESIS_TICKET", None)
        r = v.trigger_refund(check)
        assert r["triggered"] is False
        assert r["reason"] == "phronesis_ticket_required"


def test_trigger_refund_with_phronesis_succeeds():
    """Test 8: Refund mit PHRONESIS_TICKET → triggered=True."""
    v = USACouplingValidator(sandbox_mode=True)
    check = v.check_guarantee("H1", "a", "b", 100.0, 600.0, 100)
    with patch.dict(os.environ, {"PHRONESIS_TICKET": "PT-USA-001"}, clear=False):
        r = v.trigger_refund(check)
        assert r["triggered"] is True
        assert r["phronesis_ticket"] == "PT-USA-001"


def test_audit_chain_valid(tmp_path):
    """Test 9: Audit-Chain valid."""
    a = AuditLogger(audit_path=tmp_path / "a.jsonl", secret="s")
    a.append({"e": "1"})
    a.append({"e": "2"})
    assert a.verify_chain()["valid"] is True


def test_orchestrator_main_exits_zero(monkeypatch, tmp_path):
    """Test 10: orchestrator_main() exit-code 0."""
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = orchestrator_main([])
    assert rc == 0
