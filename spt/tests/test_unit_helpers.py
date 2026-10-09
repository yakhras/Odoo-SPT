# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.spt.models.syp_rate_provider_sptoday import SPTODAY_TZ, _local_date, _to_float

from .common import SptCommon


@tagged("post_install", "-at_install")
class TestUnitHelpers(SptCommon):
    def test_to_float(self):
        self.assertEqual(_to_float("14500"), 14500.0)
        self.assertEqual(_to_float(14500.5), 14500.5)
        for value in (None, "abc", 0, -5, "", {}):
            self.assertEqual(_to_float(value), 0.0, value)

    def test_local_date_rolls_over_to_damascus_day(self):
        # 22:30 UTC = 01:30 next day in Damascus (UTC+3)
        self.assertEqual(_local_date("2026-01-17T22:30:00+00:00"), "2026-01-18")
        self.assertEqual(_local_date("2026-01-17T10:30:00+00:00"), "2026-01-17")

    def test_local_date_naive_is_utc(self):
        self.assertEqual(_local_date("2026-01-17T22:30:00"), "2026-01-18")

    def test_local_date_z_suffix(self):
        self.assertEqual(_local_date("2026-01-17T22:30:00Z"), "2026-01-18")

    def test_local_date_invalid_is_today(self):
        today = datetime.now(SPTODAY_TZ).date().isoformat()
        self.assertEqual(_local_date(None), today)
        self.assertEqual(_local_date("garbage"), today)

    def test_quota_headers_full(self):
        quota = self.provider_a._sptoday_quota_from_headers(
            {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "97", "X-RateLimit-Reset": "1793480400"}
        )
        self.assertEqual(quota["sptoday_quota_limit"], 100)
        self.assertEqual(quota["sptoday_quota_remaining"], 97)
        self.assertEqual(quota["sptoday_quota_reset"], datetime(2026, 10, 31, 21, 0, 0))

    def test_quota_headers_missing_or_invalid(self):
        self.assertEqual(self.provider_a._sptoday_quota_from_headers({}), {})
        quota = self.provider_a._sptoday_quota_from_headers(
            {"X-RateLimit-Limit": "abc", "X-RateLimit-Remaining": "-1", "X-RateLimit-Reset": "soon"}
        )
        self.assertEqual(quota, {})

    def test_parse_rates_and_currencies_keys(self):
        for key in ("rates", "currencies"):
            parsed = self.provider_a._sptoday_parse_currencies(
                {key: [{"code": "usd", "cities": {"damascus": {"buy": 10, "sell": 12}},
                        "updated_at": "2026-01-17T10:30:00+00:00"}]}
            )
            self.assertEqual(parsed, {"2026-01-17": {"USD": {"buy": 10.0, "sell": 12.0}}}, key)

    def test_parse_no_list_key(self):
        self.assertEqual(self.provider_a._sptoday_parse_currencies({}), {})
        self.assertEqual(self.provider_a._sptoday_parse_currencies({"rates": []}), {})

    def test_parse_non_list_raises(self):
        with self.assertRaises(UserError):
            self.provider_a._sptoday_parse_currencies({"rates": {"USD": 1}})

    def test_parse_skips_incomplete_items(self):
        parsed = self.provider_a._sptoday_parse_currencies({"rates": [
            {"code": "", "cities": {"damascus": {"buy": 1, "sell": 1}}},
            {"code": "EUR", "cities": {"aleppo": {"buy": 1, "sell": 1}}},
            {"code": "TRY", "cities": {"damascus": {"buy": 0, "sell": None}}},
            {"code": "USD", "cities": {"damascus": {"buy": 5, "sell": 6}}},
        ]})
        (quotes,) = parsed.values()
        self.assertEqual(list(quotes), ["USD"])

    def test_parse_one_sided_price(self):
        parsed = self.provider_a._sptoday_parse_currencies({"rates": [
            {"code": "USD", "cities": {"damascus": {"buy": 5}}},
            {"code": "EUR", "cities": {"damascus": {"sell": 7}}},
        ]})
        (quotes,) = parsed.values()
        self.assertEqual(quotes["USD"], {"buy": 5.0, "sell": 5.0})
        self.assertEqual(quotes["EUR"], {"buy": 7.0, "sell": 7.0})

    def test_parse_snapshot_date_is_latest_update(self):
        parsed = self.provider_a._sptoday_parse_currencies({"rates": [
            {"code": "USD", "cities": {"damascus": {"buy": 5, "sell": 5}}, "updated_at": "2026-01-16T10:00:00+00:00"},
            {"code": "EUR", "cities": {"damascus": {"buy": 7, "sell": 7}}, "updated_at": "2026-01-17T10:00:00+00:00"},
        ]})
        self.assertEqual(list(parsed), ["2026-01-17"])
        self.assertEqual(set(parsed["2026-01-17"]), {"USD", "EUR"})

    def test_parse_uses_provider_city(self):
        self.provider_a.sptoday_city = "aleppo"
        parsed = self.provider_a._sptoday_parse_currencies({"rates": [
            {"code": "USD", "cities": {"damascus": {"buy": 5, "sell": 5}, "aleppo": {"buy": 8, "sell": 9}}},
        ]})
        (quotes,) = parsed.values()
        self.assertEqual(quotes["USD"], {"buy": 8.0, "sell": 9.0})
