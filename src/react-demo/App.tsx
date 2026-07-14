import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  FileText,
  MapPinned,
  RefreshCcw,
  Route,
  Search,
  ShieldCheck,
  UserRound
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { demoApi } from "./api";
import { AlgorithmLabPanel } from "./AlgorithmLab";
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
  PersonaSummary,
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
  stable_local_safe: "안정적 근거리 안전형",
  low_mileage_risky: "저주행 위험행동형",
  safe_multi_hub: "복수 거점 안전형",
  safe_wide_area: "광역 이동 안전형",
  mobility_change_only: "이동 변화 단독형",
  mobility_risk_cochange: "이동·위험행동 동시변화형"
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
  return decisionStateKo[value] ?? value;
}

function tierLabelKo(reward?: string | null, care?: string | null) {
  if (care === "Care Review") return "예방 케어";
  if (reward === "Hold" || care === "Hold") return "판단 보류";
  if (reward === "Reward") return "우대";
  return "기본";
}

const dynamicTextTranslations: Record<string, string> = {
  Standard: "Neutral",
  Favorable: "Reward",
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
  return personaTypeLabels[type] ?? translateText(type);
}

function destinationTypeLabel(type: string) {
  return destinationTypeLabels[type] ?? translateText(type);
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
    return <ScreenState title="시뮬레이션 근거 연결 중" detail="60명 합성 코호트와 14개월 판단 근거를 불러오는 중입니다." />;
  }

  if (directoryState === "error" || !directory) {
    return <ScreenState title="데모 데이터를 열 수 없습니다" detail={errorMessage} />;
  }

  return (
    <div className="workbench">
      <header className="app-header">
        <div className="brand-block">
          <div>
            <p className="eyebrow">FOURSURE · MASIL · GAIP Insurance Innovation Competition 2026</p>
            <h1>시니어 생활권 기반 보험 설계 대시보드</h1>
            <p>한국 마일리지 특약을 참조하되, 반복 생활권과 운전행동의 변화를 분리해 혜택과 예방 케어 검토 근거를 제안합니다.</p>
          </div>
        </div>
        <div className="header-actions">
          <div className="page-switch" aria-label="페이지 전환">
            <button
              type="button"
              className={pageMode === "overview" ? "active" : ""}
              onClick={() => setPageMode("overview")}
              aria-current={pageMode === "overview" ? "page" : undefined}
            >
              설계구조
            </button>
            <button
              type="button"
              className={pageMode === "profiles" ? "active" : ""}
              onClick={() => setPageMode("profiles")}
              aria-current={pageMode === "profiles" ? "page" : undefined}
            >
              프로필 분석
            </button>
          </div>
          <div className="contract-box">
            <span>데모 범위</span>
            <strong>합성 시뮬레이션 · 사람 검토 지원</strong>
            <small>2개월 기준선 + 12개월 평가 · 실제 요율 아님</small>
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
    <main className="overview-page" aria-label="상품 설계구조 화면">
      <OverviewComparisonPanel directory={directory} />
      {rules ? <ScenarioControlPanel rules={rules} onChange={onRulesChange} /> : null}
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
  reward_discount_rate_pct: 3,
  candidate_discount_cap_pct: 45
};

function ScenarioControlPanel({ rules, onChange }: { rules: ProductRules; onChange: (rules: ProductRules) => void }) {
  const normalized = normalizeProductWeights(rules.weights);
  const updateWeight = (key: keyof ProductRules["weights"], value: number) => {
    onChange({ ...rules, weights: { ...rules.weights, [key]: value } });
  };
  const updateRule = (key: keyof ProductRules, value: number) => {
    onChange({ ...rules, [key]: value });
  };
  const weightRows: Array<{ key: keyof ProductRules["weights"]; label: string }> = [
    { key: "mileage", label: "주행거리" },
    { key: "in_zone_safe", label: "생활권 안 안전" },
    { key: "out_zone_safe", label: "생활권 밖 안전" },
    { key: "pattern_stability", label: "패턴 안정성" }
  ];

  const presets: Array<{ id: string; label: string; hint: string; rules: ProductRules }> = [
    {
      id: "kr",
      label: "국내 기준 (기본)",
      hint: "국내 수상안 PoC 설정 — 30:30:20:20 · 우대 75점/9개월",
      rules: referenceProductRules
    },
    {
      id: "intl-conservative",
      label: "국제 예시 A · 보수적",
      hint: "혜택 문턱을 높이고 케어를 더 민감하게 보는 시장 가정",
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
      label: "국제 예시 B · 광역 시장",
      hint: "장거리 이동이 일상인 시장 가정 — 이동 변화 허용 폭 확대",
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
    <section className="panel scenario-control-panel" aria-label="상품 규칙 민감도 설정">
      <div className="panel-head">
        <div>
          <p className="eyebrow">상품 규칙 SANDBOX</p>
          <h2>상품 담당자가 후보 가중치와 임계치를 바꾸면 동일한 60명 결과가 즉시 다시 계산됩니다</h2>
        </div>
        <button type="button" className="sandbox-reset" onClick={() => onChange(referenceProductRules)}>30:30:20:20 복원</button>
      </div>
      <div className="sandbox-presets" role="group" aria-label="시장 기준 프리셋">
        <span className="sandbox-presets-title">기준 프리셋 — 시장이 달라도 같은 엔진이 다시 계산합니다</span>
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
          <RuleNumber label="Reward 점수" value={rules.reward_score_threshold} min={50} max={95} onChange={(value) => updateRule("reward_score_threshold", value)} />
          <RuleNumber label="Reward 충족월" value={rules.reward_required_months} min={1} max={12} suffix="개월" onChange={(value) => updateRule("reward_required_months", value)} />
          <RuleNumber label="최소 데이터" value={rules.minimum_data_coverage_pct} min={50} max={100} suffix="%" onChange={(value) => updateRule("minimum_data_coverage_pct", value)} />
          <RuleNumber label="이동 변화" value={rules.care_mobility_change_threshold} min={0} max={100} suffix="%" onChange={(value) => updateRule("care_mobility_change_threshold", value)} />
          <RuleNumber label="위험행동 변화" value={rules.care_risky_behavior_threshold} min={0} max={100} suffix="%" onChange={(value) => updateRule("care_risky_behavior_threshold", value)} />
        </div>
      </div>
      <p className="sandbox-footnote">
        가중치 합계는 계산 시 100%로 재정규화되며, 모든 값은 시뮬레이션 후보입니다. 알고리즘 파라미터(eps·최소
        방문일수)는 결정 주체가 달라 이 화면이 아니라 <b>알고리즘 실험실</b> 탭에서 비교합니다.
      </p>
    </section>
  );
}

function RuleNumber({
  label,
  value,
  min,
  max,
  suffix = "점",
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
  const donutBackground = `conic-gradient(#116466 0 ${p1}%, #8aa6a0 ${p1}% ${p2}%, #c96f4a ${p2}% ${p3}%, #dfe8e5 ${p3}% 100%)`;
  const avgRateDelta = summary.avg_proposed_discount_rate_pct - summary.avg_existing_discount_rate_pct;

  return (
    <section className="panel comparison-overview" aria-label="전체 비교 대시보드">
      <div className="panel-head">
        <div>
          <p className="eyebrow">전체 비교</p>
          <h2>같은 60명·14개월 합성 데이터로 기존 마일리지 기준과 제안 산식을 비교합니다</h2>
        </div>
        <span className="count-badge">기준선 2개월 + 평가 12개월 · {summary.customer_count}명</span>
      </div>

      <div className="judge-takeaway" aria-label="핵심 평가 포인트">
        <div>
          <span>문제</span>
          <strong>기존 마일리지는 저주행 여부는 보지만 이동 맥락의 차이는 설명하기 어렵습니다</strong>
          <p>같은 주행거리 안에서도 안정적 반복 이동과 갑작스러운 이동·위험행동 동시변화를 구분할 근거가 부족합니다.</p>
        </div>
        <div>
          <span>제안 차별점</span>
          <strong>거리 혜택과 예방 케어 검토를 서로 독립된 두 축으로 설계합니다</strong>
          <p>안전운전은 혜택(Reward)으로 인정하고, 같은 달 이동 변화와 위험행동 변화가 함께 나타날 때만 사람에게 예방 케어 검토를 제안합니다.</p>
        </div>
        <div>
          <span>검증 결과</span>
          <strong>도심·교외·광역 저밀도 환경에서도 동일한 안전 원칙을 검증합니다</strong>
          <p>결과는 합성 시나리오의 일관성과 예외 처리를 보여주는 것이며, 실제 사고감소·손해율·확정 요율을 뜻하지 않습니다.</p>
        </div>
      </div>

      <div className="comparison-ledger" aria-label="기존 마일리지와 제안 산식 비교표">
        <div className="ledger-head">
          <span>비교 항목</span>
          <strong>기존 마일리지 산식 · 국내 기준</strong>
          <strong>마실 제안 산식 · 시뮬레이션 후보</strong>
        </div>
        <ComparisonLedgerRow
          label="판단 기준"
          legacy="연간 주행거리와 차종으로 할인율 결정"
          proposed="주행거리 + 생활권 안/밖 안전 + 패턴 안정성"
        />
        <ComparisonLedgerRow
          label="같은 저주행 구간 처리"
          legacy="같은 거리구간이면 생활권 변화와 관계없이 같은 할인율"
          proposed="혜택은 안전 점수로, 예방 케어는 같은 달 두 변화지표의 동시 충족 조건으로 별도 계산"
        />
        <ComparisonLedgerRow
          label="연간 할인 계산"
          legacy="거리구간 할인율을 그대로 적용"
          proposed="한국 할인표를 참조하고 후보 가중치·임계치의 민감도만 비교"
        />
        <ComparisonLedgerRow
          label="설명 가능성"
          legacy="조정 근거가 ‘적게 탔다’에 머물러 설명력이 약함"
          proposed="비식별 반복 거점, 월별 근거, Reason Code와 사람 검토 기록 제공"
        />
      </div>

      <div className="overview-evidence-grid">
        <div className="decision-donut-card">
          <span>제안 산식의 판정 등급 구조</span>
          <div className="decision-donut-wrap">
            <div className="decision-donut" style={{ background: donutBackground }}>
              <div>
                <strong>3등급</strong>
                <small>연간 판정 기준</small>
              </div>
            </div>
            <div className="decision-donut-legend">
              <DecisionLegend label={`우대 ${preferredCount}명`} detail="생활권 안정형" className="preferred" />
              <DecisionLegend label={`기본 ${standardCount}명`} detail="변화 낮음" className="standard" />
              <DecisionLegend label={`예방 케어 ${careCount}명`} detail="위험변화 관찰 · 사람 검토" className="care" />
              {holdCount ? (
                <DecisionLegend label={`판단 보류 ${holdCount}명`} detail="근거 부족 · 불이익 없음" className="hold" />
              ) : null}
            </div>
          </div>
          <p className="portfolio-footnote">
            국내 수상안의 3등급 표기를 유지합니다. 내부 계산은 혜택(Reward)과 케어 검토(Care)를 독립된 두 축으로
            나눠 수행하므로, 기준이 다른 시장에서도 같은 엔진이 등급을 다시 계산할 수 있습니다.
          </p>
        </div>

        <div className="simulation-result-card">
          <span>국내 기준 A/B 시뮬레이션 · 합성 60명</span>
          <strong>총액을 맞춰 끼운 값이 아니라, 두 산식을 각각 계산한 결과입니다</strong>
          <p>
            동일한 60명(6개 운전자 유형 × 10명, 3개 이동환경)의 연간 주행 데이터를 기존 마일리지 산식과 제안 통합
            산식에 각각 넣어 비교했습니다. 실제 계약보험료를 확정하지 않은 단계이므로, 평균 할인율과
            우대·기본·예방 케어 판정 구조를 중심으로 검증합니다.
          </p>
          <div className="budget-compare-grid no-money">
            <div>
              <span>기존 평균 할인율</span>
              <strong>{percent(summary.avg_existing_discount_rate_pct)}</strong>
              <small>연간 주행거리 구간 기준</small>
            </div>
            <div>
              <span>제안 평균 할인율</span>
              <strong>{percent(summary.avg_proposed_discount_rate_pct)}</strong>
              <small>4개 지표 통합점수 기준</small>
            </div>
            <div>
              <span>평균 할인율 변화</span>
              <strong>{signedPercentPoint(avgRateDelta)}</strong>
              <small>실제 계약보험료 없이 비교 가능한 비율 차이</small>
            </div>
          </div>
          <p className="portfolio-footnote">
            합성 시뮬레이션 결과입니다. 실제 요율·인수·케어 결정은 계리·상품·심사 권한자의 검토 없이 확정하지
            않습니다. 기준을 다른 시장 값으로 바꾸면 아래 상품 Sandbox가 같은 60명을 즉시 다시 계산합니다.
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
    { value: "all", label: "전체" },
    { value: "Reward", label: "우대" },
    { value: "Care Review", label: "케어" },
    { value: "Hold", label: "보류" }
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
    <aside className="case-rail" aria-label="가상 시니어 사례 목록">
      <div className="rail-heading">
        <p className="eyebrow">가상 사례</p>
        <h2>{options.length}명 사례</h2>
      </div>
      <label className="search-box">
        <Search size={15} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="유형·환경·상태 검색" />
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
                  {option.environment_display_name_ko ?? "이동환경"} · {changeTag}
                </small>
              </span>
              <span className="case-state-pills">
                <em className={`risk-pill ${decisionClass(option.reward_state ?? "Neutral").className}`}>{stateLabelKo(option.reward_state ?? "Neutral")}</em>
                {option.care_state === "Care Review" ? <em className="risk-pill care">케어</em> : null}
                {option.reward_state === "Hold" || option.care_state === "Hold" ? <em className="risk-pill hold">보류</em> : null}
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
    return <InspectorState title="사례 선택 대기" detail="좌측 사례를 선택하면 Reward·Care 검토 요약이 표시됩니다." />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const reward = decisionClass(driver.reward_state ?? comparison.annual_decision_signal);
  const selectedCare = selectedRow?.care_state ?? "None";
  const care = decisionClass(selectedCare);
  const reviewHeadline = selectedCare === "Care Review"
    ? "이동 맥락과 위험행동의 동시변화 검토"
    : selectedCare === "Hold"
      ? "근거 부족 · 판단 보류"
      : selectedCare === "Observation"
        ? "개인 기준선 관찰 · Care 평가 제외"
        : profile?.headline;
  const decisionReasons = profile
    ? [profile.headline, profile.outerPattern, profile.riskPattern]
    : driver.annual_score.annual_reason_codes.slice(0, 3).map((code) => reasonLabels[code] ?? code);

  return (
    <section className={`decision-summary-card ${driverState === "loading" ? "is-loading" : ""}`} aria-label="검토 제안 요약">
      <div className="summary-identity">
        <p className="eyebrow">검토 제안 요약</p>
        <h2>{personaName(driver.customer_id)}</h2>
        <span>{driver.environment_display_name_ko ?? personaResidence(driver)} · {personaTypeLabel(driver.persona_type)}</span>
      </div>

      <div className="summary-verdict">
        <span>선택 월 근거</span>
        <strong>{reviewHeadline ?? decisionReasons[0]}</strong>
        <p>{decisionReasons.slice(1, 3).join(" ")}</p>
      </div>

      <div className="summary-decision-stack">
        <div className={`risk-score-block ${reward.className}`}>
          <span>연간 혜택 축</span>
          <strong>{stateLabelKo(reward.label)}</strong>
          <b>후보점수 {numberFormatter.format(driver.annual_score.annual_senior_safe_mileage_score)}점</b>
        </div>

        <div className={`premium-delta-block ${care.className}`}>
          <span>선택 월 케어 축</span>
          <strong>{stateLabelKo(selectedCare === "None" ? "미충족" : selectedCare)}</strong>
          <small>같은 달 이동 변화와 위험행동 변화가 함께 있을 때만</small>
        </div>

        <div className="summary-action">
          <span>근거 상태</span>
          <strong>{zoneIsReady(driver.zone_status) ? "생활권 근거 사용 가능" : "근거 부족 · 불이익 없음"}</strong>
          <small>{selectedRow ? `데이터 커버리지 ${numberFormatter.format(selectedRow.data_coverage_pct ?? 0)}%` : driver.evidence_status ?? "simulated"}</small>
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
    return <InspectorState title="판단 과정 대기" detail="사례를 선택하면 할인 보정 과정이 표시됩니다." />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const mobilityChange = selectedRow?.mobility_change_index_pct ?? selectedRow?.out_zone_pattern_change_risk ?? 0;
  const riskyBehaviorChange = selectedRow?.risky_behavior_change_index_pct ?? 0;
  const careGate = selectedRow?.care_state === "Care Review";
  const zoneBasis = !zoneIsReady(driver.zone_status) || !zoneMap?.snapshot.living_zone.clusters.length
    ? "No Zone · 판단 보류"
    : zoneMap
      ? `Core 500m · P90 ${Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("en-US")}m`
      : "생활권 산출 중";
  const annualTierKo = tierLabelKo(driver.reward_state, driver.care_state);
  const steps = [
    {
      title: "기존 기준선",
      value: translateText(comparison.existing_matched_tier_label),
      detail: "연간 주행거리와 차종만 반영하는 비교 기준",
      icon: Route
    },
    {
      title: "생활권 생성",
      value: zoneBasis,
      detail: "기준선 2개월의 반복 목적지와 이동 반경 반영",
      icon: MapPinned
    },
    {
      title: `${selectedRow?.service_month ?? selectedMonth + "월"} 변화`,
      value: `이동 변화 ${numberFormatter.format(mobilityChange)}% · 위험행동 ${numberFormatter.format(riskyBehaviorChange)}%`,
      detail: careGate ? "같은 달 두 변화가 함께 임계치를 넘어 예방 케어 검토" : "한 지표만으로는 케어를 제안하지 않음",
      icon: Activity
    },
    {
      title: "연간 판단",
      value: `${percent(comparison.proposed_discount_rate_pct)} · ${annualTierKo}`,
      detail: "판정 근거는 사람이 최종 검토하며 자동 확정하지 않음",
      icon: AlertTriangle
    }
  ];

  return (
    <section className="decision-process-frame" aria-label="상품 근거와 사람 검토 과정">
      <div className="decision-process-copy">
        <p className="eyebrow">판단 과정</p>
        <h2>같은 저주행이라도 생활권 밖 위험변화가 있으면 다른 결론이 납니다</h2>
        <p>
          생활권 밖 이동 자체는 중립입니다. 혜택(우대)은 안전운전 근거로 계산하고, 같은 달 이동 맥락과
          위험행동이 동시에 달라질 때만 사람에게 예방 케어 검토를 제안합니다.
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
  if (!driver) return <InspectorState title="생활권 지도 대기" detail="사례를 선택하면 반복 거점과 상품 구간이 표시됩니다." />;

  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;

  return (
    <section className="decision-map-panel" aria-label="생활권 판단 지도">
      <div className="decision-section-head">
        <div>
          <p className="eyebrow">생활권 판단 지도</p>
          <h2>{zoneIsReady(driver.zone_status) ? "자택 중심 생활권과 최근 변화 목적지" : "생활권 미확정 · 반복 거점 근거 부족"}</h2>
        </div>
        {profile && zoneMap && zoneIsReady(driver.zone_status) ? (
          <div className="map-kpis">
            <span>개인 P90 {Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("ko-KR")}m</span>
            <span>생활권 밖 {percent(profile.outZoneRatio * 100)} · 감점 0</span>
            <span>위험행동 {profile.riskEvents}건</span>
          </div>
        ) : null}
      </div>

      <div className="map-stage">
        {zoneState === "loading" || !zoneMap || !profile ? (
          <p>생활권 지도를 불러오는 중입니다.</p>
        ) : !zoneIsReady(driver.zone_status) ? (
          <div className="no-zone-state">
            <MapPinned size={24} />
            <strong>반복 거점 근거가 충분하지 않습니다</strong>
            <p>가짜 중심을 만들지 않고 No Zone으로 유지합니다. Reward와 Care는 판단 보류이며 불이익을 주지 않습니다.</p>
          </div>
        ) : (
          <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
        )}
      </div>

      <div className="map-legend-row">
        <span><i className="legend-home" />반복 거점</span>
        <span><i className="legend-normal" />중심권 500m</span>
        <span><i className="legend-out" />완충권 · 개인 P90 반영</span>
        <span><i className="legend-risk" />생활권 밖 · 위치만으로 감점 없음</span>
        <b>{zoneMap?.snapshot.service_month ?? `${selectedMonth}월`} 선택 근거</b>
      </div>
      <div className="map-route-legend" aria-label="경로선 색 안내">
        <b>경로선(도식) = 자택→목적지 연결이며 색은 선택 월의 해석입니다:</b>
        <span className="rl-stable"><i />생활권 안</span>
        <span className="rl-candidate"><i />반복 외부 후보</span>
        <span className="rl-safeout"><i />생활권 밖 안정 · 중립</span>
        <span className="rl-risk"><i />동시변화 검토</span>
      </div>
      <p className="map-formula-note">완충권 = max(500m, min(개인 P90, 2km)) — 군집이 만들어진 뒤 적용하는 상품 인정 반경입니다.</p>
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
    { key: "Overview", label: "요약" },
    { key: "Monthly Pattern", label: "월별 패턴" },
    { key: "Risk Signals", label: "위험 신호" },
    { key: "Premium Simulation", label: "요율 Sandbox" },
    { key: "Algorithm Lab", label: "알고리즘 실험실" },
    { key: "Report", label: "리포트" }
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
            <InsightCard title="분류 근거" value={profile?.headline ?? "월별 근거 확인"} detail={profile?.summary ?? translateText(driver.care_context.message_focus)} />
            <InsightCard title="생활권 변화" value={`이동 ${numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0)} · 위험 ${numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0)}`} detail={`${selectedRow.service_month}: 같은 달 동시조건 적용`} />
            <InsightCard title="상품 제안" value={`연간 ${stateLabelKo(driver.reward_state ?? "Neutral")} · 월 케어 ${stateLabelKo(selectedRow.care_state ?? "None")}`} detail="연간 혜택과 선택 월 케어를 독립 계산한 뒤 사람이 검토합니다." />
          </div>
        ) : null}

        {activeTab === "Monthly Pattern" ? (
          <MonthlyPatternChart rows={rows} selectedMonth={selectedMonth} onSelectMonth={onSelectMonth} />
        ) : null}

        {activeTab === "Risk Signals" && driver && selectedRow ? (
          <div className="risk-signal-grid">
            <ScoreMeter label="주행거리 점수" value={selectedRow.mileage_score} helper="월별 주행거리를 연환산해 저주행일수록 높게 계산" />
            <ScoreMeter label="생활권 안 안전점수" value={selectedRow.in_zone_safe_driving_score} helper="생활권 안 급감속·과속·야간 비율이 낮을수록 높음" />
            <ScoreMeter label="생활권 밖 안전점수" value={selectedRow.out_zone_safe_driving_score} helper="생활권 밖 위험행동과 야간 비율이 낮을수록 높음" />
            <ScoreMeter label="패턴 안정성" value={selectedRow.pattern_stability_score ?? Math.max(0, 100 - selectedRow.out_zone_pattern_change_risk)} helper="개인 기준선 대비 이동 맥락의 안정성" />
            <div className={`care-gate-card ${selectedRow.care_state === "Care Review" ? "active" : ""}`}>
              <span>케어 동시조건</span>
              <strong>이동 {numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0)} + 위험행동 {numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0)}</strong>
              <small>{selectedRow.care_state === "Care Review" ? "사람 검토 제안" : "케어 자동 제안 없음"}</small>
            </div>
            <div className="reason-chip-row">
              {[...driver.annual_score.annual_reason_codes, ...selectedRow.reason_codes].slice(0, 8).map((code) => (
                <span key={`${code}-${selectedMonth}`}>{reasonLabels[code] ?? code}</span>
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
            <strong>리포트 입력 근거</strong>
            <p>{profile.summary}</p>
            <span>우측 Human Review 패널에서 근거 초안을 생성합니다. 설명문은 최종 보험료·인수·Care 결정을 대신하지 않습니다.</span>
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
            <span>{row.month}월</span>
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
        <span>기존 마일리지 기준 · 국내</span>
        <strong>{percent(existingRate)}</strong>
        <i><b style={{ width: `${(existingRate / maxRate) * 100}%` }} /></i>
        <small>적용 시 {krwWithUsd(comparison.existing_net_premium_krw)}</small>
      </div>
      <div>
        <span>마실 제안 산식 · 후보</span>
        <strong>{percent(proposedRate)}</strong>
        <i><b style={{ width: `${(proposedRate / maxRate) * 100}%` }} /></i>
        <small>적용 시 {krwWithUsd(comparison.proposed_net_premium_krw)}</small>
      </div>
      <p>
        기준 보험료 {krwWithUsd(comparison.base_premium_krw)} 가정의 합성 비교입니다. 달러 표기는 해외 심사위원의
        규모 비교를 위한 예시 환율(1$≈₩{DEMO_USD_RATE.toLocaleString("ko-KR")}) 환산이며, 실제 계약보험료·해외
        요율을 의미하지 않습니다.
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

  if (!driver) return <aside className="decision-panel"><InspectorState title="Human Review 패널" detail="사례를 선택하면 근거와 검토 작업이 표시됩니다." /></aside>;

  const comparison = driver.ab_comparison;
  const decision = decisionClass(driver.reward_state ?? comparison.annual_decision_signal);
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const selectedCare = selectedRow?.care_state ?? "None";
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot, selectedRow) : null;
  const reviewHeadline = selectedCare === "Care Review"
    ? "이동 맥락과 위험행동의 동시변화 검토"
    : selectedCare === "Hold"
      ? "근거 부족 · 판단 보류"
      : selectedCare === "Observation"
        ? "개인 기준선 관찰 · Care 평가 제외"
        : profile?.headline;
  const xaiReasons = topXaiReasons(driver, zoneMap, selectedMonth);
  const rateDelta = comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct;
  const generate = async () => {
    setState("streaming");
    setMarkdown("");
    setError("");
    setProgress("월별 주행 근거를 리포트 API로 전송 중");
    try {
      let next = "";
      await demoApi.streamMonthlyReport(driver.customer_id, selectedMonth, (chunk) => {
        next += chunk;
        setProgress(`생성 중: ${latestReportSection(next)}`);
        setMarkdown(next);
      }, rules ?? undefined);
      setProgress("리포트 생성 완료");
      setState("ready");
    } catch (reportError) {
      setState("error");
      setError(reportError instanceof Error ? reportError.message : "리포트 생성에 실패했습니다");
    }
  };

  return (
    <aside className={`decision-panel ${loading ? "is-loading" : ""} ${markdown ? "has-report" : ""}`} aria-label="사람 검토 패널">
      <div className="decision-panel-head">
        <p className="eyebrow">HUMAN REVIEW</p>
        <h2>검토 제안</h2>
        <em className={`decision ${decision.className}`}>{stateLabelKo(decision.label)}</em>
      </div>

      <div className="decision-money-stack">
        <div>
          <span>기존 마일리지 기준</span>
          <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
          <small>{translateText(comparison.existing_matched_tier_label)}</small>
        </div>
        <div>
          <span>마실 제안 후보</span>
          <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
          <small>통합점수 {numberFormatter.format(comparison.annual_senior_safe_mileage_score)}점</small>
        </div>
        <div className="money-delta">
          <span>후보 차이</span>
          <strong>{signedPercentPoint(rateDelta)}</strong>
          <small>후보 민감도 · 확정 요율 아님</small>
        </div>
      </div>

      <div className="decision-reason-box">
        <span>검토 근거</span>
        <strong>{translateText(reviewHeadline ?? driver.care_context.product_role)}</strong>
        <p>{translateText(profile?.summary ?? driver.care_context.message_focus)}</p>
      </div>

      <div className="xai-inspector" aria-label="Reason Code evidence">
        <span>XAI 판단 근거 · {zoneMap?.snapshot.service_month ?? selectedMonth + "월"}</span>
        {xaiReasons.map((reason) => (
          <div key={reason.label}>
            <strong>{reason.label}</strong>
            <i><b style={{ width: `${reason.width}%` }} /></i>
            <em>{reason.detail}</em>
          </div>
        ))}
      </div>

      <div className="review-state-box" aria-label="현재 화면의 사람 검토 상태">
        <div>
          <span>연간 혜택</span>
          <strong>{stateLabelKo(driver.reward_state ?? "Neutral")}</strong>
        </div>
        <div>
          <span>선택 월 케어</span>
          <strong>{stateLabelKo(selectedCare)}</strong>
        </div>
        <div>
          <span>모델</span>
          <strong title={driver.model_version ?? "masil-gaip-simulation/v1"}>합성 시뮬레이션 엔진 v1</strong>
        </div>
      </div>

      <label className="review-note-field">
        <span>담당자 메모</span>
        <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder="승인·보류 이유 또는 추가 확인사항" />
      </label>
      <div className="review-actions">
        <button type="button" className={reviewDecision === "approved" ? "active approve" : ""} onClick={() => setReviewDecision("approved")}>근거 확인</button>
        <button type="button" className={reviewDecision === "requested" ? "active request" : ""} onClick={() => setReviewDecision("requested")}>추가근거 요청</button>
        <button type="button" className={reviewDecision === "held" ? "active hold" : ""} onClick={() => setReviewDecision("held")}>판단 보류</button>
      </div>
      <p className="review-audit-line">
        {reviewDecision === "pending"
          ? "검토 전 · AI 제안은 실제 결정에 반영되지 않음 · 저장되지 않은 데모 상태"
          : reviewDecision === "approved"
            ? "현재 화면에서 근거 확인 표시 · 저장되지 않음 · 실제 상품 결정은 별도 권한자 승인 필요"
            : reviewDecision === "requested"
              ? "현재 화면에서 추가근거 요청 표시 · 저장되지 않음 · 자동 판단 없음"
              : "현재 화면에서 판단 보류 표시 · 저장되지 않음 · 고객 불이익 없음"}
      </p>

      <button className="report-button" type="button" onClick={generate} disabled={state === "streaming"}>
        {state === "streaming" ? <RefreshCcw size={15} /> : <FileText size={15} />}
        {state === "streaming" ? "근거 초안 생성 중" : `${zoneMap?.snapshot.service_month ?? selectedMonth + "월"} 근거 초안`}
      </button>

      {state === "error" ? <p className="error-copy">{error}</p> : null}
      {progress ? <p className="report-progress">{progress}</p> : null}
      {markdown ? (
        <div className="report-popout" role="status" aria-live="polite">
          <div className="report-popout-head">
            <div>
              <span>보험사 직원용 검토 초안</span>
              <strong>{personaName(driver.customer_id)} · {zoneMap?.snapshot.service_month ?? selectedMonth + "월"} 근거 분석</strong>
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
              {state === "streaming" ? "생성 중" : "완료"}
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
  return latest && latest.length > 6 ? latest : "리포트 초안 수신 중";
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
  const scoreDetail = (value: number | null) => value === null || !Number.isFinite(value) ? "N/A · 관측 없음" : `${numberFormatter.format(value)}점`;
  return [
    {
      label: "이동 맥락 변화",
      width: meterWidth(risk),
      detail: scoreDetail(risk)
    },
    {
      label: "선택 월 생활권 안 안전점수",
      width: meterWidth(inZone),
      detail: scoreDetail(inZone)
    },
    {
      label: "선택 월 생활권 밖 안전점수",
      width: meterWidth(outZone),
      detail: scoreDetail(outZone)
    },
    {
      label: "선택 월 주행거리 점수",
      width: meterWidth(mileage),
      detail: `${scoreDetail(mileage)} · ${tripCount}건`
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

function ProblemFrame({ directory, driver }: { directory: PersonaDirectoryResponse; driver: DriverAnnualSummary | null }) {
  const summary = directory.summary;

  return (
    <section className="panel problem-frame" aria-label="문제와 기존 방식 비교">
      <div className="panel-head">
        <div>
          <p className="eyebrow">문제 정의</p>
          <h2>같은 마일리지 할인구간 안에 서로 다른 위험 패턴이 섞여 있습니다</h2>
        </div>
        <span className="count-badge">30명 가상 사례</span>
      </div>
      <div className="formula-compare">
        <div>
          <span>기존 마일리지 특약</span>
          <strong>연간 주행거리 + 차종</strong>
          <p>생활권과 위험변화 패턴이 달라도 같은 구간이면 같은 할인율을 적용합니다.</p>
        </div>
        <ArrowRight size={18} />
        <div>
          <span>제안 통합 산식</span>
          <strong>주행거리 + 생활권 안/밖 안전 + 위험변화</strong>
          <p>저주행 고객 안에서도 우대·기본·예방 케어를 구분합니다.</p>
        </div>
      </div>
      <div className="metric-strip">
        <Metric label="기존 평균 할인율" value={percent(summary.avg_existing_discount_rate_pct)} />
        <Metric label="제안 평균 할인율" value={percent(summary.avg_proposed_discount_rate_pct)} />
        <Metric label="평균 보정폭" value={signedPercentPoint(summary.avg_proposed_discount_rate_pct - summary.avg_existing_discount_rate_pct)} />
        <Metric label="판정 등급" value="우대 · 기본 · 예방 케어" tone="care" />
        <Metric label="평균 통합점수" value={`${numberFormatter.format(summary.avg_annual_score)}점`} tone="good" />
      </div>
      <div className="tier-proof">
        <div>
          <span>연간 할인 결과 비교</span>
          <strong>기존 평균 {percent(summary.avg_existing_discount_rate_pct)} / 제안 평균 {percent(summary.avg_proposed_discount_rate_pct)}</strong>
          <p>
            같은 30명 연간 데이터를 두 산식에 각각 적용했습니다. 실제 계약보험료 없이도 할인율 차이와 판정 근거를 비교할 수 있습니다.
          </p>
        </div>
        {driver ? (
          <div className="current-case">
            <span>현재 선택</span>
            <strong>
              {personaName(driver.customer_id)} · {personaTypeLabel(driver.persona_type)}
            </strong>
            <small>{translateText(driver.ab_comparison.existing_matched_tier_label)} / {decisionClass(driver.ab_comparison.annual_decision_signal).label}</small>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function ProductBlueprintPanel({ directory }: { directory: PersonaDirectoryResponse }) {
  const weights = normalizeProductWeights(directory.product_rules?.weights ?? referenceProductRules.weights);
  return (
    <section className="panel blueprint-panel" aria-label="데이터 생성 방식과 최종 산식">
      <div className="panel-head">
        <div>
          <p className="eyebrow">AI 활용과 상품 검증</p>
          <h2>AI는 보험료를 직접 결정하지 않고, 생활권 생성·후보 산식 탐색·판정 설명을 보조합니다.</h2>
        </div>
        <span className="count-badge">4개 지표 가중치 비교</span>
      </div>

      <div className="ai-proof-row" aria-label="AI 활용 위치">
        <div>
          <span>AI 1</span>
          <strong>생활권 자동 생성</strong>
          <p>기준선 2개월의 목적지를 DBSCAN으로 군집화하고, 개인 P90 반경으로 주차·우회 같은 작은 흔들림을 흡수합니다.</p>
        </div>
        <div>
          <span>AI 2</span>
          <strong>4개 지표 가중치 선택</strong>
          <p>주행거리, 생활권 안 안전, 생활권 밖 안전, 위험변화를 어느 비율로 반영할지 후보 산식을 비교합니다.</p>
        </div>
        <div>
          <span>AI 3</span>
          <strong>XAI + 직원용 리포트</strong>
          <p>XAI가 4개 지표의 영향을 추출하면 LLM이 직원용 설명문으로 바꿉니다. 보험료·인수·케어는 사람이 최종 결정합니다.</p>
        </div>
      </div>

      <div className="blueprint-flow" aria-label="산식 설계 흐름">
        <div className="flow-step">
          <span>1</span>
          <strong>시니어 주행 시나리오 생성</strong>
          <p>6개 운전자 유형 × 10명, 3개 이동환경 각 20명 — 총 {directory.summary.customer_count}명에게 자택, 마트, 병원, 자녀 집, 경로당 같은 합성 목적지와 외출 성향을 부여합니다.</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>2</span>
          <strong>2개월 기준선으로 생활권 생성</strong>
          <p>DBSCAN은 반복 거점을 찾고, 각 거점에 Core 500m와 중심–방문점 radial P90 Buffer를 별도로 적용합니다.</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>3</span>
          <strong>12개월 평가와 사람 검토</strong>
          <p>Reward와 Care를 독립 계산하고, Care는 같은 달 이동 변화와 위험행동 변화가 모두 있을 때만 검토를 제안합니다.</p>
        </div>
      </div>

      <div className="formula-workbench">
        <div className="formula-decision-card">
          <div className="blueprint-title">
            <BarChart3 size={17} />
            <strong>최종 통합점수 산식</strong>
          </div>
          <p className="formula-lead">
            한국 마일리지 거리 기준은 참조값으로 유지하되, Reward 산식과 케어 동시조건를 분리해 처벌 없는 예방지원 구조를 검증합니다.
          </p>
          <div className="weight-layout" aria-label="Final Formula Weights">
            <div className="weight-block mileage">
              <span>주행거리</span>
              <strong>{weights.mileage}%</strong>
              <small>저주행 우대 기준 유지</small>
            </div>
            <div className="weight-block in-zone">
              <span>생활권 안 안전</span>
              <strong>{weights.in_zone_safe}%</strong>
              <small>익숙한 반경 안 안정운전</small>
            </div>
            <div className="weight-block out-zone">
              <span>생활권 밖 안전</span>
              <strong>{weights.out_zone_safe}%</strong>
              <small>외부 주행 자체를 불리하게 보지 않음</small>
            </div>
            <div className="weight-block risk">
              <span>패턴 안정성</span>
              <strong>{weights.pattern_stability}%</strong>
              <small>개인 기준선 대비 변화 맥락</small>
            </div>
          </div>
          <div className="formula-box simplified">
            <span>계산 방식</span>
            <strong>Reward 후보점수 = 주행거리 {weights.mileage}% + 생활권 안 안전 {weights.in_zone_safe}% + 생활권 밖 안전 {weights.out_zone_safe}% + 패턴 안정성 {weights.pattern_stability}%</strong>
          </div>
        </div>

        <div className="formula-evidence-card">
          <div className="blueprint-title">
            <ShieldCheck size={17} />
            <strong>왜 이 비율을 선택했나</strong>
          </div>
          <div className="evidence-checklist">
            <div>
              <span>비용 검증</span>
              <strong>평균 할인율 변화가 설명 가능한 범위인지 확인</strong>
              <p>두 산식을 각각 계산해 기존 할인 구조와 비교하고, 변화폭이 과도하지 않은지 확인합니다.</p>
            </div>
            <div>
              <span>공정성 조건</span>
              <strong>생활권 밖이라는 이유만으로 감점하지 않음</strong>
              <p>반복 외부 목적지와 안정 주행은 기본 또는 우대 판단이 가능해야 합니다.</p>
            </div>
            <div>
              <span>Care 조건</span>
              <strong>같은 달의 이동 변화와 위험행동 변화 동시 충족</strong>
              <p>한 지표만 변하거나 데이터가 부족하면 자동 Care가 아니라 정상 또는 판단 보류로 남깁니다.</p>
            </div>
          </div>
          <CandidateSearchChart />
        </div>
      </div>
    </section>
  );
}

function ProfileLandingPanel({
  driver,
  zoneMap,
  selectedMonth,
  zoneState,
  driverState
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  selectedMonth: number;
  zoneState: LoadState;
  driverState: LoadState;
}) {
  if (!driver) {
    return <InspectorState title="프로필 선택 대기" detail="좌측 시니어 프로필을 선택하면 이 영역이 해당 사례 기준으로 갱신됩니다." />;
  }

  const annual = driver.annual_score;
  const comparison = driver.ab_comparison;
  const decision = decisionClass(annual.annual_decision_signal);
  const destinations = destinationLabels(driver);
  const formulaRows = [
    { label: "주행거리", score: annual.annual_mileage_score, weight: selectedPolicy.weights.mileage },
    { label: "생활권 안", score: annual.annual_in_zone_safe_driving_score, weight: selectedPolicy.weights.inZone },
    { label: "생활권 밖", score: annual.annual_out_zone_safe_driving_score, weight: selectedPolicy.weights.outZone },
    { label: "100-위험변화", score: 100 - annual.annual_out_zone_pattern_change_risk, weight: selectedPolicy.weights.riskChange }
  ];
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;

  return (
    <section className={`panel profile-landing ${driverState === "loading" ? "is-loading" : ""}`} aria-label="운전자 생활권 분석">
      <div className="profile-hero">
        <div>
          <p className="eyebrow">운전자 생활권 분석</p>
          <h2>
            {personaName(driver.customer_id)} · {personaTypeLabel(driver.persona_type)}
          </h2>
          <p>{translateText(driver.care_context.message_focus)}</p>
        </div>
        <em className={`decision ${decision.className}`}>{stateLabelKo(decision.label)}</em>
      </div>

      <div className="profile-landing-grid">
        <div className="profile-card map-card">
          <div className="map-card-head">
            <div>
              <p className="eyebrow">생활권 시각화</p>
              <h3>{selectedMonth}월 목적지 좌표 분석</h3>
              <span>DBSCAN 생활권 + P90 반경 + 선택 월 주행 해석</span>
            </div>
            {profile ? (
              <div className="map-stat-row">
                <b>P90 {Math.round(zoneMap?.snapshot.living_zone.buffer.departure_p90_threshold_m ?? 0).toLocaleString("ko-KR")}m</b>
                <b>생활권 밖 {percent(profile.outZoneRatio * 100)}</b>
                <b>위험행동 {profile.riskEvents}건</b>
              </div>
            ) : null}
          </div>
          {zoneState === "loading" || !zoneMap || !profile ? (
            <p>생활권 지도를 불러오는 중입니다.</p>
          ) : (
            <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
          )}
        </div>

        <div className="profile-card driver-card">
          <div className="blueprint-title">
            <UserRound size={17} />
            <strong>어르신 특성</strong>
          </div>
          <div className="trait-list compact">
            <Fact label="외출 빈도" value={driver.living_pattern.weekly_outing_frequency_ko} />
            <Fact label="주요 목적지" value={destinations.join(", ")} />
            <Fact label="생활권 밖 성향" value={driver.living_pattern.outer_trip_tendency} />
            <Fact label="위험행동 성향" value={driver.living_pattern.risk_behavior_tendency} />
            <Fact label="상품상 의미" value={driver.care_context.product_role} />
          </div>
        </div>

        <div className="profile-card formula-card profile-formula-card">
          <div className="blueprint-title">
            <BarChart3 size={17} />
            <strong>이 프로필의 산식 적용</strong>
          </div>
          <div className="same-driver-compare">
            <div>
              <span>기존 마일리지</span>
              <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
              <small>{translateText(comparison.existing_matched_tier_label)}</small>
            </div>
            <ArrowRight size={18} />
            <div>
              <span>제안 산식</span>
              <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
              <small>통합점수 {annual.annual_senior_safe_mileage_score}점</small>
            </div>
          </div>
          <div className="formula-substitution profile">
            {formulaRows.map((row) => (
              <div key={row.label}>
                <span>{row.label}</span>
                <strong>
                  {row.score === null ? "N/A" : numberFormatter.format(row.score)} × {row.weight.toFixed(2)}
                </strong>
                <em>{row.score === null ? "재정규화" : numberFormatter.format(row.score * row.weight)}</em>
              </div>
            ))}
            <div className="formula-total">
              <span>통합점수</span>
              <strong>{numberFormatter.format(annual.annual_senior_safe_mileage_score)}점</strong>
              <em>{decision.label}</em>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function CandidateSearchChart() {
  return (
    <div className="candidate-search formula-choice-board">
      <div className="candidate-chart-head">
        <span>생활권 알고리즘 운영 역할</span>
        <strong>화면에서는 DBSCAN 결과만 사용하며, 다른 알고리즘의 결과를 실행한 것처럼 표시하지 않습니다.</strong>
      </div>

      <div className="candidate-comparison-grid" aria-label="후보 산식 비교">
        <div className="selected">
          <span>DBSCAN</span>
          <strong>운영 참조</strong>
          <p>같은 미터 단위의 방문 이벤트에서 설명 가능한 반복 거점을 생성합니다.</p>
        </div>
        <div className="deferred">
          <span>HDBSCAN</span>
          <strong>오프라인 Challenger</strong>
          <p>도시와 광역 저밀도처럼 밀도가 다른 경우를 동일 입력으로 비교할 후보입니다.</p>
        </div>
        <div className="deferred">
          <span>Grid Count</span>
          <strong>Sanity Check</strong>
          <p>군집 알고리즘의 복잡도가 실제 개선을 만드는지 확인하는 최소 기준선입니다.</p>
        </div>
      </div>

      <div className="selection-criteria">
        <span>채택 기준</span>
        <strong>생활권 생성률 · noise · 복수 거점 · 도시/광역 공정성 · 설명 가능성 · 사람 검토 부담</strong>
      </div>
    </div>
  );
}

function PersonaMatrix({ summaries, selectedOption }: { summaries: PersonaSummary[]; selectedOption?: DriverOption }) {
  return (
    <section className="panel persona-matrix" aria-label="페르소나 유형 비교">
      <div className="panel-head">
        <div>
          <p className="eyebrow">페르소나 유형</p>
          <h2>6개 유형이 서로 다른 판단 장면을 만듭니다</h2>
        </div>
        {selectedOption ? <span className="count-badge">{caseNo(selectedOption.customer_id)}</span> : null}
      </div>
      <div className="persona-grid">
        {summaries.map((summary) => (
          <div className={`persona-card ${personaTone(summary.persona_type)}`} key={summary.persona_type}>
            <div className="mini-scene" aria-hidden="true">
              <span />
              <i />
              <b />
            </div>
            <strong>{personaTypeLabel(summary.persona_type)}</strong>
            <p>{personaNarrative(summary.persona_type)}</p>
            <small>
              평균 {numberFormatter.format(summary.avg_annual_distance_km)}km · {formatDecisionCounts(summary.decision_counts)}
            </small>
          </div>
        ))}
      </div>
    </section>
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
      ? `${numberFormatter.format(monthlyIntegratedScore)}점 · 기준선 관찰`
      : selectedRow.basis_status === "evaluation_ready"
        ? `${numberFormatter.format(monthlyIntegratedScore)}점`
        : "N/A · 판단 보류";

  return (
    <section className={`panel evidence-lane ${loading ? "is-loading" : ""}`} aria-label="월별 4지표 근거">
      <div className="panel-head">
        <div>
          <p className="eyebrow">월별 근거</p>
          <h2>2개월 기준선과 12개월 평가 근거를 같은 흐름에서 확인합니다</h2>
        </div>
        <div className="legend">
          {Object.entries(interpretationMeta).map(([key, meta]) => (
            <span key={key} className={meta.className}>{meta.label}</span>
          ))}
        </div>
      </div>

      {selectedRow && selectedMeta ? (
        <div className="month-focus-panel">
          <div className="month-focus-copy">
            <span>선택 월</span>
            <strong>
              {selectedRow.service_month} · {selectedMeta.label}
            </strong>
            <p>
              {numberFormatter.format(selectedRow.monthly_total_distance_km)}km 주행, {basisLabel(selectedRow.basis_status)}으로 생활권을 판단했습니다.
              {selectedRow.period_role === "baseline" ? " 이 달은 개인 기준선 관찰용이며 Reward·Care 평가에서 제외됩니다." : " 아래 값은 월 보험료가 아니라 상품 검토 근거입니다."}
            </p>
          </div>
          <div className="score-meter-grid">
            <ScoreMeter label="주행거리 점수" value={selectedRow.mileage_score} helper="월별 주행거리가 낮을수록 높음" />
            <ScoreMeter label="생활권 안 안전점수" value={selectedRow.in_zone_safe_driving_score} helper="생활권 안 위험행동이 낮을수록 높음" />
            <ScoreMeter label="생활권 밖 안전점수" value={selectedRow.out_zone_safe_driving_score} helper="생활권 밖 주행이 안정적일수록 높음" />
            <ScoreMeter label="패턴 안정성" value={selectedRow.pattern_stability_score ?? Math.max(0, 100 - selectedRow.out_zone_pattern_change_risk)} helper="개인 기준선 대비 이동 맥락 안정성" />
          </div>
          <p className="score-legend-copy">
            안전점수의 관측값이 없으면 100점으로 채우지 않고 N/A로 남긴 뒤, 관측된 구성요소의 가중치만 재정규화합니다.
          </p>
          <div className="monthly-integrated-formula" aria-label="월별 통합 근거점수 산식">
            <span>월별 통합 근거점수</span>
            <strong>{monthlyIntegratedLabel}</strong>
            <p>주행거리 {weights.mileage}% + 생활권 안 안전 {weights.in_zone_safe}% + 생활권 밖 안전 {weights.out_zone_safe}% + 패턴 안정성 {weights.pattern_stability}%</p>
            <small>Reward 후보점수와 케어 동시조건은 독립 계산되며, 어느 쪽도 보험료·인수 결정을 자동 확정하지 않습니다.</small>
            <div className={`monthly-care-gate ${selectedRow.care_state === "Care Review" ? "active" : ""}`}>
              <b>케어 동시조건</b>
              <span>이동 {numberFormatter.format(selectedRow.mobility_change_index_pct ?? 0)} · 위험행동 {numberFormatter.format(selectedRow.risky_behavior_change_index_pct ?? 0)}</span>
              <em>{selectedRow.period_role === "baseline" ? "기준선" : selectedRow.care_state === "Care Review" ? "사람 검토 제안" : "미충족"}</em>
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
              <span>{row.service_month.slice(2)} · {row.period_role === "baseline" ? "기준선" : "평가"}</span>
              <strong>{numberFormatter.format(row.monthly_total_distance_km)}km</strong>
              <small>{basisLabel(row.basis_status)}</small>
              <em>{row.care_state === "Care Review" ? "케어 검토" : stateLabelKo(row.reward_state ?? "Observation")}</em>
              <i style={{ width: `${Math.min(100, row.mobility_change_index_pct ?? row.out_zone_pattern_change_risk)}%` }} />
            </button>
          );
        })}
      </div>
    </section>
  );
}

function AnnualComparison({ driver, loading }: { driver: DriverAnnualSummary | null; loading: boolean }) {
  if (!driver) return <InspectorState title="연간 산식 로딩" detail="선택 사례의 연간 비교를 불러오는 중입니다." />;
  const comparison = driver.ab_comparison;
  const decision = decisionClass(comparison.annual_decision_signal);

  return (
    <section className={`panel side-panel ${loading ? "is-loading" : ""}`} aria-label="연간 산식 비교">
      <div className="panel-head compact">
        <div>
          <p className="eyebrow">연간 산식 비교</p>
          <h2>연간 할인 기준</h2>
        </div>
        <em className={`decision ${decision.className}`}>{stateLabelKo(decision.label)}</em>
      </div>
      <div className="premium-grid">
        <div>
          <span>연간 평가 주행거리</span>
          <strong>{numberFormatter.format(comparison.annual_total_distance_km)}km</strong>
        </div>
        <div>
          <span>기존 할인구간</span>
          <strong>{translateText(comparison.existing_matched_tier_label)}</strong>
        </div>
      </div>
      <ComparisonRow title="기존 마일리지 특약" subtitle={comparison.existing_matched_tier_label} rate={comparison.existing_discount_rate_pct} />
      <ComparisonRow title="제안 통합 산식" subtitle={`통합점수 ${numberFormatter.format(comparison.annual_senior_safe_mileage_score)}점`} rate={comparison.proposed_discount_rate_pct} />
      <div className="delta-box">
        <span>기존 대비 보정폭</span>
        <strong>{signedPercentPoint(comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct)}</strong>
        <small>월별 지표는 근거로만 쓰고, 최종 비교는 연간 할인 기준으로 계산합니다.</small>
      </div>
    </section>
  );
}

function EvidenceProfile({
  driver,
  zoneMap,
  selectedMonth,
  state,
  error
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  selectedMonth: number;
  state: LoadState;
  error: string;
}) {
  if (!driver) return <InspectorState title="생활권 근거 로딩" detail="운전자 프로필을 불러오는 중입니다." />;
  if (state === "loading" || !zoneMap) return <InspectorState title={`${selectedMonth}월 생활권 로딩`} detail="선택 월의 목적지와 위험행동 근거를 불러오는 중입니다." />;
  if (state === "error") return <InspectorState title="생활권 근거 오류" detail={error} />;

  const profile = deriveEvidenceProfile(driver, zoneMap.snapshot);

  return (
    <section className="panel side-panel evidence-profile" aria-label="선택 월 생활권 근거">
      <div className="panel-head compact">
        <div>
          <p className="eyebrow">선택 월 근거</p>
          <h2>{zoneMap.snapshot.service_month} 사례 분석</h2>
        </div>
        <MapPinned size={18} />
      </div>
      <div className="dynamic-copy">
        <strong>{profile.headline}</strong>
        <p>{profile.summary}</p>
      </div>
      <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
      <div className="derived-grid">
        <Fact label="주요 목적지" value={profile.topDestinations.join(", ")} />
        <Fact label="생활권 밖 패턴" value={profile.outerPattern} />
        <Fact label="위험행동" value={profile.riskPattern} />
        <Fact label="판정 기준" value={basisLabel(zoneMap.snapshot.basis_window.basis_status)} />
      </div>
      <DestinationEvidence trips={zoneMap.snapshot.trip_interpretations} />
    </section>
  );
}

function GeoLivingZoneCanvas({ driver, snapshot, profile }: { driver: DriverAnnualSummary; snapshot: ZoneSnapshot; profile: DerivedProfile }) {
  if (!snapshot.living_zone.clusters.length) {
    return (
      <div className="no-zone-state">
        <MapPinned size={24} />
        <strong>반복 거점 근거가 충분하지 않습니다</strong>
        <p>가짜 중심을 만들지 않고 No Zone으로 유지합니다. Reward와 Care는 판단 보류이며 불이익을 주지 않습니다.</p>
      </div>
    );
  }
  const groups = Object.values(groupTrips(snapshot.trip_interpretations)).sort((a, b) => b.count - a.count);
  const home = destinationForType(driver, "home");
  const destinations = groups
    .map((group) => ({ group, destination: destinationForType(driver, group.key) }))
    .filter((item): item is { group: TripGroup; destination: Destination } => Boolean(item.destination) && item.group.key !== "home");
  const visibleDestinations = destinations.slice(0, 6);
  const clusterPoints = snapshot.living_zone.clusters.map((cluster) => ({
    longitude: cluster.center_longitude,
    latitude: cluster.center_latitude
  }));
  const mapWidth = 900;
  const mapHeight = 560;
  const projector = createProjector(
    [
      ...(home ? [home] : []),
      ...visibleDestinations.map((item) => item.destination),
      ...clusterPoints
    ],
    { width: mapWidth, height: mapHeight, marginX: 132, marginY: 96 }
  );

  const homePoint = home ? projector(home.longitude, home.latitude) : { x: 230, y: 300 };
  const primaryCluster = snapshot.living_zone.clusters[0];
  const clusterCenter = primaryCluster ? projector(primaryCluster.center_longitude, primaryCluster.center_latitude) : homePoint;
  const radialP90M = primaryCluster?.p90_radius_m ?? snapshot.living_zone.buffer.departure_p90_threshold_m;
  const productBufferM = Math.max(500, Math.min(2000, radialP90M));
  const coreRadius = 48;
  const p90Radius = Math.max(coreRadius + 8, Math.min(128, productBufferM / 10));
  const routePath = (point: { x: number; y: number }, index: number) => {
    const bend = index % 2 === 0 ? -72 : 72;
    const midX = (homePoint.x + point.x) / 2;
    const midY = (homePoint.y + point.y) / 2;
    return `M${homePoint.x} ${homePoint.y} C${midX} ${midY + bend}, ${midX} ${midY - bend}, ${point.x} ${point.y}`;
  };
  const destinationViews = visibleDestinations.map((item, index) => {
    const rawPoint = projector(item.destination.longitude, item.destination.latitude);
    const distanceFromHome = Math.hypot(rawPoint.x - homePoint.x, rawPoint.y - homePoint.y);
    const distanceFromCore = Math.hypot(rawPoint.x - clusterCenter.x, rawPoint.y - clusterCenter.y);
    const needsSeparation = distanceFromHome < 88 || distanceFromCore < Math.max(82, p90Radius * 0.7);
    const angle = -1.35 + index * 0.72;
    const push = needsSeparation ? 72 : 0;
    return {
      ...item,
      point: {
        x: Math.max(42, Math.min(mapWidth - 42, rawPoint.x + Math.cos(angle) * push)),
        y: Math.max(42, Math.min(mapHeight - 42, rawPoint.y + Math.sin(angle) * push))
      }
    };
  });

  return (
    <div className="geo-canvas-shell">
      <svg className="geo-map" viewBox={`0 0 ${mapWidth} ${mapHeight}`} role="img" aria-label="비식별 정규화 좌표 기반 생활권 지도">
      <defs>
        <linearGradient id="mapSurface" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#f9fbfd" />
          <stop offset="100%" stopColor="#eef3f8" />
        </linearGradient>
        <filter id="nodeShadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="8" stdDeviation="8" floodColor="#0f172a" floodOpacity="0.14" />
        </filter>
      </defs>
      <rect x="0" y="0" width={mapWidth} height={mapHeight} rx="18" />
      {[110, 185, 260, 335, 410, 485].map((y) => <line key={`h${y}`} className="map-grid" x1="44" y1={y} x2="856" y2={y} />)}
      {[120, 240, 360, 480, 600, 720].map((x) => <line key={`v${x}`} className="map-grid" x1={x} y1="66" x2={x} y2="516" />)}
      <path className="map-road arterial" d="M38 405 C195 344 253 384 392 300 S665 190 862 138" />
      <path className="map-road" d="M78 130 C214 190 324 222 470 232 S708 278 840 376" />
      <path className="map-road muted" d="M126 502 C236 424 325 366 436 318 S672 283 812 250" />
      <text className="geo-title" x="42" y="42">생활권 판단 지도</text>
      <text className="geo-subtitle" x="42" y="63">개념도(축척 아님) · 중심권 500m · 완충권은 개인 P90 반영(최대 2km)</text>

      <g className="geo-core-ring">
        <circle cx={clusterCenter.x} cy={clusterCenter.y} r={p90Radius} />
        <circle cx={clusterCenter.x} cy={clusterCenter.y} r={coreRadius} />
        <text x={clusterCenter.x} y={clusterCenter.y - p90Radius - 10} textAnchor="middle">{snapshot.living_zone.clusters[0]?.label_ko ?? "반복 거점 A"}</text>
      </g>

      {snapshot.living_zone.clusters.slice(1).map((cluster, index) => {
        const point = projector(cluster.center_longitude, cluster.center_latitude);
        const clusterProductBuffer = Math.max(500, Math.min(2000, cluster.p90_radius_m));
        const radius = Math.max(coreRadius + 8, Math.min(92, clusterProductBuffer / 11));
        return (
          <g key={cluster.cluster_id} className="geo-cluster">
            <circle cx={point.x} cy={point.y} r={radius} />
            <circle cx={point.x} cy={point.y} r={coreRadius} />
            <text x={point.x} y={point.y - radius - 9} textAnchor="middle">{cluster.label_ko ?? `반복 거점 ${String.fromCharCode(66 + index)}`}</text>
          </g>
        );
      })}

      {destinationViews.map(({ group, point }, index) => {
        const meta = interpretationClass(group.dominant);
        return (
          <g key={`route-${group.key}`} className="route-layer">
            <path className="geo-route-shadow" d={routePath(point, index)} />
            <path className={`geo-route ${meta.className}`} d={routePath(point, index)} />
          </g>
        );
      })}

      {home ? (
        <g className="geo-node home">
          <circle cx={homePoint.x} cy={homePoint.y} r="18" />
          <text x={homePoint.x} y={homePoint.y - 27} textAnchor="middle">기준 방문점</text>
        </g>
      ) : null}

      {destinationViews.map(({ group, point }, index) => {
        const meta = interpretationClass(group.dominant);
        return (
          <g key={`node-${group.key}`} className={`geo-node ${meta.className}`}>
            <circle cx={point.x} cy={point.y} r={group.riskEvents > 0 ? 15 : 12} />
            <text className="geo-node-index" x={point.x} y={point.y + 4}>{index + 1}</text>
          </g>
        );
      })}

      <g className="geo-badge" transform="translate(42 500)">
        <rect width="318" height="34" rx="9" />
        <text x="13" y="22">Core 500m · Buffer {Math.round(productBufferM).toLocaleString("ko-KR")}m · radial P90 {Math.round(radialP90M).toLocaleString("ko-KR")}m</text>
      </g>
      <g className="geo-badge risk" transform="translate(374 500)">
        <rect width="260" height="34" rx="9" />
        <text x="13" y="22">Outer {percent(profile.outZoneRatio * 100)} · 위치 감점 0 · 위험행동 {profile.riskEvents}건</text>
      </g>
      </svg>
      <aside className="geo-detail-panel" aria-label="생활권 지도 근거 상세">
        <span>방문 근거 · 합성 라벨</span>
        {visibleDestinations.map(({ group, destination }, index) => {
          const meta = interpretationClass(group.dominant);
          return (
            <div key={`geo-detail-${group.key}`} className={`geo-detail-row ${meta.className}`}>
              <b>{index + 1}</b>
              <strong>{group.label ?? destinationTypeLabel(group.key)}</strong>
              <small>{meta.label} · {group.count}회 방문</small>
              <em>{group.distanceKm.toFixed(0)}km · 위험행동 {group.riskEvents}건</em>
            </div>
          );
        })}
      </aside>
    </div>
  );
}

function ScenarioCanvas({ driver, snapshot, profile }: { driver: DriverAnnualSummary; snapshot: ZoneSnapshot; profile: DerivedProfile }) {
  const scenario = scenarioBlueprint(driver.persona_type, profile, snapshot);
  return (
    <svg className={`scenario scenario-${scenario.kind}`} viewBox="0 0 360 250" role="img" aria-label={scenario.title}>
      <rect x="0" y="0" width="360" height="250" rx="8" />
      <text className="scenario-title" x="18" y="28">{scenario.title}</text>
      <text className="scenario-subtitle" x="18" y="48">{scenario.subtitle}</text>
      <circle className="core-zone" cx={scenario.center.x} cy={scenario.center.y} r={scenario.coreRadius} />
      <circle className="buffer-zone" cx={scenario.center.x} cy={scenario.center.y} r={scenario.bufferRadius} />
      {scenario.routes.map((item) => (
        <path key={item.id} className={`route-line ${item.tone}`} d={item.d} />
      ))}
      {scenario.nodes.map((item) => (
        <g key={item.id} className={`scene-node ${item.tone}`}>
          <circle cx={item.x} cy={item.y} r={item.size ?? 6} />
          <text x={item.anchor === "end" ? item.x - 10 : item.x + 10} y={item.y + 4} textAnchor={item.anchor ?? "start"}>{item.label}</text>
        </g>
      ))}
      {scenario.badges.map((item) => (
        <g key={item.label} className={`scene-badge ${item.tone}`} transform={`translate(${item.x} ${item.y})`}>
          <rect width={item.width} height="24" rx="5" />
          <text x="9" y="16">{item.label}</text>
        </g>
      ))}
      <text className="scenario-note" x="18" y="232">{scenario.note}</text>
    </svg>
  );
}

function DestinationEvidence({ trips }: { trips: ZoneTripInterpretation[] }) {
  const grouped = Object.values(groupTrips(trips)).sort((a, b) => b.count - a.count);
  return (
    <div className="destination-list">
      <div className="destination-head">
        <span>선택 월 목적지 근거</span>
        <span>{trips.length}회 주행</span>
      </div>
      {grouped.map((item) => {
        const meta = interpretationClass(item.dominant);
        return (
          <div className="destination-row" key={item.label}>
            <span>
              <strong>{item.label}</strong>
              <small>{item.count}회 주행 · 위험행동 {item.riskEvents}건 · 야간 {item.nightTrips}회</small>
            </span>
            <em className={`tag ${meta.className}`}>{meta.label}</em>
          </div>
        );
      })}
    </div>
  );
}

function NarrativeReport({ driver, zoneMap, selectedMonth }: { driver: DriverAnnualSummary | null; zoneMap: ZoneMapResponse | null; selectedMonth: number }) {
  const [state, setState] = useState<"idle" | "streaming" | "ready" | "error">("idle");
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setState("idle");
    setMarkdown("");
    setError("");
  }, [driver?.customer_id, selectedMonth]);

  if (!driver) return <InspectorState title="리포트 대기" detail="운전자를 선택하면 직원용 리포트를 생성할 수 있습니다." />;

  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const generate = async () => {
    setState("streaming");
    setMarkdown("");
    setError("");
    try {
      let next = "";
      await demoApi.streamMonthlyReport(driver.customer_id, selectedMonth, (chunk) => {
        next += chunk;
        setMarkdown(next);
      });
      setState("ready");
    } catch (reportError) {
      setState("error");
      setError(reportError instanceof Error ? reportError.message : "리포트 생성에 실패했습니다");
    }
  };

  return (
    <section className="panel side-panel report-panel" aria-label="직원용 리포트">
      <div className="panel-head compact">
        <div>
          <p className="eyebrow">직원용 리포트</p>
          <h2>근거 기반 설명문 생성</h2>
        </div>
        <FileText size={18} />
      </div>
      <div className="llm-boundary">
        <ShieldCheck size={16} />
        <span>리포트는 월별 근거를 직원이 이해할 수 있는 문장으로 설명합니다. 실제 계약 보험료 계산은 이 데모 범위 밖입니다.</span>
      </div>
      {profile ? (
        <div className="report-input">
          <span>생성 입력</span>
          <strong>{profile.headline}</strong>
          <small>{profile.topDestinations.join(", ")} · {profile.riskPattern}</small>
        </div>
      ) : null}
      <button className="report-button" type="button" onClick={generate} disabled={state === "streaming"}>
        {state === "streaming" ? <RefreshCcw size={15} /> : <FileText size={15} />}
        {state === "streaming" ? "생성 중" : `${selectedMonth}월 리포트 생성`}
      </button>
      {state === "error" ? <p className="error-copy">{error}</p> : null}
      {markdown ? <MarkdownReport markdown={markdown} className="markdown-stream" /> : null}
    </section>
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
      <strong>{numberFormatter.format(value)}점</strong>
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
  const topDestinations = grouped.slice(0, 3).map((item) => item.label);
  const riskEvents = grouped.reduce((sum, item) => sum + item.riskEvents, 0);
  const nightTrips = trips.reduce((sum, trip) => sum + Number(trip.night_drive_flag), 0);
  const repeatTrips = trips.reduce((sum, trip) => sum + Number(trip.route_repeat_flag), 0);
  const newDestinationTrips = trips.reduce((sum, trip) => sum + Number(trip.new_destination_flag), 0);
  const repeatRate = trips.length ? repeatTrips / trips.length : 0;
  if (!snapshot.living_zone.clusters.length) {
    const riskObservation = riskEvents > 0
      ? `위험행동 ${riskEvents}건은 관찰됐지만 생활권 안·밖으로 분류하지 않습니다.`
      : "위험행동 관찰값도 생활권 안·밖으로 분류하지 않습니다.";
    return {
      headline: "근거 부족 · 판단 보류",
      summary: `${snapshot.service_month}은 반복 거점 근거가 없어 No Zone입니다. ${riskObservation} Reward·Care는 보류하며 위치로 불이익을 주지 않습니다.`,
      topDestinations: [],
      outerPattern: "생활권 안·밖 미분류",
      riskPattern: "No Zone · 상품 판단 보류",
      repeatRate: 0,
      outZoneRatio: 0,
      riskEvents,
      nightTrips,
      newDestinationTrips
    };
  }
  const outZoneRatio = snapshot.monthly_evidence.out_zone_distance_ratio;
  const riskScore = snapshot.scores.out_zone_pattern_change_risk;

  let headline = "생활권 안 반복 주행";
  if (selectedRow?.care_state === "Care Review") headline = "이동 맥락과 위험행동의 동시변화 검토";
  else if (riskScore >= careReviewRiskThreshold) headline = "선택 월 이동 맥락 변화 관찰";
  else if (riskEvents > 0 && riskScore < preferredRiskCeiling) headline = "위험행동은 있으나 변화위험은 낮음";
  else if (outZoneRatio > 0.25 && repeatRate > 0.55 && riskEvents <= trips.length * 0.2) headline = "반복 외부 목적지 안정";
  else if (newDestinationTrips > 0 && outZoneRatio > 0.15) headline = "신규 외부 목적지 관찰";
  else if (driver.persona_type === "medical_visit_pattern") headline = "정기 반복 외부 이동 관찰";
  else if (driver.persona_type === "irregular_family_support") headline = "비정기 외부 이동 관찰";

  const outerPattern =
    outZoneRatio < 0.12
      ? "대부분 생활권 안 주행"
      : repeatRate >= 0.6
        ? "반복 외부 목적지 중심"
        : newDestinationTrips > 0
          ? "신규 외부 목적지 포함"
          : "분산된 외부 이동";
  const riskPattern =
    selectedRow?.care_state === "Care Review"
      ? `이동 맥락 변화와 위험행동 변화가 같은 평가월에 함께 나타나 사람 검토가 필요함`
      : riskEvents === 0
      ? "위험행동 거의 없음"
      : riskScore >= careReviewRiskThreshold
        ? `위험행동 ${riskEvents}건 · 변화위험 높음`
        : `위험행동 ${riskEvents}건이 관찰됐지만 변화위험은 ${numberFormatter.format(riskScore)}점으로 급증 신호는 제한적${nightTrips > 0 ? ` · 야간 ${nightTrips}회` : ""}`;

  return {
    headline,
    summary: `${snapshot.service_month}에는 ${topDestinations.join(", ")} 방문이 중심이며, 생활권 밖 비중은 ${percent(outZoneRatio * 100)}입니다. ${outerPattern}, ${riskPattern}으로 해석됩니다.`,
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
      label: trip.destination_label_ko ?? destinationTypeLabel(trip.destination_type),
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

type SceneNode = {
  id: string;
  label: string;
  x: number;
  y: number;
  tone: "core" | "buffer" | "safe" | "risk" | "care" | "muted";
  size?: number;
  anchor?: "start" | "end";
};

type SceneRoute = {
  id: string;
  d: string;
  tone: "safe" | "risk" | "care" | "muted";
};

type SceneBadge = {
  label: string;
  x: number;
  y: number;
  width: number;
  tone: "safe" | "risk" | "care" | "muted";
};

function scenarioBlueprint(personaType: string, profile: DerivedProfile, snapshot: ZoneSnapshot) {
  const base = {
    center: { x: 140, y: 145 },
    coreRadius: 42,
    bufferRadius: 80
  };

  if (personaType === "stable_outer_safe") {
    return {
      ...base,
      kind: "outer-safe",
      title: "Stable Repeated External Routes",
      subtitle: "Destinations and behavior remain stable even with Out-Zone driving",
      note: `Repeat Rate ${percent(profile.repeatRate * 100)} · Out-Zone ${percent(profile.outZoneRatio * 100)}`,
      nodes: [
        node("home", "House", 140, 145, "core", 7),
        node("clinic", "Hospital", 166, 121, "buffer"),
        node("family", "Repeated External", 286, 78, "safe", 8, "end"),
        node("leisure", "Nearby Area", 294, 184, "safe", 8, "end")
      ],
      routes: [
        route("family", "M140 145 C185 96 236 74 286 78", "safe"),
        route("leisure", "M140 145 C195 174 245 186 294 184", "safe")
      ],
      badges: [badge("Favorable Candidate", 235, 36, 76, "safe"), badge("Repeated External", 236, 210, 82, "safe")]
    };
  }

  if (personaType === "recent_outer_risk_change") {
    return {
      ...base,
      kind: "outer-risk",
      title: "New External Destination + Risk Change",
      subtitle: "Recent Out-Zone driving, harsh braking, and night-driving signals increase together",
      note: `Risk Events ${profile.riskEvents} Events · New Destination ${profile.newDestinationTrips} Trips`,
      nodes: [
        node("home", "House", 132, 148, "core", 7),
        node("market", "Mart", 160, 127, "core"),
        node("unknown", "New Destination", 304, 73, "risk", 9, "end"),
        node("brake", "Harsh Braking", 256, 132, "risk", 8, "end"),
        node("night", "Night", 304, 195, "risk", 7, "end")
      ],
      routes: [
        route("unknown", "M140 145 C190 78 246 59 304 73", "risk"),
        route("brake", "M140 145 C185 129 220 130 256 132", "risk"),
        route("night", "M140 145 C197 181 248 198 304 195", "risk")
      ],
      badges: [badge("Preventive Care", 229, 35, 86, "risk"), badge("Change Detected", 246, 210, 82, "risk")]
    };
  }

  if (personaType === "in_zone_risky_low_mileage") {
    return {
      ...base,
      kind: "inner-risk",
      title: "In-Zone Risk Events",
      subtitle: "Harsh braking and speeding accumulate locally despite low mileage",
      note: `Low mileage, but risk events ${profile.riskEvents} Events`,
      nodes: [
        node("home", "House", 140, 145, "core", 7),
        node("market", "Mart", 109, 126, "core"),
        node("clinic", "Hospital", 169, 116, "buffer"),
        node("brake", "Harsh Deceleration", 153, 95, "risk", 8),
        node("speed", "Speeding", 101, 164, "risk", 7),
        node("turn", "Sharp Turn", 181, 168, "risk", 7)
      ],
      routes: [
        route("local1", "M109 126 C132 98 153 94 169 116", "risk"),
        route("local2", "M140 145 C124 154 112 159 101 164", "risk")
      ],
      badges: [badge("Low-Mileage Blind Spot", 220, 38, 88, "risk"), badge("Local Risk", 220, 210, 92, "risk")]
    };
  }

  if (personaType === "medical_visit_pattern") {
    return {
      ...base,
      kind: "medical",
      title: "Repeated Hospital Visits",
      subtitle: "Although it appears external, repeated visits are observed as a candidate Safe Zone",
      note: `Main Destinations ${profile.topDestinations.join(", ")}`,
      nodes: [
        node("home", "House", 126, 146, "core", 7),
        node("pharmacy", "Pharmacy", 164, 162, "core"),
        node("clinic", "Hospital", 257, 116, "care", 9, "end"),
        node("hospital", "Regular Care", 298, 154, "care", 8, "end")
      ],
      routes: [
        route("clinic", "M126 146 C171 112 214 105 257 116", "care"),
        route("hospital", "M126 146 C184 158 236 166 298 154", "care")
      ],
      badges: [badge("Candidate Safe Zone", 222, 45, 92, "care"), badge("Repeated Visit", 230, 210, 78, "care")]
    };
  }

  if (personaType === "irregular_family_support") {
    return {
      ...base,
      kind: "family",
      title: "Family-Care Out-Zone Travel",
      subtitle: "Destinations are dispersed, requiring continued observation",
      note: `Out-Zone ${percent(profile.outZoneRatio * 100)} · Repeat Rate ${percent(profile.repeatRate * 100)}`,
      nodes: [
        node("home", "House", 140, 145, "core", 7),
        node("family", "Family House", 294, 73, "safe", 7, "end"),
        node("care", "Care Site", 302, 178, "safe", 7, "end"),
        node("temp", "Temporary Visit", 54, 75, "muted", 6),
        node("unknown", "Irregular", 62, 204, "risk", 7)
      ],
      routes: [
        route("family", "M140 145 C195 90 240 70 294 73", "safe"),
        route("care", "M140 145 C200 164 250 183 302 178", "safe"),
        route("temp", "M140 145 C103 110 77 88 54 75", "muted"),
        route("unknown", "M140 145 C105 162 76 186 62 204", "muted")
      ],
      badges: [badge("Observe", 265, 210, 52, "safe"), badge("Dispersed Travel", 36, 36, 78, "muted")]
    };
  }

  return {
    ...base,
    kind: "compact",
    title: "Repeated In-Zone Stability",
    subtitle: "Short, repeated trips centered on home, mart, and pharmacy",
    note: `Out-Zone ${percent(profile.outZoneRatio * 100)} · Risk Events ${profile.riskEvents} Events`,
    nodes: [
      node("home", "House", 140, 145, "core", 7),
      node("market", "Mart", 112, 123, "core"),
      node("pharmacy", "Pharmacy", 168, 126, "core"),
      node("clinic", "Hospital", 174, 170, "buffer"),
      node("outer", "External Destination", 294, 84, "muted", 5, "end")
    ],
    routes: [
      route("core1", "M112 123 C132 110 154 112 168 126", "safe"),
      route("core2", "M140 145 C152 161 163 170 174 170", "safe"),
      route("outer", "M140 145 C198 108 243 87 294 84", "muted")
    ],
    badges: [badge("Favorable Candidate", 236, 43, 78, "safe"), badge("Repeated Stability", 48, 210, 78, "safe")]
  };
}

function node(id: string, label: string, x: number, y: number, tone: SceneNode["tone"], size = 6, anchor: SceneNode["anchor"] = "start"): SceneNode {
  return { id, label, x, y, tone, size, anchor };
}

function route(id: string, d: string, tone: SceneRoute["tone"]): SceneRoute {
  return { id, d, tone };
}

function badge(label: string, x: number, y: number, width: number, tone: SceneBadge["tone"]): SceneBadge {
  return { label, x, y, width, tone };
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
  return `가상 ${String(personaIndex(customerId) + 1).padStart(2, "0")}`;
}

function personaAge(customerId: string) {
  const ages = [72, 76, 69, 81, 74, 78, 71, 83, 75, 80, 77, 73, 82, 70, 79, 84, 76, 72, 68, 81, 75, 79, 73, 85, 77, 74, 82, 71, 78, 80];
  return ages[personaIndex(customerId)] ?? 76;
}

function personaResidence(driver: DriverAnnualSummary) {
  return driver.environment_display_name_ko ?? "이동환경 미지정";
}

function caseType(option: DriverOption) {
  return personaTypeLabel(option.persona_type);
}

function coreChangeTag(personaType: string) {
  const tags: Record<string, string> = {
    stable_local_safe: "근거리 안정",
    low_mileage_risky: "저주행 위험행동",
    safe_multi_hub: "복수 거점",
    safe_wide_area: "광역 안전",
    mobility_change_only: "이동 변화",
    mobility_risk_cochange: "동시변화",
    stable_local_low_mileage: "반복 안정",
    stable_outer_safe: "외부 안정",
    recent_outer_risk_change: "활동반경 확대",
    in_zone_risky_low_mileage: "생활권 안 위험",
    medical_visit_pattern: "정기 외부",
    irregular_family_support: "불규칙 외부"
  };
  return tags[personaType] ?? "패턴 관찰";
}

function riskBadgeForOption(option: DriverOption) {
  return decisionClass(option.annual_decision_signal);
}

function riskBadgeForDriver(driver: DriverAnnualSummary) {
  return decisionClass(driver.ab_comparison.annual_decision_signal);
}

function recommendedAction(driver: DriverAnnualSummary, selectedRow?: MonthlyEvidence) {
  if (driver.reward_state === "Hold" || driver.care_state === "Hold") return "근거 부족 · 판단 보류 · 불이익 없음";
  if (driver.care_state === "Care Review") return "담당자가 근거 확인 후 비징벌적 Care 여부 검토";
  if (driver.reward_state === "Reward") return "Reward 후보 근거 확인";
  if ((selectedRow?.mobility_change_index_pct ?? 0) > 0) return "변화 추세 관찰 · 자동 조치 없음";
  return "Neutral 유지";
}

function personaTone(type: string) {
  if (type === "mobility_risk_cochange" || type === "low_mileage_risky") return "risk";
  if (type === "mobility_change_only") return "care";
  if (type === "safe_multi_hub" || type === "stable_local_safe" || type === "safe_wide_area") return "safe";
  return "base";
}

function personaNarrative(type: string) {
  const text: Record<string, string> = {
    stable_local_safe: "짧은 반복 이동과 안정운전이 함께 나타나는 Reward 기준군",
    low_mileage_risky: "적게 운전해도 위험행동이 있어 mileage-only의 한계를 보여주는 군",
    safe_multi_hub: "멀리 떨어진 복수 반복 거점을 하나의 큰 원으로 합치지 않아야 하는 검증군",
    safe_wide_area: "이동반경이 넓어도 안전행동을 유지해 Outer 자체를 감점하지 않아야 하는 공정성 검증군",
    mobility_change_only: "이동 맥락만 달라지고 위험행동은 변하지 않아 Care를 제안하면 안 되는 음성 대조군",
    mobility_risk_cochange: "같은 평가월에 이동과 위험행동이 함께 달라져 사람 검토가 필요한 핵심군",
    stable_local_low_mileage: "짧은 반복 주행이 많아 기존 마일리지와 제안 산식 모두 우대 가능성이 높은 기준군",
    stable_outer_safe: "생활권 밖 이동이 있어도 목적지 반복성과 낮은 위험행동으로 오분류를 막아야 하는 공정성 검증군",
    recent_outer_risk_change: "저주행이지만 하반기 외부 목적지와 위험행동이 함께 늘어 예방 케어가 필요한 핵심군",
    in_zone_risky_low_mileage: "멀리 가지 않아도 생활권 안 급감속과 과속이 누적되는 저주행 함정군",
    medical_visit_pattern: "정기적으로 반복되는 외부 방문을 위험으로 단정하지 않고 후보 생활권으로 관찰하는 군",
    irregular_family_support: "이동 목적을 추정하지 않고 불규칙한 외부 이동의 변화 근거만 관찰하는 군"
  };
  return text[type] ?? "월별 주행 근거에 따라 연간 판단이 달라지는 사례군";
}

function destinationLabels(driver: DriverAnnualSummary) {
  const fallback: Record<string, string> = {
    home: "기준 방문점",
    routine_hub_a: "반복 거점 A",
    routine_hub_b: "반복 거점 B",
    routine_hub_c: "반복 거점 C",
    new_visit: "신규 방문"
  };

  return driver.living_pattern.primary_destinations.map((key) => {
    const destination = driver.living_destinations[key] ?? driver.living_destinations[`${key}_home`];
    return translateText(destination?.label_ko ?? destinationTypeLabel(key) ?? fallback[key] ?? key);
  });
}

function basisLabel(value: string) {
  if (value === "baseline_observation") return "개인 기준선 관찰";
  if (value === "evaluation_ready") return "평가 근거 사용 가능";
  if (value === "living_zone_evidence_hold") return "생활권 근거 부족 · 보류";
  if (value === "data_coverage_hold") return "데이터 충분성 미달 · 보류";
  if (value === "pre_policy_60_day_dbscan") return "가입 전 60일 기준";
  if (value === "rolling_60_day_dbscan") return "직전 60일 갱신";
  return value;
}

function decisionClass(value: DecisionSignal) {
  return decisionMeta[value] ?? { label: translateText(value), className: "base" };
}

function interpretationClass(value: Interpretation) {
  return interpretationMeta[value] ?? { label: translateText(value), className: "stable", short: translateText(value) };
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
