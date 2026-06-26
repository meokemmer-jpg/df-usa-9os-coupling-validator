"""Adapter-Orchestrator (LaunchAgent-Entry) [CRUX-MK]."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    hotel_id: str
    coupling_status: str
    profit_usd: float
    guarantee_met: bool
    refund_eligible: bool
    audit_hash: str
    sandbox_mode: bool


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    if Path("/tmp/df-usa-9os-coupling-validator.stop").exists():
        return 0

    from .usa_9os_coupling_validator_main import USACouplingValidator
    from .audit_logger import AuditLogger

    v = USACouplingValidator()
    audit = AuditLogger()

    # Sandbox-Demo Cape-Coral-Pilot
    state = v.register_coupling("CAPE-CORAL-PILOT-01", "2026-05-12")
    snap = v.compute_profit(
        hotel_id="CAPE-CORAL-PILOT-01",
        period_start_iso="2026-05-12",
        period_end_iso="2026-08-12",
        direct_revenue_usd=18000.0,
        avoided_ota_commission_usd=3240.0,
        nine_os_cost_usd=720.0,
    )
    check = v.check_guarantee(
        hotel_id="CAPE-CORAL-PILOT-01",
        period_start_iso="2026-05-12",
        period_end_iso="2026-08-12",
        profit_usd=snap.profit_usd,
        nine_os_cost_usd=720.0,
        coupling_days=92,
    )

    audit_hash = audit.append({
        "type": "usa_coupling_check",
        "hotel_id": "CAPE-CORAL-PILOT-01",
        "coupling_status": state.status.value,
        "profit_usd": snap.profit_usd,
        "guarantee_met": check.guarantee_met,
        "refund_eligible": check.refund_eligible,
        "sandbox_mode": v.sandbox_mode,
    })

    result = OrchestratorResult(
        hotel_id="CAPE-CORAL-PILOT-01",
        coupling_status=state.status.value,
        profit_usd=snap.profit_usd,
        guarantee_met=check.guarantee_met,
        refund_eligible=check.refund_eligible,
        audit_hash=audit_hash,
        sandbox_mode=v.sandbox_mode,
    )
    logger.info(f"USA-9OS-Coupling-Validator: {result}")
    return 0


def __df_guarded_entry():  # K16+K11-FOUNDATION-WIRED [CRUX-MK]
    sys.exit(main(sys.argv[1:]))

if __name__ == "__main__":  # K16+K11-FOUNDATION-WIRED [CRUX-MK]
    try:
        from _df_common.df_foundation import run_guarded as _rg
    except Exception:
        raise SystemExit(__df_guarded_entry())   # Foundation weg -> normal
    raise SystemExit(_rg("df-usa-9os-coupling-validator", __df_guarded_entry))   # K14+K16+K15+K11 echt
