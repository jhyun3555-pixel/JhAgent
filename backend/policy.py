"""Deterministic gates shared by policy and the final dispatch adapter."""
import re

FORBIDDEN = ('원금 보장', '수익 보장', '무조건 수익', '확정 수익', '손실 없음', '100% 수익', '확정 환급', 'guaranteed return')
CHANNEL_COST = {'push': 20, 'inapp': 0, 'sms': 50}


def exclusion(customer, domain):
    if not customer['consent']:
        return '수신 동의 없음'
    if customer['recent_sends'] >= 3:
        return '7일 발송 빈도 초과'
    if domain == 'portfolio' and not customer['risk_profile']:
        return '투자성향 미확인'
    if domain == 'portfolio' and customer['has_portfolio']:
        return '동일 서비스 보유'
    if domain == 'deposit' and customer['maturity_days'] > 30:
        return '만기 조건 미충족'
    if domain == 'loan' and customer['loan_balance'] <= 0:
        return '보유 대출 없음'
    if domain == 'card' and customer['card_spend'] < 500000:
        return '카드 이용 조건 미충족'
    if domain == 'mydata' and customer['mydata']:
        return '마이데이터 연결 완료'
    if domain == 'tax' and not customer['mydata']:
        return '검토에 필요한 정보 미연결'
    return None


def forbidden_text(text):
    compact = re.sub(r'\s+', '', text).lower()
    return [word for word in FORBIDDEN if re.sub(r'\s+', '', word).lower() in compact]
