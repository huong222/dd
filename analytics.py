from __future__ import annotations

from collections import defaultdict
from typing import Any

from db import row, rows


def _latest_lh(project_id: int) -> dict[str, Any] | None:
    return row(
        "SELECT * FROM lh_assessments WHERE project_id=? ORDER BY assessed_at DESC, id DESC LIMIT 1",
        (project_id,),
    )


def _latest_local(project_id: int) -> dict[str, Any] | None:
    return row(
        "SELECT * FROM local_fundamentals WHERE project_id=? ORDER BY assessed_at DESC, id DESC LIMIT 1",
        (project_id,),
    )


def _latest_market(company_id: int) -> dict[str, Any] | None:
    return row(
        "SELECT * FROM market_snapshots WHERE company_id=? ORDER BY ts DESC, id DESC LIMIT 1",
        (company_id,),
    )


def company_overview() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    companies = rows("SELECT * FROM companies ORDER BY name")

    for company in companies:
        exposures = rows(
            """
            SELECT e.*, p.name AS project_name
            FROM exposures e
            JOIN projects p ON p.id=e.project_id
            WHERE e.company_id=?
            ORDER BY p.name
            """,
            (company["id"],),
        )
        project_ids = sorted({int(x["project_id"]) for x in exposures})
        conditional_base = sum(float(x["benefit_base_krw"] or 0) for x in exposures)
        expected_base = 0.0
        exposure_conf = []
        lh_probs = []
        local_scores = []
        distress_scores = []

        for exposure in exposures:
            pid = int(exposure["project_id"])
            lh = _latest_lh(pid)
            probability = float(lh["probability"] or 0) if lh else 0.0
            expected_base += float(exposure["benefit_base_krw"] or 0) * probability
            exposure_conf.append(float(exposure["confidence"] or 0))

        for pid in project_ids:
            lh = _latest_lh(pid)
            if lh:
                lh_probs.append(float(lh["probability"] or 0))
            local = _latest_local(pid)
            if local:
                keys = [
                    "industrial_cycle_score",
                    "employment_score",
                    "population_score",
                    "housing_supply_score",
                    "infrastructure_score",
                    "rental_demand_score",
                    "asset_quality_score",
                ]
                local_scores.append(sum(float(local[k] or 0) for k in keys) / len(keys))
                distress_scores.append(float(local["distress_score"] or 0))

        market_cap = float(company["market_cap_krw"] or 0)
        market = _latest_market(int(company["id"]))
        expected_ratio = expected_base / market_cap if market_cap > 0 else 0.0

        result.append(
            {
                "company_id": company["id"],
                "ticker": company["ticker"],
                "company": company["name"],
                "projects": len(project_ids),
                "market_cap_krw": market_cap,
                "conditional_benefit_base_krw": conditional_base,
                "probability_weighted_benefit_krw": expected_base,
                "benefit_to_market_cap_pct": expected_ratio * 100,
                "avg_exposure_confidence_pct": (sum(exposure_conf) / len(exposure_conf) * 100) if exposure_conf else 0,
                "avg_lh_probability_pct": (sum(lh_probs) / len(lh_probs) * 100) if lh_probs else 0,
                "local_fundamental_score": (sum(local_scores) / len(local_scores)) if local_scores else None,
                "distress_score": (sum(distress_scores) / len(distress_scores)) if distress_scores else None,
                "last_price": float(market["price"] or 0) if market else None,
                "daily_structure": market["structure_daily"] if market else None,
                "event_reaction_pct": float(market["event_reaction_pct"] or 0) if market else None,
            }
        )

    return sorted(result, key=lambda x: x["benefit_to_market_cap_pct"], reverse=True)


def company_projects(company_id: int) -> list[dict[str, Any]]:
    exposures = rows(
        """
        SELECT e.*, p.name AS project_name, p.province, p.city, p.district,
               p.total_units, p.unsold_units, p.completed_unsold_units, p.developer
        FROM exposures e
        JOIN projects p ON p.id=e.project_id
        WHERE e.company_id=?
        ORDER BY p.name
        """,
        (company_id,),
    )
    for item in exposures:
        item["lh"] = _latest_lh(int(item["project_id"]))
        item["local"] = _latest_local(int(item["project_id"]))
    return exposures


def open_paper_exposure() -> float:
    result = row("SELECT COALESCE(SUM(notional_krw), 0) AS total FROM paper_trades WHERE status='OPEN'")
    return float(result["total"] if result else 0)


def open_position_by_company(company_id: int) -> float:
    result = row(
        "SELECT COALESCE(SUM(notional_krw), 0) AS total FROM paper_trades WHERE status='OPEN' AND company_id=?",
        (company_id,),
    )
    return float(result["total"] if result else 0)
