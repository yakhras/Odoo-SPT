# -*- coding: utf-8 -*-

import logging

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SptCommon, _payload, _response

OPERATIONS = ("read", "write", "create", "unlink")


@tagged("post_install", "-at_install")
class TestSecurity(SptCommon):
    def _assert_acl(self, model, user, allowed):
        records = self.env[model].with_user(user)
        for operation in OPERATIONS:
            if operation in allowed:
                records.check_access(operation)
            else:
                with self.assertRaises(AccessError, msg=f"{user.login} {operation} {model}"):
                    records.check_access(operation)

    def test_acl_provider(self):
        model = "syp.rate.provider"
        self._assert_acl(model, self.user_admin, OPERATIONS)
        self._assert_acl(model, self.user_manager, ("read",))
        self._assert_acl(model, self.user_invoice, ())
        self._assert_acl(model, self.user_portal, ())

    def test_acl_wizard(self):
        model = "syp.rate.update.wizard"
        self._assert_acl(model, self.user_admin, OPERATIONS)
        self._assert_acl(model, self.user_manager, OPERATIONS)
        self._assert_acl(model, self.user_invoice, ())
        self._assert_acl(model, self.user_portal, ())

    def test_manager_cannot_change_provider(self):
        provider = self.provider_a.with_user(self.user_manager)
        with self.assertRaises(AccessError):
            provider.write({"price_side": "buy"})
        with self.assertRaises(AccessError):
            provider.unlink()

    def test_api_key_restricted_to_admin(self):
        self.assertEqual(self.provider_a.with_user(self.user_admin).api_key, "test-key")
        manager_provider = self.provider_a.with_user(self.user_manager)
        with self.assertRaises(AccessError):
            manager_provider.read(["api_key"])
        self.assertNotIn("api_key", manager_provider.fields_get())
        self.assertIn("api_key", self.provider_a.with_user(self.user_admin).fields_get())

    def test_multi_company_rule(self):
        Provider = self.env["syp.rate.provider"].with_user(self.user_manager_a)
        visible = Provider.search([])
        self.assertIn(self.provider_a, visible)
        self.assertNotIn(self.provider_b, visible)
        with self.assertRaises(AccessError):
            self.provider_b.with_user(self.user_manager_a).read(["service"])

    def test_company_restricted_user_updates_own_company_only(self):
        providers = self.env["syp.rate.provider"].with_user(self.user_manager_a).search([("service", "=", "sptoday")])
        with self.mock_get():
            providers._update(self.date, self.date)
        self.assertTrue(self._rate(self.company_a))
        self.assertFalse(self._rate(self.company_b))

    def test_api_key_never_leaks(self):
        body = {"ok": False, "error": {"code": "INVALID_API_KEY", "message": "nope"}}
        with self.assertLogs("odoo.addons.spt", level=logging.DEBUG) as logs, mute_logger("odoo.sql_db"):
            with self.mock_get(_response(status=401, body=body)):
                self.provider_a._update(self.date, self.date)
            self.clear_fetch_cache()
            with self.mock_get(_response(body=_payload())):
                self.provider_a._update(self.date, self.date)
        self.assertNotIn("test-key", "\n".join(logs.output))
        for message in self.provider_a.message_ids:
            self.assertNotIn("test-key", message.body or "")
        for value in self.provider_a.message_ids.tracking_value_ids.mapped("new_value_char"):
            self.assertNotIn("test-key", value or "")

    def test_api_key_not_copied(self):
        company = self.env["res.company"].create({"name": "SYP Test C", "currency_id": self.usd.id})
        copy = self.provider_a.copy({"company_id": company.id})
        self.assertFalse(copy.api_key)
