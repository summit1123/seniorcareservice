"""AI 프로필 존 라벨 다양화 — 표시 전용 필드만 교체(판정 불변).

배경: 프로필 생성 시 다양성 제약이 없어 60명 중 44명이 '우리동네 새마을시장'을
받음. 라벨은 UI 표시 전용(판정은 bearing·share·시점만 사용)이므로, kind별 합성
라벨 풀에서 사람×존 시드로 결정론 추첨해 교체한다. 실존 상호는 사용하지 않는다.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "data" / "fixtures" / "mobility_profiles.json"

# kind → [(ko, en)] 합성 라벨 풀 (동네 어휘, 실존 상호 아님)
POOLS: dict[str, list[tuple[str, str]]] = {
    "market": [
        ("중앙시장", "Central Market"), ("골목시장", "Alley Market"), ("큰길시장", "Main Street Market"),
        ("은행나무시장", "Ginkgo Market"), ("샘터시장", "Springside Market"), ("햇살마트", "Sunshine Mart"),
        ("동네 하나마트", "Corner Grocery"), ("오거리시장", "Five-way Market"), ("풍년시장", "Harvest Market"),
        ("솔뫼시장", "Pine Hill Market"), ("장터거리", "Old Fair Street"), ("미소마트", "Smile Mart"),
    ],
    "senior_center": [
        ("동네 경로당", "Senior Hall"), ("마을 노인정", "Village Elder Lounge"), ("실버 사랑방", "Silver Lounge"),
        ("어르신 쉼터", "Elders' Rest House"), ("장수 경로당", "Longevity Hall"),
    ],
    "family": [
        ("딸네 집", "Daughter's Home"), ("아들네 집", "Son's Home"), ("손주네 집", "Grandchild's Home"),
        ("큰딸 집", "Eldest Daughter's Home"), ("막내네 집", "Youngest's Home"), ("동생네 집", "Sibling's Home"),
    ],
    "community": [
        ("주민센터 문화교실", "Community Culture Class"), ("서예 교실", "Calligraphy Class"),
        ("노래 교실", "Singing Class"), ("복지관 프로그램", "Welfare Center Program"),
        ("마을회관", "Village Hall"), ("탁구 교실", "Table Tennis Class"),
    ],
    "leisure": [
        ("냇가 산책길", "Riverside Walk"), ("약수터", "Mineral Spring"), ("뒷산 등산로", "Back-hill Trail"),
        ("게이트볼장", "Gateball Court"), ("동네 목욕탕", "Neighborhood Bathhouse"), ("호수공원", "Lake Park"),
        ("낚시터", "Fishing Spot"), ("파크골프장", "Park Golf Course"), ("장미공원", "Rose Park"),
    ],
    "church": [
        ("동네 성당", "Parish Church"), ("언덕 위 교회", "Hillside Church"), ("새벽교회", "Dawn Church"),
        ("중앙교회", "Central Church"),
    ],
    "temple": [("산사", "Mountain Temple"), ("솔숲 암자", "Pine Grove Hermitage")],
    "clinic": [
        ("정형외과 의원", "Orthopedic Clinic"), ("동네 내과", "Internal Medicine Clinic"),
        ("한의원", "Korean Medicine Clinic"), ("안과 의원", "Eye Clinic"),
    ],
    "hospital": [("종합병원", "General Hospital"), ("재활병원", "Rehab Hospital")],
    "friend": [("친구 집", "Friend's Home"), ("옛 동료 집", "Old Colleague's Home"), ("이웃사촌 집", "Close Neighbor's Home")],
    "farm": [("텃밭", "Vegetable Patch"), ("주말농장", "Weekend Farm"), ("비닐하우스", "Greenhouse")],
}
FALLBACK = [("단골 나들이처", "Regular Outing Spot"), ("자주 가는 곳", "Frequent Stop")]


def main() -> None:
    raw = json.loads(PROFILES.read_text(encoding="utf-8"))
    profiles = raw["profiles"] if isinstance(raw, dict) and "profiles" in raw else raw
    items = profiles.items() if isinstance(profiles, dict) else list(enumerate(profiles))

    changed = 0
    for key, prof in items:
        rng = random.Random(f"label-diversity|{key}")
        used: set[str] = set()
        for zi, zone in enumerate(prof.get("zones", [])):
            pool = POOLS.get(str(zone.get("kind")), FALLBACK)
            # 사람 안에서 중복 회피, 사람 간에는 시드로 자연 분산
            candidates = [p for p in pool if p[0] not in used] or pool
            ko, en = candidates[rng.randrange(len(candidates))]
            used.add(ko)
            if zone.get("label_ko") != ko:
                changed += 1
            zone["label_ko"] = ko
            zone["label_en"] = en
    PROFILES.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"라벨 교체 {changed}건 완료")


if __name__ == "__main__":
    main()
