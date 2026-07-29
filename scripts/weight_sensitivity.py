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


def grid_sweep(drivers):
    """가중치 공간 전체(5 단위, 각 축 ≥5, 합 100 = 969개)를 스윕한다."""
    import itertools, statistics as st
    from collections import defaultdict
    base = annual_reward_states(drivers, VARIANTS["30/30/20/20 (현행)"])
    grid = [c for c in itertools.product(range(5, 90, 5), repeat=4) if sum(c) == 100]
    changes = {}
    for w in grid:
        s = annual_reward_states(drivers, w)
        changes[w] = sum(1 for a, b in zip(base, s) if a != b)
    vals = list(changes.values())
    print(f"\n■ 전체 격자 {len(grid)}개 조합 — 판정 변경 중앙값 {st.median(vals):.0f}건 · 최대 {max(vals)}건")
    near = [w for w in grid if all(abs(a - b) <= 5 for a, b in zip(w, (30, 30, 20, 20)))]
    nv = [changes[w] for w in near]
    print(f"■ 현행 ±5 이웃 {len(near)}개 — 중앙값 {st.median(nv):.0f}건 · 최대 {max(nv)}건")
    # 4축 각각을 같은 조건에서 본다. 한 축을 볼 때 나머지 지배 축(주행거리≤30,
    # 안 안전≥25)은 안정 구간에 고정해 교란을 제거한다 — 고정하지 않으면 다른
    # 축의 폭주가 그 축의 효과로 잘못 읽힌다.
    views = [
        ("주행거리", 0, lambda w: w[1] >= 25, "안 안전≥25 고정"),
        ("안 안전", 1, lambda w: w[0] <= 30, "주행거리≤30 고정"),
        ("밖 안전", 2, lambda w: w[0] <= 30 and w[1] >= 25, "주행거리≤30·안 안전≥25 고정"),
        ("패턴 안정성", 3, lambda w: w[0] <= 30 and w[1] >= 25, "주행거리≤30·안 안전≥25 고정"),
    ]
    profiles = {}
    for name, idx, keep, note in views:
        d = defaultdict(list)
        for w, c in changes.items():
            if keep(w):
                d[w[idx]].append(c)
        prof = {k: st.mean(v) for k, v in sorted(d.items()) if k <= 50 and len(v) >= 3}
        profiles[name] = prof
        span = max(prof.values()) - min(prof.values())
        print(f"\n■ {name} ({note}) — 진폭 {span:.0f}건")
        print("   " + "  ".join(f"{k}:{m:5.1f}" for k, m in prof.items()))
    stable = [w for w in grid if w[0] <= 30 and w[1] >= 25]
    sv = [changes[w] for w in stable]
    print(f"\n■ 두 안정 구간(주행거리≤30·안 안전≥25)을 지키는 {len(stable)}개 조합 "
          f"— 중앙값 {st.median(sv):.0f}건 · 최대 {max(sv)}건")
    return changes


if __name__ == "__main__":
    import json as _j
    _drivers = _j.loads(BUNDLE.read_text(encoding="utf-8"))["drivers"]
    grid_sweep(_drivers)
