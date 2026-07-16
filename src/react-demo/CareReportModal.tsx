/**
 * 케어 리포트 확장 모달 — 직원 검수 → 승인 → 모바일(고객) 화면의 연속 흐름.
 *
 * 1단계(직원): 구조화 리포트(판정·14개월 패턴 타임라인·기여 도넛·XAI·사후지원
 *   제안 카드). 직원이 사후지원 항목을 체크/해제하고 승인한다.
 * 2단계(고객): 승인 시 폰 프레임 안에 고객용 웹앱 화면이 나타난다 — 같은 근거가
 *   비징벌 언어로 재해석되고, 직원이 확정한 지원만 신청 카드로 보인다.
 *
 * 숫자는 전부 로컬 결정론 빌더(care-report.ts)가 채우고, 서버(LLM)는 서사 필드만
 * 덧입힌다 — 실패해도 로컬 서사로 데모가 계속된다.
 */
import { useEffect, useMemo, useState } from "react";
import { X, FileText, CheckCircle2, Smartphone, ArrowLeft, RefreshCcw } from "lucide-react";
import { t, tf } from "./i18n";
import { buildLocalCareReport, type CareReport } from "./care-report";
import { enrichCareReport } from "./api";
import type { DriverAnnualSummary, MonthlyEvidence } from "./types";
import type { ProductRules } from "./gaip-types";

const numberFmt = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });

function ContributionDonut({ report }: { report: CareReport }) {
  const entries = report.weight_contributions.filter((c) => c.contribution !== null) as Array<{
    key: string; label_ko: string; contribution: number; weight_pct: number; score: number | null;
  }>;
  const total = entries.reduce((sum, c) => sum + c.contribution, 0);
  const R = 52;
  const CIRC = 2 * Math.PI * R;
  let offset = 0;
  const tones = ["#0e8c74", "#28a88e", "#4c63b6", "#c2762b"];
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
          {report.verdict.integrated_score === null ? "—" : numberFmt.format(report.verdict.integrated_score)}
        </text>
        <text x="70" y="84" textAnchor="middle" className="care-donut-caption">{t("통합점수")}</text>
      </svg>
      <ul className="care-donut-legend">
        {entries.map((c, i) => (
          <li key={c.key}>
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
  return (
    <div className="care-timeline" role="img" aria-label={t("14개월 이동 변화 타임라인")}>
      {report.pattern_timeline.map((m) => (
        <div key={m.month} className={`care-timeline-col ${m.baseline ? "baseline" : ""} ${m.care ? "care" : ""} ${m.selected ? "selected" : ""}`}>
          <i><b style={{ height: `${Math.max(6, Math.min(100, m.change_pct))}%` }} /></i>
          <span>{m.month.slice(2)}</span>
        </div>
      ))}
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
  const [enriching, setEnriching] = useState(true);
  const [stage, setStage] = useState<"staff" | "customer">("staff");
  const [picked, setPicked] = useState<Record<string, boolean>>(
    () => Object.fromEntries(local.aftercare.map((a) => [a.id, true]))
  );

  useEffect(() => {
    let alive = true;
    setReport(local);
    setPicked(Object.fromEntries(local.aftercare.map((a) => [a.id, true])));
    setStage("staff");
    setEnriching(true);
    enrichCareReport(local)
      .then((enriched) => { if (alive && enriched) setReport(enriched); })
      .finally(() => { if (alive) setEnriching(false); });
    return () => { alive = false; };
  }, [local]);

  const selectedAftercare = report.aftercare.filter((a) => picked[a.id]);
  const baselineRows = rows.filter((r) => r.period_role === "baseline");
  const baselineAvgKm = baselineRows.length
    ? baselineRows.reduce((sum, r) => sum + r.monthly_total_distance_km, 0) / baselineRows.length
    : null;
  const careStatus = report.verdict.care_axis === "Care Review" ? "watch" : (report.verdict.favorable_axis || "").toLowerCase() === "hold" ? "hold" : "ok";
  const familyName = report.driver.name_ko.replace(/\s*\(.*\)\s*$/, "");

  return (
    <div className="care-overlay" role="dialog" aria-modal="true" aria-label={t("케어 리포트 검수")}>
      <div className="care-modal">
        <header className="care-modal-head">
          <div>
            <span className="eyebrow">{t("직원 검수 리포트")} · {report.report_month}</span>
            <strong>{driverNameKo} · {t(report.driver.environment_ko)}</strong>
          </div>
          <div className="care-head-badges">
            <em className={`decision ${report.verdict.care_axis === "Care Review" ? "care" : "preferred"}`}>
              {report.verdict.care_axis === "Care Review" ? t("예방 케어") : t("우대")}
            </em>
            {enriching ? <em className="care-enriching"><RefreshCcw size={12} /> {t("AI 서사 생성 중 — 숫자는 엔진 확정값")}</em> : (
              <em className="care-genby">{report.generated_by === "openai_structured" ? t("AI 서사 + 엔진 수치") : t("결정론 로컬 서사")}</em>
            )}
            <button type="button" className="care-close" onClick={onClose} aria-label={t("닫기")}><X size={16} /></button>
          </div>
        </header>

        <div className={`care-stage-track stage-${stage}`}>
          {/* ---------- 1단계: 직원 리포트 ---------- */}
          <section className="care-staff">
            <div className="care-verdict">
              <FileText size={16} />
              <div>
                <strong>{report.verdict.headline_ko}</strong>
                <p>{report.verdict.summary_ko}</p>
              </div>
            </div>

            <div className="care-grid">
              <div className="care-card">
                <span>{t("14개월 이동 변화 타임라인")}</span>
                <PatternTimeline report={report} />
                <small>{t("점선 = 기준선 관찰 · 주황 = 케어 검토 월 · 테두리 = 선택 월")}</small>
              </div>
              <div className="care-card">
                <span>{t("지표별 기여 분해")}</span>
                <ContributionDonut report={report} />
              </div>
            </div>

            <div className="care-card">
              <span>{t("판단 사유 (XAI)")}</span>
              <ul className="care-xai">
                {report.xai_reasons.map((r) => (
                  <li key={r.label_ko} className={r.direction}>
                    <b>{t(r.label_ko)}</b>
                    <p>{r.note_ko}</p>
                  </li>
                ))}
              </ul>
            </div>

            <div className="care-card">
              <span>{t("사후지원 제안 — 발송 전 담당자가 확정합니다")}</span>
              <ul className="care-aftercare">
                {report.aftercare.map((a) => (
                  <li key={a.id} className={picked[a.id] ? "on" : ""}>
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

            <footer className="care-staff-actions">
              <div className="care-staff-reco">
                <span>{t("검수 권고")}</span>
                <strong>{report.staff_review.recommendation === "confirm" ? t("승인 권고") : report.staff_review.recommendation === "hold" ? t("판단 보류 권고") : t("추가근거 권고")}</strong>
                <p>{report.staff_review.rationale_ko}</p>
              </div>
              <button type="button" className="care-approve" onClick={() => setStage("customer")}>
                <CheckCircle2 size={15} /> {tf("승인하고 고객 화면 보기 ({n}개 지원 포함)", { n: selectedAftercare.length })}
              </button>
            </footer>
          </section>

          {/* ---------- 2단계: 가족 앱 화면 ---------- */}
          <section className="care-customer">
            <div className="care-customer-side">
              <span className="eyebrow"><Smartphone size={13} /> {t("가족 앱 미리보기")}</span>
              <p>{t("직원이 승인한 리포트가 가족(보호자)에게 소식으로 전달됩니다. 부모님의 운전을 걱정하는 자녀가 상태를 한눈에 보고, 지원을 대신 신청할 수 있습니다.")}</p>
              <p className="care-consent-note">{t("가족 알림 동의를 받은 계약에만 전송됩니다 — 동의 없이는 어떤 정보도 공유되지 않습니다.")}</p>
              <button type="button" className="care-back" onClick={() => setStage("staff")}>
                <ArrowLeft size={14} /> {t("직원 화면으로")}
              </button>
            </div>
            <div className="phone-frame">
              <div className="phone-notch" />
              <div className="phone-screen family-app">
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
                <p className="fam-closing">{report.family_message.closing_ko}</p>
                <p className="fam-disclaimer">{report.data_status}</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
