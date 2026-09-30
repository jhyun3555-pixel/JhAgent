# 로컬 HTTP API

기본 주소 `http://127.0.0.1:8765`. JSON 응답을 사용합니다. 상태 변경 요청은 `Content-Type: application/json`, bootstrap에서 발급한 `X-CSRF-Token`이 필요합니다. 브라우저 origin과 host는 현재 로컬 서버만 허용합니다. 키는 서버 시작마다 바뀝니다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/api/health` | 서버·provider 상태 |
| GET | `/api/bootstrap` | CSRF, 고객, 시나리오, 초기 상태 |
| GET | `/api/snapshot?minutes=15` | 5/15/60/1440분 대시보드 |
| GET | `/api/stream?minutes=15` | SSE `snapshot` 이벤트 |
| GET | `/api/jobs` | 최근 24시간 작업 최대 500건 |
| POST | `/api/jobs` | 이벤트 또는 캠페인 생성 |
| GET | `/api/jobs/{id}` | 입력·단계·결과·발송·감사 이력 |
| POST | `/api/jobs/{id}/decision` | 담당자/고객 선택 |
| POST | `/api/jobs/{id}/retry` | 실패 단계부터 재시도 |
| POST | `/api/jobs/{id}/cancel` | 종료 전 작업 중단 |
| POST | `/api/demo` | 2분 자동 트래픽 시작/중지 |
| GET | `/api/audit` | 최근 감사 기록 500건 |
| GET | `/api/reports` | 저장된 리포트 목록 |
| POST | `/api/reports` | 기간별 리포트 스냅샷 생성 |
| GET | `/api/reports/{id}` | 리포트 JSON |
| GET | `/api/reports/{id}.csv` | UTF-8 BOM CSV |
| GET | `/api/reports/{id}.html` | 인쇄/PDF 저장용 문서 |

## 작업 입력

```json
{"mode":"event","event_type":"salary","customer_id":"C0001","amount":4200000,"channel":"push"}
```

```json
{"mode":"campaign","brief":"여유자금 포트폴리오 안내","domain":"portfolio","min_balance":10000000,"max_audience":50,"budget":10000,"channel":"push"}
```

`Idempotency-Key` 헤더(128자 이하)를 주면 동일한 요청의 재전송은 기존 작업 ID를 반환합니다. 같은 키의 다른 내용은 거절합니다. 금액·인원은 유한한 정수만 허용합니다. 요청 본문 최대 크기는 16KB입니다. 최대 처리 대기열은 64개, 동시 작업은 4개입니다.

## 승인·선택 입력

```json
{"action":"approve"}
```

캠페인에는 `approve`/`reject`, 개인화에는 `accept`/`defer`/`decline`을 사용합니다. `accept`에는 `"consent":true`가 추가로 필요합니다. 현재 대기 상태가 액션과 일치해야 합니다.

```json
{"action":"accept","consent":true}
```

재시도·중단 입력은 `{}`입니다. 자동 트래픽은 `{"enabled":true}` 또는 `false`, 리포트 생성은 `{"days":7}` (1/7/30)입니다.

오류는 400/403/404/500 상태 코드와 `{"error":"설명"}`으로 반환합니다. SSE 연결은 상태 변경 또는 최대 2초 간격으로 스냅샷을 전송합니다. SSE 재연결 시 전체 상태를 재조회하므로 이벤트 유실이 화면 상태 유실로 이어지지 않습니다.
