"""USA 9OS Coupling Validator Core [CRUX-MK].

USD-Profit-Garantie + Refund-Mechanik fuer HeyLou-USA + 9OS-NEXT-USA.
K_0-DIREKT: KEINE Refund-Triggers ohne PHRONESIS_TICKET.

[CRUX-MK]
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class USACouplingStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED_HEYLOU_USA = "degraded_heylou_usa"
    DEGRADED_9OS_USA = "degraded_9os_usa"
    BOTH_DEGRADED = "both_degraded"
    NOT_COUPLED = "not_coupled"


@dataclass
class USACouplingState:
    hotel_id: str
    heylou_usa_active: bool
    nine_os_usa_active: bool
    coupling_start_iso: str
    last_health_check_ts: float = field(default_factory=time.time)
    consecutive_unhealthy_checks: int = 0

    @property
    def status(self) -> USACouplingStatus:
        if not self.heylou_usa_active and not self.nine_os_usa_active:
            return USACouplingStatus.NOT_COUPLED
        if self.heylou_usa_active and not self.nine_os_usa_active:
            return USACouplingStatus.DEGRADED_9OS_USA
        if not self.heylou_usa_active and self.nine_os_usa_active:
            return USACouplingStatus.DEGRADED_HEYLOU_USA
        return USACouplingStatus.HEALTHY


@dataclass(frozen=True)
class ProfitSnapshotUSD:
    hotel_id: str
    period_start_iso: str
    period_end_iso: str
    direct_revenue_usd: float
    avoided_ota_commission_usd: float
    nine_os_cost_usd: float
    profit_usd: float
    profit_margin_pct: float


@dataclass(frozen=True)
class USGuaranteeCheck:
    hotel_id: str
    period_start_iso: str
    period_end_iso: str
    profit_usd: float
    threshold_usd: float
    guarantee_met: bool
    refund_eligible: bool
    refund_usd: float
    coupling_days: int


class USACouplingValidator:
    def __init__(self, sandbox_mode: Optional[bool] = None):
        if sandbox_mode is None:
            sandbox_mode = (
                os.environ.get("DF_USA_9OS_COUPLING_REAL_ENABLED", "false").lower() != "true"
            )
        self.sandbox_mode = sandbox_mode
        self._states: dict[str, USACouplingState] = {}

    def register_coupling(
        self,
        hotel_id: str,
        coupling_start_iso: str,
        heylou_usa_active: bool = True,
        nine_os_usa_active: bool = True,
    ) -> USACouplingState:
        s = USACouplingState(
            hotel_id=hotel_id,
            heylou_usa_active=heylou_usa_active,
            nine_os_usa_active=nine_os_usa_active,
            coupling_start_iso=coupling_start_iso,
        )
        self._states[hotel_id] = s
        return s

    def compute_profit(
        self,
        hotel_id: str,
        period_start_iso: str,
        period_end_iso: str,
        direct_revenue_usd: float,
        avoided_ota_commission_usd: float,
        nine_os_cost_usd: float,
    ) -> ProfitSnapshotUSD:
        if direct_revenue_usd < 0 or avoided_ota_commission_usd < 0 or nine_os_cost_usd < 0:
            raise ValueError("All USD inputs must be >= 0")
        profit = direct_revenue_usd + avoided_ota_commission_usd - nine_os_cost_usd
        denom = direct_revenue_usd if direct_revenue_usd > 0 else 0.0
        margin = (profit / denom * 100.0) if denom > 0 else 0.0
        return ProfitSnapshotUSD(
            hotel_id=hotel_id,
            period_start_iso=period_start_iso,
            period_end_iso=period_end_iso,
            direct_revenue_usd=direct_revenue_usd,
            avoided_ota_commission_usd=avoided_ota_commission_usd,
            nine_os_cost_usd=nine_os_cost_usd,
            profit_usd=round(profit, 2),
            profit_margin_pct=round(margin, 2),
        )

    def check_guarantee(
        self,
        hotel_id: str,
        period_start_iso: str,
        period_end_iso: str,
        profit_usd: float,
        nine_os_cost_usd: float,
        coupling_days: int,
        threshold_multiplier: float = 1.5,
    ) -> USGuaranteeCheck:
        if threshold_multiplier <= 0:
            raise ValueError("threshold_multiplier must be > 0")
        if coupling_days < 0:
            raise ValueError("coupling_days must be >= 0")
        threshold = nine_os_cost_usd * threshold_multiplier
        guarantee_met = profit_usd >= threshold
        refund_eligible = (not guarantee_met) and coupling_days >= 90
        if refund_eligible:
            shortfall = threshold - profit_usd
            refund = min(shortfall, nine_os_cost_usd)
            refund = max(0.0, refund)
        else:
            refund = 0.0
        return USGuaranteeCheck(
            hotel_id=hotel_id,
            period_start_iso=period_start_iso,
            period_end_iso=period_end_iso,
            profit_usd=profit_usd,
            threshold_usd=threshold,
            guarantee_met=guarantee_met,
            refund_eligible=refund_eligible,
            refund_usd=round(refund, 2),
            coupling_days=coupling_days,
        )

    def trigger_refund(self, check: USGuaranteeCheck) -> dict:
        """K_0-CRITICAL: requires PHRONESIS_TICKET."""
        if not check.refund_eligible:
            return {"triggered": False, "reason": "not_eligible"}
        ticket = os.environ.get("PHRONESIS_TICKET")
        if not ticket:
            return {
                "triggered": False,
                "reason": "phronesis_ticket_required",
            }
        return {
            "triggered": True,
            "refund_usd": check.refund_usd,
            "phronesis_ticket": ticket,
            "hotel_id": check.hotel_id,
        }
