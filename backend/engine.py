import hashlib
import importlib
import json
import os
import random
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from backend.catalog import EVENT_FLOW, CAMPAIGN_FLOW, EVENTS
from backend.database import encode
from backend.policy import exclusion, forbidden_text, CHANNEL_COST
from backend.validation import validate_request

TERMINAL = {'completed', 'blocked', 'no_action', 'failed', 'cancelled'}


class Engine:
    def __init__(self, db, delay=None):
        self.db = db
        self.delay = float(os.getenv('AGENT_STEP_DELAY', '.7')) if delay is None else delay
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='workflow')
        self.lock = threading.RLock()
        self.changed = threading.Condition()
        self.revision = 0
        self.demo_until = 0
        self.closed = False
        self.root = Path(__file__).resolve().parent.parent
        for row in db.rows("SELECT id FROM jobs WHERE status IN ('running','queued')"):
            db.execute("UPDATE jobs SET status='failed',error='서버가 재시작되었습니다. 재시도를 선택하세요.',updated_at=? WHERE id=?", (time.time(), row['id']))
            db.execute("UPDATE steps SET status='failed',error='서버 재시작',ended_at=? WHERE job_id=? AND status='running'", (time.time(), row['id']))
            db.audit(row['id'], 'recovery', '서버 재시작으로 진행 중 작업을 안전하게 중단했습니다.')

    def notify(self):
        with self.changed:
            self.revision += 1
            self.changed.notify_all()

    def submit(self, data, key=None, parent_id=None, background=True, seeded=False):
        request = validate_request(data)
        if request['mode'] == 'event' and not self.db.customers(request['customer_id']):
            raise ValueError('존재하지 않는 고객입니다.')
        if key and (not isinstance(key, str) or len(key) > 128):
            raise ValueError('잘못된 멱등성 키입니다.')
        with self.lock:
            if key:
                existing = self.db.one('SELECT id,request FROM jobs WHERE idempotency_key=?', (key,))
                if existing:
                    if existing['request'] != encode(request):
                        raise ValueError('같은 요청 키에 다른 내용을 사용할 수 없습니다.')
                    return existing['id']
            if background and self.db.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('queued','running')")['n'] >= 64:
                raise ValueError('처리 대기열이 가득 찼습니다. 잠시 후 다시 시도하세요.')
            job_id = 'NT-' + uuid.uuid4().hex[:8].upper()
            now = time.time()
            title = request['brief'][:60] if request['mode'] == 'campaign' else EVENTS[request['event_type']] + ' · ' + request['customer_id']
            self.db.execute('INSERT INTO jobs(id,title,mode,status,request,created_at,updated_at,parent_id,idempotency_key,seeded) VALUES(?,?,?,?,?,?,?,?,?,?)', (job_id, title, request['mode'], 'queued', encode(request), now, now, parent_id, key, int(seeded)))
            self.db.audit(job_id, 'created', '가상 데이터 작업 접수 · ' + title)
        self.notify()
        if background:
            self.pool.submit(self.run, job_id)
        return job_id

    def context(self, job):
        req = job['request']
        customers = self.db.customers(req.get('customer_id'))
        # The entered event amount affects analysis in this event snapshot only.
        # The customer master is a fixture, so replaying an event never double-books a balance.
        if req['mode'] == 'event' and req['event_type'] in ('salary', 'balance'):
            customers[0]['balance'] += req['amount']
        return {'contract_version': 1, 'request': req, 'results': job['results'], 'customers': customers, 'decision': job['decision'], 'deliveries': job['deliveries'], 'previous_audience': [r['customer_id'] for r in self.db.rows('SELECT DISTINCT customer_id FROM deliveries WHERE created_at > ?', (time.time() - 7 * 86400,))], 'llm_enabled': not job['seeded']}

    def invoke(self, agent, ctx, fast=False):
        if ctx['request'].get('inject_failure') == agent:
            raise RuntimeError('시연용 분석 오류가 발생했습니다. 재시도하면 장애 주입을 해제합니다.')
        if fast:
            return importlib.import_module('backend.agents.' + agent).run(ctx)
        response = subprocess.run([sys.executable, '-m', 'backend.worker', agent], input=encode(ctx), capture_output=True, text=True, cwd=self.root, timeout=float(os.getenv('AGENT_TIMEOUT', '60')))
        try:
            envelope = json.loads(response.stdout)
        except json.JSONDecodeError:
            raise RuntimeError('Agent 프로세스가 유효한 JSON을 반환하지 않았습니다.') from None
        if response.returncode or not envelope.get('ok'):
            raise RuntimeError(envelope.get('error', 'Agent 실행 실패'))
        return envelope['output']

    def set_status(self, job_id, status, error=None):
        self.db.execute('UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?', (status, error, time.time(), job_id))
        self.notify()

    def run(self, job_id, fast=False):
        step_id = None
        try:
            with self.lock:
                job = self.db.job(job_id)
                if job['status'] != 'queued':
                    return
                self.set_status(job_id, 'running')
            flow = CAMPAIGN_FLOW if job['mode'] == 'campaign' else EVENT_FLOW
            for agent in flow:
                with self.lock:
                    job = self.db.job(job_id)
                    if job['status'] != 'running':
                        return
                    result = job['results'].get(agent)
                    if result and not result.get('awaiting'):
                        continue
                    ctx = self.context(job)
                    start = time.time()
                    # Persist a bounded, safe input summary rather than provider credentials.
                    shown_input = {'contract_version': 1, 'request': ctx['request'], 'customer_count': len(ctx['customers']), 'available_results': list(ctx['results']), 'decision': ctx['decision']}
                    step_id = self.db.execute('INSERT INTO steps(job_id,agent_id,status,started_at,input) VALUES(?,?,?,?,?)', (job_id, agent, 'running', start, encode(shown_input)))
                    self.db.execute('UPDATE jobs SET active_agent=?,updated_at=? WHERE id=?', (agent, start, job_id))
                self.notify()
                if not fast:
                    time.sleep(self.delay)
                output = self.invoke(agent, ctx, fast)
                with self.lock:
                    if self.db.job(job_id)['status'] != 'running':
                        self.db.execute("UPDATE steps SET status='cancelled',ended_at=? WHERE id=?", (time.time(), step_id))
                        return
                    if agent == 'journey' and not job['decision']:
                        self.dispatch(job, preview=True)
                    if agent == 'journey' and job['decision']:
                        self.record_choice(job)
                    if agent == 'campaign' and job['decision'] == 'approve':
                        self.dispatch(job)
                    end = time.time()
                    duration = (end - start) * 1000
                    status = 'waiting' if output.get('awaiting') else 'completed'
                    self.db.execute('UPDATE steps SET status=?,ended_at=?,duration_ms=?,output=? WHERE id=?', (status, end, duration, encode(output), step_id))
                    job['results'][agent] = output
                    self.db.execute('UPDATE jobs SET results=?,duration_ms=duration_ms+?,updated_at=? WHERE id=?', (encode(job['results']), duration, end, job_id))
                    self.db.audit(job_id, 'step', agent + ' · ' + output['summary'])
                    step_id = None
                    if output.get('decision') == 'do_nothing':
                        self.set_status(job_id, 'no_action')
                        return
                    if agent == 'compliance' and not output['allowed']:
                        self.set_status(job_id, 'blocked')
                        self.db.audit(job_id, 'policy', output['summary'])
                        return
                    if output.get('awaiting'):
                        self.set_status(job_id, 'waiting_approval' if output['awaiting'] == 'staff' else 'waiting_customer')
                        return
                self.notify()
            with self.lock:
                if self.db.job(job_id)['status'] == 'running':
                    self.set_status(job_id, 'completed')
                    self.db.audit(job_id, 'completed', '모든 처리 단계 완료 · 외부 서비스 호출 없음')
        except Exception as error:
            message = 'Agent 실행 시간 초과' if isinstance(error, subprocess.TimeoutExpired) else str(error)
            with self.lock:
                current = self.db.job(job_id)
                if current['status'] == 'cancelled':
                    return
                if step_id:
                    self.db.execute("UPDATE steps SET status='failed',ended_at=?,error=? WHERE id=?", (time.time(), message, step_id))
                self.set_status(job_id, 'failed', message)
                self.db.audit(job_id, 'error', message)

    def dispatch(self, job, preview=False):
        """Atomic final policy check + idempotent simulated outbox."""
        content = job['results']['content']
        if forbidden_text(' '.join(content[k] for k in ('title', 'message_a', 'message_b'))):
            raise RuntimeError('발송 직전 정책 검증 실패: 금지 표현')
        ids = [job['request']['customer_id']] if preview else job['results']['audience']['customer_ids']
        with self.db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            customers = {c['id']: c for c in self.db.customers(con=con)}
            existing = {r['customer_id'] for r in con.execute('SELECT customer_id FROM deliveries WHERE job_id=?', (job['id'],))}
            targets = [cid for cid in ids if cid not in existing]
            for cid in targets:
                reason = exclusion(customers[cid], content['domain'])
                if reason:
                    raise RuntimeError('발송 직전 정책 변경: ' + cid + ' · ' + reason + ' (새 작업으로 대상 재검토)')
            cost = CHANNEL_COST[job['request']['channel']]
            if not preview and len(ids) * cost > job['request']['budget']:
                raise RuntimeError('발송 직전 예산 초과')
            for i, cid in enumerate(targets):
                n = int(hashlib.sha256((job['id'] + cid).encode()).hexdigest()[:8], 16) % 100
                opened = int(n < 68) if not preview else 0
                clicked = int(n < 31) if not preview else 0
                converted = int(n < 12) if not preview else 0
                con.execute('INSERT OR IGNORE INTO deliveries(job_id,customer_id,channel,variant,opened,clicked,converted,cost,created_at) VALUES(?,?,?,?,?,?,?,?,?)', (job['id'], cid, job['request']['channel'], 'A' if i % 2 == 0 else 'B', opened, clicked, converted, cost, time.time()))
        self.db.audit(job['id'], 'dispatch', f'시연 안내 {len(targets)}건 기록 · 실제 발송 없음')

    def record_choice(self, job):
        if job['decision'] == 'accept':
            customer = self.db.customers(job['request']['customer_id'])[0]
            if not customer['consent']:
                raise RuntimeError('고객 동의가 변경되어 서비스 연결을 중단합니다.')
        accepted = int(job['decision'] == 'accept')
        self.db.execute('UPDATE deliveries SET opened=1,clicked=?,converted=? WHERE job_id=?', (accepted, accepted, job['id']))
        self.db.audit(job['id'], 'customer_choice', f'가상 고객 선택: {job["decision"]} · 외부 연결 시연')

    def decide(self, job_id, action, consent=False, background=True, actor='시연 운영자'):
        with self.lock:
            job = self.db.job(job_id)
            if action == 'approve' and job['status'] == 'waiting_approval':
                pass
            elif action in ('accept', 'defer', 'decline') and job['status'] == 'waiting_customer':
                if action == 'accept' and consent is not True:
                    raise ValueError('서비스 연결에 대한 고객 동의가 필요합니다.')
            elif action == 'reject' and job['status'] == 'waiting_approval':
                self.set_status(job_id, 'cancelled')
                self.db.audit(job_id, 'rejected', actor + ': 캠페인 반려')
                return
            else:
                raise ValueError('현재 상태에서는 이 결정을 적용할 수 없습니다.')
            self.db.execute("UPDATE jobs SET decision=?,status='queued',updated_at=? WHERE id=?", (action, time.time(), job_id))
            self.db.audit(job_id, 'decision', actor + ': ' + action + (' · 명시적 고객 동의 확인' if consent else ''))
        self.notify()
        if background:
            self.pool.submit(self.run, job_id)

    def cancel(self, job_id):
        with self.lock:
            job = self.db.job(job_id)
            if job['status'] in TERMINAL:
                raise ValueError('이미 종료된 작업입니다.')
            self.set_status(job_id, 'cancelled')
            self.db.audit(job_id, 'cancelled', '운영자가 작업을 중단했습니다. 이미 기록된 안내는 유지합니다.')

    def retry(self, job_id):
        job = self.db.job(job_id)
        if job['status'] != 'failed':
            raise ValueError('실패한 작업만 재시도할 수 있습니다.')
        # Resume from persisted successful checkpoints, using the same outbox key.
        with self.lock:
            job = self.db.job(job_id)
            if job['status'] != 'failed':
                raise ValueError('이미 재시도 중입니다.')
            request = dict(job['request'])
            request.pop('inject_failure', None)
            self.db.execute("UPDATE jobs SET request=?,status='queued',error=NULL,updated_at=? WHERE id=?", (encode(request), time.time(), job_id))
            self.db.audit(job_id, 'retry', '실패 단계부터 재시도 · 성공 단계와 중복 발송 방지 키 유지')
        self.notify()
        self.pool.submit(self.run, job_id)
        return job_id

    def set_demo(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('enabled 값은 boolean이어야 합니다.')
        if enabled and os.getenv('AGENT_PROVIDER', 'demo') != 'demo':
            raise ValueError('자동 트래픽은 비용 없는 시연 모드에서만 실행할 수 있습니다.')
        if enabled and self.demo_until > time.time():
            return
        self.demo_until = time.time() + 120 if enabled else 0
        self.db.audit(None, 'traffic', '가상 이벤트 스트림 ' + ('시작 (2분 후 자동 종료)' if enabled else '중지'))
        if enabled:
            threading.Thread(target=self._demo, daemon=True).start()
        self.notify()

    def _demo(self):
        while not self.closed and time.time() < self.demo_until:
            try:
                self.submit({'mode': 'event', 'event_type': random.choice(['salary', 'maturity', 'card', 'tax', 'quiet', 'balance']), 'customer_id': f'C{random.randint(30, 230):04}', 'amount': 3000000, 'channel': 'push'})
            except ValueError:
                pass
            time.sleep(2.7)
        self.notify()

    def seed_history(self):
        if self.db.one("SELECT value FROM settings WHERE key='history_seeded'"):
            return
        rng = random.Random(33)
        now = time.time()
        for i in range(64):
            if i % 16 == 0:
                req = {'mode': 'campaign', 'brief': ['월급 이후 여유자금 관리 캠페인', '가을 맞이 예적금 만기 고객 안내', '생활 소비에 맞는 카드 혜택 비교', '마이데이터 연결 가치 안내'][i // 16], 'domain': ['portfolio', 'deposit', 'card', 'mydata'][i // 16], 'channel': 'push', 'min_balance': 30000000, 'budget': 10000, 'max_audience': 24}
            else:
                req = {'mode': 'event', 'event_type': ['salary', 'maturity', 'card', 'tax', 'quiet', 'loan'][i % 6], 'customer_id': f'C{30+i:04}', 'amount': 3500000, 'channel': 'push'}
                if i in (11, 43):
                    req['inject_failure'] = 'insight'
            jid = self.submit(req, background=False, seeded=True)
            self.run(jid, fast=True)
            job = self.db.job(jid)
            if job['status'] == 'waiting_approval' and i != 48:
                self.decide(jid, 'approve', background=False, actor='가상 이력 생성기')
                self.run(jid, fast=True)
            elif job['status'] == 'waiting_customer':
                self.decide(jid, 'accept' if i % 4 else 'defer', consent=True, background=False, actor='가상 고객 이력')
                self.run(jid, fast=True)
            # Historical fixture timing is intentionally synthetic and identified in the UI.
            job = self.db.job(jid)
            start = now - (64 - i) * 12.8
            cursor = start
            total = 0
            with self.db.connect() as con:
                for step in job['steps']:
                    duration = rng.uniform(.12, 1.6) * (2 if i % 11 == 0 else 1)
                    con.execute('UPDATE steps SET started_at=?,ended_at=?,duration_ms=? WHERE id=?', (cursor, cursor + duration, duration * 1000, step['id']))
                    cursor += duration
                    total += duration * 1000
                con.execute('UPDATE jobs SET created_at=?,updated_at=?,duration_ms=? WHERE id=?', (start, cursor, total, jid))
                con.execute('UPDATE deliveries SET created_at=? WHERE job_id=?', (cursor, jid))
                con.execute('UPDATE audit SET created_at=? WHERE job_id=?', (cursor, jid))
        self.db.execute("INSERT INTO settings(key,value) VALUES('history_seeded','1')")

    def close(self):
        self.closed = True
        self.demo_until = 0
        self.pool.shutdown(wait=True, cancel_futures=True)
