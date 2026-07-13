import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import type { ServerResponse } from "node:http";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import type { PreviewServer, ViteDevServer } from "vite";

import {
  hasTraversalSegments,
  isAllowedRequestHost,
  isAllowedRequestOrigin,
  isPrivateArtifactRequest,
  isViteFileSystemRequest,
  sanitizeGaipBundleForUi
} from "./src/gaip_server_policy";

const repoRoot = dirname(fileURLToPath(import.meta.url));
const gaipStudioPath = resolve(repoRoot, "data", "fixtures", "gaip_simulation_bundle.json");

function sendJson(res: ServerResponse, statusCode: number, payload: unknown): void {
  const body = `${JSON.stringify(payload)}\n`;
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Content-Length", Buffer.byteLength(body));
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.end(body);
}

async function readJson(path: string): Promise<unknown> {
  return JSON.parse(await readFile(path, "utf8"));
}

/**
 * Install the same privacy and request boundary in both `vite dev` and
 * `vite preview`. Non-API requests continue into Vite so the existing index,
 * modules, assets, SPA fallback and HMR behavior stay intact.
 */
function configureGaipServer(server: ViteDevServer | PreviewServer): void {
  server.middlewares.use(async (req, res, next) => {
    if (!req.url) {
      next();
      return;
    }

    const origin = typeof req.headers.origin === "string" ? req.headers.origin : undefined;
    if (!isAllowedRequestHost(req.headers.host) || !isAllowedRequestOrigin(origin)) {
      sendJson(res, 403, { message: "Request host or origin is not allowed." });
      return;
    }

    if (hasTraversalSegments(req.url)) {
      sendJson(res, 400, { message: "Path traversal segments are not allowed." });
      return;
    }

    if (isViteFileSystemRequest(req.url)) {
      sendJson(res, 403, { message: "Direct filesystem access is not available." });
      return;
    }

    if (isPrivateArtifactRequest(req.url)) {
      sendJson(res, 403, {
        message: "Raw GAIP simulation artifacts are server-private and are not served directly to the UI."
      });
      return;
    }

    let requestUrl: URL;
    try {
      requestUrl = new URL(req.url, "http://localhost");
    } catch {
      sendJson(res, 400, { message: "Invalid request URL." });
      return;
    }

    if (!requestUrl.pathname.toLowerCase().startsWith("/api/")) {
      next();
      return;
    }

    if (req.method !== "GET") {
      res.setHeader("Allow", "GET");
      sendJson(res, 405, { message: "Only GET is supported by the read-only GAIP dashboard API." });
      return;
    }

    if (requestUrl.pathname !== "/api/gaip/studio") {
      sendJson(res, 404, {
        message: "Unknown API route. The dashboard exposes only /api/gaip/studio."
      });
      return;
    }

    if (!existsSync(gaipStudioPath)) {
      sendJson(res, 503, {
        message: "GAIP simulation bundle is not generated yet. Run npm run generate:gaip first."
      });
      return;
    }

    try {
      const bundle = sanitizeGaipBundleForUi(await readJson(gaipStudioPath));
      sendJson(res, 200, bundle);
    } catch (error) {
      sendJson(res, 500, {
        message: error instanceof Error ? error.message : "Unable to load the GAIP simulation bundle."
      });
    }
  });
}

export default defineConfig({
  server: {
    allowedHosts: [".summit1123.co.kr"],
    port: 5173,
    strictPort: false,
    fs: {
      strict: true,
      deny: [
        "**/data/**",
        "**/.env*",
        "**/*.pem",
        "**/*.crt",
        "**/.git/**"
      ]
    }
  },
  preview: {
    allowedHosts: [".summit1123.co.kr"],
    port: 4173,
    strictPort: false
  },
  plugins: [
    {
      name: "masil-gaip-existing-dashboard-api",
      enforce: "pre",
      configureServer: configureGaipServer,
      configurePreviewServer: configureGaipServer
    }
  ]
});
