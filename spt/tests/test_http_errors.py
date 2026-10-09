# -*- coding: utf-8 -*-

import requests

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SptCommon, _response

LOGGER = "odoo.addons.spt.models.syp_rate_provider"


@tagged("post_install", "-at_install")
class TestHttpErrors(SptCommon):
    def _assert_failure(self, expected_text, **mock_kwargs):
        """Nothing written, error posted on each provider, a single call for both."""
        self.clear_fetch_cache()
        providers = self.provider_a | self.provider_b
        with mute_logger(LOGGER), self.mock_get(**mock_kwargs) as get:
            providers._update(self.date, self.date)
        self.assertEqual(get.call_count, 1)
        self.assertFalse(self._rate(self.company_a))
        self.assertFalse(self._rate(self.company_b))
        for provider in providers:
            self.assertIn(expected_text, provider.message_ids[0].body)

    def test_timeout(self):
        self._assert_failure("request failed", side_effect=requests.Timeout("timed out"))

    def test_connection_error(self):
        self._assert_failure("request failed", side_effect=requests.ConnectionError("no route"))

    def test_server_error_html_body(self):
        self._assert_failure("HTTP 500", response=_response(status=500, json_error=ValueError("not json")))

    def test_ok_false_with_http_200(self):
        body = {"ok": False, "error": {"code": "SOMETHING", "message": "bad"}}
        self._assert_failure("SOMETHING", response=_response(body=body))

    def test_not_found(self):
        body = {"ok": False, "error": {"code": "NOT_FOUND", "message": "nope"}}
        self._assert_failure("NOT_FOUND", response=_response(status=404, body=body))

    def test_auth_and_quota_errors(self):
        for status, code in ((401, "INVALID_API_KEY"), (401, "MISSING_API_KEY"), (429, "QUOTA_EXCEEDED")):
            body = {"ok": False, "error": {"code": code, "message": "resets_at 2026-11-01"}}
            self._assert_failure(code, response=_response(status=status, body=body))

    def test_unexpected_payload(self):
        body = {"ok": True, "data": {"rates": "maintenance"}}
        self._assert_failure("unexpected payload", response=_response(body=body))

    def test_failure_does_not_block_next_transaction_fetch(self):
        with mute_logger(LOGGER), self.mock_get(side_effect=requests.Timeout("x")):
            self.provider_a._update(self.date, self.date)
        self.clear_fetch_cache()
        with self.mock_get() as get:
            self.provider_a._update(self.date, self.date)
        self.assertEqual(get.call_count, 1)
        self.assertTrue(self._rate(self.company_a))
