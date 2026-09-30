import json
from backend.catalog import DOMAINS
from backend.provider import generate


def run(ctx):
    req = ctx['request']
    domain = DOMAINS[req['domain']]
    draft = generate(['concept', 'rationale'], json.dumps({'brief': req['brief'], 'domain': domain}, ensure_ascii=False), {'concept': f'고객의 다음 금융 순간, {domain}', 'rationale': f'“{req["brief"]}” 목표에 맞춰 보유 정보와 수신 동의를 확인하고 고객이 직접 선택하는 안내를 구성합니다.'}, ctx.get('llm_enabled', True))
    draft.update(summary=draft['concept'], ideas=[{'name': f'지금 시작하는 {domain}', 'approach': '고객의 현재 금융 상황에 집중', 'variant': 'A'}, {'name': '나에게 맞는 다음 선택', 'approach': '선택지 비교와 부담 없는 검토', 'variant': 'B'}, {'name': '필요한 순간에만 안내', 'approach': '동의·빈도를 고려한 접점 최소화', 'variant': 'C'}], domain=req['domain'], approval_items=['목적', '대상 조건', '발송 인원', '메시지', '채널', '예산', '실행 시점'])
    return draft
