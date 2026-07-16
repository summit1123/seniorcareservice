"""반사실 손익 시뮬레이션 — "마실이 할인을 더 주면 보험사는 손해 아닌가?"에 대한 답.

번들의 180개 시나리오 요율(기존 마일리지 vs 마실 후보)을 그대로 사용해:
  1) 포트폴리오 보험료 델타(마실 도입 시 연간 수입보험료 변화)를 계산하고
  2) 케어 개입 대상(동시변화 신호 발생) 세그먼트의 기대 클레임 풀을 잡은 뒤
  3) 케어 개입이 그 세그먼트의 클레임을 몇 % 줄이면 손익분기인지(breakeven)를 푼다.

모든 화폐 수치는 번들의 합성 요율 그대로(₩), 클레임 가정은 명시된 파라미터.
결과는 표준출력 + reports/loss_ratio_counterfactual.json 에 저장한다.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data" / "fixtures" / "gaip_simulation_bundle.json"
OUT = ROOT / "reports" / "loss_ratio_counterfactual.json"

# --- 명시 가정 (덱에서 그대로 선언) -----------------------------------------
# 순보험료율: 수입보험료 중 기대 클레임(손해액)의 비중. 국내 자동차보험 합산
# 손해율이 80% 안팎에서 움직이므로 보수적으로 낮춰 잡는다(낮을수록 breakeven이
# 어려워지는 보수적 방향).
PURE_PREMIUM_RATIO = 0.65
# 고령 운전자 사고 심도 상대계수: 동일 빈도라도 고령층 사고의 치명도·심도가 높다
# 는 공지의 방향성만 반영(1.0 = 반영 안 함도 함께 출력).
SEVERITY_RELATIVITY = [1.0, 1.2]
# 케어 개입의 클레임 절감 가정 그리드(문헌 검증 대상 — 텔레매틱스 피드백·운전
# 적합 검진 프로그램의 보고 범위를 넓게 커버).
REDUCTION_GRID = [0.05, 0.10, 0.15, 0.20, 0.30]


def main() -> None:
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    drivers = bundle["drivers"]

    portfolio = {
        "n": 0,
        "korea_net_sum": 0,
        "masil_net_sum": 0,
        "base_sum": 0,
    }
    care_segment = {"n": 0, "korea_net_sum": 0, "base_sum": 0, "care_month_sum": 0}

    for d in drivers:
        t = d.get("tariff") or {}
        korea_net = t.get("korea_mileage_net_premium_krw")
        masil_net = t.get("masil_candidate_net_premium_krw")
        base = t.get("base_premium_krw")
        if korea_net is None or masil_net is None or base is None:
            continue
        portfolio["n"] += 1
        portfolio["korea_net_sum"] += korea_net
        portfolio["masil_net_sum"] += masil_net
        portfolio["base_sum"] += base
        care_months = int(d.get("care_review_month_count") or 0)
        if care_months > 0:
            care_segment["n"] += 1
            care_segment["korea_net_sum"] += korea_net
            care_segment["base_sum"] += base
            care_segment["care_month_sum"] += care_months

    # 1) 포트폴리오 델타: 마실 도입 시 연간 수입보험료 변화(음수 = 보험사가 덜 걷음)
    revenue_delta = portfolio["masil_net_sum"] - portfolio["korea_net_sum"]

    # 2) 케어 세그먼트 기대 클레임 풀(연간): 순보험료율 × 기준 보험료 기반
    results = {
        "inputs": {
            "drivers": portfolio["n"],
            "pure_premium_ratio": PURE_PREMIUM_RATIO,
            "reduction_grid": REDUCTION_GRID,
            "severity_relativity": SEVERITY_RELATIVITY,
        },
        "portfolio": {
            "korea_net_sum_krw": portfolio["korea_net_sum"],
            "masil_net_sum_krw": portfolio["masil_net_sum"],
            "revenue_delta_krw": revenue_delta,
            "revenue_delta_pct_of_korea": round(100 * revenue_delta / portfolio["korea_net_sum"], 2),
        },
        "care_segment": {
            "n": care_segment["n"],
            "share_of_cohort_pct": round(100 * care_segment["n"] / portfolio["n"], 1),
            "care_months_total": care_segment["care_month_sum"],
        },
        "scenarios": [],
    }

    for sev in SEVERITY_RELATIVITY:
        expected_claims_care = care_segment["base_sum"] * PURE_PREMIUM_RATIO * sev
        # 3) breakeven: 케어 세그먼트 클레임 절감액이 포트폴리오 할인 추가분을 상쇄
        giveaway = -revenue_delta  # 보험사가 포기한 수입(양수)
        breakeven = giveaway / expected_claims_care if expected_claims_care else None
        rows = []
        for r in REDUCTION_GRID:
            savings = expected_claims_care * r
            rows.append({
                "assumed_claim_reduction_pct": round(100 * r, 1),
                "claims_savings_krw": round(savings),
                "net_effect_krw": round(savings + revenue_delta),
                "net_effect_per_driver_krw": round((savings + revenue_delta) / portfolio["n"]),
            })
        results["scenarios"].append({
            "severity_relativity": sev,
            "care_segment_expected_claims_krw": round(expected_claims_care),
            "giveaway_krw": round(giveaway),
            "breakeven_claim_reduction_pct": round(100 * breakeven, 2) if breakeven else None,
            "grid": rows,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    p = results["portfolio"]
    print(f"코호트 {portfolio['n']}건 · 기존 수입 {p['korea_net_sum_krw']:,}원 → 마실 {p['masil_net_sum_krw']:,}원")
    print(f"수입 델타 {p['revenue_delta_krw']:,}원 ({p['revenue_delta_pct_of_korea']}%)")
    print(f"케어 세그먼트 {care_segment['n']}건 ({results['care_segment']['share_of_cohort_pct']}%) · 케어 월 {care_segment['care_month_sum']}회")
    for sc in results["scenarios"]:
        print(f"[심도 {sc['severity_relativity']}x] 기대 클레임 {sc['care_segment_expected_claims_krw']:,}원 → breakeven 절감률 {sc['breakeven_claim_reduction_pct']}%")
        for row in sc["grid"]:
            print(f"  절감 {row['assumed_claim_reduction_pct']:>4}% → 순효과 {row['net_effect_krw']:,}원 (인당 {row['net_effect_per_driver_krw']:,}원)")


if __name__ == "__main__":
    main()
