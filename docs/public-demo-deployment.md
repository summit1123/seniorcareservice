# Public Demo Deployment

이 문서는 팀원 또는 심사위원이 `Senior Safe Mileage` 데모를 외부 URL로 볼 수 있게 만드는 운영 절차입니다.

## Cloudflare 설정

Cloudflare Zero Trust의 Tunnel Published Application은 아래 값으로 둡니다.

```text
Hostname: forsure.summit1123.co.kr
Path: 비움
Service URL: http://127.0.0.1:8003
```

- `Path`는 비워야 `/`, `/detail`, `/api/validation` 전체가 라우팅됩니다.
- `localhost`보다 `127.0.0.1`을 권장합니다. IPv6 해석 차이로 터널이 다른 주소를 볼 가능성을 줄입니다.
- 심사 직전 공개 링크로 쓸 때는 Access 정책을 끄거나, 심사위원 이메일 allowlist를 미리 등록합니다.
- 공개 기간이 길어질 경우 Cloudflare Access로 팀원/심사위원만 허용하는 편이 낫습니다.

## 로컬 실행

앱 서버와 Cloudflare 커넥터가 둘 다 살아 있어야 외부 URL이 동작합니다.

```bash
python3 -m src.webapp.customer_decision_app --host 127.0.0.1 --port 8003
cloudflared tunnel run --token-file ~/.cloudflared/summit1123.token
```

편의 스크립트:

```bash
scripts/run_public_demo.sh
```

이미 `8003` 앱 서버 또는 `summit1123.token` 기반 `cloudflared`가 떠 있으면 스크립트는 기존 프로세스를 재사용합니다. 터널 커넥터가 꺼져 있고 스크립트로 직접 켜야 하면 아래처럼 명시합니다.

```bash
START_TUNNEL=true scripts/run_public_demo.sh
```

## 체크

```bash
lsof -nP -iTCP:8003 -sTCP:LISTEN
curl -sS -I https://forsure.summit1123.co.kr/
curl -sS https://forsure.summit1123.co.kr/api/validation
```

정상 기준:

- `/`는 200 응답과 HTML 본문을 반환합니다.
- `/api/validation`은 200 응답과 `ok: true` JSON을 반환합니다.
- 5xx가 나오면 로컬 서버, Cloudflare 터널 커넥터, Published Application의 Service URL 순서로 확인합니다.

## 심사위원용 시연 순서

1. 첫 화면에서 `90일 주행 데이터`, `30명 고객`, `1,389건 trip log`, `OpenAI Report Agent 호출 상태`를 먼저 확인시킵니다.
2. `기존 마일리지 보험`과 `시니어 안심주행 방식`의 차이를 보여줍니다. 핵심은 “적게 타서 할인”이 아니라 “평소 생활권에서 벗어난 변화와 위험행동 증가를 조기 포착”하는 것입니다.
3. `고객 011` 사례를 중심으로 낮은 주행거리만 보면 우량 고객이지만, 최근 생활권 이탈과 급감속 패턴 변화가 커져 예방 케어로 넘어가는 흐름을 설명합니다.
4. 조건을 바꿔보는 시뮬레이션과 생활권 좌표 프리뷰를 보여주고, 필요할 때만 `/detail?customer_id=cust_011` 상세 화면으로 들어갑니다.

## 운영 주의사항

- 노트북으로 시연하면 macOS sleep을 막아야 합니다. 필요하면 다른 터미널에서 `caffeinate`를 켭니다.
- `.env`, OpenAI API key, Cloudflare token은 절대 커밋하지 않습니다.
- 외부 링크는 심사 또는 팀 공유가 끝나면 Access를 다시 걸거나 Published Application을 비활성화합니다.
