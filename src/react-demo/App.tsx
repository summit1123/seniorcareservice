import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  FileText,
  MapPinned,
  Moon,
  Route,
  Search,
  ShieldCheck,
  Sun
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { demoApi } from "./api";
import { AlgorithmLabPanel } from "./AlgorithmLab";
import { CareReportModal } from "./CareReportModal";
import { getLocale, LOCALE_META, LOCALE_ORDER, setLocale, t, tf, type Locale } from "./i18n";
import { normalizeProductWeights } from "./gaip-decision";
import type { ProductRules } from "./gaip-types";
import type {
  DecisionSignal,
  Destination,
  DriverAnnualSummary,
  DriverOption,
  Interpretation,
  MatchedPairComparison,
  MatchedPairSide,
  MonthlyEvidence,
  PersonaDirectoryResponse,
  PersonaSummary,
  ZoneMapResponse,
  ZoneSnapshot,
  ZoneTripInterpretation
} from "./types";

const numberFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });

const decisionMeta: Record<string, { label: string; className: string }> = {
  // Labels are Korean source strings so t() localizes them (우대 → Favorable / 优待 / 優待 / Ưu đãi),
  // keeping the whole dashboard on the aligned "Favorable" terminology instead of raw "Reward".
  Reward: { label: "우대", className: "good" },
  Neutral: { label: "기본", className: "base" },
  Hold: { label: "판단 보류", className: "hold" },
  "Care Review": { label: "예방 케어", className: "care" },
  "Reward + Care Review": { label: "우대 + 예방 케어", className: "care" },
  우대: { label: "우대", className: "good" },
  기본: { label: "기본", className: "base" },
  "예방 케어": { label: "예방 케어", className: "care" },
  Favorable: { label: "우대", className: "good" },
  Preferred: { label: "우대", className: "good" },
  Standard: { label: "기본", className: "base" },
  "Preventive Care": { label: "예방 케어", className: "care" }
};

const interpretationMeta: Record<string, { label: string; className: string; short: string }> = {
  existing_living_zone: { label: "기준 생활권 안", className: "stable", short: "생활권 안" },
  out_zone_safe_driving: { label: "생활권 밖 안정", className: "safeout", short: "외부 안정" },
  out_zone_pattern_change_risk: { label: "동시변화 검토", className: "risk", short: "케어 검토" },
  // Months with zone unavailable / coverage below minimum — must not fall through to
  // the raw key with a green "stable" tone (84 such months exist in the bundle).
  evidence_hold: { label: "근거 부족 · 판단 보류", className: "hold", short: "보류" }
};

const reasonLabels: Record<string, string> = {
  BASELINE_OBSERVATION: "기준선 관찰월",
  CARE_EVIDENCE_INSUFFICIENT: "케어 근거 부족",
  HUMAN_CARE_REVIEW_SUGGESTED: "사람 검토 제안",
  REWARD_EVIDENCE_INSUFFICIENT: "우대 근거 부족",
  REWARD_REQUIRED_MONTHS_MET: "우대 충족월 기준 통과",
  REWARD_REQUIRED_MONTHS_NOT_MET: "우대 충족월 기준 미달",
  SAME_MONTH_CARE_GATE_MET: "같은 달 이동·위험행동 동시변화",
  PPT_ANNUAL_REFUND_CANDIDATE_USED: "발표용 연간 환급 후보값",
  SAME_MONTH_CARE_GATE_NOT_MET: "동시변화 게이트 미충족",
  CANDIDATE_LIVING_ZONE: "후보 생활권 관찰",
  HARSH_BRAKE_INCREASE: "급감속 증가",
  LOW_MILEAGE: "저주행 조건",
  LOW_NIGHT_DRIVING: "야간 주행 낮음",
  LOW_RISK_EVENTS: "위험행동 낮음",
  NIGHT_DRIVING_INCREASE: "야간 주행 증가",
  NO_RECENT_OUT_ZONE_SPIKE: "최근 생활권 밖 급증 없음",
  NO_STRONG_RISK_CHANGE: "강한 위험변화 없음",
  OUT_ZONE_PATTERN_CHANGE_RISK: "생활권 밖 위험변화",
  OUT_ZONE_RATIO_INCREASE: "생활권 밖 비중 증가",
  OUT_ZONE_SAFE: "생활권 밖 안정",
  OUT_ZONE_SAFE_DRIVING: "생활권 밖 안전주행",
  PREVENTIVE_CARE_REVIEW: "예방 케어 검토",
  RISK_EVENT_INCREASE: "위험행동 증가",
  STABLE_IN_ZONE_DRIVING: "생활권 안 안정주행"
};

const personaTypeLabels: Record<string, string> = {
  stable_reward: "안정 저주행형",
  in_zone_risky: "생활권 내 위험행동형",
  mobility_change_safe: "이동변화·안전유지형",
  mobility_risk_cochange: "이동·위험행동 동시변화형",
  multi_zone: "복수 생활권형",
  wide_area_safe: "광역 이동·안전형"
};

const destinationTypeLabels: Record<string, string> = {
  routine_hub_a: "반복 거점 A",
  routine_hub_b: "반복 거점 B",
  routine_hub_c: "반복 거점 C",
  new_visit: "신규 방문",
  outer_context: "생활권 밖 맥락"
};

const decisionStateKo: Record<string, string> = {
  Reward: "우대",
  Neutral: "기본",
  "Care Review": "예방 케어",
  Hold: "판단 보류",
  None: "해당 없음",
  Observation: "기준선 관찰"
};

function stateLabelKo(value: string | null | undefined) {
  if (!value) return "—";
  return t(decisionStateKo[value] ?? value);
}

// Agent mobility-profile text is bilingual (ko + en); Korean locale shows ko,
// every other locale shows en (proper-noun destination names / rationale).
function localeText(ko?: string | null, en?: string | null): string {
  const korean = (ko ?? "").trim();
  const english = (en ?? "").trim();
  return getLocale() === "ko" ? korean || english : english || korean;
}

function zoneRoleLabel(role?: string): string {
  if (role === "secondary") return t("두 번째 생활권");
  if (role === "change_destination") return t("하반기 신규 목적지");
  return t("생활권 안 거점");
}

function tierLabelKo(reward?: string | null, care?: string | null) {
  if (care === "Care Review") return t("예방 케어");
  if (reward === "Hold" || care === "Hold") return t("판단 보류");
  if (reward === "Reward") return t("우대");
  return t("기본");
}

const dynamicTextTranslations: Record<string, string> = {
  Neutral: "Standard",
  "Preventive Care": "Care Review"
};

// Display-only mirror of the engine's product formula (weights + mobility-change
// gate). These drive on-screen narrative text and score-meter tone ONLY — never a
// decision. The single source of truth is the bundle's product_rules; these values
// mirror DEFAULT_PRODUCT_RULES so the on-screen story matches the actual gate.
const selectedPolicy = {
  weights: {
    mileage: 0.3,
    inZone: 0.3,
    outZone: 0.2,
    riskChange: 0.2
  },
  thresholds: {
    // mobility_change_index gate = 0.25 → 25pt on the 0–100 change-index scale
    // (the engine's real Care mobility gate; previously a stray hardcoded 70).
    care: 25
  }
};

const careReviewRiskThreshold = selectedPolicy.thresholds.care;
const preferredRiskCeiling = 25;

function translateText(value: string) {
  let translated = value;
  Object.entries(dynamicTextTranslations).forEach(([source, target]) => {
    translated = translated.replaceAll(source, target);
  });
  return translated;
}

function personaTypeLabel(type: string) {
  return t(personaTypeLabels[type] ?? translateText(type));
}

function destinationTypeLabel(type: string) {
  return t(destinationTypeLabels[type] ?? translateText(type));
}


type LoadState = "loading" | "ready" | "error";
type PageMode = "overview" | "profiles";

function App() {
  const captureMode = typeof window !== "undefined"
    ? new URLSearchParams(window.location.search).get("capture")
    : null;
  const [directory, setDirectory] = useState<PersonaDirectoryResponse | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState("gaip-051");
  // The live presentation opens on the Jackie Chan case. The design overview
  // remains one click away for judges who want to inspect the model structure.
  const [pageMode, setPageMode] = useState<PageMode>("profiles");
  const [driver, setDriver] = useState<DriverAnnualSummary | null>(null);
  const [monthlyEvidence, setMonthlyEvidence] = useState<MonthlyEvidence[]>([]);
  const [selectedMonth, setSelectedMonth] = useState(1);
  const [zoneMap, setZoneMap] = useState<ZoneMapResponse | null>(null);
  const [directoryState, setDirectoryState] = useState<LoadState>("loading");
  const [driverState, setDriverState] = useState<LoadState>("loading");
  const [zoneState, setZoneState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [productRules, setProductRules] = useState<ProductRules | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof document === "undefined") return "light";
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "dark" || attr === "light") return attr;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("masil-theme", next);
    } catch (error) {
      void error;
    }
  };

  // ALWAYS English on entry (팀 결정 8/3): ignore any persisted choice so a
  // judge's first screen is EN even on a shared demo machine.
  const [lang, setLang] = useState<Locale>(() => getLocale());
  // Keep the i18n module locale in sync (source of truth for t()).
  if (typeof document !== "undefined") setLocale(lang);
  const changeLang = (next: Locale) => {
    setLocale(next);
    setLang(next);
    try {
      localStorage.setItem("masil-lang", next);
    } catch (error) {
      void error;
    }
  };

  useEffect(() => {
    let active = true;
    demoApi
      .getPersonaDirectory()
      .then((payload) => {
        if (!active) return;
        registerPersonaNames(payload.driver_options);
        setDirectory(payload);
        setProductRules(payload.product_rules ?? null);
        setSelectedCustomerId(payload.default_customer_id ?? payload.driver_options[0]?.customer_id ?? "gaip-051");
        setDirectoryState("ready");
      })
      .catch((error: Error) => {
        if (!active) return;
        setErrorMessage(error.message);
        setDirectoryState("error");
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!productRules || !directory) return;
    let active = true;
    demoApi.getPersonaDirectory(productRules).then((payload) => {
      if (!active) return;
      registerPersonaNames(payload.driver_options);
      setDirectory(payload);
    }).catch((error: Error) => {
      if (active) setErrorMessage(error.message);
    });
    return () => {
      active = false;
    };
  }, [productRules]);

  useEffect(() => {
    if (!directory) return;
    let active = true;
    setDriverState("loading");
    setZoneMap(null);
    Promise.all([
      demoApi.getAnnualSummary(selectedCustomerId, productRules ?? undefined),
      demoApi.getMonthlySnapshots(selectedCustomerId, productRules ?? undefined)
    ])
      .then(([summary, monthly]) => {
        if (!active) return;
        const focusMonth = chooseFocusMonth(monthly.monthly_evidence);
        setDriver(summary);
        setMonthlyEvidence(monthly.monthly_evidence);
        setSelectedMonth(focusMonth);
        setDriverState("ready");
      })
      .catch((error: Error) => {
        if (!active) return;
        setErrorMessage(error.message);
        setDriverState("error");
      });

    return () => {
      active = false;
    };
  }, [selectedCustomerId, productRules]);

  useEffect(() => {
    if (!driver) return;
    let active = true;
    setZoneState("loading");
    demoApi
      .getZoneMap(driver.customer_id, selectedMonth, productRules ?? undefined)
      .then((payload) => {
        if (!active) return;
        setZoneMap(payload);
        setZoneState("ready");
      })
      .catch((error: Error) => {
        if (!active) return;
        setErrorMessage(error.message);
        setZoneState("error");
      });

    return () => {
      active = false;
    };
  }, [driver, selectedMonth, productRules]);

  const selectedOption = useMemo(
    () => directory?.driver_options.find((option) => option.customer_id === selectedCustomerId),
    [directory, selectedCustomerId]
  );

  const selectProfile = (customerId: string) => {
    setSelectedCustomerId(customerId);
    setPageMode("profiles");
  };

  if (directoryState === "loading") {
    return <ScreenState title={t("시뮬레이션 근거 연결 중")} detail={t("60명 합성 코호트와 14개월 판단 근거를 불러오는 중입니다.")} />;
  }

  if (directoryState === "error" || !directory) {
    return <ScreenState title={t("데모 데이터를 열 수 없습니다")} detail={errorMessage} />;
  }

  if (captureMode === "monthly") {
    if (driverState !== "ready" || !monthlyEvidence.length) {
      return <ScreenState title={t("월별 점수 불러오는 중")} detail={t("캡처 전용 화면을 준비하고 있습니다.")} />;
    }
    return <MonthlyScoreCapture rows={monthlyEvidence} rules={productRules} />;
  }

  return (
    <div className="workbench">
      <header className="app-header">
        <div className="brand-block">
          <div>
            <p className="eyebrow">FOURSURE · MASIL · GAIP Insurance Innovation Competition 2026</p>
            <h1>{t("Senior MASIL Zone Rider 대시보드")}</h1>
            <p>{t("월별 4개 지표를 통합점수와 3단계로 연결하고, 12개월 결과로 연간 환급을 제안합니다.")}</p>
          </div>
        </div>
        <div className="header-actions">
          <div className="header-controls">
            <div className="page-switch" aria-label={t("페이지 전환")}>
              <button
                type="button"
                className={pageMode === "profiles" ? "active" : ""}
                onClick={() => setPageMode("profiles")}
                aria-current={pageMode === "profiles" ? "page" : undefined}
              >
                {t("프로필 분석")}
              </button>
              <button
                type="button"
                className={pageMode === "overview" ? "active" : ""}
                onClick={() => setPageMode("overview")}
                aria-current={pageMode === "overview" ? "page" : undefined}
              >
                {t("설계구조")}
              </button>
            </div>
            <div className="lang-switch" role="group" aria-label={t("언어 선택")}>
              {LOCALE_ORDER.map((code) => (
                <button
                  key={code}
                  type="button"
                  className={lang === code ? "active" : ""}
                  onClick={() => changeLang(code)}
                  aria-pressed={lang === code}
                  title={LOCALE_META[code].label}
                >
                  {LOCALE_META[code].short}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="theme-toggle"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? t("라이트 모드로 전환") : t("다크 모드로 전환")}
              title={theme === "dark" ? t("라이트 모드") : t("다크 모드")}
            >
              {theme === "dark" ? <Sun /> : <Moon />}
            </button>
          </div>
          <div className="contract-box">
            <span>{t("데모 범위")}</span>
            <strong>{t("합성 데이터 · 고정 규칙 · 사람 승인")}</strong>
            <small>{t("2개월 기준선 + 12개월 평가 · 실제 환급률 아님")}</small>
          </div>
        </div>
      </header>

      {pageMode === "overview" ? (
        <DesignOverviewPage directory={directory} rules={productRules} onRulesChange={setProductRules} />
      ) : (
        <main className="decision-dashboard">
          <CaseRail
            options={directory.driver_options}
            selectedCustomerId={selectedCustomerId}
            onSelect={selectProfile}
          />

          <section className="decision-main">
            <EnvSwitcher
              options={directory.driver_options}
              selectedCustomerId={selectedCustomerId}
              onSelect={selectProfile}
            />
            <DecisionSummaryCard
              driver={driver}
              zoneMap={zoneMap}
              rows={monthlyEvidence}
              selectedMonth={selectedMonth}
              driverState={driverState}
            />

            <LivingZoneDecisionMap
              driver={driver}
              zoneMap={zoneMap}
              selectedMonth={selectedMonth}
              zoneState={zoneState}
            />

            <DecisionProcessFrame
              driver={driver}
              zoneMap={zoneMap}
              rows={monthlyEvidence}
              selectedMonth={selectedMonth}
              rules={productRules}
            />

            <MonthlyEvidenceLane
              rows={monthlyEvidence}
              selectedMonth={selectedMonth}
              loading={driverState === "loading"}
              onSelectMonth={setSelectedMonth}
              rules={productRules}
            />

            <AnalysisTabs
              driver={driver}
              zoneMap={zoneMap}
              rows={monthlyEvidence}
              selectedMonth={selectedMonth}
              loading={driverState === "loading"}
              onSelectMonth={setSelectedMonth}
              rules={productRules}
            />
          </section>

          <DecisionPanel
            driver={driver}
            zoneMap={zoneMap}
            rows={monthlyEvidence}
            selectedMonth={selectedMonth}
            loading={driverState === "loading"}
            rules={productRules}
          />
        </main>
      )}
    </div>
  );
}

function MonthlyScoreCapture({ rows, rules }: { rows: MonthlyEvidence[]; rules: ProductRules | null }) {
  const weights = normalizeProductWeights(rules?.weights ?? referenceProductRules.weights);
  const focusMonth = chooseFocusMonth(rows);
  const row = rows.find((item) => item.month === focusMonth) ?? rows[0];
  const score = row.monthly_integrated_evidence_score ?? monthlyIntegratedEvidenceScore(row);

  return (
    <main className="monthly-capture-page" aria-label={t("PPT용 월별 점수 요약")}>
      <section className="monthly-capture-card">
        <div className="monthly-capture-month">
          <span>{t("선택 월")}</span>
          <strong>{row.service_month}</strong>
          <small>{t("월별 4개 지표")}</small>
        </div>
        <div className="monthly-capture-metrics">
          <ScoreMeter label={t("주행거리 점수")} value={row.mileage_score} />
          <ScoreMeter label={t("생활권 안 안전점수")} value={row.in_zone_safe_driving_score} />
          <ScoreMeter label={t("생활권 밖 안전점수")} value={row.out_zone_safe_driving_score} />
          <ScoreMeter label={t("패턴 안정성")} value={row.pattern_stability_score ?? Math.max(0, 100 - row.out_zone_pattern_change_risk)} />
        </div>
        <ArrowRight className="monthly-capture-arrow" aria-hidden="true" />
        <div className="monthly-capture-result">
          <span>{t("월 통합점수")}</span>
          <strong>{tf("{score}점", { score: numberFormatter.format(score) })}</strong>
          <small>{tf("{mileage} · {inZone} · {outZone} · {stability}", { mileage: `${weights.mileage}%`, inZone: `${weights.in_zone_safe}%`, outZone: `${weights.out_zone_safe}%`, stability: `${weights.pattern_stability}%` })}</small>
        </div>
      </section>
    </main>
  );
}

function DesignOverviewPage({
  directory,
  rules,
  onRulesChange
}: {
  directory: PersonaDirectoryResponse;
  rules: ProductRules | null;
  onRulesChange: (rules: ProductRules) => void;
}) {
  return (
    <main className="overview-page" aria-label={t("상품 설계구조 화면")}>
      {/* Narrative order: problem/result → the formula and WHY (blueprint) → THEN the
          sandbox that lets a judge perturb that formula → persona overview. Knobs after
          the machine they tune. */}
      <OverviewComparisonPanel directory={directory} />
      <RepresentativePairPanel rules={rules} />
      <ProductBlueprintPanel directory={directory} />
      {rules ? <ScenarioControlPanel rules={rules} onChange={onRulesChange} directory={directory} /> : null}
      <PersonaMatrix summaries={directory.persona_summaries} />
    </main>
  );
}

// 대표 대조 사례 — 180개 시나리오에서 조건이 가장 비슷하고 행동만 다른 케어×우대
// 페어를 고정 표로 보여준다. 샌드박스 규칙이 바뀌면 같은 기준으로 다시 고른다.
function RepresentativePairPanel({ rules }: { rules: ProductRules | null }) {
  const [pair, setPair] = useState<MatchedPairComparison | null>(null);
  useEffect(() => {
    let cancelled = false;
    demoApi.getRepresentativePair(rules ?? undefined).then((result) => {
      if (!cancelled) setPair(result);
    }).catch(() => {
      if (!cancelled) setPair(null);
    });
    return () => { cancelled = true; };
  }, [rules]);
  if (!pair) return null;
  return (
    <section className="panel representative-pair-panel" aria-label={t("대표 대조 사례")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("대표 사례")}</p>
          <h2>{t("같은 조건, 다른 행동")}</h2>
        </div>
        <p className="panel-note">{t("180개 시나리오에서 조건이 가장 비슷하고 행동만 다른 두 사람의 실제 판정입니다.")}</p>
      </div>
      <MatchedPairTable pair={pair} selfTag={t("케어 사례")} otherTag={t("우대 사례")} />
    </section>
  );
}

function personaToneFromDecisions(counts: Record<string, number>): string {
  const care = (counts["Care Review"] ?? 0) + (counts["Reward + Care Review"] ?? 0);
  const neutral = counts["Neutral"] ?? 0;
  const reward = counts["Reward"] ?? 0;
  const hold = counts["판단 보류"] ?? 0;
  if (care > 0) return "risk";
  if (hold > reward + neutral) return "base";
  if (neutral > reward) return "base";
  return "safe";
}

function PersonaMatrix({ summaries }: { summaries: PersonaSummary[] }) {
  if (!summaries.length) return null;
  const total = summaries.reduce((sum, item) => sum + item.customer_count, 0);
  return (
    <section className="panel persona-matrix" aria-label={t("페르소나 유형 비교")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("페르소나 유형")}</p>
          <h2>{t("6개 유형이 서로 다른 판단 장면을 만듭니다")}</h2>
        </div>
        <span className="count-badge">{tf("{count}개 시나리오", { count: total })}</span>
      </div>
      <div className="persona-grid">
        {summaries.map((summary) => (
          <div className={`persona-card ${personaToneFromDecisions(summary.decision_counts)}`} key={summary.persona_type}>
            <strong>{personaTypeLabel(summary.persona_type)}</strong>
            <div className="persona-metrics">
              <span>
                <b>{tf("{km}km", { km: numberFormatter.format(Math.round(summary.avg_annual_distance_km)) })}</b>
                <small>{t("평균 연간 주행")}</small>
              </span>
              <span>
                <b>{tf("{score}점", { score: numberFormatter.format(summary.avg_annual_score) })}</b>
                <small>{t("평균 통합점수")}</small>
              </span>
            </div>
            <p className="persona-decisions">{formatDecisionCounts(summary.decision_counts)}</p>
            <small className="persona-rate">
              {tf("환급률 {a}% → {b}%", { a: numberFormatter.format(summary.avg_existing_discount_rate_pct), b: numberFormatter.format(summary.avg_proposed_discount_rate_pct) })}
            </small>
          </div>
        ))}
      </div>
    </section>
  );
}

const referenceProductRules: ProductRules = {
  weights: { mileage: 30, in_zone_safe: 30, out_zone_safe: 20, pattern_stability: 20 },
  reward_score_threshold: 75,
  minimum_data_coverage_pct: 80,
  reward_required_months: 9,
  care_mobility_change_threshold: 25,
  care_risky_behavior_threshold: 20,
  reward_discount_rate_pct: 7,
  reward_bonus_floor_pct: 1,
  candidate_discount_cap_pct: 45
};

function ScenarioControlPanel({
  rules,
  onChange,
  directory
}: {
  rules: ProductRules;
  onChange: (rules: ProductRules) => void;
  directory: PersonaDirectoryResponse;
}) {
  const normalized = normalizeProductWeights(rules.weights);
  // The directory is re-derived from `rules` upstream, so these counts update
  // live as the sliders move — the "same engine recomputes" readout.
  const options = directory.driver_options;
  const total = Math.max(1, options.length);
  const liveCare = options.filter((o) => o.care_state === "Care Review").length;
  const liveHold = options.filter((o) => o.reward_state === "Hold" || o.care_state === "Hold").length;
  const liveReward = options.filter(
    (o) => o.reward_state === "Reward" && o.care_state !== "Care Review" && o.care_state !== "Hold"
  ).length;
  const liveNeutral = Math.max(0, total - liveReward - liveCare - liveHold);
  const liveReadout: Array<{ key: string; label: string; count: number; cls: string }> = [
    { key: "reward", label: t("우대"), count: liveReward, cls: "preferred" },
    { key: "neutral", label: t("기본"), count: liveNeutral, cls: "standard" },
    { key: "care", label: t("예방 케어"), count: liveCare, cls: "care" },
    { key: "hold", label: t("판단 보류"), count: liveHold, cls: "hold" }
  ];
  const avgDiscount = directory.summary.avg_proposed_discount_rate_pct;
  const updateWeight = (key: keyof ProductRules["weights"], value: number) => {
    onChange({ ...rules, weights: { ...rules.weights, [key]: value } });
  };
  const updateRule = (key: keyof ProductRules, value: number) => {
    onChange({ ...rules, [key]: value });
  };
  const weightRows: Array<{ key: keyof ProductRules["weights"]; label: string }> = [
    { key: "mileage", label: t("주행거리") },
    { key: "in_zone_safe", label: t("생활권 안 안전") },
    { key: "out_zone_safe", label: t("생활권 밖 안전") },
    { key: "pattern_stability", label: t("패턴 안정성") }
  ];

  const presets: Array<{ id: string; label: string; hint: string; rules: ProductRules }> = [
    {
      id: "kr",
      label: t("국내 기준 (기본)"),
      hint: t("국내 수상안 PoC 설정 — 30:30:20:20 · 우대 75점/9개월"),
      rules: referenceProductRules
    },
    {
      id: "intl-conservative",
      label: t("국제 예시 A · 보수적"),
      hint: t("우대 문턱을 높이고 케어를 더 민감하게 보는 시장 가정"),
      rules: {
        ...referenceProductRules,
        reward_score_threshold: 80,
        reward_required_months: 10,
        care_mobility_change_threshold: 20,
        care_risky_behavior_threshold: 15
      }
    },
    {
      id: "intl-wide",
      label: t("국제 예시 B · 광역 시장"),
      hint: t("장거리 이동이 일상인 시장 가정 — 이동 변화 허용 폭 확대"),
      rules: {
        ...referenceProductRules,
        weights: { mileage: 25, in_zone_safe: 30, out_zone_safe: 25, pattern_stability: 20 },
        reward_score_threshold: 70,
        reward_required_months: 8,
        care_mobility_change_threshold: 35,
        care_risky_behavior_threshold: 25
      }
    }
  ];

  return (
    <section className="panel scenario-control-panel" aria-label={t("상품 규칙 민감도 설정")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("상품 규칙 샌드박스")}</p>
          <h2>{t("상품 담당자가 후보 가중치와 임계치를 바꾸면 180개 사례가 즉시 다시 계산됩니다")}</h2>
        </div>
        <button type="button" className="sandbox-reset" onClick={() => onChange(referenceProductRules)}>{t("30:30:20:20 복원")}</button>
      </div>
      <div className="sandbox-presets" role="group" aria-label={t("시장 기준 프리셋")}>
        <span className="sandbox-presets-title">{t("기준 프리셋 — 시장이 달라도 같은 엔진이 다시 계산합니다")}</span>
        <div className="sandbox-presets-row">
          {presets.map((preset) => (
            <button key={preset.id} type="button" title={preset.hint} onClick={() => onChange(preset.rules)}>
              {preset.label}
            </button>
          ))}
        </div>
      </div>
      <div className="sandbox-layout">
        <span className="sandbox-axis-label">{t("① 월 통합점수 가중치 — 4개 지표를 어떤 비율로 합칠지 (합계 100%)")}</span>
        <div className="sandbox-weight-grid">
          {weightRows.map((row) => (
            <label key={row.key}>
              <span>{row.label}</span>
              <strong>{normalized[row.key]}%</strong>
              <input
                type="range"
                min="0"
                max="60"
                step="5"
                value={rules.weights[row.key]}
                onChange={(event) => updateWeight(row.key, Number(event.target.value))}
              />
            </label>
          ))}
        </div>
        <span className="sandbox-axis-label">{t("② Favorable 기준 — 월 점수를 Favorable로 인정하는 기준")}</span>
        <div className="sandbox-threshold-grid">
          <RuleNumber label={t("우대 점수")} helper={t("통합점수가 이 값 이상인 달을 우대 후보로 봄")} value={rules.reward_score_threshold} min={50} max={95} onChange={(value) => updateRule("reward_score_threshold", value)} />
          <RuleNumber label={t("우대 충족월")} helper={t("12개월 중 우대 점수를 넘긴 달이 이만큼 있어야 연간 우대")} value={rules.reward_required_months} min={1} max={12} suffix={t("개월")} onChange={(value) => updateRule("reward_required_months", value)} />
          <RuleNumber label={t("최소 데이터")} helper={t("이 커버리지 미만이면 판단 보류(불이익 없음)")} value={rules.minimum_data_coverage_pct} min={50} max={100} suffix="%" onChange={(value) => updateRule("minimum_data_coverage_pct", value)} />
        </div>
        <span className="sandbox-axis-label care">{t("③ Care 기준 — 직전 2개월 대비 이동 변화와 위험행동 변화가 같은 달 함께 나타날 때")}</span>
        <div className="sandbox-threshold-grid">
          <RuleNumber label={t("이동 변화 임계")} helper={t("기준선 대비 생활권 밖 비중 상승폭이 이 값을 넘어야 케어 후보")} value={rules.care_mobility_change_threshold} min={0} max={100} suffix="%" onChange={(value) => updateRule("care_mobility_change_threshold", value)} />
          <RuleNumber label={t("위험행동 변화 임계")} helper={t("기준선 대비 위험행동 상승폭 — 이동 변화와 함께 넘어야 케어")} value={rules.care_risky_behavior_threshold} min={0} max={100} suffix="%" onChange={(value) => updateRule("care_risky_behavior_threshold", value)} />
          <div className="rule-static" title={t("케어 검토 진행 중")}>
            <span>{t("케어 결합 규칙 (선언값)")}</span>
            <strong>{t("사람 검토로 연결")}</strong>
            <small>{t("Care는 그달의 예방지원 상태입니다. 다음 달은 다시 같은 기준으로 평가하며, Care 자체가 연간 환급을 자동으로 줄이지 않습니다.")}</small>
          </div>
        </div>
      </div>
      <div className="sandbox-live" aria-live="polite">
        <div className="sandbox-live-head">
          <span className="sandbox-live-title">{t("지금 규칙으로 다시 계산한 180개 사례")}</span>
          <span className="sandbox-live-avg">{t("제안 평균 환급률 ")}<strong>{percent(avgDiscount)}</strong></span>
        </div>
        <div className="sandbox-live-bar" role="img" aria-label={tf("우대 {reward}, 기본 {neutral}, 예방 케어 {care}, 판단 보류 {hold}", { reward: liveReward, neutral: liveNeutral, care: liveCare, hold: liveHold })}>
          {liveReadout.map((seg) =>
            seg.count > 0 ? (
              <span
                key={seg.key}
                className={`sandbox-live-seg ${seg.cls}`}
                style={{ flexGrow: seg.count }}
                title={tf("{label} {count}사례", { label: seg.label, count: seg.count })}
              />
            ) : null
          )}
        </div>
        <div className="sandbox-live-legend">
          {liveReadout.map((seg) => (
            <span key={seg.key} className={`sandbox-live-chip ${seg.cls}`}>
              <i />
              {seg.label} <strong>{seg.count}</strong>
            </span>
          ))}
        </div>
      </div>
      <p className="sandbox-footnote">
        {t("가중치 합계는 계산 시 100%로 재정규화되며, 모든 값은 시뮬레이션 후보입니다. 알고리즘 파라미터(eps·최소 방문일수)는 결정 주체가 달라 이 화면이 아니라 ")}<b>{t("알고리즘 실험실")}</b>{t(" 탭에서 비교합니다.")}
      </p>
    </section>
  );
}

function RuleNumber({
  label,
  value,
  min,
  max,
  suffix = t("점"),
  helper,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  suffix?: string;
  helper?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="rule-number">
      <span>{label}</span>
      <input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Math.max(min, Math.min(max, Number(event.target.value))))} />
      <em>{suffix}</em>
      {helper ? <small>{helper}</small> : null}
    </label>
  );
}

function OverviewComparisonPanel({ directory }: { directory: PersonaDirectoryResponse }) {
  const summary = directory.summary;
  const total = Math.max(1, directory.driver_options.length);
  const careCount = directory.driver_options.filter((option) => option.care_state === "Care Review").length;
  const holdCount = directory.driver_options.filter(
    (option) => option.reward_state === "Hold" || option.care_state === "Hold"
  ).length;
  const preferredCount = directory.driver_options.filter(
    (option) => option.reward_state === "Reward" && option.care_state !== "Care Review" && option.care_state !== "Hold"
  ).length;
  const standardCount = Math.max(0, total - preferredCount - careCount - holdCount);
  const p1 = (preferredCount / total) * 100;
  const p2 = p1 + (standardCount / total) * 100;
  const p3 = p2 + (careCount / total) * 100;
  const donutBackground = `conic-gradient(var(--primary) 0 ${p1}%, var(--faint) ${p1}% ${p2}%, var(--amber) ${p2}% ${p3}%, var(--line-strong) ${p3}% 100%)`;
  const avgRateDelta = summary.avg_proposed_discount_rate_pct - summary.avg_existing_discount_rate_pct;

  return (
    <section className="panel comparison-overview" aria-label={t("전체 비교 대시보드")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("전체 비교")}</p>
          <h2>{t("시니어 60명을 3개 이동환경에서 각각 돌린 180개 사례로, 기존 마일리지 기준과 제안 산식을 비교합니다")}</h2>
        </div>
        <span className="count-badge">{tf("인물 60명 × 3환경 = {count}사례 · 기준선 2개월 + 평가 12개월", { count: summary.customer_count })}</span>
      </div>

      <div className="judge-takeaway" aria-label={t("핵심 평가 포인트")}>
        <div>
          <span>{t("문제")}</span>
          <strong>{t("기존 마일리지는 저주행 여부는 보지만 이동 맥락의 차이는 설명하기 어렵습니다")}</strong>
          <p>{t("같은 주행거리 안에서도 안정적 반복 이동과 갑작스러운 이동·위험행동 동시변화를 구분할 근거가 부족합니다.")}</p>
        </div>
        <div>
          <span>{t("제안 차별점")}</span>
          <strong>{t("월별 4개 지표를 통합점수와 3단계로 연결합니다")}</strong>
          <p>{t("월 통합점수는 Favorable·Standard·Care를 구분하고, 12개월 점수는 연간 환급 제안으로 이어집니다.")}</p>
          <p className="stakes-line">{t("예방 케어는 처벌이 아니라 조기 개입입니다 — 심각한 사고가 나기 전에 담당자가 가족·의료·이동지원과 연결할 근거를 만드는 것이 목표입니다.")}</p>
        </div>
        <div>
          <span>{t("검증 결과")}</span>
          <strong>{t("도심·교외·광역 저밀도 환경에서도 동일한 안전 원칙을 검증합니다")}</strong>
          <p>{t("결과는 합성 시나리오에서 상품 논리의 일관성과 예외 처리를 확인한 것입니다. 실제 사고감소·손해율·최종 환급률은 파일럿에서 검증합니다.")}</p>
        </div>
      </div>

      <div className="risk-hypothesis">
        <span className="eyebrow">{t("위험 가설")}</span>
        <strong>{t("익숙함은 개인마다 다르므로, 각자의 기준선에서 변화를 봅니다")}</strong>
        <p>{t("처음 가는 길은 더 많은 주의가 필요한 맥락이지만, 생활권 밖이라는 위치만으로 불이익을 주지는 않습니다. 실제 안전운전과 평소 대비 변화를 함께 봅니다.")}</p>
        <p className="hypothesis-note">{t("이 가설의 계산 가능성과 예외 처리를 합성 데이터로 검증하며, 실제 사고·손해율 상관은 별도 실증이 필요합니다.")}</p>
      </div>

      <div className="experiment-structure">
        <span className="eyebrow">{t("데이터 실험 구조")}</span>
        <strong>{t("근거 기반 표본 프로필로 주행 데이터를 만들고, 고정 규칙으로 상품 논리를 검증합니다")}</strong>
        <div className="experiment-structure-grid">
          <div className="es-step">
            <b>{t("1 · 표본 프로필과 주행 로그")}</b>
            <p>{t("6개 시니어 유형과 공개 운전 기준·사고 통계를 참고해 3개 지역의 14개월 합성 주행 로그를 만듭니다.")}</p>
          </div>
          <div className="es-step">
            <b>{t("2 · 분석 — 결정론 엔진")}</b>
            <p>{t("DBSCAN과 P90으로 개인별 MASIL Zone을 만들고, 4개 점수와 3단계를 고정된 설명 가능 규칙으로 계산합니다.")}</p>
          </div>
          <div className="es-step">
            <b>{t("3 · 검증 — 재현 가능")}</b>
            <p>{t("같은 입력에는 같은 결과가 나오도록 180개 시나리오의 계산 재현성과 예외 처리를 확인합니다.")}</p>
          </div>
        </div>
        <p className="experiment-structure-note">{t("합성 데이터는 상품 로직을 검증하기 위한 표본입니다. 실제 사고 감소·손해율·최종 환급률은 실데이터 파일럿에서 검증합니다.")}</p>
      </div>

      <div className="buyer-trust">
        <span className="eyebrow">{t("구매자 행동 · 신뢰")}</span>
        <strong>{t("감시가 아니라, 계속 안전하게 운전할 자유를 지키는 설계입니다")}</strong>
        <div className="buyer-trust-grid">
          <div>
            <b>{t("운전할 자유")}</b>
            <p>{t("나이로 벌점을 매기지 않고, 익숙한 생활권 안 안전운전을 혜택으로 돌려줍니다. 시니어가 가장 두려워하는 운전 상실을 처벌이 아니라 인정으로 바꿉니다.")}</p>
          </div>
          <div>
            <b>{t("감시가 아닌 존중")}</b>
            <p>{t("어디를 가든 위치만으로 감점하지 않습니다. 목적지 이름은 가리고, 최소 수집과 권한 분리 원칙으로 필요한 정보만 다룹니다.")}</p>
          </div>
          <div>
            <b>{t("가족의 안심")}</b>
            <p>{t("이동과 위험행동이 같은 달에 함께 나빠질 때만, 처벌이 아니라 조기 개입 신호를 사람에게 전합니다. 부모의 운전을 걱정하는 가족이 믿고 맡길 수 있는 근거입니다.")}</p>
          </div>
        </div>
        <p className="buyer-trust-note">{t("운전을 제한하기보다 개인별 위험을 더 정확히 보고, 안전한 이동을 오래 유지하도록 돕는 것이 이 설계의 목표입니다.")}</p>
      </div>

      <div className="comparison-ledger" aria-label={t("기존 마일리지와 제안 산식 비교표")}>
        <div className="ledger-head">
          <span>{t("비교 항목")}</span>
          <strong>{t("기존 마일리지 산식 · 국내 기준")}</strong>
          <strong>{t("마실 제안 산식 · 시뮬레이션 후보")}</strong>
        </div>
        <ComparisonLedgerRow
          label={t("판단 기준")}
          legacy={t("연간 주행거리 구간으로 환급률 결정")}
          proposed={t("주행거리 + 생활권 안/밖 안전 + 패턴 안정성")}
        />
        <ComparisonLedgerRow
          label={t("같은 저주행 구간 처리")}
          legacy={t("같은 거리구간이면 행동 차이와 관계없이 같은 환급")}
          proposed={t("4개 지표의 월 통합점수로 Favorable·Standard·Care를 구분")}
        />
        <ComparisonLedgerRow
          label={t("연간 환급 계산")}
          legacy={t("거리구간 환급률을 그대로 적용")}
          proposed={t("12개월 점수의 연간 평균과 Favorable 누적을 환급 제안에 반영")}
        />
        <ComparisonLedgerRow
          label={t("설명 가능성")}
          legacy={t("조정 근거가 ‘적게 탔다’에 머물러 설명력이 약함")}
          proposed={t("비식별 반복 거점, 월별 근거, 사유 코드와 사람 검토 기록 제공")}
        />
      </div>

      <div className="overview-evidence-grid">
        <div className="decision-donut-card">
          <span>{t("월 통합점수의 3단계 결과")}</span>
          <div className="decision-donut-wrap">
            <div className="decision-donut" style={{ background: donutBackground }}>
              <div>
                <strong>{summary.customer_count}</strong>
                <small>{t("사례 판정 분포")}</small>
              </div>
            </div>
            <div className="decision-donut-legend">
              <DecisionLegend label={tf("우대 {count}", { count: preferredCount })} detail={t("월 점수 · 안전 인정")} className="preferred" />
              <DecisionLegend label={tf("기본 {count}", { count: standardCount })} detail={t("변화 낮음 · 중립")} className="standard" />
              <DecisionLegend label={tf("예방 케어 {count}", { count: careCount })} detail={t("동시변화 · 사람 검토")} className="care" />
              {holdCount ? (
                <DecisionLegend label={tf("판단 보류 {count}", { count: holdCount })} detail={t("근거 부족 · 불이익 없음")} className="hold" />
              ) : null}
            </div>
          </div>
          <p className="portfolio-footnote">
            {t("4개 지표의 월 통합점수는 Favorable·Standard·Care로 표시합니다. Hold는 네 번째 위험등급이 아니라, 근거가 부족해 판단을 미루는 상태입니다.")}
          </p>
        </div>

        <div className="simulation-result-card">
          <span>{t("국내 기준 A/B 시뮬레이션 · 180개 사례")}</span>
          <strong>{t("총액을 맞춰 끼운 값이 아니라, 두 산식을 각각 계산한 결과입니다")}</strong>
          <p>
            {t("같은 인물 60명(6개 유형 × 10명)을 3개 이동환경에서 각각 시뮬레이션한 180개 사례의 연간 주행 데이터를, 기존 마일리지 산식과 제안 통합 산식에 각각 넣어 비교했습니다. 이 단계에서는 평균 환급률과 Favorable·Standard·Care 판정 구조를 검증합니다.")}
          </p>
          <p className="business-case-line">{t("제안 산식은 비슷한 주행거리 안의 위험 차이를 더 세밀하게 구분합니다. 조기 예방지원이 실제 사고와 손해율을 얼마나 줄이는지는 파일럿에서 검증합니다.")}</p>
          <div className="budget-compare-grid no-money">
            <div>
              <span>{t("기존 평균 환급률")}</span>
              <strong>{percent(summary.avg_existing_discount_rate_pct)}</strong>
              <small>{t("연간 주행거리 구간 기준")}</small>
            </div>
            <div>
              <span>{t("제안 평균 환급률")}</span>
              <strong>{percent(summary.avg_proposed_discount_rate_pct)}</strong>
              <small>{t("4개 지표 통합점수 기준")}</small>
            </div>
            <div>
              <span>{t("기존 대비 평균 차이")}</span>
              <strong>{signedPercentPoint(avgRateDelta)}</strong>
              <small>{t("4개 지표와 연간 점수로 환급 후보를 다시 배분한 합성 비교")}</small>
            </div>
          </div>
          <p className="portfolio-footnote">
            {t("합성 시뮬레이션 결과입니다. 실제 환급률·인수·케어 결정은 계리·상품·심사 권한자의 검토 없이 확정하지 않습니다. 기준을 바꾸면 아래 상품 샌드박스가 180개 사례를 다시 계산합니다.")}
          </p>
        </div>
      </div>
    </section>
  );
}

function ComparisonLedgerRow({ label, legacy, proposed }: { label: string; legacy: string; proposed: string }) {
  return (
    <div className="ledger-row">
      <span>{label}</span>
      <p>{legacy}</p>
      <p>{proposed}</p>
    </div>
  );
}

function DecisionLegend({ label, detail, className }: { label: string; detail: string; className: string }) {
  return (
    <div className={`decision-donut-legend-row ${className}`}>
      <i />
      <strong>{label}</strong>
      <span>{detail}</span>
    </div>
  );
}


/** 같은 사람을 3개 이동환경에서 비교 — 회의 결정: 좌측은 사람, 환경은 중앙에서 전환. */
function EnvSwitcher({ options, selectedCustomerId, onSelect }: {
  options: DriverOption[];
  selectedCustomerId: string;
  onSelect: (id: string) => void;
}) {
  const current = options.find((o) => o.customer_id === selectedCustomerId);
  if (!current) return null;
  const person = personaName(current.customer_id);
  const siblings = options.filter((o) => personaName(o.customer_id) === person);
  if (siblings.length < 2) return null;
  return (
    <div className="env-switch" role="tablist" aria-label={t("이동환경 비교")}>
      <span>{t("같은 사람 · 환경 비교")}</span>
      {siblings.map((o) => (
        <button
          key={o.customer_id}
          type="button"
          role="tab"
          aria-selected={o.customer_id === selectedCustomerId}
          className={o.customer_id === selectedCustomerId ? "active" : ""}
          onClick={() => onSelect(o.customer_id)}
        >
          {t(o.environment_display_name_ko ?? o.environment_id ?? "")}
        </button>
      ))}
    </div>
  );
}

function CaseRail({
  options,
  selectedCustomerId,
  onSelect
}: {
  options: DriverOption[];
  selectedCustomerId: string;
  onSelect: (customerId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [decisionFilter, setDecisionFilter] = useState("all");
  const decisionFilters = [
    { value: "all", label: t("전체") },
    { value: "Reward", label: t("우대") },
    { value: "Neutral", label: t("기본") },
    { value: "Care Review", label: t("케어") },
    { value: "Hold", label: t("보류") }
  ];
  const filtered = options.filter((option) => {
    const text = `${personaName(option.customer_id)} ${caseNo(option.customer_id)} ${caseType(option)} ${option.environment_display_name_ko ?? ""} ${option.reward_state ?? ""} ${option.care_state ?? ""}`.toLowerCase();
    const queryMatch = text.includes(query.toLowerCase());
    const decisionMatch = matchesCaseFilter(option, decisionFilter);
    return queryMatch && decisionMatch;
  });
  const ordered = [...filtered].sort((a, b) => {
    if (a.customer_id === selectedCustomerId) return -1;
    if (b.customer_id === selectedCustomerId) return 1;
    return personaIndex(a.customer_id) - personaIndex(b.customer_id);
  });
  // 회의 결정: 좌측은 사람 60명만 — 같은 사람의 3개 환경 시나리오는 중앙의
  // 환경 스위처로 비교한다. 대표 카드는 현재 선택된 환경의 시나리오.
  const currentEnvId = options.find((o) => o.customer_id === selectedCustomerId)?.environment_id;
  const personMap = new Map<string, DriverOption[]>();
  ordered.forEach((o) => {
    const key = personaName(o.customer_id);
    const arr = personMap.get(key) ?? [];
    arr.push(o);
    personMap.set(key, arr);
  });
  const personRows = [...personMap.values()].map(
    (arr) => arr.find((o) => o.environment_id === currentEnvId) ?? arr[0]
  );
  // 환경 3종 상태 카운트(팀 결정: '케어1/우대1/기본1' 식) — 필터와 무관하게 전체 기준.
  const fullGroupByName = new Map<string, DriverOption[]>();
  options.forEach((o) => {
    const key = personaName(o.customer_id);
    const arr = fullGroupByName.get(key) ?? [];
    arr.push(o);
    fullGroupByName.set(key, arr);
  });

  return (
    <aside className="case-rail" aria-label={t("가상 시니어 사례 목록")}>
      <div className="rail-heading">
        <p className="eyebrow">{t("가상 사례")}</p>
        <h2>{tf("{count}명 · 환경 3종 시나리오", { count: personMap.size })}</h2>
        <small>{t("표시 이름은 합성 시나리오를 위한 발표용 가명입니다")}</small>
      </div>
      <label className="search-box">
        <Search size={15} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("유형·환경·상태 검색")} />
      </label>
      <div className="filter-row">
        {decisionFilters.map((filter) => (
          <button key={filter.value} className={decisionFilter === filter.value ? "active" : ""} type="button" onClick={() => setDecisionFilter(filter.value)}>
            {filter.label}
          </button>
        ))}
      </div>
      <div className="case-list">
        {personRows.map((option) => {
          const changeTag = coreChangeTag(option.persona_type);
          return (
            <button
              key={option.customer_id}
              type="button"
              className={`case-row ${selectedCustomerId === option.customer_id ? "selected" : ""}`}
              onClick={() => onSelect(option.customer_id)}
              aria-pressed={selectedCustomerId === option.customer_id}
            >
              <span>
                <strong>{personaName(option.customer_id)}</strong>
                {personaBirthYear(option.customer_id) ? (
                  <span className="case-birth-year">Birth year {personaBirthYear(option.customer_id)}</span>
                ) : null}
                <small>
                  {changeTag}
                  {(() => {
                    const group = fullGroupByName.get(personaName(option.customer_id)) ?? [option];
                    const counts = new Map<string, number>();
                    group.forEach((o) => {
                      const st = caseDisplayState(o);
                      counts.set(st, (counts.get(st) ?? 0) + 1);
                    });
                    const order: Array<[string, string, string]> = [
                      ["Care Review", "care", t("케어")],
                      ["Hold", "hold", t("보류")],
                      ["Reward", "good", t("우대")],
                      ["Neutral", "base", t("기본")]
                    ];
                    return order
                      .filter(([state]) => (counts.get(state) ?? 0) > 0)
                      .map(([state, cls, label]) => (
                        <i key={state} className={`state-inline ${cls}`}>{label}{counts.get(state)}</i>
                      ));
                  })()}
                </small>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function DecisionSummaryCard({
  driver,
  zoneMap,
  rows,
  selectedMonth,
  driverState
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  rows: MonthlyEvidence[];
  selectedMonth: number;
  driverState: LoadState;
}) {
  if (!driver) {
    return <InspectorState title={t("사례 선택 대기")} detail={t("좌측 사례를 선택하면 우대·케어 검토 요약이 표시됩니다.")} />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const reward = decisionClass(driver.reward_state ?? comparison.annual_decision_signal);
  const selectedCare = selectedRow?.care_state ?? "None";
  const care = decisionClass(selectedCare);
  const reviewHeadline = selectedCare === "Care Review"
    ? t("이동 맥락과 위험행동의 동시변화 검토")
    : selectedCare === "Hold"
      ? t("근거 부족 · 판단 보류")
      : selectedCare === "Observation"
        ? t("개인 기준선 관찰 · 케어 평가 제외")
        : profile?.headline;
  const decisionReasons = profile
    ? [profile.headline, profile.outerPattern, profile.riskPattern]
    : driver.annual_score.annual_reason_codes.slice(0, 3).map((code) => t(reasonLabels[code] ?? code));

  return (
    <section className={`decision-summary-card ${driverState === "loading" ? "is-loading" : ""}`} aria-label={t("검토 제안 요약")}>
      <div className="summary-identity">
        <p className="eyebrow">{t("검토 제안 요약")}</p>
        <h2>{personaName(driver.customer_id)}</h2>
        {personaBirthYear(driver.customer_id) ? (
          <small className="summary-birth-year">Birth year {personaBirthYear(driver.customer_id)}</small>
        ) : null}
        <span>
          {driver.environment_display_name_ko ? t(driver.environment_display_name_ko) : personaResidence(driver)}
          {" · "}
          <em className="designed-type-tag" title={t("엔진 판정에는 사용되지 않는 설계 시나리오 라벨(실험 통제변수)")}>
            {tf("설계형 {type}", { type: personaTypeLabel(driver.persona_type) })}
          </em>
        </span>
      </div>

      <div className="summary-verdict">
        <span>{tf("선택 월 {month} 근거", { month: selectedRow?.service_month ?? tf("{n}월", { n: selectedMonth }) })}</span>
        <strong>{reviewHeadline ?? decisionReasons[0]}</strong>
        <p>{decisionReasons.slice(1, 3).filter(Boolean).join(" · ")}</p>
      </div>

      <div className="summary-decision-stack">
        {(() => {
          const collapsed = driver.reward_state === "Hold" || driver.care_state === "Hold"
            ? { label: t("판단 보류"), className: reward.className }
            : { label: tf("{score}점", { score: numberFormatter.format(driver.ab_comparison.annual_senior_safe_mileage_score) }), className: reward.className };
          return (
        <div className={`risk-score-block ${collapsed.className}`}>
          <span>{t("연간 평균 점수")}</span>
          <strong>{collapsed.label}</strong>
          <b>{tf("연간 환급률 {rate}% · 기존 마일리지 환급률 {existing}%", { rate: numberFormatter.format(driver.ab_comparison.proposed_discount_rate_pct), existing: numberFormatter.format(driver.ab_comparison.existing_discount_rate_pct) })}</b>
          <small className="axis-note">
            {(() => {
              const careMonthCount = rows.filter((row) => row.care_state === "Care Review").length;
              // reward.label은 번역된 값이라 영문 리터럴과 비교하면 항상 참이 된다 — 상태값으로 비교한다.
              if (careMonthCount > 0 && driver.reward_state !== "Reward") {
                return tf("동시변화로 케어 검토가 {n}개월 발생 — 사람이 검토하고 예방 지원으로 연결합니다", { n: careMonthCount });
              }
              return careMonthCount > 0
                ? tf("우대 요건 충족 · 케어 검토 {n}개월 발생 — 사람이 검토하고 예방 지원으로 연결합니다", { n: careMonthCount })
                : t("케어 검토 발생 없음 — 안정 주행 기반 환급");
            })()}
          </small>
        </div>
          );
        })()}

        <div className={`premium-delta-block ${care.className}`}>
          <span>{tf("선택 월 {month} Care 상태", { month: selectedRow?.service_month ?? tf("{n}월", { n: selectedMonth }) })}</span>
          <strong>{stateLabelKo(selectedCare === "None" ? "미충족" : selectedCare)}</strong>
          <small>{t("같은 달 이동 변화와 위험행동 변화가 함께 있을 때만")}</small>
        </div>

        <div className="summary-action">
          <span>{t("근거 상태")}</span>
          <strong>{zoneIsReady(driver.zone_status) ? t("생활권 근거 사용 가능") : t("근거 부족 · 불이익 없음")}</strong>
          <small>{selectedRow ? tf("데이터 커버리지 {pct}%", { pct: numberFormatter.format(selectedRow.data_coverage_pct ?? 0) }) : driver.evidence_status ?? "simulated"}</small>
        </div>
      </div>
    </section>
  );
}

function DecisionProcessFrame({
  driver,
  zoneMap,
  rows,
  selectedMonth,
  rules
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  rows: MonthlyEvidence[];
  selectedMonth: number;
  rules: ProductRules | null;
}) {
  if (!driver) {
    return <InspectorState title={t("판단 과정 대기")} detail={t("사례를 선택하면 월별 점수와 연간 환급 과정이 표시됩니다.")} />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const mobilityChange = selectedRow?.mobility_change_index_pct ?? 0;
  const riskyBehaviorChange = selectedRow?.risky_behavior_change_index_pct ?? 0;
  const careGate = selectedRow?.care_state === "Care Review";
  const zoneBasis = !zoneIsReady(driver.zone_status) || !zoneMap?.snapshot.living_zone.clusters.length
    ? t("생활권 없음 · 판단 보류")
    : zoneMap
      ? tf("중심권 500m · P90 {p90}m", { p90: Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("ko-KR") })
      : t("생활권 산출 중");
  const steps = [
    {
      title: t("기존 기준선"),
      value: tf("기존 마일리지 기준 {rate}%", { rate: comparison.existing_discount_rate_pct }),
      detail: t("연간 주행거리와 차종만 반영하는 비교 기준"),
      icon: Route
    },
    {
      title: t("생활권 생성"),
      value: zoneBasis,
      detail: t("직전 2개월의 반복 목적지와 이동 반경 반영 · 매달 갱신"),
      icon: MapPinned
    },
    {
      title: tf("{month} 변화", { month: selectedRow?.service_month ?? tf("{n}월", { n: selectedMonth }) }),
      value: tf("이동 변화 {mob}% · 위험행동 {risk}%", { mob: numberFormatter.format(mobilityChange), risk: numberFormatter.format(riskyBehaviorChange) }),
      detail: careGate ? t("같은 달 두 변화가 함께 임계치를 넘어 예방 케어 검토") : t("한 지표만으로는 케어를 제안하지 않음"),
      icon: Activity
    },
    {
      title: t("연간 점수와 환급"),
      value: tf("{score}점 · 환급률 {rate}%", { score: numberFormatter.format(comparison.annual_senior_safe_mileage_score), rate: numberFormatter.format(comparison.proposed_discount_rate_pct) }),
      detail: t("12개월의 월 통합점수를 평균해 연간 환급 제안에 반영"),
      icon: AlertTriangle
    }
  ];

  return (
    <section className="decision-process-frame" aria-label={t("상품 근거와 사람 검토 과정")}>
      <div className="decision-process-copy">
        <p className="eyebrow">{t("판단 과정")}</p>
        <h2>{t("월별 Care 신호와 연간 환급은 서로 다른 역할을 합니다")}</h2>
        <p>
          {t("매월 4개 지표로 점수와 상태를 확인합니다. 이동 맥락과 위험행동이 함께 달라지면 Care를 제안하지만, Care 자체가 환급률을 낮추지는 않습니다. 연간 환급은 12개월 점수를 기준으로 별도 계산합니다.")}
        </p>
      </div>
      <div className="process-rail">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <div className="process-step" key={step.title}>
              <span>{index + 1}</span>
              <Icon size={17} />
              <strong>{step.title}</strong>
              <b>{step.value}</b>
              <small>{step.detail}</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LivingZoneDecisionMap({
  driver,
  zoneMap,
  selectedMonth,
  zoneState
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  selectedMonth: number;
  zoneState: LoadState;
}) {
  if (!driver) return <InspectorState title={t("생활권 지도 대기")} detail={t("사례를 선택하면 반복 거점과 상품 구간이 표시됩니다.")} />;

  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;

  return (
    <section className="decision-map-panel" aria-label={t("생활권 판단 지도")}>
      <div className="decision-section-head">
        <div>
          <p className="eyebrow">{t("생활권 판단 지도")}</p>
          <h2>{zoneIsReady(driver.zone_status) ? t("생활권과 최근 변화 목적지") : t("생활권 미확정 · 반복 거점 근거 부족")}</h2>
        </div>
        {profile && zoneMap && zoneIsReady(driver.zone_status) ? (
          <div className="map-kpis">
            <span>{t("지도 갱신 · 매달 직전 2개월")}</span>
            <span>{tf("개인 P90 {p90}m", { p90: Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("ko-KR") })}</span>
            <span>{tf("생활권 밖 {pct} · 감점 0", { pct: percent(profile.outZoneRatio * 100) })}</span>
            <span>{tf("위험행동 {n}건", { n: profile.riskEvents })}</span>
          </div>
        ) : null}
      </div>

      <div className="map-stage">
        {zoneState === "loading" || !zoneMap || !profile ? (
          <p>{t("생활권 지도를 불러오는 중입니다.")}</p>
        ) : !zoneIsReady(driver.zone_status) ? (
          <div className="no-zone-state">
            <MapPinned size={24} />
            <strong>{t("반복 거점 근거가 충분하지 않습니다")}</strong>
            <p>{t("가짜 중심을 만들지 않고 생활권 없음으로 유지합니다. 우대와 케어는 판단 보류이며 불이익을 주지 않습니다.")}</p>
          </div>
        ) : (
          <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
        )}
      </div>

      {driver.mobility_profile && driver.mobility_profile.zones.length ? (
        <div className="agent-mobility">
          <div className="agent-mobility-head">
            <span className="eyebrow">{t("근거 기반 샘플 생활 동선")}</span>
            <span className="agent-badge">{t("합성 데이터 · 고정 규칙으로 분석")}</span>
          </div>
          {localeText(driver.mobility_profile.reasoning_ko, driver.mobility_profile.reasoning_en) ? (
            <p className="agent-reasoning">{localeText(driver.mobility_profile.reasoning_ko, driver.mobility_profile.reasoning_en)}</p>
          ) : null}
          <ul className="agent-zones">
            {driver.mobility_profile.zones.map((zone, index) => (
              <li key={index} className={`agent-zone role-${zone.role ?? "in_zone"}`}>
                <strong>{localeText(zone.label_ko, zone.label_en)}</strong>
                <span className="agent-zone-role">{zoneRoleLabel(zone.role)}</span>
              </li>
            ))}
          </ul>
          {driver.mobility_profile.change_month && localeText(driver.mobility_profile.change_trigger_ko, driver.mobility_profile.change_trigger_en) ? (
            <p className="agent-change">
              {tf("변화 계기 · 평가 {month}개월차", { month: driver.mobility_profile.change_month })}
              {" — "}
              {localeText(driver.mobility_profile.change_trigger_ko, driver.mobility_profile.change_trigger_en)}
            </p>
          ) : null}
          <p className="agent-mobility-note">{t("이 동선은 공개 통계와 문헌을 참고해 만든 합성 사례이며, 실제 위치·인물이 아닙니다. 화면에는 목적지 이름 대신 판정에 필요한 근거만 표시합니다.")}</p>
        </div>
      ) : null}

      <div className="map-legend-row">
        <span><i className="legend-home" />{t("반복 거점")}</span>
        <span><i className="legend-normal" />{t("중심권 500m")}</span>
        <span><i className="legend-out" />{t("완충권 · 개인 P90 반영")}</span>
        <span><i className="legend-risk" />{t("생활권 밖 · 위치만으로 감점 없음")}</span>
        <span><i className="legend-risk-ring" />{t("위험행동 발생(빨간 테두리)")}</span>
        <b>{zoneMap?.snapshot.service_month ?? tf("{n}월", { n: selectedMonth })} {t("선택 근거")}</b>
      </div>
      <div className="map-route-legend" aria-label={t("경로선 색 안내")}>
        <b>{t("경로선(도식) = 자택→목적지 연결이며 색은 선택 월의 해석입니다:")}</b>
        <span className="rl-stable"><i />{t("생활권 안")}</span>
        <span className="rl-candidate"><i />{t("반복 외부 후보")}</span>
        <span className="rl-safeout"><i />{t("생활권 밖 안정 · 중립")}</span>
        <span className="rl-risk"><i />{t("동시변화 검토")}</span>
      </div>
      <p className="map-formula-note">{t("생활권의 기준은 자택이 아니라 반복 방문이 만든 군집(거점)입니다. 중심권·완충권은 그 거점 중심에 적용되는 상품 인정 반경 — 완충권 = max(500m, min(개인 P90, 2km)). 자택은 지도의 원점(상대 위치 기준)일 뿐 판정 기준이 아닙니다.")}</p>
    </section>
  );
}

function AnalysisTabs({
  driver,
  zoneMap,
  rows,
  selectedMonth,
  loading,
  onSelectMonth,
  rules
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  rows: MonthlyEvidence[];
  selectedMonth: number;
  loading: boolean;
  onSelectMonth: (month: number) => void;
  rules: ProductRules | null;
}) {
  const [activeTab, setActiveTab] = useState("Overview");
  const selectedRow = rows.find((row) => row.month === selectedMonth) ?? rows[0];
  const profile = driver && zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const tabs = [
    { key: "Overview", label: t("요약") },
    { key: "Monthly Pattern", label: t("월별 패턴") },
    { key: "Risk Signals", label: t("위험 신호") },
    { key: "Premium Simulation", label: t("환급 시뮬레이션") },
    { key: "Algorithm Lab", label: t("알고리즘 실험실") }
  ];

  return (
    <section className={`analysis-tabs ${loading ? "is-loading" : ""}`} aria-label={t("하위 분석 탭")}>
      <div className="analysis-tabbar">
        {tabs.map((tab) => (
          <button key={tab.key} type="button" className={activeTab === tab.key ? "active" : ""} onClick={() => setActiveTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </div>

      <div className="analysis-content">
        {activeTab === "Overview" && driver && selectedRow ? (
          <div className="insight-grid">
            <InsightCard title={t("분류 근거")} value={profile?.headline ?? t("월별 근거 확인")} detail={profile?.summary ?? translateText(driver.care_context.message_focus)} />
            <InsightCard title={t("생활권 변화")} value={tf("이동 {mob} · 위험 {risk}", { mob: numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0), risk: numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0) })} detail={tf("{month}: 같은 달 동시조건 적용", { month: selectedRow.service_month })} />
            <InsightCard title={t("상품 제안")} value={tf("연간 {score}점 · 선택월 {care}", { score: numberFormatter.format(driver.ab_comparison.annual_senior_safe_mileage_score), care: stateLabelKo(selectedRow.care_state ?? "None") })} detail={t("월별 4개 지표를 통합한 연간 점수와 선택 월 케어 근거를 사람이 함께 검토합니다.")} />
          </div>
        ) : null}

        {activeTab === "Monthly Pattern" ? (
          <MonthlyPatternChart rows={rows} selectedMonth={selectedMonth} onSelectMonth={onSelectMonth} rules={rules} />
        ) : null}

        {activeTab === "Risk Signals" && driver && selectedRow ? (
          <div className="risk-signal-grid">
            {/* The four score meters + care-gate card render permanently in the
                monthly-evidence lane above — this tab keeps only its UNIQUE content:
                the score×weight formula substitution and the reason-code chips. */}
            <FormulaSubstitution driver={driver} selectedRow={selectedRow} rules={rules} />
            <div className="reason-chip-row">
              {[...driver.annual_score.annual_reason_codes, ...selectedRow.reason_codes].slice(0, 8).map((code) => (
                <span key={`${code}-${selectedMonth}`}>{t(reasonLabels[code] ?? code)}</span>
              ))}
            </div>
          </div>
        ) : null}

        {activeTab === "Premium Simulation" && driver ? (
          <PremiumSimulation driver={driver} />
        ) : null}

        {activeTab === "Algorithm Lab" ? (
          <AlgorithmLabPanel preferredDriverId={driver?.customer_id ?? null} />
        ) : null}

        {activeTab === "Report" && profile ? (
          <div className="report-tab-summary">
            <strong>{t("리포트 입력 근거")}</strong>
            <p>{profile.summary}</p>
            <span>{t("우측 사람 검토 패널에서 근거 초안을 생성합니다. 설명문은 최종 보험료·인수·케어 결정을 대신하지 않습니다.")}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

// 연간 우대는 '평균'이 아니라 '넘긴 달의 수'로 정해진다 — 화면에 그 규칙이
// 없어서 판정 근거가 안 보였다. 문턱선과 달성 카운터를 함께 보여준다.
function RewardMonthTracker({ rows, rules }: { rows: MonthlyEvidence[]; rules: ProductRules | null }) {
  const active = rules ?? referenceProductRules;
  const threshold = active.reward_score_threshold;
  const required = active.reward_required_months;
  const evaluation = rows.filter((row) => row.period_role !== "baseline");
  const scored = evaluation.map((row) => ({
    row,
    score: row.monthly_integrated_evidence_score ?? monthlyIntegratedEvidenceScore(row),
    hold: row.reward_state === "Hold" || row.care_state === "Hold"
  }));
  const met = scored.filter((s) => !s.hold && s.score >= threshold).length;
  const achieved = met >= required;
  return (
    <div className="reward-tracker">
      <div className="reward-tracker-head">
        <div>
          <strong>{tf("우대 충족 {met} / {total}개월", { met, total: evaluation.length })}</strong>
          <span>{tf("연간 우대는 통합점수 {threshold}점을 넘긴 달이 {required}개월 이상이어야 성립합니다 — 평균이 아니라 달 수입니다.", { threshold, required })}</span>
        </div>
        <em className={achieved ? "ok" : "short"}>
          {achieved ? t("연간 우대 성립") : tf("{n}개월 부족", { n: required - met })}
        </em>
      </div>
      <div className="reward-tracker-bars">
        {/* 트랙을 독립 요소로 두어 문턱선을 %로 직접 지정한다 — 라벨 높이 같은
            바깥 치수를 추정하지 않으므로 선과 막대가 항상 같은 좌표계에 있다. */}
        <div className="reward-track">
          {scored.map(({ row, score, hold }) => {
            const state = hold ? "hold" : score >= threshold ? "met" : "miss";
            return (
              <div key={row.service_month} className={`reward-month ${state}`} title={`${row.service_month} · ${numberFormatter.format(score)}`}>
                <b style={{ height: `${Math.max(2, Math.min(100, score))}%` }} />
              </div>
            );
          })}
          <u style={{ bottom: `${Math.min(100, threshold)}%` }}>{tf("{threshold}점", { threshold })}</u>
        </div>
        <div className="reward-labels">
          {scored.map(({ row }) => <span key={row.service_month}>{row.service_month.slice(-2)}</span>)}
        </div>
      </div>
    </div>
  );
}

function MonthlyPatternChart({ rows, selectedMonth, onSelectMonth, rules }: { rows: MonthlyEvidence[]; selectedMonth: number; onSelectMonth: (month: number) => void; rules: ProductRules | null }) {
  return (
    <div className="monthly-pattern-wrap">
    <RewardMonthTracker rows={rows} rules={rules} />
    <div className="monthly-pattern-chart">
      {rows.map((row) => {
        const meta = interpretationClass(row.dominant_interpretation);
        return (
          <button
            key={row.service_month}
            type="button"
            className={`month-bar ${meta.className} ${row.month === selectedMonth ? "selected" : ""}`}
            onClick={() => onSelectMonth(row.month)}
          >
            {/* Real service month (e.g. 25-11 / 26-01), not the 1..14 array index —
                "13월/14월" does not exist as a calendar month. */}
            <span>{row.service_month}</span>
            <i><b style={{ height: `${Math.max(12, Math.min(92, row.out_zone_pattern_change_risk))}%` }} /></i>
            <b>{numberFormatter.format(row.out_zone_pattern_change_risk)}</b>
          </button>
        );
      })}
    </div>
    </div>
  );
}

function FormulaSubstitution({ driver, selectedRow, rules }: { driver: DriverAnnualSummary; selectedRow: MonthlyEvidence; rules: ProductRules | null }) {
  // Use the ACTIVE sandbox weights so the score×weight breakdown and its total stay
  // consistent with the integrated score (which the adapter computes with live rules).
  const weights = normalizeProductWeights((rules ?? referenceProductRules).weights);
  const comparison = driver.ab_comparison;
  const integrated = selectedRow.monthly_integrated_evidence_score ?? monthlyIntegratedEvidenceScore(selectedRow);
  const formulaRows: Array<{ label: string; score: number | null; weight: number }> = [
    { label: t("주행거리"), score: selectedRow.mileage_score, weight: weights.mileage },
    { label: t("생활권 안 안전"), score: selectedRow.in_zone_safe_driving_score, weight: weights.in_zone_safe },
    { label: t("생활권 밖 안전"), score: selectedRow.out_zone_safe_driving_score, weight: weights.out_zone_safe },
    { label: t("패턴 안정성"), score: selectedRow.pattern_stability_score ?? Math.max(0, 100 - selectedRow.out_zone_pattern_change_risk), weight: weights.pattern_stability }
  ];
  return (
    <div className="profile-formula-card">
      <div className="blueprint-title">
        <BarChart3 size={17} />
        <strong>{t("이 프로필의 산식 적용")}</strong>
      </div>
      <div className="same-driver-compare">
        <div>
          <span>{t("기존 마일리지")}</span>
          <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
          {/* 어댑터의 한국어 데이터 문자열 대신 i18n 템플릿으로 렌더 — EN 화면 한글 잔존 방지 */}
          <small>{tf("기존 마일리지 기준 {rate}%", { rate: numberFormatter.format(comparison.existing_discount_rate_pct) })}</small>
        </div>
        <ArrowRight size={18} />
        <div>
          <span>{t("제안 산식")}</span>
          <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
          <small>{tf("통합점수 {score}점", { score: numberFormatter.format(integrated) })}</small>
        </div>
      </div>
      <div className="formula-substitution profile">
        {formulaRows.map((row) => (
          <div key={row.label}>
            <span>{row.label}</span>
            <strong>
              {row.score === null ? t("관측 없음") : `${numberFormatter.format(row.score)} × ${(row.weight / 100).toFixed(2)}`}
            </strong>
            <em>{row.score === null ? "—" : (row.score * row.weight / 100).toFixed(1)}</em>
          </div>
        ))}
        <div className="formula-total">
          <span>{t("통합점수")}</span>
          <strong>{tf("{score}점", { score: numberFormatter.format(integrated) })}</strong>
          <em>{stateLabelKo(selectedRow.reward_state ?? "Neutral")}</em>
        </div>
      </div>
      <p className="formula-substitution-note">{t("선택 월의 4개 지표를 합쳐 월 통합점수를 만들고, 12개월 점수를 모아 연간 환급을 제안합니다. 표시된 환급률은 합성 시나리오의 예시입니다.")}</p>
    </div>
  );
}

const DEMO_KRW_PER_USD = 1350; // 발표용 고정 환율 — 실제 계약 환율 아님
const DEMO_SGD_PER_USD = 1.28;

// 싱가포르 심사 기준 — SGD를 앞에 두고 원화를 괄호로 남긴다.
function krwWithSgd(amount: number | null | undefined) {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "—";
  const sgd = (amount / DEMO_KRW_PER_USD) * DEMO_SGD_PER_USD;
  return `$${sgd.toLocaleString("en-SG", { maximumFractionDigits: 0 })} (₩${Math.round(amount).toLocaleString("ko-KR")})`;
}

function PremiumSimulation({ driver }: { driver: DriverAnnualSummary }) {
  const comparison = driver.ab_comparison;
  const existingRate = comparison.existing_discount_rate_pct;
  const proposedRate = comparison.proposed_discount_rate_pct;
  const maxRate = Math.max(existingRate, proposedRate, 1);
  // 환급액의 차이와 방향을 즉시 읽히게 한다. 요율 엔진은 그대로 두고
  // 기준보험료 × 환급률로 이미 산출된 discount_amount만 표시한다.
  const rateDelta = proposedRate - existingRate;
  const refundDelta = (comparison.proposed_discount_amount_krw ?? 0) - (comparison.existing_discount_amount_krw ?? 0);
  return (
    <div className="premium-simulation">
      <p className="premium-basis">{t("연간 환급률과 환급액 기준의 비교입니다")}</p>
      <div>
        <span>{t("기존 마일리지 환급률")}</span>
        <strong>{percent(existingRate)}</strong>
        <i><b style={{ width: `${(existingRate / maxRate) * 100}%` }} /></i>
        <small>{tf("연간 환급액 {amount}", { amount: krwWithSgd(comparison.existing_discount_amount_krw) })}</small>
      </div>
      <div>
        <span>{t("MASIL 환급률 · 후보")}</span>
        <strong>{percent(proposedRate)}</strong>
        <i><b style={{ width: `${(proposedRate / maxRate) * 100}%` }} /></i>
        <small>{tf("연간 환급액 {amount}", { amount: krwWithSgd(comparison.proposed_discount_amount_krw) })}</small>
      </div>
      <p className={`premium-verdict ${rateDelta > 0.05 ? "gain" : rateDelta < -0.05 ? "reduce" : "same"}`}>
        {rateDelta > 0.05
          ? tf("고객 이득 — 기존 대비 연간 환급률 {pct}%p 확대, 환급액 {amount} 증가", { pct: Math.abs(rateDelta).toFixed(1), amount: krwWithSgd(Math.abs(refundDelta)) })
          : rateDelta < -0.05
            ? t("후보 민감도 · 최종 환급률 아님")
            : t("기존 기준과 동일한 수준입니다")}
      </p>
      <MatchedPairTable pair={driver.matched_pair ?? null} />
      <p>
        {tf("예시 연 보험료 {base} 가정의 합성 비교입니다. 환급액은 연 보험료 × 환급률이며, 싱가포르 달러는 발표용 고정 환율(US$1=₩{krw}, US$1=SGD {sgd})로 환산했습니다. 실제 계약보험료·해외 요율을 의미하지 않습니다.", { base: krwWithSgd(comparison.base_premium_krw), krw: DEMO_KRW_PER_USD.toLocaleString("ko-KR"), sgd: DEMO_SGD_PER_USD.toFixed(2) })}
      </p>
    </div>
  );
}

// '같은 조건, 다른 행동' — 같은 차종(1단계는 기존 요율까지 동일)에서 반대 판정을
// 받은 실제 시나리오와의 자동 대조. 상대가 없는 시나리오는 표를 그리지 않는다.
function MatchedPairTable({ pair, selfTag, otherTag }: { pair: MatchedPairComparison | null; selfTag?: string; otherTag?: string }) {
  if (!pair) return null;
  // 비교표는 환급 후 보험료가 아니라 기준보험료 × 환급률로 계산한 환급액을 표시한다.
  const sgd = (value: number) => `$${Math.round((value / DEMO_KRW_PER_USD) * DEMO_SGD_PER_USD).toLocaleString("en-SG")}`;
  const refundAmount = (netPremium: number) => Math.max(0, pair.base_premium_krw - netPremium);
  const name = (side: MatchedPairSide) => (getLocale() === "ko" ? side.display_label : side.display_label_en);
  const identical = pair.match_tier === "identical";
  const sides = [pair.self, pair.other];
  return (
    <div className="pair-compare">
      <div className="pair-compare-head">
        <strong>{t("같은 조건, 다른 행동")}</strong>
        <span>
          {identical
            ? t("비슷한 연간 주행거리 · 동일한 기존 특약 환급")
            : t("같은 차종 · 서로 다른 기존 특약 환급")}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th />
            <th>
              <strong className="pair-person-name">{name(pair.self)}</strong>
              {pair.self.birth_year ? <small className="pair-birth-year">{tf("출생연도 {year}", { year: pair.self.birth_year })}</small> : null}
              <em>{selfTag ?? t("현재 선택")}</em>
            </th>
            <th>
              <strong className="pair-person-name">{name(pair.other)}</strong>
              {pair.other.birth_year ? <small className="pair-birth-year">{tf("출생연도 {year}", { year: pair.other.birth_year })}</small> : null}
              <em>{otherTag ?? t("대조 사례")}</em>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr className="pair-section-row">
            <th colSpan={3}>{t("[현재] 같은 거리 (연간)")}</th>
          </tr>
          <tr>
            <th>{t("연간 주행거리")}</th>
            {sides.map((side) => <td key={side.driver_id}>{numberFormatter.format(side.annual_distance_km)} km</td>)}
          </tr>
          <tr className={identical ? "is-same" : undefined}>
            <th>{t("기존 Pay-As-You-Drive 특약")}</th>
            {sides.map((side) => (
              <td key={side.driver_id}>{percent(side.existing_rate_pct)} ({sgd(refundAmount(side.existing_premium_krw))})</td>
            ))}
          </tr>
          <tr className="pair-explainer-row">
            <td colSpan={3}>{t("같은 거리는 같은 환급을 받습니다")}</td>
          </tr>
          <tr className="pair-section-row risk">
            <th colSpan={3}>{t("[MASIL] 다른 위험 (연간)")}</th>
          </tr>
          <tr>
            <th>{t("생활권 밖 주행 비중")}</th>
            {sides.map((side) => <td key={side.driver_id}>{percent(side.outer_share_pct)}</td>)}
          </tr>
          <tr>
            <th>{t("위험 이벤트 · 12개월 평가")}</th>
            {sides.map((side) => (
              <td key={side.driver_id}>{side.risk_event_count === null ? "—" : numberFormatter.format(side.risk_event_count)}</td>
            ))}
          </tr>
          <tr className="is-pivot">
            <th>{t("생활권 밖 안전점수")}</th>
            {sides.map((side) => (
              <td key={side.driver_id}>{side.out_zone_safe_score === null ? t("관측 없음") : numberFormatter.format(side.out_zone_safe_score)}</td>
            ))}
          </tr>
          <tr>
            <th>{t("연간 평균 점수")}</th>
            {sides.map((side) => (
              <td key={side.driver_id}>{numberFormatter.format(side.integrated_score)}</td>
            ))}
          </tr>
          <tr className="is-strong">
            <th>{t("MASIL 제안 (환급률)")}</th>
            {sides.map((side) => (
              <td key={side.driver_id}>{percent(side.proposed_rate_pct)} ({sgd(refundAmount(side.proposed_premium_krw))})</td>
            ))}
          </tr>
        </tbody>
      </table>
      <p>{t("180개 합성 시나리오에서 주행거리가 비슷한 두 사례를 비교했습니다. 기존 특약은 같은 환급을 주지만, MASIL은 4개 지표로 드러난 위험 차이를 연간 환급 제안에 반영합니다.")}</p>
    </div>
  );
}

function DecisionPanel({
  driver,
  zoneMap,
  rows,
  selectedMonth,
  loading,
  rules
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  rows: MonthlyEvidence[];
  selectedMonth: number;
  loading: boolean;
  rules: ProductRules | null;
}) {
  const [careReportOpen, setCareReportOpen] = useState(false);

  useEffect(() => {
    setCareReportOpen(false);
  }, [driver?.customer_id, selectedMonth]);

  if (!driver) return <aside className="decision-panel"><InspectorState title={t("사람 검토 패널")} detail={t("사례를 선택하면 근거와 검토 작업이 표시됩니다.")} /></aside>;

  const comparison = driver.ab_comparison;
  const refundRateDifference = comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct;
  const decision = decisionClass(driver.reward_state ?? comparison.annual_decision_signal);
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const selectedCare = selectedRow?.care_state ?? "None";
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const reviewHeadline = selectedCare === "Care Review"
    ? t("이동 맥락과 위험행동의 동시변화 검토")
    : selectedCare === "Hold"
      ? t("근거 부족 · 판단 보류")
      : selectedCare === "Observation"
        ? t("개인 기준선 관찰 · 케어 평가 제외")
        : profile?.headline;
  const xaiReasons = topXaiReasons(driver, zoneMap, selectedMonth);
  return (
    <aside className={`decision-panel ${loading ? "is-loading" : ""} ${careReportOpen ? "has-report" : ""}`} aria-label={t("사람 검토 패널")}>
      <div className="decision-panel-head">
        <p className="eyebrow">{t("사람 검토")}</p>
        <h2>{t("검토 제안")}</h2>
        <em
          className={`decision ${driver.care_state === "Care Review" ? "care" : decision.className}`}
          title={t("연간 평균 점수")}
        >
          {driver.reward_state === "Hold" || driver.care_state === "Hold"
            ? t("연간 판단 보류")
            : tf("연간 {score}점", { score: numberFormatter.format(comparison.annual_senior_safe_mileage_score) })}
        </em>
      </div>

      <div className="decision-money-stack">
        <div>
          <span>{t("기존 마일리지 환급률")}</span>
          <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
          <small>{tf("연간 환급액 {amount}", { amount: krwWithSgd(comparison.existing_discount_amount_krw) })}</small>
        </div>
        <div>
          <span>{t("MASIL 환급률 · 후보")}</span>
          <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
          <small>{tf("4개 지표 → 통합점수 {score}점 · 환급액 {amount}", { score: numberFormatter.format(comparison.annual_senior_safe_mileage_score), amount: krwWithSgd(comparison.proposed_discount_amount_krw) })}</small>
        </div>
        <div className="refund-rate-difference">
          <span>{t("제안 − 기존 환급률 차이")}</span>
          <strong>{refundRateDifference > 0 ? "+" : ""}{numberFormatter.format(refundRateDifference)}%p</strong>
          <small>
            {refundRateDifference > 0
              ? tf("기존 환급률 대비 {pct}%p 높음", { pct: numberFormatter.format(Math.abs(refundRateDifference)) })
              : refundRateDifference < 0
                ? tf("기존 환급률 대비 {pct}%p 낮음", { pct: numberFormatter.format(Math.abs(refundRateDifference)) })
                : t("기존 환급률과 동일")}
          </small>
        </div>
      </div>

      <div className="decision-reason-box">
        <span>{t("검토 근거")}</span>
        <strong>{translateText(reviewHeadline ?? driver.care_context.product_role)}</strong>
        <p>{translateText(profile?.summary ?? driver.care_context.message_focus)}</p>
      </div>

      <div className="xai-inspector" aria-label={t("사유 코드 근거")}>
        <span>{tf("지표별 영향 분해 · {month}", { month: zoneMap?.snapshot.service_month ?? tf("{n}월", { n: selectedMonth }) })}</span>
        {xaiReasons.map((reason) => (
          <div key={reason.label} className={`xai-reason ${reason.tone}`}>
            <strong>{reason.label}</strong>
            <i><b style={{ width: `${reason.width}%` }} /></i>
            <em>{reason.detail}</em>
          </div>
        ))}
      </div>

      {/* 담당자 메모·보류/추가근거 결정은 케어 리포트 모달의 06 검수·승인으로 통합
          — 같은 판단 UI가 두 곳에 있던 중복을 제거한다. */}
      <button className="report-button" type="button" onClick={() => setCareReportOpen(true)} disabled={!selectedRow}>
        <FileText size={15} />
        {tf("{month} 케어 리포트 검수", { month: zoneMap?.snapshot.service_month ?? tf("{n}월", { n: selectedMonth }) })}
      </button>
      <p className="report-progress">{t("직원 검수 → 승인 → 고객 앱 전달의 연속 흐름을 확장 화면으로 엽니다.")}</p>

      {careReportOpen && driver && selectedRow && rules ? (
        <CareReportModal
          driver={driver}
          rows={rows}
          selectedRow={selectedRow}
          rules={rules}
          driverNameKo={personaName(driver.customer_id)}
          onClose={() => setCareReportOpen(false)}
        />
      ) : null}
    </aside>
  );
}


function renderInlineMarkdown(text: string) {
  const normalized = translateText(text);
  return normalized.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function topXaiReasons(driver: DriverAnnualSummary, zoneMap: ZoneMapResponse | null, selectedMonth: number) {
  const monthly = zoneMap?.snapshot.scores;
  const risk = monthly?.out_zone_pattern_change_risk ?? driver.annual_score.annual_out_zone_pattern_change_risk;
  const inZone = monthly ? monthly.in_zone_safe_driving_score : driver.annual_score.annual_in_zone_safe_driving_score;
  const outZone = monthly ? monthly.out_zone_safe_driving_score : driver.annual_score.annual_out_zone_safe_driving_score;
  const mileage = monthly?.mileage_score ?? driver.annual_score.annual_mileage_score;
  const tripCount = zoneMap?.snapshot.basis_window.scored_trip_count ?? driver.annual_score.annual_trip_count;
  const meterWidth = (value: number | null) => value === null || !Number.isFinite(value) ? 0 : Math.max(8, Math.min(100, value));
  const scoreDetail = (value: number | null) => value === null || !Number.isFinite(value) ? t("N/A · 관측 없음") : tf("{score}점", { score: numberFormatter.format(value) });
  return [
    {
      // A CHANGE index, not a score: higher = more change = more attention. Rendered
      // in a distinct "change" tone so a long bar doesn't read as a good safety score.
      label: t("이동 맥락 변화 (높을수록 변화 큼)"),
      width: meterWidth(risk),
      detail: scoreDetail(risk),
      tone: "change"
    },
    {
      label: t("선택 월 생활권 안 안전점수"),
      width: meterWidth(inZone),
      detail: scoreDetail(inZone),
      tone: "score"
    },
    {
      label: t("선택 월 생활권 밖 안전점수"),
      width: meterWidth(outZone),
      detail: scoreDetail(outZone),
      tone: "score"
    },
    {
      label: t("선택 월 주행거리 점수"),
      width: meterWidth(mileage),
      detail: tf("{detail} · {count}건", { detail: scoreDetail(mileage), count: tripCount }),
      tone: "score"
    }
  ];
}

function InsightCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="insight-card">
      <span>{translateText(title)}</span>
      <strong>{translateText(value)}</strong>
      <p>{translateText(detail)}</p>
    </div>
  );
}

function ProductBlueprintPanel({ directory }: { directory: PersonaDirectoryResponse }) {
  const weights = normalizeProductWeights(directory.product_rules?.weights ?? referenceProductRules.weights);
  const adopted = normalizeProductWeights(referenceProductRules.weights);
  // Guard against misreading a sandbox experiment as the adopted formula: the
  // card mirrors live slider values, so flag any deviation from 30/30/20/20.
  const isExperiment =
    weights.mileage !== adopted.mileage ||
    weights.in_zone_safe !== adopted.in_zone_safe ||
    weights.out_zone_safe !== adopted.out_zone_safe ||
    weights.pattern_stability !== adopted.pattern_stability;
  return (
    <section className="panel blueprint-panel" aria-label={t("데이터 생성 방식과 최종 산식")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("AI 활용과 상품 검증")}</p>
          <h2>{t("AI는 보험료를 결정하지 않습니다. 합성 데이터와 설명을 보조하고, 판정과 환급은 고정 규칙으로 계산합니다.")}</h2>
        </div>
        <span className="count-badge">{t("4개 지표 가중치 비교")}</span>
      </div>

      <div className="ai-proof-row" aria-label={t("AI 활용 위치")}>
        <div>
          <span>AI 1</span>
          <strong>{t("합성 주행 데이터 생성")}</strong>
          <p>{t("표본 운전자 프로필과 공개 기준을 바탕으로 14개월 합성 주행 로그를 만듭니다.")}</p>
        </div>
        <div>
          <span>AI 2</span>
          <strong>{t("고정 규칙 계산 · 민감도 검증")}</strong>
          <p>{t("DBSCAN·P90과 사람이 정한 가중치로 점수를 계산합니다. 30/30/20/20은 969개 조합 민감도 분석에서 확인한 안정적인 초기 후보입니다.")}</p>
        </div>
        <div>
          <span>AI 3</span>
          <strong>{t("설명가능 AI(XAI) + 직원용 리포트")}</strong>
          <p>{t("4개 지표와 Reason Code를 LLM이 직원이 읽기 쉬운 설명으로 바꿉니다. 직원이 월별 결과와 연간 환급을 최종 승인합니다.")}</p>
        </div>
      </div>

      <div className="blueprint-flow" aria-label={t("산식 설계 흐름")}>
        <div className="flow-step">
          <span>1</span>
          <strong>{t("시니어 주행 시나리오 생성")}</strong>
          <p>{tf("6개 운전자 유형 × 10명 = 인물 60명을 도심·교외·광역 3개 이동환경에서 각각 시뮬레이션 — 총 {count}개 사례에 자택, 마트, 병원, 자녀 집, 경로당 같은 합성 목적지와 외출 성향을 부여합니다.", { count: directory.summary.customer_count })}</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>2</span>
          <strong>{t("직전 2개월 기록으로 생활권 형성·갱신")}</strong>
          <p>{t("DBSCAN은 반복 거점을 찾고, 각 거점에 중심권 500m와 중심–방문점 P90 완충권을 별도로 적용합니다.")}</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>3</span>
          <strong>{t("월별 3단계와 연간 환급")}</strong>
          <p>{t("매월 4개 지표로 Favorable·Standard·Care를 계산하고, 12개월 점수로 연간 환급을 제안합니다. Care 자체가 환급을 자동으로 줄이지 않습니다.")}</p>
        </div>
      </div>

      <div className="formula-workbench">
        <div className="formula-decision-card">
          <div className="blueprint-title">
            <BarChart3 size={17} />
            <strong>{t("최종 통합점수 산식")}</strong>
            {isExperiment ? <em className="formula-experiment-badge">{t("실험 중 — 채택값 30/30/20/20 아님")}</em> : null}
          </div>
          <p className="formula-lead">
            {t("한국 마일리지 거리 기준은 참조값으로 유지하되, 우대 산식과 케어 동시조건을 분리해 처벌 없는 예방지원 구조를 검증합니다.")}
          </p>
          <div className="weight-layout" aria-label={t("최종 산식 가중치")}>
            <div className="weight-block mileage">
              <span>{t("주행거리")}</span>
              <strong>{weights.mileage}%</strong>
              <small>{t("저주행 우대 기준 유지")}</small>
            </div>
            <div className="weight-block in-zone">
              <span>{t("생활권 안 안전")}</span>
              <strong>{weights.in_zone_safe}%</strong>
              <small>{t("익숙한 반경 안 안정운전")}</small>
            </div>
            <div className="weight-block out-zone">
              <span>{t("생활권 밖 안전")}</span>
              <strong>{weights.out_zone_safe}%</strong>
              <small>{t("외부 주행 자체를 불리하게 보지 않음")}</small>
            </div>
            <div className="weight-block risk">
              <span>{t("패턴 안정성")}</span>
              <strong>{weights.pattern_stability}%</strong>
              <small>{t("개인 기준선 대비 변화 맥락")}</small>
            </div>
          </div>
          <div className="formula-box simplified">
            <span>{t("계산 방식")}</span>
            <strong>{tf("우대 후보점수 = 주행거리 {mileage}% + 생활권 안 안전 {inZone}% + 생활권 밖 안전 {outZone}% + 패턴 안정성 {stability}%", { mileage: weights.mileage, inZone: weights.in_zone_safe, outZone: weights.out_zone_safe, stability: weights.pattern_stability })}</strong>
          </div>
        </div>

        <div className="formula-evidence-card">
          <div className="blueprint-title">
            <ShieldCheck size={17} />
            <strong>{t("왜 30/30/20/20을 선택했나")}</strong>
          </div>
          <div className="evidence-checklist">
            <div>
              <span>{t("비용 검증")}</span>
              <strong>{t("평균 환급률 변화가 설명 가능한 범위인지 확인")}</strong>
              <p>{t("두 산식을 각각 계산해 기존 환급 구조와 비교하고, 변화폭이 과도하지 않은지 확인합니다.")}</p>
            </div>
            <div>
              <span>{t("공정성 조건")}</span>
              <strong>{t("생활권 밖이라는 이유만으로 감점하지 않음")}</strong>
              <p>{t("반복 외부 목적지와 안정 주행은 기본 또는 우대 판단이 가능해야 합니다.")}</p>
            </div>
            <div>
              <span>{t("케어 조건")}</span>
              <strong>{t("같은 달의 이동 변화와 위험행동 변화 동시 충족")}</strong>
              <p>{t("한 지표만 변하거나 데이터가 부족하면 자동 케어가 아니라 기본 또는 판단 보류로 남깁니다.")}</p>
            </div>
          </div>
          <CandidateSearchChart />
        </div>
      </div>
    </section>
  );
}

function CandidateSearchChart() {
  return (
    <div className="candidate-search formula-choice-board">
      <div className="candidate-chart-head">
        <span>{t("산식 후보 비교 결과")}</span>
        <strong>{t("최종 비율은 위 산식에 반영하고, 이 영역은 다른 후보를 왜 제외했는지 설명합니다.")}</strong>
      </div>

      <div className="candidate-comparison-grid" aria-label={t("후보 산식 비교")}>
        <div className="rejected">
          <span>{t("거리 중심안")}</span>
          <strong>{t("탈락")}</strong>
          <p>{t("기존 마일리지와 차이가 작아 저주행 위험변화군을 설명하기 어렵습니다.")}</p>
        </div>
        <div className="selected">
          <span>{t("균형안")}</span>
          <strong>{t("선택")}</strong>
          <p>{t("저주행 우대는 남기고, 생활권 안/밖 안정성과 위험변화를 함께 설명합니다.")}</p>
        </div>
        <div className="deferred">
          <span>{t("위험변화 과대안")}</span>
          <strong>{t("보류")}</strong>
          <p>{t("반복 외부 목적지까지 과도하게 불리하게 볼 수 있어 보류했습니다.")}</p>
        </div>
      </div>

      <div className="selection-criteria">
        <span>{t("선택 기준")}</span>
        <strong>{t("평균 환급률 변화가 과도하지 않음 · 위험변화군 분리 가능 · 외부 안정주행 오분류 방지")}</strong>
      </div>
    </div>
  );
}

function MonthlyEvidenceLane({
  rows,
  selectedMonth,
  loading,
  onSelectMonth,
  rules
}: {
  rows: MonthlyEvidence[];
  selectedMonth: number;
  loading: boolean;
  onSelectMonth: (month: number) => void;
  rules: ProductRules | null;
}) {
  const weights = normalizeProductWeights(rules?.weights ?? referenceProductRules.weights);
  const selectedRow = rows.find((row) => row.month === selectedMonth) ?? rows[0];
  const selectedMeta = selectedRow ? interpretationClass(selectedRow.dominant_interpretation) : null;
  const monthlyIntegratedScore = selectedRow
    ? selectedRow.monthly_integrated_evidence_score ?? monthlyIntegratedEvidenceScore(selectedRow)
    : 0;
  const monthlyIntegratedLabel = !selectedRow
    ? "N/A"
    : selectedRow.period_role === "baseline"
      ? tf("{score}점 · 기준선 관찰", { score: numberFormatter.format(monthlyIntegratedScore) })
      : selectedRow.basis_status === "evaluation_ready"
        ? tf("{score}점", { score: numberFormatter.format(monthlyIntegratedScore) })
        : t("N/A · 판단 보류");

  return (
    <section className={`panel evidence-lane ${loading ? "is-loading" : ""}`} aria-label={t("월별 4지표 근거")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("월별 근거")}</p>
          <h2>{t("2개월 기준선과 12개월 평가 근거를 같은 흐름에서 확인합니다")}</h2>
        </div>
        <div className="legend">
          {Object.entries(interpretationMeta).map(([key, meta]) => (
            <span key={key} className={meta.className}>{t(meta.label)}</span>
          ))}
        </div>
      </div>

      {selectedRow && selectedMeta ? (
        <div className="month-focus-panel">
          <div className="month-focus-copy">
            <span>{t("선택 월")}</span>
            <strong>{selectedRow.service_month}</strong>
          </div>
          <div className="score-meter-grid">
            <ScoreMeter label={t("주행거리 점수")} value={selectedRow.mileage_score} />
            <ScoreMeter label={t("생활권 안 안전점수")} value={selectedRow.in_zone_safe_driving_score} />
            <ScoreMeter label={t("생활권 밖 안전점수")} value={selectedRow.out_zone_safe_driving_score} />
            <ScoreMeter label={t("패턴 안정성")} value={selectedRow.pattern_stability_score ?? Math.max(0, 100 - selectedRow.out_zone_pattern_change_risk)} />
          </div>
          <div className="monthly-integrated-formula" aria-label={t("월별 통합 근거점수 산식")}>
            <div className="monthly-integrated-score">
              <span>{t("월별 통합 근거점수")}</span>
              <strong>{monthlyIntegratedLabel}</strong>
            </div>
            <p>{tf("주행거리 {mileage}% + 생활권 안 안전 {inZone}% + 생활권 밖 안전 {outZone}% + 패턴 안정성 {stability}%", { mileage: weights.mileage, inZone: weights.in_zone_safe, outZone: weights.out_zone_safe, stability: weights.pattern_stability })}</p>
            <div className={`monthly-care-gate ${selectedRow.care_state === "Care Review" ? "active" : ""}`}>
              <b>{t("케어 동시조건")}</b>
              <span>{tf("이동 {mob} · 위험행동 {risk}", { mob: numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0), risk: numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0) })}</span>
              <em>{selectedRow.period_role === "baseline" ? t("기준선") : selectedRow.care_state === "Care Review" ? t("사람 검토 제안") : t("미충족")}</em>
            </div>
          </div>
        </div>
      ) : null}

      <p className="month-board-hint">{t("케어 검토가 발생한 달이 자동 선택됩니다 — 다른 달을 누르면 위 요약·지도·근거가 그 달 기준으로 바뀝니다.")}</p>
      <div className="month-board">
        {rows.map((row) => {
          const meta = interpretationClass(row.dominant_interpretation);
          return (
            <button
              key={row.service_month}
              type="button"
              className={`month-card ${meta.className} ${row.period_role === "baseline" ? "baseline" : "evaluation"} ${selectedMonth === row.month ? "selected" : ""}`}
              onClick={() => onSelectMonth(row.month)}
            >
              <span>{row.service_month.slice(2)} · {row.period_role === "baseline" ? t("기준선") : t("평가")}</span>
              <strong>{numberFormatter.format(row.monthly_total_distance_km)}km</strong>
              <small>{basisLabel(row.basis_status)}</small>
              <em>{row.care_state === "Care Review" ? t("케어 검토") : stateLabelKo(row.reward_state ?? "Observation")}</em>
              {row.period_role === "baseline" ? <u className="baseline-tag">{t("평가 제외")}</u> : null}
              <i style={{ width: `${Math.min(100, row.mobility_change_index_pct ?? row.out_zone_pattern_change_risk)}%` }} />
            </button>
          );
        })}
      </div>
    </section>
  );
}

// Deterministic synthetic visit scatter for the schematic map (NO real
// coordinates — reconstructed from a seed so it renders as a plausible cloud of
// month-long visits around each destination, not a single bare dot).
function GeoLivingZoneCanvas({ driver, snapshot, profile }: { driver: DriverAnnualSummary; snapshot: ZoneSnapshot; profile: DerivedProfile }) {
  if (!snapshot.living_zone.clusters.length) {
    return (
      <div className="no-zone-state">
        <MapPinned size={24} />
        <strong>{t("반복 거점 근거가 충분하지 않습니다")}</strong>
        <p>{t("가짜 중심을 만들지 않고 생활권 없음으로 유지합니다. 우대와 케어는 판단 보류이며 불이익을 주지 않습니다.")}</p>
      </div>
    );
  }
  const groups = Object.values(groupTrips(snapshot.trip_interpretations)).sort((a, b) => b.count - a.count);
  const home = destinationForType(driver, "home");
  const profileZones = driver.mobility_profile?.zones ?? [];
  const secondaryZoneQueue = profileZones.filter((zone) => zone.role === "secondary");

  // ---- Zone-driven map (Option C) ----------------------------------------
  // The engine generates visits to EVERY profile zone (each with its own AI
  // bearing), but the raw event vocabulary has only 3 labels, so a person's 2nd
  // and 3rd in-zone destinations collapse into one "Routine Hub B" group. To show
  // driving in ALL its real directions, map nodes are the PROFILE ZONES active in
  // the selected month; each label-group's stats are apportioned across its zones
  // by the profile visit_share (the same weights that generated the events).
  const monthIdx = (() => {
    const [yy, mm] = snapshot.service_month.split("-").map(Number);
    return Number.isFinite(yy) && Number.isFinite(mm) ? (yy - 2025) * 12 + (mm - 11) + 1 : 14;
  })();
  const activeZones = profileZones.filter((zone) => {
    const from = zone.active_from_month ?? 1;
    const to = zone.active_to_month ?? 14;
    return from <= monthIdx && monthIdx <= to;
  });
  const groupByKey = new Map(groups.map((group) => [group.key, group]));
  const groupKeyForZone = (zone: (typeof profileZones)[number], inZoneIndex: number) =>
    zone.role === "in_zone" ? (inZoneIndex === 0 ? "routine_hub_a" : "routine_hub_b") : "outer_context";

  type MapDest = { group: TripGroup; destination: { living_zone_role: string }; zone: (typeof profileZones)[number] | null };
  let mapDestinations: MapDest[] = [];
  if (activeZones.length) {
    // visit_share per group key, for apportioning that group's stats
    let seenInZone = 0;
    const zoneMetas = activeZones.map((zone) => {
      const key = groupKeyForZone(zone, zone.role === "in_zone" ? seenInZone++ : 0);
      return { zone, key, share: Math.max(0.05, zone.visit_share ?? 0.3) };
    });
    const shareTotals = new Map<string, number>();
    zoneMetas.forEach((m) => shareTotals.set(m.key, (shareTotals.get(m.key) ?? 0) + m.share));
    mapDestinations = zoneMetas
      .filter((m) => groupByKey.has(m.key))
      .map((m, order) => {
        const parent = groupByKey.get(m.key)!;
        const frac = m.share / (shareTotals.get(m.key) ?? 1);
        return {
          zone: m.zone,
          destination: { living_zone_role: m.zone.role === "in_zone" ? "in" : "outer" },
          group: {
            ...parent,
            key: `${m.key}-z${order}`,
            label: localeText(m.zone.label_ko, m.zone.label_en) ?? parent.label,
            count: Math.max(1, Math.round(parent.count * frac)),
            distanceKm: parent.distanceKm * frac,
            riskEvents: Math.round(parent.riskEvents * frac),
            nightTrips: Math.round(parent.nightTrips * frac)
          }
        };
      });
  }
  if (!mapDestinations.length) {
    // Fallback (no profile): legacy label-group nodes.
    mapDestinations = groups
      .map((group) => ({ group, legacy: destinationForType(driver, group.key) }))
      .filter((item) => Boolean(item.legacy) && item.group.key !== "home")
      .map((item) => ({
        group: item.group,
        zone: null,
        destination: { living_zone_role: item.legacy?.living_zone_role ?? "in" }
      }));
  }
  const visibleDestinations = mapDestinations.slice(0, 6);
  const agentDestZones = visibleDestinations.map((item) => item.zone);
  const agentDestLabels = agentDestZones.map((zone) => (zone ? localeText(zone.label_ko, zone.label_en) : null));

  // Home-centred radial schematic (not a real map — coordinates are never
  // exposed). The residence sits at the centre with its Core (500m) and Buffer
  // (personal P90) rings; destinations fan out around it: in-zone stops inside
  // the buffer, out-of-zone stops beyond it. This reads as one legible living
  // zone instead of a projected "tadpole".
  const mapWidth = 900;
  const mapHeight = 520;
  const center = { x: mapWidth * 0.3, y: mapHeight * 0.52 };
  const radialP90M = snapshot.living_zone.clusters[0]?.p90_radius_m ?? snapshot.living_zone.buffer.departure_p90_threshold_m;
  const productBufferM = Math.max(500, Math.min(2000, radialP90M));
  // 환경별 차이가 화면에 보이게: 완충권 px는 실제 P90에 비례(도심 ~500m는 작게,
  // 광역 ~1500m+는 크게), 중심권 500m는 완충권 대비 '실제 비율'로 그린다 —
  // 도심은 중심권≈완충권(빽빽), 광역은 큰 완충권 속 작은 중심권.
  const bufferRadius = Math.max(64, Math.min(215, 55 + productBufferM * 0.11));
  const coreRadius = Math.max(30, Math.min(bufferRadius - 4, bufferRadius * (500 / productBufferM)));

  // ---- 실측 방문점 투영 -----------------------------------------------------
  // 모든 점은 엔진이 생성한 실제 방문 이벤트의 자택 기준 상대변위(m)다. 완충권
  // 안은 선형 축척, 밖은 √압축(캔버스에 담기 위한 선언된 압축)으로 투영한다.
  const selectedVisits = snapshot.visit_scatter?.selected ?? [];
  const baselineGhost = snapshot.visit_scatter?.baseline ?? [];
  const projectVisit = (dxEastM: number, dyNorthM: number, index = 0) => {
    const dist = Math.hypot(dxEastM, dyNorthM);
    const px = dist <= productBufferM
      ? (dist / productBufferM) * bufferRadius
      : bufferRadius + Math.min(190, Math.sqrt(dist - productBufferM) * 2.2);
    const ux = dist > 0 ? dxEastM / dist : 0;
    const uy = dist > 0 ? dyNorthM / dist : 0;
    // 10m 반올림으로 겹치는 실측점을 골든앵글 나선으로 '표시만' 펼친다(위치값은 실측).
    const spiralR = 3 + (index % 14) * 1.7;
    const spiralA = index * 2.39996;
    return {
      x: Math.max(30, Math.min(mapWidth - 30, center.x + ux * px + Math.cos(spiralA) * spiralR)),
      y: Math.max(56, Math.min(mapHeight - 56, center.y - uy * px + Math.sin(spiralA) * spiralR))
    };
  };

  const destCount = Math.max(1, visibleDestinations.length);
  const arcStart = -Math.PI * 0.82;
  const arcSpan = Math.PI * 1.42;
  // Per-driver deterministic jitter so even same-band zones never overlap the
  // same pixel across drivers (seeded by customer id — stable across renders).
  const driverSeed = Array.from(driver.customer_id).reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) % 9973, 7);
  const bandRadius = (band: string | undefined, outer: boolean, index: number): number => {
    switch (band) {
      case "near": return bufferRadius * (0.5 + ((driverSeed + index * 37) % 16) / 100);
      case "mid_in": return bufferRadius * (0.76 + ((driverSeed + index * 53) % 14) / 100);
      case "secondary": return bufferRadius + 190 + ((driverSeed + index * 29) % 60);
      case "outer": return bufferRadius + 150 + ((driverSeed + index * 41) % 90);
      default: return outer ? bufferRadius + 160 + (index % 3) * 40 : bufferRadius * 0.62;
    }
  };
  const routePath = (point: { x: number; y: number }) => {
    const dx = point.x - center.x;
    const dy = point.y - center.y;
    const reach = Math.hypot(dx, dy);
    // 먼 목적지일수록 크게 휘어 원본처럼 캔버스를 가로질러 흐른다.
    const bend = Math.min(0.3, 0.1 + reach / 2200);
    const midX = center.x + dx * 0.5 - dy * bend;
    const midY = center.y + dy * 0.5 + dx * bend;
    return `M${center.x} ${center.y} Q${midX} ${midY}, ${point.x} ${point.y}`;
  };
  const rawViews = visibleDestinations.map((item, index) => {
    const outer = item.destination.living_zone_role === "outer";
    const zone = agentDestZones[index];
    // Geometry from the AI profile when available: bearing_deg (0°=north,
    // clockwise) + distance band. Fallback: legacy index arc.
    const fallbackAngle = destCount === 1 ? -Math.PI * 0.3 : arcStart + (index / (destCount - 1)) * arcSpan;
    const angle = zone && Number.isFinite(zone.bearing_deg)
      ? ((Number(zone.bearing_deg) - 90) * Math.PI) / 180
      : fallbackAngle;
    return { item, outer, angle, dist: bandRadius(zone?.distance_band, outer, index) };
  });
  // 방위가 몰리면 라벨이 겹치므로 최소 0.42rad씩 벌린다(실측 방위의 순서는 유지).
  const sortedByAngle = [...rawViews].sort((a, b) => a.angle - b.angle);
  for (let i = 1; i < sortedByAngle.length; i += 1) {
    const gap = sortedByAngle[i].angle - sortedByAngle[i - 1].angle;
    if (gap < 0.42) sortedByAngle[i].angle = sortedByAngle[i - 1].angle + 0.42;
  }
  // 하드 클램프 대신 광선-맞춤: 방위를 그대로 유지한 채, 라벨·배지 여백을 남기고
  // 캔버스 경계 안에서 멈추도록 거리만 줄인다(모서리 짓눌림 방지).
  const fitDistance = (angle: number, dist: number): number => {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    let t = dist;
    if (cos > 0.001) t = Math.min(t, (mapWidth - 84 - center.x) / cos);
    if (cos < -0.001) t = Math.min(t, (84 - center.x) / cos);
    if (sin > 0.001) t = Math.min(t, (mapHeight - 118 - center.y) / sin);
    if (sin < -0.001) t = Math.min(t, (74 - center.y) / sin);
    return Math.max(48, t);
  };
  const destinationViews = rawViews.map(({ item, outer, angle, dist }) => {
    const fitted = fitDistance(angle, dist);
    return {
      ...item,
      outer,
      point: { x: center.x + Math.cos(angle) * fitted, y: center.y + Math.sin(angle) * fitted }
    };
  });

  return (
    <div className="geo-canvas-shell">
      <svg className="geo-map" viewBox={`0 0 ${mapWidth} ${mapHeight}`} role="img" aria-label={t("비식별 정규화 좌표 기반 생활권 지도")}>
      <defs>
        <linearGradient id="mapSurface" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--panel-soft)" />
          <stop offset="100%" stopColor="var(--bg)" />
        </linearGradient>
        <radialGradient id="zoneGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="color-mix(in srgb, var(--primary) 15%, transparent)" />
          <stop offset="100%" stopColor="transparent" />
        </radialGradient>
      </defs>
      <rect x="0" y="0" width={mapWidth} height={mapHeight} rx="18" />
      <g className="geo-roads" aria-hidden="true">
        <path d={`M -40 ${mapHeight * 0.7 + (driverSeed % 40)} C ${mapWidth * 0.28} ${mapHeight * 0.58}, ${mapWidth * 0.52} ${mapHeight * 0.88}, ${mapWidth + 40} ${mapHeight * 0.52}`} />
        <path d={`M -40 ${mapHeight * 0.26 + (driverSeed % 30)} C ${mapWidth * 0.32} ${mapHeight * 0.4}, ${mapWidth * 0.62} ${mapHeight * 0.14}, ${mapWidth + 40} ${mapHeight * 0.38}`} />
        <path d={`M ${mapWidth * 0.6 + (driverSeed % 60)} -30 C ${mapWidth * 0.54} ${mapHeight * 0.42}, ${mapWidth * 0.74} ${mapHeight * 0.68}, ${mapWidth * 0.66} ${mapHeight + 30}`} />
      </g>
      {[bufferRadius + 108, bufferRadius + 48].map((r) => (
        <circle key={`guide-${r}`} className="geo-guide-ring" cx={center.x} cy={center.y} r={r} />
      ))}
      <g className="geo-scatter" aria-hidden="true">
        {baselineGhost.map((pt, i) => {
          const pos = projectVisit(pt[0], pt[1], i);
          return <circle key={`sc-base-${i}`} className="ghost" cx={pos.x} cy={pos.y} r={2} />;
        })}
        {selectedVisits.map((pt, i) => {
          const pos = projectVisit(pt[0], pt[1], i);
          return (
            <circle
              key={`sc-real-${i}`}
              className={`${pt[3] ? "outer" : ""}${pt[2] ? " risk" : ""}`}
              cx={pos.x}
              cy={pos.y}
              r={pt[2] ? 3 : 2.3}
            />
          );
        })}
      </g>
      <text className="geo-title" x="42" y="42">{t("생활권 판단 지도")}</text>
      <text className="geo-subtitle" x="42" y="63">{t("점 = 실제 방문(자택 기준 상대 위치) · 회색 = 기준선 2개월 · 완충권 밖은 축척 압축")}</text>

      <circle cx={center.x} cy={center.y} r={bufferRadius + 6} fill="url(#zoneGlow)" />
      <g className="geo-core-ring">
        <circle cx={center.x} cy={center.y} r={bufferRadius} />
        <circle cx={center.x} cy={center.y} r={coreRadius} />
        <text x={center.x - bufferRadius * 0.62} y={center.y - bufferRadius * 0.86} textAnchor="middle">{t("기준 생활권")}</text>
      </g>

      {snapshot.living_zone.clusters.slice(1).map((cluster, index) => {
        const secZone = secondaryZoneQueue[index];
        const secAngle = secZone && Number.isFinite(secZone.bearing_deg)
          ? ((Number(secZone.bearing_deg) - 90) * Math.PI) / 180
          : Math.PI * 0.3;
        const secDist = bufferRadius + 124 + ((driverSeed + index * 17) % 30);
        const cx = Math.max(96, Math.min(mapWidth - 96, center.x + Math.cos(secAngle) * secDist));
        const cy = Math.max(78, Math.min(mapHeight - 78, center.y + Math.sin(secAngle) * secDist));
        const secBuffer = Math.max(40, Math.min(78, cluster.p90_radius_m / 16));
        return (
          <g key={cluster.cluster_id} className="geo-cluster">
            <circle cx={cx} cy={cy} r={secBuffer} />
            <circle cx={cx} cy={cy} r={Math.min(coreRadius - 6, secBuffer - 12)} />
            <text x={cx} y={cy - secBuffer - 9} textAnchor="middle">{(secondaryZoneQueue[index] ? localeText(secondaryZoneQueue[index].label_ko, secondaryZoneQueue[index].label_en) : null) ?? (cluster.label_ko ? t(cluster.label_ko) : tf("반복 거점 {letter}", { letter: String.fromCharCode(66 + index) }))}</text>
          </g>
        );
      })}

      {destinationViews.map(({ group, point }) => {
        const meta = interpretationClass(group.dominant);
        return (
          <g key={`route-${group.key}`} className="route-layer">
            <path className="geo-route-shadow" d={routePath(point)} />
            <path className={`geo-route ${meta.className}`} d={routePath(point)} />
          </g>
        );
      })}

      {home ? (
        <g className="geo-node home">
          <circle cx={center.x} cy={center.y} r="20" />
          <text x={center.x} y={center.y - 32} textAnchor="middle">{t("자택")}</text>
        </g>
      ) : null}

      {destinationViews.map(({ group, point }, index) => {
        const meta = interpretationClass(group.dominant);
        const risk = group.riskEvents > 0;
        return (
          <g key={`node-${group.key}`} className={`geo-node ${meta.className}${risk ? " has-risk" : ""}`}>
            {risk ? <circle className="geo-node-halo" cx={point.x} cy={point.y} r="24" /> : null}
            <circle cx={point.x} cy={point.y} r={risk ? 15 : 12} />
            <text className="geo-node-index" x={point.x} y={point.y + 4}>{index + 1}</text>
            <text className="geo-node-label" x={point.x} y={point.y + (risk ? 33 : 29)} textAnchor="middle">
              {agentDestLabels[index] ?? group.label ?? destinationTypeLabel(group.key)}
            </text>
          </g>
        );
      })}

      <g className="geo-badge" transform="translate(42 466)">
        <rect width="318" height="34" rx="9" />
        <text x="13" y="22">{tf("중심권 500m · 완충권 {buffer}m · P90 {p90}m", { buffer: Math.round(productBufferM).toLocaleString("ko-KR"), p90: Math.round(radialP90M).toLocaleString("ko-KR") })}</text>
      </g>
      <g className="geo-badge risk" transform="translate(374 466)">
        <rect width="270" height="34" rx="9" />
        <text x="13" y="22">{tf("생활권 밖 {pct} · 위치 감점 0 · 위험행동 {n}건", { pct: percent(profile.outZoneRatio * 100), n: profile.riskEvents })}</text>
      </g>
      </svg>
      <aside className="geo-detail-panel" aria-label={t("생활권 지도 근거 상세")}>
        <span>{t("방문 근거 · 합성 라벨")}</span>
        {visibleDestinations.map(({ group, destination }, index) => {
          const meta = interpretationClass(group.dominant);
          return (
            <div key={`geo-detail-${group.key}`} className={`geo-detail-row ${meta.className}`}>
              <b>{index + 1}</b>
              <strong>{agentDestLabels[index] ?? group.label ?? destinationTypeLabel(group.key)}</strong>
              <small>{meta.label} · {tf("{count}회 방문", { count: group.count })}</small>
              <em>{tf("{km}km · 위험행동 {n}건", { km: group.distanceKm.toFixed(0), n: group.riskEvents })}</em>
            </div>
          );
        })}
      </aside>
    </div>
  );
}

function ComparisonRow({ title, subtitle, rate }: { title: string; subtitle: string; rate: number }) {
  return (
    <div className="comparison-row">
      <span>
        <strong>{translateText(title)}</strong>
        <small>{translateText(subtitle)}</small>
      </span>
      <em>{percent(rate)}</em>
    </div>
  );
}

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "good" | "care" }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{translateText(label)}</span>
      <strong>{translateText(value)}</strong>
    </div>
  );
}

function ScoreMeter({ label, value, inverse = false }: { label: string; value: number | null; inverse?: boolean }) {
  if (value === null || !Number.isFinite(value)) {
    return (
      <div className="score-meter unavailable">
        <span>{translateText(label)}</span>
        <strong>N/A</strong>
        <i><b style={{ width: "0%" }} /></i>
      </div>
    );
  }
  const normalized = Math.max(0, Math.min(100, value));
  const tone = inverse && normalized >= careReviewRiskThreshold ? "risk" : normalized >= 70 ? "good" : "base";
  return (
    <div className={`score-meter ${tone}`}>
      <span>{translateText(label)}</span>
      <strong>{tf("{score}점", { score: numberFormatter.format(value) })}</strong>
      <i>
        <b style={{ width: `${normalized}%` }} />
      </i>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <span>{translateText(label)}</span>
      <strong>{translateText(value)}</strong>
    </div>
  );
}

function InspectorState({ title, detail }: { title: string; detail: string }) {
  return (
    <section className="panel inspector-state">
      <AlertTriangle size={18} />
      <h2>{title}</h2>
      <p>{detail}</p>
    </section>
  );
}

function ScreenState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="screen-state">
      <div>
        <Activity size={22} />
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
    </div>
  );
}

type DerivedProfile = {
  headline: string;
  summary: string;
  topDestinations: string[];
  outerPattern: string;
  riskPattern: string;
  repeatRate: number;
  outZoneRatio: number;
  riskEvents: number;
  nightTrips: number;
  newDestinationTrips: number;
};

type TripGroup = {
  key: string;
  label: string;
  count: number;
  distanceKm: number;
  riskEvents: number;
  nightTrips: number;
  interpretations: Record<string, number>;
  dominant: Interpretation;
};

function deriveEvidenceProfile(_driver: DriverAnnualSummary, snapshot: ZoneSnapshot, selectedRow?: MonthlyEvidence): DerivedProfile {
  const trips = snapshot.trip_interpretations;
  const grouped = Object.values(groupTrips(trips)).sort((a, b) => b.count - a.count);
  const topDestinations = grouped.slice(0, 3).map((item) => t(item.label));
  const riskEvents = grouped.reduce((sum, item) => sum + item.riskEvents, 0);
  const nightTrips = trips.reduce((sum, trip) => sum + Number(trip.night_drive_flag), 0);
  const repeatTrips = trips.reduce((sum, trip) => sum + Number(trip.route_repeat_flag), 0);
  const newDestinationTrips = trips.reduce((sum, trip) => sum + Number(trip.new_destination_flag), 0);
  const repeatRate = trips.length ? repeatTrips / trips.length : 0;
  if (!snapshot.living_zone.clusters.length) {
    const riskObservation = riskEvents > 0
      ? tf("위험행동 {n}건은 관찰됐지만 생활권 안·밖으로 분류하지 않습니다.", { n: riskEvents })
      : t("위험행동 관찰값도 생활권 안·밖으로 분류하지 않습니다.");
    return {
      headline: t("근거 부족 · 판단 보류"),
      summary: tf("{month}은 반복 거점 근거가 없어 생활권 없음입니다. {obs} 우대·케어는 보류하며 위치로 불이익을 주지 않습니다.", { month: snapshot.service_month, obs: riskObservation }),
      topDestinations: [],
      outerPattern: t("생활권 안·밖 미분류"),
      riskPattern: t("생활권 없음 · 상품 판단 보류"),
      repeatRate: 0,
      outZoneRatio: 0,
      riskEvents,
      nightTrips,
      newDestinationTrips
    };
  }
  const outZoneRatio = snapshot.monthly_evidence.out_zone_distance_ratio;
  const riskScore = snapshot.scores.out_zone_pattern_change_risk;
  // Zone STRUCTURE from the clusters (not the archetype label) — keeps the on-screen
  // interpretation type-blind, consistent with the "engine analyses without knowing
  // the type" claim. Multiple clusters ⇒ multi-zone; a wide radial P90 ⇒ wide-area.
  const zoneCount = snapshot.living_zone.clusters.length;
  const maxZoneRadiusM = Math.max(0, ...snapshot.living_zone.clusters.map((cluster) => cluster.p90_radius_m ?? 0));

  let headline = t("생활권 안 반복 주행");
  if (selectedRow?.care_state === "Care Review") headline = t("이동 맥락과 위험행동의 동시변화 검토");
  else if (riskScore >= careReviewRiskThreshold) headline = t("선택 월 이동 맥락 변화 관찰");
  else if (riskEvents > 0 && riskScore < preferredRiskCeiling) headline = t("위험행동은 있으나 변화위험은 낮음");
  else if (outZoneRatio > 0.25 && repeatRate > 0.55 && riskEvents <= trips.length * 0.2) headline = t("반복 외부 목적지 안정");
  else if (newDestinationTrips > 0 && outZoneRatio > 0.15) headline = t("신규 외부 목적지 관찰");
  else if (zoneCount >= 2) headline = t("복수 생활권 반복 이동 관찰");
  else if (maxZoneRadiusM >= 1200) headline = t("광역 반복 외부 이동 관찰");

  const outerPattern =
    outZoneRatio < 0.12
      ? t("대부분 생활권 안 주행")
      : repeatRate >= 0.6
        ? t("반복 외부 목적지 중심")
        : newDestinationTrips > 0
          ? t("신규 외부 목적지 포함")
          : t("분산된 외부 이동");
  const riskPattern =
    selectedRow?.care_state === "Care Review"
      ? t("이동 맥락 변화와 위험행동 변화가 같은 평가월에 함께 나타나 사람 검토가 필요함")
      : riskEvents === 0
      ? t("위험행동 거의 없음")
      : riskScore >= careReviewRiskThreshold
        ? tf("위험행동 {n}건 · 변화위험 높음", { n: riskEvents })
        : tf("위험행동 {n}건이 관찰됐지만 변화위험은 {score}점으로 급증 신호는 제한적", { n: riskEvents, score: numberFormatter.format(riskScore) }) + (nightTrips > 0 ? tf(" · 야간 {night}회", { night: nightTrips }) : "");

  return {
    headline,
    summary: tf("{month}에는 {destinations} 방문이 중심이며, 생활권 밖 비중은 {ratio}입니다. {outer}, {risk}으로 해석됩니다.", { month: snapshot.service_month, destinations: topDestinations.join(", "), ratio: percent(outZoneRatio * 100), outer: outerPattern, risk: riskPattern }),
    topDestinations,
    outerPattern,
    riskPattern,
    repeatRate,
    outZoneRatio,
    riskEvents,
    nightTrips,
    newDestinationTrips
  };
}

function groupTrips(trips: ZoneTripInterpretation[]) {
  const grouped: Record<string, TripGroup> = {};

  trips.forEach((trip) => {
    const current = grouped[trip.destination_type] ?? {
      key: trip.destination_type,
      label: trip.destination_label_ko ? t(trip.destination_label_ko) : destinationTypeLabel(trip.destination_type),
      count: 0,
      distanceKm: 0,
      riskEvents: 0,
      nightTrips: 0,
      interpretations: {},
      dominant: trip.interpretation
    };
    current.count += 1;
    current.distanceKm += trip.distance_km;
    current.riskEvents += trip.risk_event_count;
    current.nightTrips += Number(trip.night_drive_flag);
    current.interpretations[trip.interpretation] = (current.interpretations[trip.interpretation] ?? 0) + 1;
    current.dominant = Object.entries(current.interpretations).sort((a, b) => b[1] - a[1])[0][0];
    grouped[trip.destination_type] = current;
  });

  return grouped;
}

function destinationForType(driver: DriverAnnualSummary, type: string): Destination | null {
  const keyMap: Record<string, string> = {
    family: "family_home",
    hospital: "clinic"
  };
  return driver.living_destinations[type] ?? driver.living_destinations[keyMap[type]] ?? null;
}

function createProjector(points: Array<{ longitude: number; latitude: number }>, options = { width: 360, height: 270, marginX: 36, marginY: 52 }) {
  const longitudes = points.map((point) => point.longitude);
  const latitudes = points.map((point) => point.latitude);
  const minLon = Math.min(...longitudes);
  const maxLon = Math.max(...longitudes);
  const minLat = Math.min(...latitudes);
  const maxLat = Math.max(...latitudes);
  const lonSpan = Math.max(0.01, maxLon - minLon);
  const latSpan = Math.max(0.01, maxLat - minLat);
  const plotWidth = Math.max(1, options.width - options.marginX * 2);
  const plotHeight = Math.max(1, options.height - options.marginY * 2);

  return (longitude: number, latitude: number) => ({
    x: options.marginX + ((longitude - minLon) / lonSpan) * plotWidth,
    y: options.height - options.marginY - ((latitude - minLat) / latSpan) * plotHeight
  });
}

function chooseFocusMonth(rows: MonthlyEvidence[]) {
  if (rows.length === 0) return 1;
  const evaluation = rows.filter((row) => row.period_role !== "baseline");
  const candidates = evaluation.length ? evaluation : rows;
  return candidates.reduce((best, row) => {
    if (row.care_state === "Care Review" && best.care_state !== "Care Review") return row;
    return (row.mobility_change_index_pct ?? row.out_zone_pattern_change_risk) > (best.mobility_change_index_pct ?? best.out_zone_pattern_change_risk) ? row : best;
  }).month;
}

function monthlyIntegratedEvidenceScore(row: MonthlyEvidence) {
  const components = [
    { value: row.mileage_score, weight: selectedPolicy.weights.mileage },
    { value: row.in_zone_safe_driving_score, weight: selectedPolicy.weights.inZone },
    { value: row.out_zone_safe_driving_score, weight: selectedPolicy.weights.outZone },
    { value: row.pattern_stability_score ?? 100 - row.out_zone_pattern_change_risk, weight: selectedPolicy.weights.riskChange }
  ].filter((item): item is { value: number; weight: number } => item.value !== null && Number.isFinite(item.value));
  const observedWeight = components.reduce((sum, item) => sum + item.weight, 0);
  if (!observedWeight) return 0;
  const score = components.reduce((sum, item) => sum + item.value * item.weight, 0) / observedWeight;
  return Math.max(0, Math.min(100, score));
}

/** 카드에 표시되는 대표 상태와 동일한 우선순위: 케어 > 보류 > 우대 > 기본. */
function caseDisplayState(option: DriverOption): "Care Review" | "Hold" | "Reward" | "Neutral" {
  if (option.care_state === "Care Review") return "Care Review";
  if (option.reward_state === "Hold" || option.care_state === "Hold") return "Hold";
  if (option.reward_state === "Reward") return "Reward";
  return "Neutral";
}

function matchesCaseFilter(option: DriverOption, filter: string) {
  return filter === "all" || caseDisplayState(option) === filter;
}

function zoneIsReady(status: string | undefined) {
  return status === "available" || status === "ready";
}

const personaNameRegistry = new Map<string, { ko: string; en?: string; birthYear?: number }>();

export function registerPersonaNames(options: Array<{ customer_id: string; label: string; label_en?: string; birth_year?: number }>) {
  options.forEach((option) => {
    if (option.label) personaNameRegistry.set(option.customer_id, { ko: option.label, en: option.label_en, birthYear: option.birth_year });
  });
}

function personaName(customerId: string) {
  const entry = personaNameRegistry.get(customerId);
  if (!entry) return tf("합성 시니어 {n}", { n: String(personaIndex(customerId) + 1).padStart(2, "0") });
  // Korean locale shows the Hangul name; every other locale the romanized one.
  return getLocale() === "ko" ? entry.ko : entry.en ?? entry.ko;
}

function personaBirthYear(customerId: string) {
  return personaNameRegistry.get(customerId)?.birthYear;
}

function personaIndex(customerId: string) {
  const matched = customerId.match(/(\d+)$/);
  return matched ? Math.max(0, Number(matched[1]) - 1) : 0;
}

function caseNo(customerId: string) {
  return tf("가상 {num}", { num: String(personaIndex(customerId) + 1).padStart(2, "0") });
}

function personaResidence(driver: DriverAnnualSummary) {
  return t(driver.environment_display_name_ko ?? "이동환경 미지정");
}

function caseType(option: DriverOption) {
  return personaTypeLabel(option.persona_type);
}

function coreChangeTag(personaType: string) {
  const tags: Record<string, string> = {
    stable_reward: "저주행 안정",
    in_zone_risky: "생활권 안 위험",
    mobility_change_safe: "이동 변화",
    mobility_risk_cochange: "동시변화",
    multi_zone: "복수 생활권",
    wide_area_safe: "광역 안전"
  };
  return t(tags[personaType] ?? "패턴 관찰");
}

function riskBadgeForOption(option: DriverOption) {
  return decisionClass(option.annual_decision_signal);
}

function riskBadgeForDriver(driver: DriverAnnualSummary) {
  return decisionClass(driver.ab_comparison.annual_decision_signal);
}

function recommendedAction(driver: DriverAnnualSummary, selectedRow?: MonthlyEvidence) {
  if (driver.reward_state === "Hold" || driver.care_state === "Hold") return t("근거 부족 · 판단 보류 · 불이익 없음");
  if (driver.care_state === "Care Review") return t("담당자가 근거 확인 후 비징벌적 케어 여부 검토");
  if (driver.reward_state === "Reward") return t("우대 후보 근거 확인");
  if ((selectedRow?.mobility_change_index_pct ?? 0) > 0) return t("변화 추세 관찰 · 자동 조치 없음");
  return t("기본 유지");
}

function basisLabel(value: string) {
  if (value === "baseline_observation") return t("개인 기준선 관찰");
  if (value === "evaluation_ready") return t("평가 근거 사용 가능");
  if (value === "living_zone_evidence_hold") return t("생활권 근거 부족 · 보류");
  if (value === "data_coverage_hold") return t("데이터 충분성 미달 · 보류");
  if (value === "pre_policy_60_day_dbscan") return t("가입 전 60일 기준");
  if (value === "rolling_60_day_dbscan") return t("직전 60일 갱신");
  return value;
}

function decisionClass(value: DecisionSignal) {
  const meta = decisionMeta[value] ?? { label: translateText(value), className: "base" };
  return { ...meta, label: t(meta.label) };
}

function interpretationClass(value: Interpretation) {
  const meta = interpretationMeta[value] ?? { label: translateText(value), className: "stable", short: translateText(value) };
  return { ...meta, label: t(meta.label), short: t(meta.short) };
}

function formatDecisionCounts(counts: Record<string, number>) {
  return Object.entries(counts)
    .map(([signal, count]) => `${decisionClass(signal).label} ${count}`)
    .join(" / ");
}

function percent(value: number) {
  return `${numberFormatter.format(value)}%`;
}

function signedPercentPoint(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${numberFormatter.format(value)}%p`;
}

export default App;
