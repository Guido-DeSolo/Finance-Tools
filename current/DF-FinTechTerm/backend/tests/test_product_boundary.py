import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend_cli import ACTIONS, SERVICES, catalog_payload
from fintech_core import ExecutionMode, RuntimeConfig


class RuntimeBoundaryTests(unittest.TestCase):
    def test_missing_mode_defaults_to_backtest(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(RuntimeConfig.from_env().mode, ExecutionMode.BACKTEST)

    def test_live_mode_requires_exact_second_acknowledgement(self):
        config = RuntimeConfig(ExecutionMode.LIVE)
        with self.assertRaises(RuntimeError):
            config.require_live_acknowledgement(None)
        config.require_live_acknowledgement("LIVE")

    def test_catalog_keeps_services_and_actions_disjoint(self):
        self.assertFalse(set(SERVICES) & set(ACTIONS))
        self.assertTrue(all(item.writes_database for item in SERVICES.values()))
        self.assertFalse(ACTIONS["insider-backtest"].writes_database)
        self.assertEqual(set(ACTIONS), {
            "candidate-packets", "daily-research", "insider-backtest", "benchmark-quant-v2",
        })

    def test_catalog_is_machine_readable_and_safe_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            payload = catalog_payload()
        self.assertEqual(payload["execution_mode"], "backtest")
        self.assertEqual(len(payload["services"]), len(SERVICES))
        json.dumps(payload)

    def test_cli_lists_both_surfaces(self):
        services = subprocess.run(
            [sys.executable, str(ROOT / "backend_cli.py"), "services"],
            check=True, capture_output=True, text=True,
        )
        actions = subprocess.run(
            [sys.executable, str(ROOT / "backend_cli.py"), "actions"],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("BACKGROUND / SCHEDULED SERVICES", services.stdout)
        self.assertIn("USER ACTIONS", actions.stdout)


if __name__ == "__main__":
    unittest.main()
