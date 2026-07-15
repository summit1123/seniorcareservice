"""Nemotron-grounded senior-driver persona archetypes.

Method (mirrors NVIDIA Nemotron-Personas): a small set of REGION-NEUTRAL behaviour
archetypes (how a person drives), instantiated into distinct individuals with
correlated demographic variation AND per-person narrative variation (each person
gets their own bio, hobbies, family situation, goal, and habit nuance — two people
of the same type are never described identically).

Structure the engine relies on:
- 6 behaviour archetypes × 10 people = 60 distinct people (the roster).
- Each person is then run through all 3 mobility environments (도심·도농·광역),
  giving 60 × 3 = 180 simulated cases. Because the archetype is behaviour-only
  (no region baked into its identity), placing the same person in a denser or
  sparser environment is coherent — that IS the transferability experiment.
- ``designed_type`` is a VALIDATION label only; it never enters scoring (no leak).
- ``disposition`` shapes how the person drives; outcomes (우대/기본/예방케어/보류)
  emerge from the engine and are not targeted.
- A few individuals carry sparse telematics (device/low-activity variation), so
  판단 보류 appears naturally rather than being manufactured.
"""
from __future__ import annotations

from typing import Any

HOUSEHOLD_TYPES = {
    "solo": "독거",
    "couple": "부부 2인",
    "with_children": "자녀 동거",
    "with_spouse_care": "배우자 돌봄",
}

# 6 behaviour families (region-neutral). Value = display label.
DESIGNED_TYPES = {
    "stable_reward": "안정 저주행형",
    "in_zone_risky": "생활권 내 위험행동형",
    "mobility_change_safe": "이동변화·안전유지형",
    "mobility_risk_cochange": "이동·위험행동 동시변화형",
    "multi_zone": "복수 생활권형",
    "wide_area_safe": "광역 이동·안전형",
}

# ---------------------------------------------------------------------------
# 6 behaviour archetypes. `disposition` keys consumed by the engine:
#   monthly_visits      base visits/month
#   in_zone_reach_frac  in-zone destinations as a fraction of the environment's
#                       zone_reach_m (list = multiple destinations)
#   has_secondary_zone  a genuine second living zone (revisited, distinct cluster)
#   risk_rate           per-visit probability of a risky event at its locus
#   risk_locus          "none" | "in_zone" | "outer"
#   night_pref          0..1 share of night trips
#   change              None | "mobility" | "cochange" (shift from ~eval month 8)
# The identity carries NO region — density comes only from the environment.
# ---------------------------------------------------------------------------
ARCHETYPES: list[dict[str, Any]] = [
    {
        "id": "stable_reward",
        "name_ko": "안정 저주행형",
        "designed_type": "stable_reward",
        "age_range": (68, 84),
        "life_context_ko": "익숙한 반복 경로를 규칙적으로 오가는 저주행 안전 운전자",
        "disposition": {
            "monthly_visits": 7, "in_zone_reach_frac": [0.30, 0.55, 0.80],
            "has_secondary_zone": False, "risk_rate": 0.03, "risk_locus": "none",
            "night_pref": 0.06, "change": None,
        },
    },
    {
        "id": "in_zone_risky",
        "name_ko": "생활권 내 위험행동형",
        "designed_type": "in_zone_risky",
        "age_range": (67, 84),
        "life_context_ko": "멀리 가진 않지만 생활권 안에서 급제동·과속이 반복되는 운전자",
        "disposition": {
            "monthly_visits": 7, "in_zone_reach_frac": [0.30, 0.55],
            "has_secondary_zone": False, "risk_rate": 0.72, "risk_locus": "in_zone",
            "night_pref": 0.13, "change": None,
        },
    },
    {
        "id": "mobility_change_safe",
        "name_ko": "이동변화·안전유지형",
        "designed_type": "mobility_change_safe",
        "age_range": (66, 81),
        "life_context_ko": "하반기에 이동 범위가 넓어졌지만 위험행동 증가는 없는 운전자",
        "disposition": {
            "monthly_visits": 8, "in_zone_reach_frac": [0.35, 0.62],
            "has_secondary_zone": False, "risk_rate": 0.03, "risk_locus": "none",
            "night_pref": 0.13, "change": "mobility",
        },
    },
    {
        "id": "mobility_risk_cochange",
        "name_ko": "이동·위험행동 동시변화형",
        "designed_type": "mobility_risk_cochange",
        "age_range": (68, 83),
        "life_context_ko": "하반기에 외곽·야간 이동이 늘고 그 경로에서 위험행동이 함께 증가한 운전자",
        "disposition": {
            "monthly_visits": 8, "in_zone_reach_frac": [0.35, 0.60],
            "has_secondary_zone": False, "risk_rate": 0.03, "risk_locus": "outer",
            "night_pref": 0.18, "change": "cochange",
        },
    },
    {
        "id": "multi_zone",
        "name_ko": "복수 생활권형",
        "designed_type": "multi_zone",
        "age_range": (66, 78),
        "life_context_ko": "집과 멀리 떨어진 두 번째 거점을 규칙적으로 오가며 안전 운전을 유지하는 운전자",
        "disposition": {
            "monthly_visits": 10, "in_zone_reach_frac": [0.35, 0.60],
            "has_secondary_zone": True, "risk_rate": 0.03, "risk_locus": "none",
            "night_pref": 0.10, "change": None,
        },
    },
    {
        "id": "wide_area_safe",
        "name_ko": "광역 이동·안전형",
        "designed_type": "wide_area_safe",
        "age_range": (66, 83),
        "life_context_ko": "생활권 반경이 넓어 먼 거리를 자주 다니지만 위치와 무관하게 안전 운전을 유지하는 운전자",
        "disposition": {
            "monthly_visits": 8, "in_zone_reach_frac": [0.60, 0.95],
            "has_secondary_zone": False, "risk_rate": 0.045, "risk_locus": "none",
            "night_pref": 0.11, "change": None,
        },
    },
]

# 10 distinct people per archetype → 60-person roster.
PERSONS_PER_ARCHETYPE: dict[str, int] = {archetype["id"]: 10 for archetype in ARCHETYPES}
ROSTER_SIZE = sum(PERSONS_PER_ARCHETYPE.values())   # 60 distinct people
ENVIRONMENTS_PER_PERSON = 3                          # each person × 3 환경
COHORT_SIZE = ROSTER_SIZE * ENVIRONMENTS_PER_PERSON  # 180 simulated cases

# ---------------------------------------------------------------------------
# Synthetic names (성+이름, mixed gender). Not real people.
# ---------------------------------------------------------------------------
FAMILY_NAMES = (
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "류", "홍",
    "전", "고", "문", "손", "배", "백", "허", "유", "남", "심",
)
GIVEN_NAMES_FEMALE = (
    "순애", "말순", "옥분", "영자", "금례", "정순", "말자", "점례", "복순", "옥자",
    "순덕", "금자", "명숙", "춘자", "덕례", "말녀", "귀순", "옥임", "분례", "금순",
    "순임", "정례", "옥녀", "말숙", "금분", "순예", "덕순", "영순", "정자", "화자",
)
GIVEN_NAMES_MALE = (
    "병호", "정호", "재술", "갑수", "종달", "병국", "동철", "기석", "만복", "병수",
    "재복", "갑룡", "병희", "종수", "재만", "덕수", "우섭", "병철", "일만", "기수",
    "종국", "상철", "병일", "재훈", "만수", "석준", "영도", "기철", "종호", "태식",
)

# ---------------------------------------------------------------------------
# Per-person narrative variation (Nemotron pairs structured demographics with a
# personal narrative). Two people of the same behaviour type get different life
# details, goals, and habit nuances so no bio repeats.
# ---------------------------------------------------------------------------
HOUSEHOLDS_POOL = ("solo", "couple", "with_children", "with_spouse_care")
HOUSEHOLD_WEIGHTS = (0.42, 0.40, 0.12, 0.06)

LIFE_DETAILS = (
    "젊어서 시장에서 장사를 오래 했고 지금은 손주 보는 낙으로 지낸다",
    "평생 농사를 짓다 은퇴했고 텃밭 가꾸는 일을 이어간다",
    "교직에서 정년퇴직한 뒤 지역 봉사활동에 참여한다",
    "작은 가게를 운영하다 정리하고 요즘은 서예를 배운다",
    "공장 일을 오래 하다 은퇴했고 아침마다 약수터에 오른다",
    "주부로 지내며 성당·교회 모임을 꾸준히 나간다",
    "택시 운전을 오래 했고 지금도 운전에는 자신이 있다",
    "자녀를 다 출가시키고 배우자와 조용히 지낸다",
    "몸이 예전 같지 않아 병원 다니는 일이 잦아졌다",
    "동네 노인정에서 바둑·화투로 소일한다",
    "손주 등하원을 돕느라 정해진 시간에 움직인다",
    "낚시와 등산을 좋아해 주말이면 멀리 나선다",
    "종교 생활을 중심으로 규칙적인 하루를 보낸다",
    "혼자 지내며 필요한 볼일만 최소한으로 다닌다",
    "친목계 모임과 경조사 참석이 잦은 편이다",
)
HOBBY_POOL = (
    "서예", "텃밭 가꾸기", "등산", "낚시", "바둑", "화투", "노래 교실",
    "성당 봉사", "손주 돌보기", "산책", "게이트볼", "탁구",
)

# per-designed_type habit nuances (varied phrasings)
HABIT_VARIANTS: dict[str, tuple[str, ...]] = {
    "stable_reward": (
        "주로 낮 시간에 익숙한 길만 다니고 야간 운전은 삼간다",
        "가는 곳이 거의 정해져 있어 운전 습관이 한결같다",
        "비 오는 날이나 어두워지면 아예 차를 두고 걸어 다닌다",
        "출발 전 늘 여유 있게 준비하고 서두르지 않는다",
    ),
    "in_zone_risky": (
        "가까운 거리인데도 급출발·급제동이 잦은 편이다",
        "신호가 바뀌면 서두르는 습관이 있어 급정거가 많다",
        "짧은 길이라 방심하는지 과속이 반복된다",
        "익숙한 길일수록 속도를 내는 경향이 있다",
    ),
    "mobility_change_safe": (
        "최근 다니는 범위가 넓어졌지만 운전 자체는 조심스럽다",
        "새 일정이 생겨 이동이 늘었어도 위험한 습관은 없다",
        "먼 길이 잦아졌지만 속도를 지키며 다닌다",
        "이동은 많아졌으나 야간엔 되도록 운전을 피한다",
    ),
    "mobility_risk_cochange": (
        "하반기 들어 야간·외곽 운전이 늘고 그 길에서 급제동이 잦아졌다",
        "생활 리듬이 바뀌며 늦은 시간 먼 길 운전이 부쩍 늘었다",
        "새로 다니게 된 외곽 경로에서 과속·급정거가 함께 늘었다",
        "달라진 동선에서 위험 운전 신호가 함께 나타난다",
    ),
    "multi_zone": (
        "집과 두 번째 거점을 규칙적으로 오가며 대체로 안정적이다",
        "멀리 떨어진 곳을 정기적으로 다니지만 운전은 차분하다",
        "두 생활권을 오가는 동선이 몸에 배어 안정적으로 운전한다",
        "정해진 왕복 경로라 익숙하게, 안전하게 다닌다",
    ),
    "wide_area_safe": (
        "먼 거리를 자주 다니지만 위험 운전 없이 꾸준하다",
        "이동 반경이 넓어도 규정 속도를 지키며 다닌다",
        "장거리가 잦아도 무리 없이 안전하게 운전한다",
        "위치는 넓게 다녀도 운전 습관은 안정적이다",
    ),
}
GOAL_VARIANTS: dict[str, tuple[str, ...]] = {
    "stable_reward": (
        "익숙한 동네 안에서 앞으로도 안전하게 직접 운전하며 지내는 것",
        "지금처럼 큰 사고 없이 필요한 볼일을 스스로 다니는 것",
        "가족에게 부담 주지 않고 오래 운전대를 잡는 것",
    ),
    "in_zone_risky": (
        "가까운 볼일은 계속 다니되 급한 운전 습관을 스스로 줄이는 것",
        "사고 없이 지금의 이동을 이어가되 조급함을 고치는 것",
        "익숙한 길에서도 속도를 지키는 습관을 들이는 것",
    ),
    "mobility_change_safe": (
        "가족·건강 사정으로 늘어난 이동을 무리 없이 감당하는 것",
        "바뀐 일정을 소화하면서도 안전 운전을 유지하는 것",
        "이동이 많아져도 사고 없이 다니는 것",
    ),
    "mobility_risk_cochange": (
        "달라진 생활 리듬 속에서도 사고 없이 이동을 이어가는 것",
        "늘어난 야간·외곽 운전을 스스로 점검하며 안전을 되찾는 것",
        "필요한 이동은 하되 위험 운전 습관을 줄이는 것",
    ),
    "multi_zone": (
        "두 생활권을 오가며 가족을 돌보는 일상을 계속 유지하는 것",
        "멀리 있는 가족을 오래도록 직접 챙기러 다니는 것",
        "왕복 이동을 안전하게 이어가며 돌봄을 지속하는 것",
    ),
    "wide_area_safe": (
        "거리가 멀어도 필요한 곳까지 안전하게 오가는 것",
        "넓은 반경의 일상을 사고 없이 유지하는 것",
        "먼 취미·볼일을 앞으로도 직접 다니는 것",
    ),
}
# individuals (by roster index) whose telematics is sparse → 판단 보류 emerges.
# One low-activity safe person and one wide-area person; sparse in all 3 환경.
SPARSE_PERSON_INDEXES = (6, 57)


def _person_seed(seed: int, *parts: object) -> int:
    import hashlib

    key = "|".join(str(part) for part in (seed, "roster", *parts))
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)


def build_person_roster(seed: int) -> list[dict[str, Any]]:
    """Deterministically build the 60-person roster.

    Each person is a distinct individual (unique name, exact age, household,
    hobby, and a personal narrative varied per person) carrying one behaviour
    archetype's disposition. The engine runs each person across all 3 environments.
    """
    import random

    used_names: set[str] = set()
    roster: list[dict[str, Any]] = []
    sequence = 0
    for archetype in ARCHETYPES:
        count = PERSONS_PER_ARCHETYPE.get(archetype["id"], 0)
        for local_index in range(count):
            roster_index = sequence
            sequence += 1
            person_id = f"p{sequence:02d}"
            rng = random.Random(_person_seed(seed, archetype["id"], local_index))
            dtype = archetype["designed_type"]

            # sex + name (unique)
            sex = "female" if rng.random() < 0.52 else "male"
            given_pool = GIVEN_NAMES_FEMALE if sex == "female" else GIVEN_NAMES_MALE
            name = ""
            for _ in range(400):
                candidate = rng.choice(FAMILY_NAMES) + rng.choice(given_pool)
                if candidate not in used_names:
                    name = candidate
                    break
            if not name:
                name = rng.choice(FAMILY_NAMES) + rng.choice(given_pool) + rng.choice("자순덕")
            used_names.add(name)

            low, high = archetype["age_range"]
            age = rng.randint(low, high)
            household = rng.choices(HOUSEHOLDS_POOL, weights=HOUSEHOLD_WEIGHTS, k=1)[0]
            hh_ko = HOUSEHOLD_TYPES[household]
            retired = age >= 68 or rng.random() < 0.7
            life_detail = rng.choice(LIFE_DETAILS)
            hobby = rng.choice(HOBBY_POOL)
            habit = rng.choice(HABIT_VARIANTS[dtype])
            goal = rng.choice(GOAL_VARIANTS[dtype])
            purpose = archetype["life_context_ko"]

            narrative = (
                f"{name}({age}세)은 {hh_ko} 가구의 시니어로, {life_detail}. "
                f"취미는 {hobby}이며, {habit}."
            )

            disposition = dict(archetype["disposition"])
            data_quality = "sparse" if roster_index in SPARSE_PERSON_INDEXES else "good"
            if data_quality == "sparse":
                disposition["monthly_visits"] = 5
                disposition["trip_distance_scale"] = round(rng.uniform(0.85, 1.15), 2)
            else:
                # Per-person driving variation so two people of the same archetype
                # are not near-identical. Bounded around the archetype base, so the
                # behaviour tendency (and the Care gates, which don't read risk_rate)
                # is preserved while activity level, risk intensity, and odometer
                # km genuinely differ person to person.
                base_visits = int(disposition["monthly_visits"])
                disposition["monthly_visits"] = max(4, round(base_visits * rng.uniform(0.7, 1.4)))
                disposition["risk_rate"] = round(min(0.92, float(disposition["risk_rate"]) * rng.uniform(0.6, 1.5)), 3)
                # Odometer km per trip varies by person. For the in-zone-risky type
                # the whole point is high risk *density* (events per km), so keep its
                # per-trip distance tight — otherwise longer trips dilute the density
                # and the driver drifts out of the neutral tendency. Scaling monthly
                # visits (which adds risk events and km together) keeps density intact.
                if disposition.get("risk_locus") == "in_zone":
                    disposition["trip_distance_scale"] = round(rng.uniform(0.9, 1.12), 2)
                else:
                    disposition["trip_distance_scale"] = round(rng.uniform(0.78, 1.4), 2)
            disposition["data_quality"] = data_quality

            roster.append(
                {
                    "person_id": person_id,
                    "archetype_id": archetype["id"],
                    "designed_type": dtype,
                    "designed_type_ko": DESIGNED_TYPES[dtype],
                    "name_ko": name,
                    "age": age,
                    "sex": sex,
                    "household": household,
                    "household_ko": hh_ko,
                    "retired": retired,
                    "hobby_ko": hobby,
                    "primary_purpose_ko": purpose,
                    "life_context_ko": archetype["life_context_ko"],
                    "persona_narrative_ko": narrative,
                    "mobility_goal_ko": goal,
                    "driving_habit_ko": habit,
                    "data_quality": data_quality,
                    "disposition": disposition,
                }
            )
    return roster
