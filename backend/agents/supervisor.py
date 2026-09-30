from backend.catalog import EVENT_FLOW, CAMPAIGN_FLOW


def run(ctx):
    campaign = ctx['request']['mode'] == 'campaign'
    return {'summary': '담당자 협업 캠페인 계획 수립' if campaign else '고객 이벤트 기반 개인화 계획 수립', 'flow': CAMPAIGN_FLOW if campaign else EVENT_FLOW, 'mode': ctx['request']['mode'], 'requires_staff_approval': campaign, 'contract_version': 1}
