from backend.catalog import DOMAINS


def mydata(customer, event):
    return not customer['mydata'] and event in ('tax', 'mydata')


def deposit(customer, event):
    return event == 'maturity' and customer['maturity_days'] <= 30


def portfolio(customer, event):
    return event in ('salary', 'balance') and customer['balance'] >= 10000000 and not customer['has_portfolio']


def loan(customer, event):
    return event == 'loan' and customer['loan_balance'] > 0


def card(customer, event):
    return event == 'card' and customer['card_spend'] >= 500000


def tax(customer, event):
    return event == 'tax' and bool(customer['mydata'])


TOOLS = {'mydata': mydata, 'deposit': deposit, 'portfolio': portfolio, 'loan': loan, 'card': card, 'tax': tax}
REASONS = {'mydata': '추가 정보가 필요한 상황으로, 고객 동의 후 연결 안내가 가능합니다.', 'deposit': '30일 이내 만기 예정 자금이 있어 재예치 선택지를 비교합니다.', 'portfolio': '1천만원 이상 여유자금이 있으며 포트폴리오 서비스를 보유하지 않았습니다.', 'loan': '보유 대출의 조건을 확인하고 상담 선택지를 제공합니다.', 'card': '월 카드 이용액을 바탕으로 혜택 비교를 안내합니다.', 'tax': '안경점 결제의 공제 가능성을 검토할 수 있습니다. 환급을 확정하지 않습니다.'}


def discover(customer, event):
    return [{'domain': key, 'label': DOMAINS[key], 'reason': REASONS[key]} for key, tool in TOOLS.items() if tool(customer, event)]
