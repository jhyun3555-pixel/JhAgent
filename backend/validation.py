import math
from backend.catalog import DOMAINS, EVENTS


def number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not minimum <= value <= maximum:
        raise ValueError(f'{name}: {minimum:,}~{maximum:,} 사이 정수를 입력하세요.')
    return int(value)


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError('JSON 객체를 입력하세요.')
    mode = data.get('mode', 'event')
    if mode not in ('event', 'campaign'):
        raise ValueError('지원하지 않는 작업 유형입니다.')
    channel = data.get('channel', 'push')
    if channel not in ('push', 'inapp', 'sms'):
        raise ValueError('지원하지 않는 채널입니다.')
    result = {'mode': mode, 'channel': channel}
    if mode == 'event':
        if data.get('event_type') not in EVENTS:
            raise ValueError('지원하지 않는 이벤트입니다.')
        cid = data.get('customer_id')
        if not isinstance(cid, str) or len(cid) > 20:
            raise ValueError('고객을 선택하세요.')
        result.update(customer_id=cid, event_type=data['event_type'], amount=number(data.get('amount', 0), '이벤트 금액', 0, 100000000000))
        if data.get('inject_failure'):
            if data['inject_failure'] != 'insight':
                raise ValueError('지원하지 않는 장애 시나리오입니다.')
            result['inject_failure'] = 'insight'
    else:
        brief = data.get('brief', '')
        if not isinstance(brief, str) or not 5 <= len(brief.strip()) <= 2000:
            raise ValueError('캠페인 목표를 5~2,000자로 입력하세요.')
        if data.get('domain') not in DOMAINS:
            raise ValueError('도메인을 선택하세요.')
        result.update(brief=brief.strip(), domain=data['domain'], min_balance=number(data.get('min_balance', 10000000), '최소 잔액', 0, 100000000000), budget=number(data.get('budget', 100000), '예산', 0, 100000000), max_audience=number(data.get('max_audience', 100), '최대 대상', 1, 240))
    return result
