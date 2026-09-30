from collections import Counter
from backend.policy import exclusion


def run(ctx):
    req = ctx['request']
    candidates = [c for c in ctx['customers'] if c['balance'] >= req['min_balance']]
    excluded, eligible = Counter(), []
    for c in candidates:
        reason = exclusion(c, req['domain'])
        if reason:
            excluded[reason] += 1
        else:
            eligible.append(c['id'])
    limit = req.get('max_audience', 100)
    excluded['대상 인원 상한'] += max(0, len(eligible) - limit)
    ids = eligible[:limit]
    previous = set(ctx.get('previous_audience', []))
    return {'summary': f'후보 {len(candidates)}명 → 최종 {len(ids)}명 · {len(candidates)-len(ids)}명 제외', 'candidate_count': len(candidates), 'customer_ids': ids, 'count': len(ids), 'excluded': {k: v for k, v in excluded.items() if v}, 'overlap_count': len(set(ids) & previous), 'condition': f'잔액 ≥ {req["min_balance"]:,}원 / 수신 동의 / 최근 7일 3회 미만 / 적합성 / 최대 {limit}명', 'query': 'SELECT id FROM customers WHERE balance >= ? ORDER BY id; -- 동의·빈도·적합성 정책 필터 적용', 'parameters': [req['min_balance']], 'extraction': '서버 조회 데이터에 결정론적 규칙 적용 (LLM SQL 실행 없음)'}
