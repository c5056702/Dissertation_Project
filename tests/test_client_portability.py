import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from run_live import live_environment, resolve_webots
from setup_client import verify_manifest
import run_live
import check_live_inputs


class ClientPortabilityTests(unittest.TestCase):
    def test_live_cannot_inherit_replay_or_fault_injection(self):
        env = live_environment({"PATH": "keep", "EPUCK_SCENARIO_FILE": "auto.json", "epuck_transcript_replay": "voice.json", "EPUCK_FORCE_CONTROLLER_FAILURE": "1", "PYTHONHOME": "other", "MICROPHONE_DEVICE": "old"})
        self.assertEqual(env, {"PATH": "keep"})

    def test_explicit_missing_webots_does_not_silently_select_another(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(resolve_webots(str(Path(folder) / "missing.exe")))

    def test_manifest_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "SHA256SUMS.txt").write_text("0" * 64 + "  ../outside.txt\n")
            with self.assertRaisesRegex(ValueError, "Unsafe manifest"):
                verify_manifest(root)

    def test_cancelled_preflight_never_launches_webots(self):
        for require_ready in (False, True):
            for outcome in (130, -2, 0xC000013A, -1073741510, KeyboardInterrupt()):
                with self.subTest(require_ready=require_ready, outcome=outcome):
                    with tempfile.TemporaryDirectory() as folder:
                        root = Path(folder)
                        python = root / ".venv" / "Scripts" / "python.exe"
                        python.parent.mkdir(parents=True)
                        python.touch()
                        (root / "models" / "vosk-model-small-en-us-0.15").mkdir(parents=True)
                        argv = ["run_live.py", "--microphone", "1"]
                        if require_ready:
                            argv.append("--require-ready")
                        stderr = io.StringIO()
                        with (
                            mock.patch.object(run_live, "PROJECT", root),
                            mock.patch.object(run_live, "resolve_webots", return_value=root / "webots.exe"),
                            mock.patch.object(sys, "argv", argv),
                            mock.patch.object(run_live.subprocess, "run") as preflight,
                            mock.patch.object(run_live.subprocess, "call") as launch,
                            contextlib.redirect_stdout(io.StringIO()),
                            contextlib.redirect_stderr(stderr),
                        ):
                            if isinstance(outcome, KeyboardInterrupt):
                                preflight.side_effect = outcome
                            else:
                                preflight.return_value.returncode = outcome
                            self.assertEqual(run_live.main(), 130)
                        launch.assert_not_called()
                        self.assertIn("Webots was not started", stderr.getvalue())

    def test_preflight_cancellation_writes_report_and_releases_open_inputs(self):
        for during_initialization in (False, True):
            with self.subTest(during_initialization=during_initialization):
                with tempfile.TemporaryDirectory() as folder:
                    output = Path(folder) / "devices.json"
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with (
                        mock.patch.object(sys, "argv", ["check_live_inputs.py", "--output", str(output)]),
                        mock.patch("input_adapters.LocalMultimodalInput") as create_inputs,
                        contextlib.redirect_stdout(stdout),
                        contextlib.redirect_stderr(stderr),
                    ):
                        inputs = create_inputs.return_value
                        inputs.ready = False
                        if during_initialization:
                            create_inputs.side_effect = KeyboardInterrupt
                        else:
                            inputs.poll.side_effect = KeyboardInterrupt
                        self.assertEqual(check_live_inputs.main(), 130)
                    report = json.loads(output.read_text(encoding="utf-8"))
                    self.assertTrue(report["cancelled"])
                    self.assertFalse(report["ready"])
                    self.assertFalse(report["media_saved"])
                    self.assertEqual(json.loads(stdout.getvalue()), report)
                    self.assertIn("Cancelled by keyboard interrupt", stderr.getvalue())
                    if not during_initialization:
                        inputs.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
