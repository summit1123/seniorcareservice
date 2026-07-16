import { getLocale } from "./i18n";
import { gaipStudioApi } from "./gaip-api";
import {
  adaptAnnualSummary,
  adaptDirectory,
  adaptMonthlySnapshots,
  adaptZoneMap,
  buildEvidenceReport
} from "./legacy-gaip-adapter";
import type { GaipStudioBundle, ProductRules } from "./gaip-types";
import type {
  DriverAnnualSummary,
  MonthlySnapshotResponse,
  PersonaDirectoryResponse,
  ZoneMapResponse
} from "./types";

let studioPromise: Promise<GaipStudioBundle> | null = null;

function studio(): Promise<GaipStudioBundle> {
  // Never cache a REJECTED promise: a single transient failure (server warming up,
  // fixture regenerating) would otherwise brick every later call until a hard
  // reload. Clear the cache on failure so the next call retries naturally.
  if (!studioPromise) {
    const attempt = gaipStudioApi.getStudio();
    studioPromise = attempt;
    attempt.catch(() => {
      if (studioPromise === attempt) studioPromise = null;
    });
  }
  return studioPromise;
}

function reportChunks(report: string): string[] {
  const sections = report.split(/(?=^##\s)/gm).filter(Boolean);
  return sections.length ? sections : [report];
}

export const demoApi = {
  async getPersonaDirectory(rules?: ProductRules): Promise<PersonaDirectoryResponse> {
    return adaptDirectory(await studio(), rules);
  },
  async getAnnualSummary(driverId: string, rules?: ProductRules): Promise<DriverAnnualSummary> {
    return adaptAnnualSummary(await studio(), driverId, rules);
  },
  async getMonthlySnapshots(driverId: string, rules?: ProductRules): Promise<MonthlySnapshotResponse> {
    return adaptMonthlySnapshots(await studio(), driverId, rules);
  },
  async getZoneMap(driverId: string, month: number, rules?: ProductRules): Promise<ZoneMapResponse> {
    return adaptZoneMap(await studio(), driverId, month, rules);
  },
  async streamMonthlyReport(
    driverId: string,
    month: number | string,
    onChunk: (chunk: string) => void,
    rules?: ProductRules
  ): Promise<string> {
    // 1순위: 서버 AI 리포트 스트림(OpenAI, 7섹션 Markdown). 실패 시 로컬 결정적 리포트로 대체.
    try {
      const response = await fetch(
        `/api/gaip/report/stream?driver=${encodeURIComponent(driverId)}&month=${encodeURIComponent(String(month))}&lang=${encodeURIComponent(getLocale())}`
      );
      if (response.ok && response.body && response.headers.get("X-Report-Mode") === "openai-responses-stream") {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let full = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          if (chunk) {
            full += chunk;
            onChunk(chunk);
          }
        }
        if (full.trim()) return full;
      }
    } catch {
      // 네트워크/키 부재 — 아래 로컬 리포트로 진행
    }
    const report = buildEvidenceReport(await studio(), driverId, month, rules);
    for (const chunk of reportChunks(report)) {
      onChunk(chunk);
      await Promise.resolve();
    }
    return report;
  }
};

/**
 * 케어 리포트 서사 보강 — 서버(LLM)는 서사 필드만 생성하고, 숫자는 로컬 리포트의
 * 값을 그대로 유지한다(병합 시 서사 키만 덮어씀 → 수치 무결성이 구조적으로 보장).
 * 서버가 없거나 실패하면 null을 반환해 호출자가 로컬 서사를 그대로 쓴다.
 */
export async function enrichCareReport(local: import("./care-report").CareReport): Promise<import("./care-report").CareReport | null> {
  try {
    const response = await fetch("/api/gaip/report/care", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...local, target_language: getLocale() })
    });
    if (!response.ok) return null;
    const narrative = (await response.json()) as {
      headline_ko?: string; summary_ko?: string;
      analyst_report_ko?: string;
      xai_notes?: Array<{ label_ko: string; note_ko: string }>;
      aftercare_reasons?: Array<{ id: string; reason_ko: string }>;
      staff_rationale_ko?: string;
      family_title_ko?: string; family_body_ko?: string; family_closing_ko?: string;
    };
    if (!narrative || typeof narrative !== "object") return null;
    const xaiByLabel = new Map((narrative.xai_notes ?? []).map((n) => [n.label_ko, n.note_ko]));
    const reasonById = new Map((narrative.aftercare_reasons ?? []).map((n) => [n.id, n.reason_ko]));
    return {
      ...local,
      generated_by: "openai_structured",
      verdict: {
        ...local.verdict,
        headline_ko: narrative.headline_ko || local.verdict.headline_ko,
        summary_ko: narrative.summary_ko || local.verdict.summary_ko
      },
      analyst_report_ko: narrative.analyst_report_ko || local.analyst_report_ko,
      xai_reasons: local.xai_reasons.map((r) => ({ ...r, note_ko: xaiByLabel.get(r.label_ko) || r.note_ko })),
      aftercare: local.aftercare.map((a) => ({ ...a, reason_ko: reasonById.get(a.id) || a.reason_ko })),
      staff_review: { ...local.staff_review, rationale_ko: narrative.staff_rationale_ko || local.staff_review.rationale_ko },
      family_message: {
        title_ko: narrative.family_title_ko || local.family_message.title_ko,
        body_ko: narrative.family_body_ko || local.family_message.body_ko,
        closing_ko: narrative.family_closing_ko || local.family_message.closing_ko
      }
    };
  } catch {
    return null;
  }
}
