from decimal import Decimal, InvalidOperation

OUTPUTS = ['price_excl_vat', 'max_invoice_price', 'cogs_limit', 'cu_total_margin']

def vat_rate():
    from .models import TargetCostingSettings
    policy = TargetCostingSettings.objects.first()
    return policy.vat_percent if policy else Decimal('10.0')

def calculate(values, vat=None):
    """Keep full precision between formulas; missing inputs stay unknown."""
    def number(key):
        try:
            value = Decimal(str(values.get(key)))
            return value if value.is_finite() else None
        except (InvalidOperation, ValueError, TypeError):
            return None
    vat = Decimal(str(vat if vat is not None else vat_rate()))
    price, margin, rebate, vendor = [number(key) for key in
        ['target_shelf_price', 'cu_margin', 'vendor_rebate', 'vendor_margin']]
    net = price / (1 + vat / 100) if price is not None else None
    invoice = net * (1 - margin / 100) if net is not None and margin is not None else None
    limit = invoice * (1 - rebate / 100) * (1 - vendor / 100) if invoice is not None and rebate is not None and vendor is not None else None
    total = (1 - (1 - margin / 100) * (1 - rebate / 100)) * 100 if margin is not None and rebate is not None else None
    return dict(zip(['vat_percent'] + OUTPUTS, [vat, net, invoice, limit, total]))
