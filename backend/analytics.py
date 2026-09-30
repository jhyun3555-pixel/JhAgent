import csv
import hashlib
import html
import io
import json
import math
import os
import time
import uuid
from collections import Counter
from datetime import datetime
from backend.catalog import AGENTS, DOMAINS
from backend.database import encode


def metrics(db, since=0, until=None):
    until = time.time() if until is None else until
    jobs = db.rows('SELECT * FROM jobs WHERE created_at>=? AND created_at<=? ORDER BY created_at DESC', (since, until))
    deliveries = db.rows('SELECT d.* FROM deliveries d JOIN jobs j ON j.id=d.job_id WHERE j.created_at>=? AND j.created_at<=? AND d.created_at<=?', (since, until, until))
    counts = Counter(j['status'] for j in jobs)
    finished = [j['duration_ms'] for j in jobs if j['status'] in ('completed', 'blocked', 'no_action', 'failed')]
    sorted_durations = sorted(finished)
    sent = len(deliveries)
    clicked = sum(r['clicked'] for r in deliveries)
    converted = sum(r['converted'] for r in deliveries)
    return {'total': len(jobs), 'counts': dict(counts), 'active': counts['running'] + counts['queued'], 'waiting': counts['waiting_approval'] + counts['waiting_customer'], 'completed': counts['completed'], 'blocked': counts['blocked'], 'no_action': counts['no_action'], 'failed': counts['failed'], 'avg_ms': round(sum(finished) / max(1, len(finished))), 'p95_ms': round(sorted_durations[max(0, math.ceil(len(sorted_durations) * .95) - 1)]) if sorted_durations else 0, 'sent': sent, 'opened': sum(r['opened'] for r in deliveries), 'clicked': clicked, 'converted': converted, 'ctr': round(clicked / max(1, sent) * 100, 1), 'conversion_rate': round(converted / max(1, sent) * 100, 1), 'cost': sum(r['cost'] for r in deliveries), 'jobs': jobs, 'deliveries': deliveries}


def snapshot(db, engine, minutes=15):
    now = time.time()
    since = now - minutes * 60
    all_data = metrics(db, since, now)
    rows = all_data.pop('jobs')
    all_data.pop('deliveries')
    jobs = []
    for row in rows:
        req = json.loads(row.pop('request'))
        row.pop('results')
        row.pop('idempotency_key')
        row['channel'] = req['channel']
        row['customer_id'] = req.get('customer_id')
        row['domain'] = req.get('domain')
        jobs.append(row)
    activity = db.rows('SELECT * FROM audit ORDER BY id DESC LIMIT 30')
    agent_stats = db.rows('SELECT agent_id,COUNT(*) calls,AVG(duration_ms) avg_ms,SUM(CASE WHEN status="failed" THEN 1 ELSE 0 END) failures FROM steps WHERE started_at>=? GROUP BY agent_id', (since,))
    stat_map = {a['agent_id']: a for a in agent_stats}
    running = Counter(r['active_agent'] for r in db.rows("SELECT active_agent FROM jobs WHERE status='running'"))
    agents = [{'id': aid, 'name': name, 'description': desc, 'group': group, 'active': running[aid], 'calls': stat_map.get(aid, {}).get('calls', 0), 'avg_ms': round(stat_map.get(aid, {}).get('avg_ms') or 0), 'failures': stat_map.get(aid, {}).get('failures', 0), 'version': '1.0.0'} for aid, name, desc, group in AGENTS]
    series = [0] * 30
    for j in jobs:
        index = min(29, max(0, int((j['created_at'] - since) / (minutes * 60) * 30)))
        series[index] += 1
    return {'now': now, 'revision': engine.revision, 'minutes': minutes, 'metrics': all_data, 'jobs': jobs[:500], 'agents': agents, 'activity': activity, 'series': series, 'demo_active': engine.demo_until > now, 'demo_until': engine.demo_until, 'provider': os.getenv('AGENT_PROVIDER', 'demo'), 'customer_count': db.one('SELECT COUNT(*) n FROM customers')['n'], 'waiting_total': db.one("SELECT COUNT(*) n FROM jobs WHERE status IN ('waiting_approval','waiting_customer')")['n'], 'data_kind': 'synthetic'}


def create_report(db, days):
    if type(days) is not int or days not in (1, 7, 30):
        raise ValueError('리포트 기간은 1일, 7일, 30일 중 선택하세요.')
    now = time.time()
    data = metrics(db, now - days * 86400, now)
    rows = data.pop('jobs')
    deliveries = data.pop('deliveries')
    by_channel = []
    for channel in ('push', 'inapp', 'sms'):
        items = [d for d in deliveries if d['channel'] == channel]
        by_channel.append({'channel': channel, 'sent': len(items), 'clicked': sum(d['clicked'] for d in items), 'converted': sum(d['converted'] for d in items), 'cost': sum(d['cost'] for d in items)})
    variants = []
    for variant in ('A', 'B'):
        items = [d for d in deliveries if d['variant'] == variant]
        variants.append({'variant': variant, 'sent': len(items), 'clicked': sum(d['clicked'] for d in items), 'ctr': round(sum(d['clicked'] for d in items) / max(1, len(items)) * 100, 1)})
    campaigns = []
    for j in rows:
        if j['mode'] == 'campaign':
            sent = [d for d in deliveries if d['job_id'] == j['id']]
            campaigns.append({'id': j['id'], 'title': j['title'], 'status': j['status'], 'sent': len(sent), 'clicked': sum(d['clicked'] for d in sent), 'converted': sum(d['converted'] for d in sent), 'cost': sum(d['cost'] for d in sent)})
    payload = {'metrics': data, 'channels': by_channel, 'variants': variants, 'campaigns': campaigns, 'period': {'days': days, 'from': now - days * 86400, 'to': now}, 'data_kind': 'synthetic', 'note': '가상 고객과 시뮬레이션 반응 데이터입니다. 실측 매출·ROI·고객 편익은 산정하지 않습니다. 클릭률=클릭/발송, 연결률=서비스 연결/발송. 지연시간은 승인 대기를 제외한 agent 실행시간 합계이며 초기 이력은 합성 시간입니다.', 'recommendations': ['A/B 문안의 클릭률 차이를 다음 실험의 가설로 활용하세요. 표본이 적으므로 우열을 확정하지 않습니다.', '정책 차단과 Do Nothing을 별도 관리해 불필요한 접촉을 줄이세요.', '실제 채널 연동 시 수신거부·민원·고객 편익 데이터를 추가 수집하세요.']}
    payload['sha256'] = hashlib.sha256(encode(payload).encode()).hexdigest()
    rid = 'R-' + uuid.uuid4().hex[:8].upper()
    title = datetime.fromtimestamp(now).strftime('%Y.%m.%d') + f' 마케팅 운영 리포트 · 최근 {days}일'
    db.execute('INSERT INTO reports VALUES(?,?,?,?)', (rid, title, now, encode(payload)))
    db.audit(None, 'report', title + ' 생성')
    return get_report(db, rid)


def get_report(db, rid):
    report = db.one('SELECT * FROM reports WHERE id=?', (rid,))
    if not report:
        raise KeyError('리포트를 찾을 수 없습니다.')
    report['data'] = json.loads(report['data'])
    return report


def csv_report(report):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['구분', '항목', '값'])
    writer.writerow(['안내', '데이터', '가상 고객 및 시뮬레이션 성과'])
    metric_labels = {'total':'총 작업(건)','active':'실행 중(건)','waiting':'선택·승인 대기(건)','completed':'완료(건)','blocked':'정책 차단(건)','no_action':'제안 생략(건)','failed':'실패(건)','avg_ms':'평균 처리시간(ms)','p95_ms':'P95 처리시간(ms)','sent':'시연 발송(건)','opened':'열람(건)','clicked':'클릭(건)','converted':'서비스 연결(건)','ctr':'클릭률(%)','conversion_rate':'서비스 연결률(%)','cost':'시연 비용(원)'}
    for k, v in report['data']['metrics'].items():
        if not isinstance(v, dict):
            writer.writerow(['운영 지표', metric_labels.get(k, k), v])
    writer.writerow([])
    writer.writerow(['A/B 문안', '발송', '클릭', '클릭률(%)'])
    for v in report['data']['variants']:
        writer.writerow([v['variant'], v['sent'], v['clicked'], v['ctr']])
    writer.writerow([])
    writer.writerow(['채널', '발송', '클릭', '연결', '비용(원)'])
    for c in report['data']['channels']:
        writer.writerow([c['channel'].upper(), c['sent'], c['clicked'], c['converted'], c['cost']])
    writer.writerow([])
    writer.writerow(['캠페인', '발송', '클릭', '연결', '비용(원)'])
    for c in report['data']['campaigns']:
        title = c['title']
        if title.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            title = "'" + title
        writer.writerow([title, c['sent'], c['clicked'], c['converted'], c['cost']])
    return '\ufeff' + buf.getvalue()


def html_report(report):
    esc = html.escape
    data, m = report['data'], report['data']['metrics']
    cards = ''.join(f'<div class="card"><small>{label}</small><strong>{value:,}{unit}</strong></div>' for label, value, unit in [('총 작업', m['total'], '건'), ('시연 발송', m['sent'], '건'), ('클릭률', m['ctr'], '%'), ('서비스 연결률', m['conversion_rate'], '%')])
    rows = ''.join(f'<tr><td>{esc(c["title"])}</td><td>{c["sent"]}</td><td>{c["clicked"]}</td><td>{c["converted"]}</td><td>{c["cost"]:,}원</td></tr>' for c in data['campaigns'])
    recommendations = ''.join('<li>' + esc(x) + '</li>' for x in data['recommendations'])
    channels = ''.join(f'<tr><td>{c["channel"].upper()}</td><td>{c["sent"]}</td><td>{c["clicked"]}</td><td>{c["converted"]}</td><td>{c["cost"]:,}원</td></tr>' for c in data['channels'])
    variants = ''.join(f'<tr><td>Variant {v["variant"]}</td><td>{v["sent"]}</td><td>{v["clicked"]}</td><td>{v["ctr"]}%</td></tr>' for v in data['variants'])
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>{esc(report['title'])}</title><style>
    *{{box-sizing:border-box}}body{{font:15px/1.7 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;color:#152238;background:#eef2f5;margin:0;padding:40px}}main{{max-width:1000px;margin:auto;background:white;padding:52px;border-radius:12px}}.brand{{letter-spacing:3px;font-weight:800;color:#20847f}}h1{{font-size:30px;line-height:1.4}}h2{{font-size:20px;margin-top:32px}}.muted{{color:#667788;font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0}}.card{{background:#f1f6f6;padding:20px;border-radius:8px}}strong{{display:block;font-size:25px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce3e9}}th{{background:#f0f4f6}}button{{background:#18313d;color:white;border:0;border-radius:8px;padding:12px 20px;cursor:pointer}}.note{{background:#f3f7f8;padding:16px}}@media print{{body{{padding:0;background:white}}main{{padding:0}}button{{display:none}}h2,tr,.grid{{break-inside:avoid}}}}@page{{size:A4;margin:18mm}}</style>
    <main><div class="brand">NEUTECH / AGENT OPERATIONS</div><h1>{esc(report['title'])}</h1><p class="muted">{esc(report['id'])} · 생성 시점 기준 고정 스냅샷 · 가상 데이터</p><button onclick="window.print()">인쇄 / PDF 저장</button>{'<div class="grid">'+cards+'</div>'}<h2>운영 현황</h2><p>완료 {m['completed']}건 · 정책 차단 {m['blocked']}건 · 제안 생략 {m['no_action']}건 · 실패 {m['failed']}건</p><p>평균 처리 {m['avg_ms']/1000:.2f}초 · P95 {m['p95_ms']/1000:.2f}초 · 시연 비용 {m['cost']:,}원</p><h2>채널별 성과</h2><table><tr><th>채널</th><th>발송</th><th>클릭</th><th>연결</th><th>비용</th></tr>{channels}</table><h2>캠페인 성과</h2><table><tr><th>캠페인</th><th>발송</th><th>클릭</th><th>연결</th><th>비용</th></tr>{rows or '<tr><td colspan="5">기간 내 캠페인이 없습니다.</td></tr>'}</table><h2>A/B 문안 비교</h2><table><tr><th>문안</th><th>발송</th><th>클릭</th><th>클릭률</th></tr>{variants}</table><p class="muted">가상 표본이며 통계적 유의성을 검증하지 않았습니다.</p><h2>다음 운영을 위한 제안</h2><ul>{recommendations}</ul><p class="note muted">{esc(data['note'])}</p><p class="muted">데이터 무결성 SHA-256 · {data['sha256']}</p></main></html>'''
