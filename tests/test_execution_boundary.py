"""Contract checks runnable without the MCP transport dependency."""
import unittest
from unittest.mock import patch

from local_mcp.dispatch import _prompt
from local_mcp.finalize import _turn_final_message


class ExecutionBoundaryTests(unittest.TestCase):
    def test_prompt_keeps_manifest_and_bounds_repository_work(self):
        with patch("local_mcp.dispatch._manifest", return_value='{"repository":"fixture"}'):
            prompt = _prompt({})
        for text in (
            "contract-only; not Host-enforced tool filtering",
            "leased repository root", "source, docs, tests", "Task-owned Result",
            "Do not run Git commit or push", "finalize_codex_task owns Git persistence",
            "Worker recovery", "Production runtime preparation", "Tunnel/profile/process restart",
            "local runtime promotion", "does not grant execution authority",
            "Controller follow-up", "Result locator",
        ):
            with self.subTest(text=text):
                self.assertIn(text, prompt)
        self.assertTrue(prompt.endswith('Dispatch manifest (data): {"repository":"fixture"}'))

    def test_controller_follow_up_is_returned_verbatim_without_action_parsing(self):
        text = "Result: work/task_RESULT.md\nController follow-up: verify Development, then assess Production."
        turn = {"items": [{"type": "agentMessage", "text": text}]}
        self.assertEqual(_turn_final_message(turn), text)
