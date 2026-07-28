"""알고리즘 실험실 사전계산 — DBSCAN eps·최소 방문일수 grid + HDBSCAN 실측.

- 입력: data/fixtures/gaip_visit_events.csv (합성 60명, 기준선 2개월 + 평가 12개월)
- 출력: data/fixtures/gaip_algorithm_lab.json (요약 지표 + 대표 운전자 도식 기하)
- 원칙:
  * 대시보드는 이 사전계산 결과를 열람만 한다 — 실시간 군집화·외부 의존성 없음.
  * 운영 기준(DBSCAN, 환경별 eps)은 바꾸지 않는다. HDBSCAN은 비교 열람용 실측.
  * 원시 위경도는 출력하지 않는다 — 운전자 기준점 대비 미터 오프셋(도식 좌표)만.
  * 모든 수치는 Simulated. 과병합/누락의 정답 기준은 생성 시 부여된 합성 라벨.

실행: (HDBSCAN용 scikit-learn이 있는 파이썬으로)
  python scripts/generate_gaip_algorithm_lab.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gaip_simulation.clustering import (  # noqa: E402
    dbscan_distinct_days,
    haversine_m,
    percentile_nearest_rank,
)
from src.gaip_simulation.engine import ENVIRONMENTS  # noqa: E402

CSV_PATH = ROOT / "data" / "fixtures" / "gaip_visit_events.csv"
OUT_PATH = ROOT / "data" / "fixtures" / "gaip_algorithm_lab.json"

# Operating eps per environment = the engine's single source of truth, so the lab's
# highlighted "operating value" always matches the eps that generated the dashboard
# hubs (no drift between the shield and the main screen).
ENV_OPERATING_EPS = {env: float(cfg["dbscan_eps_m"]) for env, cfg in ENVIRONMENTS.items()}
# Sweep grid brackets each environment's operating eps AND contains it, so the
# highlighted point is a real swept row rather than an interpolated claim.
EPS_GRID_M = sorted({100.0, 300.0, 600.0, 900.0, 1200.0, *ENV_OPERATING_EPS.values()})
MIN_DAYS_GRID = [2, 3, 5]
HDBSCAN_GRID = [(3, 2), (3, 3), (5, 2), (5, 3)]  # (min_cluster_size, min_samples)
CORE_M = 500.0
CAP_M = 2000.0
# A pair of truth hubs only counts as "over-merge eligible" when they are farther
# apart than the environment's designed living-zone reach: the engine deliberately
# places Routine Hub A/B inside zone_reach_m of home so the operating eps groups
# them into ONE living zone (engine.py ENVIRONMENTS comment). Counting those
# by-design merges as 과병합 falsely penalises the operating eps in low-density
# environments. Pairs >= zone_reach_m are genuinely separate zones.
MERGE_TRUTH_MIN_SEP_BY_ENV = {env: float(cfg["zone_reach_m"]) for env, cfg in ENVIRONMENTS.items()}
MERGE_TRUTH_MIN_SEP_FALLBACK_M = 800.0
SHOWCASE_PER_PERSONA = 1  # 페르소나별 대표 1명 + 기본 고객
# 확장 지표(면적·IoU)용 격자 표본 간격 — 원 반경(>=500m)의 1/8 수준이면 면적 오차 ~1%.
ZONE_GRID_STEP_M = 60.0
# 거점 자격 기준(서로 다른 3일)은 운영 규칙과 동일하게 정답 존 구성에도 적용.
TRUTH_HUB_MIN_DAYS = 3


def load_events():
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_driver = defaultdict(list)
    for r in rows:
        r["latitude"] = float(r["latitude"])
        r["longitude"] = float(r["longitude"])
        by_driver[r["driver_id"]].append(r)
    return by_driver, rows


def project_offsets(events, anchor):
    """운전자 기준점 대비 (동쪽 m, 북쪽 m) — 위경도 필드는 출력 금지."""
    lat0, lon0 = anchor
    out = []
    for e in events:
        y = (e["latitude"] - lat0) * 111_320.0
        x = (e["longitude"] - lon0) * 111_320.0 * math.cos(math.radians(lat0))
        out.append((round(x, 1), round(y, 1)))
    return out


def cluster_summary(fit_events, labels):
    groups = defaultdict(list)
    for e, l in zip(fit_events, labels):
        if l >= 0:
            groups[l].append(e)
    clusters = []
    for l, evs in sorted(groups.items()):
        lat = sum(e["latitude"] for e in evs) / len(evs)
        lon = sum(e["longitude"] for e in evs) / len(evs)
        dists = [haversine_m(e["latitude"], e["longitude"], lat, lon) for e in evs]
        p90 = percentile_nearest_rank(dists, 0.90) if dists else 0.0
        clusters.append({
            "_center": (lat, lon),
            "events": evs,
            "distinct_days": len({e["visit_date"] for e in evs}),
            "radial_p90_m": round(p90, 1),
            "buffer_m": round(max(CORE_M, min(p90, CAP_M)), 1),
        })
    clusters.sort(key=lambda c: (-c["distinct_days"], -len(c["events"])))
    return clusters


def truth_centroids(fit_events):
    by_label = defaultdict(list)
    for e in fit_events:
        by_label[e["visit_label"]].append(e)
    cents = {}
    for lab, evs in by_label.items():
        lat = sum(e["latitude"] for e in evs) / len(evs)
        lon = sum(e["longitude"] for e in evs) / len(evs)
        cents[lab] = {"center": (lat, lon),
                      "distinct_days": len({e["visit_date"] for e in evs})}
    return cents


def assign_cluster(pt, clusters):
    best, bd = None, None
    for i, c in enumerate(clusters):
        d = haversine_m(pt[0], pt[1], c["_center"][0], c["_center"][1])
        if d <= c["buffer_m"] and (bd is None or d < bd):
            best, bd = i, d
    return best


def combo_metrics(fit_events, eval_events, labels):
    clusters = cluster_summary(fit_events, labels)
    noise = sum(1 for l in labels if l < 0)
    noise_pct = round(noise / len(labels) * 100, 1) if labels else None

    cov = None
    if clusters and eval_events:
        inz = 0
        for e in eval_events:
            for c in clusters:
                d = haversine_m(e["latitude"], e["longitude"], *c["_center"])
                if d <= max(CORE_M, c["buffer_m"]):
                    inz += 1
                    break
        cov = round(inz / len(eval_events) * 100, 1)

    cents = truth_centroids(fit_events)
    assigned = {lab: assign_cluster(v["center"], clusters) for lab, v in cents.items()}
    env_id = str(fit_events[0].get("environment_id", "")) if fit_events else ""
    min_sep = MERGE_TRUTH_MIN_SEP_BY_ENV.get(env_id, MERGE_TRUTH_MIN_SEP_FALLBACK_M)
    merged = 0
    pairs = 0
    labs = list(cents)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            a, b = labs[i], labs[j]
            sep = haversine_m(*cents[a]["center"], *cents[b]["center"])
            if sep < min_sep:
                continue
            if assigned[a] is None or assigned[b] is None:
                continue
            pairs += 1
            if assigned[a] == assigned[b]:
                merged += 1
    overmerge = (merged, pairs)
    missed = sum(1 for lab, v in cents.items()
                 if v["distinct_days"] >= 3 and assigned[lab] is None)
    miss_base = sum(1 for v in cents.values() if v["distinct_days"] >= 3)
    return clusters, {"noise_pct": noise_pct, "coverage_pct": cov,
                      "overmerge": overmerge, "missed": (missed, miss_base),
                      "n_hubs": len(clusters)}


def circle_offsets(clusters, anchor):
    """생성된 생활권 원들을 (동쪽 m, 북쪽 m, 반경 m)으로 — 판정과 동일한 max(코어, 버퍼) 반경."""
    lat0 = anchor[0]
    out = []
    for c in clusters:
        x = (c["_center"][1] - anchor[1]) * 111_320.0 * math.cos(math.radians(lat0))
        y = (c["_center"][0] - anchor[0]) * 111_320.0
        out.append((x, y, max(CORE_M, c["buffer_m"])))
    return out


def truth_circles(fit_events, anchor):
    """정답 라벨 기준의 존: 라벨이 완벽했다면 같은 원 규칙이 만들었을 생활권."""
    by_label = defaultdict(list)
    for e in fit_events:
        by_label[e["visit_label"]].append(e)
    lat0 = anchor[0]
    out = []
    for lab, evs in sorted(by_label.items()):
        if len({e["visit_date"] for e in evs}) < TRUTH_HUB_MIN_DAYS:
            continue
        lat = sum(e["latitude"] for e in evs) / len(evs)
        lon = sum(e["longitude"] for e in evs) / len(evs)
        dists = [haversine_m(e["latitude"], e["longitude"], lat, lon) for e in evs]
        p90 = percentile_nearest_rank(dists, 0.90)
        x = (lon - anchor[1]) * 111_320.0 * math.cos(math.radians(lat0))
        y = (lat - anchor[0]) * 111_320.0
        out.append((x, y, max(CORE_M, min(p90, CAP_M))))
    return out


def zone_area_and_iou(circles_a, circles_b, step=ZONE_GRID_STEP_M):
    """격자 표본으로 (A 면적 km², B 면적 km², IoU) — 한쪽이 비면 IoU 0, 둘 다 비면 None."""
    import numpy as np

    if not circles_a and not circles_b:
        return None, None, None
    every = circles_a + circles_b
    min_x = min(x - r for x, y, r in every) - step
    max_x = max(x + r for x, y, r in every) + step
    min_y = min(y - r for x, y, r in every) - step
    max_y = max(y + r for x, y, r in every) + step
    xs = np.arange(min_x, max_x, step)
    ys = np.arange(min_y, max_y, step)
    grid_x, grid_y = np.meshgrid(xs, ys)

    def mask(circles):
        covered = np.zeros(grid_x.shape, dtype=bool)
        for (x, y, r) in circles:
            covered |= (grid_x - x) ** 2 + (grid_y - y) ** 2 <= r * r
        return covered

    mask_a = mask(circles_a)
    mask_b = mask(circles_b)
    cell_km2 = (step * step) / 1e6
    union = (mask_a | mask_b).sum()
    inter = (mask_a & mask_b).sum()
    iou = round(float(inter) / float(union), 3) if union else None
    return round(float(mask_a.sum()) * cell_km2, 4), round(float(mask_b.sum()) * cell_km2, 4), iou


def extended_metrics(fit_events, eval_events, clusters, anchor):
    """파편화·부풀림을 실제로 벌점 주는 확장 지표.

    - area_inflation: 생성 존 면적 / 정답 존 면적 (>1 = 부풀림)
    - truth_zone_iou: 생성 존과 정답 존의 모양 일치도
    - new_hub_inside: 평가기간 New Hub(변화 목적지) 방문이 기준선 존 안으로 흡수된 수
    - redundant_hubs: 정답 거점 하나가 2개 이상 군집으로 쪼개진 수 (파편화)
    """
    produced = circle_offsets(clusters, anchor)
    truth = truth_circles(fit_events, anchor)
    area_produced, area_truth, truth_iou = zone_area_and_iou(produced, truth)
    inflation = (
        round(area_produced / area_truth, 3)
        if area_produced is not None and area_truth
        else None
    )

    new_hub_events = [e for e in eval_events if e["visit_label"] == "New Hub"]
    swallowed = 0
    for e in new_hub_events:
        for c in clusters:
            d = haversine_m(e["latitude"], e["longitude"], *c["_center"])
            if d <= max(CORE_M, c["buffer_m"]):
                swallowed += 1
                break

    majority = [
        Counter(e["visit_label"] for e in c["events"]).most_common(1)[0][0]
        for c in clusters
    ]
    clusters_per_label = Counter(majority)
    qualified = {
        lab
        for lab, evs in _group_by_label(fit_events).items()
        if len({e["visit_date"] for e in evs}) >= TRUTH_HUB_MIN_DAYS
    }
    redundant = sum(1 for lab in qualified if clusters_per_label.get(lab, 0) >= 2)

    return {
        "area_produced_km2": area_produced,
        "area_truth_km2": area_truth,
        "area_inflation": inflation,
        "truth_zone_iou": truth_iou,
        "new_hub_inside": (swallowed, len(new_hub_events)),
        "redundant_hubs": (redundant, len(qualified)),
    }


def _group_by_label(events):
    grouped = defaultdict(list)
    for e in events:
        grouped[e["visit_label"]].append(e)
    return grouped


def stability_iou(fit_events, anchor, label_fn):
    """기준선 1개월차 vs 2개월차 — 같은 평소 루틴의 두 독립 표본이 같은 존을 만드는가."""
    months = sorted({e["month"] for e in fit_events})
    if len(months) < 2:
        return None
    window_a = [e for e in fit_events if e["month"] == months[0]]
    window_b = [e for e in fit_events if e["month"] == months[1]]
    if not window_a or not window_b:
        return None
    circles = []
    for window in (window_a, window_b):
        labels = label_fn(window)
        clusters = cluster_summary(window, labels)
        circles.append(circle_offsets(clusters, anchor))
    if not circles[0] and not circles[1]:
        return None
    _, _, iou = zone_area_and_iou(circles[0], circles[1])
    return iou if iou is not None else 0.0


def geometry(clusters, anchor, fit_events):
    offs = project_offsets(fit_events, anchor)
    pts = [{"x_m": x, "y_m": y} for (x, y) in offs]
    cl = []
    for c in clusters:
        cx, cy = project_offsets([{"latitude": c["_center"][0],
                                   "longitude": c["_center"][1]}], anchor)[0]
        cl.append({"x_m": cx, "y_m": cy, "buffer_m": c["buffer_m"],
                   "radial_p90_m": c["radial_p90_m"],
                   "distinct_days": c["distinct_days"]})
    return {"points": pts, "clusters": cl}


def run_hdbscan(fit_xy, mcs, ms):
    from sklearn.cluster import HDBSCAN
    import numpy as np
    if len(fit_xy) < max(mcs, 3):
        return [-1] * len(fit_xy)
    h = HDBSCAN(min_cluster_size=mcs, min_samples=ms, allow_single_cluster=True)
    return h.fit_predict(np.array(fit_xy)).tolist()


def main():
    by_driver, all_rows = load_events()
    drivers = sorted(by_driver)

    showcase = {}
    for d in drivers:
        p = by_driver[d][0]["designed_type"]
        showcase.setdefault(p, d)
    showcase_ids = set(showcase.values()) | {"gaip-051"}

    agg = defaultdict(lambda: {"cov": [], "noise": [], "merged": 0, "pairs": 0,
                               "missed": 0, "miss_base": 0, "hubs": [],
                               "area_infl": [], "truth_iou": [],
                               "nh_inside": 0, "nh_base": 0,
                               "redundant": 0, "redundant_base": 0,
                               "stab_iou": []})
    detail = defaultdict(dict)

    for d in drivers:
        evs = by_driver[d]
        fit = [e for e in evs if e["period_role"] == "baseline"]
        ev = [e for e in evs if e["period_role"] != "baseline"]
        env = evs[0]["environment_id"]
        if not fit:
            continue
        anchor = (sum(e["latitude"] for e in fit) / len(fit),
                  sum(e["longitude"] for e in fit) / len(fit))
        lat0 = anchor[0]
        fit_xy = [((e["longitude"] - anchor[1]) * 111_320.0 * math.cos(math.radians(lat0)),
                   (e["latitude"] - anchor[0]) * 111_320.0) for e in fit]

        for eps in EPS_GRID_M:
            for md in MIN_DAYS_GRID:
                res = dbscan_distinct_days(fit, eps_m=eps, min_distinct_days=md)
                clusters, m = combo_metrics(fit, ev, res["labels"])
                x = extended_metrics(fit, ev, clusters, anchor)
                stab = stability_iou(
                    fit, anchor,
                    lambda w, _e=eps, _m=md: dbscan_distinct_days(
                        w, eps_m=_e, min_distinct_days=_m)["labels"])
                key = ("dbscan", eps, md, env)
                a = agg[key]
                if m["coverage_pct"] is not None: a["cov"].append(m["coverage_pct"])
                if m["noise_pct"] is not None: a["noise"].append(m["noise_pct"])
                a["merged"] += m["overmerge"][0]; a["pairs"] += m["overmerge"][1]
                a["missed"] += m["missed"][0]; a["miss_base"] += m["missed"][1]
                a["hubs"].append(m["n_hubs"])
                if x["area_inflation"] is not None: a["area_infl"].append(x["area_inflation"])
                if x["truth_zone_iou"] is not None: a["truth_iou"].append(x["truth_zone_iou"])
                a["nh_inside"] += x["new_hub_inside"][0]; a["nh_base"] += x["new_hub_inside"][1]
                a["redundant"] += x["redundant_hubs"][0]; a["redundant_base"] += x["redundant_hubs"][1]
                if stab is not None: a["stab_iou"].append(stab)
                if d in showcase_ids:
                    detail[d][f"dbscan-e{int(eps)}-d{md}"] = {
                        **{k: v for k, v in m.items() if k not in ("overmerge", "missed")},
                        "merged_pairs": m["overmerge"][0],
                        "geometry": geometry(clusters, anchor, fit)}

        def hdbscan_window_labels(window, _mcs, _ms):
            lat0_w = anchor[0]
            window_xy = [
                ((e["longitude"] - anchor[1]) * 111_320.0 * math.cos(math.radians(lat0_w)),
                 (e["latitude"] - anchor[0]) * 111_320.0)
                for e in window
            ]
            return run_hdbscan(window_xy, _mcs, _ms)

        for (mcs, ms) in HDBSCAN_GRID:
            labels = run_hdbscan(fit_xy, mcs, ms)
            clusters, m = combo_metrics(fit, ev, labels)
            x = extended_metrics(fit, ev, clusters, anchor)
            stab = stability_iou(
                fit, anchor,
                lambda w, _c=mcs, _s=ms: hdbscan_window_labels(w, _c, _s))
            key = ("hdbscan", float(mcs), ms, env)
            a = agg[key]
            if m["coverage_pct"] is not None: a["cov"].append(m["coverage_pct"])
            if m["noise_pct"] is not None: a["noise"].append(m["noise_pct"])
            a["merged"] += m["overmerge"][0]; a["pairs"] += m["overmerge"][1]
            a["missed"] += m["missed"][0]; a["miss_base"] += m["missed"][1]
            a["hubs"].append(m["n_hubs"])
            if x["area_inflation"] is not None: a["area_infl"].append(x["area_inflation"])
            if x["truth_zone_iou"] is not None: a["truth_iou"].append(x["truth_zone_iou"])
            a["nh_inside"] += x["new_hub_inside"][0]; a["nh_base"] += x["new_hub_inside"][1]
            a["redundant"] += x["redundant_hubs"][0]; a["redundant_base"] += x["redundant_hubs"][1]
            if stab is not None: a["stab_iou"].append(stab)
            if d in showcase_ids:
                detail[d][f"hdbscan-c{mcs}-s{ms}"] = {
                    **{k: v for k, v in m.items() if k not in ("overmerge", "missed")},
                    "merged_pairs": m["overmerge"][0],
                    "geometry": geometry(clusters, anchor, fit)}

    def agg_rows(algo):
        rows = []
        keys = sorted(k for k in agg if k[0] == algo)
        for (a_, p1, p2, env) in keys:
            v = agg[(a_, p1, p2, env)]
            mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
            mean3 = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
            rows.append({
                "param_1": p1, "param_2": p2, "environment_id": env,
                "mean_coverage_pct": mean(v["cov"]),
                "mean_noise_pct": mean(v["noise"]),
                "overmerge_pct": round(v["merged"] / v["pairs"] * 100, 1) if v["pairs"] else None,
                "repeat_hub_miss_pct": round(v["missed"] / v["miss_base"] * 100, 1) if v["miss_base"] else None,
                "mean_hub_count": mean(v["hubs"]),
                "mean_area_inflation": mean3(v["area_infl"]),
                "mean_truth_zone_iou": mean3(v["truth_iou"]),
                "new_hub_inside_pct": round(v["nh_inside"] / v["nh_base"] * 100, 1) if v["nh_base"] else None,
                "redundant_hub_pct": round(v["redundant"] / v["redundant_base"] * 100, 1) if v["redundant_base"] else None,
                "mean_stability_iou": mean3(v["stab_iou"]),
            })
        return rows

    try:
        import sklearn
        skv = sklearn.__version__
    except Exception:
        skv = "unavailable"

    csv_sha = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    bundle = {
        "metadata": {
            "schema_version": "masil-gaip-lab/v1",
            "synthetic_data": True,
            "data_status": "Simulated",
            "source_events_sha256": csv_sha,
            "hdbscan_dependency": f"scikit-learn {skv} (사전계산 전용 — 대시보드 런타임 불필요)",
            "coordinate_policy": "운전자 기준점 대비 미터 오프셋(도식) — 원시 위경도 미포함",
            "truth_basis": "합성 생성 라벨(Routine Hub A/B/New Hub) 기준의 과병합·누락",
            "extended_metrics_note": (
                "확장 지표 5종 — area_inflation(생성 존 면적/정답 존 면적, >1=부풀림), "
                "truth_zone_iou(정답 존과 모양 일치), new_hub_inside_pct(평가기간 New Hub "
                "방문이 기준선 존에 흡수된 비율 — 변화 신호 소실), redundant_hub_pct(정답 "
                "거점 1개가 2개 이상 군집으로 쪼개진 비율 — 파편화), stability_iou(기준선 "
                "1개월차 vs 2개월차 존 IoU — 같은 루틴의 두 표본이 같은 존을 만드는가)"
            ),
            "note": (
                "운영 기준은 환경별 DBSCAN("
                + "/".join(f"{int(ENV_OPERATING_EPS[e])}" for e in ("dense_urban", "suburban_mid_density", "wide_low_density"))
                + "m)이며 이 실험실은 열람·검증용"
            ),
        },
        "grids": {
            "dbscan": {"eps_m": EPS_GRID_M, "min_distinct_days": MIN_DAYS_GRID,
                       "operating_eps_by_env": ENV_OPERATING_EPS},
            "hdbscan": {"combos": [{"min_cluster_size": a, "min_samples": b}
                                   for (a, b) in HDBSCAN_GRID]},
            "product_zone_fixed": {"core_m": CORE_M, "cap_m": CAP_M},
        },
        "prior_experiment_reference": {
            "run_ids": ["RUN-20260713-P1", "RUN-20260713-P2"],
            "safe_band_note": "안정 구간은 환경 밀도에 비례해 이동합니다 — 표의 과병합 0% 구간으로 "
                              "환경별 안정 상한을 확인하세요(과병합 판정은 설계상 한 생활권인 근접 거점 쌍을 "
                              "제외한, 환경별 생활권 반경 이상 떨어진 거점 쌍 기준)",
        },
        "aggregates": {"dbscan": agg_rows("dbscan"), "hdbscan": agg_rows("hdbscan")},
        "showcase_drivers": {d: detail[d] for d in sorted(detail)},
    }
    OUT_PATH.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":"),
                                   sort_keys=True), encoding="utf-8")
    print(json.dumps({"out": str(OUT_PATH.relative_to(ROOT)),
                      "bytes": OUT_PATH.stat().st_size,
                      "dbscan_rows": len(bundle["aggregates"]["dbscan"]),
                      "hdbscan_rows": len(bundle["aggregates"]["hdbscan"]),
                      "showcase": sorted(detail)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
