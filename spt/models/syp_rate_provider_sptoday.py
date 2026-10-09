# -*- coding: utf-8 -*-

import logging

from datetime import datetime

import pytz
import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SPTODAY_BASE_URL = "https://api-v2.sp-today.com/api/v1"
SPTODAY_TIMEOUT = 15
SPTODAY_TZ = pytz.timezone("Asia/Damascus")


class SypRateProviderSPToday(models.Model):
    _inherit = "syp.rate.provider"

    service = fields.Selection(
        selection_add=[("sptoday", "SP Today")],
        ondelete={"sptoday": "set default"},
    )
    sptoday_city = fields.Selection(
        string="City",
        selection=[("damascus", "Damascus"), ("aleppo", "Aleppo"), ("homs", "Homs")],
        default="damascus",
    )
    sptoday_quota_limit = fields.Integer(string="Monthly Quota", readonly=True)
    sptoday_quota_remaining = fields.Integer(string="Remaining Requests", readonly=True)
    sptoday_quota_reset = fields.Datetime(string="Quota Resets On", readonly=True)

    def _get_supported_currencies(self):
        self.ensure_one()
        if self.service != "sptoday":
            return super()._get_supported_currencies()  # pragma: no cover
        return ["SYP"]

    def _get_source_scale(self):
        self.ensure_one()
        if self.service != "sptoday":
            return super()._get_source_scale()  # pragma: no cover
        # verified on the first live fetch (2026-10-08): USD buy 13850 -> old pound
        return "old"

    def _obtain_rates(self, base_currency, currencies, date_from, date_to):
        self.ensure_one()
        if self.service != "sptoday":
            return super()._obtain_rates(
                base_currency, currencies, date_from, date_to
            )  # pragma: no cover
        api_key = self.sudo().api_key
        if not api_key:
            raise UserError(_("SP Today API key is not set on provider (company %s).", self.company_id.name))
        # /currencies returns every currency for every city: one call serves all
        # providers sharing the same key (the quota belongs to the key).
        data, quota = self._cached_fetch(
            ("sptoday", "/currencies", api_key),
            lambda: self._sptoday_fetch_currencies(api_key),
        )
        if quota:
            # account managers have read-only access on providers
            self.sudo().write(quota)
        return self._sptoday_parse_currencies(data)

    def _sptoday_fetch_currencies(self, api_key):
        _logger.info("SP Today: GET %s/currencies", SPTODAY_BASE_URL)
        try:
            response = requests.get(
                f"{SPTODAY_BASE_URL}/currencies",
                params={"lang": "en"},
                headers={"X-API-Key": api_key, "Accept": "application/json"},
                timeout=SPTODAY_TIMEOUT,
            )
        except requests.RequestException as e:
            raise UserError(_("SP Today request failed: %s", e)) from e

        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200 or not body.get("ok"):
            error = body.get("error") or {}
            raise UserError(
                _(
                    "SP Today error (HTTP %(status)s) %(code)s: %(message)s",
                    status=response.status_code,
                    code=error.get("code") or "-",
                    message=error.get("message") or response.reason,
                )
            )
        return body.get("data") or {}, self._sptoday_quota_from_headers(response.headers)

    def _sptoday_quota_from_headers(self, headers):
        quota = {}
        for header, field in (
            ("X-RateLimit-Limit", "sptoday_quota_limit"),
            ("X-RateLimit-Remaining", "sptoday_quota_remaining"),
        ):
            value = headers.get(header)
            if value is not None and str(value).isdigit():
                quota[field] = int(value)
        reset = headers.get("X-RateLimit-Reset")
        if reset is not None and str(reset).isdigit():
            quota["sptoday_quota_reset"] = datetime.fromtimestamp(int(reset), tz=pytz.utc).replace(tzinfo=None)
        return quota

    def _sptoday_parse_currencies(self, data):
        """Return {date_iso: {ISO: {"buy", "sell"}}} in SYP per 1 unit, for this provider's city.
        An item with only one of buy/sell uses it for both.

        The documentation shows the list as `data.rates` (overview) and as
        `data.currencies` (code samples); both are accepted.
        """
        self.ensure_one()
        items = data.get("rates") or data.get("currencies") or []
        if not isinstance(items, list):
            raise UserError(_("SP Today returned an unexpected payload: %s", str(data)[:300]))
        city = self.sptoday_city or "damascus"
        quotes, dates = {}, []
        for item in items:
            code = (item.get("code") or "").upper()
            prices = (item.get("cities") or {}).get(city) or {}
            buy = _to_float(prices.get("buy"))
            sell = _to_float(prices.get("sell"))
            if not code or not (buy or sell):
                continue
            quotes[code] = {"buy": buy or sell, "sell": sell or buy}
            if item.get("updated_at"):
                dates.append(_local_date(item["updated_at"]))
        if not quotes:
            return {}
        # /currencies is a live snapshot: all quotes belong to its latest update date.
        date = max(dates) if dates else _local_date(None)
        return {date: quotes}


def _to_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def _local_date(value):
    """ISO-8601 timestamp -> Damascus date (ISO string); today if missing/invalid."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(SPTODAY_TZ).date().isoformat()
    if moment.tzinfo is None:
        moment = pytz.utc.localize(moment)
    return moment.astimezone(SPTODAY_TZ).date().isoformat()
