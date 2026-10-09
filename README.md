# Odoo-SPT

 Odoo API integration that keeps **Syrian Pound (SYP)** exchange rates up to date from Syrian
 market rate providers. The supported provider in this module is **[SP Today](https://sp-today.com)**,
 and the design is extensible to other sources.

 ## Features
 - Fetches SYP market rates from the SP Today API (Damascus, Aleppo or Homs)
 - One rate provider per company (multi-company safe)
 - Choice of price side: **Buy**, **Sell** or **Mid (average)**. Buy and sell are stored on the rate as well.
 - Old / new Syrian pound scale (new = old ÷ 100), converted automatically
 - Scheduled updates at a configurable interval (days / weeks / months)
 - Manual update: an **Update Rates Now** button, plus a wizard for a date range
 - Shows the remaining API quota (monthly limit, remaining requests, reset date)
 - Coexists with other currency rate providers without conflicts

 ## Requirements
 - Odoo (one branch per version, e.g. `18.0`)
 - Odoo modules: `account`, `mail`
 - Python: `requests`, `pytz`
 - An SP Today API key

 ## Installation
 1. Clone the branch that matches your Odoo version into your addons path:
    `git clone -b 18.0 https://github.com/yakhras/Odoo-SPT.git`
 2. Restart Odoo, update the apps list, and install **SPT**.

 ## Configuration
 1. Go to **Accounting → Configuration → Syrian Rate Providers** and create a provider.
 2. Set the service (**SP Today**), the city, the API key (administrators only), the price side, the scale and the update interval.
 3. Save. Rates are then updated by the scheduled action, or right away with **Update Rates Now**.

 ## Usage
 - Rates appear in **Accounting → Configuration → Currencies → SYP → Rates**.
 - SP Today serves a live snapshot only. Each update stores the latest market rate, dated by the provider's last update time in Damascus.
   Past dates cannot be backfilled

 ## Author
 Yaser Akhras ([yaserakhras.com](https://yaserakhras.com))

 ## License
 LGPL-3. See [LICENSE](LICENSE).
