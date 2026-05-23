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

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

const personaNames = [
  "Alex Kim",
  "Soon Park",
  "Jung Lee",
  "Mia Choi",
  "Kevin Jung",
  "Bok Yoon",
  "Sang Han",
  "Mija Oh",
  "Moon Kang",
  "Rye Seo",
  "Han Jo",
  "Young Moon",
  "Sang Bae",
  "Ok Shin",
  "Man Yoo",
  "Kyung Lim",
  "Sung Noh",
  "Geum Hong",
  "Tae Kwon",
  "Soon Jang",
  "Jae Ko",
  "Young Baek",
  "Ki Nam",
  "Hwa Song",
  "Chun Yang",
  "Mikyung Cha",
  "Byung Joo",
  "Jung Min",
  "Seok Ha",
  "Young Do"
];

const decisionMeta: Record<string, { label: string; className: string }> = {
  우대: { label: "Favorable", className: "good" },
  기본: { label: "Standard", className: "base" },
  "예방 케어": { label: "Preventive Care", className: "care" },
  Favorable: { label: "Favorable", className: "good" },
  Preferred: { label: "Favorable", className: "good" },
  Standard: { label: "Standard", className: "base" },
  "Preventive Care": { label: "Preventive Care", className: "care" }
};

const interpretationMeta: Record<string, { label: string; className: string; short: string }> = {
  existing_living_zone: { label: "Baseline In-Zone", className: "stable", short: "In-Zone" },
  candidate_living_zone: { label: "Repeated Out-Zone Candidate", className: "candidate", short: "Candidate" },
  out_zone_safe_driving: { label: "Stable Out-Zone", className: "safeout", short: "Out-Zone Stable" },
  out_zone_pattern_change_risk: { label: "Risk Change Observed", className: "risk", short: "Change" }
};

const reasonLabels: Record<string, string> = {
  CANDIDATE_LIVING_ZONE: "Candidate Safe Zone Observed",
  HARSH_BRAKE_INCREASE: "Harsh Braking Increase",
  LOW_MILEAGE: "Low-Mileage Condition",
  LOW_NIGHT_DRIVING: "Low Night Driving",
  LOW_RISK_EVENTS: "Low Risk Events",
  NIGHT_DRIVING_INCREASE: "Night Driving Increase",
  NO_RECENT_OUT_ZONE_SPIKE: "No Recent Out-Zone Spike",
  NO_STRONG_RISK_CHANGE: "No Strong Risk Change",
  OUT_ZONE_PATTERN_CHANGE_RISK: "Out-Zone Risk Change",
  OUT_ZONE_RATIO_INCREASE: "Out-Zone Share Increase",
  OUT_ZONE_SAFE: "Stable Out-Zone",
  OUT_ZONE_SAFE_DRIVING: "Safe Out-Zone Driving",
  PREVENTIVE_CARE_REVIEW: "Preventive Care Review",
  RISK_EVENT_INCREASE: "Risk Event Increase",
  STABLE_IN_ZONE_DRIVING: "Stable In-Zone Driving"
};

const personaTypeLabels: Record<string, string> = {
  stable_local_low_mileage: "Stable Local Low-Mileage",
  stable_outer_safe: "Stable Out-Zone Driver",
  recent_outer_risk_change: "Recent Out-Zone Risk Change",
  in_zone_risky_low_mileage: "In-Zone Risk Behavior",
  medical_visit_pattern: "Repeated Medical-Visit Pattern",
  irregular_family_support: "Irregular Family-Care Travel"
};

const destinationTypeLabels: Record<string, string> = {
  clinic: "Hospital",
  family: "Family House",
  family_home: "Family House",
  home: "House",
  leisure: "Nearby Outing",
  market: "Mart",
  pharmacy: "Pharmacy",
  unknown_outer: "New External Destination"
};

const dynamicTextTranslations: Record<string, string> = {
  "생활권 안 저주행 안정형": "Stable Local Low-Mileage",
  "생활권 밖 안정 주행형": "Stable Out-Zone Driver",
  "최근 생활권 밖 위험변화형": "Recent Out-Zone Risk Change",
  "생활권 안 저주행 위험행동형": "In-Zone Risk Behavior",
  "병원 방문 반복 외부 목적지형": "Repeated Medical-Visit Pattern",
  "가족 돌봄 불규칙 외부 이동형": "Irregular Family-Care Travel",
  "주 2회 내외": "About 2 trips/week",
  "주 3~4회": "3-4 trips/week",
  "3천km 이하": "Under 3,000 km",
  "4천km 이하": "Under 4,000 km",
  "5천km 이하": "Under 5,000 km",
  "6천km 이하": "Under 6,000 km",
  "7천km 이하": "Under 7,000 km",
  "8천km 이하": "Under 8,000 km",
  "9천km 이하": "Under 9,000 km",
  "생활권 안 중심": "Mostly In-Zone",
  "생활권 안 반복 주행과 낮은 위험행동을 근거로 안정 저주행 고객으로 설명": "Explains the driver as a stable low-mileage customer based on repeated In-Zone driving and low risk events",
  "기존 거리 중심 산식과 제안 통합 산식 모두 우량으로 분류되어야 하는 기준 우량군": "Reference preferred group that should be classified as stable by both the existing mileage formula and the proposed integrated formula",
  "예방 케어로 잘못 분류되면 안정 고객 비용 효율 평가가 왜곡됨": "If misclassified into Preventive Care, the cost-efficiency assessment for stable customers is distorted",
  "반복 외부 목적지 안정": "Repeated external destinations with stable behavior",
  "생활권 밖 주행 자체를 과도하게 불리하게 보지 않는지 확인하는 공정성/오분류 방지군": "Fairness and misclassification-control group for checking that Out-Zone driving itself is not over-penalized",
  "외부 주행은 있으나 반복 목적지와 안정 운전으로 예방 케어 대상은 아님": "Has external driving, but repeated destinations and stable driving mean it should not automatically become a Preventive Care case",
  "생활권 밖 비율만으로 위험군 처리하면 모델 공정성이 약해짐": "Treating the driver as risky based only on Out-Zone share weakens model fairness",
  "하반기 외부 목적지 증가": "Increase in external destinations in the second half",
  "하반기 야간/급제동 증가": "Increase in night driving and harsh braking in the second half",
  "저주행임에도 최근 생활권 밖 야간/위험행동이 함께 늘어난 예방 케어 신호": "Preventive Care signal: despite low mileage, recent Out-Zone night driving and risk events increased together",
  "기존 마일리지 산식이 놓칠 수 있는 저주행 위험변화 핵심 포착 대상군": "Core target group for detecting low-mileage risk changes that the existing mileage formula can miss",
  "핵심 타깃을 놓치면 A/B 우수성 승인 게이트를 통과하기 어려움": "Missing this target group makes it difficult to pass the A/B validation gate",
  "생활권 안 과속/급감속 반복": "Repeated In-Zone speeding and harsh braking",
  "생활권 안 주행이라도 과속/급감속이 있으면 감점되는지 확인하는 엣지케이스": "Edge case for checking whether speeding and harsh braking are penalized even inside the safe zone",
  "생활권 내 주행이 많지만 위험행동이 있어 우대 판단은 보수적으로 설명": "Mostly In-Zone driving, but risk events require a conservative preferred decision",
  "생활권 안이라는 이유로 무조건 안정형 처리하면 모델 해석 원칙을 위반함": "Classifying as stable solely because it is In-Zone violates the model's interpretation principle",
  "반복 병원 목적 외부 이동": "Repeated external hospital trips",
  "주간 병원 이동 중심, 위험행동 낮음": "Mostly daytime hospital trips with low risk events",
  "반복 의료 목적 외부 이동을 신규 위험변화로 오판하지 않는지 확인하는 케어 맥락군": "Care-context group for checking that repeated medical trips are not mistaken for new risk changes",
  "정기 병원 방문처럼 반복 목적지가 있는 외부 이동은 변화 위험과 구분": "Repeated external trips, such as regular hospital visits, are separated from risk-change signals",
  "의료 목적 반복 이동을 위험변화로 오판하면 직원 설명 품질이 낮아짐": "If repeated medical trips are mistaken for risk changes, explanation quality for employees drops",
  "가족 돌봄 외부 이동 변동": "Variable external travel for family care",
  "외부 이동은 변동하나 위험행동 제한적": "External travel varies, but risk events remain limited",
  "불규칙 외부 이동이 있어도 위험행동과 야간 증가가 동반되는지 분리 평가하는 엣지케이스": "Edge case for separately evaluating whether irregular external travel is accompanied by risk-event and night-driving increases",
  "불규칙 가족 지원 이동은 있으나 위험행동 증가가 제한적이면 예방 케어로 단정하지 않음": "Irregular family-support travel exists, but it should not be treated as Preventive Care when risk-event increases are limited",
  "외부 이동 증가만으로 케어 대상 처리하면 오탐 제한 조건에 불리함": "Treating external-travel increases alone as care cases hurts the false-positive control condition",
  "위험행동 낮음": "Low risk events",
  "기본": "Standard",
  "우대": "Favorable",
  "예방 케어": "Preventive Care",
  "신규 외부 목적지": "New External Destination",
  "근교 외출지": "Nearby Outing",
  "자녀집": "Family House",
  "자택": "House",
  "병원": "Hospital",
  "마트": "Mart",
  "약국": "Pharmacy"
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
  const [selectedCustomerId, setSelectedCustomerId] = useState("cust_011");
  const [pageMode, setPageMode] = useState<PageMode>("overview");
  const [driver, setDriver] = useState<DriverAnnualSummary | null>(null);
  const [monthlyEvidence, setMonthlyEvidence] = useState<MonthlyEvidence[]>([]);
  const [selectedMonth, setSelectedMonth] = useState(1);
  const [zoneMap, setZoneMap] = useState<ZoneMapResponse | null>(null);
  const [directoryState, setDirectoryState] = useState<LoadState>("loading");
  const [driverState, setDriverState] = useState<LoadState>("loading");
  const [zoneState, setZoneState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let active = true;
    demoApi
      .getPersonaDirectory()
      .then((payload) => {
        if (!active) return;
        setDirectory(payload);
        setSelectedCustomerId(payload.default_customer_id ?? payload.driver_options[0]?.customer_id ?? "cust_011");
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
    if (!directory) return;
    let active = true;
    setDriverState("loading");
    setZoneMap(null);
    Promise.all([
      demoApi.getAnnualSummary(selectedCustomerId),
      demoApi.getMonthlySnapshots(selectedCustomerId)
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
  }, [directory, selectedCustomerId]);

  useEffect(() => {
    if (!driver) return;
    let active = true;
    setZoneState("loading");
    demoApi
      .getZoneMap(driver.customer_id, selectedMonth)
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
  }, [driver, selectedMonth]);

  const selectedOption = useMemo(
    () => directory?.driver_options.find((option) => option.customer_id === selectedCustomerId),
    [directory, selectedCustomerId]
  );

  const selectProfile = (customerId: string) => {
    setSelectedCustomerId(customerId);
    setPageMode("profiles");
  };

  if (directoryState === "loading") {
    return <ScreenState title="Connecting Demo Data" detail="Loading 30 personas and annual comparison outputs." />;
  }

  if (directoryState === "error" || !directory) {
    return <ScreenState title="Unable to Open Demo Data" detail={errorMessage} />;
  }

  return (
    <div className="workbench">
      <header className="app-header">
        <div className="brand-block">
          <div>
            <p className="eyebrow">Samsung Fire & Marine AI Challenge · Decision Dashboard</p>
            <h1>Senior Safe Zone Rider</h1>
            <p>Shows how Safe Zone stability and risk-change signals supplement the annual mileage-based discount structure.</p>
          </div>
        </div>
        <div className="header-actions">
          <div className="page-switch" aria-label="Page Switch">
            <button
              type="button"
              className={pageMode === "overview" ? "active" : ""}
              onClick={() => setPageMode("overview")}
              aria-current={pageMode === "overview" ? "page" : undefined}
            >
              Model Design
            </button>
            <button
              type="button"
              className={pageMode === "profiles" ? "active" : ""}
              onClick={() => setPageMode("profiles")}
              aria-current={pageMode === "profiles" ? "page" : undefined}
            >
              Profile Analysis
            </button>
          </div>
          <div className="contract-box">
            <span>Decision Unit</span>
            <strong>Annual Review · Monthly Evidence</strong>
            <small>First 60 days are used only to build the Safe Zone</small>
          </div>
        </div>
      </header>

      {pageMode === "overview" ? (
        <DesignOverviewPage directory={directory} />
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
            />

            <MonthlyEvidenceLane
              rows={monthlyEvidence}
              selectedMonth={selectedMonth}
              loading={driverState === "loading"}
              onSelectMonth={setSelectedMonth}
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
            selectedMonth={selectedMonth}
            loading={driverState === "loading"}
          />
        </main>
      )}
    </div>
  );
}

function DesignOverviewPage({ directory }: { directory: PersonaDirectoryResponse }) {
  return (
    <main className="overview-page" aria-label="Product Design Overview Page">
      <OverviewComparisonPanel directory={directory} />

      <ProductBlueprintPanel directory={directory} />
    </main>
  );
}

function OverviewComparisonPanel({ directory }: { directory: PersonaDirectoryResponse }) {
  const summary = directory.summary;
  const donutBackground = "conic-gradient(#0b63f6 0 33.333%, #344054 33.333% 66.666%, #d97706 66.666% 100%)";
  const avgRateDelta = summary.avg_proposed_discount_rate_pct - summary.avg_existing_discount_rate_pct;

  return (
    <section className="panel comparison-overview" aria-label="Overall Comparison Dashboard">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Overall Comparison</p>
          <h2>Comparing the existing mileage discount and the proposed formula using the same 30 drivers and annual mileage data</h2>
        </div>
        <span className="count-badge">12-Month Evaluation · {summary.customer_count} Drivers</span>
      </div>

      <div className="judge-takeaway" aria-label="Key Evaluation Points">
        <div>
          <span>Problem</span>
          <strong>Existing mileage discounts cannot distinguish risk differences within the same low-mileage group</strong>
          <p>Under the existing mileage discount, drivers in the same annual mileage band receive the same discount even if Safe Zone departures, night driving, or harsh braking patterns change.</p>
        </div>
        <div>
          <span>Proposed Differentiation</span>
          <strong>Adds Safe Zone stability and risk-change signals on top of mileage</strong>
            <p>Favorable drivers are identified more accurately, while risk-change cases are separated into Preventive Care before the annual discount is recalculated.</p>
        </div>
        <div>
          <span>Validation Result</span>
          <strong>Even within the same low-mileage group, decisions can differ as Favorable, Standard, or Preventive Care</strong>
          <p>The dashboard shows only verifiable average discount changes and classification results, without using actual contract premiums.</p>
        </div>
      </div>

      <div className="comparison-ledger" aria-label="Existing Mileage vs Proposed Formula Table">
        <div className="ledger-head">
          <span>Comparison Item</span>
          <strong>Existing Mileage Rider</strong>
          <strong>Proposed Integrated Formula</strong>
        </div>
        <ComparisonLedgerRow
          label="Evaluation Basis"
          legacy="Uses only annual mileage and vehicle type"
          proposed="Uses annual mileage, In-Zone Safety, Out-Zone Safety, and Risk Change together"
        />
        <ComparisonLedgerRow
          label="Within the Same Low-Mileage Group"
          legacy="Drivers in the same mileage band usually receive the same discount"
          proposed="Even within the same low-mileage band, Safe Zone evidence can split customers into Favorable, Standard, or Preventive Care"
        />
        <ComparisonLedgerRow
          label="Discount Decision Method"
          legacy="Applies the mileage-band discount table as is"
          proposed="Starts from the existing discount table, then uses the integrated score to decide Favorable, Standard, or Preventive Care routing"
        />
        <ComparisonLedgerRow
          label="Explainability"
          legacy="Limited evidence to explain why the same discount is applied or why an adjustment is needed"
          proposed="Safe Zone maps, monthly four-factor scores, and XAI reports explain the reason for each adjustment"
        />
      </div>

      <div className="overview-evidence-grid">
        <div className="decision-donut-card">
          <span>Decision Tier Structure of the Proposed Formula</span>
          <div className="decision-donut-wrap">
            <div className="decision-donut" style={{ background: donutBackground }}>
              <div>
                <strong>3 Tiers</strong>
                <small>Annual Decision Criteria</small>
              </div>
            </div>
            <div className="decision-donut-legend">
              <DecisionLegend label="Favorable" detail="Safe Zone Stable" className="preferred" />
              <DecisionLegend label="Standard" detail="Low Change" className="standard" />
              <DecisionLegend label="Preventive Care" detail="Risk Change Observed" className="care" />
            </div>
          </div>
        </div>

        <div className="simulation-result-card">
          <span>A/B Simulation Results for 30 Drivers</span>
          <strong>Comparing discount rates and classification outcomes</strong>
          <p>
            The same annual driving data from 30 drivers was applied to both the existing mileage formula and the proposed integrated formula. Since actual contract premiums are not used at this stage,
            the comparison focuses on average discount rates and Favorable/Standard/Preventive Care classifications.
          </p>
          <div className="budget-compare-grid no-money">
            <div>
              <span>Existing Avg. Discount</span>
              <strong>{percent(summary.avg_existing_discount_rate_pct)}</strong>
              <small>Based on annual mileage bands</small>
            </div>
            <div>
              <span>Proposed Avg. Discount</span>
              <strong>{percent(summary.avg_proposed_discount_rate_pct)}</strong>
              <small>Based on the four-factor integrated score</small>
            </div>
            <div>
              <span>Avg. Discount Change</span>
              <strong>{signedPercentPoint(avgRateDelta)}</strong>
              <small>Rate difference comparable without actual contract premiums</small>
            </div>
          </div>
          <p className="portfolio-footnote">
            Before actual premiums and coverage terms are finalized, only discount rates and decision evidence are presented.
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
    { value: "all", label: "All" },
    { value: "Favorable", label: "Favorable" },
    { value: "Standard", label: "Standard" },
    { value: "Preventive Care", label: "Preventive Care" }
  ];
  const filtered = options.filter((option) => {
    const text = `${personaName(option.customer_id)} ${caseNo(option.customer_id)} ${caseType(option)} ${decisionClass(option.annual_decision_signal).label}`.toLowerCase();
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
    <aside className="case-rail" aria-label="Virtual Senior Case List">
      <div className="rail-heading">
        <p className="eyebrow">Virtual Cases</p>
        <h2>30 Cases</h2>
      </div>
      <label className="search-box">
        <Search size={15} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or tag" />
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
          const risk = riskBadgeForOption(option);
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
                  {personaAge(option.customer_id)} yrs · {changeTag}
                </small>
              </span>
              <em className={`risk-pill ${risk.className}`}>{risk.label}</em>
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
    return <InspectorState title="Waiting for Case Decision" detail="Select a case on the left to view the final decision summary." />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const risk = riskBadgeForDriver(driver);
  const rateDelta = comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct;
  const action = recommendedAction(driver, selectedRow);
  const decisionReasons = profile
    ? [profile.headline, profile.outerPattern, profile.riskPattern]
    : driver.annual_score.annual_reason_codes.slice(0, 3).map((code) => reasonLabels[code] ?? code);

  return (
    <section className={`decision-summary-card ${driverState === "loading" ? "is-loading" : ""}`} aria-label="Final Decision Summary">
      <div className="summary-identity">
        <p className="eyebrow">Final Decision Summary</p>
        <h2>{personaName(driver.customer_id)}</h2>
        <span>{personaAge(driver.customer_id)} yrs · {personaResidence(driver)} · {personaTypeLabel(driver.persona_type)}</span>
      </div>

      <div className="summary-verdict">
        <span>Current Decision</span>
        <strong>{profile?.headline ?? decisionReasons[0]}</strong>
        <p>{decisionReasons.slice(1, 3).join(" ")}</p>
      </div>

      <div className="summary-decision-stack">
        <div className={`risk-score-block ${risk.className}`}>
          <span>Decision Tier</span>
          <strong>{risk.label}</strong>
          <b>Integrated Score {numberFormatter.format(driver.annual_score.annual_senior_safe_mileage_score)} pts</b>
        </div>

        <div className="premium-delta-block">
          <span>Discount Change</span>
          <strong>{signedPercentPoint(rateDelta)}</strong>
          <small>{percent(comparison.existing_discount_rate_pct)} → {percent(comparison.proposed_discount_rate_pct)}</small>
        </div>

        <div className="summary-action">
          <span>Recommended Action</span>
          <strong>{action}</strong>
        </div>
      </div>
    </section>
  );
}

function DecisionProcessFrame({
  driver,
  zoneMap,
  rows,
  selectedMonth
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  rows: MonthlyEvidence[];
  selectedMonth: number;
}) {
  if (!driver) {
    return <InspectorState title="Waiting for Decision Process" detail="Select a case to view the discount adjustment process." />;
  }

  const comparison = driver.ab_comparison;
  const selectedRow = rows.find((row) => row.month === selectedMonth);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const decision = decisionClass(comparison.annual_decision_signal);
  const riskScore = selectedRow?.out_zone_pattern_change_risk ?? comparison.annual_out_zone_pattern_change_risk;
  const zoneBasis = zoneMap
    ? `P90 ${Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("en-US")}m`
    : "Building Safe Zone";
  const steps = [
    {
      title: "Existing Baseline",
      value: `${translateText(comparison.existing_matched_tier_label)} · ${percent(comparison.existing_discount_rate_pct)}`,
      detail: "Uses only annual mileage and vehicle type",
      icon: Route
    },
    {
      title: "Safe Zone Build",
      value: zoneBasis,
      detail: "Repeated destinations and travel radius over the previous 60 days",
      icon: MapPinned
    },
    {
      title: `Month ${selectedMonth} Change`,
      value: profile ? `${percent(profile.outZoneRatio * 100)}  Out-Zone driving` : "Building monthly evidence",
      detail: profile?.riskPattern ?? "Checks Out-Zone, night-driving, and risk-event changes",
      icon: Activity
    },
    {
      title: "Annual Decision",
      value: `${percent(comparison.proposed_discount_rate_pct)} · ${decision.label}`,
      detail: `Risk Change ${numberFormatter.format(riskScore)} pts`,
      icon: AlertTriangle
    }
  ];

  return (
    <section className="decision-process-frame" aria-label="Discount Adjustment Decision Process">
      <div className="decision-process-copy">
        <p className="eyebrow">Decision Process</p>
        <h2>Even with the same low mileage, Out-Zone risk changes can lead to a different decision</h2>
        <p>
          The existing mileage discount is used as a comparison baseline, while In-Zone/Out-Zone safety and recent risk changes are calculated into an annual integrated score for{" "}
          {personaName(driver.customer_id)} annual decision.
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
  if (!driver) return <InspectorState title="Waiting for Safe Zone Map" detail="Select a case to display the Safe Zone radius and recent external destinations." />;

  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;

  return (
    <section className="decision-map-panel" aria-label="Safe Zone Decision Map">
      <div className="decision-section-head">
        <div>
          <p className="eyebrow">Safe Zone Decision Map</p>
          <h2>House-Centered Safe Zone and Recent Change Destinations</h2>
        </div>
        {profile && zoneMap ? (
          <div className="map-kpis">
            <span>P90 {Math.round(zoneMap.snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("en-US")}m</span>
            <span>Out-Zone {percent(profile.outZoneRatio * 100)}</span>
            <span>Risk Segments {profile.riskEvents} Events</span>
          </div>
        ) : null}
      </div>

      <div className="map-stage">
        {zoneState === "loading" || !zoneMap || !profile ? (
          <p>Loading the Safe Zone map.</p>
        ) : (
          <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
        )}
      </div>

      <div className="map-legend-row">
        <span><i className="legend-home" />House / Safe Zone Center</span>
        <span><i className="legend-normal" />Usual Repeated Route</span>
        <span><i className="legend-out" />Out-Zone Destination</span>
        <span><i className="legend-risk" />Risk Driving Segment</span>
        <b>{selectedMonth} Selected-Month Evidence</b>
      </div>
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
  const profile = driver && zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const tabs = [
    { key: "Overview", label: "Overview" },
    { key: "Monthly Pattern", label: "Monthly Pattern" },
    { key: "Risk Signals", label: "Risk Signals" },
    { key: "Premium Simulation", label: "Annual Discount" },
    { key: "Report", label: "Report" }
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
            <InsightCard title="Classification Reason" value={profile?.headline ?? "Review Monthly Evidence"} detail={profile?.summary ?? driver.care_context.message_focus} />
            <InsightCard title="Safe Zone Change" value={`${numberFormatter.format(selectedRow.out_zone_pattern_change_risk ?? 0)} pts Risk Change`} detail={`Month ${selectedMonth} baseline: ${basisLabel(selectedRow.basis_status)} applied`} />
            <InsightCard title="Product Decision" value={decisionClass(driver.ab_comparison.annual_decision_signal).label} detail={driver.care_context.product_role} />
          </div>
        ) : null}

        {activeTab === "Monthly Pattern" ? (
          <MonthlyPatternChart rows={rows} selectedMonth={selectedMonth} onSelectMonth={onSelectMonth} />
        ) : null}

        {activeTab === "Risk Signals" && driver && selectedRow ? (
          <div className="risk-signal-grid">
            <ScoreMeter label="Mileage Score" value={selectedRow.mileage_score} helper="Annualizes monthly mileage; lower mileage receives a higher score" />
            <ScoreMeter label="In-Zone Safety Score" value={selectedRow.in_zone_safe_driving_score} helper="Higher when harsh braking, speeding, and night-driving ratios are lower In-Zone" />
            <ScoreMeter label="Out-Zone Safety Score" value={selectedRow.out_zone_safe_driving_score} helper="Higher when risk events and night-driving ratios are lower Out-Zone" />
            <ScoreMeter label="Risk Change Index" value={selectedRow.out_zone_pattern_change_risk} inverse helper="Higher when Out-Zone, night-driving, and risk events increase versus the previous 60 days" />
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

        {activeTab === "Report" && profile ? (
          <div className="report-tab-summary">
            <strong>Monthly Report Input Evidence</strong>
            <p>{profile.summary}</p>
            <span>The Decision Panel turns this monthly evidence into an employee report. Monthly values are evidence for the annual decision, not monthly premiums.</span>
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
            <span>Month {row.month}</span>
            <i><b style={{ height: `${Math.max(12, Math.min(92, row.out_zone_pattern_change_risk))}%` }} /></i>
            <b>{numberFormatter.format(row.out_zone_pattern_change_risk)}</b>
          </button>
        );
      })}
    </div>
  );
}

function PremiumSimulation({ driver }: { driver: DriverAnnualSummary }) {
  const comparison = driver.ab_comparison;
  const existingRate = comparison.existing_discount_rate_pct;
  const proposedRate = comparison.proposed_discount_rate_pct;
  const maxRate = Math.max(existingRate, proposedRate, 1);
  return (
    <div className="premium-simulation">
      <div>
        <span>Existing Mileage Rider Rate</span>
        <strong>{percent(existingRate)}</strong>
        <i><b style={{ width: `${(existingRate / maxRate) * 100}%` }} /></i>
      </div>
      <div>
        <span>Proposed Integrated Formula</span>
        <strong>{percent(proposedRate)}</strong>
        <i><b style={{ width: `${(proposedRate / maxRate) * 100}%` }} /></i>
      </div>
      <p>This compares discount rates for the same annual mileage after reflecting Safe Zone stability, Out-Zone safety, and risk-change signals. Actual contract premiums are not calculated.</p>
    </div>
  );
}

function DecisionPanel({
  driver,
  zoneMap,
  selectedMonth,
  loading
}: {
  driver: DriverAnnualSummary | null;
  zoneMap: ZoneMapResponse | null;
  selectedMonth: number;
  loading: boolean;
}) {
  const [state, setState] = useState<"idle" | "streaming" | "ready" | "error">("idle");
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");

  useEffect(() => {
    setState("idle");
    setMarkdown("");
    setError("");
    setProgress("");
  }, [driver?.customer_id, selectedMonth]);

  if (!driver) return <aside className="decision-panel"><InspectorState title="Decision Panel" detail="Select a case to view the final action panel." /></aside>;

  const comparison = driver.ab_comparison;
  const decision = decisionClass(comparison.annual_decision_signal);
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;
  const xaiReasons = topXaiReasons(driver, zoneMap, selectedMonth);
  const rateDelta = comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct;
  const generate = async () => {
    setState("streaming");
    setMarkdown("");
    setError("");
    setProgress("Sending monthly driving evidence to the report API");
    try {
      let next = "";
      await demoApi.streamMonthlyReport(driver.customer_id, selectedMonth, (chunk) => {
        next += chunk;
        setProgress(`Generating: ${latestReportSection(next)}`);
        setMarkdown(next);
      });
      setProgress("Report generation complete");
      setState("ready");
    } catch (reportError) {
      setState("error");
      setError(reportError instanceof Error ? reportError.message : "Report generation failed");
    }
  };

  return (
    <aside className={`decision-panel ${loading ? "is-loading" : ""} ${markdown ? "has-report" : ""}`} aria-label="Decision Panel">
      <div className="decision-panel-head">
        <p className="eyebrow">Decision Panel</p>
        <h2>Final Action</h2>
        <em className={`decision ${decision.className}`}>{decision.label}</em>
      </div>

      <div className="decision-money-stack">
        <div>
          <span>Baseline Mileage Discount</span>
          <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
          <small>{translateText(comparison.existing_matched_tier_label)}</small>
        </div>
        <div>
          <span>Proposed Discount Rate</span>
          <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
          <small>Integrated Score {numberFormatter.format(comparison.annual_senior_safe_mileage_score)} pts</small>
        </div>
        <div className="money-delta">
          <span>Adjustment vs Mileage Baseline</span>
          <strong>{signedPercentPoint(rateDelta)}</strong>
          <small>Calculated separately after actual contract details are finalized</small>
        </div>
      </div>

      <div className="decision-reason-box">
        <span>Adjustment Reason</span>
        <strong>{translateText(profile?.headline ?? driver.care_context.product_role)}</strong>
        <p>{translateText(profile?.summary ?? driver.care_context.message_focus)}</p>
      </div>

      <div className="xai-inspector" aria-label="XAI Decision Evidence">
        <span>XAI Decision Evidence · Month {selectedMonth}</span>
        {xaiReasons.map((reason) => (
          <div key={reason.label}>
            <strong>{reason.label}</strong>
            <i><b style={{ width: `${reason.width}%` }} /></i>
            <em>{reason.detail}</em>
          </div>
        ))}
      </div>

      <button className="report-button" type="button" onClick={generate} disabled={state === "streaming"}>
        {state === "streaming" ? <RefreshCcw size={15} /> : <FileText size={15} />}
        {state === "streaming" ? "Generating Report" : `Generate Month ${selectedMonth} Report`}
      </button>

      {state === "error" ? <p className="error-copy">{error}</p> : null}
      {progress ? <p className="report-progress">{progress}</p> : null}
      {markdown ? (
        <div className="report-popout" role="status" aria-live="polite">
          <div className="report-popout-head">
            <div>
              <span>Employee Report for Insurance Staff</span>
              <strong>{personaName(driver.customer_id)} · {selectedMonth}Monthly Evidence Analysis</strong>
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
              {state === "streaming" ? "Generating" : "Done"}
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
    "Monthly Conclusion Summary",
    "Annual Formula Reflection",
    "Safe Zone Decision Evidence",
    "Monthly Driving Pattern",
    "Key XAI Drivers",
    "Consultation and Care Actions",
    "Review Limits and Follow-Up Items"
  ];
  const known = knownSections.filter((section) => markdown.includes(section)).at(-1);
  if (known) return known;
  const matches = [...markdown.matchAll(/^##\s+\d+\.\s+(.+)$/gm)];
  const latest = matches.at(-1)?.[1]?.trim();
  return latest && latest.length > 6 ? latest : "Receiving report draft";
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
  const inZone = monthly?.in_zone_safe_driving_score ?? driver.annual_score.annual_in_zone_safe_driving_score;
  const outZone = monthly?.out_zone_safe_driving_score ?? driver.annual_score.annual_out_zone_safe_driving_score;
  const mileage = monthly?.mileage_score ?? driver.annual_score.annual_mileage_score;
  const tripCount = zoneMap?.snapshot.basis_window.scored_trip_count ?? driver.annual_score.annual_trip_count;
  return [
    {
      label: "Out-Zone Risk Change",
      width: Math.max(8, Math.min(100, risk)),
      detail: `${numberFormatter.format(risk)} pts`
    },
    {
      label: "In-Zone Safety",
      width: Math.max(8, Math.min(100, inZone)),
      detail: `${numberFormatter.format(inZone)} pts`
    },
    {
      label: "Out-Zone Safety",
      width: Math.max(8, Math.min(100, outZone)),
      detail: `${numberFormatter.format(outZone)} pts`
    },
    {
      label: "Mileage Score",
      width: Math.max(8, Math.min(100, mileage)),
      detail: `${numberFormatter.format(mileage)} pts · ${tripCount} Events`
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
    <section className="panel problem-frame" aria-label="Problem and Existing Method Comparison">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Problem</p>
          <h2>Different risk patterns are mixed within the same mileage discount band</h2>
        </div>
        <span className="count-badge">30 Virtual Cases</span>
      </div>
      <div className="formula-compare">
        <div>
          <span>Existing Mileage Rider</span>
          <strong>Annual Mileage + Vehicle Type</strong>
          <p>Drivers in the same band receive the same discount even when Safe Zone and risk-change patterns differ.</p>
        </div>
        <ArrowRight size={18} />
        <div>
          <span>Proposed Integrated Formula</span>
          <strong>Mileage + In/Out-Zone Safety + Risk Change</strong>
          <p>Distinguishes Favorable, Standard, and Preventive Care within low-mileage customers.</p>
        </div>
      </div>
      <div className="metric-strip">
        <Metric label="Existing Avg. Discount" value={percent(summary.avg_existing_discount_rate_pct)} />
        <Metric label="Proposed Avg. Discount" value={percent(summary.avg_proposed_discount_rate_pct)} />
        <Metric label="Average Adjustment vs Baseline" value={signedPercentPoint(summary.avg_proposed_discount_rate_pct - summary.avg_existing_discount_rate_pct)} />
        <Metric label="Decision Tier" value="Favorable · Standard · Preventive Care" tone="care" />
        <Metric label="Average Integrated Score" value={`${numberFormatter.format(summary.avg_annual_score)} pts`} tone="good" />
      </div>
      <div className="tier-proof">
        <div>
          <span>Annual Discount Result Comparison</span>
          <strong>Existing Avg. {percent(summary.avg_existing_discount_rate_pct)} / Proposed Avg. {percent(summary.avg_proposed_discount_rate_pct)}</strong>
          <p>
            The same annual data for 30 drivers was applied to both formulas. This shows comparable discount differences without actual contract premiums.
          </p>
        </div>
        {driver ? (
          <div className="current-case">
            <span>Current Selection</span>
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
  return (
    <section className="panel blueprint-panel" aria-label="Data Generation Method and Final Formula">
      <div className="panel-head">
        <div>
          <p className="eyebrow">AI Usage and Formula Rationale</p>
          <h2>AI does not decide premiums directly. It supports Safe Zone generation, candidate formula search, and decision explanation.</h2>
        </div>
        <span className="count-badge">Four-Factor Weight Comparison</span>
      </div>

      <div className="ai-proof-row" aria-label="Where AI Is Used">
        <div>
          <span>AI 1</span>
          <strong>Automated Safe Zone Generation</strong>
          <p>DBSCAN clusters destinations from the first 60 days, while the P90 radius absorbs small variations such as parking and minor detours.</p>
        </div>
        <div>
          <span>AI 2</span>
          <strong>Four-Factor Weight Selection</strong>
          <p>Multiple candidate weight sets are compared to decide how much mileage, In-Zone safety, Out-Zone safety, and risk change should contribute to the final formula.</p>
        </div>
        <div>
          <span>AI 3</span>
          <strong>XAI + Employee Report</strong>
          <p>XAI extracts how the four factors influenced the decision, and the LLM is used only to generate readable explanations for insurance staff.</p>
        </div>
      </div>

      <div className="blueprint-flow" aria-label="Formula Design Flow">
        <div className="flow-step">
          <span>1</span>
          <strong>Build Senior Driving Scenarios</strong>
          <p>Six driver types and a total of {directory.summary.customer_count} drivers are assigned destinations such as home, hospital, mart, family house, nearby areas, and different outing tendencies.</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>2</span>
          <strong>Build Safe Zones from the First 60 Days</strong>
          <p>DBSCAN clusters repeated destinations, and the P90 radius includes minor detours and parking movements within the Safe Zone.</p>
        </div>
        <ArrowRight size={18} />
        <div className="flow-step">
          <span>3</span>
          <strong>Compare 12 Evaluation Months under the Same Conditions</strong>
          <p>The same annual driving data is applied to the existing mileage formula and the proposed formula to compare discount changes and classification results.</p>
        </div>
      </div>

      <div className="formula-workbench">
        <div className="formula-decision-card">
          <div className="blueprint-title">
            <BarChart3 size={17} />
            <strong>Final Integrated Score Formula</strong>
          </div>
          <p className="formula-lead">
            The mileage-based standard is retained, while Safe Zone indicators are added to distinguish stable drivers from Preventive Care candidates within the same low-mileage group.
          </p>
          <div className="weight-layout" aria-label="Final Formula Weights">
            <div className="weight-block mileage">
              <span>Mileage</span>
              <strong>30%</strong>
              <small>Maintains the low-mileage benefit principle</small>
            </div>
            <div className="weight-block in-zone">
              <span>In-Zone Safety</span>
              <strong>30%</strong>
              <small>Stable driving within the familiar radius</small>
            </div>
            <div className="weight-block out-zone">
              <span>Out-Zone Safety</span>
              <strong>20%</strong>
              <small>Does not penalize Out-Zone driving itself</small>
            </div>
            <div className="weight-block risk">
              <span>Risk-Change Adjustment</span>
              <strong>20%</strong>
              <small>Score decreases as risk-change signals increase</small>
            </div>
          </div>
          <div className="formula-box simplified">
            <span>Calculation Method</span>
            <strong>Integrated Score = Mileage Score × 0.30 + In-Zone Safety × 0.30 + Out-Zone Safety × 0.20 + (100 - Risk Change) × 0.20</strong>
          </div>
        </div>

        <div className="formula-evidence-card">
          <div className="blueprint-title">
            <ShieldCheck size={17} />
            <strong>Why This Weight Set Was Selected</strong>
          </div>
          <div className="evidence-checklist">
            <div>
              <span>Rate Stability</span>
              <strong>Checks whether the average discount change remains within an explainable range</strong>
              <p>Both formulas are calculated and compared with the existing discount system to confirm that the change is explainable.</p>
            </div>
            <div>
              <span>Fairness Condition</span>
              <strong>No penalty solely for driving outside the Safe Zone</strong>
              <p>Repeated external destinations and stable driving should still qualify for Standard or Favorable decisions.</p>
            </div>
            <div>
              <span>Prevention Condition</span>
              <strong>Drivers with rising risk signals are separated into Preventive Care</strong>
              <p>Cases with recent increases in Out-Zone driving, night driving, and harsh braking are linked to reports and preventive guidance.</p>
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
    return <InspectorState title="Waiting for Profile Landing" detail="Select a senior profile on the left to update this area for that case." />;
  }

  const annual = driver.annual_score;
  const comparison = driver.ab_comparison;
  const decision = decisionClass(annual.annual_decision_signal);
  const destinations = destinationLabels(driver);
  const formulaRows = [
    { label: "Mileage", score: annual.annual_mileage_score, weight: selectedPolicy.weights.mileage },
    { label: "In-Zone", score: annual.annual_in_zone_safe_driving_score, weight: selectedPolicy.weights.inZone },
    { label: "Out-Zone", score: annual.annual_out_zone_safe_driving_score, weight: selectedPolicy.weights.outZone },
    { label: "100-Risk", score: 100 - annual.annual_out_zone_pattern_change_risk, weight: selectedPolicy.weights.riskChange }
  ];
  const profile = zoneMap ? deriveEvidenceProfile(driver, zoneMap.snapshot) : null;

  return (
    <section className={`panel profile-landing ${driverState === "loading" ? "is-loading" : ""}`} aria-label="Driver Safe Zone Analysis">
      <div className="profile-hero">
        <div>
          <p className="eyebrow">Driver Safe Zone Analysis</p>
          <h2>
            {personaName(driver.customer_id)} · {personaTypeLabel(driver.persona_type)}
          </h2>
          <p>{translateText(driver.care_context.message_focus)}</p>
        </div>
        <em className={`decision ${decision.className}`}>{decision.label}</em>
      </div>

      <div className="profile-landing-grid">
        <div className="profile-card map-card">
          <div className="map-card-head">
            <div>
              <p className="eyebrow">Safe Zone Visualization</p>
              <h3>Month {selectedMonth} Destination Coordinate Analysis</h3>
              <span>DBSCAN Safe Zone + P90 Radius + Selected-Month Trip Interpretation</span>
            </div>
            {profile ? (
              <div className="map-stat-row">
                <b>P90 {Math.round(zoneMap?.snapshot.living_zone.buffer.departure_p90_threshold_m ?? 0).toLocaleString("en-US")}m</b>
                <b>Out-Zone {percent(profile.outZoneRatio * 100)}</b>
                <b>{profile.riskEvents} Risk Events</b>
              </div>
            ) : null}
          </div>
          {zoneState === "loading" || !zoneMap || !profile ? (
            <p>Loading the Safe Zone map.</p>
          ) : (
            <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
          )}
        </div>

        <div className="profile-card driver-card">
          <div className="blueprint-title">
            <UserRound size={17} />
            <strong>Senior Driver Profile</strong>
          </div>
          <div className="trait-list compact">
            <Fact label="Outing Frequency" value={driver.living_pattern.weekly_outing_frequency_ko} />
            <Fact label="Main Destinations" value={destinations.join(", ")} />
            <Fact label="Out-Zone Tendency" value={driver.living_pattern.outer_trip_tendency} />
            <Fact label="Risk-Event Tendency" value={driver.living_pattern.risk_behavior_tendency} />
            <Fact label="Product Meaning" value={driver.care_context.product_role} />
          </div>
        </div>

        <div className="profile-card formula-card profile-formula-card">
          <div className="blueprint-title">
            <BarChart3 size={17} />
            <strong>Formula Application for This Profile</strong>
          </div>
          <div className="same-driver-compare">
            <div>
              <span>Existing Mileage Rider</span>
              <strong>{percent(comparison.existing_discount_rate_pct)}</strong>
              <small>{translateText(comparison.existing_matched_tier_label)}</small>
            </div>
            <ArrowRight size={18} />
            <div>
              <span>Proposed Formula</span>
              <strong>{percent(comparison.proposed_discount_rate_pct)}</strong>
              <small>Integrated Score {annual.annual_senior_safe_mileage_score} pts</small>
            </div>
          </div>
          <div className="formula-substitution profile">
            {formulaRows.map((row) => (
              <div key={row.label}>
                <span>{row.label}</span>
                <strong>
                  {numberFormatter.format(row.score)} × {row.weight.toFixed(2)}
                </strong>
                <em>{numberFormatter.format(row.score * row.weight)}</em>
              </div>
            ))}
            <div className="formula-total">
              <span>Integrated Score</span>
              <strong>{numberFormatter.format(annual.annual_senior_safe_mileage_score)} pts</strong>
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
        <span>Candidate Formula Comparison Result</span>
        <strong>The final weights are shown in the formula, while this section explains why other candidates were rejected.</strong>
      </div>

      <div className="candidate-comparison-grid" aria-label="Candidate Formula Comparison">
        <div className="rejected">
          <span>Mileage-Centered Option</span>
          <strong>Rejected</strong>
          <p>Too similar to the existing mileage discount, making it difficult to explain low-mileage drivers with rising risk signals.</p>
        </div>
        <div className="selected">
          <span>Balanced Option</span>
          <strong>Selected</strong>
          <p>Preserves the low-mileage benefit while incorporating In-Zone/Out-Zone safety and risk-change signals.</p>
        </div>
        <div className="deferred">
          <span>Risk-Change Heavy Option</span>
          <strong>On Hold</strong>
          <p>Put on hold because it may unfairly penalize repeated external destinations.</p>
        </div>
      </div>

      <div className="selection-criteria">
        <span>Selection Criteria</span>
        <strong>Moderate average discount change · Separates risk-change drivers · Prevents misclassification of stable Out-Zone drivers</strong>
      </div>
    </div>
  );
}

function PersonaMatrix({ summaries, selectedOption }: { summaries: PersonaSummary[]; selectedOption?: DriverOption }) {
  return (
    <section className="panel persona-matrix" aria-label="Persona Type Comparison">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Persona Types</p>
          <h2>Six driver types create different decision scenarios</h2>
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
              Avg. {numberFormatter.format(summary.avg_annual_distance_km)}km · {formatDecisionCounts(summary.decision_counts)}
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
  onSelectMonth
}: {
  rows: MonthlyEvidence[];
  selectedMonth: number;
  loading: boolean;
  onSelectMonth: (month: number) => void;
}) {
  const selectedRow = rows.find((row) => row.month === selectedMonth) ?? rows[0];
  const selectedMeta = selectedRow ? interpretationClass(selectedRow.dominant_interpretation) : null;
  const monthlyIntegratedScore = selectedRow
    ? selectedRow.monthly_integrated_evidence_score ?? monthlyIntegratedEvidenceScore(selectedRow)
    : 0;

  return (
    <section className={`panel evidence-lane ${loading ? "is-loading" : ""}`} aria-label="Monthly Four-Factor Evidence">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Monthly Evidence</p>
          <h2>Shows which evidence accumulated into the annual decision over 12 months</h2>
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
            <span>Selected Month</span>
            <strong>
              {selectedRow.service_month} · {selectedMeta.label}
            </strong>
            <p>
              {numberFormatter.format(selectedRow.monthly_total_distance_km)} km driven, {basisLabel(selectedRow.basis_status)} was used for the Safe Zone decision.
              The values below are evidence scores accumulated into the annual formula, not monthly discount rates.
            </p>
          </div>
          <div className="score-meter-grid">
            <ScoreMeter label="Mileage Score" value={selectedRow.mileage_score} helper="Higher when monthly mileage is lower" />
            <ScoreMeter label="In-Zone Safety Score" value={selectedRow.in_zone_safe_driving_score} helper="Higher when In-Zone risk events are lower" />
            <ScoreMeter label="Out-Zone Safety Score" value={selectedRow.out_zone_safe_driving_score} helper="Higher when Out-Zone driving remains stable" />
            <ScoreMeter label="Risk Change Index" value={selectedRow.out_zone_pattern_change_risk} inverse helper="Higher means more attention is needed" />
          </div>
          <p className="score-legend-copy">
            The four values are standardized 0-100 inputs for the annual formula, not monthly premiums. Safety scores are better when higher, while the risk-change index is more stable when lower.
          </p>
          <div className="monthly-integrated-formula" aria-label="Monthly Integrated Evidence Score Formula">
            <span>Monthly Integrated Evidence Score</span>
            <strong>{numberFormatter.format(monthlyIntegratedScore)} pts</strong>
            <p>Low Mileage 30% + In-Zone Safety 30% + Out-Zone Safety 20% + (100 - Risk Change) 20%</p>
            <small>This score does not directly determine a monthly premium; 12 months of evidence are aggregated to compare the annual proposed discount rate.</small>
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
              className={`month-card ${meta.className} ${selectedMonth === row.month ? "selected" : ""}`}
              onClick={() => onSelectMonth(row.month)}
            >
              <span>Month {row.month}</span>
              <strong>{numberFormatter.format(row.monthly_total_distance_km)}km</strong>
              <small>{basisLabel(row.basis_status)}</small>
              <em>Change {numberFormatter.format(row.out_zone_pattern_change_risk)} pts</em>
              <i style={{ width: `${Math.min(100, row.out_zone_pattern_change_risk)}%` }} />
            </button>
          );
        })}
      </div>
    </section>
  );
}

function AnnualComparison({ driver, loading }: { driver: DriverAnnualSummary | null; loading: boolean }) {
  if (!driver) return <InspectorState title="Loading Annual Formula" detail="Loading the annual comparison for the selected case." />;
  const comparison = driver.ab_comparison;
  const decision = decisionClass(comparison.annual_decision_signal);

  return (
    <section className={`panel side-panel ${loading ? "is-loading" : ""}`} aria-label="Annual Formula Comparison">
      <div className="panel-head compact">
        <div>
          <p className="eyebrow">Annual Formula Comparison</p>
          <h2>Annual Discount Basis</h2>
        </div>
        <em className={`decision ${decision.className}`}>{decision.label}</em>
      </div>
      <div className="premium-grid">
        <div>
          <span>Annual Evaluation Mileage</span>
          <strong>{numberFormatter.format(comparison.annual_total_distance_km)}km</strong>
        </div>
        <div>
          <span>Existing Discount Band</span>
          <strong>{translateText(comparison.existing_matched_tier_label)}</strong>
        </div>
      </div>
      <ComparisonRow title="Existing Mileage Rider" subtitle={comparison.existing_matched_tier_label} rate={comparison.existing_discount_rate_pct} />
      <ComparisonRow title="Proposed Integrated Formula" subtitle={`Integrated Score ${numberFormatter.format(comparison.annual_senior_safe_mileage_score)} pts`} rate={comparison.proposed_discount_rate_pct} />
      <div className="delta-box">
        <span>Adjustment vs Mileage Baseline</span>
        <strong>{signedPercentPoint(comparison.proposed_discount_rate_pct - comparison.existing_discount_rate_pct)}</strong>
        <small>Monthly indicators are used only as evidence; the final comparison is calculated on the annual discount basis.</small>
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
  if (!driver) return <InspectorState title="Loading Safe Zone Evidence" detail="Loading the driver profile." />;
  if (state === "loading" || !zoneMap) return <InspectorState title={`${selectedMonth} Safe Zone Loading`} detail="Loading destination and risk-event evidence for the selected month." />;
  if (state === "error") return <InspectorState title="Safe Zone Evidence Error" detail={error} />;

  const profile = deriveEvidenceProfile(driver, zoneMap.snapshot);

  return (
    <section className="panel side-panel evidence-profile" aria-label="Selected-Month Safe Zone Evidence">
      <div className="panel-head compact">
        <div>
          <p className="eyebrow">Selected Month Evidence</p>
          <h2>{zoneMap.snapshot.service_month} Case Analysis</h2>
        </div>
        <MapPinned size={18} />
      </div>
      <div className="dynamic-copy">
        <strong>{profile.headline}</strong>
        <p>{profile.summary}</p>
      </div>
      <GeoLivingZoneCanvas driver={driver} snapshot={zoneMap.snapshot} profile={profile} />
      <div className="derived-grid">
        <Fact label="Main Destinations" value={profile.topDestinations.join(", ")} />
        <Fact label="Out-Zone Driving Pattern" value={profile.outerPattern} />
        <Fact label="Risk Events" value={profile.riskPattern} />
        <Fact label="Decision Basis" value={basisLabel(zoneMap.snapshot.basis_window.basis_status)} />
      </div>
      <DestinationEvidence trips={zoneMap.snapshot.trip_interpretations} />
    </section>
  );
}

function GeoLivingZoneCanvas({ driver, snapshot, profile }: { driver: DriverAnnualSummary; snapshot: ZoneSnapshot; profile: DerivedProfile }) {
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
  const p90Radius = Math.max(58, Math.min(128, (primaryCluster?.p90_radius_m ?? snapshot.living_zone.buffer.departure_p90_threshold_m) / 10));
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
      <svg className="geo-map" viewBox={`0 0 ${mapWidth} ${mapHeight}`} role="img" aria-label="Safe Zone Map Based on Actual Coordinates">
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
      <text className="geo-title" x="42" y="42">Safe Zone Decision Map</text>
      <text className="geo-subtitle" x="42" y="63">Actual destination coordinates · Baseline Safe Zone · Recent change destinations · Risk driving segments</text>

      <g className="geo-core-ring">
        <circle cx={clusterCenter.x} cy={clusterCenter.y} r={p90Radius * 1.55} />
        <circle cx={clusterCenter.x} cy={clusterCenter.y} r={p90Radius} />
        <circle cx={clusterCenter.x} cy={clusterCenter.y} r={Math.max(38, p90Radius * 0.48)} />
      </g>

      {snapshot.living_zone.clusters.slice(1).map((cluster, index) => {
        const point = projector(cluster.center_longitude, cluster.center_latitude);
        const radius = Math.max(36, Math.min(92, cluster.p90_radius_m / 11));
        return (
          <g key={cluster.cluster_id} className="geo-cluster">
            <circle cx={point.x} cy={point.y} r={radius} />
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
          <text x={homePoint.x} y={homePoint.y - 27} textAnchor="middle">House</text>
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
        <rect width="210" height="34" rx="9" />
        <text x="13" y="22">P90 {Math.round(snapshot.living_zone.buffer.departure_p90_threshold_m).toLocaleString("en-US")}m Safe Zone</text>
      </g>
      <g className="geo-badge risk" transform="translate(268 500)">
        <rect width="260" height="34" rx="9" />
        <text x="13" y="22">Out-Zone {percent(profile.outZoneRatio * 100)} · {profile.riskEvents} Risk Events</text>
      </g>
      </svg>
      <aside className="geo-detail-panel" aria-label="Safe Zone Map Evidence Details">
        <span>Destination Evidence</span>
        {visibleDestinations.map(({ group, destination }, index) => {
          const meta = interpretationClass(group.dominant);
          return (
            <div key={`geo-detail-${group.key}`} className={`geo-detail-row ${meta.className}`}>
              <b>{index + 1}</b>
              <strong>{destinationTypeLabel(group.key)}</strong>
              <small>{meta.label} · {group.count} Visits</small>
              <em>{group.distanceKm.toFixed(0)}km · {group.riskEvents} Risk Events</em>
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
        <span>Selected Month Destination Evidence</span>
        <span>{trips.length} Trips</span>
      </div>
      {grouped.map((item) => {
        const meta = interpretationClass(item.dominant);
        return (
          <div className="destination-row" key={item.label}>
            <span>
              <strong>{item.label}</strong>
              <small>{item.count} Trips · {item.riskEvents} Risk Events · {item.nightTrips} Night Trips</small>
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

  if (!driver) return <InspectorState title="Waiting for Report" detail="Select a driver to generate the employee report." />;

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
      setError(reportError instanceof Error ? reportError.message : "Report generation failed");
    }
  };

  return (
    <section className="panel side-panel report-panel" aria-label="Employee Report">
      <div className="panel-head compact">
        <div>
          <p className="eyebrow">Employee Report</p>
          <h2>Evidence-Based Explanation Generation</h2>
        </div>
        <FileText size={18} />
      </div>
      <div className="llm-boundary">
        <ShieldCheck size={16} />
        <span>The report explains monthly evidence in employee-facing language. Actual contract premium calculation is outside this demo scope.</span>
      </div>
      {profile ? (
        <div className="report-input">
          <span>Generation Input</span>
          <strong>{profile.headline}</strong>
          <small>{profile.topDestinations.join(", ")} · {profile.riskPattern}</small>
        </div>
      ) : null}
      <button className="report-button" type="button" onClick={generate} disabled={state === "streaming"}>
        {state === "streaming" ? <RefreshCcw size={15} /> : <FileText size={15} />}
        {state === "streaming" ? "Generating" : `Generate Month ${selectedMonth} Report`}
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

function ScoreMeter({ label, value, inverse = false, helper }: { label: string; value: number; inverse?: boolean; helper?: string }) {
  const normalized = Math.max(0, Math.min(100, value));
  const tone = inverse && normalized >= careReviewRiskThreshold ? "risk" : normalized >= 70 ? "good" : "base";
  return (
    <div className={`score-meter ${tone}`}>
      <span>{translateText(label)}</span>
      <strong>{numberFormatter.format(value)} pts</strong>
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

function deriveEvidenceProfile(driver: DriverAnnualSummary, snapshot: ZoneSnapshot): DerivedProfile {
  const trips = snapshot.trip_interpretations;
  const grouped = Object.values(groupTrips(trips)).sort((a, b) => b.count - a.count);
  const topDestinations = grouped.slice(0, 3).map((item) => item.label);
  const riskEvents = grouped.reduce((sum, item) => sum + item.riskEvents, 0);
  const nightTrips = trips.reduce((sum, trip) => sum + Number(trip.night_drive_flag), 0);
  const repeatTrips = trips.reduce((sum, trip) => sum + Number(trip.route_repeat_flag), 0);
  const newDestinationTrips = trips.reduce((sum, trip) => sum + Number(trip.new_destination_flag), 0);
  const repeatRate = trips.length ? repeatTrips / trips.length : 0;
  const outZoneRatio = snapshot.monthly_evidence.out_zone_distance_ratio;
  const riskScore = snapshot.scores.out_zone_pattern_change_risk;

  let headline = "Repeated In-Zone Driving";
  if (riskScore >= careReviewRiskThreshold) headline = "Out-Zone Risk Change Detected in the Selected Month";
  else if (riskEvents > 0 && riskScore < preferredRiskCeiling) headline = "Risk Events Observed, But Change Risk Is Low";
  else if (outZoneRatio > 0.25 && repeatRate > 0.55 && riskEvents <= trips.length * 0.2) headline = "Repeated Out-Zone Driving Is Stable";
  else if (newDestinationTrips > 0 && outZoneRatio > 0.15) headline = "New External Destination Observed";
  else if (driver.persona_type === "medical_visit_pattern") headline = "Repeated Hospital Visits Observed";
  else if (driver.persona_type === "irregular_family_support") headline = "Family-Care Out-Zone Travel Observed";

  const outerPattern =
    outZoneRatio < 0.12
      ? "Mostly In-Zone"
      : repeatRate >= 0.6
        ? "Repeated External Destinations"
        : newDestinationTrips > 0
          ? "Includes New External Destinations"
          : "Dispersed External Travel";
  const riskPattern =
    riskEvents === 0
      ? "Almost No Risk Events"
      : riskScore >= careReviewRiskThreshold
        ? `${riskEvents} risk events · high change risk`
        : `${riskEvents} risk events observed, but change risk is ${numberFormatter.format(riskScore)} pts, so no sharp spike signal is detected${nightTrips > 0 ? ` · ${nightTrips} night trips` : ""}`;

  return {
    headline,
    summary: `In ${snapshot.service_month}, visits center on ${topDestinations.join(", ")}, and the Out-Zone share is ${percent(outZoneRatio * 100)}. Interpreted as: ${outerPattern}; ${riskPattern}.`,
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
      label: destinationTypeLabel(trip.destination_type),
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
  return rows.reduce((best, row) => (row.out_zone_pattern_change_risk > best.out_zone_pattern_change_risk ? row : best)).month;
}

function monthlyIntegratedEvidenceScore(row: MonthlyEvidence) {
  const score =
    row.mileage_score * selectedPolicy.weights.mileage +
    row.in_zone_safe_driving_score * selectedPolicy.weights.inZone +
    row.out_zone_safe_driving_score * selectedPolicy.weights.outZone +
    (100 - row.out_zone_pattern_change_risk) * selectedPolicy.weights.riskChange;
  return Math.max(0, Math.min(100, score));
}

function matchesCaseFilter(option: DriverOption, filter: string) {
  if (filter === "all") return true;
  return decisionClass(option.annual_decision_signal).label === filter;
}

function personaName(customerId: string) {
  return `${personaNames[personaIndex(customerId)] ?? "Senior Driver"}`;
}

function personaIndex(customerId: string) {
  const matched = customerId.match(/(\d+)$/);
  return matched ? Math.max(0, Number(matched[1]) - 1) : 0;
}

function caseNo(customerId: string) {
  return `Case ${String(personaIndex(customerId) + 1).padStart(2, "0")}`;
}

function personaAge(customerId: string) {
  const ages = [72, 76, 69, 81, 74, 78, 71, 83, 75, 80, 77, 73, 82, 70, 79, 84, 76, 72, 68, 81, 75, 79, 73, 85, 77, 74, 82, 71, 78, 80];
  return ages[personaIndex(customerId)] ?? 76;
}

function personaResidence(driver: DriverAnnualSummary) {
  const districts = [
    "Seoul Gangnam",
    "Seoul Songpa",
    "Seoul Nowon",
    "Seoul Eunpyeong",
    "Seoul Gangseo",
    "Gyeonggi Seongnam",
    "Gyeonggi Goyang",
    "Gyeonggi Suwon",
    "Incheon Namdong",
    "Seoul Geumcheon"
  ];
  return districts[personaIndex(driver.customer_id) % districts.length];
}

function caseType(option: DriverOption) {
  return personaTypeLabel(option.persona_type);
}

function coreChangeTag(personaType: string) {
  const tags: Record<string, string> = {
    stable_local_low_mileage: "Repeated Stability",
    stable_outer_safe: "Out-Zone Stable",
    recent_outer_risk_change: "Expanded Radius",
    in_zone_risky_low_mileage: "In-Zone Risk",
    medical_visit_pattern: "Repeated Hospital",
    irregular_family_support: "Irregular Out-Zone"
  };
  return tags[personaType] ?? "Pattern Observed";
}

function riskBadgeForOption(option: DriverOption) {
  return decisionClass(option.annual_decision_signal);
}

function riskBadgeForDriver(driver: DriverAnnualSummary) {
  return decisionClass(driver.ab_comparison.annual_decision_signal);
}

function recommendedAction(driver: DriverAnnualSummary, selectedRow?: MonthlyEvidence) {
  if (driver.ab_comparison.preventive_care_required) return "Send preventive care guidance and a safe-driving report";
  if ((selectedRow?.out_zone_pattern_change_risk ?? 0) >= 50) return "Recheck change magnitude next month";
  if (decisionClass(driver.ab_comparison.annual_decision_signal).label === "Favorable") return "Candidate for continued Favorable status";
  return "Maintain Standard status and monitor monthly";
}

function personaTone(type: string) {
  if (type === "recent_outer_risk_change" || type === "in_zone_risky_low_mileage") return "risk";
  if (type === "medical_visit_pattern") return "care";
  if (type === "stable_outer_safe" || type === "stable_local_low_mileage") return "safe";
  return "base";
}

function personaNarrative(type: string) {
  const text: Record<string, string> = {
    stable_local_low_mileage: "Reference group likely to qualify as Favorable under both existing mileage and proposed formulas due to short repeated trips",
    stable_outer_safe: "Fairness test group: Out-Zone travel exists, but repeated destinations and low risk events should prevent misclassification",
    recent_outer_risk_change: "Core group needing Preventive Care: low mileage but rising external destinations and risk events in the second half",
    in_zone_risky_low_mileage: "Low-mileage blind-spot group: harsh braking and speeding accumulate even within the Safe Zone",
    medical_visit_pattern: "Group where repeated hospital/pharmacy visits should be observed as a candidate Safe Zone, not automatically treated as external risk",
    irregular_family_support: "Observation group with legitimate but irregular external travel for family care"
  };
  return text[type] ?? "Case group where annual decisions vary based on monthly driving evidence";
}

function destinationLabels(driver: DriverAnnualSummary) {
  const fallback: Record<string, string> = {
    clinic: "Hospital",
    family: "Family House",
    family_home: "Family House",
    home: "House",
    leisure: "Nearby Outing",
    market: "Mart",
    pharmacy: "Pharmacy",
    unknown_outer: "New External Destination"
  };

  return driver.living_pattern.primary_destinations.map((key) => {
    const destination = driver.living_destinations[key] ?? driver.living_destinations[`${key}_home`];
    return destinationTypeLabel(key) ?? translateText(destination?.label_ko ?? fallback[key] ?? key);
  });
}

function basisLabel(value: string) {
  if (value === "pre_policy_60_day_dbscan") return "Pre-policy 60-day baseline";
  if (value === "rolling_60_day_dbscan") return "Rolling previous 60 days";
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
