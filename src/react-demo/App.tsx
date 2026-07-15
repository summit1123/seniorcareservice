import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  FileText,
  MapPinned,
  Moon,
  RefreshCcw,
  Route,
  Search,
  ShieldCheck,
  Sun
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { demoApi } from "./api";
import { AlgorithmLabPanel } from "./AlgorithmLab";
import { getLocale, LOCALE_META, LOCALE_ORDER, setLocale, t, tf, type Locale } from "./i18n";
import { normalizeProductWeights } from "./gaip-decision";
import type { ProductRules } from "./gaip-types";
import type {
  DecisionSignal,
  Destination,
  DriverAnnualSummary,
  DriverOption,
  Interpretation,
  MonthlyEvidence,
  PersonaDirectoryResponse,
  ZoneMapResponse,
  ZoneSnapshot,
  ZoneTripInterpretation
} from "./types";

const numberFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });

const decisionMeta: Record<string, { label: string; className: string }> = {
  Reward: { label: "Reward", className: "good" },
  Neutral: { label: "Neutral", className: "base" },
  Hold: { label: "판단 보류", className: "hold" },
  "Care Review": { label: "Care Review", className: "care" },
  "Reward + Care Review": { label: "Reward + Care", className: "care" },
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
  candidate_living_zone: { label: "반복 외부 후보", className: "candidate", short: "후보 생활권" },
  out_zone_safe_driving: { label: "생활권 밖 안정", className: "safeout", short: "외부 안정" },
  out_zone_pattern_change_risk: { label: "동시변화 검토", className: "risk", short: "Care 검토" }
};

const reasonLabels: Record<string, string> = {
  BASELINE_OBSERVATION: "기준선 관찰월",
  CARE_EVIDENCE_INSUFFICIENT: "Care 근거 부족",
  HUMAN_CARE_REVIEW_SUGGESTED: "사람 검토 제안",
  REWARD_EVIDENCE_INSUFFICIENT: "Reward 근거 부족",
  REWARD_REQUIRED_MONTHS_MET: "Reward 충족월 기준 통과",
  REWARD_REQUIRED_MONTHS_NOT_MET: "Reward 충족월 기준 미달",
  SAME_MONTH_CARE_GATE_MET: "같은 달 이동·위험행동 동시변화",
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
  Standard: "Neutral",
  "Preventive Care": "Care Review"
};

const selectedPolicy = {
  id: "policy_30_30_20_20_p20_a75",
  candidateCount: 114,
  rankingScore: 120.4,
  baselineRiskCapture: 0,
  riskTargetCapture: 5,
  falsePositiveCount: 1,
  weights: {
    mileage: 0.3,
    inZone: 0.3,
    outZone: 0.2,
    riskChange: 0.2
  },
  thresholds: {
    care: 70,
    S: 85,
    A: 75,
    B: 55,
    C: 0
  },
  discountFactors: {
    preferred: "Favorable allocation for high integrated scores",
    standard: "Standard allocation by integrated score",
    care: "Lower allocation + Preventive Care"
  }
};

const careReviewRiskThreshold = selectedPolicy.thresholds.care;
const preferredRiskCeiling = 35;

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

const candidateDots = [
  { id: "c1", falsePositive: 4.4, capture: 1.1, score: 42 },
  { id: "c2", falsePositive: 3.7, capture: 2.2, score: 56 },
  { id: "c3", falsePositive: 2.9, capture: 2.9, score: 68 },
  { id: "c4", falsePositive: 2.2, capture: 3.1, score: 73 },
  { id: "c5", falsePositive: 1.8, capture: 3.7, score: 85 },
  { id: "c6", falsePositive: 0.7, capture: 2.6, score: 77 },
  { id: "c7", falsePositive: 3.1, capture: 4.1, score: 81 },
  { id: "c8", falsePositive: 2.4, capture: 4.6, score: 91 },
  { id: "c9", falsePositive: 1.5, capture: 4.8, score: 104 },
  { id: "selected", falsePositive: selectedPolicy.falsePositiveCount, capture: selectedPolicy.riskTargetCapture, score: selectedPolicy.rankingScore, selected: true },
  { id: "c10", falsePositive: 0.4, capture: 3.4, score: 94 },
  { id: "c11", falsePositive: 4.8, capture: 4.4, score: 70 },
  { id: "c12", falsePositive: 3.8, capture: 5.0, score: 89 },
  { id: "c13", falsePositive: 0.9, capture: 1.8, score: 66 },
  { id: "c14", falsePositive: 2.7, capture: 1.4, score: 51 }
];

type LoadState = "loading" | "ready" | "error";
type PageMode = "overview" | "profiles";

function App() {
  const [directory, setDirectory] = useState<PersonaDirectoryResponse | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState("gaip-051");
  const [pageMode, setPageMode] = useState<PageMode>("overview");
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

  const [lang, setLang] = useState<Locale>(() => {
    if (typeof localStorage === "undefined") return "ko";
    const saved = localStorage.getItem("masil-lang");
    return saved && LOCALE_ORDER.includes(saved as Locale) ? (saved as Locale) : "ko";
  });
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

  return (
    <div className="workbench">
      <header className="app-header">
        <div className="brand-block">
          <div>
            <p className="eyebrow">FOURSURE · MASIL · GAIP Insurance Innovation Competition 2026</p>
            <h1>{t("시니어 생활권 기반 보험 설계 대시보드")}</h1>
            <p>{t("한국 마일리지 특약을 참조하되, 반복 생활권과 운전행동의 변화를 분리해 혜택과 예방 케어 검토 근거를 제안합니다.")}</p>
          </div>
        </div>
        <div className="header-actions">
          <div className="header-controls">
            <div className="page-switch" aria-label={t("페이지 전환")}>
              <button
                type="button"
                className={pageMode === "overview" ? "active" : ""}
                onClick={() => setPageMode("overview")}
                aria-current={pageMode === "overview" ? "page" : undefined}
              >
                {t("설계구조")}
              </button>
              <button
                type="button"
                className={pageMode === "profiles" ? "active" : ""}
                onClick={() => setPageMode("profiles")}
                aria-current={pageMode === "profiles" ? "page" : undefined}
              >
                {t("프로필 분석")}
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
            <strong>{t("합성 시뮬레이션 · 사람 검토 지원")}</strong>
            <small>{t("2개월 기준선 + 12개월 평가 · 실제 요율 아님")}</small>
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
      <OverviewComparisonPanel directory={directory} />
      {rules ? <ScenarioControlPanel rules={rules} onChange={onRulesChange} directory={directory} /> : null}
      <ProductBlueprintPanel directory={directory} />
    </main>
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
  care_discount_reduction_pct: 13,
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
      hint: t("혜택 문턱을 높이고 케어를 더 민감하게 보는 시장 가정"),
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
          <p className="eyebrow">{t("상품 규칙 SANDBOX")}</p>
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
        <div className="sandbox-threshold-grid">
          <RuleNumber label={t("Reward 점수")} value={rules.reward_score_threshold} min={50} max={95} onChange={(value) => updateRule("reward_score_threshold", value)} />
          <RuleNumber label={t("Reward 충족월")} value={rules.reward_required_months} min={1} max={12} suffix={t("개월")} onChange={(value) => updateRule("reward_required_months", value)} />
          <RuleNumber label={t("최소 데이터")} value={rules.minimum_data_coverage_pct} min={50} max={100} suffix="%" onChange={(value) => updateRule("minimum_data_coverage_pct", value)} />
          <RuleNumber label={t("이동 변화")} value={rules.care_mobility_change_threshold} min={0} max={100} suffix="%" onChange={(value) => updateRule("care_mobility_change_threshold", value)} />
          <RuleNumber label={t("위험행동 변화")} value={rules.care_risky_behavior_threshold} min={0} max={100} suffix="%" onChange={(value) => updateRule("care_risky_behavior_threshold", value)} />
        </div>
      </div>
      <div className="sandbox-live" aria-live="polite">
        <div className="sandbox-live-head">
          <span className="sandbox-live-title">{t("지금 규칙으로 다시 계산한 180개 사례")}</span>
          <span className="sandbox-live-avg">{t("제안 평균 할인율 ")}<strong>{percent(avgDiscount)}</strong></span>
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
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  suffix?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Math.max(min, Math.min(max, Number(event.target.value))))} />
      <em>{suffix}</em>
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
          <strong>{t("거리 혜택과 예방 케어 검토를 서로 독립된 두 축으로 설계합니다")}</strong>
          <p>{t("안전운전은 혜택(Reward)으로 인정하고, 같은 달 이동 변화와 위험행동 변화가 함께 나타날 때만 사람에게 예방 케어 검토를 제안합니다.")}</p>
          <p className="stakes-line">{t("예방 케어는 처벌이 아니라 조기 개입입니다 — 심각한 사고가 나기 전에 담당자가 가족·의료·이동지원과 연결할 근거를 만드는 것이 목표입니다.")}</p>
        </div>
        <div>
          <span>{t("검증 결과")}</span>
          <strong>{t("도심·교외·광역 저밀도 환경에서도 동일한 안전 원칙을 검증합니다")}</strong>
          <p>{t("결과는 합성 시나리오의 일관성과 예외 처리를 보여주는 것이며, 실제 사고감소·손해율·확정 요율을 뜻하지 않습니다.")}</p>
        </div>
      </div>

      <div className="risk-hypothesis">
        <span className="eyebrow">{t("위험 가설")}</span>
        <strong>{t("익숙한 생활권은 안전 신호, 반경 급확대와 행동 변화는 위험 신호입니다")}</strong>
        <p>{t("노인 운전자는 익숙한 반복 경로·시간대에서 사고 빈도가 낮습니다. 반대로 생활권 반경이 갑자기 넓어지면서 급감속·과속이 함께 늘어나는 것은 인지·신체 기능 저하가 드러나는 알려진 전조입니다. 그래서 얼마나 탔는지가 아니라, 어디를 어떻게, 어떻게 달라지며 타는지를 봅니다.")}</p>
        <p className="hypothesis-note">{t("이 가설의 계산 가능성과 예외 처리를 합성 데이터로 검증하며, 실제 사고·손해율 상관은 별도 실증이 필요합니다.")}</p>
      </div>

      <div className="experiment-structure">
        <span className="eyebrow">{t("데이터 실험 구조")}</span>
        <strong>{t("AI 에이전트가 각 시니어의 삶으로 주행 데이터를 만들고, 결정론 엔진이 유형을 모른 채 분석합니다")}</strong>
        <div className="experiment-structure-grid">
          <div className="es-step">
            <b>{t("1 · 추론 — AI 에이전트")}</b>
            <p>{t("페르소나의 생활 맥락(가구·취미·목표·운전 습관)에서 14개월간 어디를·어떤 리듬으로·언제부터 다르게 다니는지를 추론해, 이름 있는 생활권과 변화 시점을 만듭니다.")}</p>
          </div>
          <div className="es-step">
            <b>{t("2 · 분석 — 결정론 엔진")}</b>
            <p>{t("생성된 방문 데이터를 유형 라벨 없이 그대로 받아 실제 DBSCAN 군집·생활권 반경·통합 점수·같은 달 AND 게이트로 판정합니다. 결과는 엔진에서 창발하며 목표값을 심지 않습니다.")}</p>
          </div>
          <div className="es-step">
            <b>{t("3 · 검증 — 재현 가능")}</b>
            <p>{t("에이전트 생성물은 오프라인에서 한 번 만들어 캐시·고정하므로 데모는 완전히 결정론적이고 재현 가능합니다. 60명 전원이 아키타입 경향과 검증 게이트를 통과하는지 확인합니다.")}</p>
          </div>
        </div>
        <p className="experiment-structure-note">{t("추론(무엇을)과 분석(어떻게 판정)을 분리한 구조입니다. 아키타입 경향은 실험의 통제변수이고, 위험 크기는 엔진이 관리하므로 라벨 유출 없이 결과가 창발합니다.")}</p>
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
            <p>{t("어디를 가든 위치만으로는 감점하지 않고, 원본 좌표를 저장하거나 노출하지 않습니다. 텔레매틱스를 지켜봐 주는 장치로 느끼게 하는 프라이버시·설명가능 설계입니다.")}</p>
          </div>
          <div>
            <b>{t("가족의 안심")}</b>
            <p>{t("이동과 위험행동이 같은 달에 함께 나빠질 때만, 처벌이 아니라 조기 개입 신호를 사람에게 전합니다. 부모의 운전을 걱정하는 가족이 믿고 맡길 수 있는 근거입니다.")}</p>
          </div>
        </div>
        <p className="buyer-trust-note">{t("빠르게 늘어나는 고령 운전자는 저평가·과소보장되기 쉬운 세그먼트입니다. 행동 기반의 공정한 가격으로 이들을 다시 보험 안으로 초대하는 것이 이 설계의 목표입니다.")}</p>
      </div>

      <div className="comparison-ledger" aria-label={t("기존 마일리지와 제안 산식 비교표")}>
        <div className="ledger-head">
          <span>{t("비교 항목")}</span>
          <strong>{t("기존 마일리지 산식 · 국내 기준")}</strong>
          <strong>{t("마실 제안 산식 · 시뮬레이션 후보")}</strong>
        </div>
        <ComparisonLedgerRow
          label={t("판단 기준")}
          legacy={t("연간 주행거리와 차종으로 할인율 결정")}
          proposed={t("주행거리 + 생활권 안/밖 안전 + 패턴 안정성")}
        />
        <ComparisonLedgerRow
          label={t("같은 저주행 구간 처리")}
          legacy={t("같은 거리구간이면 생활권 변화와 관계없이 같은 할인율")}
          proposed={t("혜택은 안전 점수로, 예방 케어는 같은 달 두 변화지표의 동시 충족 조건으로 별도 계산")}
        />
        <ComparisonLedgerRow
          label={t("연간 할인 계산")}
          legacy={t("거리구간 할인율을 그대로 적용")}
          proposed={t("한국 할인표를 참조하고 후보 가중치·임계치의 민감도만 비교")}
        />
        <ComparisonLedgerRow
          label={t("설명 가능성")}
          legacy={t("조정 근거가 ‘적게 탔다’에 머물러 설명력이 약함")}
          proposed={t("비식별 반복 거점, 월별 근거, Reason Code와 사람 검토 기록 제공")}
        />
      </div>

      <div className="overview-evidence-grid">
        <div className="decision-donut-card">
          <span>{t("제안 산식의 판정 구조 · 2축 → 4상태")}</span>
          <div className="decision-donut-wrap">
            <div className="decision-donut" style={{ background: donutBackground }}>
              <div>
                <strong>{summary.customer_count}</strong>
                <small>{t("사례 판정 분포")}</small>
              </div>
            </div>
            <div className="decision-donut-legend">
              <DecisionLegend label={tf("우대 {count}", { count: preferredCount })} detail={t("Reward축 · 안전 인정")} className="preferred" />
              <DecisionLegend label={tf("기본 {count}", { count: standardCount })} detail={t("변화 낮음 · 중립")} className="standard" />
              <DecisionLegend label={tf("예방 케어 {count}", { count: careCount })} detail={t("Care축 · 사람 검토")} className="care" />
              {holdCount ? (
                <DecisionLegend label={tf("판단 보류 {count}", { count: holdCount })} detail={t("근거 부족 · 불이익 없음")} className="hold" />
              ) : null}
            </div>
          </div>
          <p className="portfolio-footnote">
            {t("안전운전 인정(Reward축)과 예방 케어 검토(Care축)를 독립된 두 축으로 계산하면, 두 축의 조합이 우대·기본·예방 케어·판단 보류의 네 상태로 나타납니다. 기준이 다른 시장에서도 같은 엔진이 두 축을 그대로 다시 계산합니다.")}
          </p>
        </div>

        <div className="simulation-result-card">
          <span>{t("국내 기준 A/B 시뮬레이션 · 180개 사례")}</span>
          <strong>{t("총액을 맞춰 끼운 값이 아니라, 두 산식을 각각 계산한 결과입니다")}</strong>
          <p>
            {t("같은 인물 60명(6개 유형 × 10명)을 3개 이동환경에서 각각 시뮬레이션한 180개 사례의 연간 주행 데이터를, 기존 마일리지 산식과 제안 통합 산식에 각각 넣어 비교했습니다. 실제 계약보험료를 확정하지 않은 단계이므로, 평균 할인율과 우대·기본·예방 케어 판정 구조를 중심으로 검증합니다.")}
          </p>
          <p className="business-case-line">{t("제안 산식은 평균 할인을 소폭 늘리지만, 저평가된 시니어 세그먼트의 획득·유지와 Care 축의 중대 클레임 조기 차단으로 상쇄하는 구조입니다. 손해율 효과는 별도 실증이 필요합니다.")}</p>
          <div className="budget-compare-grid no-money">
            <div>
              <span>{t("기존 평균 할인율")}</span>
              <strong>{percent(summary.avg_existing_discount_rate_pct)}</strong>
              <small>{t("연간 주행거리 구간 기준")}</small>
            </div>
            <div>
              <span>{t("제안 평균 할인율")}</span>
              <strong>{percent(summary.avg_proposed_discount_rate_pct)}</strong>
              <small>{t("4개 지표 통합점수 기준")}</small>
            </div>
            <div>
              <span>{t("평균 할인율 변화")}</span>
              <strong>{signedPercentPoint(avgRateDelta)}</strong>
              <small>{t("실제 계약보험료 없이 비교 가능한 비율 차이")}</small>
            </div>
          </div>
          <p className="portfolio-footnote">
            {t("합성 시뮬레이션 결과입니다. 실제 요율·인수·케어 결정은 계리·상품·심사 권한자의 검토 없이 확정하지 않습니다. 기준을 다른 시장 값으로 바꾸면 아래 상품 Sandbox가 180개 사례를 즉시 다시 계산합니다.")}
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

  return (
    <aside className="case-rail" aria-label={t("가상 시니어 사례 목록")}>
      <div className="rail-heading">
        <p className="eyebrow">{t("가상 사례")}</p>
        <h2>{tf("{count}개 시나리오", { count: options.length })}</h2>
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
        {ordered.map((option) => {
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
                <small>
                  {t(option.environment_display_name_ko ?? "이동환경")} · {changeTag}
                </small>
              </span>
              <span className="case-state-pills">
                <em className={`risk-pill ${decisionClass(option.reward_state ?? "Neutral").className}`}>{stateLabelKo(option.reward_state ?? "Neutral")}</em>
                {option.care_state === "Care Review" ? <em className="risk-pill care">{t("케어")}</em> : null}
                {option.reward_state === "Hold" || option.care_state === "Hold" ? <em className="risk-pill hold">{t("보류")}</em> : null}
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
    return <InspectorState title={t("사례 선택 대기")} detail={t("좌측 사례를 선택하면 Reward·Care 검토 요약이 표시됩니다.")} />;
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
        ? t("개인 기준선 관찰 · Care 평가 제외")
        : profile?.headline;
  const decisionReasons = profile
    ? [profile.headline, profile.outerPattern, profile.riskPattern]
    : driver.annual_score.annual_reason_codes.slice(0, 3).map((code) => t(reasonLabels[code] ?? code));

  return (
    <section className={`decision-summary-card ${driverState === "loading" ? "is-loading" : ""}`} aria-label={t("검토 제안 요약")}>
      <div className="summary-identity">
        <p className="eyebrow">{t("검토 제안 요약")}</p>
        <h2>{personaName(driver.customer_id)}</h2>
        <span>{driver.environment_display_name_ko ? t(driver.environment_display_name_ko) : personaResidence(driver)} · {personaTypeLabel(driver.persona_type)}</span>
      </div>

      <div className="summary-verdict">
        <span>{t("선택 월 근거")}</span>
        <strong>{reviewHeadline ?? decisionReasons[0]}</strong>
        <p>{decisionReasons.slice(1, 3).join(" ")}</p>
      </div>

      <div className="summary-decision-stack">
        <div className={`risk-score-block ${reward.className}`}>
          <span>{t("연간 혜택 축")}</span>
          <strong>{stateLabelKo(reward.label)}</strong>
          <b>{tf("후보점수 {score}점", { score: numberFormatter.format(driver.annual_score.annual_senior_safe_mileage_score) })}</b>
        </div>

        <div className={`premium-delta-block ${care.className}`}>
          <span>{t("선택 월 케어 축")}</span>
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
    return <InspectorState title={t("판단 과정 대기")} detail={t("사례를 선택하면 할인 보정 과정이 표시됩니다.")} />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const mobilityChange = selectedRow?.mobility_change_index_pct ?? selectedRow?.out_zone_pattern_change_risk ?? 0;
  const riskyBehaviorChange = selectedRow?.risky_behavior_change_index_pct ?? 0;
  const careGate = selectedRow?.care_state === "Care Review";
  const zoneBasis = !zoneIsReady(driver.zone_status) || !zoneMap?.snapshot.living_zone.clusters.length
    ? t("No Zone · 판단 보류")
    : zoneMap
      ? tf("중심권 500m · P90 {p90}m", { p90: Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("ko-KR") })
      : t("생활권 산출 중");
  const annualTierKo = tierLabelKo(driver.reward_state, driver.care_state);
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
      detail: t("기준선 2개월의 반복 목적지와 이동 반경 반영"),
      icon: MapPinned
    },
    {
      title: tf("{month} 변화", { month: selectedRow?.service_month ?? tf("{n}월", { n: selectedMonth }) }),
      value: tf("이동 변화 {mob}% · 위험행동 {risk}%", { mob: numberFormatter.format(mobilityChange), risk: numberFormatter.format(riskyBehaviorChange) }),
      detail: careGate ? t("같은 달 두 변화가 함께 임계치를 넘어 예방 케어 검토") : t("한 지표만으로는 케어를 제안하지 않음"),
      icon: Activity
    },
    {
      title: t("연간 판단"),
      value: `${percent(comparison.proposed_discount_rate_pct)} · ${annualTierKo}`,
      detail: t("판정 근거는 사람이 최종 검토하며 자동 확정하지 않음"),
      icon: AlertTriangle
    }
  ];

  return (
    <section className="decision-process-frame" aria-label={t("상품 근거와 사람 검토 과정")}>
      <div className="decision-process-copy">
        <p className="eyebrow">{t("판단 과정")}</p>
        <h2>{t("같은 저주행이라도 생활권 밖 위험변화가 있으면 다른 결론이 납니다")}</h2>
        <p>
          {t("생활권 밖 이동 자체는 중립입니다. 혜택(우대)은 안전운전 근거로 계산하고, 같은 달 이동 맥락과 위험행동이 동시에 달라질 때만 사람에게 예방 케어 검토를 제안합니다.")}
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
          <h2>{zoneIsReady(driver.zone_status) ? t("자택 중심 생활권과 최근 변화 목적지") : t("생활권 미확정 · 반복 거점 근거 부족")}</h2>
        </div>
        {profile && zoneMap && zoneIsReady(driver.zone_status) ? (
          <div className="map-kpis">
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
            <p>{t("가짜 중심을 만들지 않고 No Zone으로 유지합니다. Reward와 Care는 판단 보류이며 불이익을 주지 않습니다.")}</p>
          </div>
        ) : (
          <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
        )}
      </div>

      {driver.mobility_profile && driver.mobility_profile.zones.length ? (
        <div className="agent-mobility">
          <div className="agent-mobility-head">
            <span className="eyebrow">{t("AI 에이전트가 추론한 생활 동선")}</span>
            <span className="agent-badge">{t("오프라인 생성 · 캐시 · 결정론 엔진이 유형 모른 채 분석")}</span>
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
          <p className="agent-mobility-note">{t("이 동선은 AI가 페르소나 맥락으로 생성한 합성 데이터이며, 실제 위치·인물이 아닙니다. 좌표는 결정론 엔진 내부에서만 쓰이고 화면에 노출되지 않습니다.")}</p>
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
      <p className="map-formula-note">{t("완충권 = max(500m, min(개인 P90, 2km)) — 군집이 만들어진 뒤 적용하는 상품 인정 반경입니다.")}</p>
    </section>
  );
}

function AnalysisTabs({
  driver,
  zoneMap,
  rows,
  selectedMonth,
  loading,
  onSelectMonth
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  rows: MonthlyEvidence[];
  selectedMonth: number;
  loading: boolean;
  onSelectMonth: (month: number) => void;
}) {
  const [activeTab, setActiveTab] = useState("Overview");
  const selectedRow = rows.find((row) => row.month === selectedMonth) ?? rows[0];
  const profile = driver && zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const tabs = [
    { key: "Overview", label: t("요약") },
    { key: "Monthly Pattern", label: t("월별 패턴") },
    { key: "Risk Signals", label: t("위험 신호") },
    { key: "Premium Simulation", label: t("요율 Sandbox") },
    { key: "Algorithm Lab", label: t("알고리즘 실험실") },
    { key: "Report", label: t("리포트") }
  ];

  return (
    <section className={`analysis-tabs ${loading ? "is-loading" : ""}`} aria-label="Lower Analysis Tabs">
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
            <InsightCard title={t("상품 제안")} value={tf("연간 {annual} · 월 케어 {care}", { annual: stateLabelKo(driver.reward_state ?? "Neutral"), care: stateLabelKo(selectedRow.care_state ?? "None") })} detail={t("연간 혜택과 선택 월 케어를 독립 계산한 뒤 사람이 검토합니다.")} />
          </div>
        ) : null}

        {activeTab === "Monthly Pattern" ? (
          <MonthlyPatternChart rows={rows} selectedMonth={selectedMonth} onSelectMonth={onSelectMonth} />
        ) : null}

        {activeTab === "Risk Signals" && driver && selectedRow ? (
          <div className="risk-signal-grid">
            <ScoreMeter label={t("주행거리 점수")} value={selectedRow.mileage_score} helper={t("월별 주행거리를 연환산해 저주행일수록 높게 계산")} />
            <ScoreMeter label={t("생활권 안 안전점수")} value={selectedRow.in_zone_safe_driving_score} helper={t("생활권 안 급감속·과속·야간 비율이 낮을수록 높음")} />
            <ScoreMeter label={t("생활권 밖 안전점수")} value={selectedRow.out_zone_safe_driving_score} helper={t("생활권 밖 위험행동과 야간 비율이 낮을수록 높음")} />
            <ScoreMeter label={t("패턴 안정성")} value={selectedRow.pattern_stability_score ?? Math.max(0, 100 - selectedRow.out_zone_pattern_change_risk)} helper={t("개인 기준선 대비 이동 맥락의 안정성")} />
            <div className={`care-gate-card ${selectedRow.care_state === "Care Review" ? "active" : ""}`}>
              <span>{t("케어 동시조건")}</span>
              <strong>{tf("이동 {mob} + 위험행동 {risk}", { mob: numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0), risk: numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0) })}</strong>
              <small>{selectedRow.care_state === "Care Review" ? t("사람 검토 제안") : t("케어 자동 제안 없음")}</small>
            </div>
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
            <span>{t("우측 Human Review 패널에서 근거 초안을 생성합니다. 설명문은 최종 보험료·인수·Care 결정을 대신하지 않습니다.")}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MonthlyPatternChart({ rows, selectedMonth, onSelectMonth }: { rows: MonthlyEvidence[]; selectedMonth: number; onSelectMonth: (month: number) => void }) {
  return (
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
            <span>{tf("{n}월", { n: row.month })}</span>
            <i><b style={{ height: `${Math.max(12, Math.min(92, row.out_zone_pattern_change_risk))}%` }} /></i>
            <b>{numberFormatter.format(row.out_zone_pattern_change_risk)}</b>
          </button>
        );
      })}
    </div>
  );
}

const DEMO_USD_RATE = 1350; // 예시 환율(비교 열람용) — 실제 환율 아님

function krwWithUsd(amount: number | null | undefined) {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "—";
  const usd = amount / DEMO_USD_RATE;
  return `₩${Math.round(amount).toLocaleString("ko-KR")} (≈$${usd.toLocaleString("en-US", { maximumFractionDigits: 0 })})`;
}

function PremiumSimulation({ driver }: { driver: DriverAnnualSummary }) {
  const comparison = driver.ab_comparison;
  const existingRate = comparison.existing_discount_rate_pct;
  const proposedRate = comparison.proposed_discount_rate_pct;
  const maxRate = Math.max(existingRate, proposedRate, 1);
  return (
    <div className="premium-simulation">
      <div>
        <span>{t("기존 마일리지 기준 · 국내")}</span>
        <strong>{percent(existingRate)}</strong>
        <i><b style={{ width: `${(existingRate / maxRate) * 100}%` }} /></i>
        <small>{tf("적용 시 {amount}", { amount: krwWithUsd(comparison.existing_net_premium_krw) })}</small>
      </div>
      <div>
        <span>{t("마실 제안 산식 · 후보")}</span>
        <strong>{percent(proposedRate)}</strong>
        <i><b style={{ width: `${(proposedRate / maxRate) * 100}%` }} /></i>
        <small>{tf("적용 시 {amount}", { amount: krwWithUsd(comparison.proposed_net_premium_krw) })}</small>
      </div>
      <p>
        {tf("기준 보험료 {base} 가정의 합성 비교입니다. 달러 표기는 해외 심사위원의 규모 비교를 위한 예시 환율(1$≈₩{rate}) 환산이며, 실제 계약보험료·해외 요율을 의미하지 않습니다.", { base: krwWithUsd(comparison.base_premium_krw), rate: DEMO_USD_RATE.toLocaleString("ko-KR") })}
      </p>
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
  const [state, setState] = useState<"idle" | "streaming" | "ready" | "error">("idle");
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [reviewDecision, setReviewDecision] = useState<"pending" | "approved" | "held" | "requested">("pending");
  const [reviewNote, setReviewNote] = useState("");

  useEffect(() => {
    setState("idle");
    setMarkdown("");
    setError("");
    setProgress("");
    setReviewDecision("pending");
    setReviewNote("");
  }, [driver?.customer_id, selectedMonth]);

  if (!driver) return <aside className="decision-panel"><InspectorState title={t("Human Review 패널")} detail={t("사례를 선택하면 근거와 검토 작업이 표시됩니다.")} /></aside>;

  const comparison = driver.ab_comparison;
  const decision = decisionClass(driver.reward_state ?? comparison.annual_decision_signal);
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const selectedCare = selectedRow?.care_state ?? "None";
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const reviewHeadline = selectedCare === "Care Review"
    ? t("이동 맥락과 위험행동의 동시변화 검토")
    : selectedCare === "Hold"
      ? t("근거 부족 · 판단 보류")
      : selectedCare === "Observation"
        ? t("개인 기준선 관찰 · Care 평가 제외")
        : profile?.headline;
  const xaiReasons = topXaiReasons(driver, zoneMap, selectedMonth);
  const rateDelta = comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct;
  const generate = async () => {
    setState("streaming");
    setMarkdown("");
    setError("");
    setProgress(t("월별 주행 근거를 리포트 API로 전송 중"));
    try {
      let next = "";
      await demoApi.streamMonthlyReport(driver.customer_id, selectedMonth, (chunk) => {
        next += chunk;
        setProgress(tf("생성 중: {section}", { section: latestReportSection(next) }));
        setMarkdown(next);
      }, rules ?? undefined);
      setProgress(t("리포트 생성 완료"));
      setState("ready");
    } catch (reportError) {
      setState("error");
      setError(reportError instanceof Error ? reportError.message : t("리포트 생성에 실패했습니다"));
    }
  };

  return (
    <aside className={`decision-panel ${loading ? "is-loading" : ""} ${markdown ? "has-report" : ""}`} aria-label={t("사람 검토 패널")}>
      <div className="decision-panel-head">
        <p className="eyebrow">HUMAN REVIEW</p>
        <h2>{t("검토 제안")}</h2>
        <em className={`decision ${decision.className}`}>{stateLabelKo(decision.label)}</em>
      </div>

      <div className="decision-money-stack">
        <div>
          <span>{t("기존 마일리지 기준")}</span>
          <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
        </div>
        <div>
          <span>{t("마실 제안 후보")}</span>
          <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
          <small>{tf("통합점수 {score}점", { score: numberFormatter.format(comparison.annual_senior_safe_mileage_score) })}</small>
        </div>
        <div className="money-delta">
          <span>{t("후보 차이")}</span>
          <strong>{signedPercentPoint(rateDelta)}</strong>
          <small>{t("후보 민감도 · 확정 요율 아님")}</small>
        </div>
      </div>

      <div className="decision-reason-box">
        <span>{t("검토 근거")}</span>
        <strong>{translateText(reviewHeadline ?? driver.care_context.product_role)}</strong>
        <p>{translateText(profile?.summary ?? driver.care_context.message_focus)}</p>
      </div>

      <div className="xai-inspector" aria-label="Reason Code evidence">
        <span>{tf("지표별 영향 분해 · {month}", { month: zoneMap?.snapshot.service_month ?? tf("{n}월", { n: selectedMonth }) })}</span>
        {xaiReasons.map((reason) => (
          <div key={reason.label}>
            <strong>{reason.label}</strong>
            <i><b style={{ width: `${reason.width}%` }} /></i>
            <em>{reason.detail}</em>
          </div>
        ))}
      </div>

      <div className="review-state-box" aria-label={t("현재 화면의 사람 검토 상태")}>
        <div>
          <span>{t("연간 혜택")}</span>
          <strong>{stateLabelKo(driver.reward_state ?? "Neutral")}</strong>
        </div>
        <div>
          <span>{t("선택 월 케어")}</span>
          <strong>{stateLabelKo(selectedCare)}</strong>
        </div>
        <div>
          <span>{t("모델")}</span>
          <strong title={driver.model_version ?? "masil-gaip-simulation/v1"}>{t("합성 시뮬레이션 엔진 v1")}</strong>
        </div>
      </div>

      <label className="review-note-field">
        <span>{t("담당자 메모")}</span>
        <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder={t("승인·보류 이유 또는 추가 확인사항")} />
      </label>
      <div className="review-actions">
        <button type="button" className={reviewDecision === "approved" ? "active approve" : ""} onClick={() => setReviewDecision("approved")}>{t("근거 확인")}</button>
        <button type="button" className={reviewDecision === "requested" ? "active request" : ""} onClick={() => setReviewDecision("requested")}>{t("추가근거 요청")}</button>
        <button type="button" className={reviewDecision === "held" ? "active hold" : ""} onClick={() => setReviewDecision("held")}>{t("판단 보류")}</button>
      </div>
      <p className="review-audit-line">
        {reviewDecision === "pending"
          ? t("검토 전 · AI 제안은 실제 결정에 반영되지 않음 · 저장되지 않은 데모 상태")
          : reviewDecision === "approved"
            ? t("현재 화면에서 근거 확인 표시 · 저장되지 않음 · 실제 상품 결정은 별도 권한자 승인 필요")
            : reviewDecision === "requested"
              ? t("현재 화면에서 추가근거 요청 표시 · 저장되지 않음 · 자동 판단 없음")
              : t("현재 화면에서 판단 보류 표시 · 저장되지 않음 · 고객 불이익 없음")}
      </p>

      <button className="report-button" type="button" onClick={generate} disabled={state === "streaming"}>
        {state === "streaming" ? <RefreshCcw size={15} /> : <FileText size={15} />}
        {state === "streaming" ? t("근거 초안 생성 중") : tf("{month} 근거 초안", { month: zoneMap?.snapshot.service_month ?? tf("{n}월", { n: selectedMonth }) })}
      </button>

      {state === "error" ? <p className="error-copy">{error}</p> : null}
      {progress ? <p className="report-progress">{progress}</p> : null}
      {markdown ? (
        <div className="report-popout" role="status" aria-live="polite">
          <div className="report-popout-head">
            <div>
              <span>{t("보험사 직원용 검토 초안")}</span>
              <strong>{personaName(driver.customer_id)} · {zoneMap?.snapshot.service_month ?? tf("{n}월", { n: selectedMonth })} {t("근거 분석")}</strong>
            </div>
            <button
              className="report-close-button"
              type="button"
              onClick={() => {
                setMarkdown("");
                setProgress("");
                setState("idle");
              }}
              disabled={state === "streaming"}
            >
              {state === "streaming" ? t("생성 중") : t("완료")}
            </button>
          </div>
          <MarkdownReport markdown={markdown} className="decision-report-stream" />
        </div>
      ) : null}
    </aside>
  );
}

function latestReportSection(markdown: string) {
  const knownSections = [
    "월별 결론 요약",
    "연간 산식 반영",
    "생활권 판단 근거",
    "월별 주행 패턴",
    "XAI 주요 원인",
    "상담 및 케어 액션",
    "검토 한계와 확인 필요사항"
  ];
  const known = knownSections.filter((section) => markdown.includes(section)).at(-1);
  if (known) return known;
  const matches = [...markdown.matchAll(/^##\s+\d+\.\s+(.+)$/gm)];
  const latest = matches.at(-1)?.[1]?.trim();
  return latest && latest.length > 6 ? latest : t("리포트 초안 수신 중");
}

function MarkdownReport({ markdown, className = "" }: { markdown: string; className?: string }) {
  const lines = markdown.split(/\r?\n/);
  const elements: JSX.Element[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    if (line.startsWith("### ")) {
      elements.push(<h4 key={`h4-${index}`}>{renderInlineMarkdown(line.replace(/^###\s+/, ""))}</h4>);
      index += 1;
      continue;
    }

    if (line.startsWith("## ")) {
      elements.push(<h3 key={`h3-${index}`}>{renderInlineMarkdown(line.replace(/^##\s+/, ""))}</h3>);
      index += 1;
      continue;
    }

    if (line.startsWith("# ")) {
      elements.push(<h2 key={`h2-${index}`}>{renderInlineMarkdown(line.replace(/^#\s+/, ""))}</h2>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      elements.push(
        <ul key={`ul-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      elements.push(
        <ol key={`ol-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>
      );
      continue;
    }

    elements.push(<p key={`p-${index}`}>{renderInlineMarkdown(line)}</p>);
    index += 1;
  }

  return <div className={`markdown-rendered ${className}`.trim()}>{elements}</div>;
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
      label: t("이동 맥락 변화"),
      width: meterWidth(risk),
      detail: scoreDetail(risk)
    },
    {
      label: t("선택 월 생활권 안 안전점수"),
      width: meterWidth(inZone),
      detail: scoreDetail(inZone)
    },
    {
      label: t("선택 월 생활권 밖 안전점수"),
      width: meterWidth(outZone),
      detail: scoreDetail(outZone)
    },
    {
      label: t("선택 월 주행거리 점수"),
      width: meterWidth(mileage),
      detail: tf("{detail} · {count}건", { detail: scoreDetail(mileage), count: tripCount })
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
  return (
    <section className="panel blueprint-panel" aria-label={t("데이터 생성 방식과 최종 산식")}>
      <div className="panel-head">
        <div>
          <p className="eyebrow">{t("AI 활용과 상품 검증")}</p>
          <h2>{t("AI는 보험료를 직접 결정하지 않고, 생활권 생성·후보 산식 탐색·판정 설명을 보조합니다.")}</h2>
        </div>
        <span className="count-badge">{t("4개 지표 가중치 비교")}</span>
      </div>

      <div className="ai-proof-row" aria-label={t("AI 활용 위치")}>
        <div>
          <span>AI 1</span>
          <strong>{t("생활권 자동 생성")}</strong>
          <p>{t("기준선 2개월의 목적지를 DBSCAN으로 군집화하고, 개인 P90 반경으로 주차·우회 같은 작은 흔들림을 흡수합니다.")}</p>
        </div>
        <div>
          <span>AI 2</span>
          <strong>{t("4개 지표 가중치 선택")}</strong>
          <p>{t("주행거리, 생활권 안 안전, 생활권 밖 안전, 위험변화를 어느 비율로 반영할지 후보 산식을 비교합니다.")}</p>
        </div>
        <div>
          <span>AI 3</span>
          <strong>{t("설명가능 AI(XAI) + 직원용 리포트")}</strong>
          <p>{t("설명가능 AI(XAI)가 4개 지표의 영향을 추출하면 LLM이 직원용 설명문으로 바꿉니다. 보험료·인수·케어는 사람이 최종 결정합니다.")}</p>
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
          <strong>{t("2개월 기준선으로 생활권 생성")}</strong>
          <p>{t("DBSCAN은 반복 거점을 찾고, 각 거점에 중심권 500m와 중심–방문점 P90 완충권을 별도로 적용합니다.")}</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>3</span>
          <strong>{t("12개월 평가와 사람 검토")}</strong>
          <p>{t("Reward와 Care를 독립 계산하고, Care는 같은 달 이동 변화와 위험행동 변화가 모두 있을 때만 검토를 제안합니다.")}</p>
        </div>
      </div>

      <div className="formula-workbench">
        <div className="formula-decision-card">
          <div className="blueprint-title">
            <BarChart3 size={17} />
            <strong>{t("최종 통합점수 산식")}</strong>
          </div>
          <p className="formula-lead">
            {t("한국 마일리지 거리 기준은 참조값으로 유지하되, Reward 산식과 케어 동시조건를 분리해 처벌 없는 예방지원 구조를 검증합니다.")}
          </p>
          <div className="weight-layout" aria-label="Final Formula Weights">
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
            <strong>{tf("Reward 후보점수 = 주행거리 {mileage}% + 생활권 안 안전 {inZone}% + 생활권 밖 안전 {outZone}% + 패턴 안정성 {stability}%", { mileage: weights.mileage, inZone: weights.in_zone_safe, outZone: weights.out_zone_safe, stability: weights.pattern_stability })}</strong>
          </div>
        </div>

        <div className="formula-evidence-card">
          <div className="blueprint-title">
            <ShieldCheck size={17} />
            <strong>{t("왜 이 비율을 선택했나")}</strong>
          </div>
          <div className="evidence-checklist">
            <div>
              <span>{t("비용 검증")}</span>
              <strong>{t("평균 할인율 변화가 설명 가능한 범위인지 확인")}</strong>
              <p>{t("두 산식을 각각 계산해 기존 할인 구조와 비교하고, 변화폭이 과도하지 않은지 확인합니다.")}</p>
            </div>
            <div>
              <span>{t("공정성 조건")}</span>
              <strong>{t("생활권 밖이라는 이유만으로 감점하지 않음")}</strong>
              <p>{t("반복 외부 목적지와 안정 주행은 기본 또는 우대 판단이 가능해야 합니다.")}</p>
            </div>
            <div>
              <span>{t("Care 조건")}</span>
              <strong>{t("같은 달의 이동 변화와 위험행동 변화 동시 충족")}</strong>
              <p>{t("한 지표만 변하거나 데이터가 부족하면 자동 Care가 아니라 정상 또는 판단 보류로 남깁니다.")}</p>
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
        <span>{t("생활권 알고리즘 운영 역할")}</span>
        <strong>{t("화면에서는 DBSCAN 결과만 사용하며, 다른 알고리즘의 결과를 실행한 것처럼 표시하지 않습니다.")}</strong>
      </div>

      <div className="candidate-comparison-grid" aria-label={t("후보 산식 비교")}>
        <div className="selected">
          <span>DBSCAN</span>
          <strong>{t("운영 참조")}</strong>
          <p>{t("같은 미터 단위의 방문 이벤트에서 설명 가능한 반복 거점을 생성합니다.")}</p>
        </div>
        <div className="deferred">
          <span>HDBSCAN</span>
          <strong>{t("오프라인 Challenger")}</strong>
          <p>{t("도시와 광역 저밀도처럼 밀도가 다른 경우를 동일 입력으로 비교할 후보입니다.")}</p>
        </div>
        <div className="deferred">
          <span>Grid Count</span>
          <strong>Sanity Check</strong>
          <p>{t("군집 알고리즘의 복잡도가 실제 개선을 만드는지 확인하는 최소 기준선입니다.")}</p>
        </div>
      </div>

      <div className="selection-criteria">
        <span>{t("채택 기준")}</span>
        <strong>{t("생활권 생성률 · noise · 복수 거점 · 도시/광역 공정성 · 설명 가능성 · 사람 검토 부담")}</strong>
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
            <strong>
              {selectedRow.service_month} · {selectedMeta.label}
            </strong>
            <p>
              {tf("{dist}km 주행, {basis}으로 생활권을 판단했습니다.", { dist: numberFormatter.format(selectedRow.monthly_total_distance_km), basis: basisLabel(selectedRow.basis_status) })}
              {selectedRow.period_role === "baseline" ? t(" 이 달은 개인 기준선 관찰용이며 Reward·Care 평가에서 제외됩니다.") : t(" 아래 값은 월 보험료가 아니라 상품 검토 근거입니다.")}
            </p>
          </div>
          <div className="score-meter-grid">
            <ScoreMeter label={t("주행거리 점수")} value={selectedRow.mileage_score} helper={t("월별 주행거리가 낮을수록 높음")} />
            <ScoreMeter label={t("생활권 안 안전점수")} value={selectedRow.in_zone_safe_driving_score} helper={t("생활권 안 위험행동이 낮을수록 높음")} />
            <ScoreMeter label={t("생활권 밖 안전점수")} value={selectedRow.out_zone_safe_driving_score} helper={t("생활권 밖 주행이 안정적일수록 높음")} />
            <ScoreMeter label={t("패턴 안정성")} value={selectedRow.pattern_stability_score ?? Math.max(0, 100 - selectedRow.out_zone_pattern_change_risk)} helper={t("개인 기준선 대비 이동 맥락 안정성")} />
          </div>
          <p className="score-legend-copy">
            {t("안전점수의 관측값이 없으면 100점으로 채우지 않고 N/A로 남긴 뒤, 관측된 구성요소의 가중치만 재정규화합니다.")}
          </p>
          <div className="monthly-integrated-formula" aria-label={t("월별 통합 근거점수 산식")}>
            <span>{t("월별 통합 근거점수")}</span>
            <strong>{monthlyIntegratedLabel}</strong>
            <p>{tf("주행거리 {mileage}% + 생활권 안 안전 {inZone}% + 생활권 밖 안전 {outZone}% + 패턴 안정성 {stability}%", { mileage: weights.mileage, inZone: weights.in_zone_safe, outZone: weights.out_zone_safe, stability: weights.pattern_stability })}</p>
            <small>{t("Reward 후보점수와 케어 동시조건은 독립 계산되며, 어느 쪽도 보험료·인수 결정을 자동 확정하지 않습니다.")}</small>
            <div className={`monthly-care-gate ${selectedRow.care_state === "Care Review" ? "active" : ""}`}>
              <b>{t("케어 동시조건")}</b>
              <span>{tf("이동 {mob} · 위험행동 {risk}", { mob: numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0), risk: numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0) })}</span>
              <em>{selectedRow.period_role === "baseline" ? t("기준선") : selectedRow.care_state === "Care Review" ? t("사람 검토 제안") : t("미충족")}</em>
            </div>
          </div>
        </div>
      ) : null}

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
function scatterDots(cx: number, cy: number, count: number, spread: number, seed: number) {
  const n = Math.max(5, Math.min(34, Math.round(count)));
  const out: { x: number; y: number; r: number }[] = [];
  let s = ((seed * 9301 + 49297) % 233280 + 233280) % 233280;
  const rand = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  for (let i = 0; i < n; i += 1) {
    const angle = rand() * Math.PI * 2;
    const radius = Math.sqrt(rand()) * spread;
    out.push({ x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius, r: 1.5 + rand() * 1.7 });
  }
  return out;
}

function GeoLivingZoneCanvas({ driver, snapshot, profile }: { driver: DriverAnnualSummary; snapshot: ZoneSnapshot; profile: DerivedProfile }) {
  if (!snapshot.living_zone.clusters.length) {
    return (
      <div className="no-zone-state">
        <MapPinned size={24} />
        <strong>{t("반복 거점 근거가 충분하지 않습니다")}</strong>
        <p>{t("가짜 중심을 만들지 않고 No Zone으로 유지합니다. Reward와 Care는 판단 보류이며 불이익을 주지 않습니다.")}</p>
      </div>
    );
  }
  const groups = Object.values(groupTrips(snapshot.trip_interpretations)).sort((a, b) => b.count - a.count);
  const home = destinationForType(driver, "home");
  const destinations = groups
    .map((group) => ({ group, destination: destinationForType(driver, group.key) }))
    .filter((item): item is { group: TripGroup; destination: Destination } => Boolean(item.destination) && item.group.key !== "home");
  const visibleDestinations = destinations.slice(0, 6);

  // Agent-named living zones (Option C): put the LLM's life-grounded names onto
  // the map's own legend, matched by role — an out-of-zone node takes a change
  // destination name, an in-zone node takes an in-zone name — with a generic
  // fallback so a mismatch never leaves a node unlabelled.
  const profileZones = driver.mobility_profile?.zones ?? [];
  const inZoneQueue = profileZones.filter((zone) => zone.role === "in_zone").map((zone) => localeText(zone.label_ko, zone.label_en));
  const secondaryQueue = profileZones.filter((zone) => zone.role === "secondary").map((zone) => localeText(zone.label_ko, zone.label_en));
  const changeQueue = profileZones.filter((zone) => zone.role === "change_destination").map((zone) => localeText(zone.label_ko, zone.label_en));
  let inCursor = 0;
  let changeCursor = 0;
  const agentDestLabels = visibleDestinations.map((item) => {
    const outer = item.destination.living_zone_role === "outer";
    if (outer && changeCursor < changeQueue.length) return changeQueue[changeCursor++];
    if (!outer && inCursor < inZoneQueue.length) return inZoneQueue[inCursor++];
    return null;
  });

  // Home-centred radial schematic (not a real map — coordinates are never
  // exposed). The residence sits at the centre with its Core (500m) and Buffer
  // (personal P90) rings; destinations fan out around it: in-zone stops inside
  // the buffer, out-of-zone stops beyond it. This reads as one legible living
  // zone instead of a projected "tadpole".
  const mapWidth = 900;
  const mapHeight = 520;
  const center = { x: mapWidth * 0.45, y: mapHeight * 0.48 };
  const radialP90M = snapshot.living_zone.clusters[0]?.p90_radius_m ?? snapshot.living_zone.buffer.departure_p90_threshold_m;
  const productBufferM = Math.max(500, Math.min(2000, radialP90M));
  const coreRadius = 58;
  const bufferRadius = Math.max(coreRadius + 30, Math.min(150, 64 + productBufferM / 15));

  const destCount = Math.max(1, visibleDestinations.length);
  const arcStart = -Math.PI * 0.82;
  const arcSpan = Math.PI * 1.42;
  const routePath = (point: { x: number; y: number }) => {
    const dx = point.x - center.x;
    const dy = point.y - center.y;
    const midX = center.x + dx * 0.5 - dy * 0.1;
    const midY = center.y + dy * 0.5 + dx * 0.1;
    return `M${center.x} ${center.y} Q${midX} ${midY}, ${point.x} ${point.y}`;
  };
  const destinationViews = visibleDestinations.map((item, index) => {
    const outer = item.destination.living_zone_role === "outer";
    const angle = destCount === 1 ? -Math.PI * 0.3 : arcStart + (index / (destCount - 1)) * arcSpan;
    const dist = outer ? bufferRadius + 78 + (index % 3) * 26 : bufferRadius * 0.58;
    return {
      ...item,
      outer,
      point: {
        x: Math.max(48, Math.min(mapWidth - 48, center.x + Math.cos(angle) * dist)),
        y: Math.max(64, Math.min(mapHeight - 64, center.y + Math.sin(angle) * dist))
      }
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
      {[bufferRadius + 108, bufferRadius + 48].map((r) => (
        <circle key={`guide-${r}`} className="geo-guide-ring" cx={center.x} cy={center.y} r={r} />
      ))}
      <g className="geo-scatter" aria-hidden="true">
        {scatterDots(center.x, center.y, 26, coreRadius * 0.85, 7).map((d, i) => (
          <circle key={`sc-home-${i}`} cx={d.x} cy={d.y} r={d.r} />
        ))}
        {destinationViews.map(({ group, point, outer }, gi) =>
          scatterDots(point.x, point.y, group.count, outer ? 27 : 19, gi * 53 + 11).map((d, i) => (
            <circle key={`sc-${gi}-${i}`} className={outer ? "outer" : ""} cx={d.x} cy={d.y} r={d.r} />
          ))
        )}
      </g>
      <text className="geo-title" x="42" y="42">{t("생활권 판단 지도")}</text>
      <text className="geo-subtitle" x="42" y="63">{t("개념도(축척 아님) · 중심권 500m · 완충권은 개인 P90 반영(최대 2km)")}</text>

      <circle cx={center.x} cy={center.y} r={bufferRadius + 6} fill="url(#zoneGlow)" />
      <g className="geo-core-ring">
        <circle cx={center.x} cy={center.y} r={bufferRadius} />
        <circle cx={center.x} cy={center.y} r={coreRadius} />
        <text x={center.x} y={center.y - bufferRadius - 12} textAnchor="middle">{t(snapshot.living_zone.clusters[0]?.label_ko ?? "반복 거점 A")}</text>
      </g>

      {snapshot.living_zone.clusters.slice(1).map((cluster, index) => {
        const secAngle = Math.PI * 0.3;
        const secDist = bufferRadius + 140;
        const cx = Math.min(mapWidth - 96, center.x + Math.cos(secAngle) * secDist);
        const cy = Math.min(mapHeight - 78, center.y + Math.sin(secAngle) * secDist);
        const secBuffer = Math.max(40, Math.min(78, cluster.p90_radius_m / 16));
        return (
          <g key={cluster.cluster_id} className="geo-cluster">
            <g className="geo-scatter" aria-hidden="true">
              {scatterDots(cx, cy, 16, secBuffer * 0.78, index * 71 + 29).map((d, i) => (
                <circle key={`scs-${index}-${i}`} cx={d.x} cy={d.y} r={d.r} />
              ))}
            </g>
            <circle cx={cx} cy={cy} r={secBuffer} />
            <circle cx={cx} cy={cy} r={Math.min(coreRadius - 6, secBuffer - 12)} />
            <text x={cx} y={cy - secBuffer - 9} textAnchor="middle">{secondaryQueue[index] ?? (cluster.label_ko ? t(cluster.label_ko) : tf("반복 거점 {letter}", { letter: String.fromCharCode(66 + index) }))}</text>
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

function ScoreMeter({ label, value, inverse = false, helper }: { label: string; value: number | null; inverse?: boolean; helper?: string }) {
  if (value === null || !Number.isFinite(value)) {
    return (
      <div className="score-meter unavailable">
        <span>{translateText(label)}</span>
        <strong>N/A</strong>
        {helper ? <small>{translateText(helper)}</small> : null}
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
      {helper ? <small>{translateText(helper)}</small> : null}
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

function deriveEvidenceProfile(driver: DriverAnnualSummary, snapshot: ZoneSnapshot, selectedRow?: MonthlyEvidence): DerivedProfile {
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
      summary: tf("{month}은 반복 거점 근거가 없어 No Zone입니다. {obs} Reward·Care는 보류하며 위치로 불이익을 주지 않습니다.", { month: snapshot.service_month, obs: riskObservation }),
      topDestinations: [],
      outerPattern: t("생활권 안·밖 미분류"),
      riskPattern: t("No Zone · 상품 판단 보류"),
      repeatRate: 0,
      outZoneRatio: 0,
      riskEvents,
      nightTrips,
      newDestinationTrips
    };
  }
  const outZoneRatio = snapshot.monthly_evidence.out_zone_distance_ratio;
  const riskScore = snapshot.scores.out_zone_pattern_change_risk;

  let headline = t("생활권 안 반복 주행");
  if (selectedRow?.care_state === "Care Review") headline = t("이동 맥락과 위험행동의 동시변화 검토");
  else if (riskScore >= careReviewRiskThreshold) headline = t("선택 월 이동 맥락 변화 관찰");
  else if (riskEvents > 0 && riskScore < preferredRiskCeiling) headline = t("위험행동은 있으나 변화위험은 낮음");
  else if (outZoneRatio > 0.25 && repeatRate > 0.55 && riskEvents <= trips.length * 0.2) headline = t("반복 외부 목적지 안정");
  else if (newDestinationTrips > 0 && outZoneRatio > 0.15) headline = t("신규 외부 목적지 관찰");
  else if (driver.persona_type === "multi_zone") headline = t("복수 생활권 반복 이동 관찰");
  else if (driver.persona_type === "wide_area_safe") headline = t("광역 반복 외부 이동 관찰");

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

function matchesCaseFilter(option: DriverOption, filter: string) {
  if (filter === "all") return true;
  if (filter === "Reward") return option.reward_state === "Reward";
  if (filter === "Care Review") return option.care_state === "Care Review";
  if (filter === "Hold") return option.reward_state === "Hold" || option.care_state === "Hold";
  return false;
}

function zoneIsReady(status: string | undefined) {
  return status === "available" || status === "ready";
}

const personaNameRegistry = new Map<string, string>();

export function registerPersonaNames(options: Array<{ customer_id: string; label: string }>) {
  options.forEach((option) => {
    if (option.label) personaNameRegistry.set(option.customer_id, option.label);
  });
}

function personaName(customerId: string) {
  return personaNameRegistry.get(customerId) ?? `합성 시니어 ${String(personaIndex(customerId) + 1).padStart(2, "0")}`;
}

function personaIndex(customerId: string) {
  const matched = customerId.match(/(\d+)$/);
  return matched ? Math.max(0, Number(matched[1]) - 1) : 0;
}

function caseNo(customerId: string) {
  return tf("가상 {num}", { num: String(personaIndex(customerId) + 1).padStart(2, "0") });
}

function personaAge(customerId: string) {
  const ages = [72, 76, 69, 81, 74, 78, 71, 83, 75, 80, 77, 73, 82, 70, 79, 84, 76, 72, 68, 81, 75, 79, 73, 85, 77, 74, 82, 71, 78, 80];
  return ages[personaIndex(customerId)] ?? 76;
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
  if (driver.care_state === "Care Review") return t("담당자가 근거 확인 후 비징벌적 Care 여부 검토");
  if (driver.reward_state === "Reward") return t("Reward 후보 근거 확인");
  if ((selectedRow?.mobility_change_index_pct ?? 0) > 0) return t("변화 추세 관찰 · 자동 조치 없음");
  return t("Neutral 유지");
}

function personaTone(type: string) {
  if (type === "mobility_risk_cochange" || type === "in_zone_risky") return "risk";
  if (type === "mobility_change_safe") return "care";
  if (type === "multi_zone" || type === "stable_reward" || type === "wide_area_safe") return "safe";
  return "base";
}

function personaNarrative(type: string) {
  const text: Record<string, string> = {
    stable_reward: "짧은 반복 이동과 안정운전이 함께 나타나는 Reward 기준군",
    in_zone_risky: "멀리 가지 않아도 생활권 안 급감속·과속이 누적되는 저주행 위험군",
    mobility_change_safe: "이동 맥락만 달라지고 위험행동은 그대로여서 Care를 제안하면 안 되는 음성 대조군",
    mobility_risk_cochange: "같은 평가월에 이동과 위험행동이 함께 달라져 사람 검토가 필요한 핵심군",
    multi_zone: "멀리 떨어진 복수 반복 거점을 하나의 큰 원으로 합치지 않아야 하는 검증군",
    wide_area_safe: "이동반경이 넓어도 안전행동을 유지해 Outer 자체를 감점하지 않아야 하는 공정성 검증군"
  };
  return t(text[type] ?? "월별 주행 근거에 따라 연간 판단이 달라지는 사례군");
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
