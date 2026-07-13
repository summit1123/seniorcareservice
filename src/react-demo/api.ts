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
    const report = buildEvidenceReport(await studio(), driverId, month, rules);
    for (const chunk of reportChunks(report)) {
      onChunk(chunk);
      await Promise.resolve();
    }
    return report;
  }
};
