# -*- coding: utf-8 -*-

from odoo import Command, api, fields, models


class SypRateUpdateWizard(models.TransientModel):
    _name = "syp.rate.update.wizard"
    _description = "Syrian Currency Rate Update Wizard"

    date_from = fields.Date(
        string="Start Date", required=True, default=fields.Date.context_today
    )
    date_to = fields.Date(
        string="End Date", required=True, default=fields.Date.context_today
    )
    provider_ids = fields.Many2many(
        string="Providers",
        comodel_name="syp.rate.provider",
        relation="syp_rate_update_wizard_provider_rel",
        column1="wizard_id",
        column2="provider_id",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get("active_model") == "syp.rate.provider" and self._context.get("active_ids"):
            res["provider_ids"] = [Command.set(self._context["active_ids"])]
        return res

    def action_update(self):
        self.ensure_one()
        self.provider_ids._update(self.date_from, self.date_to)
        return {"type": "ir.actions.act_window_close"}
