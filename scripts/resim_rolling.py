"""Rolling 생활권 재시뮬레이션 — 채택 설계(2026-08-02)의 판정 diff.

채택 설계:
  · 생활권 형성 = 매달 직전 2개월(달력 2개 월) 방문 이벤트로 재군집 (해당 월 제외)
  · 군집 실패 시 직전 지도 유지 (원안 폴백)
  · 케어 분리 = 평소값(기준선 2개월 평균)·해제 기준 고정, 감지는 직전 2개월 지표 비교
    (현행 엔진의 케어 로직 그대로 — 바뀌는 것은 월별 지도뿐)

입력: data/fixtures/gaip_visit_events.csv (고정 엔진과 동일한 이벤트 — 생성은 재사용)
출력: 고정(번들) 대비 연간 우대/케어 diff, 유형별 교차표, 오탐 대조군, 명멸 통계.
엔진 원본은 수정하지 않는다.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from gaip_simulation import engine  # noqa: E402
from gaip_simulation.clustering import (  # noqa: E402
    dbscan_distinct_days,
    locate_product_zone,
    summarize_clusters,
)

RULES = engine.DEFAULT_PRODUCT_RULES
ALL_MONTHS = list(engine.ALL_MONTHS)
MOB_TH = float(RULES["care_thresholds"]["mobility_change_index"])
RISK_TH = float(RULES["care_thresholds"]["risky_behavior_change_index"])


def load_events() -> dict[str, list[dict]]:
    by_driver: dict[str, list[dict]] = defaultdict(list)
    with open(ROOT / "data/fixtures/gaip_visit_events.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row["latitude"] = float(row["latitude"])
            row["longitude"] = float(row["longitude"])
            row["trip_distance_km"] = float(row["trip_distance_km"])
            row["risk_event_count"] = int(row["risk_event_count"])
            row["data_coverage_pct"] = float(row["data_coverage_pct"])
            by_driver[row["driver_id"]].append(row)
    return by_driver


def monthly_hubs_rolling(driver: dict, events: list[dict]) -> tuple[dict[str, list], Counter]:
    """월별 지도: 기준선 두 달은 기준선 창, 평가 월 M은 [M-2, M-1] 창. 실패 시 직전 지도."""
    environment = engine.ENVIRONMENTS[str(driver["environment_id"])]
    home_center = engine._hub_centers(driver)["__home__"]
    by_month: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        by_month[ev["month"]].append(ev)

    hubs_by_month: dict[str, list] = {}
    stats = Counter()
    prev_hubs: list = []
    for idx, month in enumerate(ALL_MONTHS):
        if idx <= 1:
            window = [m for m in ALL_MONTHS[:2]]
        else:
            window = [ALL_MONTHS[idx - 2], ALL_MONTHS[idx - 1]]
        window_events = [ev for m in window for ev in by_month.get(m, [])]
        hubs: list = []
        if window_events:
            clustering = dbscan_distinct_days(
                window_events,
                eps_m=float(environment["dbscan_eps_m"]),
                min_distinct_days=3,
            )
            hubs = summarize_clusters(
                window_events,
                clustering["labels"],
                core_radius_m=float(RULES["core_radius_m"]),
                buffer_cap_m=float(RULES["buffer_cap_m"]),
                home_zone_reach_m=float(environment["zone_reach_m"]) * engine._HOME_ZONE_REACH_FACTOR,
                home_center=home_center,
            )
        if not hubs and prev_hubs:
            hubs = prev_hubs
            stats["fallback_months"] += 1
        if idx >= 2 and prev_hubs:
            delta = len(hubs) - len(prev_hubs)
            if delta < 0:
                stats["hub_drop_months"] += 1
                stats["hubs_dropped"] += -delta
            elif delta > 0:
                stats["hub_gain_months"] += 1
        hubs_by_month[month] = hubs
        prev_hubs = hubs
    return hubs_by_month, stats


def judge_driver(driver: dict, events: list[dict]) -> tuple[str, str, Counter]:
    hubs_by_month, flicker = monthly_hubs_rolling(driver, events)
    by_month: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        by_month[ev["month"]].append(ev)

    raw: dict[str, dict] = {}
    for month in ALL_MONTHS:
        rows = by_month.get(month, [])
        hubs = hubs_by_month[month]
        if not rows:
            raw[month] = {
                "month": month, "period_role": engine._period_role(month), "trip_count": 0,
                "outer_visit_share": 0.0, "risky_behavior_rate": 0.0, "data_coverage_pct": 0.0,
                "zone_available": bool(hubs), "total_distance_km": 0.0,
                "mileage_score": None, "in_zone_safe_score": None, "out_zone_safe_score": None,
            }
            continue
        located = {r["visit_event_id"]: locate_product_zone(r, hubs) for r in rows}
        in_zone = [r for r in rows if located[r["visit_event_id"]]["zone"] in {"core", "buffer"}]
        out_zone = [r for r in rows if located[r["visit_event_id"]]["zone"] == "outer"]
        total_distance = sum(r["trip_distance_km"] for r in rows)
        risky_trip_count = sum(r["risk_event_count"] > 0 for r in rows)
        raw[month] = {
            "month": month,
            "period_role": engine._period_role(month),
            "trip_count": len(rows),
            "total_distance_km": total_distance,
            "data_coverage_pct": round(sum(r["data_coverage_pct"] for r in rows) / len(rows), 2),
            "outer_visit_share": round(len(out_zone) / len(rows), 4),
            "risky_behavior_rate": round(risky_trip_count / len(rows), 4),
            "mileage_score": engine._mileage_score(total_distance),
            "in_zone_safe_score": engine._safety_score(in_zone),
            "out_zone_safe_score": engine._safety_score(out_zone),
            "zone_available": bool(hubs),
        }

    baseline_months = ALL_MONTHS[:2]
    baseline_risk = sum(raw[m]["risky_behavior_rate"] for m in baseline_months) / 2
    baseline_outer = sum(raw[m]["outer_visit_share"] for m in baseline_months) / 2

    care_open = False
    monthly: list[dict] = []
    for idx, month in enumerate(ALL_MONTHS):
        cur = raw[month]
        if idx < 2:
            fires, open_now = False, False
        else:
            prev1, prev2 = raw[ALL_MONTHS[idx - 1]], raw[ALL_MONTHS[idx - 2]]
            trail_mob = cur["outer_visit_share"] - (prev1["outer_visit_share"] + prev2["outer_visit_share"]) / 2
            trail_risk = cur["risky_behavior_rate"] - (prev1["risky_behavior_rate"] + prev2["risky_behavior_rate"]) / 2
            fires = trail_mob >= MOB_TH and trail_risk >= RISK_TH
            sustained = (
                (cur["outer_visit_share"] - baseline_outer) >= MOB_TH
                and (cur["risky_behavior_rate"] - baseline_risk) >= RISK_TH
            )
            care_open = fires or (care_open and sustained)
            open_now = care_open
        metrics = dict(cur)
        metrics["mobility_change_index"] = round(max(0.0, cur["outer_visit_share"] - baseline_outer), 4)
        metrics["risky_behavior_change_index"] = round(max(0.0, cur["risky_behavior_rate"] - baseline_risk), 4)
        metrics["pattern_stability_score"] = round(max(0.0, 100.0 - metrics["risky_behavior_change_index"] * 100.0), 2)
        metrics["care_two_stage_open"] = open_now
        decision = engine.classify_month(metrics, RULES)
        if cur["period_role"] == "baseline":
            decision = {**decision, "reward_state": "observation", "care_state": "observation"}
        monthly.append({**metrics, **decision})

    annual_reward, annual_care = engine._annual_state(monthly, RULES)
    return annual_reward, annual_care, flicker


def main() -> None:
    bundle = json.loads((ROOT / "data/fixtures/gaip_simulation_bundle.json").read_text())
    fixed = {
        d["driver_id"]: (d["annual_reward_state"], d["annual_care_state"], d["archetype_id"], d["person_id"], d["environment_id"])
        for d in bundle["drivers"]
    }
    contracts = {d["driver_id"]: d for d in engine._build_driver_contracts(engine.DEFAULT_SEED)}
    events_by_driver = load_events()

    rows = []
    flicker_total = Counter()
    for driver_id, (f_reward, f_care, arch, person, env) in fixed.items():
        driver = contracts[driver_id]
        r_reward, r_care, flicker = judge_driver(driver, events_by_driver[driver_id])
        flicker_total.update(flicker)
        rows.append({
            "driver_id": driver_id, "archetype": arch, "person": person, "environment": env,
            "fixed_reward": f_reward, "rolling_reward": r_reward,
            "fixed_care": f_care, "rolling_care": r_care,
            "reward_changed": f_reward != r_reward, "care_changed": f_care != r_care,
        })

    reward_diff = [r for r in rows if r["reward_changed"]]
    care_diff = [r for r in rows if r["care_changed"]]
    print(f"=== Rolling 재판정 (180건, 이벤트·규칙 동일, 지도만 매달 직전 2개월) ===")
    print(f"연간 우대상태 변경: {len(reward_diff)}건 · 케어상태 변경: {len(care_diff)}건")

    print("\n■ 우대 교차 (고정 → rolling):")
    ct = Counter((r["fixed_reward"], r["rolling_reward"]) for r in rows)
    for (a, b), n in sorted(ct.items()):
        mark = "" if a == b else "  ← 변경"
        print(f"  {a:8s} → {b:8s}: {n:3d}{mark}")
    print("■ 케어 교차 (고정 → rolling):")
    ct = Counter((r["fixed_care"], r["rolling_care"]) for r in rows)
    for (a, b), n in sorted(ct.items()):
        mark = "" if a == b else "  ← 변경"
        print(f"  {a:12s} → {b:12s}: {n:3d}{mark}")

    print("\n■ 유형별 rolling 판정:")
    by_arch: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_arch[r["archetype"]][(r["rolling_reward"], r["rolling_care"])] += 1
    for arch in sorted(by_arch):
        print(f"  {arch:24s}: {dict(by_arch[arch])}")

    fp = [r for r in rows if r["archetype"] == "mobility_change_safe" and r["rolling_care"] == "care_review"]
    print(f"\n■ 오탐 대조군(이동변화·안전유지형 30건) 케어 발동: {len(fp)}건")
    missed = [r for r in rows if r["archetype"] == "mobility_risk_cochange" and r["rolling_care"] != "care_review"]
    print(f"■ 케어 대상(동시변화형 30건) 미발동: {len(missed)}건")

    persons: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        persons[(r["person"],)][r["environment"]] = (r["rolling_reward"], r["rolling_care"])
    same_reward = sum(1 for envs in persons.values() if len({v[0] for v in envs.values()}) == 1)
    same_care = sum(1 for envs in persons.values() if len({v[1] for v in envs.values()}) == 1)
    print(f"■ 3환경 동일인 일치(rolling): 우대 {same_reward}/60 · 케어 {same_care}/60")

    print(f"\n■ 명멸·폴백 (평가 12개월 × 180명 = 2,160 드라이버-월):")
    for k in ("hub_drop_months", "hubs_dropped", "hub_gain_months", "fallback_months"):
        print(f"  {k}: {flicker_total.get(k, 0)}")

    if reward_diff or care_diff:
        print("\n■ 변경 상세 (최대 20건):")
        for r in (reward_diff + [x for x in care_diff if x not in reward_diff])[:20]:
            print(f"  {r['driver_id']} [{r['archetype']}/{r['environment']}] "
                  f"우대 {r['fixed_reward']}→{r['rolling_reward']} · 케어 {r['fixed_care']}→{r['rolling_care']}")

    out = ROOT / "data" / "fixtures" / "resim_rolling_diff.json"
    out.write_text(json.dumps({"rows": rows, "flicker": dict(flicker_total)}, ensure_ascii=False, indent=1))
    print(f"\n상세 저장: {out}")


if __name__ == "__main__":
    main()
