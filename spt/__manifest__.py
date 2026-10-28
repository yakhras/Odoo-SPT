# -*- coding: utf-8 -*-

{
    "name": "SPT",
    "version": "20.0.1.0.0",
    "author": "Yaser Akhras",
    "maintainers": ["yakhras"],
    "website": "https://yaserakhras.com",
    "license": "LGPL-3",
    "category": "Financial Management/Configuration",
    "summary": "Update SYP exchange rates from Syrian market providers (SP Today, ...)",
    "depends": ["account", "mail"],
    "external_dependencies": {"python": ["requests", "pytz"]},
    "data": [
        "data/ir_cron_data.xml",
        "security/ir.access.csv",
        "wizards/syp_rate_update_wizard.xml",
        "views/syp_rate_provider_views.xml",
        "views/res_currency_rate_views.xml",
    ],
    "installable": True,
}
