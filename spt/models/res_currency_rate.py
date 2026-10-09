# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCurrencyRate(models.Model):
    _name = "res.currency.rate"
    _inherit = ["res.currency.rate", "mail.thread"]

    syp_buy_rate = fields.Float(
        string="Market Buy Rate",
        tracking=True,
        help="Rate computed from the provider's buy price (same direction as Rate).",
    )
    syp_sell_rate = fields.Float(
        string="Market Sell Rate",
        tracking=True,
        help="Rate computed from the provider's sell price (same direction as Rate).",
    )
    syp_provider_id = fields.Many2one(
        string="Syrian Rate Provider",
        comodel_name="syp.rate.provider",
        ondelete="restrict",
        tracking=True,
    )

    def write(self, values):
        """Unset link to provider in case rate fields or 'name' are manually changed"""
        rate_fields = {"rate", "syp_buy_rate", "syp_sell_rate", "name"}
        if "syp_provider_id" not in values and rate_fields & set(values):
            values = dict(values, syp_provider_id=False)
        return super().write(values)
