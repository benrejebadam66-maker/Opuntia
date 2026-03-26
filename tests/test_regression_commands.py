import os
import tempfile
import unittest
from unittest.mock import patch

from windows_agent import WindowsAgent


def _make_agent(tmp_root):
    agent = WindowsAgent.__new__(WindowsAgent)
    agent.workspace_root = os.path.join(tmp_root, "workspace")
    agent.desktop_root = os.path.join(tmp_root, "desktop")
    agent.audit_log_file = os.path.join(tmp_root, "logs", "security_audit.jsonl")
    agent.prompt_training_file = os.path.join(tmp_root, "prompt_training.json")
    agent.memory_file = os.path.join(tmp_root, "memory", "conversation_memory.json")
    agent.allowed_subprocess_bins = {"netsh", "powershell", "taskkill", "explorer.exe"}
    agent.allowed_launch_bins = {"notepad.exe", "cmd.exe", "powershell.exe", "explorer.exe", "chrome.exe", "msedge.exe", "brave.exe"}

    # Runtime/model config defaults for offline tests.
    agent.groq_api_key = ""
    agent.deepseek_api_key = ""
    agent.qwen_api_key = ""
    agent.gemini_api_key = ""
    agent.ai_provider = "auto"
    agent.groq_model = "llama-3.3-70b-versatile"
    agent.groq_fallback_models = []
    agent.deepseek_model = "deepseek-chat"
    agent.deepseek_fallback_models = []
    agent.qwen_model = "qwen-plus"
    agent.qwen_fallback_models = []
    agent.gemini_model = "gemini-1.5-flash"
    agent.gemini_fallback_models = []
    agent.qwen_base_url = "https://example.invalid"
    agent.client = None
    agent.response_temperature = 0.25
    agent.response_top_p = 0.9
    agent.response_max_tokens = 240
    agent.ai_request_timeout = 10
    agent.ai_max_retries = 0
    agent.ai_cache_ttl_sec = 20

    # Mutable runtime state used by process_command.
    agent._screen_summary_cache = {}
    agent._ai_response_cache = {}
    agent.pending_confirmation = None
    agent.pending_plan_execution = None
    agent.last_screen_action_plan = None
    agent.last_ai_runtime = {"provider": "local", "model": "rules", "status": "idle", "error": ""}
    agent.last_status_app = None
    agent.last_apps_check = None
    agent.last_apps_list = []
    agent.app_launch_index = {}
    agent.app_index_last_build = 0
    agent.start_apps_index = {}
    agent.start_apps_last_build = 0
    agent.conversation_history = []
    agent.max_memory_items = 20
    agent.prompt_examples = []

    os.makedirs(agent.workspace_root, exist_ok=True)
    os.makedirs(agent.desktop_root, exist_ok=True)
    return agent


class RegressionCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = _make_agent(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_greeting_does_not_trigger_inventory(self):
        reply = self.agent.process_command("hello")
        self.assertEqual(reply, "Hello. How can I help?")

    def test_spoken_typo_normalization(self):
        normalized = self.agent._normalize_spoken_typos("open power shell and insta gram")
        self.assertIn("powershell", normalized.lower())
        self.assertIn("instagram", normalized.lower())

    def test_extract_multilingual_search_intent(self):
        query, app = self.agent._extract_search_intent("recherche instagram sur brave")
        self.assertEqual(query, "instagram")
        self.assertEqual(app, "brave")

    def test_open_typo_asks_confirmation(self):
        with patch.object(WindowsAgent, "open_app", return_value=None):
            reply = self.agent.process_command("open vscde")
        self.assertIn("yes/no", reply.lower())
        self.assertIn("do you want me to open", reply.lower())
        self.assertIsNotNone(self.agent.pending_confirmation)

    def test_confirmation_yes_executes_pending_action(self):
        self.agent.pending_confirmation = {"action": "open_app", "payload": {"target": "vs code"}}
        with patch.object(WindowsAgent, "open_app", return_value="Opened VS Code"):
            reply = self.agent.process_command("yes")
        self.assertEqual(reply, "Opened VS Code")
        self.assertIsNone(self.agent.pending_confirmation)

    def test_confirmation_no_cancels_pending_action(self):
        self.agent.pending_confirmation = {"action": "open_app", "payload": {"target": "vs code"}}
        reply = self.agent.process_command("no")
        self.assertEqual(reply, "Cancelled.")
        self.assertIsNone(self.agent.pending_confirmation)

    def test_unclear_search_target_requests_confirmation(self):
        reply = self.agent.process_command("search instagram on brve")
        self.assertIn("default browser", reply.lower())
        self.assertIn("yes/no", reply.lower())
        self.assertIsNotNone(self.agent.pending_confirmation)

    def test_execute_plan_without_plan(self):
        reply = self.agent.process_command("execute plan")
        self.assertIn("no executable screen action plan", reply.lower())

    def test_execute_plan_with_confirmation_cycle(self):
        self.agent.last_screen_action_plan = {
            "actions": [
                {"step": 1, "action": "wait", "value": "0"},
                {"step": 2, "action": "hotkey", "value": "ctrl,l"},
            ]
        }
        first = self.agent.process_command("start plan")
        self.assertIn("step 1/2", first.lower())
        self.assertIsNotNone(self.agent.pending_confirmation)

        with patch("windows_agent.pyautogui.hotkey") as hotkey_mock:
            second = self.agent.process_command("yes")
            self.assertIn("done: waited", second.lower())
            self.assertIn("step 2/2", second.lower())
            final = self.agent.process_command("yes")
            self.assertIn("done: hotkey", final.lower())
            self.assertIn("plan execution completed", final.lower())
            hotkey_mock.assert_called_once_with("ctrl", "l")

    def test_click_step_resolves_from_step_bbox(self):
        self.agent.last_screen_action_plan = {
            "actions": [
                {"step": 1, "action": "click", "target": "Search box", "bbox": [100, 200, 50, 20]}
            ]
        }
        _ = self.agent.process_command("execute plan")
        with patch("windows_agent.pyautogui.click") as click_mock:
            reply = self.agent.process_command("yes")
            self.assertIn("done: click", reply.lower())
            click_mock.assert_called_once()

    def test_click_step_resolves_from_targets_meta(self):
        self.agent.last_screen_action_plan = {
            "targets_meta": [
                {"label": "Search box", "bbox": [300, 400, 80, 24], "confidence": 0.9}
            ],
            "actions": [
                {"step": 1, "action": "click", "target": "search box"}
            ],
        }
        _ = self.agent.process_command("run plan")
        with patch("windows_agent.pyautogui.click") as click_mock:
            reply = self.agent.process_command("yes")
            self.assertIn("done: click", reply.lower())
            click_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
