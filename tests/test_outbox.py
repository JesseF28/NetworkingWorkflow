"""Run from the repo root: python -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTBOX = os.path.join(ROOT, "scripts", "outbox.py")


def person(name, email, confidence):
    return {"name": name, "firm": "Example Capital", "email": email, "email_confidence": confidence,
            "subject": "Vanderbilt freshman interested in private equity",
            "body": f"Hi {name.split()[0]},\n\nHook.\n\nWould you be open to a call? Old times.\n\nBest,\nJesse Fagen"}


class OutboxTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.box = os.path.join(self.dir.name, "outbox.json")
        self.prospects = os.path.join(self.dir.name, "p.json")
        with open(self.prospects, "w", encoding="utf-8") as f:
            json.dump([person("Ana Verified", "ana@example.com", "Verified (PitchBook)"),
                       person("Ben Pattern", "ben@example.com", "Pattern-matched (based on x@example.com)"),
                       person("Cy Guessed", "cy@example.com", "Guessed")], f)
        self.run_ok("add", "--prospects", self.prospects, "--run-date", "2026-11-10")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", OUTBOX, "--outbox", self.box, *args],
                              capture_output=True, text=True, encoding="utf-8")

    def run_ok(self, *args):
        r = self.run_cli(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def run_bad(self, *args):
        r = self.run_cli(*args)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        return r.stdout

    def status(self, email):
        with open(self.box, encoding="utf-8") as f:
            return next(i for i in json.load(f) if i["email"] == email)["status"]

    def test_adding_twice_does_not_duplicate(self):
        self.assertIn("0 added", self.run_ok("add", "--prospects", self.prospects))

    def test_nothing_is_offered_before_approval(self):
        self.assertIn("Nothing approved", self.run_ok("next"))

    def test_cannot_schedule_without_approval(self):
        out = self.run_bad("mark", "--email", "ana@example.com", "--status", "scheduled", "--scheduled-for", "x")
        self.assertIn("approve", out)
        self.assertEqual(self.status("ana@example.com"), "needs_approval")

    def test_verified_only_leaves_the_rest_waiting(self):
        self.run_ok("approve", "--verified")
        self.assertEqual(self.status("ana@example.com"), "approved")
        self.assertEqual(self.status("cy@example.com"), "needs_approval")

    def test_approve_all_warns_about_unverified(self):
        out = self.run_ok("approve", "--all")
        self.assertIn("Ben Pattern", out.split("may bounce")[1])
        self.assertIn("Cy Guessed", out.split("may bounce")[1])

    def test_approve_by_name_and_ambiguous_name(self):
        self.run_ok("approve", "--names", "cy guessed")
        self.assertEqual(self.status("cy@example.com"), "approved")
        self.run_bad("approve", "--names", "e")  # matches both remaining people
        self.assertEqual(self.status("ana@example.com"), "needs_approval")

    def test_scheduled_needs_the_time_outlook_showed(self):
        self.run_ok("approve", "--verified")
        self.run_bad("mark", "--email", "ana@example.com", "--status", "scheduled")
        self.run_ok("mark", "--email", "ana@example.com", "--status", "scheduled",
                    "--scheduled-for", "2026-11-12 13:00 ET")
        self.assertIn("Nothing approved", self.run_ok("next"))

    def body(self, email):
        with open(self.box, encoding="utf-8") as f:
            return next(i for i in json.load(f) if i["email"] == email)["body"]

    def test_next_waits_for_confirmed_availability(self):
        self.run_ok("approve", "--verified")
        out = self.run_bad("next")
        self.assertIn("available", out)
        self.run_ok("availability", "--keep")
        self.assertIn("ana@example.com", self.run_ok("next"))

    def test_new_availability_replaces_only_that_paragraph(self):
        self.run_ok("approve", "--all")
        new = "Would you be open to a 15-20 minute call next week? I'm free Monday 3-5 PM EST."
        self.run_ok("availability", "--text", new)
        body = self.body("ben@example.com")
        self.assertIn(new, body)
        self.assertNotIn("Old times", body)
        self.assertTrue(body.startswith("Hi Ben,\n\nHook.\n\n") and body.endswith("Best,\nJesse Fagen"))

    def test_availability_must_look_like_the_template_line(self):
        self.run_bad("availability", "--text", "Mondays work")
        self.assertIn("Old times", self.body("ana@example.com"))

    def test_unclear_is_not_retried_without_a_note(self):
        self.run_ok("approve", "--verified")
        self.run_ok("availability", "--keep")
        self.run_ok("mark", "--email", "ana@example.com", "--status", "unclear")
        self.assertIn("Nothing approved", self.run_ok("next"))
        self.run_bad("mark", "--email", "ana@example.com", "--status", "approved")
        self.run_ok("mark", "--email", "ana@example.com", "--status", "approved", "--note", "Unscheduled in Drafts")
        self.assertIn("ana@example.com", self.run_ok("next"))

    def test_send_slot_is_the_next_thursday_at_1pm_eastern(self):
        cases = {
            "2026-11-10T10:00": "2026-11-12 13:00 ET",  # Tuesday run
            "2026-11-12T09:00": "2026-11-12 13:00 ET",  # Thursday morning, enough time
            "2026-11-12T11:30": "2026-11-19 13:00 ET",  # Thursday, too close to finish a batch
            "2026-11-12T15:00": "2026-11-19 13:00 ET",  # Thursday, already passed
            "2026-11-13T08:00": "2026-11-19 13:00 ET",  # Friday
            "2026-07-14T10:00": "2026-07-16 13:00 ET",  # summer, daylight time
        }
        for now, want in cases.items():
            self.assertIn(f"For outbox.py mark: {want}", self.run_ok("when", "--now", now), now)

    def test_send_slot_shows_central_time(self):
        out = self.run_ok("when", "--now", "2026-11-10T10:00")
        self.assertIn("Thursday, November 12, 2026, 1:00 PM Eastern", out)
        self.assertIn("In Central time: 12:00 PM", out)

    def test_sheet_rows_only_new_after_marking(self):
        rows_path = os.path.join(self.dir.name, "rows.json")
        self.run_ok("sheet-rows", "--new-only", "--out", rows_path)
        with open(rows_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["rows"]), 3)
        self.assertEqual(len(data["rows"][0]), len(data["columns"]))
        self.assertEqual(data["rows"][0][2], "Draft saved")
        self.run_ok("mark-sheet")
        self.run_ok("sheet-rows", "--new-only", "--out", rows_path)
        with open(rows_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["rows"], [])


    def test_sheet_columns_match_what_the_sunday_sync_requires(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import outbox
        import sent_sync
        self.assertEqual(outbox.SHEET_COLUMNS, sent_sync.COLUMNS)

    def test_every_sheet_stage_is_one_the_sunday_sync_knows(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import outbox
        import sent_sync
        self.assertLessEqual(set(outbox.SHEET_STAGE.values()), set(sent_sync.RANK))
        self.assertEqual(set(outbox.SHEET_STAGE), set(outbox.MOVES))

    def test_scheduled_row_shows_stage_and_target_date_as_text(self):
        self.run_ok("approve", "--verified")
        self.run_ok("mark", "--email", "ana@example.com", "--status", "scheduled",
                    "--scheduled-for", "2026-11-12 13:00 ET")
        rows_path = os.path.join(self.dir.name, "rows.json")
        self.run_ok("sheet-rows", "--out", rows_path)
        with open(rows_path, encoding="utf-8") as f:
            row = json.load(f)["rows"][0]
        self.assertEqual(row[2], "Scheduled — confirm sent")
        self.assertEqual(row[10], "'Nov 12, 2026")


if __name__ == "__main__":
    unittest.main()
