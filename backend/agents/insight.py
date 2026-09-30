def run(ctx):
    customers = ctx['customers']
    audience = ctx.get('results', {}).get('audience')
    if audience is not None:
        customers = [c for c in customers if c['id'] in audience['customer_ids']]
    n = len(customers)
    balance = round(sum(c['balance'] for c in customers) / max(1, n))
    return {'summary': f'{n}명 분석 · 평균 잔액 {balance:,}원', 'customer_count': n, 'average_balance': balance, 'consent_count': sum(bool(c['consent']) for c in customers), 'mydata_count': sum(bool(c['mydata']) for c in customers), 'segments': sorted(set(c['segment'] for c in customers)), 'data_source': '가상 고객 · 자행 거래 데이터'}
