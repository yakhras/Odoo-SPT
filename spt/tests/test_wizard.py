# -*- coding: utf-8 -*-

from datetime import date
from unittest import mock

from odoo import fields
from odoo.tests import tagged

from .common import SptCommon


@tagged("post_install", "-at_install")
class TestWizard(SptCommon):
    def test_default_get_from_providers(self):
        providers = self.provider_a | self.provider_b
        wizard = self.env["syp.rate.update.wizard"].with_context(
            active_model="syp.rate.provider", active_ids=providers.ids
        ).create({})
        self.assertEqual(wizard.provider_ids, providers)
        today = fields.Date.context_today(wizard)
        self.assertEqual((wizard.date_from, wizard.date_to), (today, today))

    def test_default_get_other_model(self):
        wizard = self.env["syp.rate.update.wizard"].with_context(
            active_model="res.partner", active_ids=self.provider_a.ids
        ).create({})
        self.assertFalse(wizard.provider_ids)

    def test_action_update_delegates(self):
        wizard = self.env["syp.rate.update.wizard"].create({
            "date_from": "2026-01-10",
            "date_to": "2026-01-17",
            "provider_ids": [(6, 0, self.provider_a.ids)],
        })
        with mock.patch.object(type(self.provider_a), "_update") as update:
            action = wizard.action_update()
        update.assert_called_once_with(date(2026, 1, 10), date(2026, 1, 17))
        self.assertEqual(action, {"type": "ir.actions.act_window_close"})

    def test_action_update_as_account_manager(self):
        env = self.env(user=self.user_manager)
        wizard = env["syp.rate.update.wizard"].with_context(
            active_model="syp.rate.provider", active_ids=self.provider_a.ids,
            allowed_company_ids=(self.company_a | self.company_b).ids,
        ).create({"date_from": self.date, "date_to": self.date})
        with self.mock_get():
            wizard.action_update()
        self.assertAlmostEqual(self._rate(self.company_a).rate, 14525.0)
