/**
 * GAIP 직원용 월별 리포트 스트림 (원본 7섹션 흐름 보존).
 *
 * - 입력은 sanitizeGaipBundleForUi를 통과한 번들만 사용한다(원시 좌표·경로 없음).
 * - OPENAI_API_KEY가 있으면 OpenAI Responses 스트림으로 Markdown을 생성한다.
 * - 키가 없거나 호출이 실패하면 라우트가 5xx JSON을 반환하고,
 *   프런트는 결정적 로컬 리포트로 대체한다(오프라인 데모 안전).
 * - LLM은 이미 계산된 값을 설명만 한다. 점수·할인율 재계산 금지(프롬프트로 강제).
 */
import { readFileSync } from "node:fs";
import type { ServerResponse } from "node:http";
import { resolve } from "node:path";

const OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses";

type JsonRecord = Record<string, unknown>;

function toRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null ? (value as JsonRecord) : {};
}

function toArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

let envCache: Record<string, string> | null = null;

export function envValue(name: string, repoRoot?: string): string {
  if (process.env[name]) return process.env[name] ?? "";
  if (envCache === null) {
    envCache = {};
    try {
      const raw = readFileSync(resolve(repoRoot ?? process.cwd(), ".env"), "utf8");
      for (const line of raw.split(/\r?\n/)) {
        const match = /^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
        if (match) envCache[match[1]] = match[2].replace(/^['"]|['"]$/g, "");
      }
    } catch {
      // .env 없음 — process.env만 사용
    }
  }
  return envCache[name] ?? "";
}

export function buildReportFeatures(bundle: JsonRecord, driverId: string, monthKey: string): JsonRecord {
  const drivers = toArray(toRecord(bundle).drivers).map(toRecord);
  const driver = drivers.find((d) => d.id === driverId || d.driver_id === driverId);
  if (!driver) throw new Error(`unknown driver: ${driverId}`);

  // monthKey is the calendar label (YYYY-MM), matching monthly_results[].month —
  // baseline months (2025-11/12) included. A missing month is a hard 404 so the
  // client falls back to the (index-correct) local report instead of silently
  // reporting on December.
  const monthly = toArray(driver.monthly_results).map(toRecord);
  const month = monthly.find((m) => m.month === monthKey);
  if (!month) {
    throw Object.assign(new Error(`unknown month for ${driverId}: ${monthKey}`), { statusCode: 404 });
  }
  const mobility = toRecord(driver.mobility);
  const tariff = toRecord(driver.tariff);
  const hubs = toArray(mobility.routine_hubs).map(toRecord).map((hub) => ({
    label: hub.display_label_ko ?? hub.display_label ?? "반복 거점",
    radial_p90_m: hub.radial_p90_m,
    buffer_radius_m: hub.buffer_radius_m,
    distinct_day_count: hub.distinct_day_count
  }));

  return {
    data_status: "Simulated — 합성 시뮬레이션 근거이며 실제 고객 데이터가 아님",
    report_month: monthKey,
    driver: {
      id: driver.driver_id ?? driver.id,
      name: driver.driver_name_ko ?? null,
      age: driver.age ?? null,
      persona: driver.persona_display_name_ko ?? driver.persona_type,
      environment: driver.environment_display_name_ko ?? driver.environment_id,
      scenario_variant: driver.scenario_variant ?? "typical"
    },
    annual: {
      reward_state: driver.annual_reward_state ?? driver.reward_state ?? toRecord(driver.annual).reward_state ?? null,
      care_state: driver.annual_care_state ?? driver.care_state ?? toRecord(driver.annual).care_state ?? null,
      korea_reference_discount_rate_pct: tariff.korea_mileage_discount_rate_pct ?? null,
      proposed_discount_rate_pct: tariff.masil_candidate_discount_rate_pct ?? tariff.proposed_discount_rate_pct ?? null
    },
    selected_month: {
      month: month.month ?? monthKey,
      period_role: month.period_role ?? null,
      data_coverage_pct: month.data_coverage_pct ?? null,
      outer_visit_share: month.outer_visit_share ?? null,
      risky_events_per_100_km: month.risky_events_per_100_km ?? null,
      mobility_change_index: month.mobility_change_index ?? null,
      risky_behavior_change_index: month.risky_behavior_change_index ?? null,
      mileage_score: month.mileage_score ?? null,
      in_zone_safe_score: month.in_zone_safe_score ?? null,
      out_zone_safe_score: month.out_zone_safe_score ?? null,
      pattern_stability_score: month.pattern_stability_score ?? null,
      reward_state: month.reward_state ?? null,
      care_state: month.care_state ?? null
    },
    living_zone: {
      hubs,
      core_radius_m: 500,
      buffer_rule: "완충권 = max(500m, min(개인 radial P90, 2km))",
      outer_policy: "생활권 밖 이동 자체는 중립 — 위치만으로 감점하지 않음"
    }
  };
}

function buildReportPrompt(features: JsonRecord) {
  const systemPrompt = [
    "당신은 자동차보험 상품기획 및 심사 직원을 위한 내부 주행 리포트를 작성하는 어시스턴트입니다.",
    "입력값은 이미 산식과 XAI 파이프라인에서 계산된 값이므로 할인율, 점수, 금액을 다시 계산하거나 추정하지 마세요.",
    "이 리포트는 고객 안내문이 아니라 내부 검토, 상담 준비, 예방 케어 판단을 위한 설명문입니다.",
    "고령 고객에게 벌점, 제재, 낙인처럼 들리는 표현을 피하고 예방 케어와 근거 확인 중심으로 작성하세요.",
    "월별 리포트는 연간 판단을 설명하는 근거 리포트이며 보험료 계산서가 아닙니다.",
    "본문에서 기존 할인액, 제안 할인액, 최종 보험료 차이, 인상, 할증, 보험료 상승을 언급하지 마세요.",
    "모든 데이터는 합성 시뮬레이션이며, 실존 인물·장소가 아님을 전제로 하세요.",
    "직원이 10초 안에 핵심을 이해할 수 있도록 월별 결론, 핵심 근거, 추천 조치를 먼저 배치하세요.",
    "Markdown으로 작성하고, 표는 최대 1개만 사용하며, 입력된 숫자 피처값은 그대로 보존하세요.",
    "값이 null인 지표는 0이 아니라 '해당 월 관측 없음'으로 서술하고 점수로 해석하지 마세요.",
    "각 섹션은 2~4개 bullet로 작성하고, 필요하면 구체적인 피처값과 상태값을 함께 언급하세요."
  ].join("\n");

  const userPrompt = [
    "아래 privacy_filtered_features만 사용해 한국어로 리포트를 작성하세요.",
    "반드시 다음 7개 Markdown 섹션 제목을 그대로 사용하세요. 섹션을 생략하거나 이름을 바꾸지 마세요.",
    "## 1. 월별 결론 요약",
    "## 2. 연간 산식 반영",
    "## 3. 생활권 판단 근거",
    "## 4. 월별 주행 패턴",
    "## 5. XAI 주요 원인",
    "## 6. 상담 및 케어 액션",
    "## 7. 검토 한계와 확인 필요사항",
    "",
    "작성 규칙:",
    "- 1번 섹션은 이번 달 생활권/위험변화 신호와 다음 직원 조치를 3줄 안에 요약하세요. 보험료 변화는 언급하지 마세요.",
    "- 2번 섹션은 이번 달 근거가 4개 지표(주행거리, 생활권 안 안전, 생활권 밖 안전, 패턴 안정성) 중 어디에 기여하는지 설명하세요. 할인율이나 최종 보험료를 계산하지 마세요.",
    "- 3번 섹션은 기준선 2개월 생활권 산출, 개인 P90 인정반경, 생활권 안/밖 비중을 구분해 설명하세요.",
    "- 4번 섹션은 반복 거점, 신규 목적지, 위험행동 흐름을 직원이 이해하기 쉽게 해석하세요.",
    "- 5번 섹션은 이동 변화·위험행동 변화 두 지표가 케어 판단에 어떻게 작용했는지 설명하세요(둘 다 임계치를 넘을 때만 케어 검토).",
    "- 6번 섹션은 필요 시 예방 케어, 안전운전 리포트, 차량 점검, 다음 달 재확인 액션을 제안하세요.",
    "- 7번 섹션은 원본 좌표가 숨겨져 있고, 데이터가 전부 합성이며, 실제 청구 데이터 검증이 필요하다는 점을 짧게 적으세요.",
    `privacy_filtered_features=${JSON.stringify(features, null, 2)}`
  ].join("\n");

  return { systemPrompt, userPrompt };
}

function extractResponseDelta(event: JsonRecord): string {
  const eventType = typeof event.type === "string" ? event.type : "";
  if (eventType.endsWith(".delta") && typeof event.delta === "string") return event.delta;
  if (eventType.endsWith(".delta") && typeof event.text === "string") return event.text;
  return "";
}

async function pipeOpenAIEventStream(response: Response, res: ServerResponse): Promise<void> {
  if (!response.body) throw new Error("OpenAI response body is empty");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split(/\n\n/);
    buffer = events.pop() ?? "";
    for (const eventBlock of events) {
      const data = eventBlock
        .split(/\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data || data === "[DONE]") continue;
      try {
        const delta = extractResponseDelta(JSON.parse(data) as JsonRecord);
        if (delta) res.write(delta);
      } catch {
        // 스트림 제어 프레임은 무시
      }
    }
  }
}

export async function streamGaipReport(
  res: ServerResponse,
  bundle: JsonRecord,
  driverId: string,
  monthKey: string,
  repoRoot?: string
): Promise<void> {
  const apiKey = envValue("OPENAI_API_KEY", repoRoot);
  if (!apiKey) {
    throw Object.assign(new Error("OPENAI_API_KEY가 없어 AI 리포트를 생성할 수 없습니다. 로컬 리포트로 대체됩니다."), {
      statusCode: 503
    });
  }
  const features = buildReportFeatures(bundle, driverId, monthKey);
  const model = envValue("OPENAI_REPORT_MODEL", repoRoot) || envValue("OPENAI_MODEL", repoRoot) || "gpt-4o-mini";
  const { systemPrompt, userPrompt } = buildReportPrompt(features);

  const openAIResponse = await fetch(envValue("OPENAI_RESPONSES_URL", repoRoot) || OPENAI_RESPONSES_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      stream: true,
      metadata: { purpose: "masil_gaip_insurer_report", report_month: String(features.report_month) },
      input: [
        { role: "system", content: [{ type: "input_text", text: systemPrompt }] },
        { role: "user", content: [{ type: "input_text", text: userPrompt }] }
      ]
    })
  });

  if (!openAIResponse.ok) {
    const body = await openAIResponse.text();
    throw Object.assign(new Error(`OpenAI report stream failed (${openAIResponse.status}): ${body.slice(0, 300)}`), {
      statusCode: 502
    });
  }

  res.statusCode = 200;
  res.setHeader("Content-Type", "text/markdown; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Report-Mode", "openai-responses-stream");
  res.setHeader("X-Report-Model", model);
  await pipeOpenAIEventStream(openAIResponse, res);
  res.end();
}

/**
 * 케어 리포트 서사 생성 — Structured Outputs(json_schema)로 서사 필드만 받는다.
 * 입력은 클라이언트가 만든 결정론 리포트(숫자 확정값). 모델은 숫자를 재계산하지
 * 않고, 헤드라인/요약/XAI 해설/사후지원 사유/직원 권고/고객 메시지를 작성한다.
 * 기본 모델은 추론 상위 계열(OPENAI_CARE_MODEL → OPENAI_REPORT_MODEL → gpt-5).
 */
const CARE_NARRATIVE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    headline_ko: { type: "string", description: "직원용 한 줄 결론 (한국어, 40자 이내)" },
    summary_ko: { type: "string", description: "직원용 2-3문장 요약 — 입력 수치를 그대로 인용" },
    xai_notes: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: { label_ko: { type: "string" }, note_ko: { type: "string" } },
        required: ["label_ko", "note_ko"]
      }
    },
    aftercare_reasons: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: { id: { type: "string" }, reason_ko: { type: "string" } },
        required: ["id", "reason_ko"]
      }
    },
    staff_rationale_ko: { type: "string" },
    family_title_ko: { type: "string", description: "가족(보호자) 앱 제목 — 따뜻하고 비징벌적, 자녀가 읽는 소식" },
    family_body_ko: { type: "string", description: "가족 대상 본문 3-4문장 — 벌점/감액/경고 금지, 부모님 상황 설명과 지원 안내 중심" },
    family_closing_ko: { type: "string" }
  },
  required: [
    "headline_ko", "summary_ko", "xai_notes", "aftercare_reasons",
    "staff_rationale_ko", "family_title_ko", "family_body_ko", "family_closing_ko"
  ]
} as const;

const CARE_LANGUAGE_NAMES: Record<string, string> = {
  ko: "한국어",
  en: "English",
  zh: "简体中文 (Simplified Chinese)",
  ja: "日本語",
  vi: "Tiếng Việt"
};

export async function generateCareNarrative(localReport: JsonRecord, repoRoot?: string): Promise<JsonRecord> {
  const apiKey = envValue("OPENAI_API_KEY", repoRoot);
  if (!apiKey) {
    throw Object.assign(new Error("OPENAI_API_KEY 없음 — 로컬 서사로 대체"), { statusCode: 503 });
  }
  const model =
    envValue("OPENAI_CARE_MODEL", repoRoot) ||
    envValue("OPENAI_REPORT_MODEL", repoRoot) ||
    "gpt-5";
  // 데모 응답속도 우선: 추론은 기본 최소(minimal). OPENAI_CARE_REASONING=low|medium|high로
  // 올리거나 "off"로 파라미터 자체를 생략할 수 있다. 서사 품질은 스키마+엔진 확정값이 지탱한다.
  const reasoningRaw = (envValue("OPENAI_CARE_REASONING", repoRoot) || "minimal").toLowerCase();
  const reasoningCapable = /^(gpt-5|o\d)/i.test(model);
  const supportsMinimal = /^gpt-5/i.test(model); // o-계열은 minimal 미지원 → low로 강등
  const reasoning =
    reasoningRaw === "off" || !reasoningCapable
      ? undefined
      : { effort: reasoningRaw === "minimal" && !supportsMinimal ? "low" : reasoningRaw };
  const systemPrompt = [
    "당신은 자동차보험 케어 리포트의 서사 작성 에이전트입니다.",
    "입력 JSON의 모든 숫자(점수·지수·거리·기여)는 결정론 엔진의 확정값입니다 — 재계산·수정·새 숫자 발명 금지, 인용만 하세요.",
    "aftercare 항목은 입력에 있는 id만 사용하세요. 새 지원 항목을 만들지 마세요.",
    "직원용(headline/summary/xai/staff)은 심사 전문가 톤으로 간결하게, 판단 근거가 10초 안에 읽히게.",
    "가족용(family_*)은 부모님의 운전을 걱정하는 자녀에게 보내는 소식입니다 — 따뜻한 존댓말로, 벌점·감액·경고·위험이라는 단어 없이 상황 설명과 지원 안내 중심으로.",
    "모든 데이터는 합성 시뮬레이션이며 실존 인물이 아닙니다.",
    `모든 서사 필드는 반드시 ${CARE_LANGUAGE_NAMES[String(localReport.target_language ?? "ko")] ?? "한국어"}(으)로 작성하세요 — 대시보드의 언어 선택을 그대로 따릅니다. 필드 키 이름(_ko 접미사 포함)은 스키마 고정이므로 바꾸지 마세요.`
  ].join("\n");
  const response = await fetch(envValue("OPENAI_RESPONSES_URL", repoRoot) || OPENAI_RESPONSES_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      ...(reasoning ? { reasoning } : {}),
      max_output_tokens: 4000,
      input: [
        { role: "system", content: systemPrompt },
        { role: "user", content: `deterministic_care_report=${JSON.stringify(localReport)}` }
      ],
      text: {
        format: {
          type: "json_schema",
          name: "care_narrative",
          strict: true,
          schema: CARE_NARRATIVE_SCHEMA
        }
      },
      metadata: { feature: "masil_care_report_v1" }
    })
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw Object.assign(new Error(`OpenAI ${response.status}: ${detail.slice(0, 200)}`), { statusCode: 502 });
  }
  const payload = (await response.json()) as JsonRecord;
  // Responses API: output[].content[].text (output_text) 또는 output_text 헬퍼 필드
  const direct = typeof payload.output_text === "string" ? payload.output_text : "";
  let text = direct;
  if (!text) {
    for (const item of toArray(payload.output)) {
      for (const part of toArray(toRecord(item).content)) {
        const rec = toRecord(part);
        if (typeof rec.text === "string") text += rec.text;
      }
    }
  }
  if (!text.trim()) {
    throw Object.assign(new Error("empty structured output"), { statusCode: 502 });
  }
  return JSON.parse(text) as JsonRecord;
}
