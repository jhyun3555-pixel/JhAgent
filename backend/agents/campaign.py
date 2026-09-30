def run(ctx):
    if ctx.get('decision') != 'approve':
        return {'summary': '캠페인 준비 완료 · 담당자 최종 승인 대기', 'awaiting': 'staff', 'external_action': False}
    return {'summary': '승인된 캠페인 발송 시연 완료', 'approved': True, 'customer_count': ctx['results']['audience']['count'], 'channel': ctx['request']['channel'], 'external_action': False}
