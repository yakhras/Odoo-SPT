# Generated demo data for screenshots (no SP Today account, no API call).
# The SP Today client is replaced, for this shell session only, by a fake that answers like
# /currencies; the module's own update then stores two weeks of SYP rates, one day at a time.
# Run on a throwaway DB: odoo shell -d spt_demo < tools/demo_data.py
# (scripts/module_lab.ps1 -Do up does this). The file is the same on every series branch.
import random
from datetime import date, datetime, timedelta

rnd = random.Random(7)
DAYS = 14
today = date.today()

syp, usd, eur = env.ref('base.SYP'), env.ref('base.USD'), env.ref('base.EUR')
(syp | eur).active = True
company = env.company
company.currency_id = usd  # SYP is the foreign currency; its rate is SYP per 1 USD
company.name = 'My Company'

state = {'day': today, 'usd': 13850.0}


def fake_fetch(provider, api_key):
    """One /currencies snapshot for state['day'], in old pounds like the real API."""
    usd_buy = state['usd']
    items = []
    for code, factor in (('USD', 1.0), ('EUR', 1.085), ('TRY', 0.0295), ('SAR', 0.2666)):
        buy = round(usd_buy * factor, 2)
        items.append({
            'code': code,
            'cities': {city: {'buy': buy + off, 'sell': round(buy * 1.004 + off, 2)}
                       for city, off in (('damascus', 0), ('aleppo', -15), ('homs', -8))},
            'updated_at': f"{state['day'].isoformat()}T09:30:00+00:00",
        })
    quota = {'sptoday_quota_limit': 1000, 'sptoday_quota_remaining': 1000 - 3 * DAYS,
             'sptoday_quota_reset': datetime.combine(today.replace(day=1) + timedelta(days=32), datetime.min.time()).replace(day=1)}
    return {'rates': items}, quota


env.registry['syp.rate.provider']._sptoday_fetch_currencies = fake_fetch

provider = env['syp.rate.provider'].create({
    'service': 'sptoday', 'company_id': company.id, 'currency_ids': [(6, 0, syp.ids)],
    'api_key': 'demo-key-not-real', 'sptoday_city': 'damascus', 'price_side': 'mid', 'scale': 'new',
})

# Two weeks of rates: the pound drifts a little every day.
for offset in range(DAYS - 1, -1, -1):
    state['day'] = today - timedelta(days=offset)
    state['usd'] = round(state['usd'] * (1 + rnd.uniform(-0.006, 0.009)), 0)
    env.cr.cache.pop('spt.fetch', None)  # the module caches one fetch per transaction
    provider._update(state['day'], state['day'])
provider.last_successful_run = today

# A second company with its own provider (Aleppo, sell side), not updated yet.
branch = env['res.company'].create({'name': 'My Company (Aleppo)', 'currency_id': usd.id})
env['syp.rate.provider'].create({
    'service': 'sptoday', 'company_id': branch.id, 'currency_ids': [(6, 0, syp.ids)],
    'api_key': 'demo-key-not-real', 'sptoday_city': 'aleppo', 'price_side': 'sell', 'scale': 'new',
})

# The demo server must not call the real SP Today with the fake key.
env.ref('spt.ir_cron_syp_rate_daily').active = False
env.cr.commit()
rates = env['res.currency.rate'].search([('currency_id', '=', syp.id), ('company_id', '=', company.id)])
# An xml id for the screenshot spec: open: /odoo/action-base.act_view_currency_rates/{ref:spt_demo.latest_syp_rate}
env['ir.model.data'].create({'module': 'spt_demo', 'name': 'latest_syp_rate',
                             'model': 'res.currency.rate', 'res_id': rates[:1].id, 'noupdate': True})
env.cr.commit()
print('demo data ready:', len(rates), 'SYP rates, latest', rates[:1].name, rates[:1].company_rate)
