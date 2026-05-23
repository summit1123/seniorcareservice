# Public Demo Deployment

이 문서는 팀원 또는 심사위원이 `Senior Safe Mileage` React Decision Dashboard를 외부 URL로 볼 수 있게 만드는 운영 절차입니다.

## Cloudflare 설정

Cloudflare Zero Trust의 Tunnel Published Application은 아래 값으로 둡니다.

```text
Hostname: forsure.summit1123.co.kr
Path: 비움
Service URL: http://localhost:8003
```

- `Path`는 비워야 `/`와 `/api/reports/stream`이 함께 라우팅됩니다.
- 현재 터널 원격 설정은 `forsure.summit1123.co.kr -> http://localhost:8003`으로 내려옵니다. 로컬 앱은 공개 배포용으로 `localhost:8003`에 띄웁니다.
- 심사 직전 공개 링크로 쓸 때는 Access 정책을 끄거나, 심사위원 이메일 allowlist를 미리 등록합니다.

## 로컬 실행

React 앱 서버와 Cloudflare 커넥터가 둘 다 살아 있어야 외부 URL이 동작합니다.

```bash
npm run dev -- --host localhost --port 8003
cloudflared tunnel run --token-file ~/.cloudflared/summit1123.token
```

편의 스크립트:

```bash
scripts/run_public_demo.sh
```

백그라운드 재기동 supervisor:

```bash
screen -S seniorcare-supervisor -dm bash "$HOME/Library/Application Support/SeniorCareService/local-demo/seniorcare-local-demo-supervisor.sh"
```

## 체크

```bash
lsof -nP -iTCP:8003 -sTCP:LISTEN
curl -sS -I https://forsure.summit1123.co.kr/
curl -N 'https://forsure.summit1123.co.kr/api/reports/stream?driverId=cust_011&month=9&basePremiumKrw=915000'
```

정상 기준:

- `/`는 200 응답과 React HTML 본문을 반환합니다.
- `/api/reports/stream`은 7개 Markdown 섹션을 chunk로 반환합니다.
- 5xx가 나오면 로컬 Vite 서버, Cloudflare 터널 커넥터, Published Application의 Service URL 순서로 확인합니다.

## 심사위원용 시연 순서

1. 첫 화면에서 30명 가상 사례, 기존 마일리지 기준선, 제안 통합 산식, 보험료 입력 영역을 먼저 확인시킵니다.
2. 같은 기존 주행거리 할인구간 안에서도 우대, 기본, 예방 케어가 갈리는 이유를 보여줍니다.
3. `조한기 어르신` 사례를 중심으로 생활권 지도, 월별 근거, XAI 판단 근거가 같은 선택 상태로 연결되는 흐름을 설명합니다.
4. 보험료 입력값을 바꿔 기존 할인액과 제안 통합 산식 할인액이 즉시 재계산되는 것을 보여줍니다.
5. 리포트 생성 버튼을 눌러 보험사 직원용 7섹션 Markdown 리포트가 streaming 되는 것을 확인시킵니다.

## 운영 주의사항

- 노트북으로 시연하면 macOS sleep을 막아야 합니다. 필요하면 다른 터미널에서 `caffeinate`를 켭니다.
- `.env`, OpenAI API key, Cloudflare token은 절대 커밋하지 않습니다.
- 외부 링크는 심사 또는 팀 공유가 끝나면 Access를 다시 걸거나 Published Application을 비활성화합니다.
