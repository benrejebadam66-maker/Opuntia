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

    # Playwright state (not set by __new__, needed by process_command playwright block)
    agent._pw_page = None
    agent._pw_intercepted = []
    agent._pw_page_cache = None
    agent._pw_page_cache_ts = 0.0
    agent._playwright_mode_active = False
    agent._pw_browser_type = "chromium"

    # Engine integration state
    agent._last_elements = None
    agent._engine_fallback = None

    # Autonomy / policy state
    agent.autonomy_profile = "balanced"

    # Conversation and memory state (added in newer windows_agent.py)
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
    agent.input_mode = "task"
    agent.search_tool_types = {k: True for k in ("info","image","news","api","tool","data","research","video","shopping")}
    agent.openai_compat_base_url = ""
    agent.openai_compat_api_key = ""
    agent.openai_compat_model = "gpt-4o-mini"
    agent.openai_compat_fallback_models = []
    agent.max_adaptive_examples = 1200
    agent.ai_provider_strict = False
    agent.ai_speed_mode = True
    agent.ai_fast_max_providers = 1
    agent.anthropic_api_key = ""
    agent.anthropic_model = "claude-3-5-sonnet-latest"
    agent.anthropic_fallback_models = []
    agent.anthropic_base_url = "https://api.anthropic.com/v1/messages"
    agent.anthropic_version = "2023-06-01"
    agent.deepseek_api_key = ""
    agent.glm_api_key = ""
    agent.glm_model = "glm-4-flash"
    agent.glm_fallback_models = []
    agent.glm_base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    agent.mimo_api_key = ""
    agent.mimo_model = "mimo-7b"
    agent.mimo_fallback_models = []
    agent.mimo_base_url = "https://api.mimo.ai/v1/chat/completions"
    agent.memory_summary_trigger = 14
    agent.memory_summary_keep_last = 6
    agent._last_summary_ts = 0.0
    agent.search_max_iterations = 5
    agent.search_deep_browse = True
    agent.search_citation_style = "numbered"
    agent.search_trace_enabled = False
    agent.auto_search_confidence_threshold = 0.65
    agent.web_research_auto = False
    agent.web_universal_mode = False
    agent.web_research_max_passes = 2
    agent.web_research_results_per_pass = 4
    agent.web_research_trace = False
    agent.web_search_providers = []
    agent.web_use_playwright = False
    agent.web_search_timeout_sec = 7
    agent.live_web_prefetch_enabled = False
    agent.web_respect_robots = True
    agent.robots_cache_ttl_sec = 1800
    agent._robots_cache = {}
    agent._web_search_cache = {}
    agent.web_search_cache_ttl_sec = 45
    agent.google_blocked_until_ts = 0.0
    agent.web_search_min_pause_sec = 1.2
    agent._last_web_search_ts = 0.0
    agent.source_attribution_enabled = False
    agent.source_show_confidence = False
    agent.source_min_credibility_score = 0.3
    agent.distinguish_source_enabled = False
    agent.training_data_cutoff = "2024-01-01"
    agent.serpapi_key = ""
    agent.google_cse_key = ""
    agent.google_cse_cx = ""
    agent.brave_search_api_key = ""
    agent.tavily_api_key = ""
    agent._source_credibility_scores = {}
    agent.last_search_metadata = {"sources_used": [], "search_type": "none", "confidence": 0.0, "timestamp": None, "query": "", "iterations": 0}
    agent.last_structured_intent = ""
    agent.last_structured_payload = {}
    agent.topic_anchor_keywords = []
    agent.topic_anchor_updated_at = 0.0
    agent.topic_anchor_ttl_sec = 900
    agent.last_live_web_error = ""
    agent.pending_workflow_plan = None
    agent.permission_request_timeout_sec = 90
    agent.user_city = ""
    agent.hostname = "testhost"
    agent.base_dir = tmp_root
    agent.appdata_dir = os.path.join(tmp_root, "appdata")
    agent.skills_root = os.path.join(tmp_root, "skills")
    agent.skills_registry_file = os.path.join(tmp_root, "skills_registry.json")
    agent.user_profile_file = os.path.join(tmp_root, "user_profile.json")
    agent.user_profile = {}
    agent.skills = []
    agent.skill_enabled_map = {}
    agent.hermes_memory = None
    agent.mcp_bridge = None
    agent.mcp_enabled = False
    agent.mcp_default_timeout_sec = 25
    agent.mcp_default_server = "filesystem"
    agent.mcp_allowed_dirs_ttl_sec = 90
    agent._mcp_allowed_dirs_cache = []
    agent._mcp_allowed_dirs_ts = 0.0
    agent.mcp_route_stats = {}
    agent.provider_health = {}
    agent.provider_cooldown_until = {}
    agent.provider_last_error = {}
    agent.vision_model = "meta-llama/llama-4-scout-17b-16e-instruct"
    agent.vision_fallback_models = []
    agent.screen_vision_detail_mode = "high"
    agent.screen_task_mode = True
    agent.screen_task_json_mode = True
    agent.screen_vision_fast_mode = False
    agent._screen_summary_cache = {}
    agent.last_screen_action_plan = None
    agent.pending_plan_execution = None
    agent.pending_workflow_plan = None

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
