"""scripts/deploy_plugin.py sends a rescan again only while the shell says it is busy."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy_plugin", ROOT / "scripts" / "deploy_plugin.py")
deploy_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy_plugin)

BUSY = subprocess.CalledProcessError(1, ["ssh"], output=b"", stderr=b"omarchy-shell is not responding\n")
OTHER = subprocess.CalledProcessError(1, ["ssh"], output=b"", stderr=b"Function not found.\n")


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RetryNotResponding(unittest.TestCase):
    def run_with(self, outcomes, deadline=20.0):
        clock, calls = Clock(), []

        def call():
            calls.append(clock.now)
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        result = deploy_plugin.retry_not_responding(call, deadline=deadline, clock=clock, sleep=clock.sleep)
        return result, calls

    def test_a_busy_shell_is_asked_again_until_it_answers(self):
        result, calls = self.run_with([BUSY, BUSY, "ok"])
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_any_other_failure_ends_the_deploy_at_once(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_with([OTHER, "ok"])
        self.assertIs(caught.exception, OTHER)

    def test_the_busy_answer_after_the_deadline_ends_the_deploy(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_with([BUSY] * 100, deadline=2.0)
        self.assertIs(caught.exception, BUSY)


if __name__ == "__main__":
    unittest.main()
