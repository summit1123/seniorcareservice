import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { request } from "node:http";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import { createServer } from "vite";

interface ResponseSnapshot {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  body: string;
}

function getResponse(
  port: number,
  path: string,
  options: { method?: string; host?: string; origin?: string; accept?: string } = {}
): Promise<ResponseSnapshot> {
  return new Promise((resolveResponse, reject) => {
    const req = request({
      hostname: "127.0.0.1",
      port,
      path,
      method: options.method ?? "GET",
      headers: {
        Host: options.host ?? `127.0.0.1:${port}`,
        Accept: options.accept ?? "application/json",
        ...(options.origin ? { Origin: options.origin } : {})
      }
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      res.on("end", () => resolveResponse({
        status: res.statusCode ?? 0,
        headers: res.headers,
        body: Buffer.concat(chunks).toString("utf8")
      }));
    });
    req.on("error", reject);
    req.end();
  });
}

test("live Vite boundary blocks host bypass and all raw data while serving an allowlisted DTO", { timeout: 20_000 }, async (t) => {
  const cacheDir = await mkdtemp(join(tmpdir(), "masil-vite-test-"));
  t.after(async () => rm(cacheDir, { force: true, recursive: true }));
  const server = await createServer({
    configFile: resolve("vite.config.ts"),
    cacheDir,
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { host: "127.0.0.1", port: 0, strictPort: false }
  });
  await server.listen();
  t.after(async () => server.close());

  const address = server.httpServer?.address();
  assert.ok(address && typeof address !== "string");
  const port = address.port;

  const index = await getResponse(port, "/", { accept: "text/html" });
  assert.equal(index.status, 200);
  assert.match(index.headers["content-type"]?.toString() ?? "", /text\/html/);

  const entryModule = await getResponse(port, "/src/react-demo/main.tsx");
  assert.equal(entryModule.status, 200);

  const api = await getResponse(port, "/api/gaip/studio");
  assert.equal(api.status, 200);
  assert.equal(api.headers["cache-control"], "no-store");
  assert.equal(api.headers["x-content-type-options"], "nosniff");
  const dto = JSON.parse(api.body);
  assert.equal(dto.metadata.synthetic_data, true);
  assert.equal(dto.drivers.length, 60);
  assert.equal(dto.metadata.source_artifacts, undefined);
  const serialized = api.body.toLowerCase();
  for (const forbidden of [
    '"latitude"', '"longitude"', '"coordinates"', '"center_latitude"',
    '"start_gps_x"', "gaip_visit_events.csv", '"sha256"'
  ]) assert.equal(serialized.includes(forbidden), false, forbidden);

  for (const rawPath of [
    "/data/fixtures/gaip_visit_events.csv",
    "/data/fixtures/gaip_simulation_bundle.json",
    "/data/fixtures/annual_trip_logs.csv",
    "/data/processed/monthly_zone_snapshots.json",
    "/%2564ata/processed/customer_living_zone_records.json",
    `/@fs${resolve("data/fixtures/annual_trip_logs.csv")}`,
    "/@fs/etc/passwd",
    "/%2540fs/etc/passwd"
  ]) {
    const response = await getResponse(port, rawPath);
    assert.equal(response.status, 403, rawPath);
  }

  assert.equal((await getResponse(port, "/api/gaip/studio", { host: `evil.test:${port}` })).status, 403);
  assert.equal((await getResponse(port, "/api/gaip/studio", { origin: "https://evil.test" })).status, 403);
  assert.equal((await getResponse(port, "/api/drivers/gaip-001/zone-map")).status, 404);
  assert.equal((await getResponse(port, "/api/gaip/%2e%2e/gaip/studio")).status, 400);

  const post = await getResponse(port, "/api/gaip/studio", { method: "POST" });
  assert.equal(post.status, 405);
  assert.equal(post.headers.allow, "GET");
});
