# -*- coding: utf-8 -*-

from unittest import mock

from odoo.tests import tagged

from .common import SptCommon

QUOTES = {"USD": {"buy": 14000.0, "sell": 14200.0}, "EUR": {"buy": 16000.0, "sell": 16400.0}}


@tagged("post_install", "-at_install")
class TestUnitRateMath(SptCommon):
    def test_side_price(self):
        quote = {"buy": 100.0, "sell": 110.0}
        for side, expected in (("buy", 100.0), ("sell", 110.0), ("mid", 105.0)):
            self.provider_a.price_side = side
            self.assertEqual(self.provider_a._get_side_price(quote), expected, side)

    def test_scale_factor(self):
        provider = self.provider_a  # SP Today source scale is "old"
        provider.scale = "old"
        self.assertEqual(provider._get_scale_factor(), 1.0)
        provider.scale = "new"
        self.assertEqual(provider._get_scale_factor(), 0.01)
        with mock.patch.object(type(provider), "_get_source_scale", return_value="new"):
            self.assertEqual(provider._get_scale_factor(), 1.0)
            provider.scale = "old"
            self.assertEqual(provider._get_scale_factor(), 100.0)

    def test_quote_syp_never_scaled(self):
        self.provider_a.scale = "new"
        self.assertEqual(self.provider_a._get_quote(self.syp, {}), {"buy": 1.0, "sell": 1.0})

    def test_quote_scaled(self):
        self.provider_a.scale = "new"
        self.assertEqual(self.provider_a._get_quote(self.usd, QUOTES), {"buy": 140.0, "sell": 142.0})

    def test_quote_missing_or_zero(self):
        self.assertIsNone(self.provider_a._get_quote(self.eur, {"USD": QUOTES["USD"]}))
        self.assertIsNone(self.provider_a._get_quote(self.usd, {"USD": {"buy": 0.0, "sell": 5.0}}))

    def test_process_rate_usd_company(self):
        vals = self.provider_a._process_rate(self.syp, QUOTES)
        self.assertAlmostEqual(vals["rate"], 14100.0)
        self.assertAlmostEqual(vals["syp_buy_rate"], 14000.0)
        self.assertAlmostEqual(vals["syp_sell_rate"], 14200.0)

    def test_process_rate_syp_company(self):
        """Company in SYP: rate(USD) = 1 / q[USD]."""
        self.company_a.currency_id = self.syp
        vals = self.provider_a._process_rate(self.usd, {"USD": {"buy": 100.0, "sell": 100.0}})
        self.assertAlmostEqual(vals["rate"], 0.01)

    def test_process_rate_syp_company_new_scale(self):
        """Company in SYP (new pound): rate(USD) = 1 / (q_old / 100)."""
        self.company_a.currency_id = self.syp
        self.provider_a.scale = "new"
        vals = self.provider_a._process_rate(self.usd, {"USD": {"buy": 14000.0, "sell": 14000.0}})
        self.assertAlmostEqual(vals["rate"], 1 / 140.0)

    def test_process_rate_cross_rate_scale_cancels(self):
        """EUR company, USD target: q[EUR] / q[USD], independent of the SYP scale."""
        self.company_a.currency_id = self.eur
        self.provider_a.price_side = "buy"
        results = []
        for scale in ("old", "new"):
            self.provider_a.scale = scale
            results.append(self.provider_a._process_rate(self.usd, QUOTES))
        for vals in results:
            self.assertAlmostEqual(vals["rate"], 16000.0 / 14000.0)
            self.assertAlmostEqual(vals["syp_buy_rate"], 16000.0 / 14000.0)
            self.assertAlmostEqual(vals["syp_sell_rate"], 16400.0 / 14200.0)

    def test_process_rate_missing_quote(self):
        self.assertEqual(self.provider_a._process_rate(self.syp, {"EUR": QUOTES["EUR"]}), {})
