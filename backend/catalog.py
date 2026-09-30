AGENTS = [
    ('supervisor', 'Supervisor', '업무 분류 · 실행 계획', 'control'),
    ('insight', 'Customer Insight', '고객 상황 · 금융 맥락', 'analysis'),
    ('opportunity', 'Opportunity Discovery', '6개 도메인 기회 탐색', 'analysis'),
    ('strategy', 'Campaign Strategy', '캠페인 콘셉트 · 아이디어', 'campaign'),
    ('audience', 'Audience Builder', '대상 추출 · 중복 및 제외', 'campaign'),
    ('content', 'Personalization & Content', '개인화 메시지 · A/B 문안', 'creation'),
    ('compliance', 'Compliance & Policy', '동의 · 적합성 · 발송 정책', 'policy'),
    ('journey', 'Individual Journey', '고객 선택 · 서비스 연결', 'execution'),
    ('campaign', 'Campaign Orchestrator', '담당자 승인 · 캠페인 실행', 'execution'),
    ('performance', 'Performance & Learning', '성과 측정 · 개선안', 'learning'),
]
AGENT_IDS = [a[0] for a in AGENTS]
EVENT_FLOW = ['supervisor', 'insight', 'opportunity', 'content', 'compliance', 'journey', 'performance']
CAMPAIGN_FLOW = ['supervisor', 'strategy', 'audience', 'insight', 'content', 'compliance', 'campaign', 'performance']
DOMAINS = {'portfolio': 'AI 포트폴리오', 'deposit': '예적금·만기', 'loan': '대출 관리', 'card': '카드 혜택', 'tax': '환급·절세 검토', 'mydata': '마이데이터 연결'}
EVENTS = {'salary': '급여 입금', 'balance': '잔액 증가', 'maturity': '예적금 만기', 'loan': '대출 조건 점검', 'card': '카드 결제', 'tax': '안경점 결제', 'mydata': '정보 연결 필요', 'quiet': '일반 거래'}
SCENARIOS = [
    {'id': 'salary', 'title': '급여 입금', 'description': '여유자금 분석과 포트폴리오 안내', 'event_type': 'salary', 'customer_id': 'C0001', 'amount': 4200000, 'expected': '고객 선택 대기', 'color': 'cyan'},
    {'id': 'maturity', 'title': '예적금 만기', 'description': '만기 자금의 재예치 선택지 비교', 'event_type': 'maturity', 'customer_id': 'C0002', 'amount': 30000000, 'expected': '고객 선택 대기', 'color': 'purple'},
    {'id': 'tax', 'title': '안경점 결제', 'description': '정보가 부족하면 마이데이터 연결 제안', 'event_type': 'tax', 'customer_id': 'C0003', 'amount': 350000, 'expected': '고객 동의 필요', 'color': 'blue'},
    {'id': 'no_consent', 'title': '수신 동의 없음', 'description': '동의 미보유 고객의 발송 자동 차단', 'event_type': 'salary', 'customer_id': 'C0004', 'amount': 4200000, 'expected': '정책 차단', 'color': 'red'},
    {'id': 'frequency', 'title': '발송 빈도 초과', 'description': '최근 7일간 3회 이상 안내한 고객 제외', 'event_type': 'balance', 'customer_id': 'C0005', 'amount': 12000000, 'expected': '정책 차단', 'color': 'amber'},
    {'id': 'nothing', 'title': 'Do Nothing', 'description': '유의미한 기회가 없으면 제안하지 않음', 'event_type': 'quiet', 'customer_id': 'C0006', 'amount': 12000, 'expected': '제안 생략', 'color': 'gray'},
    {'id': 'fault', 'title': 'Agent 장애', 'description': '분석 실패와 재시도 흐름을 확인', 'event_type': 'salary', 'customer_id': 'C0001', 'amount': 4200000, 'inject_failure': 'insight', 'expected': '실패 → 재시도', 'color': 'red'},
    {'id': 'loan', 'title': '대출 조건 점검', 'description': '대출 정보를 확인하고 상담 연결', 'event_type': 'loan', 'customer_id': 'C0007', 'amount': 0, 'expected': '고객 선택 대기', 'color': 'green'},
]
