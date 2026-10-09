# -*- coding: utf-8 -*-

import logging

from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Key of the per-transaction cache (cursor.cache) holding raw provider responses,
# so N company providers of the same service cost a single HTTP call per run.
FETCH_CACHE_KEY = "spt.fetch"


class SypRateProvider(models.Model):
    """Generic Syrian rates provider (blueprint: tcmb res.currency.rate.provider).

    Each provider service plugs in through `selection_add` on `service` and
    overrides `_get_supported_currencies()` and `_obtain_rates()`.

    `_obtain_rates()` must return quotes in SYP per 1 unit of each currency:
        {date_iso: {ISO: {"buy": float, "sell": float}}}
    The conversion to Odoo rates (relative to the company currency) is done here.
    """

    _name = "syp.rate.provider"
    _description = "Syrian Currency Rates Provider"
    _inherit = ["mail.thread"]
    _order = "name"

    company_id = fields.Many2one(
        string="Company",
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    service = fields.Selection(
        string="Provider",
        selection=[("none", "None")],
        default="none",
        required=True,
    )
    name = fields.Char(compute="_compute_name", store=True)
    api_key = fields.Char(
        string="API Key",
        groups="base.group_system",
        copy=False,
        help="Key used to authenticate against the provider's API.",
    )
    available_currency_ids = fields.Many2many(
        string="Available Currencies",
        comodel_name="res.currency",
        compute="_compute_available_currency_ids",
    )
    currency_ids = fields.Many2many(
        string="Currencies",
        comodel_name="res.currency",
        relation="syp_rate_provider_currency_rel",
        column1="provider_id",
        column2="currency_id",
        required=True,
        default=lambda self: self.env.ref("base.SYP", raise_if_not_found=False),
        help="Currencies to be updated by this provider",
    )
    price_side = fields.Selection(
        string="Price Side",
        selection=[("buy", "Buy"), ("sell", "Sell"), ("mid", "Mid (average)")],
        default="mid",
        required=True,
        help="Market price used for the Odoo rate. Buy and sell are stored on the rate anyway.",
    )
    scale = fields.Selection(
        string="Scale",
        selection=[("old", "Old Pound"), ("new", "New Pound (old ÷ 100)")],
        default="new",
        required=True,
        help="Syrian pound scale of the rates stored in Odoo. "
        "Prices are converted from the scale returned by the provider's API.",
    )
    interval_type = fields.Selection(
        string="Scheduled Update Interval Unit",
        selection=[("days", "Day(s)"), ("weeks", "Week(s)"), ("months", "Month(s)")],
        default="days",
        required=True,
    )
    interval_number = fields.Integer(
        string="Scheduled Update Interval", default=1, required=True
    )
    update_schedule = fields.Char(compute="_compute_update_schedule")
    last_successful_run = fields.Date(string="Last Successful Update")
    next_run = fields.Date(
        string="Next Scheduled Update", default=fields.Date.today, required=True
    )
    daily = fields.Boolean(compute="_compute_daily", store=True)

    _sql_constraints = [
        (
            "service_company_id_uniq",
            "UNIQUE(service, company_id)",
            "This provider has already been setup in this company.",
        ),
        (
            "valid_interval_number",
            "CHECK(interval_number > 0)",
            "Scheduled update interval must be strictly positive.",
        ),
    ]

    @api.depends("service")
    def _compute_name(self):
        services = dict(self._fields["service"].selection)
        for provider in self:
            provider.name = services.get(provider.service)

    @api.depends("active", "interval_type", "interval_number")
    def _compute_update_schedule(self):
        interval_types = dict(self._fields["interval_type"].selection)
        for provider in self:
            if not provider.active:
                provider.update_schedule = _("Inactive")
                continue
            provider.update_schedule = _("%(number)s %(type)s") % {
                "number": provider.interval_number,
                "type": interval_types.get(provider.interval_type),
            }

    @api.depends("service")
    def _compute_available_currency_ids(self):
        Currency = self.env["res.currency"]
        for provider in self:
            provider.available_currency_ids = Currency.search(
                [("name", "in", provider._get_supported_currencies())]
            )

    @api.depends("interval_type", "interval_number")
    def _compute_daily(self):
        for provider in self:
            provider.daily = provider.interval_type == "days" and provider.interval_number == 1

    def _update(self, date_from, date_to, newest_only=False):
        CurrencyRate = self.env["res.currency.rate"]
        is_scheduled = self.env.context.get("scheduled")
        for provider in self:
            try:
                data = provider._obtain_rates(
                    provider.company_id.currency_id.name,
                    provider.currency_ids.mapped("name"),
                    date_from,
                    date_to,
                )
            except Exception as e:
                _logger.warning(
                    'Syrian Rate Provider "%s" (company %s) failed to obtain data since %s until %s',
                    provider.name, provider.company_id.name, date_from, date_to,
                    exc_info=True,
                )
                # sudo: account managers only have read access on providers
                provider.sudo().message_post(
                    subject=_("Currency Rate Provider Failure"),
                    body=_(
                        'Currency Rate Provider "%(name)s" failed to obtain data'
                        " since %(date_from)s until %(date_to)s:\n%(error)s"
                    )
                    % {
                        "name": provider.name,
                        "date_from": date_from,
                        "date_to": date_to,
                        "error": str(e) or _("N/A"),
                    },
                )
                continue

            if not data:
                continue

            items = list(data.items())
            if newest_only:
                items = [max(items, key=lambda x: fields.Date.from_string(x[0]))]

            newest_date = False
            for content_date, quotes in items:
                timestamp = fields.Date.from_string(content_date)
                if not newest_date or timestamp > newest_date:
                    newest_date = timestamp
                for currency in provider.currency_ids:
                    if currency == provider.company_id.currency_id:
                        continue
                    vals = provider._process_rate(currency, quotes)
                    if not vals:
                        _logger.warning(
                            'Syrian Rate Provider "%s": no quote for %s/%s on %s, skipped',
                            provider.name, currency.name,
                            provider.company_id.currency_id.name, content_date,
                        )
                        continue
                    vals["syp_provider_id"] = provider.id
                    record = CurrencyRate.search(
                        [
                            ("company_id", "=", provider.company_id.id),
                            ("currency_id", "=", currency.id),
                            ("name", "=", timestamp),
                        ],
                        limit=1,
                    )
                    if record:
                        record.write(vals)
                    else:
                        CurrencyRate.create(
                            {
                                "company_id": provider.company_id.id,
                                "currency_id": currency.id,
                                "name": timestamp,
                                **vals,
                            }
                        )

            if is_scheduled and newest_date:
                provider._schedule_last_successful_run(newest_date)
                provider._schedule_next_run(newest_date)

    def _process_rate(self, currency, quotes):
        """Convert SYP-based quotes into Odoo rate values for `currency`.

        Odoo `rate` = units of `currency` per 1 unit of the company currency C.
        With q = SYP per 1 unit: rate(X) = q[C] / q[X]  (q[SYP] = 1), so:
          X = SYP -> q[C]       C = SYP -> 1 / q[X]
        """
        self.ensure_one()
        q_x = self._get_quote(currency, quotes)
        q_c = self._get_quote(self.company_id.currency_id, quotes)
        if not q_x or not q_c:
            return {}
        return {
            "rate": self._get_side_price(q_c) / self._get_side_price(q_x),
            "syp_buy_rate": q_c["buy"] / q_x["buy"],
            "syp_sell_rate": q_c["sell"] / q_x["sell"],
        }

    def _get_quote(self, currency, quotes):
        """SYP per 1 unit of `currency`, converted to the provider's target scale."""
        self.ensure_one()
        if currency.name == "SYP":
            return {"buy": 1.0, "sell": 1.0}
        quote = quotes.get(currency.name)
        if not quote or not quote.get("buy") or not quote.get("sell"):
            return None
        factor = self._get_scale_factor()
        return {"buy": quote["buy"] * factor, "sell": quote["sell"] * factor}

    def _get_scale_factor(self):
        self.ensure_one()
        source = self._get_source_scale()
        if source == self.scale:
            return 1.0
        return 0.01 if source == "old" else 100.0

    def _get_source_scale(self):
        """Scale ('old' or 'new') of the prices returned by the provider's API."""
        self.ensure_one()
        return "old"

    def _get_side_price(self, quote):
        self.ensure_one()
        if self.price_side == "buy":
            return quote["buy"]
        if self.price_side == "sell":
            return quote["sell"]
        return (quote["buy"] + quote["sell"]) / 2.0

    def _cached_fetch(self, key, fetch):
        """Run `fetch()` once per transaction for `key`; errors are cached too,
        so a failing service is not retried for every company (quota)."""
        cache = self.env.cr.cache.setdefault(FETCH_CACHE_KEY, {})
        if key not in cache:
            try:
                cache[key] = (True, fetch())
            except Exception as e:
                cache[key] = (False, e)
        ok, value = cache[key]
        if not ok:
            raise value
        return value

    def _schedule_last_successful_run(self, newest_date):
        self.last_successful_run = newest_date

    def _schedule_next_run(self, newest_date):
        self.ensure_one()
        self.next_run = (
            datetime.combine(newest_date, time.min) + self._get_next_run_period()
        ).date()

    def _get_next_run_period(self):
        self.ensure_one()
        if self.interval_type == "days":
            return relativedelta(days=self.interval_number)
        elif self.interval_type == "weeks":
            return relativedelta(weeks=self.interval_number)
        elif self.interval_type == "months":
            return relativedelta(months=self.interval_number)

    @api.model
    def _scheduled_update(self):
        _logger.info("Scheduled Syrian currency rates update...")
        today = fields.Date.context_today(self)
        providers = self.search(
            [
                ("active", "=", True),
                "|",
                ("next_run", "<=", today),
                ("daily", "=", True),
            ]
        )
        for provider in providers.with_context(scheduled=True):
            date_from = (
                (provider.last_successful_run + relativedelta(days=1))
                if provider.last_successful_run
                else (provider.next_run - provider._get_next_run_period())
            )
            newest_only = True
            date_to = provider.next_run
            if provider.daily:
                newest_only = False
                date_to = today
            provider._update(date_from, date_to, newest_only=newest_only)
        _logger.info("Scheduled Syrian currency rates update complete.")

    def _get_supported_currencies(self):
        # pragma: no cover
        self.ensure_one()
        return []

    def _obtain_rates(self, base_currency, currencies, date_from, date_to):
        # pragma: no cover
        self.ensure_one()
        return {}
