from __future__ import annotations

from typing import Any

from analytics import open_paper_exposure, open_position_by_company
from db import row


def settings() -> dict[str, Any]:
    return row("SELECT * FROM portfolio_settings WHERE id=1") or {
        "initial_equity_krw": 100_000_000,
        "max_position_weight": 0.08,
        "max_sector_weight": 0.25,
        "max_total_exposure": 1.0,
    }


def sector_open_exposure(sector: str) -> float:
    result = row(
        """
        SELECT COALESCE(SUM(t.notional_krw), 0) AS total
        FROM paper_trades t
        JOIN companies c ON c.id=t.company_id
        WHERE t.status='OPEN' AND c.sector=?
        """,
        (sector,),
    )
    return float(result["total"] if result else 0)


def validate_target_weight(company_id: int, target_weight: float) -> dict[str, Any]:
    cfg = settings()
    company = row("SELECT * FROM companies WHERE id=?", (company_id,))
    if not company:
        raise ValueError("회사 정보를 찾을 수 없음")

    equity = float(cfg["initial_equity_krw"])
    requested_weight = max(0.0, float(target_weight))
    requested_total = equity * requested_weight
    position_cap = equity * float(cfg["max_position_weight"])
    total_cap = equity * float(cfg["max_total_exposure"])
    sector_cap = equity * float(cfg["max_sector_weight"])

    current_company = open_position_by_company(company_id)
    current_total = open_paper_exposure()
    current_sector = sector_open_exposure(str(company["sector"] or ""))

    desired_total = min(requested_total, position_cap)
    add_for_company = max(0.0, desired_total - current_company)
    total_room = max(0.0, total_cap - current_total)
    sector_room = max(0.0, sector_cap - current_sector)
    allowed_add = min(add_for_company, total_room, sector_room)

    reasons: list[str] = []
    if requested_total > position_cap:
        reasons.append("종목당 최대 비중 제한으로 축소")
    if add_for_company > total_room:
        reasons.append("총 익스포저 제한으로 축소")
    if add_for_company > sector_room:
        reasons.append("섹터 비중 제한으로 축소")

    return {
        "requested_weight": requested_weight,
        "requested_total_krw": requested_total,
        "current_company_krw": current_company,
        "allowed_add_krw": allowed_add,
        "effective_target_weight": (current_company + allowed_add) / equity if equity else 0,
        "reasons": reasons,
    }
