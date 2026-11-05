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
            "subject": "Vanderbilt freshman interested in private equity", "body": f"Hi {name.split()[0]},"}


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
                    "--scheduled-for", "2026-11-11 12:00 ET")
        self.assertIn("Nothing approved", self.run_ok("next"))

    def test_unclear_is_not_retried_without_a_note(self):
        self.run_ok("approve", "--verified")
        self.run_ok("mark", "--email", "ana@example.com", "--status", "unclear")
        self.assertIn("Nothing approved", self.run_ok("next"))
        self.run_bad("mark", "--email", "ana@example.com", "--status", "approved")
        self.run_ok("mark", "--email", "ana@example.com", "--status", "approved", "--note", "Unscheduled in Drafts")
        self.assertIn("ana@example.com", self.run_ok("next"))

    def test_sheet_rows_only_new_after_marking(self):
        rows_path = os.path.join(self.dir.name, "rows.json")
        self.run_ok("sheet-rows", "--new-only", "--out", rows_path)
        with open(rows_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["rows"]), 3)
        self.assertEqual(len(data["rows"][0]), len(data["columns"]))
        self.assertEqual(data["rows"][0][-1], "Needs approval")
        self.run_ok("mark-sheet")
        self.run_ok("sheet-rows", "--new-only", "--out", rows_path)
        with open(rows_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["rows"], [])


if __name__ == "__main__":
    unittest.main()
