# -*- coding: utf-8 -*-

from odoo.tests import tagged

from .common import SptCommon


@tagged("post_install", "-at_install")
class TestCoexistenceTcmb(SptCommon):
    """spt is built on the tcmb blueprint without depending on it: both must live together."""

    def setUp(self):
        super().setUp()
        if "res.currency.rate.provider" not in self.env:
            self.skipTest("tcmb is not installed")
        self.tcmb_provider = self.env["res.currency.rate.provider"].search([], limit=1)

    def test_spt_rate_has_no_tcmb_provider(self):
        with self.mock_get():
            self.provider_a._update(self.date, self.date)
        rate = self._rate(self.company_a)
        self.assertEqual(rate.syp_provider_id, self.provider_a)
        self.assertFalse(rate.provider_id)

    def test_manual_edit_clears_both_links(self):
        if not self.tcmb_provider:
            self.skipTest("no tcmb provider record")
        rate = self.env["res.currency.rate"].create({
            "company_id": self.company_a.id,
            "currency_id": self.syp.id,
            "name": self.date,
            "rate": 14500.0,
            "syp_provider_id": self.provider_a.id,
            "provider_id": self.tcmb_provider.id,
        })
        rate.rate = 14000.0
        self.assertFalse(rate.syp_provider_id)
        self.assertFalse(rate.provider_id)

    def test_each_module_keeps_its_own_link(self):
        if not self.tcmb_provider:
            self.skipTest("no tcmb provider record")
        rate = self.env["res.currency.rate"].create({
            "company_id": self.company_a.id,
            "currency_id": self.syp.id,
            "name": self.date,
            "rate": 14500.0,
        })
        rate.write({"rate": 1.0, "syp_provider_id": self.provider_a.id})
        self.assertEqual(rate.syp_provider_id, self.provider_a)
        rate.write({"rate": 2.0, "provider_id": self.tcmb_provider.id})
        self.assertEqual(rate.provider_id, self.tcmb_provider)
        self.assertFalse(rate.syp_provider_id)

    def test_distinct_models_and_crons(self):
        self.assertNotEqual(self.env["syp.rate.provider"]._table, self.env["res.currency.rate.provider"]._table)
        self.assertNotEqual(self.env.ref("spt.ir_cron_syp_rate_daily"), self.env.ref("tcmb.ir_cron_tcmb_every_day"))
