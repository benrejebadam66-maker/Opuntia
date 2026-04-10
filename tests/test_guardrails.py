import json
import os
import tempfile
import unittest
from types import SimpleNamespace
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
    agent.allowed_launch_bins = {"notepad.exe", "cmd.exe", "powershell.exe", "explorer.exe", "chrome.exe"}
    agent._screen_summary_cache = {}
    agent._ai_response_cache = {}
    agent.last_status_app = None
    agent.app_launch_index = {}
    agent.app_index_last_build = 0
    agent.start_apps_index = {}
    agent.start_apps_last_build = 0
    agent.last_apps_check = None
    agent.last_apps_list = []
    agent.pending_confirmation = None
    agent.last_ai_runtime = {"provider": "local", "model": "rules", "status": "idle", "error": ""}
    agent.ai_cache_ttl_sec = 20
    agent.ai_provider = "auto"
    agent.groq_api_key = ""
    agent.deepseek_api_key = ""
    agent.qwen_api_key = ""
    agent.gemini_api_key = ""
    agent.groq_model = "dummy"
    agent.groq_fallback_models = []
    agent.deepseek_model = "dummy"
    agent.deepseek_fallback_models = []
    agent.qwen_model = "dummy"
    agent.qwen_fallback_models = []
    agent.gemini_model = "dummy"
    agent.gemini_fallback_models = []
    agent.qwen_base_url = "https://example.invalid"
    agent.client = None
    agent.response_temperature = 0.2
    agent.response_top_p = 0.9
    agent.response_max_tokens = 120
    agent.ai_request_timeout = 10
    agent.ai_max_retries = 0
    agent.conversation_history = []
    agent.max_memory_items = 10
    agent.prompt_examples = []
    # Attributes required by newer windows_agent.py (added when engine integration was wired in)
    agent._pw_page = None
    agent._pw_intercepted = []
    agent._pw_page_cache = None
    agent._pw_page_cache_ts = 0.0
    agent._playwright_mode_active = False
    agent._pw_browser_type = "chromium"
    agent._last_elements = None
    agent._engine_fallback = None
    agent.autonomy_profile = "balanced"
    agent.last_user_message = ""
    agent.last_assistant_message = ""
    agent.memory_enabled = True
    agent.topic_anchor_text = ""
    agent.session_recaps = []
    agent.trajectory_memory = []
    agent.task_outcomes = []
    agent.pending_question = None
    agent.memory_journal_file = os.path.join(tmp_root, "memory", "conversation_memory.jsonl")
    agent._memory_snapshot_every = 8
    agent.max_session_recaps = 120
    agent.session_recap_trigger = 10
    agent.max_task_outcomes = 800
    agent.max_trajectories = 200
    agent.trajectory_compact_trigger = 12
    agent.learned_facts = []
    agent.adaptive_examples = []
    agent.failure_patterns = {}
    agent._trajectory_source_cursor = 0
    agent.task_conversation_history = []
    agent.last_live_web_query = ""
    agent.last_live_web_error = ""
    agent.screen_sharing_active = False
    agent.fast_prompt_mode = True
    agent.input_mode = "chat"
    agent.pending_plan_execution = None
    agent.pending_workflow_plan = None
    agent.last_screen_action_plan = None
    os.makedirs(agent.workspace_root, exist_ok=True)
    os.makedirs(agent.desktop_root, exist_ok=True)
    return agent


def _read_audit(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


class GuardrailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.agent = _make_agent(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_subprocess_allowlist_blocks_disallowed_binary(self):
        with self.assertRaises(PermissionError):
            self.agent._run_allowed_subprocess(["python.exe", "-V"])
        audit = _read_audit(self.agent.audit_log_file)
        self.assertTrue(any(e["action"] == "subprocess" and e["status"] == "blocked" for e in audit))

    def test_subprocess_allowlist_allows_configured_binary(self):
        with patch("windows_agent.subprocess.run", return_value=SimpleNamespace(returncode=0)) as run_mock:
            self.agent._run_allowed_subprocess(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True)
            run_mock.assert_called_once()
        audit = _read_audit(self.agent.audit_log_file)
        self.assertTrue(any(e["action"] == "subprocess" and e["status"] == "allowed" for e in audit))

    def test_path_sandbox_blocks_outside_workspace(self):
        path, err = self.agent._resolve_workspace_path(r"C:\Windows\System32\drivers\etc\hosts", allow_desktop=False)
        self.assertIsNone(path)
        self.assertIsNotNone(err)
        audit = _read_audit(self.agent.audit_log_file)
        self.assertTrue(any(e["action"] == "path_sandbox" and e["status"] == "blocked" for e in audit))

    def test_file_mutation_requires_explicit_consent(self):
        denied = self.agent._handle_file_command(
            "create file test.txt with content: hello",
            allow_desktop=False,
            allow_mutation=False,
        )
        self.assertIn("Authorization required", denied)

        allowed = self.agent._handle_file_command(
            "create file test.txt with content: hello",
            allow_desktop=False,
            allow_mutation=True,
        )
        self.assertIn("Saved file", allowed)
        self.assertTrue(os.path.exists(os.path.join(self.agent.workspace_root, "test.txt")))

    def test_process_command_requires_consent_for_close_app(self):
        denied = self.agent.process_command("close chrome")
        self.assertIn("Authorization required before closing apps.", denied)

        with patch.object(WindowsAgent, "close_app", return_value="Closed Google Chrome"):
            allowed = self.agent.process_command("AUTH_OK::close chrome")
            self.assertIn("Closed Google Chrome", allowed)

        audit = _read_audit(self.agent.audit_log_file)
        self.assertTrue(any(e["action"] == "authorization" and e["status"] == "granted" for e in audit))

    def test_reload_training_prompts_command(self):
        with open(self.agent.prompt_training_file, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"user": "open chrome", "assistant": "Opened Google Chrome."},
                    {"user": "bad", "assistant": ""},
                ],
                f,
            )
        reply = self.agent.process_command("reload training prompts")
        self.assertIn("Reloaded training prompts (1 examples).", reply)
        self.assertEqual(len(self.agent.prompt_examples), 1)
        audit = _read_audit(self.agent.audit_log_file)
        self.assertTrue(any(e["action"] == "training_reload" and e["status"] == "allowed" for e in audit))


if __name__ == "__main__":
    unittest.main()
