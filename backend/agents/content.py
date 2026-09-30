import json
from backend.catalog import DOMAINS
from backend.provider import generate


def run(ctx):
    req, results = ctx['request'], ctx['results']
    domain = req.get('domain') if req['mode'] == 'campaign' else results['opportunity']['domain']
    label = DOMAINS[domain]
    name = ctx['customers'][0]['name'] if req['mode'] == 'event' else '고객'
    draft = generate(['title', 'message_a', 'message_b'], json.dumps({'topic': label, 'brief': req.get('brief', ''), 'mode': req['mode']}, ensure_ascii=False), {'title': f'{label}, 나에게 맞는 선택은?', 'message_a': f'{name}님, 지금 {label} 선택지를 확인해 보세요. 조건을 비교하고 원할 때 진행할 수 있어요.', 'message_b': f'잠깐의 확인으로 다음 금융 계획을 준비하세요. {label}에 필요한 정보와 유의사항을 안내해 드려요.'}, ctx.get('llm_enabled', True))
    draft.update(summary=f'{label} · {req["channel"].upper()} A/B 메시지 작성', domain=domain, channel=req['channel'], schedule='승인 후 즉시 · 시연 환경', choices=['자세히 보기', '다음에 보기', '관심 없음'], disclaimer='정보 제공용 시연입니다. 상품 가입·외부 정보 연결은 고객 선택과 별도 동의 후 진행됩니다.')
    return draft
