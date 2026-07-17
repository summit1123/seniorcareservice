/**
 * 케어 리포트 확장 모달 — 생성 연출 → 직원 검수 → 승인 → 모바일(가족) 화면의 연속 흐름.
 *
 * 0단계(생성): AI 서사 요청이 진행되는 동안 생성 오브+단계 티커를 보여주고,
 *   응답이 확정(성공 또는 로컬 폴백)되는 순간 리포트 전체(차트 포함)가 한꺼번에
 *   스태거로 등장한다 — "위에만 찔끔 바뀌는" 문제를 구조적으로 제거.
 * 1단계(직원): 마스트헤드(리포트 번호·관찰 기간·커버리지·생성 모드) + 01~05
 *   섹션 넘버링의 리포트 구조. AI가 쓴 문장에는 AI 배지가 붙는다.
 * 2단계(가족): 폰 프레임 안 가족 앱 — 상태바·아바타·하단 내비, 스크롤바 없는
 *   드래그 스크롤(인앱 뷰어 감각).
 *
 * 숫자는 전부 로컬 결정론 빌더(care-report.ts)가 채우고, 서버(LLM)는 서사 필드만
 * 덧입힌다 — 실패해도 로컬 서사로 데모가 계속된다.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  X, FileText, CheckCircle2, Smartphone, ArrowLeft, RefreshCcw, Sparkles,
  Home, ScrollText, Gift, Settings
} from "lucide-react";
import { t, tf } from "./i18n";
import { buildLocalCareReport, type CareReport } from "./care-report";
import { enrichCareReport } from "./api";
import type { DriverAnnualSummary, MonthlyEvidence } from "./types";
import type { ProductRules } from "./gaip-types";

const numberFmt = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });

/** 생성 단계 티커 — 실제 파이프라인 순서(엔진 값 → 기준선 → 규칙 → 서사)를 그대로 읽어준다. */
const GEN_STEPS = [
  "엔진 확정값 불러오는 중",
  "기준선 대비 변화 계산 중",
  "케어 신호·지원 규칙 대조 중",
  "AI 서사 작성 중"
] as const;

/** 통합점수 카운트업 — 값이 AI 스트림처럼 차오르는 연출(값 자체는 엔진 확정값). */
function useCountUp(target: number | null, ms = 1100): number | null {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (target === null) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setValue(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return target === null ? null : value;
}

/** 선택 월 이후(미래)는 리포트에 존재하지 않는다 — 기준선 2개월 + 선택 월까지만. */
function visibleTimeline(report: CareReport) {
  const selIdx = report.pattern_timeline.findIndex((m) => m.selected);
  return selIdx >= 0 ? report.pattern_timeline.slice(0, selIdx + 1) : report.pattern_timeline;
}

function SectionMark({ n, label, ai }: { n: string; label: string; ai?: boolean }) {
  return (
    <div className="care-sec">
      <i>{n}</i>
      <span>{label}</span>
      {ai ? <em className="ai-chip"><Sparkles size={10} /> {t("AI 생성")}</em> : null}
    </div>
  );
}

function ContributionDonut({ report }: { report: CareReport }) {
  const animated = useCountUp(report.verdict.integrated_score);
  const entries = report.weight_contributions.filter((c) => c.contribution !== null) as Array<{
    key: string; label_ko: string; contribution: number; weight_pct: number; score: number | null;
  }>;
  const total = entries.reduce((sum, c) => sum + c.contribution, 0);
  const R = 52;
  const CIRC = 2 * Math.PI * R;
  let offset = 0;
  const tones = ["#0b63f6", "#5bc2e7", "#4c63b6", "#c2762b"];
  return (
    <div className="care-donut">
      <svg viewBox="0 0 140 140" role="img" aria-label={t("지표별 기여 분해")}>
        <circle cx="70" cy="70" r={R} className="care-donut-track" />
        {entries.map((c, i) => {
          const frac = total > 0 ? c.contribution / total : 0;
          const dash = frac * CIRC;
          const el = (
            <circle
              key={c.key}
              cx="70" cy="70" r={R}
              stroke={tones[i % tones.length]}
              strokeDasharray={`${dash} ${CIRC - dash}`}
              strokeDashoffset={-offset}
              className="care-donut-seg"
            />
          );
          offset += dash;
          return el;
        })}
        <text x="70" y="66" textAnchor="middle" className="care-donut-score">
          {animated === null ? "—" : numberFmt.format(animated)}
        </text>
        <text x="70" y="84" textAnchor="middle" className="care-donut-caption">{t("통합점수")}</text>
      </svg>
      <ul className="care-donut-legend">
        {entries.map((c, i) => (
          <li key={c.key} style={{ "--j": i } as React.CSSProperties}>
            <i style={{ background: tones[i % tones.length] }} />
            <span>{t(c.label_ko)}</span>
            <b>{numberFmt.format(c.contribution)}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PatternTimeline({ report }: { report: CareReport }) {
  const months = visibleTimeline(report);
  return (
    <div className="care-timeline" role="img" aria-label={t("이동 변화 타임라인")}>
      {months.map((m, idx) => (
        <div key={m.month} style={{ "--i": idx } as React.CSSProperties} className={`care-timeline-col ${m.baseline ? "baseline" : ""} ${m.care ? "care" : ""} ${m.selected ? "selected" : ""}`}>
          <i><b style={{ height: `${Math.max(6, Math.min(100, m.change_pct))}%` }} /></i>
          <span>{m.month.slice(2)}</span>
        </div>
      ))}
    </div>
  );
}

/** 0단계 — AI 생성 진행. 절제된 타이포 + 얇은 진행선 하나만 움직인다. */
function GeneratingState({ step, elapsed }: { step: number; elapsed: number }) {
  return (
    <div className="care-generating" role="status" aria-live="polite">
      <strong>{t("AI 케어 리포트 생성 중")}</strong>
      <div className="care-gen-line" aria-hidden="true" />
      <ul className="care-gen-steps">
        {GEN_STEPS.map((label, i) => (
          <li key={label} className={i < step ? "done" : i === step ? "active" : ""}>
            <span>{t(label)}</span>
          </li>
        ))}
      </ul>
      <small>
        {t("숫자는 엔진 확정값 — AI는 서사만 작성합니다")}
        {elapsed > 0 ? ` · ${tf("{s}초 경과", { s: elapsed })}` : ""}
      </small>
    </div>
  );
}

export function CareReportModal({
  driver,
  rows,
  selectedRow,
  rules,
  driverNameKo,
  onClose
}: {
  driver: DriverAnnualSummary;
  rows: MonthlyEvidence[];
  selectedRow: MonthlyEvidence;
  rules: ProductRules;
  driverNameKo: string;
  onClose: () => void;
}) {
  const local = useMemo(
    () => buildLocalCareReport(driver, rows, selectedRow, rules, driverNameKo),
    [driver, rows, selectedRow, rules, driverNameKo]
  );
  const [report, setReport] = useState<CareReport>(local);
  const [phase, setPhase] = useState<"generating" | "ready">("generating");
  const [genStep, setGenStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [stage, setStage] = useState<"staff" | "customer">("staff");
  const [picked, setPicked] = useState<Record<string, boolean>>(
    () => Object.fromEntries(local.aftercare.map((a) => [a.id, true]))
  );
  // 검수 보조 결정 — 저장되지 않는 데모 상태(자동 판단 없음).
  const [staffMemo, setStaffMemo] = useState("");
  const [staffFlag, setStaffFlag] = useState<"none" | "request" | "hold">("none");

  useEffect(() => {
    let alive = true;
    setReport(local);
    setPicked(Object.fromEntries(local.aftercare.map((a) => [a.id, true])));
    setStage("staff");
    setPhase("generating");
    setGenStep(0);
    setElapsed(0);
    // 최소 1.6초는 생성 연출을 유지 — 즉시 폴백돼도 "생성되는" 흐름이 읽히게.
    const minHold = new Promise((resolve) => { setTimeout(resolve, 1600); });
    const enrich = enrichCareReport(local)
      .then((enriched) => { if (alive && enriched) setReport(enriched); })
      .catch(() => {});
    Promise.all([minHold, enrich]).then(() => { if (alive) setPhase("ready"); });
    return () => { alive = false; };
  }, [local]);

  useEffect(() => {
    if (phase !== "generating") return;
    const stepTimer = setInterval(() => setGenStep((s) => Math.min(s + 1, GEN_STEPS.length - 1)), 1200);
    const secTimer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => { clearInterval(stepTimer); clearInterval(secTimer); };
  }, [phase]);

  // 폰 화면 드래그 스크롤 — 인앱 뷰어처럼 마우스로 끌어서 내린다(스크롤바 없음).
  const screenRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef({ startY: 0, startTop: 0, active: false });
  const onScreenPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const el = screenRef.current;
    if (!el) return;
    dragRef.current = { startY: event.clientY, startTop: el.scrollTop, active: true };
  };
  const onScreenPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const el = screenRef.current;
    if (!el || !dragRef.current.active) return;
    el.scrollTop = dragRef.current.startTop - (event.clientY - dragRef.current.startY);
  };
  const endScreenDrag = () => { dragRef.current.active = false; };

  const generating = phase === "generating";
  const aiNarrative = report.generated_by === "openai_structured";
  const timeline = visibleTimeline(report);
  const baselineCount = timeline.filter((m) => m.baseline).length;
  const selectedAftercare = report.aftercare.filter((a) => picked[a.id]);
  const baselineRows = rows.filter((r) => r.period_role === "baseline");
  const baselineAvgKm = baselineRows.length
    ? baselineRows.reduce((sum, r) => sum + r.monthly_total_distance_km, 0) / baselineRows.length
    : null;
  const careStatus = report.verdict.care_axis === "Care Review" ? "watch" : (report.verdict.favorable_axis || "").toLowerCase() === "hold" ? "hold" : "ok";
  const familyName = report.driver.name_ko.replace(/\s*\(.*\)\s*$/, "");
  const reportNo = `CR-${driver.customer_id.replace(/[^a-z0-9]/gi, "").toUpperCase()}-${report.report_month.replace("-", "")}`;

  return (
    <div className="care-overlay" role="dialog" aria-modal="true" aria-label={t("케어 리포트 검수")}>
      <div className={`care-modal ${generating ? "is-enriching" : ""}`}>
        <header className="care-modal-head">
          <div>
            <span className="eyebrow">{t("직원 검수 리포트")} · {report.report_month}</span>
            <strong>{driverNameKo} · {t(report.driver.environment_ko)}</strong>
          </div>
          <div className="care-head-badges">
            <em className={`decision ${report.verdict.care_axis === "Care Review" ? "care" : "preferred"}`}>
              {report.verdict.care_axis === "Care Review" ? t("예방 케어") : t("우대")}
            </em>
            {generating ? <em className="care-enriching"><RefreshCcw size={12} /> {t("AI 서사 생성 중 — 숫자는 엔진 확정값")}</em> : (
              <em className="care-genby">{aiNarrative ? t("AI 서사 + 엔진 수치") : t("결정론 로컬 서사")}</em>
            )}
            <button type="button" className="care-close" onClick={onClose} aria-label={t("닫기")}><X size={16} /></button>
          </div>
        </header>

        <div className={`care-stage-track stage-${stage}`}>
          {generating ? (
            <GeneratingState step={genStep} elapsed={elapsed} />
          ) : (
            <>
              {/* ---------- 1단계: 직원 리포트 ---------- */}
              <section className="care-staff">
                <div className="care-meta" style={{ "--i": 0 } as React.CSSProperties}>
                  <div>
                    <span>{t("리포트 번호")}</span>
                    <b>{reportNo}</b>
                  </div>
                  <div>
                    <span>{t("관찰 기간")}</span>
                    <b>{timeline[0]?.month ?? ""} – {report.report_month}</b>
                  </div>
                  <div>
                    <span>{t("데이터 커버리지")}</span>
                    <b>{numberFmt.format(report.metrics.data_coverage_pct)}%</b>
                  </div>
                  <div>
                    <span>{t("서사 생성")}</span>
                    <b>{aiNarrative ? t("AI 구조화 출력") : t("결정론 로컬")}</b>
                  </div>
                </div>

                <div className="care-sec-block" style={{ "--i": 1 } as React.CSSProperties}>
                  <SectionMark n="01" label={t("판정 결론")} />
                  <div className="care-verdict">
                    <FileText size={16} />
                    <div>
                      <strong>
                        {report.verdict.headline_ko}
                        {aiNarrative ? <em className="ai-chip"><Sparkles size={10} /> {t("AI 생성")}</em> : null}
                      </strong>
                      <p>{report.verdict.summary_ko}</p>
                    </div>
                  </div>
                </div>

                <div className="care-sec-block" style={{ "--i": 2 } as React.CSSProperties}>
                  <SectionMark n="02" label={t("종합 소견")} ai={aiNarrative} />
                  <div className="care-card care-analyst">
                    {report.analyst_report_ko.split(/\n{2,}/).map((paragraph, idx) => (
                      <p key={idx}>
                        {paragraph.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
                          part.startsWith("**") && part.endsWith("**")
                            ? <strong key={j}>{part.slice(2, -2)}</strong>
                            : part
                        )}
                      </p>
                    ))}
                  </div>
                </div>

                <div className="care-sec-block" style={{ "--i": 3 } as React.CSSProperties}>
                  <SectionMark n="03" label={t("근거 차트")} />
                  <div className="care-grid">
                    <div className="care-card">
                      <span>{tf("이동 변화 타임라인 — 기준선 {b}개월 + 관찰 {n}개월", { b: baselineCount, n: Math.max(0, timeline.length - baselineCount) })}</span>
                      <p className="care-baseline-callout">
                        {tf("선택 월 {month} — 개인 기준선(첫 2개월, {b1}·{b2}) 대비 이동 변화 {pct}%p", {
                          month: report.report_month,
                          b1: report.pattern_timeline[0]?.month ?? "",
                          b2: report.pattern_timeline[1]?.month ?? "",
                          pct: numberFmt.format(report.metrics.mobility_change_pct)
                        })}
                      </p>
                      <PatternTimeline report={report} />
                      <small>{t("점선 = 기준선 관찰 · 주황 = 케어 검토 월 · 테두리 = 선택 월")}</small>
                    </div>
                    <div className="care-card">
                      <span>{t("지표별 기여 분해")}</span>
                      <ContributionDonut report={report} />
                    </div>
                  </div>
                </div>

                <div className="care-sec-block" style={{ "--i": 4 } as React.CSSProperties}>
                  <SectionMark n="04" label={t("판단 사유 (XAI)")} ai={aiNarrative} />
                  <div className="care-card">
                    <ul className="care-xai">
                      {report.xai_reasons.map((r, idx) => (
                        <li key={r.label_ko} className={r.direction} style={{ "--j": idx } as React.CSSProperties}>
                          <b>{t(r.label_ko)}</b>
                          <p>{r.note_ko}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="care-sec-block" style={{ "--i": 5 } as React.CSSProperties}>
                  <SectionMark n="05" label={t("사후지원 제안")} ai={aiNarrative} />
                  <div className="care-card">
                    <span>{t("발송 전 담당자가 확정합니다 — 체크 해제 시 발송되지 않습니다")}</span>
                    <ul className="care-aftercare">
                      {report.aftercare.map((a, idx) => (
                        <li key={a.id} className={picked[a.id] ? "on" : ""} style={{ "--j": idx } as React.CSSProperties}>
                          <label>
                            <input
                              type="checkbox"
                              checked={!!picked[a.id]}
                              onChange={(event) => setPicked((prev) => ({ ...prev, [a.id]: event.target.checked }))}
                            />
                            <div>
                              <b>{a.title_ko} <em className={`urgency ${a.urgency}`}>{a.urgency === "high" ? t("우선") : a.urgency === "medium" ? t("권장") : t("선택형")}</em></b>
                              <p>{a.description_ko}</p>
                              <small>{t("선정 사유")}: {a.reason_ko}</small>
                            </div>
                          </label>
                        </li>
                      ))}
                      {report.aftercare.length === 0 ? <li className="none">{t("이번 달 발동된 지원 신호가 없습니다 — 리포트만 발송됩니다.")}</li> : null}
                    </ul>
                  </div>
                </div>

                <div className="care-sec-block" style={{ "--i": 6 } as React.CSSProperties}>
                  <SectionMark n="06" label={t("검수·승인")} />
                  <footer className="care-staff-actions">
                    <div className="care-staff-reco">
                      <span>{t("검수 권고")}</span>
                      <strong>
                        {report.staff_review.recommendation === "confirm" ? t("승인 권고") : report.staff_review.recommendation === "hold" ? t("판단 보류 권고") : t("추가근거 권고")}
                        {aiNarrative ? <em className="ai-chip"><Sparkles size={10} /> {t("AI 생성")}</em> : null}
                      </strong>
                      <p>{report.staff_review.rationale_ko}</p>
                    </div>
                    <button type="button" className="care-approve" onClick={() => setStage("customer")}>
                      <CheckCircle2 size={15} /> {tf("승인하고 고객 화면 보기 ({n}개 지원 포함)", { n: selectedAftercare.length })}
                    </button>
                  </footer>
                  <div className="care-decision-extra">
                    <label className="care-memo">
                      <span>{t("담당자 메모")}</span>
                      <textarea
                        value={staffMemo}
                        onChange={(event) => setStaffMemo(event.target.value)}
                        placeholder={t("승인·보류 이유 또는 추가 확인사항")}
                      />
                    </label>
                    <div className="care-secondary-actions">
                      <button
                        type="button"
                        className={staffFlag === "request" ? "active" : ""}
                        onClick={() => setStaffFlag((prev) => (prev === "request" ? "none" : "request"))}
                      >
                        {t("추가근거 요청")}
                      </button>
                      <button
                        type="button"
                        className={staffFlag === "hold" ? "active" : ""}
                        onClick={() => setStaffFlag((prev) => (prev === "hold" ? "none" : "hold"))}
                      >
                        {t("판단 보류")}
                      </button>
                    </div>
                    <p className="care-audit-note">{t("메모와 결정은 저장되지 않는 데모이며 자동 판단이 없습니다. 전체 7섹션 AI 심사 리포트는 '리포트' 탭에서 확인할 수 있습니다.")}</p>
                  </div>
                </div>
              </section>

              {/* ---------- 2단계: 가족 앱 화면 ---------- */}
              <section className="care-customer">
                <div className="care-customer-side">
                  <span className="eyebrow"><Smartphone size={13} /> {t("가족 앱 미리보기")}</span>
                  <p>{t("직원이 승인한 리포트가 가족(보호자)에게 소식으로 전달됩니다. 부모님의 운전을 걱정하는 자녀가 상태를 한눈에 보고, 지원을 대신 신청할 수 있습니다.")}</p>
                  <div className="care-send-summary">
                    <div><span>{t("수신 대상")}</span><b>{t("가족(보호자) — 알림 동의 계약")}</b></div>
                    <div><span>{t("채널")}</span><b>MASIL Family</b></div>
                    <div><span>{t("포함 지원")}</span><b>{tf("{n}건", { n: selectedAftercare.length })}</b></div>
                    <div><span>{t("발송 월")}</span><b>{report.report_month}</b></div>
                  </div>
                  <div className="care-flow">
                    <span>{t("전달 프로세스")}</span>
                    <div className="care-flow-step done">
                      <i />
                      <div>
                        <b>{t("담당자 승인")}</b>
                        <small>{t("방금 완료 — 아래 화면이 그대로 전송됩니다")}</small>
                      </div>
                    </div>
                    <div className="care-flow-step">
                      <i />
                      <div>
                        <b>{t("가족 알림 발송")}</b>
                        <small>{t("알림 동의 계약에만 발송 · 심야 발송 제한")}</small>
                      </div>
                    </div>
                    <div className="care-flow-step">
                      <i />
                      <div>
                        <b>{t("열람·지원 신청")}</b>
                        <small>{t("자녀가 부모님 대신 신청할 수 있습니다")}</small>
                      </div>
                    </div>
                    <div className="care-flow-step">
                      <i />
                      <div>
                        <b>{t("케어팀 연결")}</b>
                        <small>{t("신청 접수 시 케어 매니저가 일정을 조율합니다")}</small>
                      </div>
                    </div>
                  </div>
                  <p className="care-consent-note">{t("가족 알림 동의를 받은 계약에만 전송됩니다 — 동의 없이는 어떤 정보도 공유되지 않습니다.")}</p>
                  <button type="button" className="care-back" onClick={() => setStage("staff")}>
                    <ArrowLeft size={14} /> {t("직원 화면으로")}
                  </button>
                </div>
                <div className="phone-frame">
                  <div className="phone-notch" />
                  <div
                    ref={screenRef}
                    className="phone-screen family-app"
                    onPointerDown={onScreenPointerDown}
                    onPointerMove={onScreenPointerMove}
                    onPointerUp={endScreenDrag}
                    onPointerLeave={endScreenDrag}
                  >
                    <div className="phone-statusbar" aria-hidden="true">
                      <span>9:41</span>
                      <span className="phone-statusbar-icons"><i /><i /><i /></span>
                    </div>
                    <div className="fam-head">
                      <b>MASIL <span>Family</span></b>
                      <em>{report.report_month}</em>
                    </div>
                    <div className={`fam-status ${careStatus}`}>
                      <span>{tf("{name} 님의 이번 달 운전", { name: familyName })}</span>
                      <strong>
                        {careStatus === "watch" ? t("한 번 살펴봐 주세요") : careStatus === "hold" ? t("데이터가 부족했어요") : t("안심하셔도 좋아요")}
                      </strong>
                      <p>{report.family_message.body_ko}</p>
                    </div>
                    <div className="fam-stats">
                      <div>
                        <span>{t("이번 달 이동")}</span>
                        <b>{numberFmt.format(report.metrics.monthly_distance_km)}<i>km</i></b>
                        {baselineAvgKm !== null ? <small>{tf("평소 약 {km}km", { km: numberFmt.format(Math.round(baselineAvgKm)) })}</small> : null}
                      </div>
                      <div>
                        <span>{t("새로운 길 비중")}</span>
                        <b>{numberFmt.format(report.metrics.mobility_change_pct)}<i>%p</i></b>
                        <small>{t("평소 생활권 대비")}</small>
                      </div>
                    </div>
                    {selectedAftercare.length ? (
                      <div className="fam-benefits">
                        <span>{t("보험사가 준비한 지원")}</span>
                        {selectedAftercare.map((a) => (
                          <div key={a.id} className="fam-benefit-card">
                            <b>{a.title_ko}</b>
                            <p>{a.customer_benefit_ko}</p>
                            <button type="button">{t("부모님 대신 신청하기")}</button>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    <button type="button" className="fam-contact">{t("케어 매니저에게 문의")}</button>
                    <p className="fam-closing">{report.family_message.closing_ko}</p>
                    <p className="fam-disclaimer">{report.data_status}</p>
                    <nav className="fam-nav" aria-label="app navigation">
                      <button type="button"><Home size={17} /><span>{t("홈")}</span></button>
                      <button type="button" className="active"><ScrollText size={17} /><span>{t("리포트")}</span></button>
                      <button type="button"><Gift size={17} /><span>{t("혜택")}</span></button>
                      <button type="button"><Settings size={17} /><span>{t("설정")}</span></button>
                    </nav>
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
