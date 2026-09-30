from backend.provider import generate


def run(ctx):
    rows = ctx.get('deliveries', [])
    sent = len(rows)
    opened = sum(r['opened'] for r in rows)
    clicked = sum(r['clicked'] for r in rows)
    converted = sum(r['converted'] for r in rows)
    result = {'summary': f'시연 발송 {sent}건 · 클릭 {clicked}건 · 연결 {converted}건', 'sent': sent, 'opened': opened, 'clicked': clicked, 'converted': converted, 'cost': sum(r['cost'] for r in rows), 'ctr': round(clicked / max(1, sent) * 100, 1), 'conversion_rate': round(converted / max(1, sent) * 100, 1), 'data_kind': 'synthetic', 'recommendation': 'A/B 문안별 클릭률을 비교하고, 빈도 제외가 많은 고객군은 안내 간격을 늘려보세요.'}
    generated = generate(['recommendation'], f'가상 데이터 성과 요약: 발송 {sent}, 열람 {opened}, 클릭 {clicked}, 연결 {converted}. 인과관계나 실측 고객편익은 단정하지 말고 다음 실험 한 가지를 제안하세요.', {'recommendation': result['recommendation']}, ctx.get('llm_enabled', True))
    result.update(generated)
    return result
