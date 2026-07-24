"""TAAS 통계 기반 위험운전 유형 가중치 — 표에서 '계산'하며, 코드에 수기 상수를 두지 않는다.

원천 사슬(심사 검증용):
  data/raw/taas_stt_2010_2024.csv (도로교통공단 TAAS 시군구 통계)
    → src/data/taas_weights.py (연도별 위반유형 비중·야간 치명률 가중 산출)
    → data/processed/taas_weight_table.csv (본 모듈의 입력)
    → 이 모듈이 최신 연도 행에서 유형 분해 가중치를 유도
    → engine._risk_event_types 가 그대로 사용

역할 한계: 이 가중치는 이벤트 '수'를 유형으로 분해하는 표시용 분포다. 판정
(우대/기본/케어)은 이벤트 수·지수만 사용하므로 이 값이 바뀌어도 판정은 불변.

매핑 선언 — TAAS 법규위반 항목과 텔레매틱스 이벤트는 1:1이 아니므로, 대응이
성립하는 항목만 매핑하고 나머지는 제외를 명시한다.
  hard_brake(급제동)   ← 안전거리 미확보   (추돌 직전 급제동으로 표면화되는 위반)
  speeding(과속)       ← 과속 + 신호위반   (규정 속도·정지 신호를 지키지 않는 위반군.
                          과속 항목은 2021년부터 원천 미집계 → 표의 2010–2020 평균
                          기준치 컬럼을 사용)
  sudden_accel(급가속) ← 중앙선 침범       (추월·차로 이탈 가속 행동의 프록시)
  제외: 안전운전 의무 불이행(포괄 항목 — 단일 이벤트로 매핑 불가), 보행자
        보호의무 위반(차량 거동 아님), 차량단독(유형 정보 없음)
  야간(night_outer)    ← 야간사고 비중 × 야간 치명률 가중 (외곽 야간 맥락 전용)
"""

from __future__ import annotations

import csv
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
TAAS_WEIGHT_TABLE_PATH = _PROJECT_ROOT / "data" / "processed" / "taas_weight_table.csv"


def _load_latest_row(path: Path = TAAS_WEIGHT_TABLE_PATH) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as csvfile:
        rows = list(csv.DictReader(csvfile))
    if not rows:
        raise ValueError(f"TAAS weight table is empty: {path}")
    return max(rows, key=lambda row: int(row["year"]))


def _speeding_share(row: dict[str, str]) -> float:
    if int(row["speeding_weight_available"]):
        return float(row["speeding_weight"])
    return float(row["speeding_weight_reference_2010_2020"])


def _rounded_distribution(shares: dict[str, float], digits: int = 4) -> dict[str, float]:
    """비중을 정규화·반올림하되 마지막 성분을 잔여로 채워 합계 1을 구조적으로 보장."""
    total = sum(shares.values())
    if total <= 0:
        raise ValueError("TAAS mapped shares sum to zero")
    labels = list(shares)
    out: dict[str, float] = {}
    for label in labels[:-1]:
        out[label] = round(shares[label] / total, digits)
    out[labels[-1]] = round(1.0 - sum(out.values()), digits)
    return out


def derive_risk_type_weights(
    path: Path = TAAS_WEIGHT_TABLE_PATH,
) -> tuple[dict[str, float], dict[str, float], dict[str, object]]:
    """(비외곽 base, 외곽 야간 outer, 출처 provenance)를 표에서 유도한다."""

    row = _load_latest_row(path)
    try:
        hard_brake = float(row["safety_distance_weight"])
        speeding = _speeding_share(row) + float(row["signal_violation_weight"])
        sudden_accel = float(row["centerline_violation_weight"])
        night_share = float(row["night_accident_share"])
        night_fatality = float(row["night_fatality_weight"])
    except KeyError as missing:
        raise ValueError(
            f"TAAS weight table column {missing} not found in {path} — "
            "src/data/taas_weights.py 로 표를 재생성했는지 확인"
        ) from missing

    base = _rounded_distribution(
        {"hard_brake": hard_brake, "speeding": speeding, "sudden_accel": sudden_accel}
    )

    # 외곽 야간 맥락: 야간사고 비중에 야간 치명률 가중을 곱해 야간 축을 세우고,
    # 잔여분을 급제동·과속의 원천 비중 비율로 배분한다(급가속은 외곽 야간 유형셋 제외).
    night = round(min(0.85, night_share * night_fatality), 4)
    residual_pair = _rounded_distribution({"hard_brake": hard_brake, "speeding": speeding})
    outer_hard_brake = round((1.0 - night) * residual_pair["hard_brake"], 4)
    outer = {
        "night_outer": night,
        "hard_brake": outer_hard_brake,
        "speeding": round(1.0 - night - outer_hard_brake, 4),
    }

    provenance: dict[str, object] = {
        "source_table": "data/processed/taas_weight_table.csv",
        "source_raw": "data/raw/taas_stt_2010_2024.csv (도로교통공단 TAAS)",
        "builder": "src/data/taas_weights.py",
        "year_used": int(row["year"]),
        "inputs": {
            "safety_distance_weight": hard_brake,
            "speeding_share_used": _speeding_share(row),
            "speeding_share_is_2010_2020_reference": not int(
                row["speeding_weight_available"]
            ),
            "signal_violation_weight": float(row["signal_violation_weight"]),
            "centerline_violation_weight": sudden_accel,
            "night_accident_share": float(row["night_accident_share"]),
            "night_fatality_weight": float(row["night_fatality_weight"]),
        },
        "mapping": {
            "hard_brake": "안전거리 미확보",
            "speeding": "과속(2010–2020 기준치) + 신호위반",
            "sudden_accel": "중앙선 침범",
            "night_outer": "야간사고 비중 × 야간 치명률 가중",
            "excluded": ["안전운전 의무 불이행(포괄)", "보행자 보호의무 위반", "차량단독"],
        },
        "derived": {"base": base, "outer_night": outer},
        "role": "type_breakdown_display_only_decisions_unaffected",
    }
    return base, outer, provenance


(
    RISK_TYPE_WEIGHTS_BASE,
    RISK_TYPE_WEIGHTS_OUTER_NIGHT,
    TAAS_RISK_WEIGHT_PROVENANCE,
) = derive_risk_type_weights()
