# -*- coding: utf-8 -*-

from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from .common import SptCommon


@tagged("post_install", "-at_install")
class TestScheduler(SptCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # providers from the database data must not change the call count
        cls.env["syp.rate.provider"].search(
            [("id", "not in", (cls.provider_a | cls.provider_b).ids)]
        ).active = False

    def _run_cron(self):
        self.clear_fetch_cache()
        with self.mock_get() as get:
            self.env["syp.rate.provider"]._scheduled_update()
        return get

    @freeze_time("2026-01-17 12:00:00")
    def test_daily_provider(self):
        self.provider_b.active = False
        self.provider_a.next_run = date(2026, 1, 17)
        get = self._run_cron()
        self.assertEqual(get.call_count, 1)
        self.assertTrue(self._rate(self.company_a))
        self.assertEqual(self.provider_a.last_successful_run, date(2026, 1, 17))
        self.assertEqual(self.provider_a.next_run, date(2026, 1, 18))

    @freeze_time("2026-01-17 12:00:00")
    def test_daily_provider_runs_even_if_next_run_in_future(self):
        self.provider_b.active = False
        self.provider_a.next_run = date(2026, 2, 1)
        self.assertEqual(self._run_cron().call_count, 1)

    def test_weekly_provider_due_only_on_next_run(self):
        self.provider_b.active = False
        self.provider_a.write({"interval_type": "weeks", "next_run": date(2026, 1, 17)})
        with freeze_time("2026-01-16 12:00:00"):
            self.assertEqual(self._run_cron().call_count, 0)
            self.assertFalse(self.provider_a.last_successful_run)
        with freeze_time("2026-01-17 12:00:00"):
            self.assertEqual(self._run_cron().call_count, 1)
        self.assertEqual(self.provider_a.last_successful_run, date(2026, 1, 17))
        self.assertEqual(self.provider_a.next_run, date(2026, 1, 24))

    @freeze_time("2026-01-17 12:00:00")
    def test_archived_provider_never_runs(self):
        (self.provider_a | self.provider_b).active = False
        self.assertEqual(self._run_cron().call_count, 0)
        self.assertFalse(self._rate(self.company_a))

    @freeze_time("2026-01-17 12:00:00")
    def test_all_companies_one_call(self):
        self.assertEqual(self._run_cron().call_count, 1)
        self.assertTrue(self._rate(self.company_a))
        self.assertTrue(self._rate(self.company_b))

    def test_cron_record(self):
        cron = self.env.ref("spt.ir_cron_syp_rate_daily")
        self.assertTrue(cron.active)
        self.assertEqual(cron.model_id.model, "syp.rate.provider")
        self.assertEqual(cron.code.strip(), "model._scheduled_update()")
        self.assertEqual((cron.interval_number, cron.interval_type), (1, "days"))

    @freeze_time("2026-01-17 12:00:00")
    def test_cron_trigger(self):
        self.clear_fetch_cache()
        with self.mock_get() as get:
            self.env.ref("spt.ir_cron_syp_rate_daily").method_direct_trigger()
        self.assertEqual(get.call_count, 1)
        self.assertTrue(self._rate(self.company_a))
