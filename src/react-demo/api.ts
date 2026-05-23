import type {
  DriverAnnualSummary,
  MonthlySnapshotResponse,
  PersonaDirectoryResponse,
  ZoneMapResponse
} from "./types";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: {
      Accept: "application/json"
    }
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { message?: string };
      message = payload.message ?? message;
    } catch {
      // Keep the HTTP status message when the server returns non-JSON errors.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export const demoApi = {
  getPersonaDirectory(): Promise<PersonaDirectoryResponse> {
    return getJson<PersonaDirectoryResponse>("/api/personas");
  },
  getAnnualSummary(driverId: string): Promise<DriverAnnualSummary> {
    return getJson<DriverAnnualSummary>(`/api/drivers/${encodeURIComponent(driverId)}/annual-summary`);
  },
  getMonthlySnapshots(driverId: string): Promise<MonthlySnapshotResponse> {
    return getJson<MonthlySnapshotResponse>(`/api/drivers/${encodeURIComponent(driverId)}/monthly-snapshots`);
  },
  getZoneMap(driverId: string, month: number): Promise<ZoneMapResponse> {
    const params = new URLSearchParams({ month: String(month) });
    return getJson<ZoneMapResponse>(`/api/drivers/${encodeURIComponent(driverId)}/zone-map?${params.toString()}`);
  },
  async streamMonthlyReport(driverId: string, month: number, onChunk: (chunk: string) => void): Promise<string> {
    const params = new URLSearchParams({ month: String(month) });
    params.set("driverId", driverId);
    const response = await fetch(`/api/reports/stream?${params.toString()}`, {
      headers: {
        Accept: "text/markdown"
      }
    });

    if (!response.ok || !response.body) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const raw = await response.text();
        if (raw) {
          const payload = JSON.parse(raw) as { message?: string };
          message = payload.message ?? raw;
        }
      } catch {
        // Keep the HTTP status message when the server returns plain text.
      }
      throw new Error(message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let report = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      report += chunk;
      onChunk(chunk);
    }

    return report;
  }
};
