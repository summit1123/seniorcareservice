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
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gaip_simulation.clustering import (  # noqa: E402
    dbscan_distinct_days,
    haversine_m,
    percentile_nearest_rank,
)

CSV_PATH = ROOT / "data" / "fixtures" / "gaip_visit_events.csv"
OUT_PATH = ROOT / "data" / "fixtures" / "gaip_algorithm_lab.json"

EPS_GRID_M = [100.0, 180.0, 300.0, 420.0, 600.0, 950.0, 1200.0]
MIN_DAYS_GRID = [2, 3, 5]
HDBSCAN_GRID = [(3, 2), (3, 3), (5, 2), (5, 3)]  # (min_cluster_size, min_samples)
CORE_M = 500.0
CAP_M = 2000.0
MERGE_TRUTH_MIN_SEP_M = 800.0
ENV_OPERATING_EPS = {"dense_urban": 180.0, "suburban_mid_density": 420.0,
                     "wide_low_density": 950.0}
SHOWCASE_PER_PERSONA = 1  # 페르소나별 대표 1명 + 기본 고객


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
    merged = 0
    pairs = 0
    labs = list(cents)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            a, b = labs[i], labs[j]
            sep = haversine_m(*cents[a]["center"], *cents[b]["center"])
            if sep < MERGE_TRUTH_MIN_SEP_M:
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
                               "missed": 0, "miss_base": 0, "hubs": []})
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
                key = ("dbscan", eps, md, env)
                a = agg[key]
                if m["coverage_pct"] is not None: a["cov"].append(m["coverage_pct"])
                if m["noise_pct"] is not None: a["noise"].append(m["noise_pct"])
                a["merged"] += m["overmerge"][0]; a["pairs"] += m["overmerge"][1]
                a["missed"] += m["missed"][0]; a["miss_base"] += m["missed"][1]
                a["hubs"].append(m["n_hubs"])
                if d in showcase_ids:
                    detail[d][f"dbscan-e{int(eps)}-d{md}"] = {
                        **{k: v for k, v in m.items() if k not in ("overmerge", "missed")},
                        "merged_pairs": m["overmerge"][0],
                        "geometry": geometry(clusters, anchor, fit)}

        for (mcs, ms) in HDBSCAN_GRID:
            labels = run_hdbscan(fit_xy, mcs, ms)
            clusters, m = combo_metrics(fit, ev, labels)
            key = ("hdbscan", float(mcs), ms, env)
            a = agg[key]
            if m["coverage_pct"] is not None: a["cov"].append(m["coverage_pct"])
            if m["noise_pct"] is not None: a["noise"].append(m["noise_pct"])
            a["merged"] += m["overmerge"][0]; a["pairs"] += m["overmerge"][1]
            a["missed"] += m["missed"][0]; a["miss_base"] += m["missed"][1]
            a["hubs"].append(m["n_hubs"])
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
            rows.append({
                "param_1": p1, "param_2": p2, "environment_id": env,
                "mean_coverage_pct": mean(v["cov"]),
                "mean_noise_pct": mean(v["noise"]),
                "overmerge_pct": round(v["merged"] / v["pairs"] * 100, 1) if v["pairs"] else None,
                "repeat_hub_miss_pct": round(v["missed"] / v["miss_base"] * 100, 1) if v["miss_base"] else None,
                "mean_hub_count": mean(v["hubs"]),
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
            "note": "운영 기준은 환경별 DBSCAN(180/420/950m)이며 이 실험실은 열람·검증용",
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
            "safe_band_note": "방문이벤트 기반 실측에서 eps 150~500m가 안정 구간 — "
                              "하한 절벽(과소·흔들림), 상한 절벽(800m~ 과병합) 확인",
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
