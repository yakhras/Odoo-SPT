# -*- coding: utf-8 -*-

from odoo.tests import Form, tagged

from .common import SptCommon


@tagged("post_install", "-at_install")
class TestViews(SptCommon):
    def _form_arch(self, user, model="syp.rate.provider"):
        return self.env[model].with_user(user).get_views([(False, "form")])["views"]["form"]["arch"]

    def test_all_module_views_valid(self):
        view_ids = self.env["ir.model.data"].search(
            [("module", "=", "spt"), ("model", "=", "ir.ui.view")]
        ).mapped("res_id")
        views = self.env["ir.ui.view"].browse(view_ids)
        self.assertGreaterEqual(len(views), 5)
        for view in views:
            view._check_xml()

    def test_currency_rate_views_render(self):
        Rate = self.env["res.currency.rate"].with_user(self.user_manager)
        views = Rate.get_views([(False, "form"), (False, "list")])["views"]
        for view_type in ("form", "list"):
            arch = views[view_type]["arch"]
            for field in ("syp_buy_rate", "syp_sell_rate", "syp_provider_id"):
                self.assertIn(f'name="{field}"', arch, view_type)

    def test_api_key_in_form_for_admin_only(self):
        self.assertIn('name="api_key"', self._form_arch(self.user_admin))
        self.assertNotIn('name="api_key"', self._form_arch(self.user_manager))

    def test_form_sptoday_section_follows_service(self):
        company = self.env["res.company"].create({"name": "SYP Test C", "currency_id": self.usd.id})
        self.user_admin.company_ids |= company
        Provider = self.env["syp.rate.provider"].with_user(self.user_admin).with_company(company)
        with Form(Provider) as form:
            with self.assertRaises(AssertionError):
                form.sptoday_city = "aleppo"  # SP Today group invisible for service "none"
            form.service = "sptoday"
            form.sptoday_city = "aleppo"
            form.api_key = "form-key"
            form.scale = "old"
        provider = form.record
        self.assertEqual(provider.name, "SP Today")
        self.assertEqual(provider.sptoday_city, "aleppo")
        self.assertEqual(provider.sudo().api_key, "form-key")
        self.assertEqual(provider.currency_ids, self.syp)

    def test_form_update_button_targets_wizard(self):
        action = self.env.ref("spt.syp_rate_update_wizard_action")
        self.assertIn(f'name="{action.id}"', self._form_arch(self.user_admin))
        self.assertEqual(action.res_model, "syp.rate.update.wizard")

    def test_wizard_form(self):
        Wizard = self.env["syp.rate.update.wizard"].with_user(self.user_manager).with_context(
            active_model="syp.rate.provider", active_ids=self.provider_a.ids
        )
        with Form(Wizard) as form:
            self.assertEqual(form.provider_ids.ids, self.provider_a.ids)
        self.assertEqual(form.record.provider_ids, self.provider_a)

    def test_action_and_menu(self):
        action = self.env.ref("spt.action_syp_rate_provider")
        self.assertEqual(action.res_model, "syp.rate.provider")
        menu = self.env.ref("spt.menu_syp_rate_provider")
        self.assertEqual(menu.action, action)
        Menu = self.env["ir.ui.menu"]
        self.assertIn(menu.id, Menu.with_user(self.user_manager)._visible_menu_ids())
        self.assertIn(menu.id, Menu.with_user(self.user_admin)._visible_menu_ids())
        self.assertNotIn(menu.id, Menu.with_user(self.user_invoice)._visible_menu_ids())
