"""Agent-generated mobility profiles (Option C).

The deterministic GAIP engine (``engine.py``) synthesises 14 months of visit
events from a person's ``disposition``.  Option C inserts a reasoning step *in
front* of that synthesis: an LLM agent reads each senior's life context (bio,
household, hobby, goal, driving habit) and reasons out **where they plausibly
go, how their week is shaped, and when their life changes** — a structured,
human-meaningful ``mobility_profile``.

Division of labour (this is the experiment structure):

* **Agent's reasoning domain** — the *spatial / temporal / naming / narrative*
  layer: named life-grounded living zones (label, kind, bearing, distance band,
  visit share, active months), the per-person **change month + trigger**, and a
  short rationale.  This is genuine reasoning grounded in the persona, not a
  template fill, and it is what the map and evidence report show on screen.
* **Engine's domain** — expands the profile into seeded visit events and then
  scores them **blind**: real DBSCAN clustering, home-radial P90 buffers, the
  integrated reward score, and the Care AND-gate.  The engine never sees the
  ``designed_type`` or the agent's intent; outcomes EMERGE.

The archetype's behavioural *tendency* (safe / risky, changes / stable, one zone
/ several) is the **experimental control**: it is fed to the agent as a
structural brief so the generated life is coherent with a known ground truth,
and the risk *magnitude* stays keyed to the archetype in the engine.  A
validation loop then confirms the blind engine recovers the intended tendency.

Profiles are generated **once, offline** and cached under
``data/fixtures/mobility_profiles.json`` (committed), so the demo stays
deterministic and reproducible; the seeded event expansion is unchanged.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

# --------------------------------------------------------------------------
# Controlled vocabulary — the agent must choose zone kinds from this set, so
# the display layer maps a stable, review-safe label set (no free-text leaks).
# --------------------------------------------------------------------------
ZONE_KINDS: dict[str, str] = {
    "home": "자택 인근",
    "market": "동네 시장·마트",
    "hospital": "종합병원",
    "clinic": "동네 의원",
    "pharmacy": "약국",
    "church": "성당·교회",
    "temple": "사찰",
    "senior_center": "노인정·경로당",
    "community": "주민센터·복지관",
    "family": "가족 집",
    "friend": "지인 모임",
    "work": "일터·텃밭",
    "farm": "농지·과수원",
    "leisure": "취미 활동지",
    "errand": "생활 볼일",
    "market_town": "읍내 중심가",
}

# Distance band -> fraction of the environment's zone_reach / outer distance.
# "near"/"mid_in" cluster inside the home zone; "secondary" forms its own
# living-zone cluster; "outer" is genuinely out of zone.  These bands keep the
# generated geometry inside contract-safe bounds regardless of agent wording.
DISTANCE_BANDS: tuple[str, ...] = ("near", "mid_in", "secondary", "outer")

# Roles the engine understands.  home is implicit (always present).
ZONE_ROLES: tuple[str, ...] = ("in_zone", "secondary", "change_destination")

EVAL_MONTH_MIN = 8
EVAL_MONTH_MAX = 12
TOTAL_MONTHS = 14


class MobilityProfileError(ValueError):
    """Raised when an agent profile fails schema / structural validation."""


# --------------------------------------------------------------------------
# Per-archetype structural brief.  The `requires` block is enforced by
# validation (regenerate on violation); the `intent` guides the reasoning.
# --------------------------------------------------------------------------
def archetype_brief(archetype_id: str) -> dict[str, Any]:
    briefs: dict[str, dict[str, Any]] = {
        "stable_reward": {
            "intent": (
                "익숙한 동네 안에서 규칙적으로만 움직이는 저주행 안전 운전자. "
                "생활권이 좁고 한결같으며, 하반기에도 이동 범위가 넓어지지 않는다."
            ),
            "requires": {"secondary": (0, 0), "change_destination": (0, 0), "change": False},
        },
        "in_zone_risky": {
            "intent": (
                "멀리 가지는 않지만 생활권 안에서 급제동·과속이 잦은 운전자. "
                "이동 범위 자체는 좁고 안정적이며, 갑작스러운 범위 확대는 없다."
            ),
            "requires": {"secondary": (0, 0), "change_destination": (0, 0), "change": False},
        },
        "mobility_change_safe": {
            "intent": (
                "하반기 어느 달부터 새로운 목적지가 생겨 이동 범위가 넓어지지만, "
                "운전 자체는 여전히 조심스러워 위험행동은 늘지 않는 운전자. "
                "이동 변화만으로는 케어 대상이 아니라는 것을 보여주는 사례."
            ),
            "requires": {"secondary": (0, 0), "change_destination": (1, 1), "change": True},
        },
        "mobility_risk_cochange": {
            "intent": (
                "하반기 어느 달부터 외곽·야간 이동이 늘고, 바로 그 새 경로에서 "
                "급제동·과속 같은 위험행동이 함께 나타나는 운전자. 같은 달 이동 변화와 "
                "위험행동 변화가 함께 나타나 사람 검토(예방 케어)가 제안되는 사례."
            ),
            "requires": {"secondary": (0, 0), "change_destination": (1, 1), "change": True},
        },
        "multi_zone": {
            "intent": (
                "집과 멀리 떨어진 두 번째(때로 세 번째) 생활 거점을 규칙적으로 오가며 "
                "안전 운전을 유지하는 운전자. 예: 다른 동네의 가족 집, 농지, 정기 모임. "
                "여러 생활권이 있어도 급작스러운 변화가 아니므로 케어 대상이 아니다."
            ),
            "requires": {"secondary": (1, 2), "change_destination": (0, 0), "change": False},
        },
        "wide_area_safe": {
            "intent": (
                "생활 반경이 넓어 먼 거리를 자주 다니지만 위치와 무관하게 안전 운전을 "
                "유지하는 운전자. 넓은 이동 자체는 불이익이 아니라는 것을 보여주는 사례."
            ),
            "requires": {"secondary": (0, 1), "change_destination": (0, 0), "change": False},
        },
    }
    return briefs[archetype_id]


SCHEMA_HINT = """{
  "reasoning_ko": "이 시니어의 생활에 근거해 왜 이런 생활권과 변화가 나오는지 1-2문장",
  "reasoning_en": "same rationale in natural English (1-2 sentences)",
  "home_label_ko": "자택 인근",
  "home_label_en": "Home area",
  "zones": [
    {
      "label_ko": "생활에 맞는 실제 목적지 이름 (예: 우리동네 새마을시장)",
      "label_en": "the same destination name in English (e.g. Neighborhood Market)",
      "kind": "market",                    // ZONE_KINDS 중 하나
      "role": "in_zone",                    // in_zone | secondary | change_destination
      "bearing_deg": 40,                    // 0-359, 집 기준 방향 (사람마다 다르게)
      "distance_band": "near",              // near | mid_in | secondary | outer
      "visit_share": 0.45,                  // 이 목적지 방문 비중 (zones 합계 ~1.0)
      "typical_days_ko": "월·수·금 오전",     // 짧은 문구
      "active_from_month": 1,               // 1-14 (1-2=기준선, 3-14=평가)
      "active_to_month": 14
    }
  ],
  "change_month": null,                     // 이동 변화형만: 8-12 사이 정수, 아니면 null
  "change_trigger_ko": null,                // 이동 변화형만: 변화 계기 1문장, 아니면 null
  "change_trigger_en": null                 // 이동 변화형만: same trigger in English, else null
}"""


def build_input_payload(person: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the Responses API messages for one person."""

    brief = archetype_brief(str(person["archetype_id"]))
    req = brief["requires"]
    sec_lo, sec_hi = req["secondary"]
    chg_lo, chg_hi = req["change_destination"]
    data_quality = str(person.get("data_quality", "good"))
    sparse_note = (
        "\n- 이 사람은 텔레매틱스 데이터가 희소(sparse)합니다. 방문이 적고 거점이 뚜렷하지 "
        "않게, zones는 1개(자택 인근 위주)로 최소화하세요."
        if data_quality == "sparse"
        else ""
    )

    system_text = (
        "당신은 시니어 운전자의 생활 맥락으로부터 현실적인 14개월 이동 프로필을 설계하는 "
        "모빌리티 애널리스트입니다. 실제 사람이 아닌 합성 페르소나이며, 결과는 결정론 "
        "보험 엔진이 '유형을 모른 채' 군집·채점합니다. 당신의 임무는 이 사람의 삶에 "
        "비추어 '어디를, 어떤 리듬으로, 언제부터 다르게' 다니는지를 근거 있게 구성하는 "
        "것입니다. 반드시 유효한 JSON 하나만 출력하세요(코드블록·주석·설명 금지)."
    )

    user_text = f"""다음 시니어의 14개월 이동 프로필을 설계하세요.

[페르소나]
- 이름/나이/가구: {person['name_ko']} · {person['age']}세 · {person['household_ko']}
- 생활 배경: {person['persona_narrative_ko']}
- 주 목적: {person['primary_purpose_ko']}
- 운전 습관: {person['driving_habit_ko']}
- 이동 목표: {person['mobility_goal_ko']}

[이 유형의 행동 성향 — 반드시 부합하게 구성]
{brief['intent']}

[구조 제약 — 반드시 지킬 것]
- 자택(home) 1곳은 암묵적으로 존재. zones에는 자택 외 목적지만 나열.
- role="in_zone"(가까운 생활권 목적지) 1~3개 포함.
- role="secondary"(집과 멀리 떨어진 별도 생활권 거점) {sec_lo}~{sec_hi}개.
- role="change_destination"(하반기부터 새로 생기는 목적지) {chg_lo}~{chg_hi}개.
- change_month: 이동 변화형이면 {EVAL_MONTH_MIN}~{EVAL_MONTH_MAX} 사이 정수(사람마다 다르게), 아니면 null.
- change_destination이 있으면 그 zone의 active_from_month = change_month 로 맞추세요.
- bearing_deg는 사람마다 다양하게(한쪽에 몰리지 않게). visit_share 합은 대략 1.0.
- 모든 텍스트 필드는 한국어(*_ko)와 자연스러운 영어(*_en)를 함께 채우세요(GAIP 영어 심사용).{sparse_note}

[출력 JSON 스키마]
{SCHEMA_HINT}

이 사람만의 실제 삶에 맞는 목적지 이름과 리듬으로, 위 스키마의 JSON만 출력하세요."""

    return [
        {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
        {"role": "user", "content": [{"type": "input_text", "text": user_text}]},
    ]


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a text response (strips code fences)."""

    cleaned = text.strip()
    # strip ```json ... ``` fences if present
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MobilityProfileError(f"response was not valid JSON: {exc}") from exc


def validate_profile(profile: Mapping[str, Any], person: Mapping[str, Any]) -> dict[str, Any]:
    """Validate + normalise one profile against the archetype's structural brief.

    Raises ``MobilityProfileError`` with an actionable message (fed back to the
    agent on retry) when the structure violates the archetype contract.
    """

    brief = archetype_brief(str(person["archetype_id"]))
    req = brief["requires"]

    if not isinstance(profile, Mapping):
        raise MobilityProfileError("profile must be a JSON object")
    zones_in = profile.get("zones")
    if not isinstance(zones_in, list) or not zones_in:
        raise MobilityProfileError("zones must be a non-empty array")

    zones: list[dict[str, Any]] = []
    role_counts = {role: 0 for role in ZONE_ROLES}
    for index, zone in enumerate(zones_in):
        if not isinstance(zone, Mapping):
            raise MobilityProfileError(f"zones[{index}] must be an object")
        kind = str(zone.get("kind", "")).strip()
        if kind not in ZONE_KINDS:
            raise MobilityProfileError(
                f"zones[{index}].kind '{kind}' not in allowed ZONE_KINDS {sorted(ZONE_KINDS)}"
            )
        role = str(zone.get("role", "")).strip()
        if role not in ZONE_ROLES:
            raise MobilityProfileError(
                f"zones[{index}].role '{role}' must be one of {ZONE_ROLES}"
            )
        band = str(zone.get("distance_band", "")).strip()
        if band not in DISTANCE_BANDS:
            raise MobilityProfileError(
                f"zones[{index}].distance_band '{band}' must be one of {DISTANCE_BANDS}"
            )
        try:
            bearing = float(zone.get("bearing_deg", 0)) % 360.0
            share = max(0.0, float(zone.get("visit_share", 0.0)))
            active_from = int(zone.get("active_from_month", 1))
            active_to = int(zone.get("active_to_month", TOTAL_MONTHS))
        except (TypeError, ValueError) as exc:
            raise MobilityProfileError(f"zones[{index}] has a non-numeric field: {exc}") from exc
        active_from = min(max(active_from, 1), TOTAL_MONTHS)
        active_to = min(max(active_to, active_from), TOTAL_MONTHS)
        # Established zones (in_zone / secondary) must be present in the 2 baseline
        # months so the engine clusters them into a home / secondary hub. Only a
        # change_destination appears mid-year (its window is set from change_month
        # below). Pinning active_from here keeps the baseline-hub contract intact
        # regardless of what the agent proposed.
        if role in ("in_zone", "secondary"):
            active_from = 1
            active_to = TOTAL_MONTHS
        label = str(zone.get("label_ko", "")).strip() or ZONE_KINDS[kind]
        label_en = str(zone.get("label_en", "")).strip() or label
        role_counts[role] += 1
        zones.append(
            {
                "label_ko": label,
                "label_en": label_en,
                "kind": kind,
                "role": role,
                "bearing_deg": round(bearing, 1),
                "distance_band": band,
                "visit_share": round(share, 4),
                "typical_days_ko": str(zone.get("typical_days_ko", "")).strip(),
                "active_from_month": active_from,
                "active_to_month": active_to,
            }
        )

    # structural contract checks
    if role_counts["in_zone"] < 1:
        raise MobilityProfileError("at least one zone with role='in_zone' is required")
    for role_key, (lo, hi) in (("secondary", req["secondary"]), ("change_destination", req["change_destination"])):
        count = role_counts[role_key]
        if not (lo <= count <= hi):
            raise MobilityProfileError(
                f"archetype '{person['archetype_id']}' requires {lo}-{hi} zones with "
                f"role='{role_key}', got {count}"
            )

    change_month = profile.get("change_month")
    change_required = bool(req["change"])
    if change_required:
        if not isinstance(change_month, (int, float)) or not (
            EVAL_MONTH_MIN <= int(change_month) <= EVAL_MONTH_MAX
        ):
            raise MobilityProfileError(
                f"change_month must be an integer {EVAL_MONTH_MIN}-{EVAL_MONTH_MAX} for this archetype"
            )
        change_month = int(change_month)
        # the change_destination must switch on at change_month
        for zone in zones:
            if zone["role"] == "change_destination":
                zone["active_from_month"] = change_month
                zone["active_to_month"] = TOTAL_MONTHS
    else:
        change_month = None

    total_share = sum(zone["visit_share"] for zone in zones) or 1.0
    for zone in zones:
        zone["visit_share"] = round(zone["visit_share"] / total_share, 4)

    reasoning_ko = str(profile.get("reasoning_ko", "")).strip()
    home_label_ko = str(profile.get("home_label_ko", "")).strip() or ZONE_KINDS["home"]
    return {
        "person_id": str(person["person_id"]),
        "archetype_id": str(person["archetype_id"]),
        "reasoning_ko": reasoning_ko,
        "reasoning_en": str(profile.get("reasoning_en", "")).strip() or reasoning_ko,
        "home_label_ko": home_label_ko,
        "home_label_en": str(profile.get("home_label_en", "")).strip() or "Home area",
        "zones": zones,
        "change_month": change_month,
        "change_trigger_ko": (
            str(profile.get("change_trigger_ko")).strip()
            if change_required and profile.get("change_trigger_ko")
            else None
        ),
        "change_trigger_en": (
            str(profile.get("change_trigger_en")).strip()
            if change_required and profile.get("change_trigger_en")
            else None
        ),
        "source": "mobility_agent",
    }


def generate_mobility_profile(person: Mapping[str, Any], client: Any, *, max_attempts: int = 3) -> dict[str, Any]:
    """Call the LLM agent for one person, parse + validate, retry with feedback."""

    payload = build_input_payload(person)
    last_error: str | None = None
    for attempt in range(max_attempts):
        messages = list(payload)
        if last_error is not None:
            messages = messages + [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "직전 출력이 검증을 통과하지 못했습니다: "
                                f"{last_error}. 구조 제약을 지켜 JSON만 다시 출력하세요."
                            ),
                        }
                    ],
                }
            ]
        response = client.create_text_response(messages, purpose="masil_gaip_mobility_profile")
        try:
            raw = _extract_json(response.text)
            return validate_profile(raw, person)
        except MobilityProfileError as exc:
            last_error = str(exc)
    raise MobilityProfileError(
        f"could not generate a valid profile for {person['person_id']} after {max_attempts} attempts: {last_error}"
    )
