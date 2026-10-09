# -*- coding: utf-8 -*-

from contextlib import contextmanager
from unittest import mock

from odoo.tests import TransactionCase

from odoo.addons.spt.models.syp_rate_provider import FETCH_CACHE_KEY

# External HTTP is already blocked by Odoo's test framework (BaseCase._request_handler):
# every test reaching SP Today must mock this target.
REQUESTS_GET = "odoo.addons.spt.models.syp_rate_provider_sptoday.requests.get"

DATE = "2026-01-17"


def _response(status=200, body=None, headers=None, json_error=None):
    response = mock.Mock()
    response.status_code = status
    response.reason = "OK" if status == 200 else "Error"
    if json_error:
        response.json.side_effect = json_error
    else:
        response.json.return_value = body if body is not None else {}
    response.headers = headers or {}
    return response


def _payload(key="rates", buy=14500, sell=14550):
    return {
        "ok": True,
        "data": {
            key: [
                {
                    "code": "USD",
                    "cities": {
                        "damascus": {"buy": buy, "sell": sell},
                        "aleppo": {"buy": buy - 20, "sell": sell - 20},
                    },
                    "updated_at": "2026-01-17T10:30:00+00:00",
                },
                {"code": "EUR", "cities": {"damascus": {"buy": 16000, "sell": 16100}}},
            ]
        },
    }


class SptCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usd = cls.env.ref("base.USD")
        cls.eur = cls.env.ref("base.EUR")
        cls.syp = cls.env.ref("base.SYP")
        (cls.syp | cls.eur).active = True
        cls.company_a = cls.env["res.company"].create({"name": "SYP Test A", "currency_id": cls.usd.id})
        cls.company_b = cls.env["res.company"].create({"name": "SYP Test B", "currency_id": cls.usd.id})
        Provider = cls.env["syp.rate.provider"]
        cls.provider_a = Provider.create(
            {"service": "sptoday", "company_id": cls.company_a.id, "currency_ids": [(6, 0, cls.syp.ids)],
             "api_key": "test-key", "scale": "old"}
        )
        cls.provider_b = Provider.create(
            {"service": "sptoday", "company_id": cls.company_b.id, "currency_ids": [(6, 0, cls.syp.ids)],
             "api_key": "test-key", "scale": "old"}
        )
        cls.date = DATE
        both = [(6, 0, (cls.company_a | cls.company_b).ids)]
        cls.user_admin = cls._create_user("spt_admin", ["base.group_system", "account.group_account_manager"], both)
        cls.user_manager = cls._create_user("spt_manager", ["account.group_account_manager"], both)
        cls.user_invoice = cls._create_user("spt_invoice", ["account.group_account_invoice"], both)
        cls.user_portal = cls._create_user("spt_portal", ["base.group_portal"], both)
        cls.user_manager_a = cls._create_user(
            "spt_manager_a", ["account.group_account_manager"], [(6, 0, cls.company_a.ids)]
        )

    @classmethod
    def _create_user(cls, login, groups, company_ids):
        return cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "company_id": company_ids[0][2][0],
            "company_ids": company_ids,
            "groups_id": [(6, 0, [cls.env.ref(g).id for g in groups])],
        })

    def setUp(self):
        super().setUp()
        # cursor cache lives across tests of the same class (same cursor)
        self.env.cr.cache.pop(FETCH_CACHE_KEY, None)

    def clear_fetch_cache(self):
        self.env.cr.cache.pop(FETCH_CACHE_KEY, None)

    @contextmanager
    def mock_get(self, response=None, **kwargs):
        if response is None and "side_effect" not in kwargs:
            response = _response(body=_payload())
        if response is not None:
            kwargs["return_value"] = response
        with mock.patch(REQUESTS_GET, **kwargs) as get:
            yield get

    def _rate(self, company, date=None):
        return self.env["res.currency.rate"].search(
            [("company_id", "=", company.id), ("currency_id", "=", self.syp.id), ("name", "=", date or self.date)]
        )
