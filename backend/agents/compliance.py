from backend.policy import exclusion, forbidden_text, CHANNEL_COST


def run(ctx):
    req, result = ctx['request'], ctx['results']
    content = result['content']
    ids = result['audience']['customer_ids'] if req['mode'] == 'campaign' else [ctx['customers'][0]['id']]
    customers = [c for c in ctx['customers'] if c['id'] in ids]
    reasons = []
    for c in customers:
        reason = exclusion(c, content['domain'])
        if reason:
            reasons.append(f'{c["id"]}: {reason}')
    violations = forbidden_text(' '.join(content[k] for k in ('title', 'message_a', 'message_b')))
    if violations:
        reasons.append('금지 표현: ' + ', '.join(violations))
    cost = len(customers) * CHANNEL_COST[req['channel']]
    if req['mode'] == 'campaign' and cost > req['budget']:
        reasons.append('예상 비용이 승인 예산을 초과합니다.')
    if not customers:
        reasons.append('조건에 맞는 대상 고객이 없습니다.')
    return {'summary': '정책 검증 통과 · 발송 가능' if not reasons else '발송 차단 · ' + ' / '.join(reasons), 'allowed': not reasons, 'reasons': reasons, 'checks': [{'name': '수신 동의', 'passed': bool(customers) and all(c['consent'] for c in customers)}, {'name': '7일 발송 빈도', 'passed': bool(customers) and all(c['recent_sends'] < 3 for c in customers)}, {'name': '상품 적합성', 'passed': bool(customers) and not any(exclusion(c, content['domain']) not in (None, '수신 동의 없음', '7일 발송 빈도 초과') for c in customers)}, {'name': '금지 표현', 'passed': not violations}, {'name': '예산', 'passed': req['mode'] != 'campaign' or cost <= req['budget']}], 'estimated_cost': cost, 'policy_version': 'demo-policy-1.0', 'policy_note': '시연용 내부 정책이며 법적 적합성 인증이 아닙니다.'}
