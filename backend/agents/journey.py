def run(ctx):
    choice = ctx.get('decision')
    if not choice:
        return {'summary': '개인화 안내 준비 · 고객 선택과 동의 대기', 'awaiting': 'customer', 'service': ctx['results']['content']['domain'], 'external_action': False}
    accepted = choice == 'accept'
    return {'summary': '고객 동의 후 서비스 연결 시연 완료' if accepted else '고객의 보류·관심 없음 선택을 존중하여 종료', 'choice': choice, 'connected': accepted, 'external_action': False, 'service': ctx['results']['content']['domain']}
