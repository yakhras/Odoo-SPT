# -*- coding: utf-8 -*-

from unittest import mock

from odoo.tests import tagged

from .common import SptCommon, _payload, _response


@tagged("post_install", "-at_install")
class TestUpdateFlow(SptCommon):
    def test_mid_rate_and_storage(self):
        headers = {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "97", "X-RateLimit-Reset": "1769904000"}
        with self.mock_get(_response(body=_payload(), headers=headers)):
            self.provider_a._update(self.date, self.date)
        rate = self._rate(self.company_a)
        self.assertEqual(len(rate), 1)
        self.assertAlmostEqual(rate.rate, 14525.0)
        self.assertAlmostEqual(rate.syp_buy_rate, 14500.0)
        self.assertAlmostEqual(rate.syp_sell_rate, 14550.0)
        self.assertEqual(rate.syp_provider_id, self.provider_a)
        self.assertEqual(self.provider_a.sptoday_quota_remaining, 97)
        self.assertEqual(self.provider_a.sptoday_quota_limit, 100)

    def test_currencies_payload_key_and_side(self):
        self.provider_a.price_side = "sell"
        with self.mock_get(_response(body=_payload(key="currencies"))):
            self.provider_a._update(self.date, self.date)
        self.assertAlmostEqual(self._rate(self.company_a).rate, 14550.0)

    def test_city(self):
        self.provider_a.sptoday_city = "aleppo"
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        self.assertAlmostEqual(self._rate(self.company_a).rate, 14505.0)

    def test_one_http_call_for_all_companies(self):
        with self.mock_get() as get:
            (self.provider_a | self.provider_b)._update(self.date, self.date)
        self.assertEqual(get.call_count, 1)
        self.assertTrue(self._rate(self.company_a))
        self.assertTrue(self._rate(self.company_b))

    def test_new_scale_divides_by_100(self):
        self.provider_a.scale = "new"
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        rate = self._rate(self.company_a)
        self.assertAlmostEqual(rate.rate, 145.25)
        self.assertAlmostEqual(rate.syp_buy_rate, 145.0)
        self.assertAlmostEqual(rate.syp_sell_rate, 145.5)

    def test_api_key_sent_from_provider(self):
        with self.mock_get() as get:
            self.provider_a._update(self.date, self.date)
        kwargs = get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-API-Key"], "test-key")
        self.assertNotIn("api_key", kwargs.get("params") or {})
        self.assertTrue(kwargs.get("timeout"))

    def test_different_keys_separate_calls(self):
        self.provider_b.api_key = "other-key"
        with self.mock_get() as get:
            (self.provider_a | self.provider_b)._update(self.date, self.date)
        self.assertEqual(get.call_count, 2)

    def test_missing_key(self):
        self.provider_a.api_key = False
        with self.mock_get() as get:
            self.provider_a._update(self.date, self.date)
        get.assert_not_called()
        self.assertFalse(self._rate(self.company_a))
        self.assertIn("API key is not set", self.provider_a.message_ids[0].body)

    def test_account_manager_manual_update(self):
        """Read-only provider access must still allow a manual update (key read, quota write)."""
        with self.mock_get(_response(body=_payload(), headers={"X-RateLimit-Remaining": "90"})):
            self.provider_a.with_user(self.user_manager_a).with_company(self.company_a)._update(
                self.date, self.date
            )
        self.assertAlmostEqual(self._rate(self.company_a).rate, 14525.0)
        self.assertEqual(self.provider_a.sptoday_quota_remaining, 90)

    def test_upsert_same_day(self):
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        self.clear_fetch_cache()
        with self.mock_get(_response(body=_payload(buy=15000, sell=15000))):
            self.provider_a._update(self.date, self.date)
        rate = self._rate(self.company_a)
        self.assertEqual(len(rate), 1)
        self.assertAlmostEqual(rate.rate, 15000.0)

    def test_manual_edit_unlinks_provider(self):
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        rate = self._rate(self.company_a)
        rate.rate = 14000
        self.assertFalse(rate.syp_provider_id)

    def test_newest_only(self):
        data = {
            "2026-01-15": {"USD": {"buy": 100.0, "sell": 100.0}},
            "2026-01-17": {"USD": {"buy": 200.0, "sell": 200.0}},
        }
        with mock.patch.object(type(self.provider_a), "_obtain_rates", return_value=data):
            self.provider_a._update("2026-01-15", "2026-01-17", newest_only=True)
        self.assertFalse(self._rate(self.company_a, "2026-01-15"))
        self.assertAlmostEqual(self._rate(self.company_a, "2026-01-17").rate, 200.0)

    def test_all_dates_without_newest_only(self):
        data = {
            "2026-01-15": {"USD": {"buy": 100.0, "sell": 100.0}},
            "2026-01-17": {"USD": {"buy": 200.0, "sell": 200.0}},
        }
        with mock.patch.object(type(self.provider_a), "_obtain_rates", return_value=data):
            self.provider_a._update("2026-01-15", "2026-01-17")
        self.assertAlmostEqual(self._rate(self.company_a, "2026-01-15").rate, 100.0)
        self.assertAlmostEqual(self._rate(self.company_a, "2026-01-17").rate, 200.0)

    def test_company_currency_skipped(self):
        self.provider_a.currency_ids = self.syp | self.usd
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        usd_rates = self.env["res.currency.rate"].search(
            [("company_id", "=", self.company_a.id), ("currency_id", "=", self.usd.id)]
        )
        self.assertFalse(usd_rates.filtered("syp_provider_id"))
        self.assertTrue(self._rate(self.company_a))

    def test_quota_written_only_on_success(self):
        self.provider_a.sudo().sptoday_quota_remaining = 50
        body = {"ok": False, "error": {"code": "QUOTA_EXCEEDED", "message": "nope"}}
        with self.mock_get(_response(status=429, body=body, headers={"X-RateLimit-Remaining": "0"})):
            self.provider_a._update(self.date, self.date)
        self.assertEqual(self.provider_a.sptoday_quota_remaining, 50)

    def test_manual_update_does_not_touch_schedule(self):
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        self.assertFalse(self.provider_a.last_successful_run)
