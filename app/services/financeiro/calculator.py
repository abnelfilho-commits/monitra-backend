"""Pure deterministic Decimal arithmetic. No database or care-plan dependency."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

CENT = Decimal('0.01')


def subtotal(unit_price, quantity=1):
    if not isinstance(unit_price, Decimal) or not unit_price.is_finite() or unit_price < 0:
        raise ValueError('Preço deve ser Decimal finito não negativo')
    if type(quantity) is not int or quantity < 1:
        raise ValueError('Quantidade deve ser inteiro positivo')
    with localcontext() as context:
        context.prec = max(28, len(unit_price.as_tuple().digits) + abs(unit_price.adjusted()) + len(str(quantity)) + 4)
        return (unit_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)


def summarize(items):
    items = tuple(items)
    priced = [item.subtotal for item in items if item.estado == 'CALCULADO']
    with localcontext() as context:
        context.prec = max(28, max((len(p.as_tuple().digits) for p in priced), default=1) + len(str(len(priced))) + 4)
        amount = sum(priced, Decimal('0.00')).quantize(CENT, rounding=ROUND_HALF_UP) if priced else None
    return dict(quantidade_considerada=len(items), quantidade_precificada=len(priced),
                quantidade_pendente=len(items) - len(priced), subtotal_precificado=amount)
