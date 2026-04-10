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
    agent.groq_api_key = ""
    agent.deepseek_api_key = ""
    agent.qwen_api_key = ""
    agent.gemini_api_key = ""
    agent.ai_provider = "auto"
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
    agent.ai_cache_ttl_sec = 20
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
    agent.input_mode = "task"
    agent.search_tool_types = {k: True for k in ("info", "image", "news", "api", "tool", "data", "research", "video", "shopping")}
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
