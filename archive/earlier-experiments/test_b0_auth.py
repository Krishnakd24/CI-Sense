"""Offline auth recovery tests: no notebook, browser, CLI or model execution."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import b0_runner as runner


class AuthRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / "b0_data_v1.json").write_text(json.dumps([
            {"id": "1", "test_code": "first"}, {"id": "2", "test_code": "second"}]))
        (self.base / "prompt_b0.txt").write_text("Role: Expert Software Engineer.\n{{TEST_CODE}}")

    def response(self, error=None):
        class Response:
            returncode = 0
            stderr = ""
        r = Response()
        payload = {"status": "ERROR", "error": error} if error else {
            "status": "SUCCESS", "structured_output": {"flaky_probability": 0.7}}
        r.stdout = json.dumps({"event": "result", "result": payload})
        return r

    def run_experiment(self):
        return runner.run_predictions(self.base, None, cli=sys.executable)

    def test_credit_error_retries_pending_row(self):
        with patch.object(runner, "interactive_login", return_value=True) as login, patch.object(
            runner.subprocess, "run", side_effect=[self.response(), self.response("Insufficient credits"), self.response()]
        ) as calls:
            folder = self.run_experiment()
            self.assertEqual(calls.call_count, 3)
            self.assertEqual(login.call_count, 2)
            self.assertEqual(calls.call_args_list[1].kwargs["input"], calls.call_args_list[2].kwargs["input"])
        records = [json.loads(line) for line in (folder / "predictions.jsonl").read_text().splitlines()]
        self.assertEqual([r["status"] for r in records], ["success", "blocked", "success"])
        self.assertNotEqual(records[0]["auth_session"], records[2]["auth_session"])
        with patch.object(runner.subprocess, "run") as calls, patch.object(runner, "interactive_login") as login:
            self.run_experiment()
            calls.assert_not_called()
            login.assert_not_called()

    def test_stop_saves_failure_and_later_resumes(self):
        with patch.object(runner, "interactive_login", side_effect=[True, False]), patch.object(
            runner.subprocess, "run", return_value=self.response("authentication failed")
        ):
            folder = self.run_experiment()
        self.assertEqual(len((folder / "predictions.jsonl").read_text().splitlines()), 1)
        with patch.object(runner, "interactive_login", return_value=True), patch.object(
            runner.subprocess, "run", return_value=self.response()
        ) as calls:
            self.run_experiment()
            self.assertEqual(calls.call_count, 2)

    def test_initial_stop_makes_no_requests(self):
        with patch.object(runner, "interactive_login", return_value=False), patch.object(runner.subprocess, "run") as calls:
            self.run_experiment()
            calls.assert_not_called()

    def test_visible_login_menu(self):
        with patch("builtins.input", side_effect=["login", "ready"]), patch.object(runner.subprocess, "Popen") as launch:
            self.assertTrue(runner.interactive_login(sys.executable, "Sign in"))
            if sys.platform == "win32":
                self.assertEqual(launch.call_args.kwargs["creationflags"], runner.subprocess.CREATE_NEW_CONSOLE)
                self.assertIsNone(launch.call_args.kwargs["stdin"])

    def test_original_manifest_migration_preserves_config_guard(self):
        with patch.object(runner, "interactive_login", return_value=False):
            folder = self.run_experiment()
        manifest = folder / "manifest.json"
        old = json.loads(manifest.read_text())
        old["runner_sha256"] = runner.PRE_AUTH_FIX_SHA256
        manifest.write_text(json.dumps(old))
        with patch.object(runner, "interactive_login", return_value=False):
            self.run_experiment()
        self.assertEqual(json.loads((folder / "manifest_before_auth_fix.json").read_text()), old)
        old["model"] = "other model"
        manifest.write_text(json.dumps(old))
        with self.assertRaises(ValueError):
            self.run_experiment()


if __name__ == "__main__":
    unittest.main()
