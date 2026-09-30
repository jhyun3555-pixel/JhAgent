from backend.skills.opportunities import discover


def run(ctx):
    options = discover(ctx['customers'][0], ctx['request']['event_type'])
    return {'summary': options[0]['reason'] if options else '고객에게 유의미한 금융기회가 없어 제안을 생략합니다.', 'opportunities': options, 'domain': options[0]['domain'] if options else None, 'decision': 'propose' if options else 'do_nothing', 'tools_evaluated': ['mydata', 'deposit', 'portfolio', 'loan', 'card', 'tax']}
