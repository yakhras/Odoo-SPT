# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SptCommon


@tagged("post_install", "-at_install")
class TestProviderModel(SptCommon):
    def _new_company(self, name="SYP Test C"):
        return self.env["res.company"].create({"name": name, "currency_id": self.usd.id})

    def test_defaults(self):
        company = self._new_company()
        provider = self.env["syp.rate.provider"].with_company(company).create({})
        self.assertEqual(provider.service, "none")
        self.assertEqual(provider.price_side, "mid")
        self.assertEqual(provider.scale, "new")
        self.assertEqual(provider.sptoday_city, "damascus")
        self.assertEqual(provider.currency_ids, self.syp)
        self.assertEqual(provider.company_id, company)
        self.assertEqual(provider.interval_type, "days")
        self.assertEqual(provider.interval_number, 1)
        self.assertEqual(provider.next_run, fields.Date.today())
        self.assertTrue(provider.active)

    def test_compute_name(self):
        provider = self.env["syp.rate.provider"].create({"company_id": self._new_company().id})
        self.assertEqual(provider.name, "None")
        provider.service = "sptoday"
        self.assertEqual(provider.name, "SP Today")

    def test_compute_daily(self):
        self.assertTrue(self.provider_a.daily)
        self.provider_a.interval_number = 2
        self.assertFalse(self.provider_a.daily)
        self.provider_a.write({"interval_number": 1, "interval_type": "weeks"})
        self.assertFalse(self.provider_a.daily)

    def test_compute_update_schedule(self):
        self.assertEqual(self.provider_a.update_schedule, "1 Day(s)")
        self.provider_a.write({"interval_number": 2, "interval_type": "weeks"})
        self.assertEqual(self.provider_a.update_schedule, "2 Week(s)")
        self.provider_a.active = False
        self.assertEqual(self.provider_a.update_schedule, "Inactive")

    def test_available_currencies(self):
        self.assertEqual(self.provider_a.available_currency_ids, self.syp)
        provider = self.env["syp.rate.provider"].create({"company_id": self._new_company().id})
        self.assertFalse(provider.available_currency_ids)

    @mute_logger("odoo.sql_db")
    def test_unique_service_per_company(self):
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["syp.rate.provider"].create({"service": "sptoday", "company_id": self.company_a.id})

    @mute_logger("odoo.sql_db")
    def test_interval_strictly_positive(self):
        for value in (0, -1):
            with self.assertRaises(IntegrityError), self.env.cr.savepoint():
                self.provider_a.interval_number = value
                self.provider_a.flush_recordset()

    def test_next_run_period(self):
        provider = self.provider_a
        for interval_type, expected in (
            ("days", relativedelta(days=3)),
            ("weeks", relativedelta(weeks=3)),
            ("months", relativedelta(months=3)),
        ):
            provider.write({"interval_type": interval_type, "interval_number": 3})
            self.assertEqual(provider._get_next_run_period(), expected)


@tagged("post_install", "-at_install")
class TestCurrencyRateLink(SptCommon):
    def setUp(self):
        super().setUp()
        self.rate = self.env["res.currency.rate"].create({
            "company_id": self.company_a.id,
            "currency_id": self.syp.id,
            "name": self.date,
            "rate": 14500.0,
            "syp_buy_rate": 14400.0,
            "syp_sell_rate": 14600.0,
            "syp_provider_id": self.provider_a.id,
        })

    def test_manual_rate_fields_unlink_provider(self):
        for vals in ({"rate": 1.0}, {"syp_buy_rate": 1.0}, {"syp_sell_rate": 1.0}, {"name": "2026-01-18"}):
            self.rate.syp_provider_id = self.provider_a
            self.rate.write(vals)
            self.assertFalse(self.rate.syp_provider_id, vals)

    def test_write_with_provider_keeps_link(self):
        self.rate.write({"rate": 1.0, "syp_provider_id": self.provider_a.id})
        self.assertEqual(self.rate.syp_provider_id, self.provider_a)

    def test_unrelated_field_keeps_link(self):
        self.rate.write({"company_id": self.company_a.id})
        self.assertEqual(self.rate.syp_provider_id, self.provider_a)
