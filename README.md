# Neutech · Agent Operations

뉴테크 프로젝트의 최종 **10개 agent / 6개 금융 도구** 설계를 구현한 로컬 웹 애플리케이션입니다. 고객 이벤트 개인화와 마케팅 담당자 협업 캠페인을 함께 시연합니다. IRP는 포함하지 않습니다.

## 빠른 실행

Python **3.11 이상**만 있으면 됩니다. 런타임 패키지, Node.js, 외부 DB, API 키가 필요하지 않습니다.

```sh
git clone https://github.com/jhyun3555-pixel/JhAgent.git
cd JhAgent
python3 run.py
```

브라우저에서 **http://127.0.0.1:8765** 를 엽니다. macOS에서는 `시작.command`를 실행해도 됩니다. 포트가 사용 중이면 `python3 run.py --port 8767`로 바꿉니다.

최초 실행 시 `data/neutech.db`를 생성하고 **가상 고객 240명, 처리 이력 64건, 캠페인 4건**을 채웁니다. 이미 존재하는 데이터는 유지합니다. 종료는 실행한 터미널에서 `Ctrl+C`를 누릅니다. 컴퓨터 종료 시 서버도 중단되며, 다시 실행하면 기록이 복구됩니다.

## 시연 순서

1. **운영 대시보드**: 작업 분포 차트의 점이나 최근 작업을 선택해 처리 단계를 확인합니다. 시간 범위, 화면 일시정지를 지원합니다.
2. **시나리오 스튜디오**: 급여 입금·만기·안경점 결제·수신 미동의·빈도 초과·Do Nothing·장애·대출 시나리오를 실행합니다. 고객·금액·채널을 바꿀 수 있습니다.
3. **고객 선택**: 작업 상세에서 동의를 체크하고 서비스 연결을 시연하거나 ‘다음에 보기’, ‘관심 없음’을 선택합니다.
4. **캠페인 Co-Pilot**: 브리프와 조건을 입력하고 대상 수·제외 사유·중복 수·A/B 문안·비용을 확인한 뒤 승인 또는 반려합니다.
5. **자동 트래픽**: 2분 동안 가상 이벤트를 생성해 동시에 처리되는 agent를 확인합니다. 즉시 중지할 수 있습니다.
6. **성과 리포트**: 1/7/30일 기간을 선택해 고정 스냅샷을 만들고 CSV 다운로드 또는 인쇄/PDF 저장을 사용합니다.

고객에게 실제 편익이 없는 이벤트는 `Do Nothing`으로 종료합니다. 캠페인은 담당자 승인 전 발송되지 않으며, 서비스 연결은 고객의 명시적 선택과 동의를 요구합니다. 발송 시연 직전에도 최신 동의·빈도·적합성·예산을 재검증합니다.

> 모든 고객·거래·성과는 가상 데이터입니다. 기본 모드는 결정론적 규칙과 템플릿으로 동작합니다. 실제 푸시/SMS, 금융상품 가입, 외부 마이데이터 연결은 수행하지 않습니다. 초기 이력의 처리 시간은 합성 데이터이며 새 작업의 처리 시간은 실제 실행 측정값(시연 지연 포함)입니다.

## 화면

- 제니퍼의 트랜잭션 분포·Active Service·토폴로지·상세 추적 방식을 참고한 독자적인 다크 대시보드
- SSE 실시간 업데이트와 재연결, 검색·상태 필터, 승인 알림
- 작업별 순서도·타임라인·실행시간·입출력 JSON·감사 이력
- 각 agent의 실행 횟수, 평균 응답시간, 실패 단계와 독립 실행 계약
- 태블릿·모바일 대응 및 키보드 검색(`/`), 상세 닫기(`Esc`)

## 구조

```text
frontend/                 독립 웹 클라이언트 (ES modules, CSS, SVG)
backend/
  server.py               로컬 HTTP API, SSE, 요청 검증
  engine.py               큐, 승인, 체크포인트, 프로세스 격리, 발송 어댑터
  database.py             SQLite 스키마, 고객 데이터, 영속화
  analytics.py            성과 집계, 리포트 스냅샷, CSV/HTML
  catalog.py              agent 등록, 워크플로, 시나리오
  validation.py           입력 계약 검증
  policy.py               결정론적 동의·빈도·적합성·표현 정책
  provider.py             선택적 OpenAI Responses API 어댑터
  worker.py               agent 독립 실행 진입점 (JSON stdin/stdout)
  agents/                 10개 독립 역할 모듈
  skills/                 6개 금융 기회 도구
tests/                    통합·보안·복구 테스트와 브라우저 E2E
docs/                     구조, API, 시연 가이드
data/                     자동 생성 DB (Git 제외)
```

### Agent 독립성

각 agent는 `run(context) -> dict` 계약을 가집니다. 다른 agent 구현을 import하지 않고, 공통 JSON 계약으로 필요한 선행 결과를 전달받습니다. UI에서 실행하는 작업은 **agent 단계마다 별도 Python 프로세스**로 실행하며 시간 제한과 오류 격리를 적용합니다. 프로세스 입력·출력은 JSON이고 DB 저장과 실제 부수효과는 오케스트레이터의 어댑터가 담당합니다. 초기 합성 이력 생성과 단위 테스트만 빠른 인프로세스 모드를 사용합니다.

```sh
python3 -m backend.worker supervisor < docs/example-input.json
```

에이전트별 상시 서버·독립 DB를 가진 마이크로서비스 배포는 아닙니다. 실행 프로세스와 구현 모듈을 분리한 구조이며, JSON 전송 어댑터를 HTTP/메시지 큐로 바꾸어 확장할 수 있습니다. 공유 리소스는 정책 라이브러리와 버전 1 계약입니다.

## 실제 LLM 연결 (선택)

`.env.example`을 `.env`로 복사하고 환경에 맞게 설정합니다.

```dotenv
AGENT_PROVIDER=openai
OPENAI_API_KEY=발급받은_API_키
OPENAI_MODEL=계정에서_사용가능한_모델_ID
```

서버를 다시 실행하면 Strategy, Content, Performance가 **OpenAI Responses API의 Structured Outputs**를 사용합니다. 모델을 코드에서 임의 선택하지 않으며, 키와 모델 ID가 없으면 명시적으로 실패합니다. 실패 시 시연 성공으로 대체하지 않습니다. 키는 서버 환경에만 있고 DB·브라우저·로그에 저장하지 않습니다. 고객 명단은 전송하지 않지만 담당자가 입력한 브리프는 전송됩니다.

실제 LLM 호출은 API 키가 제공되지 않아 검증하지 않았습니다. 요청 구성과 오류 처리는 자동 테스트합니다. 자동 트래픽은 유료 API 호출을 방지하기 위해 시연 모드에서만 허용합니다. 실제 채널 발송은 LLM 모드에서도 시뮬레이션입니다.

공식 문서: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## 검증

```sh
python3 -m unittest discover -s tests -v
```

브라우저 검증은 Google Chrome과 Playwright가 필요합니다. 애플리케이션 실행에는 필요하지 않습니다.

```sh
npm install --no-save playwright
node tests/browser.e2e.cjs
```

테스트는 별도 포트 8766과 `test-results/`의 별도 DB를 사용합니다. 승인, 고객 선택, 동의·빈도 차단, Do Nothing, 장애 복구, 검색, 리포트, CSV, PDF 출력, 모바일 폭, 서버 재시작 후 보존을 검증합니다. 해당 폴더는 Git에서 제외됩니다.

## 설정

| 설정 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8765` | 로컬 웹 서버 포트 |
| `AGENT_PROVIDER` | `demo` | `demo` 또는 `openai` |
| `AGENT_STEP_DELAY` | `0.7` | 흐름을 관찰하기 위한 단계별 지연(초) |
| `AGENT_TIMEOUT` | `60` | agent 프로세스 시간 제한(초) |
| `--db` | `data/neutech.db` | 별도 DB 경로 |
| `--no-seed-history` | 꺼짐 | 240명 고객만 생성하고 초기 처리 이력 생략 |

SSE와 DB는 같은 로컬 서버에서 제공되며 외부 폰트/CDN에 의존하지 않습니다. 작업은 최대 4개를 동시에 처리합니다. 서버 재시작 시 실행 중이던 작업은 실패로 표시하고 수동 재시도를 지원합니다. 승인 대기 작업은 그대로 보존합니다. 성공한 단계는 재실행하지 않고, `(작업 ID, 고객 ID)` 유일 키로 중복 발송 기록을 방지합니다.

## 운영으로 확장할 때

현재 결과물은 **로컬 시연용 실행 애플리케이션**입니다. `127.0.0.1`에만 바인딩하며 Host/Origin/CSRF 검증과 입력 검증이 있습니다. 사용자 인증·역할별 접근 제어, 외부 수신거부 이벤트, 금융사 시스템, 실제 채널, 분산 큐, 외부 LLM 회귀평가는 아직 연결하지 않았습니다. 감사 로그는 애플리케이션에서 추가만 하지만 암호학적 변조 방지 저장소는 아닙니다. SQLite 단일 서버의 데모 규모에 맞춘 구현입니다.

리포트의 클릭률은 클릭/발송, 서비스 연결률은 연결/발송입니다. 실제 매출, ROI, 고객 편익, 민원·수신거부율은 수집하지 않아 임의의 실적으로 표시하지 않습니다. 시연용 정책은 법적 적합성 인증이 아닙니다.

설계 원본: 뉴테크 프로젝트의 「AI 에이전트 제출 형태」 최신 구성(2026-09-30). UI 참고: [JENNIFER Features](https://jennifersoft.com/en/product/features/).

추가 문서: [구조와 데이터 계약](docs/architecture.md), [HTTP API](docs/api.md), [시연 가이드](docs/demo-guide.md).
