# TAAS 지자체별 대상사고통계 사용 메모

## 결론

`10_24_stt.csv`는 지자체별 대상사고통계 원천 파일로 사용한다.

다만 이 데이터는 지역별 위험도 판단에 직접 쓰지 않고, 전국/연도 기준 위험행동 가중치 테이블로 압축해서 사용한다.

```text
data/raw/taas_stt_2010_2024.csv
-> scripts/build_taas_weights.py
-> data/processed/taas_weight_table.csv
```

## 왜 지자체별 데이터를 받는가

TAAS API와 CSV가 지자체 단위로 제공되기 때문에 원천 수집은 지자체별로 한다.

하지만 우리 상품의 현재 방향은 위치기반 위험지역 모델이 아니다. 따라서 `법정동코드`를 고객 주행 위치와 직접 매칭하지 않는다.

## 집계 기준

CSV에는 시도 합계행과 하위 지자체행이 함께 들어 있다.

예를 들어 2024년 `전체` 사고는 모든 행을 합산하면 392,698건이지만, 시도 합계행만 합산하면 196,349건이다. 모든 행을 합산하면 중복 집계가 된다.

따라서 가중치 테이블은 `법정동코드`가 `00`으로 끝나는 17개 시도 합계행만 사용한다.

```text
aggregation_scope = sido_total_rows_only
```

## 사용하는 대상사고 구분

| CSV 값 | 사용 목적 |
|---|---|
| `전체` | 법규위반/사고유형 비중 계산 |
| `야간사고` | 야간 치사율 보정 |
| `고령운전사고` | 고령 운전자 사고 비중, 사망 비중, 치사율 보정 |
| `노인사고` | 참고용 고령 사고 치사율 |

## 생성되는 가중치

| 컬럼 | 의미 |
|---|---|
| `speeding_weight` | 전체사고 중 과속 비중 |
| `signal_violation_weight` | 전체사고 중 신호위반 비중 |
| `safety_distance_weight` | 전체사고 중 안전거리 미확보 비중 |
| `safe_driving_violation_weight` | 전체사고 중 안전운전 의무 불이행 비중 |
| `pedestrian_protection_weight` | 전체사고 중 보행자 보호의무 위반 비중 |
| `single_vehicle_weight` | 전체사고 중 차량단독 사고 비중 |
| `night_fatality_weight` | 야간사고 치사율 / 전체사고 치사율 |
| `elderly_driver_fatality_weight` | 고령운전사고 치사율 / 전체사고 치사율 |
| `elderly_driver_accident_share` | 전체사고 중 고령운전사고 비중 |
| `elderly_driver_death_share` | 전체 사망자 중 고령운전사고 사망자 비중 |

## 주의점

`과속` 필드는 2021년 이후 별도 집계 이슈로 CSV에서 0으로 들어온다. 따라서 2021~2024년 `speeding_weight=0`은 “과속 위험이 낮다”는 뜻이 아니라 해당 CSV 필드의 집계 한계로 본다.

이를 표시하기 위해 `speeding_weight_available`과 `speeding_weight_reference_2010_2020`을 함께 만든다.

## 발표 표현

아래처럼 표현한다.

```text
TAAS 지자체별 대상사고통계는 고객 위치를 평가하기 위한 데이터가 아니라,
과속, 안전거리 미확보, 야간, 고령운전사고 등 위험행동을 얼마나 무겁게 볼지 정하는 공공 사고통계 기반 보정 근거로 활용한다.
```
