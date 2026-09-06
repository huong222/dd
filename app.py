from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from analytics import company_overview, company_projects
from db import execute, init_db, row, rows
from risk import settings, validate_target_weight

APP_VERSION = "LH-Research-V0.1"
init_db()

st.set_page_config(page_title=APP_VERSION, layout="wide")
st.title("LH Event Research Lab")
st.caption("정책 이벤트 리서치 + 가상매매 · 실제 주문 전송 없음 · V0.1 Truth DB")


def krw(value: float | int | None) -> str:
    if value is None:
        return "-"
    value = float(value)
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:,.1f}억원"
    if abs(value) >= 10_000:
        return f"{value / 10_000:,.1f}만원"
    return f"{value:,.0f}원"


def company_options() -> dict[str, int]:
    return {f"{r['name']} ({r['ticker']})": int(r["id"]) for r in rows("SELECT * FROM companies ORDER BY name")}


def project_options() -> dict[str, int]:
    return {f"{r['name']} · {r['province'] or ''} {r['city'] or ''}": int(r["id"]) for r in rows("SELECT * FROM projects ORDER BY name")}


def source_options() -> dict[str, int | None]:
    result: dict[str, int | None] = {"출처 미지정": None}
    for r in rows("SELECT * FROM sources ORDER BY id DESC"):
        result[f"#{r['id']} {r['source_type']} · {r['title']}"] = int(r["id"])
    return result


def rerun_success(message: str) -> None:
    st.success(message)
    st.rerun()


tab_dash, tab_truth, tab_lh, tab_market, tab_paper, tab_data = st.tabs(
    ["대시보드", "Truth DB", "LH·지역", "시장·AI", "가상매매", "원본 데이터"]
)

with tab_dash:
    overview = company_overview()
    if not overview:
        st.info("아직 회사 데이터가 없습니다. `Truth DB` 탭에서 회사와 사업장을 먼저 등록하세요.")
    else:
        df = pd.DataFrame(overview)
        show = df[
            [
                "ticker",
                "company",
                "projects",
                "probability_weighted_benefit_krw",
                "benefit_to_market_cap_pct",
                "avg_exposure_confidence_pct",
                "avg_lh_probability_pct",
                "local_fundamental_score",
                "distress_score",
                "last_price",
                "daily_structure",
                "event_reaction_pct",
            ]
        ].rename(
            columns={
                "ticker": "티커",
                "company": "회사",
                "projects": "관련사업장",
                "probability_weighted_benefit_krw": "확률가중 예상효과(원)",
                "benefit_to_market_cap_pct": "시총대비 예상효과(%)",
                "avg_exposure_confidence_pct": "노출근거 확신도(%)",
                "avg_lh_probability_pct": "평균 LH 확률(%)",
                "local_fundamental_score": "지역 펀더멘털",
                "distress_score": "Distress",
                "last_price": "최근가격",
                "daily_structure": "일봉구조",
                "event_reaction_pct": "이벤트후 반응(%)",
            }
        )
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption("`확률가중 예상효과` = 각 사업장 상장사 예상효과 × 해당 사업장 최신 LH 확률. 매입가격 자체를 수혜액으로 간주하지 않음.")

        choices = company_options()
        selected_label = st.selectbox("회사 상세", list(choices))
        company_id = choices[selected_label]
        company = row("SELECT * FROM companies WHERE id=?", (company_id,))
        projects = company_projects(company_id)
        if company:
            c1, c2, c3 = st.columns(3)
            c1.metric("시가총액", krw(company["market_cap_krw"]))
            c2.metric("순차입금", krw(company["net_debt_krw"]))
            c3.metric("연결 사업장", len({p["project_id"] for p in projects}))
        if projects:
            detail_rows = []
            for item in projects:
                lh = item.get("lh") or {}
                local = item.get("local") or {}
                detail_rows.append(
                    {
                        "사업장": item["project_name"],
                        "역할": item["role"],
                        "준공후미분양": item["completed_unsold_units"],
                        "PF보증": item["pf_guarantee_krw"],
                        "공사미수금": item["receivable_krw"],
                        "조건부 예상효과": item["benefit_base_krw"],
                        "LH확률": lh.get("probability"),
                        "LH기준회차": lh.get("round_name"),
                        "산업": local.get("industrial_cycle_score"),
                        "인프라": local.get("infrastructure_score"),
                        "임대수요": local.get("rental_demand_score"),
                    }
                )
            st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

with tab_truth:
    st.subheader("1. 출처")
    with st.form("source_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        source_type = c1.selectbox("유형", ["LH", "DART", "국토부", "지자체", "회사IR", "분양공고", "기사", "기타"])
        source_title = c2.text_input("문서/자료명")
        source_url = st.text_input("URL")
        published_at = st.text_input("발행일", placeholder="YYYY-MM-DD")
        source_notes = st.text_area("메모")
        if st.form_submit_button("출처 저장"):
            if not source_title.strip():
                st.error("자료명을 입력하세요.")
            else:
                execute(
                    "INSERT INTO sources(source_type,title,url,published_at,notes) VALUES(?,?,?,?,?)",
                    (source_type, source_title.strip(), source_url.strip(), published_at.strip(), source_notes.strip()),
                )
                rerun_success("출처 저장 완료")

    st.subheader("2. 상장사")
    with st.form("company_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ticker = c1.text_input("티커/종목코드")
        company_name = c2.text_input("회사명")
        c3, c4 = st.columns(2)
        market_cap = c3.number_input("시가총액(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
        net_debt = c4.number_input("순차입금(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
        sector = st.text_input("섹터", value="건설")
        company_notes = st.text_area("메모")
        if st.form_submit_button("회사 저장"):
            if not ticker.strip() or not company_name.strip():
                st.error("티커와 회사명이 필요합니다.")
            else:
                try:
                    execute(
                        "INSERT INTO companies(ticker,name,market_cap_krw,net_debt_krw,sector,notes) VALUES(?,?,?,?,?,?)",
                        (ticker.strip(), company_name.strip(), market_cap, net_debt, sector.strip(), company_notes.strip()),
                    )
                    rerun_success("회사 저장 완료")
                except Exception as exc:
                    st.error(f"회사 저장 실패: {exc}")

    st.subheader("3. 아파트/사업장")
    with st.form("project_form", clear_on_submit=True):
        project_name = st.text_input("사업장/단지명")
        c1, c2, c3 = st.columns(3)
        province = c1.text_input("시/도")
        city = c2.text_input("시/군")
        district = c3.text_input("구/읍/면")
        address = st.text_input("주소")
        developer = st.text_input("시행사/SPC")
        c4, c5, c6 = st.columns(3)
        total_units = c4.number_input("총 세대", min_value=0, step=1)
        unsold_units = c5.number_input("미분양", min_value=0, step=1)
        completed_unsold = c6.number_input("준공후 미분양", min_value=0, step=1)
        completion_date = st.text_input("준공일", placeholder="YYYY-MM-DD")
        project_notes = st.text_area("메모")
        if st.form_submit_button("사업장 저장"):
            if not project_name.strip():
                st.error("사업장명이 필요합니다.")
            else:
                execute(
                    """
                    INSERT INTO projects(name,province,city,district,address,developer,total_units,unsold_units,completed_unsold_units,completion_date,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_name.strip(), province.strip(), city.strip(), district.strip(), address.strip(), developer.strip(),
                        int(total_units), int(unsold_units), int(completed_unsold), completion_date.strip(), project_notes.strip(),
                    ),
                )
                rerun_success("사업장 저장 완료")

    st.subheader("4. 사업장 ↔ 상장사 경제적 노출")
    cos, pros, sos = company_options(), project_options(), source_options()
    if not cos or not pros:
        st.info("회사와 사업장을 먼저 등록해야 합니다.")
    else:
        with st.form("exposure_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            company_label = c1.selectbox("상장사", list(cos))
            project_label = c2.selectbox("사업장", list(pros))
            role = st.selectbox("관계", ["시공사", "직접소유", "PF보증", "대여", "공사미수금", "기타"])
            c3, c4, c5, c6 = st.columns(4)
            receivable = c3.number_input("공사미수금(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            pf_guarantee = c4.number_input("PF보증/채무위험(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            loan = c5.number_input("대여금(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            inventory = c6.number_input("직접재고 노출(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            st.markdown("**LH 매입이 실제 발생했을 때 상장사 경제적 효과 시나리오**")
            b1, b2, b3 = st.columns(3)
            benefit_low = b1.number_input("보수(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            benefit_base = b2.number_input("기준(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            benefit_high = b3.number_input("낙관(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            confidence = st.slider("노출 관계 근거 확신도", 0.0, 1.0, 0.5, 0.05)
            source_label = st.selectbox("근거 출처", list(sos))
            exposure_notes = st.text_area("인과관계 메모", placeholder="예: LH 매입대금 -> 시행사 PF 상환 -> 당사 미수금 회수/보증 감소")
            if st.form_submit_button("경제적 노출 저장"):
                try:
                    execute(
                        """
                        INSERT INTO exposures(project_id,company_id,role,receivable_krw,pf_guarantee_krw,loan_krw,direct_inventory_krw,
                                              benefit_low_krw,benefit_base_krw,benefit_high_krw,confidence,source_id,notes)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            pros[project_label], cos[company_label], role, receivable, pf_guarantee, loan, inventory,
                            benefit_low, benefit_base, benefit_high, confidence, sos[source_label], exposure_notes.strip(),
                        ),
                    )
                    rerun_success("노출 저장 완료")
                except Exception as exc:
                    st.error(f"저장 실패: {exc}")

with tab_lh:
    pros, sos = project_options(), source_options()
    st.subheader("LH 매입 가능성")
    if not pros:
        st.info("사업장을 먼저 등록하세요.")
    else:
        with st.form("lh_form", clear_on_submit=True):
            project_label = st.selectbox("사업장", list(pros), key="lh_project")
            c1, c2 = st.columns(2)
            round_name = c1.text_input("LH 공고/회차", placeholder="예: 2026 4차")
            eligibility = c2.selectbox("기본 적격", ["PASS", "UNKNOWN", "FAIL"])
            probability = st.slider("선정/계약 확률 추정", 0.0, 1.0, 0.5, 0.05)
            u1, u2, u3 = st.columns(3)
            units_low = u1.number_input("예상 매입 세대 · 보수", min_value=0, step=1)
            units_base = u2.number_input("기준", min_value=0, step=1)
            units_high = u3.number_input("낙관", min_value=0, step=1)
            p1, p2, p3 = st.columns(3)
            purchase_low = p1.number_input("예상 LH 매입액 · 보수(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            purchase_base = p2.number_input("기준(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            purchase_high = p3.number_input("낙관(원)", min_value=0.0, step=100_000_000.0, format="%.0f")
            lh_source = st.selectbox("근거 출처", list(sos), key="lh_source")
            reasoning = st.text_area("판단 근거")
            if st.form_submit_button("LH 평가 저장"):
                execute(
                    """
                    INSERT INTO lh_assessments(project_id,round_name,eligibility,probability,expected_units_low,expected_units_base,
                                               expected_units_high,purchase_low_krw,purchase_base_krw,purchase_high_krw,reasoning,source_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        pros[project_label], round_name.strip(), eligibility, probability, int(units_low), int(units_base), int(units_high),
                        purchase_low, purchase_base, purchase_high, reasoning.strip(), sos[lh_source],
                    ),
                )
                rerun_success("LH 평가 저장 완료")

        st.subheader("지역 펀더멘털")
        with st.form("local_form", clear_on_submit=True):
            project_label = st.selectbox("사업장", list(pros), key="local_project")
            st.caption("0=매우 약함, 50=중립, 100=매우 강함. Distress는 100일수록 현재 스트레스가 큼.")
            c1, c2, c3, c4 = st.columns(4)
            industrial = c1.slider("산업 사이클", 0, 100, 50)
            employment = c2.slider("고용", 0, 100, 50)
            population = c3.slider("인구/가구", 0, 100, 50)
            housing_supply = c4.slider("주택 공급여건", 0, 100, 50)
            c5, c6, c7, c8 = st.columns(4)
            infrastructure = c5.slider("교통/생활 인프라", 0, 100, 50)
            rental = c6.slider("임대수요", 0, 100, 50)
            asset_quality = c7.slider("단지/자산 품질", 0, 100, 50)
            distress = c8.slider("현재 Distress", 0, 100, 50)
            local_source = st.selectbox("근거 출처", list(sos), key="local_source")
            local_notes = st.text_area("지역 메모", placeholder="주력산업, 고용, 순이동, 향후 입주물량, 실거래/전월세, 역/도로/학교/병원/상권 등")
            if st.form_submit_button("지역 평가 저장"):
                execute(
                    """
                    INSERT INTO local_fundamentals(project_id,industrial_cycle_score,employment_score,population_score,housing_supply_score,
                                                   infrastructure_score,rental_demand_score,asset_quality_score,distress_score,notes,source_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        pros[project_label], industrial, employment, population, housing_supply, infrastructure, rental,
                        asset_quality, distress, local_notes.strip(), sos[local_source],
                    ),
                )
                rerun_success("지역 평가 저장 완료")

with tab_market:
    cos = company_options()
    st.subheader("시장구조 스냅샷")
    if not cos:
        st.info("회사를 먼저 등록하세요.")
    else:
        with st.form("market_form", clear_on_submit=True):
            company_label = st.selectbox("회사", list(cos), key="market_company")
            c1, c2, c3 = st.columns(3)
            price = c1.number_input("가격", min_value=0.0, step=1.0)
            structure_daily = c2.selectbox("일봉 구조", ["UNKNOWN", "HH/HL", "LH/LL", "TRANSITION", "RANGE"])
            structure_60m = c3.selectbox("60분 구조", ["UNKNOWN", "HH/HL", "LH/LL", "TRANSITION", "RANGE"])
            c4, c5 = st.columns(2)
            volume_ratio = c4.number_input("거래량 / 기준 거래량", min_value=0.0, value=1.0, step=0.1)
            reaction = c5.number_input("이벤트 이후 주가반응(%)", value=0.0, step=0.1)
            market_notes = st.text_area("메모")
            if st.form_submit_button("시장 스냅샷 저장"):
                execute(
                    "INSERT INTO market_snapshots(company_id,price,structure_daily,structure_60m,volume_ratio,event_reaction_pct,notes) VALUES(?,?,?,?,?,?,?)",
                    (cos[company_label], price, structure_daily, structure_60m, volume_ratio, reaction, market_notes.strip()),
                )
                rerun_success("시장 스냅샷 저장 완료")

        st.subheader("LLM 투자판단 레코드")
        st.caption("현재 V0.1에서는 수동 입력. 다음 단계에서 LLM API가 동일 스키마로 자동 작성하게 됨.")
        with st.form("decision_form", clear_on_submit=True):
            company_label = st.selectbox("회사", list(cos), key="decision_company")
            c1, c2, c3 = st.columns(3)
            model = c1.text_input("모델", placeholder="예: Gemini / Groq")
            action = c2.selectbox("판단", ["BUY", "HOLD", "SELL", "AVOID"])
            confidence = c3.slider("확신도", 0.0, 1.0, 0.5, 0.05)
            target_weight = st.slider("제안 목표비중", 0.0, 0.30, 0.05, 0.01)
            horizon = st.text_input("예상 보유기간", placeholder="예: 3~15일")
            thesis = st.text_area("투자 논리")
            invalidation = st.text_area("판단을 뒤집을 조건")
            if st.form_submit_button("AI 판단 저장"):
                decision_id = execute(
                    """
                    INSERT INTO llm_decisions(company_id,model,action,confidence,target_weight,horizon,thesis,invalidation)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (cos[company_label], model.strip(), action, confidence, target_weight, horizon.strip(), thesis.strip(), invalidation.strip()),
                )
                if action == "BUY":
                    preview = validate_target_weight(cos[company_label], target_weight)
                    st.success(
                        f"판단 #{decision_id} 저장 · LLM 제안 {krw(preview['requested_total_krw'])} -> Risk Engine 신규 허용 {krw(preview['allowed_add_krw'])}"
                    )
                    if preview["reasons"]:
                        st.warning(" / ".join(preview["reasons"]))
                else:
                    st.success(f"판단 #{decision_id} 저장")

with tab_paper:
    cfg = settings()
    st.subheader("가상 포트폴리오 제한")
    with st.form("risk_settings"):
        c1, c2, c3, c4 = st.columns(4)
        equity = c1.number_input("가상 기준자산(원)", min_value=1_000_000.0, value=float(cfg["initial_equity_krw"]), step=10_000_000.0, format="%.0f")
        max_pos = c2.number_input("종목당 최대비중", min_value=0.01, max_value=1.0, value=float(cfg["max_position_weight"]), step=0.01)
        max_sector = c3.number_input("섹터 최대비중", min_value=0.01, max_value=1.0, value=float(cfg["max_sector_weight"]), step=0.01)
        max_total = c4.number_input("총 익스포저 한도", min_value=0.01, max_value=2.0, value=float(cfg["max_total_exposure"]), step=0.05)
        if st.form_submit_button("리스크 설정 저장"):
            execute(
                "UPDATE portfolio_settings SET initial_equity_krw=?,max_position_weight=?,max_sector_weight=?,max_total_exposure=? WHERE id=1",
                (equity, max_pos, max_sector, max_total),
            )
            rerun_success("리스크 설정 저장 완료")

    decisions = rows(
        """
        SELECT d.*, c.name AS company_name, c.ticker
        FROM llm_decisions d JOIN companies c ON c.id=d.company_id
        ORDER BY d.id DESC
        """
    )
    buy_decisions = [d for d in decisions if d["action"] == "BUY"]
    st.subheader("AI 제안 -> Risk Engine -> 가상 체결")
    if not buy_decisions:
        st.info("BUY 판단 레코드가 아직 없습니다.")
    else:
        decision_map = {
            f"#{d['id']} {d['company_name']} · {d['target_weight']*100:.1f}% · conf {d['confidence']:.2f}": d
            for d in buy_decisions
        }
        picked = st.selectbox("BUY 제안", list(decision_map))
        decision = decision_map[picked]
        preview = validate_target_weight(int(decision["company_id"]), float(decision["target_weight"]))
        c1, c2, c3 = st.columns(3)
        c1.metric("LLM 제안 총액", krw(preview["requested_total_krw"]))
        c2.metric("현재 보유", krw(preview["current_company_krw"]))
        c3.metric("이번 신규 허용", krw(preview["allowed_add_krw"]))
        if preview["reasons"]:
            st.warning("Risk Engine: " + " / ".join(preview["reasons"]))

        with st.form("paper_open"):
            entry_price = st.number_input("가상 진입가격", min_value=0.000001, step=1.0)
            execute_amount = st.number_input(
                "체결금액(원)", min_value=0.0, max_value=float(preview["allowed_add_krw"]), value=float(preview["allowed_add_krw"]), step=100_000.0
            )
            if st.form_submit_button("가상 BUY 체결", type="primary"):
                if execute_amount <= 0:
                    st.error("Risk Engine이 허용한 신규 금액이 없습니다.")
                else:
                    qty = execute_amount / entry_price
                    execute(
                        """
                        INSERT INTO paper_trades(company_id,side,entry_price,notional_krw,qty,status,entry_reason)
                        VALUES(?,?,?,?,?,'OPEN',?)
                        """,
                        (
                            decision["company_id"], "LONG", entry_price, execute_amount, qty,
                            f"LLM decision #{decision['id']}: {decision['thesis']}",
                        ),
                    )
                    rerun_success("가상 매수 체결 완료")

    open_trades = rows(
        """
        SELECT t.*, c.name AS company_name, c.ticker
        FROM paper_trades t JOIN companies c ON c.id=t.company_id
        WHERE t.status='OPEN' ORDER BY t.opened_at DESC, t.id DESC
        """
    )
    st.subheader("오픈 포지션")
    if open_trades:
        st.dataframe(pd.DataFrame(open_trades), use_container_width=True, hide_index=True)
        trade_map = {f"#{t['id']} {t['company_name']} · {krw(t['notional_krw'])}": t for t in open_trades}
        with st.form("paper_close"):
            trade_label = st.selectbox("청산할 포지션", list(trade_map))
            exit_price = st.number_input("가상 청산가격", min_value=0.000001, step=1.0)
            exit_reason = st.text_area("청산 이유")
            if st.form_submit_button("전량 가상 청산"):
                trade = trade_map[trade_label]
                entry = float(trade["entry_price"])
                ret = (exit_price / entry - 1.0) * 100
                pnl = float(trade["notional_krw"]) * ret / 100
                execute(
                    """
                    UPDATE paper_trades
                    SET closed_at=?,exit_price=?,status='CLOSED',exit_reason=?,pnl_krw=?,return_pct=?
                    WHERE id=?
                    """,
                    (datetime.now().isoformat(timespec="seconds"), exit_price, exit_reason.strip(), pnl, ret, trade["id"]),
                )
                rerun_success(f"가상 청산 완료 · 수익률 {ret:+.2f}%")
    else:
        st.info("오픈 포지션 없음")

with tab_data:
    table = st.selectbox(
        "테이블",
        [
            "sources", "companies", "projects", "exposures", "lh_assessments", "local_fundamentals",
            "market_snapshots", "llm_decisions", "paper_trades", "portfolio_settings",
        ],
    )
    data = rows(f"SELECT * FROM {table} ORDER BY id DESC" if table != "portfolio_settings" else "SELECT * FROM portfolio_settings")
    if data:
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    else:
        st.info("데이터 없음")
