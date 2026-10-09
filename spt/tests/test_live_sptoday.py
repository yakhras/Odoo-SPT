# -*- coding: utf-8 -*-
"""Live smoke test against SP Today. Costs 1 request of the monthly quota.

Never part of a standard run. Usage:
    docker exec -e SPT_LIVE_KEY=<key> odoo-docker-odoo-dev-1 odoo ... --test-enable --test-tags spt_live
"""

import os

import werkzeug.urls

from odoo.tests import TransactionCase, tagged
from odoo.tests.common import _super_send

from odoo.addons.spt.models.syp_rate_provider_sptoday import SPTODAY_BASE_URL

SPTODAY_HOST = werkzeug.urls.url_parse(SPTODAY_BASE_URL).host


@tagged("-standard", "spt_live", "post_install", "-at_install")
class TestLiveSPToday(TransactionCase):
    @classmethod
    def _request_handler(cls, s, r, /, **kw):
        # only SP Today is let through; everything else stays blocked
        if werkzeug.urls.url_parse(r.url).host == SPTODAY_HOST:
            return _super_send(s, r, **kw)
        return super()._request_handler(s, r, **kw)

    def test_live_currencies(self):
        api_key = os.environ.get("SPT_LIVE_KEY")
        if not api_key:
            self.skipTest("SPT_LIVE_KEY is not set")
        provider = self.env["syp.rate.provider"].new({"service": "sptoday", "sptoday_city": "damascus"})
        data, quota = provider._sptoday_fetch_currencies(api_key)
        self.assertTrue(data.get("rates") or data.get("currencies"), "no rates/currencies list in payload")
        self.assertIn("sptoday_quota_remaining", quota)

        (quotes,) = provider._sptoday_parse_currencies(data).values()
        usd = quotes.get("USD")
        self.assertTrue(usd, "USD missing for damascus")
        self.assertGreater(usd["buy"], 0)
        self.assertGreater(usd["sell"], 0)
        # fails the day SP Today switches to the new pound: then update _get_source_scale()
        self.assertGreater(usd["buy"], 1000, "SP Today seems to quote the NEW pound now")
