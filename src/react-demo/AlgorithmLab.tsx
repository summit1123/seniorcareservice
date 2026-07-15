/**
 * 알고리즘 실험실 — 사전계산 스냅샷 열람 전용.
 *
 * eps·최소 방문일수(DBSCAN)와 HDBSCAN 설정을 바꾸면 미리 실측해 둔 결과
 * (생활권 지도·과병합·누락·소음·커버리지)가 즉시 전환됩니다. 실시간 군집화가
 * 아니므로 데모 중 계산이 달라질 위험이 없고, 운영 기준(환경별 DBSCAN)은
 * 이 화면에서 바뀌지 않습니다. 모든 수치는 합성(Simulated)입니다.
 */
import { useEffect, useMemo, useState } from "react";
import { t, tf } from "./i18n";

type LabAggregateRow = {
  param_1: number;
  param_2: number;
  environment_id: string;
  mean_coverage_pct: number | null;
  mean_noise_pct: number | null;
  overmerge_pct: number | null;
  repeat_hub_miss_pct: number | null;
  mean_hub_count: number | null;
};

type LabGeometry = {
  points: Array<{ x_m: number; y_m: number }>;
  clusters: Array<{ x_m: number; y_m: number; buffer_m: number; radial_p90_m: number; distinct_days: number }>;
};

type LabComboDetail = {
  noise_pct: number | null;
  coverage_pct: number | null;
  n_hubs: number;
  merged_pairs: number;
  geometry: LabGeometry;
};

type LabBundle = {
  metadata: Record<string, unknown>;
  grids: {
    dbscan: { eps_m: number[]; min_distinct_days: number[]; operating_eps_by_env: Record<string, number> };
    hdbscan: { combos: Array<{ min_cluster_size: number; min_samples: number }> };
    product_zone_fixed: { core_m: number; cap_m: number };
  };
  prior_experiment_reference: { run_ids: string[]; safe_band_note: string };
  aggregates: { dbscan: LabAggregateRow[]; hdbscan: LabAggregateRow[] };
  showcase_drivers: Record<string, Record<string, LabComboDetail>>;
};

const ENV_LABELS: Record<string, string> = {
  dense_urban: "도심 고밀도",
  suburban_mid_density: "교외 중밀도",
  wide_low_density: "광역 저밀도"
};

let labPromise: Promise<LabBundle> | null = null;
function fetchLab(): Promise<LabBundle> {
  labPromise ??= fetch("/api/gaip/lab").then(async (res) => {
    if (!res.ok) throw new Error(`lab bundle ${res.status}`);
    return (await res.json()) as LabBundle;
  });
  return labPromise;
}

function fmt(value: number | null | undefined, suffix = "%") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toLocaleString("ko-KR")}${suffix}`;
}

function LabMap({ detail }: { detail: LabComboDetail | null }) {
  if (!detail) return <p className="lab-map-empty">{t("이 조합의 대표 사례 스냅샷이 없습니다.")}</p>;
  const geo = detail.geometry;
  const xs = geo.points.map((p) => p.x_m).concat(geo.clusters.map((c) => c.x_m));
  const ys = geo.points.map((p) => p.y_m).concat(geo.clusters.map((c) => c.y_m));
  const pad = Math.max(600, ...geo.clusters.map((c) => c.buffer_m));
  const minX = Math.min(0, ...xs) - pad;
  const maxX = Math.max(0, ...xs) + pad;
  const minY = Math.min(0, ...ys) - pad;
  const maxY = Math.max(0, ...ys) + pad;
  const span = Math.max(maxX - minX, maxY - minY, 1);
  const size = 320;
  const sx = (x: number) => ((x - minX) / span) * size;
  const sy = (y: number) => size - ((y - minY) / span) * size;
  const scale = size / span;

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="lab-map" role="img" aria-label={t("선택한 설정의 생활권 스냅샷(도식)")}>
      {geo.clusters.map((c, i) => (
        <g key={`c${i}`}>
          <circle cx={sx(c.x_m)} cy={sy(c.y_m)} r={Math.max(6, c.buffer_m * scale)} className="lab-buffer" />
          <circle cx={sx(c.x_m)} cy={sy(c.y_m)} r={Math.max(3, 500 * scale)} className="lab-core" />
        </g>
      ))}
      {geo.points.map((p, i) => (
        <circle key={`p${i}`} cx={sx(p.x_m)} cy={sy(p.y_m)} r={2.6} className="lab-visit" />
      ))}
      <text x={8} y={size - 8} className="lab-map-note">
        {tf("도식(축척 유지) · 기준선 2개월 방문점 {points}개 · 거점 {clusters}개", { points: geo.points.length, clusters: geo.clusters.length })}
      </text>
    </svg>
  );
}

export function AlgorithmLabPanel({ preferredDriverId }: { preferredDriverId?: string | null }) {
  const [lab, setLab] = useState<LabBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [algo, setAlgo] = useState<"dbscan" | "hdbscan">("dbscan");
  const [epsIndex, setEpsIndex] = useState(1); // 180m
  const [minDays, setMinDays] = useState(3);
  const [hdbIndex, setHdbIndex] = useState(0);

  useEffect(() => {
    fetchLab().then(setLab).catch((cause) => setError(String(cause)));
  }, []);

  const epsGrid = lab?.grids.dbscan.eps_m ?? [];
  const eps = epsGrid[epsIndex] ?? 180;
  const hdbCombos = lab?.grids.hdbscan.combos ?? [];
  const hdb = hdbCombos[hdbIndex] ?? { min_cluster_size: 3, min_samples: 2 };

  const comboKey = algo === "dbscan" ? `dbscan-e${Math.round(eps)}-d${minDays}` : `hdbscan-c${hdb.min_cluster_size}-s${hdb.min_samples}`;

  const rows = useMemo(() => {
    if (!lab) return [] as LabAggregateRow[];
    const source = lab.aggregates[algo];
    return source.filter((row) =>
      algo === "dbscan"
        ? row.param_1 === eps && row.param_2 === minDays
        : row.param_1 === hdb.min_cluster_size && row.param_2 === hdb.min_samples
    );
  }, [lab, algo, eps, minDays, hdb]);

  const showcaseId = useMemo(() => {
    if (!lab) return null;
    if (preferredDriverId && lab.showcase_drivers[preferredDriverId]) return preferredDriverId;
    return lab.showcase_drivers["gaip-051"] ? "gaip-051" : Object.keys(lab.showcase_drivers)[0] ?? null;
  }, [lab, preferredDriverId]);

  const detail = showcaseId ? lab?.showcase_drivers[showcaseId]?.[comboKey] ?? null : null;
  const inSafeBand = algo === "dbscan" && eps >= 150 && eps <= 500;

  if (error) {
    return <p className="lab-map-empty">{tf("실험실 데이터를 불러오지 못했습니다: {error}", { error })}</p>;
  }
  if (!lab) {
    return <p className="lab-map-empty">{t("사전계산 실험 결과를 불러오는 중입니다…")}</p>;
  }

  return (
    <div className="algorithm-lab" aria-label={t("알고리즘 실험실")}>
      <div className="lab-intro">
        <strong>{t("지역 어댑터 — 밀도가 다른 시장에는 기준 거리(eps) 하나만 다시 맞추면 됩니다. 모델을 새로 만들 필요가 없습니다.")}</strong>
        <p>
          {t("같은 60명을 도심·교외·광역에 그대로 두고, 각 밀도에 맞춘 DBSCAN(도심 180m · 교외 420m · 광역 950m)으로 다시 군집화한 ")}
          <b>{t("사전 실측 스냅샷")}</b>
          {t("입니다. eps를 바꿔 보면 어디서부터 서로 다른 목적지가 잘못 합쳐지는지 (과병합)가 드러납니다 — 이것이 ")}
          <b>{t("다른 국가·시장에도 파라미터만 조정해 이식할 수 있다")}</b>
          {t("는 근거입니다. HDBSCAN은 고정 eps의 한계를 검증하는 비교 후보의 실측 결과입니다.")}
        </p>
      </div>

      <div className="lab-controls" role="group" aria-label={t("실험 설정")}>
        <div className="lab-algo-toggle">
          <button type="button" className={algo === "dbscan" ? "active" : ""} onClick={() => setAlgo("dbscan")}>
            {t("DBSCAN · 운영 기준 계열")}
          </button>
          <button type="button" className={algo === "hdbscan" ? "active" : ""} onClick={() => setAlgo("hdbscan")}>
            {t("HDBSCAN · 비교 후보 실측")}
          </button>
        </div>
        {algo === "dbscan" ? (
          <>
            <label className="lab-slider">
              <span>
                {t("기준 거리 eps ")}<strong>{Math.round(eps).toLocaleString("ko-KR")}m</strong>
                {inSafeBand ? <em className="lab-band-chip ok">{t("실측 안전 구간")}</em> : <em className="lab-band-chip warn">{t("구간 밖 — 지표 확인")}</em>}
              </span>
              <input
                type="range"
                min={0}
                max={Math.max(0, epsGrid.length - 1)}
                step={1}
                value={epsIndex}
                onChange={(event) => setEpsIndex(Number(event.target.value))}
              />
              <div className="lab-slider-ticks">
                {epsGrid.map((value, index) => (
                  <i key={value} className={index === epsIndex ? "on" : ""}>{Math.round(value)}</i>
                ))}
              </div>
            </label>
            <label className="lab-mindays">
              <span>{t("최소 방문일수(서로 다른 날)")}</span>
              <div className="lab-chip-row">
                {(lab.grids.dbscan.min_distinct_days ?? [2, 3, 5]).map((value) => (
                  <button key={value} type="button" className={value === minDays ? "active" : ""} onClick={() => setMinDays(value)}>
                    {value}{t("일")}
                  </button>
                ))}
              </div>
            </label>
          </>
        ) : (
          <label className="lab-mindays">
            <span>{t("HDBSCAN 설정 (최소 무리 크기 · 이웃 수)")}</span>
            <div className="lab-chip-row">
              {hdbCombos.map((combo, index) => (
                <button key={`${combo.min_cluster_size}-${combo.min_samples}`} type="button" className={index === hdbIndex ? "active" : ""} onClick={() => setHdbIndex(index)}>
                  {combo.min_cluster_size} · {combo.min_samples}
                </button>
              ))}
            </div>
          </label>
        )}
      </div>

      <div className="lab-body">
        <div className="lab-map-card">
          <span className="lab-card-title">{t("대표 사례 생활권 스냅샷 ")}{showcaseId ? `· ${showcaseId}` : ""}</span>
          <LabMap detail={detail} />
          {detail ? (
            <div className="lab-map-kpis">
              <span>{tf("거점 {n}개", { n: detail.n_hubs })}</span>
              <span>{tf("소음 {value}", { value: fmt(detail.noise_pct) })}</span>
              <span>{tf("커버리지 {value}", { value: fmt(detail.coverage_pct) })}</span>
              {detail.merged_pairs > 0 ? <span className="warn">{tf("과병합 {pairs}쌍", { pairs: detail.merged_pairs })}</span> : <span>{t("과병합 없음")}</span>}
            </div>
          ) : null}
        </div>

        <div className="lab-table-card">
          <span className="lab-card-title">{t("환경별 60명 집계 — 같은 설정을 세 환경에 적용한 결과")}</span>
          <table className="lab-table">
            <thead>
              <tr>
                <th>{t("이동환경")}</th>
                <th>{t("커버리지")}</th>
                <th>{t("소음")}</th>
                <th>{t("과병합")}</th>
                <th>{t("정기거점 누락")}</th>
                <th>{t("평균 거점 수")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const operating = algo === "dbscan" && lab.grids.dbscan.operating_eps_by_env[row.environment_id] === row.param_1;
                return (
                  <tr key={row.environment_id} className={operating ? "operating" : ""}>
                    <td>
                      {t(ENV_LABELS[row.environment_id] ?? row.environment_id)}
                      {operating ? <em>{t(" · 운영값")}</em> : null}
                    </td>
                    <td>{fmt(row.mean_coverage_pct)}</td>
                    <td>{fmt(row.mean_noise_pct)}</td>
                    <td>{fmt(row.overmerge_pct)}</td>
                    <td>{fmt(row.repeat_hub_miss_pct)}</td>
                    <td>{fmt(row.mean_hub_count, t("개"))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="lab-footnote">
            {t(lab.prior_experiment_reference.safe_band_note)}{t(" (선행 실험 ")}{lab.prior_experiment_reference.run_ids.join(" · ")}{t("). 과병합·누락의 정답 기준은 합성 생성 라벨이며, 모든 수치는 Simulated입니다. 알고리즘 채택·교체는 이 화면이 아니라 사람 검토(모델 리스크·상품)로 결정합니다.")}
          </p>
        </div>
      </div>
    </div>
  );
}
