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
  studioPromise ??= gaipStudioApi.getStudio();
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
    month: number,
    onChunk: (chunk: string) => void,
    rules?: ProductRules
  ): Promise<string> {
    // 1순위: 서버 AI 리포트 스트림(OpenAI, 7섹션 Markdown). 실패 시 로컬 결정적 리포트로 대체.
    try {
      const response = await fetch(
        `/api/gaip/report/stream?driver=${encodeURIComponent(driverId)}&month=${encodeURIComponent(String(month))}`
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
