from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "research.sqlite3"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                published_at TEXT,
                retrieved_at TEXT DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                market_cap_krw REAL DEFAULT 0,
                net_debt_krw REAL DEFAULT 0,
                sector TEXT DEFAULT '건설',
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                province TEXT,
                city TEXT,
                district TEXT,
                address TEXT,
                developer TEXT,
                total_units INTEGER DEFAULT 0,
                unsold_units INTEGER DEFAULT 0,
                completed_unsold_units INTEGER DEFAULT 0,
                completion_date TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS exposures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                receivable_krw REAL DEFAULT 0,
                pf_guarantee_krw REAL DEFAULT 0,
                loan_krw REAL DEFAULT 0,
                direct_inventory_krw REAL DEFAULT 0,
                benefit_low_krw REAL DEFAULT 0,
                benefit_base_krw REAL DEFAULT 0,
                benefit_high_krw REAL DEFAULT 0,
                confidence REAL DEFAULT 0.5 CHECK(confidence >= 0 AND confidence <= 1),
                source_id INTEGER REFERENCES sources(id),
                notes TEXT,
                UNIQUE(project_id, company_id, role)
            );

            CREATE TABLE IF NOT EXISTS lh_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                round_name TEXT NOT NULL,
                eligibility TEXT NOT NULL,
                probability REAL DEFAULT 0 CHECK(probability >= 0 AND probability <= 1),
                expected_units_low INTEGER DEFAULT 0,
                expected_units_base INTEGER DEFAULT 0,
                expected_units_high INTEGER DEFAULT 0,
                purchase_low_krw REAL DEFAULT 0,
                purchase_base_krw REAL DEFAULT 0,
                purchase_high_krw REAL DEFAULT 0,
                reasoning TEXT,
                source_id INTEGER REFERENCES sources(id),
                assessed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS local_fundamentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                industrial_cycle_score REAL DEFAULT 50,
                employment_score REAL DEFAULT 50,
                population_score REAL DEFAULT 50,
                housing_supply_score REAL DEFAULT 50,
                infrastructure_score REAL DEFAULT 50,
                rental_demand_score REAL DEFAULT 50,
                asset_quality_score REAL DEFAULT 50,
                distress_score REAL DEFAULT 50,
                notes TEXT,
                source_id INTEGER REFERENCES sources(id),
                assessed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                price REAL DEFAULT 0,
                structure_daily TEXT,
                structure_60m TEXT,
                volume_ratio REAL DEFAULT 1,
                event_reaction_pct REAL DEFAULT 0,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS llm_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                model TEXT,
                action TEXT NOT NULL,
                confidence REAL DEFAULT 0 CHECK(confidence >= 0 AND confidence <= 1),
                target_weight REAL DEFAULT 0 CHECK(target_weight >= 0 AND target_weight <= 1),
                horizon TEXT,
                thesis TEXT,
                invalidation TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                notional_krw REAL NOT NULL,
                qty REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                entry_reason TEXT,
                exit_reason TEXT,
                pnl_krw REAL,
                return_pct REAL
            );

            CREATE TABLE IF NOT EXISTS portfolio_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                initial_equity_krw REAL NOT NULL DEFAULT 100000000,
                max_position_weight REAL NOT NULL DEFAULT 0.08,
                max_sector_weight REAL NOT NULL DEFAULT 0.25,
                max_total_exposure REAL NOT NULL DEFAULT 1.0
            );
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO portfolio_settings
            (id, initial_equity_krw, max_position_weight, max_sector_weight, max_total_exposure)
            VALUES (1, 100000000, 0.08, 0.25, 1.0)
            """
        )
        conn.commit()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return int(cur.lastrowid or 0)


def rows(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return [dict(row) for row in cur.fetchall()]


def row(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    result = rows(sql, params)
    return result[0] if result else None
