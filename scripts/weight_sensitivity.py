"""가중치 민감도 검증 — 30/30/20/20을 흔들었을 때 연간 우대 판정이 얼마나 바뀌는가.

시뮬레이션 번들(gaip_simulation_bundle.json)의 월별 축 점수를 그대로 쓰고,
가중치만 바꿔 통합점수·연간 우대를 재판정한다. 케어 판정은 가중치를 쓰지
않으므로 영향이 없다(감지식은 변화 지수 기반).

주의: 합성 시나리오 기반이므로 "값이 옳다"의 증거가 아니라, 값을 흔들었을 때
판정이 얼마나 움직이는지(둔감성)를 보는 용도다.

실행:  python3 scripts/weight_sensitivity.py
"""
import json
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "gaip_simulation_bundle.json"
AXES = ("mileage_score", "in_zone_safe_score", "out_zone_safe_score", "pattern_stability_score")
REWARD_THRESHOLD = 75.0
REWARD_REQUIRED_MONTHS = 9
MIN_COVERAGE_PCT = 80.0

VARIANTS = {
    "30/30/20/20 (현행)": (30, 30, 20, 20),
    "30/30/15/25":        (30, 30, 15, 25),
    "30/30/25/15":        (30, 30, 25, 15),
    "25/35/20/20":        (25, 35, 20, 20),
    "25/25/25/25 (균등)": (25, 25, 25, 25),
    "35/25/20/20":        (35, 25, 20, 20),
    "20/40/20/20":        (20, 40, 20, 20),
    "40/30/15/15":        (40, 30, 15, 15),
}


def annual_reward_states(drivers, weights):
    """가중치 하나에 대해 180건의 연간 우대 상태를 재판정한다."""
    w = dict(zip(AXES, weights))
    states = []
    for d in drivers:
        reward_months = 0
        eligible_months = 0
        for m in d["monthly_results"]:
            if m["period_role"] != "evaluation":
                continue
            if not m.get("zone_available") or float(m.get("data_coverage_pct", 0)) < MIN_COVERAGE_PCT:
                continue  # hold — 판정 미진입 (엔진과 동일)
            observed = [(float(m[a]), w[a]) for a in AXES if m.get(a) is not None]
            observed_weight = sum(wt for _, wt in observed)
            if observed_weight <= 0:
                continue
            eligible_months += 1
            score = sum(v * wt for v, wt in observed) / observed_weight  # 미관측 축 재정규화
            if score >= REWARD_THRESHOLD:
                reward_months += 1
        if eligible_months < REWARD_REQUIRED_MONTHS:
            states.append("hold")
        elif reward_months >= REWARD_REQUIRED_MONTHS:
            states.append("reward")
        else:
            states.append("neutral")
    return states


def main():
    drivers = json.loads(BUNDLE.read_text(encoding="utf-8"))["drivers"]
    base = annual_reward_states(drivers, VARIANTS["30/30/20/20 (현행)"])
    print(f"시나리오 {len(drivers)}건 · 현행 우대 {base.count('reward')} / 중립 {base.count('neutral')} / 보류 {base.count('hold')}\n")
    print(f"{'가중치':22s} {'우대':>4s} {'현행 대비 변경':>10s}")
    print("-" * 44)
    for name, weights in VARIANTS.items():
        states = annual_reward_states(drivers, weights)
        changed = sum(1 for a, b in zip(base, states) if a != b)
        print(f"{name:22s} {states.count('reward'):4d} {changed:9d}건")


if __name__ == "__main__":
    main()
