import os
import json
import hashlib
from pathlib import Path
import re
import time
import html
import socket
import subprocess
import ctypes
import requests
import psutil
import pyautogui
import webbrowser
import base64
import shutil
import mimetypes
from datetime import datetime
from difflib import get_close_matches
from urllib.parse import quote_plus, unquote, urlsplit
from urllib import robotparser
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from agents.hermes_memory_bridge import HermesMemoryBridge
except Exception:
    HermesMemoryBridge = None
try:
    from agents.memory_safety import validate_memory_text
except Exception:
    validate_memory_text = None
try:
    from agents.mcp_bridge import MCPBridge
except Exception:
    MCPBridge = None

try:
    from engine import perceive, execute_action, init_tracing
    from engine.types import Action, ActionType, ElementMap
    from engine.privacy.scanner import scan_elements_for_pii, redact_text
    from engine.compat.input_control_bridge import InputControlBridge
    _ENGINE_AVAILABLE = True
except Exception:
    perceive = None
    execute_action = None
    init_tracing = None
    Action = None
    ActionType = None
    ElementMap = None
    scan_elements_for_pii = None
    redact_text = None
    InputControlBridge = None
    _ENGINE_AVAILABLE = False

try:
    from groq import Groq
except Exception:
    Groq = None

try:
    import winsound
except Exception:
    winsound = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import docx
except Exception:
    docx = None

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    from pptx import Presentation
except Exception:
    Presentation = None

try:
    import pygetwindow as gw
except Exception:
    gw = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

# For web browsing and content extraction
try:
    from bs4 import BeautifulSoup
    SOUP_AVAILABLE = True
except Exception:
    BeautifulSoup = None
    SOUP_AVAILABLE = False

if load_dotenv is not None:
    try:
        _env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=_env_path, override=False)
    except Exception:
        pass

class WindowsAgent:
    """Embedded backend so ui_agent.py is self-contained."""

    # Vocabulary of known command keywords used for fuzzy typo correction.
    # Only tokens within the first 10 words of a command are corrected.
    _CMD_VOCAB = frozenset([
        # Action verbs
        'write', 'create', 'make', 'open', 'close', 'delete', 'remove', 'rename',
        'find', 'search', 'show', 'move', 'copy', 'save', 'send', 'play', 'stop',
        'pause', 'start', 'run', 'launch', 'check', 'add', 'put', 'download',
        'upload', 'take', 'capture', 'read', 'list', 'tell', 'change', 'update',
        'install', 'minimize', 'maximize', 'resize', 'refresh', 'restart', 'mute',
        'unmute', 'increase', 'decrease', 'adjust', 'enable', 'disable', 'connect',
        # Objects / nouns
        'document', 'folder', 'file', 'word', 'pdf', 'excel', 'image', 'video', 'music',
        'notepad', 'calculator', 'desktop', 'browser', 'chrome', 'firefox', 'edge',
        'screenshot', 'screen', 'window', 'photo', 'picture', 'text', 'note',
        'message', 'email', 'contact', 'calendar', 'settings', 'volume', 'brightness',
        # Common command context words
        'inside', 'content', 'things', 'response', 'answer', 'result',
        'previous', 'latest', 'first', 'last', 'next',
    ])

    def __init__(self):
        self.groq_api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.glm_api_key = (os.getenv("GLM_API_KEY") or "").strip()
        self.mimo_api_key = (os.getenv("MIMO_API_KEY") or "").strip()
        self.openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        self.anthropic_api_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or "").strip()
        self.deepseek_api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
        self.qwen_api_key = (os.getenv("ALIBABA_MODEL_STUDIO_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "").strip()
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        self.ai_provider = (os.getenv("AI_PROVIDER") or "auto").strip().lower()
        self.ai_provider_strict = (os.getenv("AI_PROVIDER_STRICT", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.ai_speed_mode = (os.getenv("AI_SPEED_MODE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.ai_fast_max_providers = int(os.getenv("AI_FAST_MAX_PROVIDERS", "1"))
        self.fast_prompt_mode = (os.getenv("FAST_PROMPT_MODE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.openai_search_model = os.getenv("OPENAI_SEARCH_MODEL", "gpt-4.1-mini")
        self.use_openai_builtin_search = (os.getenv("OPENAI_BUILTIN_SEARCH", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.openai_compat_base_url = (
            os.getenv("OPENAI_COMPAT_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or ""
        ).strip()
        self.openai_compat_api_key = (
            os.getenv("OPENAI_COMPAT_API_KEY")
            or os.getenv("LLM_API_KEY")
            or self.openai_api_key
            or ""
        ).strip()
        self.openai_compat_model = (
            os.getenv("OPENAI_COMPAT_MODEL")
            or os.getenv("OPENAI_MODEL")
            or os.getenv("LLM_MODEL")
            or "gpt-4o-mini"
        ).strip()
        self.openai_compat_fallback_models = [
            m.strip()
            for m in (
                os.getenv("OPENAI_COMPAT_FALLBACK_MODELS")
                or os.getenv("OPENAI_FALLBACK_MODELS")
                or ""
            ).split(",")
            if m.strip()
        ]
        self.anthropic_base_url = (os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1/messages").strip()
        self.anthropic_version = (os.getenv("ANTHROPIC_VERSION") or "2023-06-01").strip()
        self.anthropic_model = (
            os.getenv("ANTHROPIC_MODEL")
            or os.getenv("CLAUDE_MODEL")
            or "claude-3-5-sonnet-latest"
        ).strip()
        self.anthropic_fallback_models = [
            m.strip()
            for m in (
                os.getenv("ANTHROPIC_FALLBACK_MODELS")
                or os.getenv("CLAUDE_FALLBACK_MODELS")
                or "claude-3-5-haiku-latest"
            ).split(",")
            if m.strip()
        ]
        self.web_search_providers = [
            p.strip().lower()
            for p in (os.getenv("WEB_SEARCH_PROVIDERS", "ddg_lite,bing,google_html,ddg,bing_rss") or "").split(",")
            if p.strip()
        ]
        self.web_use_playwright = (os.getenv("WEB_USE_PLAYWRIGHT", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.web_search_timeout_sec = int(os.getenv("WEB_SEARCH_TIMEOUT_SEC", "7"))
        self.live_web_prefetch_enabled = (os.getenv("LIVE_WEB_PREFETCH", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.web_research_max_passes = int(os.getenv("WEB_RESEARCH_MAX_PASSES", "2"))
        self.web_research_results_per_pass = int(os.getenv("WEB_RESEARCH_RESULTS_PER_PASS", "4"))
        self.web_research_trace = (os.getenv("WEB_RESEARCH_TRACE", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.web_respect_robots = (os.getenv("WEB_RESPECT_ROBOTS", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.robots_cache_ttl_sec = int(os.getenv("WEB_ROBOTS_CACHE_TTL_SEC", "1800"))
        self._robots_cache = {}
        self._web_search_cache = {}
        self.web_search_cache_ttl_sec = int(os.getenv("WEB_SEARCH_CACHE_TTL_SEC", "45"))
        self.google_blocked_until_ts = 0.0
        self.web_search_min_pause_sec = float(os.getenv("WEB_SEARCH_MIN_PAUSE_SEC", "1.2"))
        self._last_web_search_ts = 0.0
        
        # Advanced search tool types configuration
        self.search_tool_types = {
            "info": True,        # General web information
            "image": True,       # Image search
            "news": True,        # News and current events
            "api": True,         # API discovery and interaction
            "tool": True,        # External tools and calculators
            "data": True,        # Datasets and structured data
            "research": True,    # Academic papers and research
            "video": True,       # Video content
            "shopping": True,    # Product/pricing info
        }
        self.search_tool_enabled = (os.getenv("SEARCH_TOOL_TYPES", "info,image,news,api,tool,data,research,video,shopping") or "").strip()
        if self.search_tool_enabled:
            enabled_types = set(t.strip().lower() for t in self.search_tool_enabled.split(",") if t.strip())
            for key in self.search_tool_types:
                self.search_tool_types[key] = key in enabled_types
        
        # Intelligent routing configuration
        self.auto_search_confidence_threshold = float(os.getenv("AUTO_SEARCH_CONFIDENCE", "0.65"))
        self.search_max_iterations = int(os.getenv("SEARCH_MAX_ITERATIONS", "5"))
        self.search_deep_browse = (os.getenv("SEARCH_DEEP_BROWSE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.search_citation_style = os.getenv("SEARCH_CITATION_STYLE", "numbered").strip().lower()
        self.search_trace_enabled = (os.getenv("SEARCH_TRACE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"})
        
        # Browser tool configuration
        self.browser_headless = (os.getenv("BROWSER_HEADLESS", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.browser_timeout_ms = int(os.getenv("BROWSER_TIMEOUT_MS", "15000"))
        self.browser_wait_load_ms = int(os.getenv("BROWSER_WAIT_LOAD_MS", "3000"))
        self.browser_extract_images = (os.getenv("BROWSER_EXTRACT_IMAGES", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.browser_extract_links = (os.getenv("BROWSER_EXTRACT_LINKS", "1").strip().lower() not in {"0", "false", "no", "off"})
        # Persistent Playwright session — runs on a dedicated thread
        self._pw_thread = None
        self._pw_cmd_queue = None   # queue.Queue for sending commands to the thread
        self._pw_res_queue = None   # queue.Queue for receiving results
        self._pw_page = None        # proxy flag: None = browser not open
        self._pw_browser_type = "chromium"  # active browser engine
        self._pw_intercepted = []   # captured network requests
        self._playwright_mode_active = False  # set True by UI when split-panel is open
        self._pw_page_cache = None           # cached dict: url/title/text/scan
        self._pw_page_cache_ts = 0.0         # epoch time of last cache fill
        
        # Source attribution
        self.source_attribution_enabled = (os.getenv("SOURCE_ATTRIBUTION", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.source_show_confidence = (os.getenv("SOURCE_SHOW_CONFIDENCE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.source_min_credibility_score = float(os.getenv("SOURCE_MIN_CREDIBILITY", "0.3"))
        
        # Training data vs live search distinction
        self.distinguish_source_enabled = (os.getenv("DISTINGUISH_SOURCE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.training_data_cutoff = os.getenv("TRAINING_DATA_CUTOFF", "2024-01-01")
        self.serpapi_key = (os.getenv("SERPAPI_API_KEY") or "").strip()
        self.google_cse_key = (os.getenv("GOOGLE_CSE_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        self.google_cse_cx = (os.getenv("GOOGLE_CSE_CX") or "").strip()
        self.brave_search_api_key = (os.getenv("BRAVE_SEARCH_API_KEY") or "").strip()
        self.tavily_api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.groq_fallback_models = ["llama-3.1-70b-versatile", "llama-3.1-8b-instant"]
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.deepseek_fallback_models = ["deepseek-chat"]
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen-plus")
        self.qwen_fallback_models = [m.strip() for m in (os.getenv("QWEN_FALLBACK_MODELS", "qwen-turbo") or "").split(",") if m.strip()]
        self.qwen_base_url = (
            os.getenv("QWEN_BASE_URL")
            or os.getenv("DASHSCOPE_BASE_URL")
            or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
        ).strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.gemini_fallback_models = [m.strip() for m in (os.getenv("GEMINI_FALLBACK_MODELS", "gemini-1.5-pro") or "").split(",") if m.strip()]
        self.glm_model = os.getenv("GLM_MODEL", "glm-4-flash")
        self.glm_fallback_models = ["glm-4-air", "glm-4"]
        self.glm_base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.mimo_model = os.getenv("MIMO_MODEL", "mimo-7b")
        self.mimo_fallback_models = ["mimo-7b"]
        self.mimo_base_url = os.getenv("MIMO_BASE_URL", "https://api.mimo.ai/v1/chat/completions")
        self.client = Groq(api_key=self.groq_api_key) if (Groq is not None and self.groq_api_key) else None
        self.response_temperature = 0.5
        self.response_top_p = 0.9
        self.response_max_tokens = int(os.getenv("AI_MAX_TOKENS", "1024"))
        self.ai_request_timeout = int(os.getenv("AI_REQUEST_TIMEOUT", "25"))
        self.ai_max_retries = int(os.getenv("AI_MAX_RETRIES", "0"))
        self.ai_cache_ttl_sec = int(os.getenv("AI_CACHE_TTL_SEC", "20"))
        self.hostname = socket.gethostname()
        self.last_apps_check = None
        self.last_apps_list = []
        self.last_status_app = None
        self.app_launch_index = {}
        self.app_index_last_build = 0
        self.start_apps_index = {}
        self.start_apps_last_build = 0
        self.workspace_root = os.path.abspath(os.getcwd())
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.desktop_root = os.path.abspath(os.path.join(os.path.expanduser("~"), "Desktop"))
        # Use shared AppData folder so both the dev run and the packaged exe share the same memory/logs.
        _appdata = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        self.appdata_dir = os.path.join(_appdata, "Opuntia Beta0.2")
        os.makedirs(self.appdata_dir, exist_ok=True)
        self.memory_dir = os.path.join(self.appdata_dir, "memory")
        self.exports_dir = os.path.join(self.memory_dir, "exports")
        self.memory_file = os.path.join(self.memory_dir, "conversation_memory.json")
        self.memory_journal_file = os.path.join(self.memory_dir, "conversation_memory.jsonl")
        self.learned_facts_file = os.path.join(self.memory_dir, "learned_facts.json")
        self.adaptive_examples_file = os.path.join(self.memory_dir, "adaptive_examples.json")
        self.session_recaps_file = os.path.join(self.memory_dir, "session_recaps.json")
        self.task_outcomes_file = os.path.join(self.memory_dir, "task_outcomes.json")
        self.trajectory_memory_file = os.path.join(self.memory_dir, "trajectory_memory.json")
        self.provider_stats_file = os.path.join(self.memory_dir, "provider_stats.json")
        self.mcp_servers_file = os.path.join(self.memory_dir, "mcp_servers.json")
        self.mcp_route_stats_file = os.path.join(self.memory_dir, "mcp_route_stats.json")
        self.mcp_repo_config_file = os.path.join(self.base_dir, "mcp_servers.json")
        self.mcp_example_config_file = os.path.join(self.base_dir, "mcp_servers.example.json")
        self.settings_file = os.path.join(self.memory_dir, "settings.json")
        self.feedback_file = os.path.join(self.memory_dir, "feedback.jsonl")
        self.last_feedback_error = ""
        self.prompt_training_file = os.path.join(self.base_dir, "prompt_training.json")
        self.skills_root = os.path.join(self.base_dir, "skills")
        self.skills_registry_file = os.path.join(self.memory_dir, "skills_registry.json")
        self.user_profile_file = os.path.join(self.memory_dir, "user_profile.json")
        self.user_profile = {}
        self.hermes_memory = None
        if HermesMemoryBridge is not None:
            self.hermes_memory = HermesMemoryBridge(
                self.memory_dir,
                max_items=int(os.getenv("HERMES_MEMORY_MAX_ITEMS", "400")),
            )
            self.hermes_memory.load()
        self.mcp_bridge = None
        self.mcp_enabled = (os.getenv("MCP_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.mcp_default_timeout_sec = int(os.getenv("MCP_DEFAULT_TIMEOUT_SEC", "25"))
        self.mcp_default_server = (os.getenv("MCP_DEFAULT_SERVER", "filesystem") or "filesystem").strip().lower()
        self.mcp_allowed_dirs_ttl_sec = int(os.getenv("MCP_ALLOWED_DIRS_TTL_SEC", "90"))
        self.mcp_config_path = (
            os.getenv("MCP_CONFIG_PATH")
            or (self.mcp_servers_file if os.path.exists(self.mcp_servers_file) else "")
            or (self.mcp_repo_config_file if os.path.exists(self.mcp_repo_config_file) else "")
            or (self.mcp_example_config_file if os.path.exists(self.mcp_example_config_file) else self.mcp_servers_file)
        )
        if self.mcp_enabled and MCPBridge is not None:
            self.mcp_bridge = MCPBridge(
                config_path=self.mcp_config_path,
                default_timeout_sec=self.mcp_default_timeout_sec,
            )
        self.max_memory_items = int(os.getenv("MAX_MEMORY_ITEMS", "2000"))
        self.max_adaptive_examples = int(os.getenv("MAX_ADAPTIVE_EXAMPLES", "1200"))
        self.max_session_recaps = int(os.getenv("MAX_SESSION_RECAPS", "120"))
        self.session_recap_trigger = int(os.getenv("SESSION_RECAP_TRIGGER", "10"))
        self.max_task_outcomes = int(os.getenv("MAX_TASK_OUTCOMES", "800"))
        self.max_trajectories = int(os.getenv("MAX_TRAJECTORIES", "200"))
        self.trajectory_compact_trigger = int(os.getenv("TRAJECTORY_COMPACT_TRIGGER", "12"))
        self.conversation_history = []
        self.task_conversation_history = []  # separate history for Task mode
        self.session_recaps = []
        self.task_outcomes = []
        self.failure_patterns = {}
        self.trajectory_memory = []
        self._trajectory_source_cursor = 0
        self.memory_safety_block_count = 0
        self.provider_health = {}
        self.provider_cooldown_until = {}
        self.provider_last_error = {}
        self.mcp_route_stats = {}
        self._mcp_allowed_dirs_cache = []
        self._mcp_allowed_dirs_ts = 0.0
        self.prompt_examples = []
        self.skills = []
        self.skill_enabled_map = {}
        self.learned_facts = []
        self.adaptive_examples = []
        self._memory_snapshot_every = 8
        self.vision_model = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        self.vision_fallback_models = [
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "llama-3.2-11b-vision-preview",
        ]
        self.screen_vision_detail_mode = (os.getenv("SCREEN_VISION_DETAIL_MODE", "high") or "high").strip().lower()
        self.screen_task_mode = (os.getenv("SCREEN_TASK_MODE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.screen_task_json_mode = (os.getenv("SCREEN_TASK_JSON_MODE", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.screen_vision_fast_mode = (os.getenv("SCREEN_VISION_FAST_MODE", "0").strip().lower() not in {"0", "false", "no", "off"})
        self.screen_sharing_active = False  # True when current message carries a live screenshot
        self._screen_summary_cache = {}
        self._ai_response_cache = {}
        self.last_user_message = ""
        self.last_assistant_message = ""
        self.topic_anchor_text = ""
        self.topic_anchor_keywords = []
        self.topic_anchor_updated_at = 0.0
        self.topic_anchor_ttl_sec = int(os.getenv("TOPIC_ANCHOR_TTL_SEC", "900"))
        self.last_live_web_query = ""
        self.last_live_web_error = ""
        self.last_structured_intent = ""
        self.last_structured_payload = {}
        self.web_research_auto = (os.getenv("WEB_RESEARCH_AUTO", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.web_universal_mode = (os.getenv("WEB_UNIVERSAL_MODE", "0").strip().lower() not in {"0", "false", "no", "off"})
        
        # Advanced search state tracking
        self.last_search_metadata = {
            "sources_used": [],
            "search_type": "none",
            "confidence": 0.0,
            "timestamp": None,
            "query": "",
            "iterations": 0,
        }
        self._source_credibility_scores = {}
        
        self.last_screen_action_plan = None
        self.pending_plan_execution = None
        self.pending_workflow_plan = None
        self.pending_confirmation = None
        self.pending_question = None
        self.autonomy_profile = (os.getenv("AUTONOMY_PROFILE", "balanced") or "balanced").strip().lower()
        self.user_city = ""  # User-set home city, overrides IP detection in greeting
        self.permission_request_timeout_sec = int(os.getenv("PERMISSION_REQUEST_TIMEOUT_SEC", "90"))
        self.last_ai_runtime = {
            "provider": "local",
            "model": "rules",
            "status": "idle",
            "error": "",
        }
        self.audit_log_file = os.path.join(self.appdata_dir, "logs", "security_audit.jsonl")
        self.allowed_subprocess_bins = {
            "netsh",
            "powershell",
            "taskkill",
            "explorer.exe",
            "shutdown",
            "rundll32.exe",
            "control.exe",
            "taskmgr.exe",
            "devmgmt.msc",
            "services.msc",
        }
        self.allowed_launch_bins = {
            "chrome.exe",
            "firefox.exe",
            "msedge.exe",
            "brave.exe",
            "notepad.exe",
            "calc.exe",
            "explorer.exe",
            "cmd.exe",
            "powershell.exe",
            "spotify.exe",
            "discord.exe",
            "telegram.exe",
            "code.exe",
            "cursor.exe",
            "wt.exe",
            "taskmgr.exe",
            "control.exe",
            "rundll32.exe",
            "shutdown.exe",
        }
        self.memory_enabled = (os.getenv("MEMORY_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.feedback_enabled = (os.getenv("FEEDBACK_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"})
        self.private_mode = False
        self._pre_private_memory_enabled = None
        self._pre_private_feedback_enabled = None
        self.memory_summary_trigger = int(os.getenv("MEMORY_SUMMARY_TRIGGER", "14"))
        self.memory_summary_keep_last = int(os.getenv("MEMORY_SUMMARY_KEEP_LAST", "6"))
        self._last_summary_ts = 0.0
        self._load_settings()
        self._load_provider_stats()
        self._load_mcp_route_stats()
        self.load_memory()
        self.load_session_recaps()
        self.load_task_outcomes()
        self.load_trajectory_memory()
        self.load_prompt_examples()
        self.load_skills()
        self.load_long_term_learning()
        self.load_user_profile()
        # On every startup: past conversations become training data, context starts fresh
        self.start_new_session()
        self.last_attachment_paths = []
        self.last_attachment_ts = 0.0
        self._pending_doc_save = None  # {"temp_path": str, "name": str} Ã¢Â€Â” waiting for save location
        self._pending_pdf_save = None  # {"content": str, "name": str, "doc_title": str} Ã¢Â€Â” waiting for save location
        self.input_mode = "chat"  # default mode; set to "task" when task prefix detected
        # Engine integration (Phase 1) — perception, execution, PII, tracing
        if init_tracing is not None:
            try:
                init_tracing()
            except Exception:
                pass
        self._engine_fallback = None   # InputControlBridge; no raw dispatcher in this agent
        self._last_elements = None     # Last ElementMap from structured UIA perception

    # ------------------------------------------------------------------
    # Engine-powered perception and action methods (Phase 1 integration)
    # These supplement, never replace, the existing screenshot/pyautogui
    # path. All fall back gracefully if the engine is unavailable.
    # ------------------------------------------------------------------

    async def get_structured_screen(self, app_name=None):
        """Get structured UI elements via Windows UIA. Returns (ElementMap, pii_matches).

        Does NOT replace _describe_screen_snapshot() — it supplements it.
        The caller receives element IDs and labels alongside the visual frame.
        """
        if perceive is None:
            return None, []
        try:
            elements = await perceive(app_name=app_name)
            self._last_elements = elements
            pii_matches = scan_elements_for_pii(elements.elements)
            return elements, pii_matches
        except Exception as e:
            import logging
            logging.warning("Engine perception failed, using screenshot only: %s", e)
            return None, []

    async def smart_click(self, element_id: str):
        """Click element by UIA element ID; falls back to raw SendInput if UIA fails."""
        if execute_action is None or self._last_elements is None:
            return None
        action = Action(action_type=ActionType.CLICK, element_id=element_id)
        return await execute_action(
            action, self._last_elements, fallback_dispatcher=self._engine_fallback
        )

    async def smart_type(self, element_id: str, text: str):
        """Type text via UIA ValuePattern; falls back to raw keystroke injection."""
        if execute_action is None or self._last_elements is None:
            return None
        action = Action(action_type=ActionType.TYPE, element_id=element_id, text=text)
        return await execute_action(
            action, self._last_elements, fallback_dispatcher=self._engine_fallback
        )

    async def smart_read(self, element_id: str):
        """Read element text via UIA ValuePattern / TextPattern / Name."""
        if execute_action is None or self._last_elements is None:
            return None
        action = Action(action_type=ActionType.READ, element_id=element_id)
        return await execute_action(action, self._last_elements)

    # ------------------------------------------------------------------

    def _call_deepseek_chat(self, messages, model_name):
        if not self.deepseek_api_key:
            raise RuntimeError("DeepSeek API key not configured.")
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": self.response_max_tokens,
            "temperature": self.response_temperature,
            "top_p": self.response_top_p,
        }
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"DeepSeek error {response.status_code}: {response.text[:240]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek returned no choices.")
        msg = (choices[0].get("message") or {}).get("content")
        if not msg:
            raise RuntimeError("DeepSeek returned empty content.")
        return msg

    def _call_groq_chat(self, messages, model_name):
        if self.client is None:
            raise RuntimeError("Groq client not configured.")
        response = self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=self.response_max_tokens,
            temperature=self.response_temperature,
            top_p=self.response_top_p,
        )
        if response and response.choices and response.choices[0].message:
            return response.choices[0].message.content
        raise RuntimeError("Groq returned empty content.")

    def _call_glm_chat(self, messages, model_name):
        if not self.glm_api_key:
            raise RuntimeError("GLM API key not configured.")
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": self.response_max_tokens,
            "temperature": self.response_temperature,
            "top_p": self.response_top_p,
        }
        response = requests.post(
            self.glm_base_url,
            headers={
                "Authorization": f"Bearer {self.glm_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"GLM error {response.status_code}: {response.text[:240]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("GLM returned no choices.")
        msg = (choices[0].get("message") or {}).get("content")
        if not msg:
            raise RuntimeError("GLM returned empty content.")
        return msg

    def _call_mimo_chat(self, messages, model_name):
        if not self.mimo_api_key:
            raise RuntimeError("Mimo API key not configured.")
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": self.response_max_tokens,
            "temperature": self.response_temperature,
            "top_p": self.response_top_p,
        }
        response = requests.post(
            self.mimo_base_url,
            headers={
                "Authorization": f"Bearer {self.mimo_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Mimo error {response.status_code}: {response.text[:240]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Mimo returned no choices.")
        msg = (choices[0].get("message") or {}).get("content")
        if not msg:
            raise RuntimeError("Mimo returned empty content.")
        return msg

    def _call_qwen_chat(self, messages, model_name):
        if not self.qwen_api_key:
            raise RuntimeError("Qwen/DashScope API key not configured.")
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": self.response_max_tokens,
            "temperature": self.response_temperature,
            "top_p": self.response_top_p,
        }
        response = requests.post(
            self.qwen_base_url,
            headers={
                "Authorization": f"Bearer {self.qwen_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Qwen error {response.status_code}: {response.text[:240]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Qwen returned no choices.")
        msg = (choices[0].get("message") or {}).get("content")
        if not msg:
            raise RuntimeError("Qwen returned empty content.")
        return msg

    def _call_openai_compatible_chat(self, messages, model_name):
        base = (self.openai_compat_base_url or "").strip()
        if not base:
            raise RuntimeError("OpenAI-compatible base URL not configured.")
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": self.response_max_tokens,
            "temperature": self.response_temperature,
            "top_p": self.response_top_p,
        }
        headers = {"Content-Type": "application/json"}
        key = (self.openai_compat_api_key or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        response = requests.post(
            base,
            headers=headers,
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI-compatible error {response.status_code}: {response.text[:260]}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI-compatible backend returned no choices.")
        msg = (choices[0].get("message") or {}).get("content")
        if isinstance(msg, list):
            text_parts = []
            for part in msg:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text") or ""))
            msg = "\n".join([x for x in text_parts if x]).strip()
        if not msg:
            raise RuntimeError("OpenAI-compatible backend returned empty content.")
        return str(msg).strip()

    def _call_anthropic_chat(self, messages, model_name):
        if not self.anthropic_api_key:
            raise RuntimeError("Anthropic API key not configured.")
        system_parts = []
        converted = []
        for m in messages or []:
            role = (m.get("role") or "user").strip().lower()
            content = m.get("content") or ""
            if isinstance(content, list):
                text_parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        text_parts.append(str(p.get("text") or ""))
                content = "\n".join([x for x in text_parts if x]).strip()
            content = str(content).strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
                continue
            if role not in {"user", "assistant"}:
                role = "user"
            converted.append({"role": role, "content": content})
        if not converted:
            raise RuntimeError("Anthropic prompt is empty.")
        payload = {
            "model": model_name,
            "max_tokens": int(self.response_max_tokens),
            "messages": converted,
        }
        system_text = "\n\n".join(system_parts).strip()
        if system_text:
            payload["system"] = system_text[:12000]
        response = requests.post(
            self.anthropic_base_url,
            headers={
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": self.anthropic_version,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Anthropic error {response.status_code}: {response.text[:260]}")
        data = response.json()
        blocks = data.get("content") or []
        texts = []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                texts.append(str(b.get("text") or ""))
        out = "\n".join([x for x in texts if x]).strip()
        if not out:
            raise RuntimeError("Anthropic returned empty content.")
        return out

    def _messages_to_plain_prompt(self, messages):
        lines = []
        for m in messages or []:
            role = (m.get("role") or "user").strip().lower()
            content = m.get("content") or ""
            if isinstance(content, list):
                parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        parts.append(str(p.get("text") or ""))
                content = "\n".join([x for x in parts if x]).strip()
            content = str(content).strip()
            if not content:
                continue
            if role == "system":
                tag = "System"
            elif role == "assistant":
                tag = "Assistant"
            else:
                tag = "User"
            lines.append(f"{tag}: {content}")
        return "\n\n".join(lines)[-12000:]

    def _call_gemini_chat(self, messages, model_name):
        if not self.gemini_api_key:
            raise RuntimeError("Gemini API key not configured.")
        prompt = self._messages_to_plain_prompt(messages)
        if not prompt:
            raise RuntimeError("Gemini prompt is empty.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "temperature": float(self.response_temperature),
                "topP": float(self.response_top_p),
                "maxOutputTokens": int(self.response_max_tokens),
            },
        }
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=self.ai_request_timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini error {response.status_code}: {response.text[:240]}")
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = ""
        for p in parts:
            if isinstance(p, dict) and p.get("text"):
                text += str(p.get("text"))
        text = text.strip()
        if not text:
            raise RuntimeError("Gemini returned empty content.")
        return text

    def _is_complex_user_request(self, messages):
        """Heuristic complexity check for provider ordering in auto mode."""
        if not messages:
            return False
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = (m.get("content") or "").lower()
                break
        if not user_text:
            return False
        patterns = [
            r"\b(code|script|python|debug|fix|error|traceback|refactor)\b",
            r"\b(plan|step by step|analyze|architecture|design)\b",
            r"\b(compare|tradeoff|best approach|optimi[sz]e)\b",
            r"\b(file|folder|directory|read|write|create|delete|rename|move|copy)\b",
        ]
        return any(re.search(p, user_text, flags=re.IGNORECASE) for p in patterns)

    def _normalize_for_prompt_cache(self, text):
        raw = str(text or "")
        if not raw:
            return ""
        # Remove highly volatile timestamps from system blocks.
        raw = re.sub(
            r"current date and time:\s*.*?(?:\n|$)",
            "current date and time: <dynamic>",
            raw,
            flags=re.IGNORECASE,
        )
        raw = re.sub(r"\d{2}:\d{2}:\d{2}", "<time>", raw)
        raw = re.sub(r"\d{4}-\d{2}-\d{2}", "<date>", raw)
        raw = re.sub(r"\s+", " ", raw.strip().lower())
        return raw[:900]

    def _cache_key_from_messages(self, messages):
        try:
            rows = list(messages or [])
            if not rows:
                return ""
            user = ""
            system_parts = []
            for m in rows:
                role = (m.get("role") or "").strip().lower()
                content = m.get("content") or ""
                if role == "system":
                    system_parts.append(self._normalize_for_prompt_cache(content))
                elif role == "user":
                    user = self._normalize_for_prompt_cache(content)
            if not user:
                return ""
            # Keep fingerprint small but context-aware: first + last system snippets.
            sampled = []
            if system_parts:
                sampled.append(system_parts[0])
                if len(system_parts) > 1:
                    sampled.append(system_parts[-1])
                if len(system_parts) > 2:
                    sampled.append(system_parts[-2])
            fingerprint_src = "||".join(sampled)
            digest = hashlib.sha1(fingerprint_src.encode("utf-8")).hexdigest()[:16] if fingerprint_src else "nosys"
            mode = getattr(self, "input_mode", "chat")
            return f"{mode}|{digest}|{user[:420]}"
        except Exception:
            return ""

    def _get_cached_ai_response(self, key):
        if not key:
            return ""
        item = self._ai_response_cache.get(key)
        if not item:
            return ""
        if (time.time() - item.get("ts", 0)) > self.ai_cache_ttl_sec:
            self._ai_response_cache.pop(key, None)
            return ""
        return (item.get("answer") or "").strip()

    def _set_cached_ai_response(self, key, answer):
        if not key or not answer:
            return
        self._ai_response_cache[key] = {"ts": time.time(), "answer": answer}
        if len(self._ai_response_cache) > 120:
            # Keep cache bounded.
            oldest = sorted(self._ai_response_cache.items(), key=lambda kv: kv[1].get("ts", 0))[:30]
            for k, _ in oldest:
                self._ai_response_cache.pop(k, None)

    def _normalize_spoken_typos(self, text):
        t = (text or "").strip()
        if not t:
            return t
        # Strip surrounding quotation marks users sometimes type e.g. "Open WhatsApp"
        # Only strip if SAME quote type on both ends (ASCII only) so file content isn't mangled
        if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
            t = t[1:-1].strip()
        # Strip lone leading quote (unmatched) e.g. "OK, remove hich.docx ? OK, remove hich.docx
        elif len(t) >= 2 and t[0] in ('"', "'") and t[-1] not in ('"', "'"):
            t = t[1:].strip()
        fixes = {
            r"\bpower\s*shell\b": "powershell",
            r"\bvs\s*cod(e)?\b": "vs code",
            r"\bv s code\b": "vs code",
            r"\binsta\s*gram\b": "instagram",
            r"\bwhats\s*app\b": "whatsapp",
            r"\bfile\s*explore\b": "file explorer",
            r"\bopen up\b": "open",
            # Common creation typos
            r"\bcreat\b(?!\w)": "create",
            r"\bcreate?\s+a?\s*word\s+doc\b": "create word doc",
            r"\bdocumnet\b": "document",
            r"\bdocument\s+word\b": "word document",
            # Word doc command typos
            r"\bwrod\b": "word",
            r"\bwor\s+doc\b": "word doc",
            r"\bcontant\b": "content",
            r"\bwrit\s+ethis\b": "write this",
            r"\bwrit\s+this\b": "write this",
            r"\bwite\s+this\b": "write this",
            r"\bthins\b": "things",
            r"\bthinsg\b": "things",
            r"\bthigns\b": "things",
        }
        out = t
        for pattern, replacement in fixes.items():
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        # Collapse horizontal whitespace only Ã¢Â€Â” preserve newlines so that
        # multi-line content pasted by the user (document body, code, etc.)
        # reaches _handle_word_command with its structure intact.
        out = re.sub(r'[^\S\n]+', ' ', out)        # spaces/tabs ? single space
        out = re.sub(r'\n{3,}', '\n\n', out)        # max 2 consecutive newlines
        out = out.strip()

        # -- Fuzzy correction for command-portion tokens (first 10 words) ------
        # Corrects novel typos like "serach"?"search", "delte"?"delete", etc.
        # Only applied to the FIRST LINE (the command), so content body lines
        # with technical terms, URLs, paths etc. are never accidentally "corrected".
        try:
            from difflib import get_close_matches
            nl_pos = out.find('\n')
            cmd_line = out[:nl_pos] if nl_pos != -1 else out
            body_rest = out[nl_pos:] if nl_pos != -1 else ''   # includes the \n
            tokens = cmd_line.split()
            corrected = []
            for idx, tok in enumerate(tokens):
                if idx >= 10:
                    # Beyond command portion Ã¢Â€Â” keep everything as-is
                    corrected.extend(tokens[idx:])
                    break
                lower = tok.lower()
                # Skip: already a vocab word, too short, filename-like, numeric
                if (lower in self._CMD_VOCAB
                        or len(lower) < 4
                        or re.search(r'[.\d/_@#\\]', tok)):
                    corrected.append(tok)
                    continue
                matches = get_close_matches(lower, self._CMD_VOCAB, n=1, cutoff=0.82)
                if matches:
                    corrected.append(matches[0])
                else:
                    corrected.append(tok)
            out = ' '.join(corrected) + body_rest
        except Exception:
            pass

        return out

    def _is_screen_task_intent(self, user_input):
        t = (user_input or "").strip().lower()
        if not t:
            return False
        patterns = [
            r"\b(click|tap|press|double.?click|right.?click)\b",
            r"\b(type|write|enter|fill|input|paste)\b",
            r"\b(scroll|swipe|drag|drop|select|choose|open tab|close tab)\b",
            r"\b(go to|navigate|submit|send|save|download|upload)\b",
            r"\b(step by step|guide me|walk me through|do this task|do it for me|do it yourself)\b",
            r"\b(find.{0,20}(click|press|open|tap)|open.{0,20}(and|then).{0,20}(search|type|click|go))\b",
            r"\b(for me|on my behalf|in my place|automatically|auto)\b",
            r"\b(close this|close the|minimize|maximize|resize|move the window)\b",
        ]
        return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)

    def _needs_screen_vision(self, user_input, screen_task_intent=False):
        """Run expensive image analysis only when request depends on visible screen content."""
        if screen_task_intent:
            return True
        t = (user_input or "").strip().lower()
        if not t:
            return False
        patterns = [
            r"\b(what (are|do) you (see|seeing|look at|looking at)|what.?s on (my )?screen|read (the )?screen)\b",
            r"\b(describe (my |the )?screen|what can you see|and now|now what)\b",
            r"\b(visible|on screen|this page|this window|this tab|this button)\b",
            r"\b(where is|find on screen|locate|which button|which tab)\b",
            r"\b(read|extract|copy)\s+(text|line|content)\b",
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in patterns):
            return True
        # Short follow-up questions (=4 words) during an active screen session
        # e.g. "Powerpoint?", "which tab?", "and Chrome?" Ã¢Â€Â” treat as screen follow-ups
        words = t.split()
        if len(words) <= 4 and self.screen_sharing_active:
            return True
        return False

    def _screen_task_prompt(self):
        base = (
            "AUTONOMOUS TASK MODE Ã¢Â€Â” you are acting as the user's hands on screen.\n"
            "The user wants you to perform actions on their behalf using the live screen context.\n"
            "1) Identify the active app/window and exact visible targets (buttons, fields, tabs, menus, links).\n"
            "2) Break the task into precise numbered steps Ã¢Â€Â” each step = one action (click, type, hotkey, scroll, etc.).\n"
            "3) Use exact labels from what you see on screen. Never invent labels.\n"
            "4) Include x/y coordinates or bounding boxes for each click target based on what you see.\n"
            "5) If a target is ambiguous or not visible, say so clearly and ask one short clarification.\n"
            "6) Keep steps short, clear, and executable.\n"
            "Output format:\n"
            "- App/window: ...\n"
            "- Task: what I will do for you\n"
            "- Steps: 1..N\n"
            "- Clarification needed: yes/no (+ question if yes)"
        )
        if not self.screen_task_json_mode:
            return base
        return (
            base
            + "\n\nAlso include a machine-readable JSON block in a fenced code block:\n"
            + "```json\n"
            + "{\n"
            + '  "app_window": "string",\n'
            + '  "targets": ["string"],\n'
            + '  "targets_meta": [\n'
            + '    {"label": "string", "bbox": [x, y, w, h], "confidence": 0.0}\n'
            + "  ],\n"
            + '  "needs_clarification": false,\n'
            + '  "clarification_question": "",\n'
            + '  "actions": [\n'
            + '    {"step": 1, "action": "click|double_click|right_click|type|hotkey|scroll|open_url|wait", "target": "string", "x": 0, "y": 0, "bbox": [x, y, w, h], "value": "optional string", "confidence": 0.0}\n'
            + "  ]\n"
            + "}\n"
            + "```\n"
            + "Rules for JSON:\n"
            + "- actions must be executable and ordered.\n"
            + "- For click-like actions, provide x/y if possible; otherwise provide bbox.\n"
            + "- confidence is 0..1.\n"
            + "- If uncertain, set needs_clarification=true and ask one concise question."
        )

    def _extract_json_block(self, text):
        s = (text or "").strip()
        if not s:
            return None
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", s, flags=re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                return None
        m2 = re.search(r"(\{[\s\S]*\"actions\"[\s\S]*\})", s, flags=re.IGNORECASE)
        if m2:
            try:
                return json.loads(m2.group(1).strip())
            except Exception:
                return None
        return None

    def get_last_screen_action_plan(self):
        return self.last_screen_action_plan

    def _build_provider_order(self, messages):
        """Keep same capabilities, but route to stronger/faster provider based on request complexity."""
        _base = (self.openai_compat_base_url or "").strip()
        _local_compat = (
            _base.startswith("http://localhost")
            or _base.startswith("http://127.0.0.1")
        )
        has_openai_compatible = bool(_base and (self.openai_compat_api_key or _local_compat))
        has_anthropic = bool((self.anthropic_api_key or "").strip())
        explicit_map = {
            "groq": "groq",
            "deepseek": "deepseek",
            "qwen": "qwen",
            "alibaba": "qwen",
            "dashscope": "qwen",
            "gemini": "gemini",
            "google": "gemini",
            "anthropic": "anthropic",
            "claude": "anthropic",
            "glm": "glm",
            "zhipu": "glm",
            "mimo": "mimo",
            "openai_compatible": "openai_compatible",
            "openai-compatible": "openai_compatible",
            "openai": "openai_compatible",
            "ollama": "openai_compatible",
            "openrouter": "openai_compatible",
        }

        available = []
        if has_anthropic:
            available.append("anthropic")
        if has_openai_compatible:
            available.append("openai_compatible")
        if self.gemini_api_key:
            available.append("gemini")
        if self.qwen_api_key:
            available.append("qwen")
        if self.deepseek_api_key:
            available.append("deepseek")
        if self.groq_api_key:
            available.append("groq")
        if self.glm_api_key:
            available.append("glm")
        if self.mimo_api_key:
            available.append("mimo")

        if not available:
            return []

        # Explicit provider preference:
        # - strict mode: use only that provider
        # - default: prefer it first, then fallback to other available providers
        if self.ai_provider in explicit_map:
            chosen = explicit_map[self.ai_provider]
            if self.ai_provider_strict:
                return [chosen] if chosen in available else []
            ordered = [chosen] if chosen in available else []
            ordered.extend([p for p in available if p != chosen])
            return ordered

        # Base preference (quality-first), then adaptive re-ranking by learned reliability.
        preferred = ["anthropic", "openai_compatible", "gemini", "qwen", "deepseek", "groq", "glm", "mimo"]
        ordered = [p for p in preferred if p in available]
        ordered.extend([p for p in available if p not in ordered])
        bias_map = {p: max(0.0, (len(ordered) - i) * 0.05) for i, p in enumerate(ordered)}
        ranked = sorted(
            ordered,
            key=lambda p: self._provider_priority_score(p, position_bias=bias_map.get(p, 0.0)),
            reverse=True,
        )
        return ranked

    def _retry_invoke(self, fn, retries):
        last_error = None
        for attempt in range(retries + 1):
            try:
                return fn()
            except Exception as e:
                last_error = e
                if attempt < retries:
                    time.sleep(0.35 * (attempt + 1))
        raise last_error

    def _set_ai_runtime(self, provider=None, model=None, status=None, error=None):
        if provider is not None:
            self.last_ai_runtime["provider"] = provider
        if model is not None:
            self.last_ai_runtime["model"] = model
        if status is not None:
            self.last_ai_runtime["status"] = status
        if error is not None:
            self.last_ai_runtime["error"] = str(error)[:220]

    def get_ai_runtime_status(self):
        return dict(self.last_ai_runtime)

    def _get_pdf_debug_logger(self):
        import logging
        lg = getattr(self, "_dbg_log", None)
        if lg is not None:
            return lg
        lg = logging.getLogger("opuntia_pdf_debug")
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        if not lg.handlers:
            log_path = (os.getenv("OPUNTIA_DEBUG_LOG_PATH") or "").strip()
            if not log_path:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                log_dir = os.path.join(base_dir, "logs")
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except Exception:
                    pass
                log_path = os.path.join(log_dir, "pdf_debug.log")
            else:
                log_path = os.path.expanduser(os.path.expandvars(log_path))
                try:
                    parent = os.path.dirname(log_path)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                except Exception:
                    pass
            try:
                handler = logging.FileHandler(log_path, encoding="utf-8")
            except Exception:
                handler = logging.NullHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            lg.addHandler(handler)
        self._dbg_log = lg
        return lg

    def _is_affirmative(self, text):
        t = (text or "").strip().lower().strip("!.,?")
        return t in {
            "yes", "y", "yep", "yeah", "yea", "yah", "yup",
            "ok", "okay", "k", "okey",
            "sure", "sure thing", "of course", "absolutely", "definitely", "certainly",
            "go", "go ahead", "go on", "proceed", "do it", "let's do it", "let's go",
            "confirm", "confirmed", "allow", "allowed", "accept", "approved", "approve",
            "correct", "right", "true",
            "oui", "si", "bien sÃƒÂ»r", "bien sur", "ouais", "???", "????", "????",
        }

    def _is_negative(self, text):
        t = (text or "").strip().lower().strip("!.,?")
        return t in {
            "no", "n", "nope", "nah", "never",
            "cancel", "cancelled", "stop", "abort",
            "deny", "denied", "reject", "rejected", "refuse",
            "non", "??", "??",
        }

    def _is_reassurance_followup(self, text):
        t = re.sub(r"\s+", " ", (text or "").strip().lower()).strip("!.,? ").strip()
        if not t:
            return False
        if t in {"are you sure", "you sure", "sure", "really", "u sure"}:
            return True
        return bool(re.match(r"^(are\s+you\s+sure|you\s+sure|really)\??$", t))

    def _handle_reassurance_followup(self):
        if not self.conversation_history:
            return None
        last = self.conversation_history[-1] or {}
        prev_user = (last.get("user") or "").strip()
        prev_assistant = (last.get("assistant") or "").strip()
        context = f"{prev_user}\n{prev_assistant}".lower()
        if not re.search(r"\b(time|timezone|date\s+and\s+time|clock|france|paris|cest|cet)\b", context):
            return None
        france_line = ""
        if re.search(r"\b(france|paris|cest|cet)\b", context):
            try:
                from zoneinfo import ZoneInfo
                now_fr = datetime.now(ZoneInfo("Europe/Paris"))
                france_line = (
                    f" In France, it is {now_fr.strftime('%H:%M:%S')} {now_fr.tzname()} "
                    f"on {now_fr.strftime('%A, %B %d, %Y')}."
                )
            except Exception:
                pass
        return (
            "Yes. To match France on Windows, set your timezone to "
            "`(UTC+01:00) Brussels, Copenhagen, Madrid, Paris` and keep "
            "`Set time automatically` enabled."
            + france_line
        )

    def _is_greeting_location_query(self, text):
        t = (text or "").strip().lower()
        if not t:
            return False
        has_greeting_ctx = bool(re.search(r"\b(greetings?|startup|welcome|header|ui)\b", t))
        has_location_ctx = bool(re.search(r"\b(location|city|where|aubagne)\b", t))
        has_opuntia_ctx = bool(re.search(r"\b(opuntia|you)\b", t))
        wrong_city_ctx = bool(re.search(r"\b(not there|wrong|isn'?t right|im not there|i'?m not there)\b", t))
        return (has_greeting_ctx and has_location_ctx and has_opuntia_ctx) or (("aubagne" in t) and has_greeting_ctx) or wrong_city_ctx

    def _greeting_location_help_text(self):
        current = (self.user_city or "").strip()
        if current:
            return (
                f"The greeting location comes from your configured city: **{current}**.\n"
                "If you want to change it, say: `my city is Paris` (or your city)."
            )
        return (
            "You are right. That city in startup greeting came from automatic IP geolocation and can be wrong.\n"
            "I fixed Opuntia to avoid showing a guessed city unless you set one.\n"
            "If you want a fixed city in greeting, say: `my city is <your city>`."
        )

    def _set_pending_confirmation(self, action, payload, prompt):
        self.pending_question = None
        self.pending_confirmation = {"action": action, "payload": payload or {}}
        return prompt

    def _set_pending_question(self, header, question, options, action=None, payload=None, timeout_sec=None, on_deny=None):
        self.pending_confirmation = None
        req_id = f"perm-{int(time.time() * 1000)}"
        opts = []
        for opt in (options or []):
            if not isinstance(opt, dict):
                continue
            label = (opt.get("label") or "").strip()
            if not label:
                continue
            opts.append(
                {
                    "label": label,
                    "description": (opt.get("description") or "").strip(),
                    "value": (opt.get("value") or label).strip().lower(),
                }
            )
        if not opts:
            opts = [
                {"label": "Allow once", "description": "Execute this action now", "value": "allow"},
                {"label": "Deny", "description": "Do not execute this action", "value": "deny"},
            ]
        default_timeout = getattr(self, "permission_request_timeout_sec", 90)
        ttl = max(10, int(timeout_sec or default_timeout))
        self.pending_question = {
            "id": req_id,
            "header": (header or "Permission Request").strip(),
            "question": (question or "Allow this action?").strip(),
            "options": opts,
            "action": action or "",
            "payload": payload or {},
            "on_deny": on_deny or "Cancelled.",
            "created_at": time.time(),
            "expires_at": time.time() + ttl,
        }
        self._audit(
            "permission_request",
            "created",
            {"id": req_id, "header": header, "question": question, "action": action, "ttl_sec": ttl},
        )
        return self._format_pending_question_prompt(self.pending_question)

    def _format_pending_question_prompt(self, req, invalid=False):
        if not isinstance(req, dict):
            return "Permission request expired."
        remaining = max(0, int(req.get("expires_at", 0) - time.time()))
        lines = [
            f"[{req.get('id', 'perm')}] {req.get('header', 'Permission Request')}",
            req.get("question", "Allow this action?"),
        ]
        for idx, opt in enumerate(req.get("options") or [], start=1):
            label = opt.get("label", "")
            desc = opt.get("description", "")
            if desc:
                lines.append(f"{idx}. {label} - {desc}")
            else:
                lines.append(f"{idx}. {label}")
        lines.append(f"Reply with option number or label. Expires in {remaining}s.")
        if invalid:
            lines.append("I did not understand your choice.")
        return "\n".join(lines)

    def _resolve_pending_question_choice(self, text, req):
        t = (text or "").strip().lower()
        if not t:
            return None
        if self._is_affirmative(t):
            return "allow"
        if self._is_negative(t):
            return "deny"
        m = re.match(r"^\s*(\d+)\s*$", t)
        options = req.get("options") or []
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(options):
                return (options[idx].get("value") or "").lower()
            return None
        for opt in options:
            label = (opt.get("label") or "").strip().lower()
            value = (opt.get("value") or "").strip().lower()
            if t == label or t == value:
                return value
            if label and re.search(r'\b' + re.escape(label) + r'\b', t):
                return value
        return None

    def _format_plan_step_prompt(self, step_item, idx, total):
        action = (step_item or {}).get("action", "unknown")
        target = (step_item or {}).get("target", "")
        value = (step_item or {}).get("value", "")
        conf = (step_item or {}).get("confidence", "")
        bits = [f"Step {idx}/{total}", f"action={action}"]
        if target:
            bits.append(f"target={target}")
        if value:
            bits.append(f"value={value}")
        if conf != "":
            bits.append(f"confidence={conf}")
        return "Execute " + ", ".join(bits) + "? (yes/no)"

    def _plan_has_click_coordinates(self, step_item):
        x = (step_item or {}).get("x")
        y = (step_item or {}).get("y")
        return isinstance(x, (int, float)) and isinstance(y, (int, float))

    def _bbox_center_xy(self, bbox):
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None, None
        try:
            a, b, c, d = [float(v) for v in bbox]
            # Interpret as [x,y,w,h] when c,d look like size, else [left,top,right,bottom].
            if c >= 0 and d >= 0 and (a + c) > a and (b + d) > b:
                return int(a + (c / 2.0)), int(b + (d / 2.0))
            return int((a + c) / 2.0), int((b + d) / 2.0)
        except Exception:
            return None, None

    def _resolve_step_click_coordinates(self, step_item):
        if not isinstance(step_item, dict):
            return None, None
        if self._plan_has_click_coordinates(step_item):
            return int(step_item.get("x")), int(step_item.get("y"))

        # 1) Try step-level bbox.
        x, y = self._bbox_center_xy(step_item.get("bbox"))
        if x is not None and y is not None:
            step_item["x"], step_item["y"] = x, y
            return x, y

        # 2) Try matching target label in plan-level targets_meta.
        plan = self.last_screen_action_plan if isinstance(self.last_screen_action_plan, dict) else {}
        metas = plan.get("targets_meta") if isinstance(plan, dict) else None
        if isinstance(metas, list):
            target = str(step_item.get("target", "")).strip().lower()
            best = None
            best_score = -1
            for m in metas:
                if not isinstance(m, dict):
                    continue
                label = str(m.get("label", "")).strip().lower()
                bbox = m.get("bbox")
                if not label or not bbox:
                    continue
                score = 0
                if target and target == label:
                    score = 3
                elif target and (target in label or label in target):
                    score = 2
                elif target:
                    overlap = len(set(target.split()) & set(label.split()))
                    score = overlap
                if score > best_score:
                    best_score = score
                    best = m
            if best is not None and best_score > 0:
                x, y = self._bbox_center_xy(best.get("bbox"))
                if x is not None and y is not None:
                    step_item["x"], step_item["y"] = x, y
                    return x, y
        return None, None

    def _execute_plan_action(self, step_item):
        action = str((step_item or {}).get("action", "")).strip().lower()
        target = str((step_item or {}).get("target", "")).strip()
        value = str((step_item or {}).get("value", "")).strip()
        x = (step_item or {}).get("x")
        y = (step_item or {}).get("y")
        def _final(msg):
            _msg = str(msg or "")
            if re.search(r"\b(done|opened|waited|typed|scrolled)\b", _msg, re.IGNORECASE):
                self._record_task_outcome(f"plan_{action or 'step'}", "success", reason=_msg, details={"target": target, "value": value})
                return _msg
            if re.search(r"\b(skipped)\b", _msg, re.IGNORECASE):
                self._record_task_outcome(f"plan_{action or 'step'}", "pending", reason=_msg, details={"target": target, "value": value})
                return _msg
            self._record_task_outcome(f"plan_{action or 'step'}", "failed", reason=_msg, details={"target": target, "value": value})
            return self._maybe_attach_failure_playbook(_msg, action_hint=f"plan_{action}", details={"target": target, "value": value})

        if action in {"click", "double_click", "right_click"}:
            if not self._plan_has_click_coordinates(step_item):
                rx, ry = self._resolve_step_click_coordinates(step_item)
                if rx is not None and ry is not None:
                    x, y = rx, ry
            if not self._plan_has_click_coordinates(step_item):
                return _final(f"Skipped {action}: missing x/y coordinates for target '{target}'.")
            try:
                if action == "click":
                    pyautogui.click(x=int(x), y=int(y))
                elif action == "double_click":
                    pyautogui.doubleClick(x=int(x), y=int(y))
                else:
                    pyautogui.rightClick(x=int(x), y=int(y))
                return _final(f"Done: {action} at ({int(x)}, {int(y)}).")
            except Exception as e:
                return _final(f"Failed {action}: {e}")

        if action == "type":
            if not value:
                return _final("Skipped type: empty value.")
            try:
                pyautogui.write(value, interval=0.015)
                return _final("Done: typed value.")
            except Exception as e:
                return _final(f"Failed type: {e}")

        if action == "hotkey":
            keys = [k.strip() for k in re.split(r"[+,]", value) if k.strip()]
            if not keys:
                return _final("Skipped hotkey: no keys provided.")
            try:
                pyautogui.hotkey(*keys)
                return _final(f"Done: hotkey {'+'.join(keys)}.")
            except Exception as e:
                return _final(f"Failed hotkey: {e}")

        if action == "scroll":
            amount = 0
            try:
                amount = int(float(value)) if value else 0
            except Exception:
                amount = 0
            if amount == 0:
                return _final("Skipped scroll: invalid value.")
            try:
                pyautogui.scroll(amount)
                return _final(f"Done: scrolled {amount}.")
            except Exception as e:
                return _final(f"Failed scroll: {e}")

        if action == "open_url":
            url = value or target
            if not url:
                return _final("Skipped open_url: empty URL.")
            if not re.match(r"^https?://", url, flags=re.IGNORECASE):
                url = "https://" + url
            try:
                webbrowser.open(url)
                return _final(f"Done: opened {url}.")
            except Exception as e:
                return _final(f"Failed open_url: {e}")

        if action == "wait":
            sec = 1.0
            try:
                sec = max(0.0, min(15.0, float(value or 1.0)))
            except Exception:
                sec = 1.0
            time.sleep(sec)
            return _final(f"Done: waited {sec:.1f}s.")

        return _final(f"Skipped unsupported action '{action}'.")

    def _start_plan_execution(self):
        plan = self.last_screen_action_plan or {}
        actions = plan.get("actions") if isinstance(plan, dict) else None
        if not isinstance(actions, list) or not actions:
            return "No executable screen action plan available yet."
        pol = self._autonomy_policy()
        if pol.get("auto_execute_plan_steps", False):
            logs = []
            for idx, step in enumerate(actions[:40], start=1):
                result = self._execute_plan_action(step)
                logs.append(f"{idx}. {result}")
                if re.search(r"\b(failed|error|could not|unable|blocked|denied)\b", str(result), re.IGNORECASE):
                    self._audit("screen_plan", "paused", {"step_index": idx, "reason": str(result)[:180]})
                    return "Screen plan auto-execution paused on failure:\n" + "\n".join(logs[-8:])
            self.pending_plan_execution = None
            return "Screen plan auto-execution completed.\n" + "\n".join(logs[-10:])
        self.pending_plan_execution = {"index": 0, "actions": actions}
        first = actions[0]
        prompt = self._format_plan_step_prompt(first, 1, len(actions))
        self.pending_confirmation = {
            "action": "execute_plan_step",
            "payload": {"step_item": first, "step_index": 0, "total": len(actions)},
        }
        return prompt

    def _cancel_plan_execution(self):
        self.pending_plan_execution = None
        return "Cancelled."

    def _run_next_plan_step_after(self, current_index):
        if not self.pending_plan_execution:
            return "Plan execution finished."
        actions = self.pending_plan_execution.get("actions") or []
        next_index = current_index + 1
        if next_index >= len(actions):
            self.pending_plan_execution = None
            return "Plan execution completed."
        next_step = actions[next_index]
        self.pending_plan_execution["index"] = next_index
        self.pending_confirmation = {
            "action": "execute_plan_step",
            "payload": {"step_item": next_step, "step_index": next_index, "total": len(actions)},
        }
        return self._format_plan_step_prompt(next_step, next_index + 1, len(actions))

    def _parse_workflow_plan_steps(self, raw_text):
        text = (raw_text or "").strip()
        if not text:
            return []
        # Try JSON first.
        try:
            m = re.search(r"```json\s*(\[[\s\S]*?\])\s*```", text, flags=re.IGNORECASE)
            arr = json.loads(m.group(1).strip()) if m else json.loads(text)
            if isinstance(arr, list):
                out = []
                for row in arr:
                    if isinstance(row, dict):
                        cmd = (row.get("command") or row.get("step") or "").strip()
                    else:
                        cmd = str(row).strip()
                    if cmd:
                        out.append(cmd[:240])
                return out[:24]
        except Exception:
            pass
        # Fallback: numbered lines.
        out = []
        for line in text.splitlines():
            line = re.sub(r"^\s*(?:\d+[\).\-\s]+|[-*]\s+)", "", line).strip()
            if line:
                out.append(line[:240])
        return out[:24]

    def _build_workflow_plan(self, goal_text):
        goal = (goal_text or "").strip()
        if not goal:
            return {"goal": "", "steps": []}
        prompt = (
            "Create a concise executable Windows task workflow.\n"
            "Output ONLY a JSON array of short command strings that Opuntia can execute.\n"
            "Rules: one action per step, imperative form, no explanations, max 12 steps."
        )
        steps = []
        try:
            plan_raw = self._call_ai(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": goal[:1200]},
                ]
            )
            steps = self._parse_workflow_plan_steps(plan_raw)
        except Exception:
            steps = []
        if not steps:
            steps = [goal[:240]]
        plan = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "goal": goal[:500],
            "steps": steps[:24],
            "cursor": 0,
        }
        self.pending_workflow_plan = plan
        self._audit("workflow_plan", "created", {"goal": goal[:180], "steps": len(plan["steps"])})
        return plan

    def _verify_workflow_step(self, step_cmd, response_text):
        msg = str(response_text or "")
        if re.search(r"\b(done|opened|saved|created|completed|running|success)\b", msg, re.IGNORECASE):
            return True
        if re.search(r"\b(failed|error|could not|unable|blocked|denied|timed out)\b", msg, re.IGNORECASE):
            return False
        # Neutral conversational outputs are treated as pass in workflow mode.
        return True

    def _attempt_recovery_chain(self, action_hint, step_cmd, failure_text):
        hint = (action_hint or "").strip().lower()
        cmd = (step_cmd or "").strip()
        fail = (failure_text or "").strip()
        attempts = []
        if hint in {"open_app", "open"}:
            target = re.sub(r"^\s*(open|launch)\s+", "", cmd, flags=re.IGNORECASE).strip()
            if target:
                suggestion = self._suggest_open_target(target)
                if suggestion and suggestion.lower() != target.lower():
                    attempts.append(f"open {suggestion}")
        if hint in {"open_url", "navigate", "search"}:
            if re.search(r"\bhttps?://", cmd, re.IGNORECASE):
                attempts.append(re.sub(r"\bopen\b", "search", cmd, flags=re.IGNORECASE))
        if hint in {"close_app", "close"}:
            target = re.sub(r"^\s*(close|quit)\s+", "", cmd, flags=re.IGNORECASE).strip()
            if target:
                attempts.append(f"check {target} running")
        # Generic fallback: ask status first, then retry exactly once.
        if not attempts:
            attempts.append(cmd)
        max_attempts = max(1, int(self._autonomy_policy().get("max_recovery_attempts", 1)))
        attempts = attempts[:max_attempts]
        for candidate in attempts:
            try:
                out = self.process_command(f"MODE_TASK::{candidate}")
            except Exception as e:
                out = f"Recovery failed: {e}"
            if out and not re.search(r"\b(failed|error|could not|unable|blocked|denied|timed out)\b", str(out), re.IGNORECASE):
                self._record_task_outcome("workflow_recovery", "success", reason=str(out), details={"candidate": candidate, "from": cmd})
                return f"Recovered via: `{candidate}`\n{out}"
        self._record_task_outcome("workflow_recovery", "failed", reason=fail or cmd, details={"from": cmd})
        return ""

    def _execute_workflow_plan(self, max_steps=24):
        plan = self.pending_workflow_plan if isinstance(self.pending_workflow_plan, dict) else None
        if not plan:
            return "No pending workflow plan. Use: plan workflow <goal>"
        steps = list(plan.get("steps") or [])
        if not steps:
            return "Workflow plan is empty."
        cursor = int(plan.get("cursor", 0))
        limit = min(len(steps), cursor + max(1, int(max_steps)))
        logs = []
        for idx in range(cursor, limit):
            step = (steps[idx] or "").strip()
            if not step:
                continue
            response = self.process_command(f"MODE_TASK::{step}")
            verified = self._verify_workflow_step(step, response)
            logs.append(f"{idx+1}. {step}\n{response}")
            if not verified:
                action_hint = "open_app" if re.match(r"^\s*(open|launch)\b", step, re.IGNORECASE) else \
                              "close_app" if re.match(r"^\s*(close|quit)\b", step, re.IGNORECASE) else \
                              "open_url" if re.search(r"\bhttps?://|navigate|visit\b", step, re.IGNORECASE) else "task"
                recovered = self._attempt_recovery_chain(action_hint, step, str(response))
                if recovered:
                    logs.append(f"Recovery:\n{recovered}")
                else:
                    plan["cursor"] = idx
                    self.pending_workflow_plan = plan
                    self._audit("workflow_plan", "paused", {"cursor": idx, "step": step[:140]})
                    return (
                        "Workflow paused at a failed step.\n\n"
                        + "\n\n".join(logs[-6:])
                        + "\n\nUse `run workflow` to retry after adjustment."
                    )
        plan["cursor"] = limit
        done = (limit >= len(steps))
        self.pending_workflow_plan = None if done else plan
        self._audit("workflow_plan", "completed" if done else "partial", {"cursor": limit, "total": len(steps)})
        return ("Workflow completed.\n\n" if done else "Workflow partially executed.\n\n") + "\n\n".join(logs[-8:])

    def _run_confirmed_action(self, action, payload):
        def _finish(text, action_name, details=None):
            msg = str(text or "")
            if re.search(r"\b(done|opened|saved|created|completed|running)\b", msg, re.IGNORECASE):
                self._record_task_outcome(action_name, "success", reason=msg, details=details if isinstance(details, dict) else {})
                return msg
            if re.search(r"\b(cancelled|authorization required|permission required)\b", msg, re.IGNORECASE):
                self._record_task_outcome(action_name, "pending", reason=msg, details=details if isinstance(details, dict) else {})
                return msg
            if re.search(r"\b(could not|failed|error|blocked|denied|unsupported|nothing was created)\b", msg, re.IGNORECASE):
                self._record_task_outcome(action_name, "failed", reason=msg, details=details if isinstance(details, dict) else {})
                return self._maybe_attach_failure_playbook(msg, action_hint=action_name, details=details if isinstance(details, dict) else {})
            return msg
        if action == "open_app":
            target = (payload or {}).get("target", "")
            if not target:
                return "Cancelled."
            opened = self.open_app(target)
            return _finish(opened or f"Could not open {target}", "open_app", {"target": target})
        if action == "close_app":
            target = (payload or {}).get("target", "")
            if not target:
                return "Cancelled."
            result = self.close_app(target)
            return _finish(result or f"Could not close {target}", "close_app", {"target": target})
        if action == "file_mutation":
            cmd = (payload or {}).get("command", "")
            allow_desktop = bool((payload or {}).get("allow_desktop", False))
            allow_outside_mcp = bool((payload or {}).get("allow_outside_mcp", False))
            if not cmd:
                return "Cancelled."
            out = self._handle_file_command(
                cmd,
                allow_desktop=allow_desktop,
                allow_mutation=True,
                allow_outside_mcp=allow_outside_mcp,
            )
            if out is None:
                return _finish("Could not execute file command.", "file_mutation", {"command": cmd[:240]})
            return _finish(out, "file_mutation", {"command": cmd[:240]})
        if action == "file_mutation_outside_allowed":
            cmd = (payload or {}).get("command", "")
            allow_desktop = bool((payload or {}).get("allow_desktop", False))
            if not cmd:
                return "Cancelled."
            out = self._handle_file_command(
                cmd,
                allow_desktop=allow_desktop,
                allow_mutation=True,
                allow_outside_mcp=True,
            )
            if out is None:
                return _finish("Could not execute file command.", "file_mutation", {"command": cmd[:240]})
            return _finish(out, "file_mutation", {"command": cmd[:240], "outside_mcp": True})
        if action == "file_tree_creation":
            operations = (payload or {}).get("operations") or []
            allow_desktop = bool((payload or {}).get("allow_desktop", False))
            if not operations:
                return "Cancelled."
            results = self._execute_file_tree(operations, allow_desktop=allow_desktop)
            if not results:
                return _finish("Nothing was created.", "file_tree_creation", {"count": 0})
            return _finish("Done! Created:\n" + "\n".join(f"  {r}" for r in results), "file_tree_creation", {"count": len(results)})
        if action == "create_word_doc":
            filepath  = (payload or {}).get("filepath", "")
            content   = (payload or {}).get("content", "")
            doc_title = (payload or {}).get("doc_title", "")
            if not filepath:
                return "Cancelled."
            return _finish(self._execute_word_creation(filepath, content, doc_title), "create_word_doc", {"filepath": filepath})
        if action == "create_word_doc_confirm":
            orig_input = (payload or {}).get("user_input", "")
            allow_desktop = bool((payload or {}).get("allow_desktop", True))
            if not orig_input:
                return "Cancelled."
            return _finish(
                self._handle_word_command(orig_input, allow_desktop=allow_desktop, allow_mutation=True),
                "create_word_doc_confirm",
                {"input": orig_input[:240]},
            )
        if action == "create_pdf_confirm":
            orig_input = (payload or {}).get("user_input", "")
            allow_desktop = bool((payload or {}).get("allow_desktop", True))
            if not orig_input:
                return "Cancelled."
            return _finish(
                self._handle_pdf_command(orig_input, allow_desktop=allow_desktop, allow_mutation=True),
                "create_pdf_confirm",
                {"input": orig_input[:240]},
            )
        if action == "create_word_doc_clarify":
            # User confirmed clarifying question â€” route through permission gate
            orig_input = (payload or {}).get("user_input", "")
            if not orig_input:
                return "Cancelled."
            return _finish(
                self._handle_word_command(orig_input, allow_desktop=True, allow_mutation=False),
                "create_word_doc_clarify",
                {"input": orig_input[:240]},
            )
        if action == "search_on_app":
            query = (payload or {}).get("query", "")
            app = (payload or {}).get("app", "")
            if not query:
                return "Cancelled."
            return _finish(self.search_web_on_app(query, app or None), "search_on_app", {"query": query[:180], "app": app})
        if action == "windows_power":
            power_action = (payload or {}).get("action", "")
            if not power_action:
                return "Cancelled."
            return _finish(self._execute_windows_power_action(power_action), "windows_power", {"action": power_action})
        if action == "execute_plan_step":
            step_item = (payload or {}).get("step_item") or {}
            step_index = int((payload or {}).get("step_index", 0))
            result = self._execute_plan_action(step_item)
            tail = self._run_next_plan_step_after(step_index)
            return _finish(result + "\n" + tail, "execute_plan_step", {"step_index": step_index})
        return "Cancelled."

    def _promote_history_to_training(self):
        """Move conversation_history into adaptive_examples (training), then clear context."""
        if not self.conversation_history:
            return
        seen = {(e.get("user", ""), e.get("assistant", "")) for e in self.adaptive_examples}
        added = 0
        for item in self.conversation_history:
            user = (item.get("user") or "").strip()
            assistant = (item.get("assistant") or "").strip()
            if not user or not assistant:
                continue
            key = (user, assistant)
            if key in seen:
                continue
            seen.add(key)
            self.adaptive_examples.append({
                "user": user[:500],
                "assistant": assistant[:900],
                "keywords": self._extract_keywords(user),
            })
            added += 1
        if added:
            self.adaptive_examples = self.adaptive_examples[-self.max_adaptive_examples:]
            self._save_adaptive_examples()
        self.conversation_history = []

    def start_new_session(self):
        """Called on new chat or app restart: forget conversation context, keep training data."""
        if self.memory_enabled:
            chat_recap = self._generate_session_recap_from_history(self.conversation_history, mode="chat")
            task_recap = self._generate_session_recap_from_history(self.task_conversation_history, mode="task")
            if chat_recap:
                self._append_session_recap("chat", chat_recap)
            if task_recap:
                self._append_session_recap("task", task_recap)
        if self.memory_enabled:
            self._promote_history_to_training()
            if self.learned_facts:
                self._save_learned_facts()
            self._save_task_outcomes()
            self._save_trajectory_memory()
            self._save_provider_stats()
            self._save_mcp_route_stats()
        self.conversation_history = []
        self.task_conversation_history = []
        self.last_live_web_query = ""
        self.last_live_web_error = ""
        self.last_structured_intent = ""
        self.last_structured_payload = {}
        self.last_screen_action_plan = None
        self.pending_plan_execution = None
        self.pending_workflow_plan = None
        self.pending_confirmation = None
        self.pending_question = None
        if self.user_profile:
            self.save_user_profile()
        self.load_user_profile()

    def _load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if "memory_enabled" in data:
                        self.memory_enabled = bool(data.get("memory_enabled"))
                    if "feedback_enabled" in data:
                        self.feedback_enabled = bool(data.get("feedback_enabled"))
                    if "private_mode" in data:
                        self.private_mode = bool(data.get("private_mode"))
                    if "memory_enabled_before_private" in data:
                        self._pre_private_memory_enabled = data.get("memory_enabled_before_private")
                    if "feedback_enabled_before_private" in data:
                        self._pre_private_feedback_enabled = data.get("feedback_enabled_before_private")
                    if "autonomy_profile" in data:
                        self.autonomy_profile = str(data.get("autonomy_profile") or self.autonomy_profile).strip().lower()
                    if "user_city" in data:
                        self.user_city = str(data.get("user_city") or "").strip()
            if self.private_mode:
                self.memory_enabled = False
                self.feedback_enabled = False
        except Exception:
            pass

    def _save_settings(self):
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "memory_enabled": bool(self.memory_enabled),
                        "feedback_enabled": bool(self.feedback_enabled),
                        "private_mode": bool(self.private_mode),
                        "memory_enabled_before_private": self._pre_private_memory_enabled,
                        "feedback_enabled_before_private": self._pre_private_feedback_enabled,
                        "autonomy_profile": self.autonomy_profile,
                        "user_city": self.user_city,
                    },
                    f,
                    indent=2,
                )
        except Exception:
            pass

    def _load_provider_stats(self):
        self.provider_health = {}
        self.provider_cooldown_until = {}
        self.provider_last_error = {}
        try:
            if not os.path.exists(self.provider_stats_file):
                return
            with open(self.provider_stats_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            ph = data.get("provider_health") or {}
            if isinstance(ph, dict):
                for provider, row in ph.items():
                    if not isinstance(row, dict):
                        continue
                    self.provider_health[str(provider)] = {
                        "ok": int(row.get("ok", 0) or 0),
                        "fail": int(row.get("fail", 0) or 0),
                        "avg_latency_ms": float(row.get("avg_latency_ms", 0.0) or 0.0),
                        "last_ok_ts": float(row.get("last_ok_ts", 0.0) or 0.0),
                        "last_fail_ts": float(row.get("last_fail_ts", 0.0) or 0.0),
                    }
            cd = data.get("provider_cooldown_until") or {}
            if isinstance(cd, dict):
                self.provider_cooldown_until = {str(k): float(v or 0.0) for k, v in cd.items()}
            le = data.get("provider_last_error") or {}
            if isinstance(le, dict):
                self.provider_last_error = {str(k): str(v or "")[:220] for k, v in le.items()}
        except Exception:
            self.provider_health = {}
            self.provider_cooldown_until = {}
            self.provider_last_error = {}

    def _save_provider_stats(self):
        try:
            os.makedirs(os.path.dirname(self.provider_stats_file), exist_ok=True)
            payload = {
                "provider_health": self.provider_health,
                "provider_cooldown_until": self.provider_cooldown_until,
                "provider_last_error": self.provider_last_error,
            }
            with open(self.provider_stats_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _record_provider_result(self, provider, ok, latency_ms=0.0, error_text=""):
        p = (provider or "").strip().lower()
        if not p:
            return
        row = self.provider_health.get(
            p,
            {"ok": 0, "fail": 0, "avg_latency_ms": 0.0, "last_ok_ts": 0.0, "last_fail_ts": 0.0},
        )
        now = time.time()
        if ok:
            row["ok"] = int(row.get("ok", 0)) + 1
            prev = float(row.get("avg_latency_ms", 0.0) or 0.0)
            if prev <= 0:
                row["avg_latency_ms"] = float(latency_ms or 0.0)
            else:
                row["avg_latency_ms"] = (prev * 0.82) + (float(latency_ms or 0.0) * 0.18)
            row["last_ok_ts"] = now
            self.provider_cooldown_until[p] = 0.0
            self.provider_last_error[p] = ""
        else:
            row["fail"] = int(row.get("fail", 0)) + 1
            row["last_fail_ts"] = now
            self.provider_last_error[p] = str(error_text or "")[:220]
            # Exponential-ish short cooldown after repeated failures.
            fail_n = max(1, int(row.get("fail", 1)))
            cooldown_sec = min(180.0, 5.0 * (1.4 ** min(8, fail_n)))
            self.provider_cooldown_until[p] = now + cooldown_sec
        self.provider_health[p] = row
        if ((row.get("ok", 0) + row.get("fail", 0)) % 4) == 0:
            self._save_provider_stats()

    def _provider_priority_score(self, provider, position_bias=0.0):
        p = (provider or "").strip().lower()
        now = time.time()
        cooldown = float(self.provider_cooldown_until.get(p, 0.0) or 0.0)
        if cooldown > now:
            return -9999.0
        row = self.provider_health.get(p, {})
        ok_n = float(row.get("ok", 0) or 0.0)
        fail_n = float(row.get("fail", 0) or 0.0)
        total = ok_n + fail_n
        success_ratio = (ok_n / total) if total > 0 else 0.6
        latency = float(row.get("avg_latency_ms", 0.0) or 0.0)
        latency_penalty = min(0.8, latency / 9000.0) if latency > 0 else 0.0
        recency_bonus = 0.0
        last_ok = float(row.get("last_ok_ts", 0.0) or 0.0)
        if last_ok > 0:
            age = max(0.0, now - last_ok)
            recency_bonus = max(0.0, 0.22 - min(0.22, age / 3600.0))
        fail_pressure = min(0.6, fail_n / max(1.0, total + 1.0))
        score = (success_ratio * 1.8) - latency_penalty - fail_pressure + recency_bonus + float(position_bias)
        return score

    def _provider_stats_text(self):
        providers = sorted(set(list(self.provider_health.keys()) + list(self.provider_cooldown_until.keys())))
        if not providers:
            return "Provider stats: no data yet."
        now = time.time()
        lines = ["Provider stats:"]
        for p in providers:
            row = self.provider_health.get(p, {})
            ok_n = int(row.get("ok", 0) or 0)
            fail_n = int(row.get("fail", 0) or 0)
            lat = float(row.get("avg_latency_ms", 0.0) or 0.0)
            cd_until = float(self.provider_cooldown_until.get(p, 0.0) or 0.0)
            cd_left = max(0.0, cd_until - now)
            err = (self.provider_last_error.get(p) or "").strip()
            line = f"- {p}: ok={ok_n}, fail={fail_n}, avg_latency={lat:.0f}ms, cooldown={cd_left:.0f}s"
            if err:
                line += f", last_error={err[:90]}"
            lines.append(line)
        return "\n".join(lines)

    def _configured_models_text(self):
        rows = [
            ("anthropic", self.anthropic_model, bool((self.anthropic_api_key or "").strip())),
            ("openai_compatible", self.openai_compat_model, bool((self.openai_compat_base_url or "").strip())),
            ("gemini", self.gemini_model, bool((self.gemini_api_key or "").strip())),
            ("qwen", self.qwen_model, bool((self.qwen_api_key or "").strip())),
            ("deepseek", self.deepseek_model, bool((self.deepseek_api_key or "").strip())),
            ("groq", self.groq_model, bool((self.groq_api_key or "").strip())),
        ]
        lines = []
        for provider, model, enabled in rows:
            lines.append(f"- {provider}: model={model}, enabled={'yes' if enabled else 'no'}")
        return "\n".join(lines)

    def _ai_model_status_text(self):
        runtime = self.get_ai_runtime_status()
        pref = (self.ai_provider or "auto").strip().lower()
        strict = bool(self.ai_provider_strict)
        return (
            "AI model status:\n"
            f"  - preferred_provider: {pref}\n"
            f"  - strict_provider: {strict}\n"
            f"  - last_runtime_provider: {runtime.get('provider', 'unknown')}\n"
            f"  - last_runtime_model: {runtime.get('model', 'unknown')}\n"
            f"  - last_runtime_status: {runtime.get('status', 'unknown')}\n"
            "Configured models:\n"
            f"{self._configured_models_text()}"
        )

    def _reset_provider_stats(self):
        self.provider_health = {}
        self.provider_cooldown_until = {}
        self.provider_last_error = {}
        self._save_provider_stats()

    def _load_mcp_route_stats(self):
        self.mcp_route_stats = {}
        try:
            if not os.path.exists(self.mcp_route_stats_file):
                return
            with open(self.mcp_route_stats_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            rs = data.get("routes") if isinstance(data.get("routes"), dict) else data
            if not isinstance(rs, dict):
                return
            cleaned = {}
            for action, row in rs.items():
                if not isinstance(row, dict):
                    continue
                cleaned[str(action)] = {
                    "mcp_ok": int(row.get("mcp_ok", 0) or 0),
                    "mcp_fail": int(row.get("mcp_fail", 0) or 0),
                    "local_ok": int(row.get("local_ok", 0) or 0),
                    "local_fail": int(row.get("local_fail", 0) or 0),
                    "last_error": str(row.get("last_error", "") or "")[:220],
                }
            self.mcp_route_stats = cleaned
        except Exception:
            self.mcp_route_stats = {}

    def _save_mcp_route_stats(self):
        try:
            os.makedirs(os.path.dirname(self.mcp_route_stats_file), exist_ok=True)
            with open(self.mcp_route_stats_file, "w", encoding="utf-8") as f:
                json.dump({"routes": self.mcp_route_stats}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _record_file_route_result(self, action_key, route, ok, error_text=""):
        k = str(action_key or "file_op").strip().lower()
        rt = "mcp" if str(route or "").strip().lower() == "mcp" else "local"
        row = self.mcp_route_stats.get(
            k,
            {"mcp_ok": 0, "mcp_fail": 0, "local_ok": 0, "local_fail": 0, "last_error": ""},
        )
        field = f"{rt}_{'ok' if ok else 'fail'}"
        row[field] = int(row.get(field, 0) or 0) + 1
        if not ok and error_text:
            row["last_error"] = str(error_text)[:220]
        self.mcp_route_stats[k] = row
        total = int(row.get("mcp_ok", 0) + row.get("mcp_fail", 0) + row.get("local_ok", 0) + row.get("local_fail", 0))
        if total % 4 == 0:
            self._save_mcp_route_stats()

    def _prefer_mcp_for_action(self, action_key):
        if not self.mcp_enabled or self.mcp_bridge is None:
            return False
        k = str(action_key or "").strip().lower()
        row = self.mcp_route_stats.get(k, {})
        m_ok = float(row.get("mcp_ok", 0) or 0.0)
        m_fail = float(row.get("mcp_fail", 0) or 0.0)
        l_ok = float(row.get("local_ok", 0) or 0.0)
        l_fail = float(row.get("local_fail", 0) or 0.0)
        # Default bias: MCP-first for read/list/search/move operations.
        if (m_ok + m_fail + l_ok + l_fail) < 2:
            return k in {"list_files", "read_file", "search_files", "create_folder", "write_file", "move_file"}
        m_score = (m_ok + 1.0) / (m_ok + m_fail + 2.0)
        l_score = (l_ok + 1.0) / (l_ok + l_fail + 2.0)
        return m_score >= (l_score - 0.03)

    def _mcp_routing_status_text(self):
        if not self.mcp_route_stats:
            return "MCP routing: no history yet."
        lines = ["MCP routing stats:"]
        for action in sorted(self.mcp_route_stats.keys()):
            row = self.mcp_route_stats.get(action, {})
            lines.append(
                f"- {action}: mcp(ok={int(row.get('mcp_ok',0))}, fail={int(row.get('mcp_fail',0))}) "
                f"local(ok={int(row.get('local_ok',0))}, fail={int(row.get('local_fail',0))}) "
                f"prefer={'mcp' if self._prefer_mcp_for_action(action) else 'local'}"
            )
        return "\n".join(lines)

    def _mcp_server_name(self):
        if self.mcp_bridge is None:
            return ""
        names = self.mcp_bridge.list_servers() if hasattr(self.mcp_bridge, "list_servers") else []
        pref = (self.mcp_default_server or "").strip().lower()
        if pref and pref in names:
            return pref
        if names:
            return names[0]
        return ""

    def _mcp_allowed_directories(self, force=False):
        now = time.time()
        if (not force) and self._mcp_allowed_dirs_cache and (now - float(self._mcp_allowed_dirs_ts or 0.0) <= max(10, self.mcp_allowed_dirs_ttl_sec)):
            return list(self._mcp_allowed_dirs_cache)
        server = self._mcp_server_name()
        if not server or self.mcp_bridge is None:
            return []
        ok, out = self.mcp_bridge.call_tool(server, "list_allowed_directories", {})
        if not ok:
            return []
        payload = ""
        if isinstance(out, dict):
            payload = str(out.get("output") or "")
        else:
            payload = str(out or "")
        dirs = []
        try:
            # Try JSON parse first
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                arr = parsed.get("allowedDirectories") or parsed.get("allowed_directories") or parsed.get("directories") or []
            elif isinstance(parsed, list):
                arr = parsed
            else:
                arr = []
            for p in arr:
                if isinstance(p, str) and p.strip():
                    dirs.append(os.path.realpath(os.path.abspath(p.strip())))
        except Exception:
            for m in re.findall(r"[A-Za-z]:\\\\[^\"'\n\r,\]]+", payload):
                dirs.append(os.path.realpath(os.path.abspath(m.strip())))
        dirs = sorted(set([d for d in dirs if d and os.path.isabs(d)]))
        self._mcp_allowed_dirs_cache = dirs
        self._mcp_allowed_dirs_ts = now
        return dirs

    def _path_within_roots(self, path_value, roots):
        try:
            p = os.path.normcase(os.path.realpath(os.path.abspath(str(path_value or "").strip())))
        except Exception:
            return False
        for r in roots or []:
            try:
                rc = os.path.normcase(os.path.realpath(os.path.abspath(str(r or "").strip())))
            except Exception:
                continue
            if p == rc or p.startswith(rc + os.sep):
                return True
        return False

    def _mcp_write_allowed(self, path_value):
        roots = self._mcp_allowed_directories(force=False)
        if not roots:
            return True
        return self._path_within_roots(path_value, roots)

    def _mcp_call_filesystem_tool(self, tool_name, arguments, action_key="file_op"):
        if not self.mcp_enabled or self.mcp_bridge is None:
            return False, "MCP unavailable."
        server = self._mcp_server_name()
        if not server:
            self._record_file_route_result(action_key, "mcp", False, error_text="no server configured")
            return False, "No MCP server configured."
        ok, out = self.mcp_bridge.call_tool(server, tool_name, arguments if isinstance(arguments, dict) else {})
        if not ok:
            self._record_file_route_result(action_key, "mcp", False, error_text=str(out))
            return False, str(out)
        msg = str((out or {}).get("output") if isinstance(out, dict) else out or "").strip()
        self._record_file_route_result(action_key, "mcp", True)
        return True, msg

    def _mcp_status_text(self):
        if not self.mcp_enabled:
            return "MCP is disabled (`MCP_ENABLED=0`)."
        if self.mcp_bridge is None:
            return "MCP bridge unavailable. Install dependency with: pip install mcp"
        st = self.mcp_bridge.status_dict() if hasattr(self.mcp_bridge, "status_dict") else {}
        server = self._mcp_server_name()
        return (
            "MCP status:\n"
            f"  - sdk_available: {bool(st.get('sdk_available', False))}\n"
            f"  - http_available: {bool(st.get('http_available', False))}\n"
            f"  - servers_count: {int(st.get('servers_count', 0))}\n"
            f"  - default_server: {server or 'none'}\n"
            f"  - config_path: {st.get('config_path', self.mcp_config_path)}\n"
            f"  - route_stats: {len(self.mcp_route_stats)} actions tracked\n"
            f"  - load_error: {st.get('load_error', '') or 'none'}"
        )

    def _mcp_servers_text(self):
        if not self.mcp_enabled:
            return "MCP is disabled."
        if self.mcp_bridge is None:
            return "MCP bridge unavailable. Install dependency with: pip install mcp"
        names = self.mcp_bridge.list_servers() if hasattr(self.mcp_bridge, "list_servers") else []
        if not names:
            return (
                "No MCP servers configured.\n"
                f"Create `{self.mcp_config_path}` with a `servers` object (or top-level map)."
            )
        lines = ["Configured MCP servers:"]
        for n in names:
            lines.append(f"- {n}")
        return "\n".join(lines)

    def _mcp_tools_text(self, server_name):
        if not self.mcp_enabled:
            return "MCP is disabled."
        if self.mcp_bridge is None:
            return "MCP bridge unavailable. Install dependency with: pip install mcp"
        ok, out = self.mcp_bridge.list_tools(server_name)
        if not ok:
            return str(out)
        tools = out if isinstance(out, list) else []
        if not tools:
            return f"MCP server `{server_name}` has no tools."
        lines = [f"MCP tools on `{server_name}` ({len(tools)}):"]
        for t in tools[:80]:
            name = str((t or {}).get("name") or "").strip()
            desc = str((t or {}).get("description") or "").strip()
            if not name:
                continue
            if desc:
                lines.append(f"- {name}: {desc[:140]}")
            else:
                lines.append(f"- {name}")
        return "\n".join(lines)

    def _mcp_call_text(self, server_name, tool_name, args_obj):
        if not self.mcp_enabled:
            return "MCP is disabled."
        if self.mcp_bridge is None:
            return "MCP bridge unavailable. Install dependency with: pip install mcp"
        ok, out = self.mcp_bridge.call_tool(server_name, tool_name, args_obj if isinstance(args_obj, dict) else {})
        if not ok:
            return str(out)
        if isinstance(out, dict):
            payload = str(out.get("output") or "").strip()
            lat = int(out.get("latency_ms", 0) or 0)
            if payload:
                return f"MCP `{server_name}.{tool_name}` ({lat} ms):\n{payload}"
            return f"MCP `{server_name}.{tool_name}` finished ({lat} ms)."
        return str(out)

    def _autonomy_policy(self):
        mode = (self.autonomy_profile or "balanced").strip().lower()
        if mode not in {"safe", "balanced", "autonomous"}:
            mode = "balanced"
            self.autonomy_profile = "balanced"
        if mode == "safe":
            return {
                "mode": "safe",
                "require_sensitive_confirmation": True,
                "auto_execute_plan_steps": False,
                "max_recovery_attempts": 1,
                "verify_steps": True,
            }
        if mode == "autonomous":
            return {
                "mode": "autonomous",
                "require_sensitive_confirmation": False,
                "auto_execute_plan_steps": True,
                "max_recovery_attempts": 3,
                "verify_steps": True,
            }
        return {
            "mode": "balanced",
            "require_sensitive_confirmation": True,
            "auto_execute_plan_steps": False,
            "max_recovery_attempts": 2,
            "verify_steps": True,
        }

    def set_autonomy_profile(self, profile, persist=True):
        p = (profile or "").strip().lower()
        if p not in {"safe", "balanced", "autonomous"}:
            return False, "Unknown autonomy profile. Use: safe, balanced, autonomous."
        self.autonomy_profile = p
        if persist:
            self._save_settings()
        self._audit("autonomy_profile", "set", {"mode": p})
        return True, f"Autonomy profile set to {p}."

    def _autonomy_status_text(self):
        pol = self._autonomy_policy()
        return (
            "Autonomy profile:\n"
            f"  - mode: {pol['mode']}\n"
            f"  - require_sensitive_confirmation: {pol['require_sensitive_confirmation']}\n"
            f"  - auto_execute_plan_steps: {pol['auto_execute_plan_steps']}\n"
            f"  - max_recovery_attempts: {pol['max_recovery_attempts']}\n"
            f"  - verify_steps: {pol['verify_steps']}"
        )

    def set_memory_enabled(self, enabled, persist=True):
        self.memory_enabled = bool(enabled)
        if persist:
            self._save_settings()
        if not self.memory_enabled:
            self.conversation_history = []

    def set_feedback_enabled(self, enabled, persist=True):
        self.feedback_enabled = bool(enabled)
        if persist:
            self._save_settings()

    def set_private_mode(self, enabled, persist=True):
        enabled = bool(enabled)
        if enabled:
            if self._pre_private_memory_enabled is None:
                self._pre_private_memory_enabled = bool(self.memory_enabled)
            if self._pre_private_feedback_enabled is None:
                self._pre_private_feedback_enabled = bool(self.feedback_enabled)
            self.private_mode = True
            self.memory_enabled = False
            self.feedback_enabled = False
            self.conversation_history = []
        else:
            self.private_mode = False
            if self._pre_private_memory_enabled is not None:
                self.memory_enabled = bool(self._pre_private_memory_enabled)
            if self._pre_private_feedback_enabled is not None:
                self.feedback_enabled = bool(self._pre_private_feedback_enabled)
            self._pre_private_memory_enabled = None
            self._pre_private_feedback_enabled = None
        if persist:
            self._save_settings()

    def load_memory(self):
        if not self.memory_enabled:
            self.conversation_history = []
            return
        try:
            merged = []
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    merged.extend([d for d in data if isinstance(d, dict)])
            if os.path.exists(self.memory_journal_file):
                with open(self.memory_journal_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = (line or "").strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except Exception:
                            continue
                        if isinstance(row, dict):
                            merged.append(row)
            if merged:
                cleaned = []
                for row in merged[-self.max_memory_items:]:
                    if not isinstance(row, dict):
                        continue
                    u = self._safe_memory_text(row.get("user") or "", max_len=900)
                    a = self._safe_memory_text(row.get("assistant") or "", max_len=1500)
                    if not u and not a:
                        continue
                    cleaned.append(
                        {
                            "timestamp": row.get("timestamp") or datetime.now().isoformat(timespec="seconds"),
                            "user": u,
                            "assistant": a,
                            "keywords": row.get("keywords") or self._extract_keywords(u),
                        }
                    )
                self.conversation_history = cleaned[-self.max_memory_items:]
        except Exception:
            self.conversation_history = []

    def save_memory(self):
        if not self.memory_enabled:
            return
        try:
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.conversation_history[-self.max_memory_items:], f, indent=2)
        except Exception:
            pass

    def _safe_memory_text(self, text, max_len=1600):
        raw = str(text or "")
        if validate_memory_text is None:
            cleaned = re.sub(r"\s+", " ", raw).strip()[: max(80, int(max_len))]
            return cleaned
        ok, reason, cleaned = validate_memory_text(raw, max_len=max_len)
        if not ok:
            self.memory_safety_block_count = int(getattr(self, "memory_safety_block_count", 0)) + 1
            self._audit("memory_safety", "blocked", {"reason": reason, "sample": cleaned[:120]})
            return ""
        return cleaned

    def load_session_recaps(self):
        self.session_recaps = []
        if not self.memory_enabled:
            return
        try:
            if os.path.exists(self.session_recaps_file):
                with open(self.session_recaps_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    cleaned = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        summary = self._safe_memory_text(item.get("summary") or "", max_len=1200)
                        if not summary:
                            continue
                        cleaned.append(
                            {
                                "timestamp": item.get("timestamp") or datetime.now().isoformat(timespec="seconds"),
                                "mode": (item.get("mode") or "chat").strip().lower(),
                                "summary": summary[:1200],
                                "keywords": item.get("keywords") or self._extract_keywords(summary),
                            }
                        )
                    self.session_recaps = cleaned[-self.max_session_recaps:]
        except Exception:
            self.session_recaps = []

    def _save_session_recaps(self):
        try:
            os.makedirs(os.path.dirname(self.session_recaps_file), exist_ok=True)
            with open(self.session_recaps_file, "w", encoding="utf-8") as f:
                json.dump(self.session_recaps[-self.max_session_recaps:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _append_session_recap(self, mode, summary):
        if not self.memory_enabled:
            return
        text = self._safe_memory_text(summary or "", max_len=1200)
        if not text:
            return
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": (mode or "chat").strip().lower(),
            "summary": text[:1200],
            "keywords": self._extract_keywords(text),
        }
        self.session_recaps.append(entry)
        self.session_recaps = self.session_recaps[-self.max_session_recaps:]
        self._save_session_recaps()

    def load_task_outcomes(self):
        self.task_outcomes = []
        self.failure_patterns = {}
        if not self.memory_enabled:
            return
        try:
            if not os.path.exists(self.task_outcomes_file):
                return
            with open(self.task_outcomes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            events = data.get("events") or []
            if isinstance(events, list):
                cleaned = []
                for row in events:
                    if not isinstance(row, dict):
                        continue
                    action = (row.get("action") or "").strip().lower()
                    status = (row.get("status") or "").strip().lower()
                    if not action or not status:
                        continue
                    cleaned.append(
                        {
                            "ts": row.get("ts") or datetime.now().isoformat(timespec="seconds"),
                            "action": action[:80],
                            "status": status[:40],
                            "reason": self._safe_memory_text(row.get("reason") or "", max_len=220),
                            "details": row.get("details") if isinstance(row.get("details"), dict) else {},
                        }
                    )
                self.task_outcomes = cleaned[-self.max_task_outcomes:]
            patterns = data.get("failure_patterns") or {}
            if isinstance(patterns, dict):
                self.failure_patterns = {str(k): int(v) for k, v in patterns.items() if str(k).strip()}
        except Exception:
            self.task_outcomes = []
            self.failure_patterns = {}

    def _save_task_outcomes(self):
        try:
            os.makedirs(os.path.dirname(self.task_outcomes_file), exist_ok=True)
            payload = {
                "events": self.task_outcomes[-self.max_task_outcomes:],
                "failure_patterns": self.failure_patterns,
            }
            with open(self.task_outcomes_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_trajectory_memory(self):
        self.trajectory_memory = []
        self._trajectory_source_cursor = len(self.task_outcomes)
        if not self.memory_enabled:
            return
        try:
            if not os.path.exists(self.trajectory_memory_file):
                return
            with open(self.trajectory_memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            rows = []
            cursor = 0
            if isinstance(data, dict):
                rows = data.get("trajectories") or []
                cursor = int(data.get("source_cursor", 0) or 0)
            elif isinstance(data, list):
                rows = data
            cleaned = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                summary = self._safe_memory_text(row.get("summary") or "", max_len=1400)
                if not summary:
                    continue
                cleaned.append(
                    {
                        "ts": row.get("ts") or datetime.now().isoformat(timespec="seconds"),
                        "span": row.get("span") or "",
                        "summary": summary,
                        "keywords": row.get("keywords") or self._extract_keywords(summary),
                        "failure_tags": row.get("failure_tags") if isinstance(row.get("failure_tags"), list) else [],
                        "actions": row.get("actions") if isinstance(row.get("actions"), list) else [],
                    }
                )
            self.trajectory_memory = cleaned[-self.max_trajectories:]
            self._trajectory_source_cursor = max(0, min(len(self.task_outcomes), cursor if cursor > 0 else len(self.task_outcomes)))
        except Exception:
            self.trajectory_memory = []
            self._trajectory_source_cursor = len(self.task_outcomes)

    def _save_trajectory_memory(self):
        try:
            os.makedirs(os.path.dirname(self.trajectory_memory_file), exist_ok=True)
            payload = {
                "source_cursor": int(self._trajectory_source_cursor),
                "trajectories": self.trajectory_memory[-self.max_trajectories:],
            }
            with open(self.trajectory_memory_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _summarize_outcome_chunk(self, rows):
        if not rows:
            return ""
        preview = []
        for r in rows[-20:]:
            preview.append(
                f"[{r.get('ts','')}] action={r.get('action','')} status={r.get('status','')} reason={r.get('reason','')}"
            )
        text = "\n".join(preview)
        if not text:
            return ""
        try:
            summary = self._call_ai(
                [
                    {
                        "role": "system",
                        "content": (
                            "Compress this task trajectory into operational memory. "
                            "Return 5-8 bullets: wins, repeated failures, root causes, and best next strategies."
                        ),
                    },
                    {"role": "user", "content": text[:5000]},
                ]
            ).strip()
        except Exception:
            summary = ""
        if not summary:
            summary = text.replace("\n", " ")[:900]
        return self._safe_memory_text(summary, max_len=1400)

    def _maybe_compact_trajectory(self):
        if not self.memory_enabled:
            return
        cursor = max(0, int(getattr(self, "_trajectory_source_cursor", 0)))
        if len(self.task_outcomes) - cursor < max(3, int(self.trajectory_compact_trigger)):
            return
        chunk = self.task_outcomes[cursor:]
        if not chunk:
            return
        summary = self._summarize_outcome_chunk(chunk)
        if not summary:
            self._trajectory_source_cursor = len(self.task_outcomes)
            return
        failure_tags = []
        actions = []
        for row in chunk:
            action = row.get("action") or ""
            if action and action not in actions:
                actions.append(action)
            if row.get("status") == "failed":
                failure_tags.append(self._classify_failure_reason(row.get("reason") or ""))
        traj = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "span": f"{chunk[0].get('ts','')} -> {chunk[-1].get('ts','')}",
            "summary": summary,
            "keywords": self._extract_keywords(summary),
            "failure_tags": list(dict.fromkeys([t for t in failure_tags if t]))[:10],
            "actions": actions[:12],
        }
        self.trajectory_memory.append(traj)
        self.trajectory_memory = self.trajectory_memory[-self.max_trajectories:]
        self._trajectory_source_cursor = len(self.task_outcomes)
        self._save_trajectory_memory()

    def _build_trajectory_context(self, user_input, limit=2):
        if not self.memory_enabled or not self.trajectory_memory:
            return ""
        qk = set(self._extract_keywords(user_input))
        ranked = []
        total = len(self.trajectory_memory)
        for idx, row in enumerate(self.trajectory_memory):
            keywords = set(row.get("keywords") or [])
            overlap = len(qk.intersection(keywords))
            recency = (idx + 1) / max(1, total)
            score = overlap * 2.2 + recency
            if qk and overlap <= 0:
                score -= 0.6
            ranked.append((score, row))
        ranked.sort(key=lambda x: x[0], reverse=True)
        selected = [row for _, row in ranked[:max(1, int(limit))]]
        if not selected:
            return ""
        lines = []
        for row in selected:
            ts = row.get("ts") or ""
            span = row.get("span") or ""
            summary = (row.get("summary") or "").strip()
            if summary:
                lines.append(f"- [{ts}] ({span}) {summary}")
        if not lines:
            return ""
        return ("Trajectory memory (compressed execution lessons):\n" + "\n".join(lines))[:1700]

    def _trajectory_status_text(self):
        return (
            "Trajectory memory:\n"
            f"  - trajectories: {len(self.trajectory_memory)}\n"
            f"  - source_cursor: {int(self._trajectory_source_cursor)}\n"
            f"  - compact_trigger: {int(self.trajectory_compact_trigger)}\n"
            f"  - file: {self.trajectory_memory_file}"
        )

    def _trajectory_recent_text(self, limit=6):
        rows = self.trajectory_memory[-max(1, int(limit)):]
        if not rows:
            return "(no trajectories)"
        out = []
        for row in rows:
            ts = row.get("ts") or ""
            summary = (row.get("summary") or "").replace("\n", " ").strip()
            out.append(f"- [{ts}] {summary[:220]}")
        return "\n".join(out)

    def _classify_failure_reason(self, text):
        t = (text or "").strip().lower()
        if not t:
            return "unknown"
        checks = [
            ("permission_denied", r"\b(permission|access is denied|denied|not allowed|blocked)\b"),
            ("not_found", r"\b(not found|could not find|no such|doesn't exist|does not exist)\b"),
            ("timeout", r"\b(timeout|timed out|deadline)\b"),
            ("network", r"\b(network|internet|dns|connection|unreachable)\b"),
            ("auth", r"\b(auth|api key|unauthorized|forbidden|401|403)\b"),
            ("validation", r"\b(invalid|missing|required|empty|unsupported|bad request)\b"),
            ("runtime_error", r"\b(error|exception|traceback|failed)\b"),
        ]
        for label, pattern in checks:
            if re.search(pattern, t, re.IGNORECASE):
                return label
        return "unknown"

    def _record_task_outcome(self, action, status, reason="", details=None):
        if not self.memory_enabled:
            return
        action = (action or "").strip().lower()
        status = (status or "").strip().lower()
        if not action or not status:
            return
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "action": action[:80],
            "status": status[:40],
            "reason": self._safe_memory_text(reason or "", max_len=220),
            "details": details if isinstance(details, dict) else {},
        }
        self.task_outcomes.append(entry)
        self.task_outcomes = self.task_outcomes[-self.max_task_outcomes:]
        if status in {"failed", "blocked", "error", "timeout", "denied", "partial"}:
            tag = self._classify_failure_reason(reason)
            key = f"{action}:{tag}"
            self.failure_patterns[key] = int(self.failure_patterns.get(key, 0)) + 1
        if len(self.task_outcomes) % 5 == 0:
            self._save_task_outcomes()
        self._maybe_compact_trajectory()

    def _record_task_outcome_from_audit(self, action, status, details=None):
        action_l = (action or "").strip().lower()
        status_l = (status or "").strip().lower()
        if not action_l or not status_l:
            return
        success_statuses = {"allowed", "ok", "approved", "granted", "completed", "done"}
        failure_statuses = {"blocked", "error", "denied", "timeout", "partial"}
        mapped = ""
        if status_l in success_statuses:
            mapped = "success"
        elif status_l in failure_statuses:
            mapped = "failed"
        elif status_l in {"permission_requested", "requested"}:
            mapped = "pending"
        if not mapped:
            return
        reason = ""
        if isinstance(details, dict):
            reason = (
                str(details.get("reason") or details.get("error") or details.get("message") or "").strip()
                or str(details.get("target") or "").strip()
            )
        self._record_task_outcome(action_l, mapped, reason=reason, details=details if isinstance(details, dict) else {})

    def _task_outcomes_status_text(self):
        rows = list(self.task_outcomes or [])
        if not rows:
            return "No task outcomes recorded yet."
        total = len(rows)
        success = len([r for r in rows if r.get("status") == "success"])
        failed = len([r for r in rows if r.get("status") == "failed"])
        pending = len([r for r in rows if r.get("status") == "pending"])
        success_rate = (success / max(1, success + failed)) * 100.0
        top_fail = sorted(self.failure_patterns.items(), key=lambda kv: kv[1], reverse=True)[:5]
        lines = [
            "Task outcomes:",
            f"  - total: {total}",
            f"  - success: {success}",
            f"  - failed: {failed}",
            f"  - pending: {pending}",
            f"  - success_rate: {success_rate:.1f}%",
        ]
        if top_fail:
            lines.append("  - top_failures:")
            for key, count in top_fail:
                lines.append(f"    * {key} ({count})")
        return "\n".join(lines)

    def _task_outcomes_recent_text(self, limit=12):
        rows = self.task_outcomes[-max(1, int(limit)):]
        if not rows:
            return "(no recent outcomes)"
        out = []
        for row in rows:
            ts = row.get("ts") or ""
            action = row.get("action") or "task"
            status = row.get("status") or "unknown"
            reason = (row.get("reason") or "").strip()
            suffix = f" | {reason[:120]}" if reason else ""
            out.append(f"- [{ts}] {action}: {status}{suffix}")
        return "\n".join(out)

    def _build_failure_playbook_text(self, action, reason="", details=None):
        action_l = (action or "").strip().lower()
        reason_tag = self._classify_failure_reason(reason)
        if not action_l:
            action_l = "task"
        lines = [f"Playbook for `{action_l}` failure ({reason_tag}):"]
        if action_l in {"open_app", "close_app"}:
            lines.extend(
                [
                    "1. Check the exact app name and try the executable name if needed.",
                    "2. Verify the app appears in running apps list before close/open attempts.",
                    "3. Retry with a simpler command: `open <app>` or `close <app>`.",
                ]
            )
        elif action_l.startswith("file") or action_l in {"create_pdf", "create_word_doc", "file_mutation"}:
            lines.extend(
                [
                    "1. Confirm target path exists and you have write permissions.",
                    "2. Avoid special characters in file names and retry.",
                    "3. If blocked, approve the permission prompt and run again.",
                ]
            )
        elif action_l in {"search_on_app", "open_url", "web_search"}:
            lines.extend(
                [
                    "1. Verify internet connectivity and retry with a direct URL/query.",
                    "2. Try default browser if a specific browser hint fails.",
                    "3. If timeout persists, shorten query and rerun.",
                ]
            )
        else:
            lines.extend(
                [
                    "1. Retry with a shorter, explicit command.",
                    "2. Confirm required permission prompts are approved.",
                    "3. If still failing, switch to step-by-step execution.",
                ]
            )
        if reason_tag == "permission_denied":
            lines.append("Extra: permission was denied/blocked, so allow-once is required for this action.")
        if reason_tag == "not_found":
            lines.append("Extra: target could not be found, so use exact names or full paths.")
        if reason_tag == "timeout":
            lines.append("Extra: timeout detected, so retry with fewer steps per command.")
        return "\n".join(lines)

    def _playbook_for_query_text(self, query):
        q = (query or "").strip().lower()
        if not q:
            top = sorted(self.failure_patterns.items(), key=lambda kv: kv[1], reverse=True)[:1]
            if top:
                action = top[0][0].split(":", 1)[0]
                return self._build_failure_playbook_text(action, reason=top[0][0])
            return "No failure playbook data yet."
        rows = [r for r in reversed(self.task_outcomes) if q in (r.get("action") or "") or q in (r.get("reason") or "").lower()]
        if rows:
            row = rows[0]
            return self._build_failure_playbook_text(row.get("action"), reason=row.get("reason"), details=row.get("details"))
        if q in {"open", "open_app", "close", "close_app"}:
            return self._build_failure_playbook_text("open_app" if "open" in q else "close_app", reason=q)
        if q in {"file", "pdf", "doc", "word", "mutation"}:
            return self._build_failure_playbook_text("file_mutation", reason=q)
        if q in {"web", "search", "url", "browser"}:
            return self._build_failure_playbook_text("open_url", reason=q)
        return self._build_failure_playbook_text("task", reason=q)

    def _maybe_attach_failure_playbook(self, response_text, action_hint="", details=None):
        text = str(response_text or "")
        if not text:
            return text
        fail = bool(re.search(r"\b(failed|error|could not|unable|blocked|denied|timed out|skipped)\b", text, re.IGNORECASE))
        if not fail:
            return text
        playbook = self._build_failure_playbook_text(action_hint or "task", reason=text, details=details if isinstance(details, dict) else {})
        return text.rstrip() + "\n\n" + playbook

    def _build_session_recap_context(self, user_input, limit=2):
        if not self.memory_enabled or not self.session_recaps:
            return ""
        qk = set(self._extract_keywords(user_input))
        ranked = []
        total = len(self.session_recaps)
        for idx, row in enumerate(self.session_recaps):
            overlap = len(qk.intersection(set(row.get("keywords") or [])))
            recency = (idx + 1) / max(1, total)
            score = (overlap * 2.0) + recency
            if overlap <= 0 and qk:
                score -= 0.7
            ranked.append((score, row))
        ranked.sort(key=lambda x: x[0], reverse=True)
        selected = [row for _, row in ranked[:max(1, int(limit))] if row.get("summary")]
        if not selected:
            return ""
        lines = []
        for row in selected:
            ts = row.get("timestamp") or ""
            mode = row.get("mode") or "chat"
            lines.append(f"- [{ts}] ({mode}) {row.get('summary', '')}")
        return ("Session recaps (compressed long-term context):\n" + "\n".join(lines))[:1400]

    def _append_memory_journal(self, entry):
        if not self.memory_enabled:
            return
        try:
            os.makedirs(os.path.dirname(self.memory_journal_file), exist_ok=True)
            with open(self.memory_journal_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def load_long_term_learning(self):
        if not self.memory_enabled:
            self.learned_facts = []
            self.adaptive_examples = []
            if self.hermes_memory is not None:
                self.hermes_memory.insights = []
            return
        self.learned_facts = []
        self.adaptive_examples = []
        try:
            if os.path.exists(self.learned_facts_file):
                with open(self.learned_facts_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.learned_facts = [d for d in data if isinstance(d, dict)][-1000:]
        except Exception:
            self.learned_facts = []
        try:
            if os.path.exists(self.adaptive_examples_file):
                with open(self.adaptive_examples_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    cleaned = []
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        user = (item.get("user") or "").strip()
                        assistant = (item.get("assistant") or "").strip()
                        if not user or not assistant:
                            continue
                        cleaned.append(
                            {
                                "user": user[:500],
                                "assistant": assistant[:900],
                                "keywords": item.get("keywords") or self._extract_keywords(user),
                                "score": item.get("score", 0),
                            }
                        )
                    self.adaptive_examples = cleaned[-self.max_adaptive_examples:]
        except Exception:
            self.adaptive_examples = []
        try:
            if self.hermes_memory is not None:
                self.hermes_memory.load()
        except Exception:
            pass
        self._apply_historical_feedback_scores()

    def load_user_profile(self):
        """Load or initialize the structured user profile."""
        default = {
            "response_style": "balanced",   # "brief" | "detailed" | "balanced"
            "format_preference": "mixed",   # "bullets" | "prose" | "mixed"
            "good_lengths": [],             # char lengths of ðŸ‘ responses (last 30)
            "bad_patterns": [],             # short description of ðŸ‘Ž patterns (last 20)
            "domains": {},                  # {"coding": 12, "design": 5, ...}
            "name": "",
            "language": "en",
        }
        try:
            if os.path.exists(self.user_profile_file):
                with open(self.user_profile_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    default.update(saved)
        except Exception:
            pass
        self.user_profile = default

    def save_user_profile(self):
        try:
            os.makedirs(os.path.dirname(self.user_profile_file), exist_ok=True)
            with open(self.user_profile_file, "w", encoding="utf-8") as f:
                json.dump(self.user_profile, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _update_profile_from_feedback(self, rating, user_text, assistant_text):
        """Update user profile based on feedback signal."""
        if not self.user_profile:
            return
        if rating == "good" and assistant_text:
            length = len(assistant_text)
            lengths = self.user_profile.get("good_lengths", [])
            lengths.append(length)
            self.user_profile["good_lengths"] = lengths[-30:]
            # Infer style from running average of liked response lengths
            avg = sum(lengths) / len(lengths)
            if avg < 220:
                self.user_profile["response_style"] = "brief"
            elif avg > 550:
                self.user_profile["response_style"] = "detailed"
            else:
                self.user_profile["response_style"] = "balanced"
            # Infer format from bullet point density in liked responses
            bullet_count = len(re.findall(r'^\s*[-*â€¢]', assistant_text, re.MULTILINE))
            lines = max(1, assistant_text.count('\n') + 1)
            if bullet_count / lines > 0.35:
                pref = "bullets"
            elif bullet_count == 0 and lines < 6:
                pref = "prose"
            else:
                pref = "mixed"
            # Update format preference using a rolling vote
            current = self.user_profile.get("format_preference", "mixed")
            votes = self.user_profile.get("_format_votes", {"bullets": 0, "prose": 0, "mixed": 0})
            votes[pref] = votes.get(pref, 0) + 1
            self.user_profile["_format_votes"] = votes
            self.user_profile["format_preference"] = max(votes, key=votes.get)
        elif rating == "bad" and assistant_text:
            # Record what pattern got thumbed down (length + format tag)
            bullet_count = len(re.findall(r'^\s*[-*â€¢]', assistant_text, re.MULTILINE))
            tag = "long-bullets" if bullet_count > 4 and len(assistant_text) > 400 else \
                  "long-prose" if len(assistant_text) > 400 else \
                  "short" if len(assistant_text) < 80 else "medium"
            patterns = self.user_profile.get("bad_patterns", [])
            if tag not in patterns:
                patterns.append(tag)
            self.user_profile["bad_patterns"] = patterns[-20:]
        self.save_user_profile()

    def _update_profile_domain(self, user_text):
        """Track what topics/domains the user asks about most."""
        profile = getattr(self, "user_profile", None)
        if not profile or not user_text:
            return
        domain_keywords = {
            "coding": r'\b(code|python|javascript|bug|function|error|git|api|debug|script|class|variable)\b',
            "design": r'\b(figma|design|ui|ux|color|font|layout|prototype|mockup|wireframe)\b',
            "writing": r'\b(write|essay|email|letter|description|content|blog|post|paragraph|text)\b',
            "search": r'\b(search|find|look up|what is|who is|when did|latest|news|price)\b',
            "system": r'\b(open|close|file|folder|app|window|screen|desktop|install|delete|move|copy)\b',
            "math": r'\b(calculate|math|equation|formula|convert|percentage|sum|average)\b',
        }
        domains = profile.get("domains", {})
        for domain, pattern in domain_keywords.items():
            if re.search(pattern, user_text, re.IGNORECASE):
                domains[domain] = domains.get(domain, 0) + 1
        profile["domains"] = domains
        # No save here â€” saved at session end to avoid disk thrash

    def _build_profile_prompt(self):
        """Return a concise system prompt block describing the user's preferences."""
        p = self.user_profile
        if not p:
            return ""
        parts = []
        name = (p.get("name") or "").strip()
        if name:
            parts.append(f"The user's name is {name}.")
        style = p.get("response_style", "balanced")
        fmt = p.get("format_preference", "mixed")
        if style == "brief":
            parts.append("This user prefers SHORT, direct answers â€” avoid long explanations unless asked.")
        elif style == "detailed":
            parts.append("This user prefers DETAILED, thorough answers with full context.")
        else:
            parts.append("This user prefers balanced answers â€” not too short, not too long.")
        if fmt == "bullets":
            parts.append("Format preference: use bullet points and structured lists.")
        elif fmt == "prose":
            parts.append("Format preference: use flowing prose, avoid excessive bullet points.")
        bad = p.get("bad_patterns", [])
        if bad:
            bad_desc = []
            if "long-bullets" in bad:
                bad_desc.append("avoid overly long bulleted responses")
            if "long-prose" in bad:
                bad_desc.append("avoid very long paragraphs")
            if "short" in bad:
                bad_desc.append("avoid overly brief one-line answers")
            if bad_desc:
                parts.append("Based on past feedback: " + "; ".join(bad_desc) + ".")
        domains = p.get("domains", {})
        if domains:
            top = sorted(domains.items(), key=lambda x: x[1], reverse=True)[:2]
            top_names = [d for d, _ in top]
            if top_names:
                parts.append(f"This user frequently asks about: {', '.join(top_names)}.")
        if not parts:
            return ""
        return "## User profile (personalization)\n" + "\n".join(parts)

    def _apply_historical_feedback_scores(self):
        """Replay the feedback log to score adaptive examples that predate the score field."""
        if not os.path.exists(self.feedback_file):
            return
        try:
            with open(self.feedback_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            # Build lookup: (user[:500], assistant[:900]) -> net score delta
            deltas = {}
            for line in lines:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                rating = (row.get("rating") or "").strip().lower()
                u = (row.get("user") or "").strip()[:500]
                a = (row.get("assistant") or "").strip()[:900]
                if not u or not a or rating not in ("good", "bad"):
                    continue
                key = (u, a)
                deltas[key] = deltas.get(key, 0) + (1 if rating == "good" else -1)
            if not deltas:
                return
            # Apply deltas to examples that still have score=0 (i.e. unscored legacy entries).
            to_remove = []
            for i, ex in enumerate(self.adaptive_examples):
                key = (ex.get("user", "")[:500], ex.get("assistant", "")[:900])
                if key in deltas and ex.get("score", 0) == 0:
                    ex["score"] = deltas[key]
                    if ex["score"] < -1:
                        to_remove.append(i)
            for i in reversed(to_remove):
                self.adaptive_examples.pop(i)
            if to_remove:
                self._save_adaptive_examples()
        except Exception:
            pass

    def record_feedback(self, payload):
        if not self.feedback_enabled:
            return False
        try:
            if not isinstance(payload, dict):
                self.last_feedback_error = "Invalid payload."
                return False
            row = dict(payload)
            row["created_at"] = datetime.now().isoformat(timespec="seconds")
            os.makedirs(os.path.dirname(self.feedback_file), exist_ok=True)
            with open(self.feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._apply_feedback_learning(row)
            self.last_feedback_error = ""
            return True
        except Exception as e:
            self.last_feedback_error = f"{e.__class__.__name__}: {e}"
            return False

    def _apply_feedback_learning(self, payload):
        if not self.memory_enabled:
            return
        rating = (payload.get("rating") or "").strip().lower()
        user = (payload.get("user") or "").strip()
        assistant = (payload.get("assistant") or "").strip()
        correction = (payload.get("correction") or "").strip()
        self._update_profile_from_feedback(rating, user, assistant)
        if self.hermes_memory is not None:
            try:
                if rating == "fix" and correction:
                    self.hermes_memory.add_insight(
                        kind="feedback_fix",
                        text=f"When asked similar to '{user[:120]}', prefer this corrected direction: {correction[:220]}",
                        keywords=self._extract_keywords(user + " " + correction),
                        score_delta=1.8,
                    )
                elif rating == "bad" and user:
                    self.hermes_memory.add_insight(
                        kind="feedback_avoid",
                        text=f"Avoid the prior response style for requests like: {user[:180]}",
                        keywords=self._extract_keywords(user),
                        score_delta=1.0,
                    )
                elif rating == "good" and user and assistant:
                    self.hermes_memory.add_insight(
                        kind="feedback_good",
                        text=f"Successful response pattern exists for requests like: {user[:180]}",
                        keywords=self._extract_keywords(user),
                        score_delta=0.35,
                    )
            except Exception:
                pass
        if not user:
            return
        if rating == "fix" and correction:
            self._add_adaptive_example(user, correction)
            return
        if rating == "good" and assistant:
            # Boost score of existing example, or add it if new.
            for ex in self.adaptive_examples:
                if ex.get("user", "")[:500] == user[:500] and ex.get("assistant", "")[:900] == assistant[:900]:
                    ex["score"] = ex.get("score", 0) + 1
                    self._save_adaptive_examples()
                    return
            self._add_adaptive_example(user, assistant)
        elif rating == "bad" and assistant:
            # Penalize matching example; remove it once score drops below -1.
            for i, ex in enumerate(self.adaptive_examples):
                if ex.get("user", "")[:500] == user[:500] and ex.get("assistant", "")[:900] == assistant[:900]:
                    ex["score"] = ex.get("score", 0) - 1
                    if ex["score"] < -1:
                        self.adaptive_examples.pop(i)
                    self._save_adaptive_examples()
                    return

    def _add_adaptive_example(self, user_text, assistant_text):
        user_text = (user_text or "").strip()[:500]
        assistant_text = (assistant_text or "").strip()[:900]
        if not user_text or not assistant_text:
            return
        seen = {(e.get("user", ""), e.get("assistant", "")) for e in self.adaptive_examples}
        if (user_text, assistant_text) in seen:
            return
        ex = {
            "user": user_text,
            "assistant": assistant_text,
            "keywords": self._extract_keywords(user_text),
            "score": 0,
        }
        self.adaptive_examples.append(ex)
        self.adaptive_examples = self.adaptive_examples[-self.max_adaptive_examples:]
        if len(self.adaptive_examples) % 6 == 0:
            self._save_adaptive_examples()

    def _export_feedback_bundle(self):
        try:
            if not os.path.exists(self.feedback_file):
                return "No feedback to export."
            out_dir = self.exports_dir
            os.makedirs(out_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(out_dir, f"feedback_export_{ts}.jsonl")
            with open(self.feedback_file, "r", encoding="utf-8") as src, open(out_path, "w", encoding="utf-8") as dst:
                for line in src:
                    if line.strip():
                        dst.write(line)
            return f"Feedback exported: {out_path}"
        except Exception as e:
            return f"Could not export feedback: {e}"

    def _save_learned_facts(self):
        try:
            os.makedirs(os.path.dirname(self.learned_facts_file), exist_ok=True)
            with open(self.learned_facts_file, "w", encoding="utf-8") as f:
                json.dump(self.learned_facts[-1000:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _save_adaptive_examples(self):
        try:
            os.makedirs(os.path.dirname(self.adaptive_examples_file), exist_ok=True)
            with open(self.adaptive_examples_file, "w", encoding="utf-8") as f:
                json.dump(self.adaptive_examples[-self.max_adaptive_examples:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def load_prompt_examples(self):
        self.prompt_examples = []
        try:
            if not os.path.exists(self.prompt_training_file):
                return
            with open(self.prompt_training_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                cleaned = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    user = (item.get("user") or "").strip()
                    assistant = (item.get("assistant") or "").strip()
                    if not user or not assistant:
                        continue
                    cleaned.append(
                        {
                            "user": user[:500],
                            "assistant": assistant[:800],
                            "keywords": self._extract_keywords(user),
                        }
                    )
                self.prompt_examples = cleaned[:300]
        except Exception:
            self.prompt_examples = []

    def _retrieve_prompt_examples(self, user_input, limit=3):
        all_examples = (self.prompt_examples or []) + (self.adaptive_examples or [])
        if not all_examples:
            return []
        qk = set(self._extract_keywords(user_input))
        scored = []
        for ex in all_examples:
            # Skip examples the user has explicitly disliked enough.
            if ex.get("score", 0) < -1:
                continue
            overlap = len(qk.intersection(set(ex.get("keywords", []))))
            if overlap <= 0:
                continue
            feedback_boost = ex.get("score", 0) * 0.5
            score = overlap * 2 + (0.2 if len(ex.get("user", "")) < 120 else 0.0) + feedback_boost
            scored.append((score, ex))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        seen = set()
        for _, e in scored:
            key = (e.get("user", ""), e.get("assistant", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def _normalize_skill_key(self, text):
        t = (text or "").strip().lower()
        t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
        return t

    def _load_skill_enabled_map(self):
        self.skill_enabled_map = {}
        try:
            if not os.path.exists(self.skills_registry_file):
                return
            with open(self.skills_registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.skill_enabled_map = {str(k): bool(v) for k, v in data.items()}
        except Exception:
            self.skill_enabled_map = {}

    def _save_skill_enabled_map(self):
        try:
            os.makedirs(os.path.dirname(self.skills_registry_file), exist_ok=True)
            with open(self.skills_registry_file, "w", encoding="utf-8") as f:
                json.dump(self.skill_enabled_map, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _parse_skill_frontmatter(self, content):
        meta = {}
        body = content or ""
        if not body.startswith("---"):
            return meta, body
        m = re.match(r"(?s)^---\s*\n(.*?)\n---\s*\n?(.*)$", body)
        if not m:
            return meta, body
        raw_meta = m.group(1) or ""
        body = m.group(2) or ""
        for line in raw_meta.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
        return meta, body

    def load_skills(self):
        self._load_skill_enabled_map()
        self.skills = []
        try:
            os.makedirs(self.skills_root, exist_ok=True)
            for root, _, files in os.walk(self.skills_root):
                for fname in files:
                    if fname.upper() != "SKILL.MD":
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            raw = f.read()
                    except Exception:
                        continue
                    meta, body = self._parse_skill_frontmatter(raw)
                    base = os.path.basename(root) if os.path.basename(root) else os.path.splitext(fname)[0]
                    name = (meta.get("name") or base or "skill").strip()
                    sid = self._normalize_skill_key(meta.get("id") or name)
                    if not sid:
                        sid = self._normalize_skill_key(base) or "skill"
                    description = (meta.get("description") or "").strip()
                    command = (meta.get("command") or f"/{sid}").strip()
                    enabled = bool(self.skill_enabled_map.get(sid, True))
                    self.skills.append(
                        {
                            "id": sid,
                            "name": name,
                            "description": description,
                            "command": command,
                            "source": "custom",
                            "is_enabled": enabled,
                            "file_path": fpath,
                            "content": body.strip(),
                            "updated_at": datetime.now().isoformat(timespec="seconds"),
                        }
                    )
            self.skills.sort(key=lambda x: x.get("name", "").lower())
        except Exception:
            self.skills = []

    def _find_skill(self, ref):
        key = self._normalize_skill_key(ref)
        if not key:
            return None
        for s in self.skills:
            if s.get("id") == key:
                return s
        for s in self.skills:
            if self._normalize_skill_key(s.get("name", "")) == key:
                return s
        return None

    def _set_skill_enabled(self, ref, enabled):
        s = self._find_skill(ref)
        if not s:
            return False, f"Skill not found: {ref}"
        sid = s.get("id", "")
        if not sid:
            return False, f"Skill not found: {ref}"
        self.skill_enabled_map[sid] = bool(enabled)
        s["is_enabled"] = bool(enabled)
        self._save_skill_enabled_map()
        self._audit("skill_toggle", "allowed", {"skill_id": sid, "enabled": bool(enabled)})
        return True, f"Skill '{s.get('name', sid)}' is now {'ON' if enabled else 'OFF'}."

    def _skills_status_text(self):
        if not self.skills:
            return "No skills found. Add folders under ./skills with a SKILL.md file."
        lines = ["Skills:"]
        for s in self.skills:
            state = "ON" if s.get("is_enabled") else "OFF"
            lines.append(
                f"- {s.get('name')} [{s.get('id')}] ({state})"
                + (f" - {s.get('description')}" if s.get("description") else "")
            )
        return "\n".join(lines)

    def _enabled_skills_prompt(self, max_chars=2800):
        enabled = [s for s in self.skills if s.get("is_enabled") and (s.get("content") or "").strip()]
        if not enabled:
            return ""
        chunks = []
        for s in enabled:
            body = (s.get("content") or "").strip()
            if not body:
                continue
            chunks.append(f"[Skill: {s.get('name')}]\n{body}")
        merged = "\n\n".join(chunks)
        if len(merged) > max_chars:
            merged = merged[:max_chars]
        return "Enabled skills context:\n" + merged

    def _enabled_skills_prompt_for_query(self, user_input, max_chars=1200):
        t = (user_input or "").strip().lower()
        if not t:
            return ""
        # Keep skill injection focused so normal chat stays fast.
        if not re.search(r"\b(skill|internet|web|online|research|search|source|news|latest|update)\b", t):
            return ""
        return self._enabled_skills_prompt(max_chars=max_chars)

    def _should_use_lightweight_llm_context(self, user_input, screen_task_intent=False):
        if not self.fast_prompt_mode:
            return False
        if screen_task_intent:
            return False
        # Never drop context when there is active conversation history Ã¢Â€Â”
        # follow-up questions are short by nature ("what about him?", "explain more")
        # and losing history causes the agent to forget who/what was discussed.
        if self.conversation_history:
            return False
        t = (user_input or "").strip().lower()
        if not t:
            return True
        # Keep heavy context for complex or memory-dependent requests.
        heavy_cues = [
            r"\b(remember|earlier|previous|before|history|memory)\b",
            r"\b(compare|analyze|analysis|explain in detail|step by step|plan)\b",
            r"\b(write code|generate code|debug|refactor|architecture)\b",
            r"\b(sources?|citations?|research|internet|web|online|latest|current|today|now)\b",
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in heavy_cues):
            return False
        return len(t.split()) <= 14

    def _audit(self, action, status, details=None):
        def _redact_obj(obj):
            if isinstance(obj, dict):
                return {k: _redact_obj(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_redact_obj(v) for v in obj]
            if isinstance(obj, tuple):
                return tuple(_redact_obj(v) for v in obj)
            if not isinstance(obj, str):
                return obj
            s = obj
            s = re.sub(r"\bsk-[A-Za-z0-9_\-]{12,}\b", "[REDACTED_API_KEY]", s)
            s = re.sub(
                r"\b(?:GROQ_API_KEY|DEEPSEEK_API_KEY|ALIBABA_MODEL_STUDIO_API_KEY|DASHSCOPE_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*([^\s\"']+)",
                lambda m: m.group(0).split("=")[0] + "=[REDACTED]",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]+\b", "Bearer [REDACTED]", s)
            return s

        try:
            os.makedirs(os.path.dirname(self.audit_log_file), exist_ok=True)
            entry = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "action": action,
                "status": status,
                "details": _redact_obj(details or {}),
            }
            with open(self.audit_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._record_task_outcome_from_audit(action, status, details if isinstance(details, dict) else {})
        except Exception:
            pass

    def _is_allowed_subprocess(self, args):
        if not isinstance(args, (list, tuple)) or not args:
            return False
        exe = os.path.basename(str(args[0]).strip().strip('"')).lower()
        return exe in self.allowed_subprocess_bins or exe in self.allowed_launch_bins

    def _run_allowed_subprocess(self, args, **kwargs):
        if not self._is_allowed_subprocess(args):
            self._audit("subprocess", "blocked", {"args": list(args) if isinstance(args, (list, tuple)) else str(args)})
            raise PermissionError("Blocked by subprocess allowlist.")
        self._audit("subprocess", "allowed", {"args": list(args)})
        return subprocess.run(args, **kwargs)

    def _popen_allowed(self, args, **kwargs):
        if not self._is_allowed_subprocess(args):
            self._audit("subprocess_popen", "blocked", {"args": list(args) if isinstance(args, (list, tuple)) else str(args)})
            raise PermissionError("Blocked by subprocess allowlist.")
        self._audit("subprocess_popen", "allowed", {"args": list(args)})
        return subprocess.Popen(args, **kwargs)

    def _is_mutating_file_command(self, text):
        t = (text or "").strip().lower()
        if not re.match(
            r"^(create|make|write|overwrite|replace|append|add|delete|remove|rename|move|copy)\b",
            t,
            flags=re.IGNORECASE,
        ):
            return False
        # rename/move/delete/copy with any target are always file mutations Ã¢Â€Â” no extra keyword needed
        if re.match(r"^(rename|move|delete|remove|copy)\b", t, flags=re.IGNORECASE):
            non_file_words = r"\b(research|search|plan|plans|more|further|sense|sure|time|money|request|decision|effort|progress|question|improvement)\b"
            if re.search(non_file_words, t[:60], flags=re.IGNORECASE):
                return False
            return True
        # create/make/write/append/add require a file/folder indicator
        non_file_words = r"\b(research|search|plan|plans|more|further|sense|sure|time|money|call|request|decision|effort|progress|question|improvement)\b"
        if re.search(non_file_words, t[:60], flags=re.IGNORECASE):
            return False
        file_indicators = r"\b(file|folder|directory|document|txt|csv|json|log|report|note|readme|script|backup|copy|dir)\b"
        return bool(re.search(file_indicators, t, flags=re.IGNORECASE))

    def _extract_keywords(self, text):
        tokens = re.findall(r"[a-zA-Z0-9']+", (text or "").lower())
        stop = {
            "the", "a", "an", "and", "or", "but", "if", "then", "to", "for", "from", "of",
            "in", "on", "at", "with", "is", "are", "was", "were", "be", "been", "i", "you",
            "we", "they", "it", "this", "that", "my", "your", "me", "do", "does", "did",
            "can", "could", "should", "would", "help", "please", "about", "what", "how",
        }
        out = []
        seen = set()
        for t in tokens:
            if len(t) > 2 and t not in stop and t not in seen:
                seen.add(t)
                out.append(t)
        return out[:12]

    def _remember_turn(self, user_text, assistant_text):
        safe_user = self._safe_memory_text(user_text or "", max_len=900)
        safe_assistant = self._safe_memory_text(assistant_text or "", max_len=1500)
        if not safe_user and not safe_assistant:
            return
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user": safe_user,
            "assistant": safe_assistant,
            "keywords": self._extract_keywords(safe_user),
        }
        # Store in mode-specific history
        _mode = getattr(self, "input_mode", "chat")
        if _mode == "task":
            self.task_conversation_history.append(entry)
            self.task_conversation_history = self.task_conversation_history[-self.max_memory_items:]
        else:
            self.conversation_history.append(entry)
            self.conversation_history = self.conversation_history[-self.max_memory_items:]
        if self.memory_enabled:
            self._append_memory_journal(entry)
            # Snapshot less frequently to keep response path fast.
            active_hist = self.task_conversation_history if _mode == "task" else self.conversation_history
            if len(active_hist) % self._memory_snapshot_every == 0 and _mode != "task":
                self.save_memory()
            self._learn_from_turn(user_text, assistant_text)
            self._maybe_compact_memory(mode=_mode)

    def _capture_turn(self, user_text, assistant_text, remember=True):
        self.last_user_message = str(user_text or "")[:1200]
        self.last_assistant_message = str(assistant_text or "")[:5000]
        self._update_topic_anchor(user_text, assistant_text)
        if remember:
            try:
                self._remember_turn(user_text, assistant_text)
            except Exception:
                pass

    def _extract_topic_anchor(self, user_text):
        t = str(user_text or "").strip()
        if not t:
            return "", []
        # Remove noisy helper words while keeping subject-bearing tokens.
        cleaned = re.sub(
            r"\b(and|also|then|what|about|how|do|does|did|can|could|should|would|please|explain|clarify|elaborate|"
            r"tell|me|you|your|that|this|it|them|those|these|one|ones|more|details|detail|use|using)\b",
            " ",
            t,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.?")
        kws = self._extract_keywords(cleaned or t)
        if len(kws) < 2:
            kws = self._extract_keywords(t)
        anchor = " ".join(kws[:8]).strip()
        return (anchor[:140], kws[:10])

    def _looks_like_topic_switch(self, user_input):
        t = str(user_input or "").strip().lower()
        if not t:
            return False
        if re.search(r"\b(new topic|another topic|different topic|change topic|switch topic|forget previous|start over)\b", t):
            return True
        return False

    def _is_ambiguous_followup_query(self, user_input):
        q = str(user_input or "").strip()
        if not q:
            return False
        if self._looks_like_topic_switch(q):
            return False
        if re.match(r"^\s*(and|also|then|so)\b", q, flags=re.IGNORECASE):
            return True
        if re.match(r"^\s*(what|how|why|when|where|which)\s+about\b", q, flags=re.IGNORECASE):
            return True
        if re.search(r"\b(it|this|that|those|these|them|that one|this one)\b", q, flags=re.IGNORECASE):
            return True
        if re.search(r"\b(how do i use|how to use|how to do that|how can i use|how can i do that)\b", q, flags=re.IGNORECASE):
            return True
        words = q.split()
        if len(words) <= 10 and re.match(r"^\s*(what|how|why|when|where|which|can|do|does|is|are)\b", q, flags=re.IGNORECASE):
            return True
        return False

    def _topic_anchor_is_fresh(self):
        if not self.topic_anchor_text:
            return False
        age = max(0.0, time.time() - float(self.topic_anchor_updated_at or 0.0))
        return age <= max(60, int(self.topic_anchor_ttl_sec))

    def _update_topic_anchor(self, user_text, assistant_text):
        u = str(user_text or "").strip()
        if not u:
            return
        if self._looks_like_topic_switch(u):
            self.topic_anchor_text = ""
            self.topic_anchor_keywords = []
            self.topic_anchor_updated_at = time.time()
            return
        # Don't replace anchor with trivial follow-up wording.
        if self._is_ambiguous_followup_query(u) and self.topic_anchor_text:
            self.topic_anchor_updated_at = time.time()
            return
        anchor, kws = self._extract_topic_anchor(u)
        if anchor:
            self.topic_anchor_text = anchor
            self.topic_anchor_keywords = list(kws or [])
            self.topic_anchor_updated_at = time.time()

    def _topic_anchor_hint(self, user_input):
        if not self._topic_anchor_is_fresh():
            return ""
        if self._looks_like_topic_switch(user_input):
            return ""
        if not self._is_ambiguous_followup_query(user_input):
            return ""
        _last_ans = (self.last_assistant_message or "").strip().replace("\n", " ")
        return (
            "TOPIC ANCHOR: Keep continuity with the active conversation subject unless the user explicitly switches topics. "
            f"Current anchor: \"{self.topic_anchor_text}\". "
            f"Recent assistant context: \"{_last_ans[:260]}\"."
        )

    def _topic_anchor_status_text(self):
        if not self.topic_anchor_text:
            return "Context anchor: none."
        age = max(0.0, time.time() - float(self.topic_anchor_updated_at or 0.0))
        return (
            "Context anchor:\n"
            f"  - anchor: {self.topic_anchor_text}\n"
            f"  - keywords: {', '.join(self.topic_anchor_keywords[:8]) if self.topic_anchor_keywords else '(none)'}\n"
            f"  - age_sec: {int(age)}\n"
            f"  - ttl_sec: {int(self.topic_anchor_ttl_sec)}\n"
            f"  - active: {self._topic_anchor_is_fresh()}"
        )

    def _reset_topic_anchor(self):
        self.topic_anchor_text = ""
        self.topic_anchor_keywords = []
        self.topic_anchor_updated_at = 0.0

    def _extract_user_facts(self, user_text):
        text = (user_text or "").strip()
        if not text:
            return []
        facts = []
        rules = [
            (r"\bmy name is\s+([A-Za-z][A-Za-z0-9_\- ]{1,40})", "name"),
            (r"\bi am\s+([A-Za-z][A-Za-z0-9_\- ]{1,40})", "identity"),
            (r"\bi prefer\s+(.{2,80})", "preference"),
            (r"\bi like\s+(.{2,80})", "like"),
            (r"\bi don't like\s+(.{2,80})", "dislike"),
            (r"\balways\s+(.{2,100})", "always_rule"),
        ]
        for pattern, kind in rules:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if not m:
                continue
            value = (m.group(1) or "").strip(" .,!?:;")
            if value:
                facts.append({"kind": kind, "value": value[:120]})
        return facts

    def _extract_learning_rules(self, user_text):
        text = (user_text or "").strip()
        if not text:
            return []
        out = []
        patterns = [
            (r"\b(?:please\s+)?always\s+(.{3,140})", "always_rule"),
            (r"\b(?:please\s+)?(?:don't|do not|never)\s+(.{3,140})", "avoid_rule"),
            (r"\b(?:i prefer|prefer)\s+(.{3,120})", "preference_rule"),
            (r"\bremember\s+(?:that\s+)?(.{3,120})", "memory_rule"),
        ]
        for pattern, kind in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if not m:
                continue
            value = (m.group(1) or "").strip(" .,!?:;")
            if value:
                out.append({"kind": kind, "value": value[:180]})
        return out

    def _learn_from_turn(self, user_text, assistant_text):
        if not self.memory_enabled:
            return
        answer = (assistant_text or "").strip()
        if answer and not answer.lower().startswith("error:"):
            ex = {
                "user": (user_text or "").strip()[:500],
                "assistant": answer[:900],
                "keywords": self._extract_keywords(user_text),
            }
            if ex["user"] and ex["assistant"]:
                self.adaptive_examples.append(ex)
                self.adaptive_examples = self.adaptive_examples[-self.max_adaptive_examples:]
                if len(self.adaptive_examples) % 12 == 0:
                    self._save_adaptive_examples()

        facts = self._extract_user_facts(user_text)
        if not facts:
            return
        now_ts = datetime.now().isoformat(timespec="seconds")
        existing = {(f.get("kind"), str(f.get("value", "")).lower()): f for f in self.learned_facts}
        changed = False
        for item in facts:
            key = (item.get("kind"), str(item.get("value", "")).lower())
            if key in existing:
                existing[key]["updated_at"] = now_ts
                changed = True
                continue
            self.learned_facts.append(
                {
                    "kind": item.get("kind"),
                    "value": item.get("value"),
                    "keywords": self._extract_keywords(item.get("value", "")),
                    "created_at": now_ts,
                    "updated_at": now_ts,
                }
            )
            changed = True
        if changed:
            self.learned_facts = self.learned_facts[-1000:]
            self._save_learned_facts()
        if self.hermes_memory is not None:
            try:
                rules = self._extract_learning_rules(user_text)
                for rule in rules:
                    insight_text = f"For this user, {rule.get('value', '')}"
                    self.hermes_memory.add_insight(
                        kind=rule.get("kind") or "rule",
                        text=insight_text,
                        keywords=(rule.get("value") or ""),
                        score_delta=1.1,
                    )
            except Exception:
                pass

    def _maybe_compact_memory(self, mode="chat"):
        if not self.memory_enabled:
            return
        if self.memory_summary_trigger <= 0:
            return
        history = self.task_conversation_history if (mode == "task") else self.conversation_history
        if len(history) < self.memory_summary_trigger:
            return
        if time.time() - self._last_summary_ts < 60:
            return
        keep_last = max(2, self.memory_summary_keep_last)
        if len(history) <= keep_last + 2:
            return
        to_summarize = history[:-keep_last]
        if not to_summarize:
            return
        text_lines = []
        for item in to_summarize[-24:]:
            text_lines.append(f"User: {item.get('user', '')}")
            text_lines.append(f"Assistant: {item.get('assistant', '')}")
        raw = "\n".join(text_lines)
        summary = self._summarize_memory_block(raw)
        if not summary:
            return
        summary_entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user": "[summary]",
            "assistant": summary,
            "keywords": self._extract_keywords(summary),
            "summary": True,
        }
        compacted = [summary_entry] + history[-keep_last:]
        if mode == "task":
            self.task_conversation_history = compacted
        else:
            self.conversation_history = compacted
            self.save_memory()
        self._last_summary_ts = time.time()

    def _summarize_memory_block(self, text):
        if not text.strip():
            return ""
        # Fast fallback if no model available
        if self.client is None and not (self.deepseek_api_key or self.qwen_api_key or self.gemini_api_key):
            compact = text.replace("\n", " ")
            return compact[:500]
        system = (
            "Summarize the conversation for future context. "
            "Keep preferences, decisions, files, tasks, and corrections. "
            "Return 6-10 short bullet points."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text[:4000]},
        ]
        try:
            return self._call_ai(messages).strip()
        except Exception:
            compact = text.replace("\n", " ")
            return compact[:500]

    def _generate_session_recap_from_history(self, history, mode="chat"):
        rows = list(history or [])
        if len(rows) < max(2, int(self.session_recap_trigger)):
            return ""
        lines = []
        for item in rows[-18:]:
            lines.append(f"User: {(item.get('user') or '')[:260]}")
            lines.append(f"Assistant: {(item.get('assistant') or '')[:360]}")
        payload = "\n".join(lines).strip()
        if not payload:
            return ""
        prompt = (
            f"Create a compact recap for future {mode} context. "
            "Keep goals, decisions, constraints, preferences, files/apps involved, and unresolved items. "
            "Return 5-8 bullet points."
        )
        try:
            recap = self._call_ai(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": payload[:4200]},
                ]
            ).strip()
        except Exception:
            recap = ""
        if not recap:
            flat = payload.replace("\n", " ")
            recap = flat[:650]
        return recap[:1200]

    def _retrieve_relevant_facts(self, user_input, limit=6):
        if not self.memory_enabled:
            return []
        if not self.learned_facts:
            return []
        qk = set(self._extract_keywords(user_input))
        scored = []
        for idx, fact in enumerate(self.learned_facts):
            overlap = len(qk.intersection(set(fact.get("keywords", []))))
            score = overlap
            if fact.get("kind") in {"name", "preference", "always_rule"}:
                score += 0.5
            # recency nudge
            score += (idx + 1) / max(1, len(self.learned_facts)) * 0.2
            scored.append((score, fact))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for s, f in scored if s > 0][:limit]

    def _format_facts_context(self, facts):
        if not facts:
            return ""
        lines = []
        for f in facts:
            kind = (f.get("kind") or "fact").replace("_", " ")
            value = f.get("value") or ""
            lines.append(f"- {kind}: {value}")
        return "User long-term memory:\n" + "\n".join(lines)

    def _build_hermes_learning_context(self, user_input):
        if not self.memory_enabled or self.hermes_memory is None:
            return ""
        try:
            return self.hermes_memory.render_context(user_input, limit=4, max_chars=900)
        except Exception:
            return ""

    def _memory_status_text(self):
        insights_count = len(getattr(self.hermes_memory, "insights", []) or [])
        return (
            "Memory status:\n"
            f"  - enabled: {self.memory_enabled}\n"
            f"  - private_mode: {self.private_mode}\n"
            f"  - feedback_enabled: {self.feedback_enabled}\n"
            f"  - conversation_history: {len(self.conversation_history)} items\n"
            f"  - learned_facts: {len(self.learned_facts)} items\n"
            f"  - adaptive_examples: {len(self.adaptive_examples)} items\n"
            f"  - hermes_insights: {insights_count} items\n"
            f"  - session_recaps: {len(self.session_recaps)} items\n"
            f"  - task_outcomes: {len(self.task_outcomes)} items\n"
            f"  - trajectories: {len(self.trajectory_memory)} items\n"
            f"  - memory_safety_blocks: {int(self.memory_safety_block_count)}\n"
            f"  - provider_stats_tracked: {len(self.provider_health)} providers\n"
            f"  - mcp_route_stats_tracked: {len(self.mcp_route_stats)} actions\n"
            f"  - memory_file: {self.memory_file}\n"
            f"  - memory_journal_file: {self.memory_journal_file}\n"
            f"  - learned_facts_file: {self.learned_facts_file}\n"
            f"  - adaptive_examples_file: {self.adaptive_examples_file}\n"
            f"  - session_recaps_file: {self.session_recaps_file}\n"
            f"  - task_outcomes_file: {self.task_outcomes_file}\n"
            f"  - trajectory_memory_file: {self.trajectory_memory_file}\n"
            f"  - provider_stats_file: {self.provider_stats_file}\n"
            f"  - mcp_route_stats_file: {self.mcp_route_stats_file}"
        )

    def _memory_recent_text(self, limit=8):
        rows = []
        for item in self.conversation_history[-max(1, int(limit)):]:
            ts = item.get("timestamp", "")
            user = (item.get("user") or "").replace("\n", " ").strip()
            assistant = (item.get("assistant") or "").replace("\n", " ").strip()
            rows.append(f"[{ts}] U: {user[:90]}")
            rows.append(f"[{ts}] A: {assistant[:120]}")
        return "\n".join(rows) if rows else "(no recent memory)"

    def _memory_facts_text(self, limit=15):
        facts = self.learned_facts[-max(1, int(limit)):]
        if not facts:
            return "(no learned facts)"
        lines = []
        for f in facts:
            kind = (f.get("kind") or "fact").replace("_", " ")
            value = (f.get("value") or "").strip()
            ts = f.get("updated_at") or f.get("created_at") or ""
            lines.append(f"- [{ts}] {kind}: {value[:140]}")
        return "\n".join(lines)

    def _memory_insights_text(self, limit=12):
        insights = list(getattr(self.hermes_memory, "insights", []) or [])[-max(1, int(limit)):]
        if not insights:
            return "(no hermes insights)"
        lines = []
        for row in insights:
            kind = (row.get("kind") or "insight").replace("_", " ")
            text = (row.get("text") or "").strip()
            ts = row.get("updated_at") or row.get("created_at") or ""
            score = float(row.get("score", 0))
            lines.append(f"- [{ts}] ({kind}, score={score:.2f}) {text[:170]}")
        return "\n".join(lines)

    def _memory_recaps_text(self, limit=8):
        recaps = self.session_recaps[-max(1, int(limit)):]
        if not recaps:
            return "(no session recaps)"
        lines = []
        for row in recaps:
            ts = row.get("timestamp") or ""
            mode = row.get("mode") or "chat"
            summary = (row.get("summary") or "").replace("\n", " ").strip()
            lines.append(f"- [{ts}] ({mode}) {summary[:220]}")
        return "\n".join(lines)

    def _export_memory_bundle(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = self.exports_dir
        out_path = os.path.join(out_dir, f"memory_export_{ts}.json")
        try:
            os.makedirs(out_dir, exist_ok=True)
            payload = {
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "conversation_history": self.conversation_history[-self.max_memory_items:],
                "learned_facts": self.learned_facts[-1000:],
                "adaptive_examples": self.adaptive_examples[-self.max_adaptive_examples:],
                "hermes_insights": list(getattr(self.hermes_memory, "insights", []) or []),
                "session_recaps": self.session_recaps[-self.max_session_recaps:],
                "task_outcomes": self.task_outcomes[-self.max_task_outcomes:],
                "failure_patterns": self.failure_patterns,
                "trajectory_memory": self.trajectory_memory[-self.max_trajectories:],
                "trajectory_source_cursor": int(self._trajectory_source_cursor),
                "memory_safety_blocks": int(self.memory_safety_block_count),
                "provider_health": self.provider_health,
                "provider_cooldown_until": self.provider_cooldown_until,
                "provider_last_error": self.provider_last_error,
                "mcp_route_stats": self.mcp_route_stats,
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            return f"Memory exported: {out_path}"
        except Exception as e:
            return f"Could not export memory: {e}"

    def _clear_memory_bucket(self, bucket):
        key = (bucket or "").strip().lower()
        if key in {"all", "*"}:
            self.conversation_history = []
            self.learned_facts = []
            self.adaptive_examples = []
            self.session_recaps = []
            self.task_outcomes = []
            self.failure_patterns = {}
            self.trajectory_memory = []
            self._trajectory_source_cursor = 0
            self.memory_safety_block_count = 0
            self.provider_health = {}
            self.provider_cooldown_until = {}
            self.provider_last_error = {}
            self.mcp_route_stats = {}
            if self.hermes_memory is not None:
                self.hermes_memory.insights = []
                self.hermes_memory.save()
            self.save_memory()
            self._save_learned_facts()
            self._save_adaptive_examples()
            self._save_session_recaps()
            self._save_task_outcomes()
            self._save_trajectory_memory()
            self._save_provider_stats()
            self._save_mcp_route_stats()
            try:
                if os.path.exists(self.memory_journal_file):
                    os.remove(self.memory_journal_file)
            except Exception:
                pass
            return "Cleared all memory."
        if key in {"history", "conversation", "conversations"}:
            self.conversation_history = []
            self.save_memory()
            try:
                if os.path.exists(self.memory_journal_file):
                    os.remove(self.memory_journal_file)
            except Exception:
                pass
            return "Cleared conversation history memory."
        if key in {"facts", "learned_facts", "profile"}:
            self.learned_facts = []
            self._save_learned_facts()
            return "Cleared learned facts memory."
        if key in {"adaptive", "examples", "training"}:
            self.adaptive_examples = []
            self._save_adaptive_examples()
            return "Cleared adaptive training memory."
        if key in {"recaps", "recap", "session"}:
            self.session_recaps = []
            self._save_session_recaps()
            return "Cleared session recap memory."
        if key in {"outcomes", "tasks", "playbooks", "failures"}:
            self.task_outcomes = []
            self.failure_patterns = {}
            self.trajectory_memory = []
            self._trajectory_source_cursor = 0
            self._save_task_outcomes()
            self._save_trajectory_memory()
            return "Cleared task outcomes, failure playbooks, and trajectory memory."
        if key in {"trajectory", "trajectories", "traces"}:
            self.trajectory_memory = []
            self._trajectory_source_cursor = len(self.task_outcomes)
            self._save_trajectory_memory()
            return "Cleared trajectory memory."
        if key in {"insights", "hermes", "learning"}:
            if self.hermes_memory is not None:
                self.hermes_memory.insights = []
                self.hermes_memory.save()
            return "Cleared Hermes learning insights memory."
        return "Unknown memory bucket. Use: all, history, facts, adaptive, recaps, outcomes, trajectory, or insights."

    def _retrieve_relevant_memory(self, user_input, limit=5):
        if not self.memory_enabled:
            return []
        if not self.conversation_history:
            return []
        query_kw = set(self._extract_keywords(user_input))
        if not query_kw:
            return self.conversation_history[-min(limit, len(self.conversation_history)):]
        scored = []
        total = len(self.conversation_history)
        for idx, item in enumerate(self.conversation_history):
            overlap = len(query_kw.intersection(set(item.get("keywords", []))))
            if overlap <= 0:
                continue
            score = overlap * 3 + ((idx + 1) / total)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _format_memory_context(self, entries):
        lines = []
        for item in entries:
            ts = item.get("timestamp", "")
            lines.append(f"[{ts}] User: {item.get('user', '')}")
            lines.append(f"[{ts}] Assistant: {item.get('assistant', '')}")
        return "\n".join(lines)

    def _should_include_live_state_context(self, user_input):
        t = (user_input or "").lower()
        if not t:
            return False
        patterns = [
            r"\b(app|open|close|running|status|window|desktop|file|folder|explorer)\b",
            r"\b(screenshot|screen|tab|browser|website|url|search)\b",
            r"\b(system|cpu|memory|disk|wifi|network|ip)\b",
        ]
        # Require at least one explicit operational cue to avoid adding heavy live context on generic chat.
        return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)

    def get_running_apps(self, force_refresh=False):
        if not force_refresh and self.last_apps_check and (time.time() - self.last_apps_check < 2):
            return self.last_apps_list
        apps = []
        app_set = set()
        real_apps = {
            "chrome.exe": "Google Chrome", "firefox.exe": "Mozilla Firefox", "msedge.exe": "Microsoft Edge",
            "brave.exe": "Brave", "discord.exe": "Discord", "telegram.exe": "Telegram",
            "whatsapp.exe": "WhatsApp", "slack.exe": "Slack", "zoom.exe": "Zoom", "teams.exe": "Microsoft Teams",
            "code.exe": "VS Code", "cursor.exe": "Cursor", "spotify.exe": "Spotify", "vlc.exe": "VLC",
            "framer.exe": "Framer",
            "outlook.exe": "Microsoft Outlook", "winword.exe": "Microsoft Word", "excel.exe": "Microsoft Excel",
            "powerpnt.exe": "Microsoft PowerPoint", "photoshop.exe": "Adobe Photoshop", "figma.exe": "Figma",
            "steam.exe": "Steam", "explorer.exe": "File Explorer", "powershell.exe": "PowerShell",
            "cmd.exe": "Command Prompt", "wt.exe": "Windows Terminal", "notepad.exe": "Notepad", "calculator.exe": "Calculator",
            "copilot.exe": "Copilot",
        }
        system_processes = [
            "svchost", "system", "conhost", "dwm", "csrss", "wininit", "winlogon", "services", "lsass",
            "smss", "fontdrvhost", "spoolsv", "runtimebroker", "dllhost", "background", "search", "ctfmon",
            "sihost", "taskhost", "registry", "openconsole", "lsaiso", "audiodg", "appv", "wmiprvse",
        ]

        # 1) Visible window titles are the best proxy for "apps user sees" (Task Manager Apps section).
        if gw is not None:
            try:
                skip_title_tokens = [
                    "program manager", "windows input experience", "nvidia", "realtek",
                    "widget", "msctfime ui", "default ime",
                ]
                for w in gw.getAllWindows():
                    if not w.visible:
                        continue
                    # Skip DWM-cloaked windows (UWP apps like Settings that are
                    # "closed" but kept suspended in memory by Windows).
                    try:
                        _cloaked = ctypes.c_int(0)
                        ctypes.windll.dwmapi.DwmGetWindowAttribute(
                            w._hWnd, 14, ctypes.byref(_cloaked), ctypes.sizeof(_cloaked)
                        )
                        if _cloaked.value != 0:
                            continue
                    except Exception:
                        pass
                    title = (w.title or "").strip()
                    if len(title) < 3:
                        continue
                    tl = title.lower()
                    if any(tok in tl for tok in skip_title_tokens):
                        continue
                    # Map common titles to canonical names
                    mapped = None
                    # Detect common "page - app" title endings first.
                    suffix_map = {
                        " - google chrome": "Google Chrome",
                        " - mozilla firefox": "Mozilla Firefox",
                        " - microsoft edge": "Microsoft Edge",
                        " - brave": "Brave",
                        " - visual studio code": "VS Code",
                        " - cursor": "Cursor",
                    }
                    for suffix, value in suffix_map.items():
                        if tl.endswith(suffix):
                            mapped = value
                            break
                    title_map = {
                        "google chrome": "Google Chrome",
                        "chrome": "Google Chrome",
                        "microsoft edge": "Microsoft Edge",
                        "edge": "Microsoft Edge",
                        "mozilla firefox": "Mozilla Firefox",
                        "firefox": "Mozilla Firefox",
                        "brave": "Brave",
                        "framer": "Framer",
                        "visual studio code": "VS Code",
                        "code": "VS Code",
                        "cursor": "Cursor",
                        "discord": "Discord",
                        "telegram": "Telegram",
                        "whatsapp": "WhatsApp",
                        "figma": "Figma",
                        "copilot": "Copilot",
                        "command prompt": "Command Prompt",
                        "powershell": "PowerShell",
                        "windows terminal": "Windows Terminal",
                        "file explorer": "File Explorer",
                        "settings": "Settings",
                    }
                    if not mapped:
                        for key, value in title_map.items():
                            if key in tl:
                                mapped = value
                                break
                    if mapped and mapped not in app_set:
                        app_set.add(mapped)
                        apps.append(mapped)
                    # Show opened folders as running entries too (Explorer windows).
                    if "file explorer" in tl and " - " in title:
                        folder_name = title.split(" - ", 1)[0].strip()
                        if 1 < len(folder_name) <= 60 and folder_name.lower() not in {"file explorer"}:
                            if folder_name not in app_set:
                                app_set.add(folder_name)
                                apps.append(folder_name)
                    # Fallback: include visible window title for unknown opened apps/windows.
                    if not mapped:
                        clean_title = title.strip()
                        if 2 < len(clean_title) <= 70 and clean_title.lower() not in app_set:
                            app_set.add(clean_title)
                            apps.append(clean_title)
            except Exception:
                pass

        # 2) Fallback to process-based detection only when window enumeration is unavailable.
        # This keeps sidebar focused on actually open/visible apps.
        if gw is None:
            try:
                for proc in psutil.process_iter(["name"]):
                    name = (proc.info.get("name") or "").lower()
                    if not name or any(p in name for p in system_processes):
                        continue
                    for exe, display in real_apps.items():
                        if exe in name and display not in app_set:
                            app_set.add(display)
                            apps.append(display)
                            break
            except Exception:
                pass
        self.last_apps_check = time.time()
        self.last_apps_list = sorted(apps)
        return self.last_apps_list

    def _running_apps_lookup(self):
        """Map normalized running app names to display names."""
        lookup = {}
        for display in self.get_running_apps(force_refresh=True):
            key = self._normalize_app_name(display)
            if key:
                lookup[key] = display
        return lookup

    def get_closed_apps(self, limit=20):
        """Installed apps that are currently not running."""
        self._build_app_launch_index()
        self._build_start_apps_index()
        installed = set(self.app_launch_index.keys()) | set(self.start_apps_index.keys())
        running = set(self._running_apps_lookup().keys())
        closed = sorted([name for name in installed if name not in running])
        return closed[:limit]

    def get_app_status(self, app_name):
        """Return Task-Manager-like status for a single app."""
        query = self._normalize_app_name(app_name)
        if not query:
            return {"found": False, "installed": False, "running": False, "matched": None}

        running_lookup = self._running_apps_lookup()
        run_key = self._find_best_index_match(query, running_lookup)
        if run_key:
            return {
                "found": True,
                "installed": True,
                "running": True,
                "matched": running_lookup[run_key],
            }

        self._build_app_launch_index()
        self._build_start_apps_index()
        installed_lookup = {}
        for key in self.app_launch_index:
            installed_lookup[key] = key
        for key in self.start_apps_index:
            installed_lookup[key] = key
        inst_key = self._find_best_index_match(query, installed_lookup)
        if inst_key:
            return {"found": True, "installed": True, "running": False, "matched": inst_key.title()}

        return {"found": False, "installed": False, "running": False, "matched": None}

    def get_system_stats(self):
        stats = {
            "cpu": psutil.cpu_percent(interval=0.5),
            "cpu_count": psutil.cpu_count(),
            "memory": psutil.virtual_memory().percent,
            "memory_used": round(psutil.virtual_memory().used / (1024**3), 2),
            "memory_total": round(psutil.virtual_memory().total / (1024**3), 2),
            "disk": psutil.disk_usage("/").percent,
            "disk_free": round(psutil.disk_usage("/").free / (1024**3), 2),
            "disk_total": round(psutil.disk_usage("/").total / (1024**3), 2),
        }
        battery = psutil.sensors_battery()
        if battery:
            stats["battery"] = battery.percent
            stats["power_plugged"] = battery.power_plugged
        return stats

    def get_network_info(self):
        info = {}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            info["ip"] = s.getsockname()[0]
            s.close()
        except Exception:
            info["ip"] = "Offline"
        try:
            requests.get("https://www.google.com", timeout=2)
            info["internet"] = True
        except Exception:
            info["internet"] = False
        try:
            result = self._run_allowed_subprocess(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in result.stdout.split("\n"):
                if "SSID" in line and "BSSID" not in line:
                    info["wifi"] = line.split(":")[1].strip()
        except Exception:
            pass
        return info

    def _run_powershell(self, script, timeout=12):
        result = self._run_allowed_subprocess(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        return result.returncode, stdout, stderr

    def _extract_percent_value(self, text, default=10, min_value=0, max_value=100):
        m = re.search(r"(\d{1,3})\s*%?", (text or ""))
        if not m:
            return max(min_value, min(max_value, int(default)))
        return max(min_value, min(max_value, int(m.group(1))))

    def set_wifi_enabled(self, enabled):
        desired = bool(enabled)
        # Try modern adapter cmdlets first.
        action_cmd = "Enable-NetAdapter" if desired else "Disable-NetAdapter"
        script = (
            "$adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | "
            "Where-Object { $_.InterfaceDescription -match 'Wi-?Fi|Wireless|802.11' -or $_.Name -match 'Wi-?Fi|Wireless|WLAN' }; "
            "if(-not $adapters){ exit 3 }; "
            f"$adapters | ForEach-Object {{ {action_cmd} -Name $_.Name -Confirm:$false -ErrorAction SilentlyContinue | Out-Null }}; "
            "($adapters | Select-Object -ExpandProperty Name) -join ', '"
        )
        try:
            rc, out, err = self._run_powershell(script, timeout=14)
            if rc == 0:
                return f"Wi-Fi turned {'on' if desired else 'off'} ({out or 'adapter updated'})."
        except Exception:
            pass

        # Fallback: common interface names.
        tried = []
        for name in ["Wi-Fi", "WiFi", "WLAN"]:
            try:
                self._run_allowed_subprocess(
                    ["netsh", "interface", "set", "interface", f"name={name}", f"admin={'enabled' if desired else 'disabled'}"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                tried.append(name)
            except Exception:
                continue
        if tried:
            return f"Requested Wi-Fi {'on' if desired else 'off'} via netsh ({', '.join(tried)})."
        return "Could not change Wi-Fi state. This action may require Administrator permissions."

    def list_wifi_networks(self):
        try:
            result = self._run_allowed_subprocess(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (result.stdout or "")
            ssids = []
            seen = set()
            for line in output.splitlines():
                ln = line.strip()
                if not ln.lower().startswith("ssid ") or "bssid" in ln.lower():
                    continue
                if ":" not in ln:
                    continue
                name = ln.split(":", 1)[1].strip()
                if not name:
                    name = "<Hidden>"
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                ssids.append(name)
            if not ssids:
                return "No Wi-Fi networks found."
            return "Available Wi-Fi networks:\n" + "\n".join([f"  - {s}" for s in ssids[:40]])
        except Exception as e:
            return f"Could not list Wi-Fi networks: {e}"

    def set_bluetooth_enabled(self, enabled):
        desired = bool(enabled)
        action_cmd = "Enable-PnpDevice" if desired else "Disable-PnpDevice"
        script = (
            "$dev = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
            "Where-Object { $_.InstanceId -and $_.FriendlyName }; "
            "if(-not $dev){ exit 3 }; "
            f"$dev | ForEach-Object {{ {action_cmd} -InstanceId $_.InstanceId -Confirm:$false -ErrorAction SilentlyContinue | Out-Null }}; "
            "($dev | Select-Object -ExpandProperty FriendlyName) -join ', '"
        )
        try:
            rc, out, err = self._run_powershell(script, timeout=16)
            if rc == 0:
                return f"Bluetooth turned {'on' if desired else 'off'} ({out or 'devices updated'})."
            if "access is denied" in (err or "").lower():
                return "Could not change Bluetooth state: Administrator permission required."
            return f"Could not change Bluetooth state: {err or 'operation failed'}"
        except Exception as e:
            return f"Could not change Bluetooth state: {e}"

    def list_bluetooth_devices(self):
        script = (
            "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName,Status | ConvertTo-Json -Compress"
        )
        try:
            rc, out, err = self._run_powershell(script, timeout=10)
            if rc != 0 or not out:
                return "No Bluetooth devices found."
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            lines = []
            for item in data:
                name = (item.get("FriendlyName") or "").strip()
                status = (item.get("Status") or "").strip() or "Unknown"
                if name:
                    lines.append(f"  - {name} ({status})")
            if not lines:
                return "No Bluetooth devices found."
            return "Bluetooth devices:\n" + "\n".join(lines[:40])
        except Exception as e:
            return f"Could not list Bluetooth devices: {e}"

    def set_brightness_percent(self, value):
        val = max(0, min(100, int(value)))
        script = (
            "$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue; "
            "if(-not $m){ exit 3 }; "
            f"$m | ForEach-Object {{ $_.WmiSetBrightness(1, {val}) | Out-Null }}; "
            f"'{val}'"
        )
        try:
            rc, out, err = self._run_powershell(script, timeout=10)
            if rc == 0:
                return f"Brightness set to {val}%."
            return "Could not set brightness. This is usually unsupported on external monitors."
        except Exception as e:
            return f"Could not set brightness: {e}"

    def change_brightness(self, delta):
        get_script = "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CurrentBrightness"
        try:
            rc, out, err = self._run_powershell(get_script, timeout=8)
            if rc != 0 or not out:
                return "Could not read current brightness."
            current = self._extract_percent_value(out, default=50, min_value=0, max_value=100)
            target = max(0, min(100, current + int(delta)))
            return self.set_brightness_percent(target)
        except Exception as e:
            return f"Could not change brightness: {e}"

    def _audio_powershell_core(self):
        return (
            "Add-Type -TypeDefinition @\"\n"
            "using System;\nusing System.Runtime.InteropServices;\n"
            "[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
            "interface IAudioEndpointVolume {\n"
            "int RegisterControlChangeNotify(IntPtr pNotify); int UnregisterControlChangeNotify(IntPtr pNotify); int GetChannelCount(out uint pnChannelCount);\n"
            "int SetMasterVolumeLevel(float fLevelDB, Guid pguidEventContext); int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);\n"
            "int GetMasterVolumeLevel(out float pfLevelDB); int GetMasterVolumeLevelScalar(out float pfLevel);\n"
            "int SetChannelVolumeLevel(uint nChannel, float fLevelDB, Guid pguidEventContext); int SetChannelVolumeLevelScalar(uint nChannel, float fLevel, Guid pguidEventContext);\n"
            "int GetChannelVolumeLevel(uint nChannel, out float pfLevelDB); int GetChannelVolumeLevelScalar(uint nChannel, out float pfLevel);\n"
            "int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext); int GetMute(out bool pbMute);\n"
            "int GetVolumeStepInfo(out uint pnStep, out uint pnStepCount); int VolumeStepUp(Guid pguidEventContext); int VolumeStepDown(Guid pguidEventContext);\n"
            "int QueryHardwareSupport(out uint pdwHardwareSupportMask); int GetVolumeRange(out float pflVolumeMindB, out float pflVolumeMaxdB, out float pflVolumeIncrementdB);\n"
            "}\n"
            "[Guid(\"A95664D2-9614-4F35-A746-DE8DB63617E6\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
            "interface IMMDeviceEnumerator { int NotImpl1(); int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppDevice); }\n"
            "[Guid(\"D666063F-1587-4E43-81F1-B948E807363F\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
            "interface IMMDevice { int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface); }\n"
            "[ComImport, Guid(\"BCDE0395-E52F-467C-8E3D-C4579291692E\")] class MMDeviceEnumeratorComObject {}\n"
            "public class AudioUtil {\n"
            "const int CLSCTX_ALL = 23;\n"
            "static IAudioEndpointVolume V() { IMMDeviceEnumerator en=(IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject()); IMMDevice dev; en.GetDefaultAudioEndpoint(0,1,out dev); object epv; Guid g=typeof(IAudioEndpointVolume).GUID; dev.Activate(ref g, CLSCTX_ALL, IntPtr.Zero, out epv); return (IAudioEndpointVolume)epv; }\n"
            "public static float GetVol() { float v; V().GetMasterVolumeLevelScalar(out v); return v; }\n"
            "public static void SetVol(float x) { if (x<0) x=0; if (x>1) x=1; V().SetMasterVolumeLevelScalar(x, Guid.Empty); }\n"
            "public static bool GetMute() { bool m; V().GetMute(out m); return m; }\n"
            "public static void SetMute(bool m) { V().SetMute(m, Guid.Empty); }\n"
            "}\n"
            "\"@ -Language CSharp"
        )

    def set_volume_percent(self, value):
        val = max(0, min(100, int(value)))
        script = self._audio_powershell_core() + f"; [AudioUtil]::SetVol({val}/100.0); '{val}'"
        try:
            rc, out, err = self._run_powershell(script, timeout=16)
            if rc == 0:
                return f"Volume set to {val}%."
            return f"Could not set volume: {err or 'operation failed'}"
        except Exception as e:
            return f"Could not set volume: {e}"

    def change_volume(self, delta):
        script = (
            self._audio_powershell_core()
            + f"; $v=[AudioUtil]::GetVol()*100.0; $n=[Math]::Max(0,[Math]::Min(100,$v+({int(delta)}))); [AudioUtil]::SetVol($n/100.0); [int]$n"
        )
        try:
            rc, out, err = self._run_powershell(script, timeout=16)
            if rc == 0:
                current = self._extract_percent_value(out, default=0, min_value=0, max_value=100)
                return f"Volume is now {current}%."
            return f"Could not change volume: {err or 'operation failed'}"
        except Exception as e:
            return f"Could not change volume: {e}"

    def set_mute(self, muted):
        desired = bool(muted)
        script = self._audio_powershell_core() + f"; [AudioUtil]::SetMute({'$true' if desired else '$false'}); '{'Muted' if desired else 'Unmuted'}'"
        try:
            rc, out, err = self._run_powershell(script, timeout=16)
            if rc == 0:
                return "Sound muted." if desired else "Sound unmuted."
            return f"Could not change mute state: {err or 'operation failed'}"
        except Exception as e:
            return f"Could not change mute state: {e}"

    def _handle_system_control_command(self, user_input, cmd_lower):
        text = (user_input or "").strip()
        lower = (cmd_lower or "").strip()

        # Skip system-control routing when the user is dictating content for a file/document.
        # Keywords like "volume", "brightness", "sleep", etc. may appear in the dictated text.
        if re.search(
            r"\b(create|make|write|generate|put|save|build)\b[^\n]{0,80}\b(file|doc|document|docx|word|pdf|folder|txt|note)\b"
            r"|\b(file|doc|document|docx|word|pdf|folder|txt|note)\b[^\n]{0,80}\b(create|make|write|generate|save|build)\b"
            r"|\b(write|type|insert|add|put)\b[^\n]{0,80}\b(inside|into|in|content|text|following)\b|\b\w+\b\s+inside\s+this\s*:"
            r"|\b(?:write|create|make|put|add|generate)\b[^\n]{0,60}(?::\s*\S|\s*-\s*\S)",
            lower
        ):
            return None

        if re.search(r"\b(list|show|scan|available)\b", lower) and re.search(r"\b(wi[\-\s]?fi|wlan|wireless)\b", lower):
            return self.list_wifi_networks()
        if re.search(r"\b(wi[\-\s]?fi|wlan|wireless)\b", lower):
            if re.search(r"\b(turn|switch|set|enable)\b", lower) and re.search(r"\bon\b", lower):
                return self.set_wifi_enabled(True)
            if re.search(r"\b(turn|switch|set|disable)\b", lower) and re.search(r"\boff\b", lower):
                return self.set_wifi_enabled(False)

        if re.search(r"\b(list|show|status|paired|devices?)\b", lower) and re.search(r"\bbluetooth\b", lower):
            return self.list_bluetooth_devices()
        if re.search(r"\bbluetooth\b", lower):
            if re.search(r"\b(turn|switch|set|enable)\b", lower) and re.search(r"\bon\b", lower):
                return self.set_bluetooth_enabled(True)
            if re.search(r"\b(turn|switch|set|disable)\b", lower) and re.search(r"\boff\b", lower):
                return self.set_bluetooth_enabled(False)

        if re.search(r"\b(brightness|luminosity|screen light|light level)\b", lower):
            if re.search(r"\b(increase|up|higher|raise)\b", lower):
                step = self._extract_percent_value(lower, default=10, min_value=1, max_value=50)
                return self.change_brightness(step)
            if re.search(r"\b(decrease|down|lower|reduce)\b", lower):
                step = self._extract_percent_value(lower, default=10, min_value=1, max_value=50)
                return self.change_brightness(-step)
            value = self._extract_percent_value(lower, default=-1, min_value=0, max_value=100)
            if value >= 0:
                return self.set_brightness_percent(value)

        if re.search(r"\b(volume|sound|audio)\b", lower):
            if re.search(r"\b(unmute)\b", lower):
                return self.set_mute(False)
            if re.search(r"\b(mute|silent)\b", lower):
                return self.set_mute(True)
            if re.search(r"\b(increase|up|higher|raise)\b", lower):
                step = self._extract_percent_value(lower, default=8, min_value=1, max_value=40)
                return self.change_volume(step)
            if re.search(r"\b(decrease|down|lower|reduce)\b", lower):
                step = self._extract_percent_value(lower, default=8, min_value=1, max_value=40)
                return self.change_volume(-step)
            value = self._extract_percent_value(lower, default=-1, min_value=0, max_value=100)
            if value >= 0:
                return self.set_volume_percent(value)

        if re.search(r"\b(open|show)\b", lower) and re.search(r"\b(settings?)\b", lower):
            if "wifi" in lower or "network" in lower:
                try:
                    self._popen_allowed(["explorer.exe", "ms-settings:network-wifi"])
                    return "Opened Wi-Fi settings."
                except Exception:
                    return "Could not open Wi-Fi settings."
            if "bluetooth" in lower:
                try:
                    self._popen_allowed(["explorer.exe", "ms-settings:bluetooth"])
                    return "Opened Bluetooth settings."
                except Exception:
                    return "Could not open Bluetooth settings."
            if "sound" in lower or "volume" in lower or "audio" in lower:
                try:
                    self._popen_allowed(["explorer.exe", "ms-settings:sound"])
                    return "Opened Sound settings."
                except Exception:
                    return "Could not open Sound settings."
            if "brightness" in lower or "display" in lower:
                try:
                    self._popen_allowed(["explorer.exe", "ms-settings:display"])
                    return "Opened Display settings."
                except Exception:
                    return "Could not open Display settings."
        return None

    def _open_windows_settings(self, topic):
        t = (topic or "").lower()
        settings_map = [
            ("wifi", "ms-settings:network-wifi"),
            ("network", "ms-settings:network"),
            ("bluetooth", "ms-settings:bluetooth"),
            ("sound", "ms-settings:sound"),
            ("audio", "ms-settings:sound"),
            ("volume", "ms-settings:sound"),
            ("display", "ms-settings:display"),
            ("brightness", "ms-settings:display"),
            ("night light", "ms-settings:nightlight"),
            ("apps", "ms-settings:appsfeatures"),
            ("startup", "ms-settings:startupapps"),
            ("privacy", "ms-settings:privacy"),
            ("windows update", "ms-settings:windowsupdate"),
            ("update", "ms-settings:windowsupdate"),
            ("storage", "ms-settings:storagesense"),
            ("battery", "ms-settings:batterysaver"),
            ("notifications", "ms-settings:notifications"),
            ("accounts", "ms-settings:yourinfo"),
            ("time", "ms-settings:dateandtime"),
            ("language", "ms-settings:regionlanguage"),
            ("keyboard", "ms-settings:typing"),
            ("mouse", "ms-settings:mousetouchpad"),
            ("camera", "ms-settings:privacy-webcam"),
            ("microphone", "ms-settings:privacy-microphone"),
            ("vpn", "ms-settings:network-vpn"),
            ("proxy", "ms-settings:network-proxy"),
            ("taskbar", "ms-settings:taskbar"),
            ("personalization", "ms-settings:personalization"),
        ]
        uri = "ms-settings:"
        for key, value in settings_map:
            if key in t:
                uri = value
                break
        try:
            self._popen_allowed(["explorer.exe", uri])
            if uri == "ms-settings:":
                return "Opened Windows Settings."
            return f"Opened Settings: {uri.replace('ms-settings:', '')}."
        except Exception as e:
            return f"Could not open Settings: {e}"

    def _clipboard_get(self):
        script = "Get-Clipboard -Raw -ErrorAction SilentlyContinue"
        try:
            rc, out, err = self._run_powershell(script, timeout=6)
            if rc != 0:
                return "Could not read clipboard."
            txt = (out or "").strip()
            if not txt:
                return "Clipboard is empty."
            if len(txt) > 1200:
                txt = txt[:1200] + "\n... (truncated)"
            return "Clipboard:\n" + txt
        except Exception as e:
            return f"Could not read clipboard: {e}"

    def _clipboard_set(self, value):
        text = (value or "").strip()
        if not text:
            return "Please provide text to copy."
        safe = text.replace("'", "''")
        script = f"Set-Clipboard -Value '{safe}'"
        try:
            rc, out, err = self._run_powershell(script, timeout=6)
            if rc == 0:
                return "Copied to clipboard."
            return f"Could not set clipboard: {err or 'operation failed'}"
        except Exception as e:
            return f"Could not set clipboard: {e}"

    def _clipboard_clear(self):
        try:
            rc, out, err = self._run_powershell("Set-Clipboard -Value ''", timeout=6)
            if rc == 0:
                return "Clipboard cleared."
            return f"Could not clear clipboard: {err or 'operation failed'}"
        except Exception as e:
            return f"Could not clear clipboard: {e}"

    def _execute_windows_power_action(self, action):
        a = (action or "").strip().lower()
        try:
            if a == "shutdown":
                self._run_allowed_subprocess(["shutdown", "/s", "/t", "0"], capture_output=True, text=True, timeout=5)
                return "Shutting down now."
            if a == "restart":
                self._run_allowed_subprocess(["shutdown", "/r", "/t", "0"], capture_output=True, text=True, timeout=5)
                return "Restarting now."
            if a == "signout":
                self._run_allowed_subprocess(["shutdown", "/l"], capture_output=True, text=True, timeout=5)
                return "Signing out now."
            if a == "sleep":
                self._run_allowed_subprocess(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], capture_output=True, text=True, timeout=5)
                return "Putting PC to sleep."
            if a == "lock":
                self._run_allowed_subprocess(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True, text=True, timeout=5)
                return "Locking your PC."
            if a == "cancel_shutdown":
                self._run_allowed_subprocess(["shutdown", "/a"], capture_output=True, text=True, timeout=5)
                return "Cancelled pending shutdown/restart."
        except Exception as e:
            return f"Could not execute power action '{a}': {e}"
        return "Unknown power action."

    def _handle_windows_core_command(self, user_input, cmd_lower):
        text = (user_input or "").strip()
        lower = (cmd_lower or "").strip()

        # Open settings pages.
        if re.search(r"\b(open|show|go to)\b", lower) and re.search(r"\bsettings?\b", lower):
            return self._open_windows_settings(lower)

        # Open common admin/system tools.
        # Guard: skip if this is a content-writing/file-creation command Ã¢Â€Â” the content
        # body may contain words like "launch", "open", "close" that describe capabilities.
        _core_is_content_task = bool(re.search(
            r"\b(create|make|write|generate|put|save|build)\b[^\n]{0,80}\b(file|doc|document|docx|word|pdf|folder|txt|note)\b"
            r"|\b(write|type|insert|add|put)\b[^\n]{0,80}\b(inside|into|in|content|text|following)\b|\b\w+\b\s+inside\s+this\s*:"
            r"|\b(?:write|create|make|put|add|generate)\b[^\n]{0,60}(?::\s*\S|\s*-\s*\S)",
            lower
        ))
        if not _core_is_content_task and re.search(r"\b(open|show|start|launch)\b", lower):
            if "task manager" in lower:
                try:
                    self._popen_allowed(["taskmgr.exe"])
                    return "Opened Task Manager."
                except Exception as e:
                    return f"Could not open Task Manager: {e}"
            if "control panel" in lower:
                try:
                    self._popen_allowed(["control.exe"])
                    return "Opened Control Panel."
                except Exception as e:
                    return f"Could not open Control Panel: {e}"
            if "device manager" in lower:
                try:
                    rc, _, err = self._run_powershell("Start-Process devmgmt.msc", timeout=8)
                    if rc != 0:
                        return f"Could not open Device Manager: {err or 'unknown error'}"
                    return "Opened Device Manager."
                except Exception as e:
                    return f"Could not open Device Manager: {e}"
            if "services" in lower and "settings" not in lower:
                try:
                    rc, _, err = self._run_powershell("Start-Process services.msc", timeout=8)
                    if rc != 0:
                        return f"Could not open Services: {err or 'unknown error'}"
                    return "Opened Services."
                except Exception as e:
                    return f"Could not open Services: {e}"

        # Clipboard control.
        if "clipboard" in lower or "copyboard" in lower:
            if re.search(r"\b(show|get|read|what(?:'s| is) in)\b", lower):
                return self._clipboard_get()
            if re.search(r"\b(clear|empty)\b", lower):
                return self._clipboard_clear()
            m = re.search(r"\b(?:set|copy)\s+(?:clipboard\s+)?(?:to\s+)?(.+)$", text, flags=re.IGNORECASE)
            if m:
                return self._clipboard_set(m.group(1))
            return "Clipboard commands: 'show clipboard', 'set clipboard to ...', 'clear clipboard'."

        # Power/session actions with confirmation for destructive ones.
        # Guard: skip power-action routing if this looks like a file/doc creation or
        # content-writing request (the user might be dictating text that contains
        # power-related words such as "sleep", "lock", "restart", etc.)
        _is_content_task = bool(re.search(
            r"\b(create|make|write|generate|put|save|open|build)\b[^\n]{0,60}\b(file|doc|document|docx|word|pdf|folder|txt|note)\b"
            r"|\b(file|doc|document|docx|word|pdf|folder|txt|note)\b[^\n]{0,60}\b(create|make|write|generate|save|build)\b"
            r"|\b(write|type|insert|add|put)\b[^\n]{0,60}\b(inside|into|in|content|text|following)\b|\b\w+\b\s+inside\s+this\s*:"
            r"|\b(?:write|create|make|put|add|generate)\b[^\n]{0,60}(?::\s*\S|\s*-\s*\S)",
            lower
        ))

        if not _is_content_task:
            if re.search(r"\bcancel\s+(shutdown|restart)\b", lower):
                return self._execute_windows_power_action("cancel_shutdown")
            if (re.search(r"\b(lock)\b", lower)
                    and re.search(r"\b(pc|computer|windows|screen|session|workstation|device)\b", lower)
                    and not re.match(r"^(?:rename|move|copy|delete|remove|create|make|put|place)\b", lower.strip())):
                return self._execute_windows_power_action("lock")
            if (re.search(r"\b(sleep)\b", lower)
                    and re.search(r"\b(pc|computer|windows|device|machine|system)\b", lower)):
                return self._set_pending_question(
                    "Permission Required",
                    "Put the computer to sleep now?",
                    [
                        {"label": "Allow once", "description": "Sleep immediately", "value": "allow"},
                        {"label": "Deny", "description": "Do not sleep now", "value": "deny"},
                    ],
                    action="windows_power",
                    payload={"action": "sleep"},
                    on_deny="Sleep cancelled.",
                )
            if re.search(r"\b(sign out|log out|logout)\b", lower):
                return self._set_pending_question(
                    "Permission Required",
                    "Sign out of Windows now?",
                    [
                        {"label": "Allow once", "description": "Sign out immediately", "value": "allow"},
                        {"label": "Deny", "description": "Stay signed in", "value": "deny"},
                    ],
                    action="windows_power",
                    payload={"action": "signout"},
                    on_deny="Sign out cancelled.",
                )
            if re.search(r"\b(restart|reboot)\b", lower):
                return self._set_pending_question(
                    "Permission Required",
                    "Restart the computer now?",
                    [
                        {"label": "Allow once", "description": "Restart immediately", "value": "allow"},
                        {"label": "Deny", "description": "Do not restart", "value": "deny"},
                    ],
                    action="windows_power",
                    payload={"action": "restart"},
                    on_deny="Restart cancelled.",
                )
            if re.search(r"\b(shut down|shutdown|power off|turn off pc|turn off computer)\b", lower):
                return self._set_pending_question(
                    "Permission Required",
                    "Shut down the computer now?",
                    [
                        {"label": "Allow once", "description": "Shut down immediately", "value": "allow"},
                        {"label": "Deny", "description": "Keep computer running", "value": "deny"},
                    ],
                    action="windows_power",
                    payload={"action": "shutdown"},
                    on_deny="Shutdown cancelled.",
                )
        return None

    def take_screenshot(self):
        filename = f"screenshot_{int(time.time())}.png"
        pyautogui.screenshot(filename)
        return filename

    def _normalize_app_name(self, name):
        cleaned = re.sub(r"\.(exe|lnk|url|appref-ms)$", "", (name or "").lower().strip())
        cleaned = re.sub(r"[\(\)\[\]\{\}\-_,.:]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        aliases = {
            "vscode": "vs code",
            "vs code": "vs code",
            "code": "vs code",
            "google": "google chrome",
            "ms edge": "microsoft edge",
            "edge": "microsoft edge",
            "cmd": "command prompt",
            "terminal": "windows terminal",
        }
        return aliases.get(cleaned, cleaned)

    def _known_app_aliases(self):
        """Canonical app aliases to avoid routing app-like requests to Desktop files."""
        return {
            "vscode": "vs code",
            "vs code": "vs code",
            "visual studio code": "vs code",
            "code": "vs code",
            "visual studio": "visual studio",
            "chrome": "chrome",
            "google chrome": "chrome",
            "google": "chrome",
            "firefox": "firefox",
            "edge": "microsoft edge",
            "microsoft edge": "microsoft edge",
            "brave": "brave",
            "discord": "discord",
            "telegram": "telegram",
            "whatsapp": "whatsapp",
            "spotify": "spotify",
            "notepad": "notepad",
            "calculator": "calculator",
            "calc": "calculator",
            "explorer": "file explorer",
            "file explorer": "file explorer",
            "cmd": "command prompt",
            "command prompt": "command prompt",
            "powershell": "powershell",
            "terminal": "windows terminal",
            "windows terminal": "windows terminal",
            "cursor": "cursor",
            "copilot": "copilot",
            "claude": "claude",
            "claude.ai": "claude",
            "anthropic claude": "claude",
            # Microsoft Office
            "word": "microsoft word",
            "ms word": "microsoft word",
            "microsoft word": "microsoft word",
            "excel": "microsoft excel",
            "ms excel": "microsoft excel",
            "microsoft excel": "microsoft excel",
            "powerpoint": "microsoft powerpoint",
            "ppt": "microsoft powerpoint",
            "ms powerpoint": "microsoft powerpoint",
            "microsoft powerpoint": "microsoft powerpoint",
            "outlook": "microsoft outlook",
            "ms outlook": "microsoft outlook",
            "microsoft outlook": "microsoft outlook",
            "onenote": "microsoft onenote",
            "ms onenote": "microsoft onenote",
            "access": "microsoft access",
            "ms access": "microsoft access",
            # Communication & collaboration
            "zoom": "zoom",
            "zoom meeting": "zoom",
            "teams": "microsoft teams",
            "ms teams": "microsoft teams",
            "microsoft teams": "microsoft teams",
            "slack": "slack",
            "skype": "skype",
            "msteams": "microsoft teams",
            # Media players
            "vlc": "vlc media player",
            "vlc player": "vlc media player",
            "vlc media player": "vlc media player",
            "winamp": "winamp",
            # Archive tools
            "7zip": "7-zip",
            "7-zip": "7-zip",
            "7 zip": "7-zip",
            "winrar": "winrar",
            # Built-in Windows apps
            "paint": "paint",
            "ms paint": "paint",
            "mspaint": "paint",
            "snipping tool": "snipping tool",
            "snip": "snipping tool",
            "snip and sketch": "snip & sketch",
            "snip & sketch": "snip & sketch",
            "wordpad": "wordpad",
            "sticky notes": "sticky notes",
            "photos": "microsoft photos",
            "camera": "camera",
            "maps": "maps",
            "mail": "mail",
            "calendar": "calendar",
            "clock": "clock",
            "weather": "weather",
            "store": "microsoft store",
            "microsoft store": "microsoft store",
            # Editors / IDEs
            "pycharm": "pycharm",
            "intellij": "intellij idea",
            "intellij idea": "intellij idea",
            "rider": "rider",
            "webstorm": "webstorm",
            "android studio": "android studio",
            "sublime": "sublime text",
            "sublime text": "sublime text",
            "atom": "atom",
            "brackets": "brackets",
            # Dev tools
            "git": "git",
            "git bash": "git bash",
            "github desktop": "github desktop",
            "postman": "postman",
            "insomnia": "insomnia",
            "dbeaver": "dbeaver",
            "wsl": "windows subsystem for linux",
            # Creative / design
            "gimp": "gimp",
            "inkscape": "inkscape",
            "blender": "blender",
            "figma": "figma",
            "audacity": "audacity",
            "obs": "obs studio",
            "obs studio": "obs studio",
            "handbrake": "handbrake",
            # Productivity
            "notion": "notion",
            "obsidian": "obsidian",
            "trello": "trello",
            # Remote desktop
            "anydesk": "anydesk",
            "teamviewer": "teamviewer",
            "remote desktop": "remote desktop connection",
            "rdp": "remote desktop connection",
            # Gaming
            "steam": "steam",
            "epic": "epic games launcher",
            "epic games": "epic games launcher",
            "origin": "origin",
            "ubisoft connect": "ubisoft connect",
            "uplay": "ubisoft connect",
            "battle.net": "battle.net",
            "battlenet": "battle.net",
        }

    def _canonicalize_known_app_name(self, app_name):
        raw = self._normalize_app_name(app_name)
        if not raw:
            return ""
        return self._known_app_aliases().get(raw, raw)

    def _looks_like_known_app_request(self, app_name):
        raw = self._normalize_app_name(app_name)
        if not raw:
            return False
        aliases = self._known_app_aliases()
        if raw in aliases:
            return True
        return any(raw in k or k in raw for k in aliases.keys())

    def _build_app_launch_index(self, force=False):
        if not force and self.app_launch_index and (time.time() - self.app_index_last_build) < 600:
            return
        index = {}
        start_menu_paths = [
            os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        ]
        valid_ext = {".lnk", ".url", ".appref-ms", ".exe"}
        for base in start_menu_paths:
            if not base or not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                for filename in files:
                    if os.path.splitext(filename)[1].lower() not in valid_ext:
                        continue
                    key = self._normalize_app_name(os.path.splitext(filename)[0])
                    if key and key not in index:
                        index[key] = os.path.join(root, filename)
        self.app_launch_index = index
        self.app_index_last_build = time.time()

    def _build_start_apps_index(self, force=False):
        """Index Start Apps (UWP/MSIX) so names like WhatsApp/Copilot can launch."""
        if not force and self.start_apps_index and (time.time() - self.start_apps_last_build) < 600:
            return

        index = {}
        cmd = (
            "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        )
        try:
            result = self._run_allowed_subprocess(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=8,
            )
            payload = (result.stdout or "").strip()
            if payload:
                data = json.loads(payload)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    name = (item.get("Name") or "").strip()
                    app_id = (item.get("AppID") or "").strip()
                    if not name or not app_id:
                        continue
                    index[self._normalize_app_name(name)] = app_id
        except Exception:
            index = {}

        self.start_apps_index = index
        self.start_apps_last_build = time.time()

    def _find_best_index_match(self, normalized_query, mapping, strict=False):
        """Find best match key with exact/contains/fuzzy search.

        strict=True: skip substring matching and use a higher fuzzy cutoff (0.85).
        Use strict=True for Desktop file lookups to prevent app names like "word"
        from accidentally matching file names like "my word document".
        """
        if not normalized_query or not mapping:
            return None
        if normalized_query in mapping:
            return normalized_query
        # Avoid dangerous fuzzy matches for tiny tokens like "it".
        if len(normalized_query) < 3:
            return None
        if not strict:
            contains = [k for k in mapping if normalized_query in k or k in normalized_query]
            if contains:
                return sorted(contains, key=len)[0]
        cutoff = 0.85 if strict else 0.72
        fuzzy = get_close_matches(normalized_query, list(mapping.keys()), n=1, cutoff=cutoff)
        return fuzzy[0] if fuzzy else None

    def _guess_open_target(self, raw_input):
        text = (raw_input or "").strip()
        lowered = text.lower()
        if "open" not in lowered:
            return ""
        after_open = text[lowered.find("open") + 4 :].strip(" :,-")
        cleaned = after_open
        for suffix in ["please", "for me", "now", "app", "application", "on my device", "on my computer", "on pc"]:
            cleaned = re.sub(r"\b" + re.escape(suffix) + r"\b", "", cleaned, flags=re.IGNORECASE).strip(" ,.-")
        return cleaned

    def _extract_app_action(self, raw_input):
        """Extract natural-language app actions (open/close + target)."""
        text = (raw_input or "").strip()
        lowered = text.lower().strip()
        if not lowered:
            return None, ""

        # Don't treat status questions as actions.
        if re.search(r"\b(is|whether|check|do you see|can you see)\b", lowered) and re.search(r"\b(open|running|closed)\b", lowered):
            return None, ""

        if "search" in lowered:
            return None, ""

        action = None
        if re.search(r"\b(open|launch|start|run)\b", lowered):
            action = "open"
        elif re.search(r"\b(close|quit|exit|terminate|kill)\b", lowered):
            action = "close"
        else:
            return None, ""

        # remove leading polite phrases and keep content after first action verb
        working = re.sub(r"^\s*(can you|could you|would you|please|pls|plz)\s+", "", text, flags=re.IGNORECASE).strip()
        m = re.search(r"\b(open|launch|start|run|close|quit|exit|terminate|kill)\b(.*)$", working, flags=re.IGNORECASE)
        if not m:
            return None, ""
        target = (m.group(2) or "").strip(" ,.-?!")

        # Strip leading filler
        target = re.sub(r"^\s*(for me|the app|app|application)\s+", "", target, flags=re.IGNORECASE).strip()
        # Strip trailing filler Ã¢Â€Â” loop to handle combinations like "for me please"
        _filler_tail = re.compile(r"\s*(for me|please|now|on my device|on my computer|on my pc|on pc|can you|could you)\s*$", re.IGNORECASE)
        for _ in range(4):
            new_target = _filler_tail.sub("", target).strip(" ,.-?!")
            if new_target == target:
                break
            target = new_target
        return action, target

    def open_app(self, app_name):
        normalized_request = self._canonicalize_known_app_name(app_name)
        app_lower = normalized_request or (app_name or "").lower()
        app_paths = {
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "edge": "msedge.exe",
            "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "spotify": "spotify.exe",
            "discord": r"C:\Users\Adam Ben Rejeb\AppData\Local\Discord\Discord.exe",
            "telegram": r"C:\Users\Adam Ben Rejeb\AppData\Roaming\Telegram Desktop\Telegram.exe",
            "vscode": r"C:\Users\Adam Ben Rejeb\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "vs code": r"C:\Users\Adam Ben Rejeb\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "cursor": r"C:\Users\Adam Ben Rejeb\AppData\Local\Programs\cursor\Cursor.exe",
            "command prompt": "cmd.exe",
        }

        # Known app-like names should try app launch first, not Desktop fuzzy matching.
        prefer_app_resolution = self._looks_like_known_app_request(app_name)

        for key, path in app_paths.items():
            if key in app_lower:
                try:
                    exe_name = os.path.basename(path).lower()
                    if exe_name and exe_name in self.allowed_launch_bins and os.path.exists(path):
                        os.startfile(path)
                        self._audit("open_app", "allowed", {"target": key, "mode": "known_path", "path": path})
                        return f"Opened {key}"
                except Exception:
                    self._audit("open_app", "error", {"target": key, "mode": "known_path", "path": path})
                    pass

        # Try Start Menu shortcuts before Desktop files so real apps are found first.
        self._build_app_launch_index()
        normalized = normalized_request or self._normalize_app_name(app_name)
        matched_key = self._find_best_index_match(normalized, self.app_launch_index)
        target = self.app_launch_index.get(matched_key) if matched_key else None
        if target:
            try:
                os.startfile(target)
                self._audit("open_app", "allowed", {"target": target, "mode": "start_menu_link"})
                return f"Opened {app_name}"
            except Exception:
                self._audit("open_app", "error", {"target": target, "mode": "start_menu_link"})
                pass

        # Try Start Apps (UWP/MSIX) entries (works for WhatsApp/Copilot Store apps).
        self._build_start_apps_index()
        start_key = self._find_best_index_match(normalized, self.start_apps_index)
        if start_key:
            app_id = self.start_apps_index[start_key]
            try:
                self._popen_allowed(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
                self._audit("open_app", "allowed", {"target": start_key, "mode": "uwp", "app_id": app_id})
                return f"Opened {start_key}"
            except Exception:
                self._audit("open_app", "error", {"target": start_key, "mode": "uwp", "app_id": app_id})
                pass

        # Open Desktop files/folders by natural name (e.g., "open Candidature") â€”
        # last resort after all app sources are exhausted, so app names like "word"
        # or "zoom" never accidentally open a same-named Desktop file instead of the app.
        if not prefer_app_resolution:
            desktop_item = self._find_desktop_item_path(app_name)
            if desktop_item:
                try:
                    os.startfile(desktop_item)
                    self._audit("open_app", "allowed", {"target": desktop_item, "mode": "desktop_item"})
                    return f"Opened {os.path.basename(desktop_item)}"
                except Exception:
                    self._audit("open_app", "error", {"target": desktop_item, "mode": "desktop_item"})
                    pass

        self._audit("open_app", "blocked", {"target": app_name, "reason": "not_in_allowlist_or_not_found"})
        return None

    def _suggest_open_target(self, target):
        """Suggest likely app names when open command cannot be resolved confidently."""
        normalized = self._normalize_app_name(target)
        if not normalized:
            return ""

        candidates = set(self._known_app_aliases().keys())
        self._build_app_launch_index()
        self._build_start_apps_index()
        candidates.update(self.app_launch_index.keys())
        candidates.update(self.start_apps_index.keys())

        if not candidates:
            return ""

        matches = get_close_matches(normalized, list(candidates), n=1, cutoff=0.78)
        if not matches:
            return ""
        return matches[0]

    # System files that should never be rename/delete targets
    _DESKTOP_SYSTEM_FILES = frozenset({
        "desktop.ini", "thumbs.db", ".ds_store", "ntuser.dat",
    })

    def _find_desktop_item_path(self, query):
        """Find a Desktop item path by exact/contains/fuzzy name."""
        normalized_query = self._normalize_app_name(query)
        if not normalized_query or not os.path.isdir(self.desktop_root):
            return None
        try:
            entries = os.listdir(self.desktop_root)
        except Exception:
            return None

        # If query contains a file extension, require exact case-insensitive match.
        # This prevents "hichem_test.docx" from fuzzily resolving to "hich.docx".
        query_stripped = query.strip()
        _, query_ext = os.path.splitext(query_stripped)
        if query_ext:
            for name in entries:
                if name.lower() in self._DESKTOP_SYSTEM_FILES or name.startswith("."):
                    continue
                if name.lower() == query_stripped.lower():
                    return os.path.join(self.desktop_root, name)
            # No exact match found Ã¢Â€Â” don't fall back to fuzzy for explicit filenames
            return None

        lookup = {}
        for name in entries:
            # Skip hidden system files
            if name.lower() in self._DESKTOP_SYSTEM_FILES or name.startswith("."):
                continue
            base = os.path.splitext(name)[0]
            key = self._normalize_app_name(base) or self._normalize_app_name(name)
            if key and key not in lookup:
                lookup[key] = os.path.join(self.desktop_root, name)

        match_key = self._find_best_index_match(normalized_query, lookup, strict=True)
        if match_key:
            return lookup.get(match_key)
        return None

    def close_app(self, app_name):
        """Close app processes/windows by name."""
        target = self._normalize_app_name(app_name)
        if not target:
            return None

        # Canonical executable hints for known apps.
        exe_hints = {
            "google chrome": ["chrome.exe"],
            "chrome": ["chrome.exe"],
            "brave": ["brave.exe"],
            "microsoft edge": ["msedge.exe"],
            "discord": ["discord.exe"],
            "telegram": ["telegram.exe"],
            "whatsapp": ["whatsapp.exe"],
            "vs code": ["code.exe"],
            "cursor": ["cursor.exe"],
            "notion": ["notion.exe"],
            "command prompt": ["cmd.exe"],
            "powershell": ["powershell.exe", "pwsh.exe"],
            "windows terminal": ["wt.exe", "windowsterminal.exe"],
        }

        candidate_exe = set(exe_hints.get(target, []))
        if not candidate_exe:
            candidate_exe.add(target.replace(" ", "") + ".exe")
            candidate_exe.add(target.replace(" ", "_") + ".exe")

        closed_any = False

        # 1) Try graceful window close for visible windows matching title.
        if gw is not None:
            try:
                for w in gw.getAllWindows():
                    title = (w.title or "").strip().lower()
                    if not title:
                        continue
                    if target in title:
                        try:
                            w.close()
                            closed_any = True
                        except Exception:
                            pass
            except Exception:
                pass

        # 2) Terminate matching processes.
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                base = os.path.splitext(name)[0]
                normalized_base = self._normalize_app_name(base)
                if (
                    name in candidate_exe
                    or target == normalized_base
                    or target in normalized_base
                    or normalized_base in target
                ):
                    try:
                        proc.terminate()
                        closed_any = True
                    except Exception:
                        pass
            except Exception:
                continue

        # 3) Enforce kill for known exe names if still alive.
        for exe in candidate_exe:
            try:
                self._run_allowed_subprocess(
                    ["taskkill", "/F", "/IM", exe],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                pass

        # Verify final status.
        st = self.get_app_status(target)
        if not st["running"]:
            self._audit("close_app", "allowed", {"target": app_name, "matched": st.get("matched")})
            return f"Closed {st['matched'] or app_name}"
        if closed_any:
            self._audit("close_app", "partial", {"target": app_name, "matched": st.get("matched")})
            return f"Tried closing {app_name}, but it still appears to be running."
        self._audit("close_app", "blocked", {"target": app_name, "reason": "not_running_or_not_found"})
        return None

    def search_web(self, query):
        webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
        return f"Searching for: {query}"

    def open_and_read_url(self, url, max_length=3000):
        """
        Open a URL, browse its content, and extract readable text.
        Returns the page content with source citation.
        """
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            # Try Playwright first (better for JavaScript sites)
            if sync_playwright is not None:
                content = self._fetch_with_playwright(url)
                if content:
                    return self._format_web_content(content, url, max_length)
            
            # Fallback to requests
            if SOUP_AVAILABLE:
                content = self._fetch_with_requests(url)
                if content:
                    return self._format_web_content(content, url, max_length)
            
            return f"Could not read content from {url}"

        except Exception as e:
            return f"Error reading {url}: {str(e)}"

    def _handle_url_with_question(self, url, question=None):
        """
        Fetch a URL and either answer the user's question about it,
        or summarize it if no question was given.
        """
        # Fetch full page content (larger limit for better answers)
        raw = self._fetch_url_for_answer(url)
        if not raw:
            return f"I couldn't read the page at {url}. It may be blocked or unavailable."

        if not question:
            # No question Ã¢Â€Â” just return a clean summary
            now = datetime.now().strftime("%Y-%m-%d")
            msgs = [
                {
                    "role": "system",
                    "content": (
                        "You are Opuntia, a smart assistant. The user shared a web page. "
                        "Summarize its main content clearly and concisely. "
                        f"Today is {now}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Page URL: {url}\n\n"
                        f"Page content:\n{raw}\n\n"
                        "Please summarize this page."
                    ),
                },
            ]
        else:
            now = datetime.now().strftime("%Y-%m-%d")
            msgs = [
                {
                    "role": "system",
                    "content": (
                        f"You are Opuntia, a smart assistant. Today is {now}.\n\n"
                        "The user shared a web page and has a question about it. Answer using only the page content.\n\n"
                        "## Answer format\n"
                        "- **Direct answer first** Ã¢Â€Â” key fact or result, no preamble.\n"
                        "- Scale depth: simple question ? 1-3 sentences; complex ? ## sections + bullet points.\n"
                        "- **Bold** key names, numbers, facts. Bullet points for 3+ items. Table for comparisons.\n"
                        "- If the answer is not on the page, say so clearly.\n"
                        "- No filler: no 'Great question!', 'Certainly!', 'Based on the information provided'."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Page URL: {url}\n\n"
                        f"Page content:\n{raw}\n\n"
                        f"User's question: {question}"
                    ),
                },
            ]
        try:
            answer = self._call_ai(msgs)
            return f"{answer}\n\n*Source: {url}*"
        except Exception as e:
            # Fallback: return the raw content with the URL
            return f"**Page content from {url}:**\n\n{raw[:3000]}"

    def _fetch_url_for_answer(self, url, max_length=6000):
        """Fetch full readable text from a URL for AI question-answering."""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            if "x.com/" in url or "twitter.com/" in url:
                tweet_text = self._fetch_tweet_syndication_text(url)
                if tweet_text:
                    return tweet_text[:max_length] if len(tweet_text) > max_length else tweet_text
                jina_text = self._fetch_url_via_jina(url)
                if jina_text:
                    return jina_text[:max_length] if len(jina_text) > max_length else jina_text
            if sync_playwright is not None:
                content = self._fetch_with_playwright(url)
                if content:
                    text = content.get('content', '')
                    if not self._is_captcha_block(text):
                        return text[:max_length] if len(text) > max_length else text
            if SOUP_AVAILABLE:
                content = self._fetch_with_requests(url)
                if content:
                    text = content.get('content', '')
                    if not self._is_captcha_block(text):
                        return text[:max_length] if len(text) > max_length else text
            if "google.com/search" in url:
                return ""
        except Exception:
            pass
        return ""

    def _is_captcha_block(self, text):
        t = (text or "").lower()
        if not t:
            return False
        return (
            "unusual traffic" in t
            or "solve the captcha" in t
            or "verify you are a human" in t
            or "enable javascript" in t
        )

    def _fetch_tweet_syndication_text(self, url):
        """Fetch tweet text via public syndication endpoint (works without JS)."""
        try:
            m = re.search(r"/status/(\d+)", url)
            if not m:
                return ""
            tweet_id = m.group(1)
            api = f"https://cdn.syndication.twimg.com/tweet?id={tweet_id}"
            resp = requests.get(api, timeout=10)
            if resp.status_code >= 400:
                return ""
            data = resp.json()
            text = (data.get("text") or "").strip()
            user = data.get("user") or {}
            name = user.get("name") or ""
            handle = user.get("screen_name") or ""
            created_at = data.get("created_at") or ""
            parts = []
            header = "Tweet"
            if name or handle:
                header += f" by {name} (@{handle})".strip()
            if created_at:
                header += f" on {created_at}"
            parts.append(header)
            if text:
                parts.append(text)
            media_urls = []
            for p in data.get("photos") or []:
                url = p.get("url") or p.get("expanded_url")
                if url:
                    media_urls.append(url)
            for v in data.get("video") or []:
                url = v.get("url")
                if url:
                    media_urls.append(url)
            if media_urls:
                parts.append("Media: " + ", ".join(media_urls))
            return "\n".join(parts).strip()
        except Exception:
            return ""

    def _fetch_url_via_jina(self, url):
        """Fetch readable text via Jina AI reader (works for JS-heavy sites)."""
        try:
            # Jina reader expects the full URL appended after the base: https://r.jina.ai/<url>
            safe = url if url.startswith("http") else f"https://{url}"
            api = f"https://r.jina.ai/{safe}"
            resp = requests.get(api, timeout=10)
            if resp.status_code >= 400:
                return ""
            text = (resp.text or "").strip()
            return text
        except Exception:
            return ""

    def _find_last_url_in_history(self):
        try:
            for item in reversed(self.conversation_history[-8:]):
                for key in ("assistant", "user"):
                    text = (item.get(key) or "")
                    urls = re.findall(r'https?://[^\s<>"\']+', text)
                    if urls:
                        return urls[0].rstrip('.,;!?)')
        except Exception:
            pass
        return ""

    def _extract_local_paths(self, text):
        paths = []
        if not text:
            return paths
        # Windows drive paths: C:\... or C:/...
        for m in re.findall(r'[A-Za-z]:[\\/][^\\n\\r\\t"\']+', text):
            paths.append(m.strip().strip(".,;!?)"))
        # Unix-like paths (/Users/... or /home/...)
        for m in re.findall(r'/(?:Users|home|mnt)[^\\s"\']+', text):
            paths.append(m.strip().strip(".,;!?)"))
        return paths

    # ── Default browser detection ─────────────────────────────────────────────
    def _pw_detect_default_browser(self):
        """
        Returns (pw_engine, channel, user_data_dir) for the Windows default browser.
        pw_engine: 'chromium' | 'firefox'
        channel:   'chrome' | 'msedge' | 'chromium' | None  (None = use playwright's bundled)
        user_data_dir: path to real browser profile so saved data is available
        """
        channel = None
        pw_engine = "chromium"
        user_data_dir = None

        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
            )
            prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
            winreg.CloseKey(key)

            _home = os.path.expanduser("~")
            if "chrome" in prog_id:
                channel = "chrome"
                pw_engine = "chromium"
                user_data_dir = os.path.join(_home, "AppData", "Local", "Google", "Chrome", "User Data")
            elif "msedge" in prog_id or "edge" in prog_id:
                channel = "msedge"
                pw_engine = "chromium"
                user_data_dir = os.path.join(_home, "AppData", "Local", "Microsoft", "Edge", "User Data")
            elif "brave" in prog_id:
                channel = "chrome"  # Brave uses Chromium channel
                pw_engine = "chromium"
                user_data_dir = os.path.join(_home, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data")
            elif "firefox" in prog_id:
                pw_engine = "firefox"
                channel = None
                # Firefox profiles are in a random folder — find the default one
                ff_profiles = os.path.join(_home, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles")
                if os.path.isdir(ff_profiles):
                    for p in os.listdir(ff_profiles):
                        if p.endswith(".default-release") or p.endswith(".default"):
                            user_data_dir = os.path.join(ff_profiles, p)
                            break
            elif "opera" in prog_id:
                channel = None
                pw_engine = "chromium"
                user_data_dir = os.path.join(_home, "AppData", "Roaming", "Opera Software", "Opera Stable")
        except Exception:
            pass

        return pw_engine, channel, user_data_dir

    # ── Persistent Playwright session (thread-safe, queue-based) ─────────────
    def _pw_ensure_thread(self):
        """Start the Playwright worker thread if not running."""
        import queue, threading
        if self._pw_cmd_queue is None:
            self._pw_cmd_queue = queue.Queue()
            self._pw_res_queue = queue.Queue()
        if self._pw_thread is None or not self._pw_thread.is_alive():
            self._pw_thread = threading.Thread(
                target=self._pw_worker_loop,
                args=(self._pw_cmd_queue, self._pw_res_queue),
                daemon=True,
            )
            self._pw_thread.start()

    def _pw_find_browser_exe(self, channel):
        """Find the browser executable path for the given channel."""
        import winreg
        candidates = []
        if channel == "chrome":
            candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.join(os.path.expanduser("~"), r"AppData\Local\Google\Chrome\Application\chrome.exe"),
            ]
        elif channel == "msedge":
            candidates = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
        elif channel == "brave":
            candidates = [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.join(os.path.expanduser("~"), r"AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _pw_worker_loop(self, cmd_q, res_q):
        """Runs on the Playwright thread. Owns the browser for its lifetime."""
        if sync_playwright is None:
            return
        try:
            with sync_playwright() as pw:
                engine_name = getattr(self, "_pw_browser_type", "chromium")
                engine = {"chromium": pw.chromium, "firefox": pw.firefox, "webkit": pw.webkit}.get(engine_name, pw.chromium)
                browser = engine.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    bypass_csp=True,
                    ignore_https_errors=True,
                )
                # Block heavy non-essential resources for faster page loads
                context.route(
                    "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}",
                    lambda route, _: route.abort()
                    if route.request.resource_type in ("image", "font")
                    else route.continue_(),
                )
                page = context.new_page()
                page.set_default_timeout(4000)
                page.set_default_navigation_timeout(25000)

                self._pw_page = page
                while True:
                    try:
                        cmd, args, kwargs = cmd_q.get(timeout=300)
                    except Exception:
                        break
                    if cmd == "__close__":
                        break
                    try:
                        result = self._pw_exec(page, browser, context, cmd, args, kwargs)
                    except Exception as e:
                        result = f"Browser error: {e}"
                    res_q.put(result)

                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
        except Exception as e:
            res_q.put(f"Playwright failed to start: {e}")
        finally:
            self._pw_page = None
            self._pw_cmd_queue = None
            self._pw_res_queue = None
            self._pw_thread = None

    def _pw_send(self, cmd, *args, _timeout=12, **kwargs):
        """Send a command to the Playwright thread and wait for the result."""
        self._pw_ensure_thread()
        self._pw_cmd_queue.put((cmd, args, kwargs))
        try:
            return self._pw_res_queue.get(timeout=_timeout)
        except Exception:
            return "Browser command timed out."

    def _pw_exec(self, page, browser, context, cmd, args, kwargs):
        """Execute a Playwright command on the worker thread."""
        import json as _json, re as _re, os as _os

        # ── Element finder — scores every element by how well it matches the target string ──
        # Checks text, aria-label, title, placeholder, alt, data-testid, id, class, name, value
        # Prioritises interactive elements. Returns best match or null.
        _JS_FIND_AND_CLICK = """
        ([target, action]) => {
            const t = (target||'').toLowerCase().trim();
            function score(el) {
                if (!el) return -1;
                const r = el.getBoundingClientRect();
                if (r.width===0 && r.height===0) return -1;
                const checks = [
                    el.innerText, el.textContent,
                    el.getAttribute('aria-label'), el.ariaLabel, el.title,
                    el.getAttribute('placeholder'), el.getAttribute('alt'),
                    el.getAttribute('data-testid'), el.getAttribute('name'),
                    el.value, el.getAttribute('data-tooltip'), el.id,
                    el.getAttribute('data-cy'), el.getAttribute('data-label'),
                ];
                for (const v of checks) {
                    if (!v) continue;
                    const vl = String(v).trim().toLowerCase();
                    if (vl === t)           return 3000 - vl.length;
                    if (vl.startsWith(t))   return 2000 - vl.length;
                    if (vl.includes(t))     return 1000 - vl.length;
                }
                return -1;
            }
            const SELECTORS = [
                'button','a','input','select','textarea',
                'input[type="submit"]','input[type="button"]','input[type="search"]','input[type="image"]',
                '[role="button"]','[role="link"]','[role="tab"]','[role="menuitem"]',
                '[role="option"]','[role="searchbox"]','[role="combobox"]','[role="checkbox"]',
                '[role="radio"]','[role="switch"]','[role="textbox"]','[role="slider"]',
                'label','[class*="btn"]','[class*="button"]','[class*="icon"]',
                'nav a','header button','header a','[class*="menu"]',
                'span','li','p','div','h1','h2','h3','h4','img','svg','i','em',
            ];
            let bestEl = null, bestScore = -1;
            const seen = new WeakSet();
            for (const sel of SELECTORS) {
                try {
                    for (const el of document.querySelectorAll(sel)) {
                        if (seen.has(el)) continue; seen.add(el);
                        const s = score(el);
                        if (s > bestScore) { bestScore = s; bestEl = el; }
                    }
                } catch(e) {}
            }
            if (!bestEl || bestScore < 0) return null;
            bestEl.scrollIntoView({block:'nearest', behavior:'instant'});
            bestEl.focus();
            if (action === 'dblclick') {
                bestEl.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true}));
            } else if (action === 'rightclick') {
                bestEl.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,button:2}));
            } else {
                bestEl.dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));
                bestEl.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}));
                bestEl.dispatchEvent(new MouseEvent('mouseup',  {bubbles:true,cancelable:true}));
                bestEl.click();
                bestEl.dispatchEvent(new MouseEvent('click',    {bubbles:true,cancelable:true}));
            }
            return (bestEl.innerText||bestEl.getAttribute('aria-label')||bestEl.title||target||'').trim().slice(0,80);
        }
        """

        _JS_SCROLL = """
        (dy) => {
            function canScroll(el) {
                const s = window.getComputedStyle(el);
                return (s.overflow+s.overflowY).match(/auto|scroll/) && el.scrollHeight > el.clientHeight + 4;
            }
            let el = document.activeElement;
            while (el && el !== document.body && el !== document.documentElement) {
                if (canScroll(el)) { el.scrollBy({top:dy,behavior:'instant'}); return; }
                el = el.parentElement;
            }
            let best=null, bestH=0;
            for (const c of document.querySelectorAll('main,article,[class*="feed"],[class*="scroll"],[class*="content"],[class*="list"],*')) {
                if (c.clientHeight>150 && canScroll(c) && c.clientHeight>bestH) { best=c; bestH=c.clientHeight; }
            }
            if (best) { best.scrollBy({top:dy,behavior:'instant'}); }
            else { window.scrollBy({top:dy,behavior:'instant'}); }
        }
        """

        _JS_FILL_INPUT = """
        ([fieldHint, text]) => {
            const t = (fieldHint||'').toLowerCase().trim();
            const vis = el => { const r=el.getBoundingClientRect(); return r.width>0&&r.height>0; };
            let best=null, bestScore=-1;
            for (const el of document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]),textarea,[contenteditable="true"],[role="textbox"],[role="searchbox"],[role="combobox"]')) {
                if (!vis(el)) continue;
                const checks = [el.getAttribute('placeholder'),el.getAttribute('aria-label'),el.name,el.id,el.getAttribute('data-testid')];
                let s=-1;
                for (const v of checks) {
                    if (!v) continue;
                    const vl=v.toLowerCase();
                    if (vl===t) {s=3000; break;}
                    if (vl.startsWith(t)) {s=Math.max(s,2000); }
                    if (vl.includes(t))   {s=Math.max(s,1000); }
                }
                if (s<0 && t==='') s=500;  // empty hint = first visible input
                if (s>bestScore) {bestScore=s; best=el;}
            }
            if (!best) return false;
            best.scrollIntoView({block:'nearest',behavior:'instant'});
            best.focus();
            best.select && best.select();
            // Native value setter to bypass React/Vue controlled inputs
            const nativeSetter = Object.getOwnPropertyDescriptor(best.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype, 'value');
            if (nativeSetter && nativeSetter.set) nativeSetter.set.call(best, text);
            else best.value = text;
            best.dispatchEvent(new Event('input',{bubbles:true}));
            best.dispatchEvent(new Event('change',{bubbles:true}));
            best.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true}));
            return true;
        }
        """

        _JS_SCAN = """
        () => {
            const vis = el => { const r=el.getBoundingClientRect(); return r.width>0&&r.height>0&&r.top<window.innerHeight+200; };
            const result = {title:document.title, url:location.href, buttons:[], links:[], inputs:[], headings:[], text:''};
            const bSet=new Set();
            for (const b of document.querySelectorAll('button,[role="button"],[role="tab"],[role="menuitem"],[role="option"]')) {
                if (!vis(b)) continue;
                const label=(b.innerText||b.getAttribute('aria-label')||b.title||'').trim().slice(0,60);
                if (label&&!bSet.has(label)) { bSet.add(label); result.buttons.push(label); }
            }
            for (const a of document.querySelectorAll('a[href]')) {
                if (!vis(a)) continue;
                const txt=(a.innerText||a.title||a.getAttribute('aria-label')||'').trim().slice(0,60);
                if (txt) result.links.push(txt);
            }
            for (const i of document.querySelectorAll('input:not([type="hidden"]),select,textarea,[role="textbox"],[role="searchbox"]')) {
                if (!vis(i)) continue;
                result.inputs.push((i.getAttribute('placeholder')||i.getAttribute('aria-label')||i.name||i.type||'field').slice(0,40));
            }
            for (const h of document.querySelectorAll('h1,h2,h3,h4')) {
                if (vis(h)) result.headings.push(h.innerText.trim().slice(0,80));
            }
            result.text = (document.body&&document.body.innerText||'').replace(/\\s+/g,' ').trim().slice(0,3000);
            return result;
        }
        """

        if cmd == "navigate":
            url = args[0]
            if not url.startswith("http"):
                url = "https://" + url
            try:
                page.goto(url, wait_until="commit", timeout=25000)
            except Exception:
                try:
                    page.goto(url, timeout=25000)
                except Exception:
                    pass
            self._inject_opuntia_banner(page, f"Browsing · {url[:80]}")
            return f"Opened **{url}** in browser."

        if cmd == "click":
            _t = args[0].strip()
            try:
                clicked = page.evaluate(_JS_FIND_AND_CLICK, [_t, "click"])
                if clicked:
                    return f"Clicked **{clicked}**."
            except Exception:
                pass
            # Playwright fallback with aria-label, role, text
            import re as _re2
            _pat = _re2.compile(_re2.escape(_t), _re2.IGNORECASE)
            for locator_fn in [
                lambda: page.get_by_label(_pat).first,
                lambda: page.get_by_role("button", name=_pat).first,
                lambda: page.get_by_role("link", name=_pat).first,
                lambda: page.get_by_role("tab", name=_pat).first,
                lambda: page.get_by_placeholder(_pat).first,
                lambda: page.get_by_text(_pat).first,
                lambda: page.locator(f'[aria-label*="{_t}" i]').first,
                lambda: page.locator(f'[title*="{_t}" i]').first,
                lambda: page.locator(f'[data-testid*="{_t}" i]').first,
            ]:
                try:
                    el = locator_fn()
                    el.scroll_into_view_if_needed(timeout=500)
                    el.click(timeout=1500, force=True)
                    return f"Clicked **{_t}**."
                except Exception:
                    pass
            return f"Could not find **{_t}** to click."

        if cmd == "double_click":
            _t = args[0].strip()
            try:
                clicked = page.evaluate(_JS_FIND_AND_CLICK, [_t, "dblclick"])
                if clicked:
                    return f"Double-clicked **{clicked}**."
            except Exception:
                pass
            try:
                page.get_by_text(_t).first.dblclick(timeout=1500)
                return f"Double-clicked **{_t}**."
            except Exception:
                pass
            return f"Could not double-click **{_t}**."

        if cmd == "right_click":
            _t = args[0].strip()
            try:
                clicked = page.evaluate(_JS_FIND_AND_CLICK, [_t, "rightclick"])
                if clicked:
                    return f"Right-clicked **{clicked}**."
            except Exception:
                pass
            try:
                page.get_by_text(_t).first.click(button="right", timeout=1500)
                return f"Right-clicked **{_t}**."
            except Exception:
                pass
            return f"Could not right-click **{_t}**."

        if cmd == "hover":
            _t = args[0].strip()
            try:
                page.evaluate(_JS_FIND_AND_CLICK, [_t, "hover"])
            except Exception:
                pass
            try:
                page.get_by_text(_t).first.hover(timeout=1500)
                return f"Hovered over **{_t}**."
            except Exception:
                pass
            try:
                page.locator(f'[aria-label*="{_t}" i]').first.hover(timeout=1500)
                return f"Hovered over **{_t}**."
            except Exception:
                pass
            return f"Could not hover over **{_t}**."

        if cmd == "drag":
            src, dst = args[0].strip(), args[1].strip()
            try:
                src_loc = page.locator(f'text={src}').first
                dst_loc = page.locator(f'text={dst}').first
                src_loc.drag_to(dst_loc)
                return f"Dragged **{src}** to **{dst}**."
            except Exception as e:
                return f"Drag failed: {e}"

        if cmd == "type":
            field, text = args[0], args[1]
            try:
                filled = page.evaluate(_JS_FILL_INPUT, [field, text])
                if filled:
                    return f"Typed into **{field}**."
            except Exception:
                pass
            import re as _re2
            _pat = _re2.compile(_re2.escape(field), _re2.IGNORECASE)
            for attempt in [
                lambda: page.get_by_placeholder(_pat).first.fill(text, timeout=1500),
                lambda: page.get_by_label(_pat).first.fill(text, timeout=1500),
                lambda: page.locator(field).first.fill(text, timeout=1500),
            ]:
                try:
                    attempt()
                    return f"Typed into **{field}**."
                except Exception:
                    pass
            return f"Could not find field **{field}**."

        if cmd == "keyboard_type":
            page.keyboard.type(args[0], delay=0)
            return f"Typed **{args[0]}**."

        if cmd == "key_combo":
            # e.g. "Control+a", "Control+c", "Alt+F4"
            combo = args[0]
            page.keyboard.press(combo)
            return f"Pressed **{combo}**."

        if cmd == "clear_input":
            _t = args[0].strip() if args else ""
            try:
                filled = page.evaluate(_JS_FILL_INPUT, [_t, ""])
                if filled:
                    return f"Cleared **{_t}**."
            except Exception:
                pass
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            return "Cleared input."

        if cmd == "tab_next":
            page.keyboard.press("Tab")
            return "Moved to next field."

        if cmd == "tab_prev":
            page.keyboard.press("Shift+Tab")
            return "Moved to previous field."

        if cmd == "select":
            field, option = args[0], args[1]
            for attempt in [
                lambda: page.locator(field).first.select_option(label=option, timeout=2000),
                lambda: page.get_by_label(field).first.select_option(label=option, timeout=2000),
            ]:
                try:
                    attempt()
                    return f"Selected **{option}** in **{field}**."
                except Exception:
                    pass
            return f"Could not select option: **{option}**"

        if cmd == "search":
            query = args[0]
            # JS-first: fill most visible search input then press Enter
            try:
                found = page.evaluate(_JS_FILL_INPUT, ["search", query])
                if not found:
                    found = page.evaluate(_JS_FILL_INPUT, ["", query])  # first visible input
                if found:
                    page.keyboard.press("Enter")
                    return f"Searched for **{query}**."
            except Exception:
                pass
            for sel_fn in [
                lambda: page.get_by_role("searchbox").first,
                lambda: page.locator('input[type="search"]').first,
                lambda: page.locator('input[name="q"]').first,
            ]:
                try:
                    el = sel_fn()
                    el.fill(query, timeout=1500)
                    page.keyboard.press("Enter")
                    return f"Searched for **{query}**."
                except Exception:
                    pass
            return "Could not find a search box on this page."

        if cmd == "scan_page":
            try:
                data = page.evaluate(_JS_SCAN)
                parts = [f"**Page:** {data.get('title','')} — {data.get('url','')}"]
                if data.get("headings"):
                    parts.append("**Headings:** " + " · ".join(data["headings"][:8]))
                if data.get("buttons"):
                    parts.append("**Buttons/Tabs:** " + ", ".join(data["buttons"][:20]))
                if data.get("links"):
                    parts.append("**Links:** " + ", ".join(data["links"][:20]))
                if data.get("inputs"):
                    parts.append("**Inputs:** " + ", ".join(data["inputs"][:10]))
                return "\n".join(parts)
            except Exception as e:
                return f"Scan failed: {e}"

        if cmd == "wait_for":
            target = args[0].strip()
            timeout_ms = int(args[1]) if len(args) > 1 else 5000
            try:
                import re as _re2
                page.get_by_text(_re2.compile(_re2.escape(target), _re2.IGNORECASE)).first.wait_for(timeout=timeout_ms)
                return f"Found **{target}** on page."
            except Exception:
                pass
            try:
                page.locator(target).first.wait_for(timeout=timeout_ms)
                return f"Element **{target}** appeared."
            except Exception:
                return f"**{target}** did not appear within {timeout_ms//1000}s."

        if cmd == "wait_for_nav":
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                return "Page loaded."
            except Exception:
                return "Page load timed out."

        if cmd == "refresh":
            page.reload(wait_until="commit", timeout=15000)
            return "Page refreshed."

        if cmd == "copy_text":
            # Copy selected text via keyboard
            page.keyboard.press("Control+c")
            return "Copied selection to clipboard."

        if cmd == "select_all":
            page.keyboard.press("Control+a")
            return "Selected all."

        if cmd == "scroll":
            direction, amount = args[0], args[1]
            dy = amount if direction == "down" else -amount
            page.evaluate(_JS_SCROLL, dy)
            return f"Scrolled {direction}."

        if cmd == "scroll_to":
            where = args[0]
            if where == "top":
                page.evaluate("""
                    () => {
                        window.scrollTo({top:0,behavior:'instant'});
                        for (const el of document.querySelectorAll('*')) {
                            if (el.scrollTop > 0) el.scrollTo({top:0,behavior:'instant'});
                        }
                    }
                """)
            else:
                page.evaluate("""
                    () => {
                        window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
                        for (const el of document.querySelectorAll('*')) {
                            if (el.scrollHeight > el.clientHeight + 4) {
                                el.scrollTo({top:el.scrollHeight,behavior:'instant'});
                            }
                        }
                    }
                """)
            return f"Scrolled to {where}."

        if cmd == "read_page":
            try:
                data = page.evaluate(_JS_SCAN)
                text = (data.get("text") or "").strip()
                import re as _re2
                text = _re2.sub(r'\n{3,}', '\n\n', text)
                return text[:4000]
            except Exception:
                pass
            return self._strip_html_tags(page.content())[:4000]

        if cmd == "screenshot":
            fname = args[0] if args else "opuntia_screenshot.png"
            if not fname.endswith(".png"):
                fname += ".png"
            path = _os.path.join(_os.path.expanduser("~"), "Desktop", fname)
            fullpage = kwargs.get("fullpage", False)
            page.screenshot(path=path, full_page=fullpage)
            label = "Full-page screenshot" if fullpage else "Screenshot"
            return f"{label} saved to Desktop as **{fname}**."

        if cmd == "screenshot_element":
            selector, fname = args[0], args[1] if len(args) > 1 else "opuntia_element.png"
            if not fname.endswith(".png"):
                fname += ".png"
            path = _os.path.join(_os.path.expanduser("~"), "Desktop", fname)
            try:
                page.locator(selector).first.screenshot(path=path)
                return f"Element screenshot saved to Desktop as **{fname}**."
            except Exception as e:
                return f"Could not capture element: {e}"

        if cmd == "record_video_start":
            import tempfile as _tf
            vdir = _tf.mkdtemp(prefix="opuntia_vid_")
            try:
                new_ctx = browser.new_context(record_video_dir=vdir)
                new_page = new_ctx.new_page()
                try:
                    cur_url = page.url
                    if cur_url and cur_url != "about:blank":
                        new_page.goto(cur_url, wait_until="commit", timeout=15000)
                except Exception:
                    pass
                self._pw_page = new_page
                self._pw_video_context = new_ctx
                self._pw_video_page = new_page
                return "Video recording started. Say **stop recording** when done."
            except Exception as e:
                return f"Could not start recording: {e}"

        if cmd == "record_video_stop":
            try:
                vpage = getattr(self, "_pw_video_page", None)
                vctx = getattr(self, "_pw_video_context", None)
                if vpage is None:
                    return "No recording in progress."
                video_path = vpage.video.path() if vpage.video else None
                vpage.close()
                if vctx:
                    vctx.close()
                self._pw_video_page = None
                self._pw_video_context = None
                if video_path:
                    dst = _os.path.join(_os.path.expanduser("~"), "Desktop", "opuntia_recording.webm")
                    import shutil as _sh
                    _sh.move(video_path, dst)
                    return "Recording saved to Desktop as **opuntia_recording.webm**."
                return "Recording stopped."
            except Exception as e:
                return f"Could not stop recording: {e}"

        if cmd == "intercept_start":
            self._pw_intercepted = []
            def _handle(route, request):
                self._pw_intercepted.append({
                    "method": request.method,
                    "url": request.url,
                    "resource": request.resource_type,
                })
                route.continue_()
            context.route("**/*", _handle)
            return "Network interception started. Say **show intercepted requests** when ready."

        if cmd == "intercept_stop":
            try:
                context.unroute("**/*")
            except Exception:
                pass
            captured = getattr(self, "_pw_intercepted", [])
            if not captured:
                return "No requests were captured."
            lines = [f"- `{r['method']}` {r['resource']} — {r['url'][:120]}" for r in captured[:40]]
            self._pw_intercepted = []
            return f"**Captured {len(captured)} requests:**\n" + "\n".join(lines)

        if cmd == "run_js":
            code = args[0]
            try:
                result = page.evaluate(code)
                return f"**JS result:** `{result}`"
            except Exception as e:
                return f"JS error: {e}"

        if cmd == "press_key":
            page.keyboard.press(args[0])
            return f"Pressed **{args[0]}**."

        if cmd == "go_back":
            page.go_back(wait_until="commit", timeout=10000)
            return "Went back."

        if cmd == "go_forward":
            page.go_forward(wait_until="commit", timeout=10000)
            return "Went forward."

        if cmd == "new_tab":
            context.new_page()
            return "Opened new tab."

        if cmd == "get_title":
            return f"Page title: **{page.title()}**"

        if cmd == "get_url":
            return f"Current URL: `{page.url}`"

        if cmd == "full_context":
            # Single round-trip: returns dict with url, title, page text, and scan.
            # Used by the LLM intelligence block to avoid 4 separate queue calls.
            try:
                _data = page.evaluate(_JS_SCAN)
                return {
                    "url":   page.url or "",
                    "title": page.title() or "",
                    "text":  (_data.get("text") or "")[:4000],
                    "scan":  str(_data)[:2000],
                }
            except Exception:
                return {"url": page.url or "", "title": "", "text": "", "scan": ""}

        return f"Unknown command: {cmd}"

    def _pw_close_session(self):
        if self._pw_cmd_queue:
            self._pw_cmd_queue.put(("__close__", [], {}))
        self._pw_page = None

    def _pw_navigate(self, url):
        return self._pw_send("navigate", url, _timeout=30)

    def _pw_automate(self, user_input):
        """Route natural language to Playwright commands. Returns reply or None."""
        if sync_playwright is None:
            return None
        low = user_input.strip().lower()

        # ── Switch browser engine ──────────────────────────────────────────
        switch_m = re.search(r'\b(?:use|switch\s+to|open\s+(?:in|with)|launch)\s+(firefox|webkit|chromium|chrome)\b', low)
        if switch_m:
            engine = switch_m.group(1)
            engine = "chromium" if engine == "chrome" else engine
            if engine != getattr(self, "_pw_browser_type", "chromium"):
                self._pw_browser_type = engine
                self._pw_close_session()
            return self._pw_send("navigate", "about:blank") if self._pw_page is None else f"Already on {engine}."

        # ── Navigate ───────────────────────────────────────────────────────
        nav_m = re.match(
            r'^(?:play|open|browse|go\s+to|navigate\s+to|visit|load)\s+(https?://\S+|www\.\S+|\S+\.\w{2,})',
            low,
        )
        if nav_m:
            url = user_input.strip().split(None, 1)[1].strip()
            self._pw_page_cache_ts = 0.0  # page will change — invalidate cache
            return self._pw_send("navigate", url, _timeout=30)

        # ── Click ──────────────────────────────────────────────────────────
        click_m = re.match(r'^click\s+(?:on\s+)?(?:the\s+)?(.+)$', low)
        if click_m:
            return self._pw_send("click", click_m.group(1).strip(' "\''))

        # ── Double-click ───────────────────────────────────────────────────
        dbl_m = re.match(r'^(?:double[\s-]?click|dbl\s+click)\s+(?:on\s+)?(?:the\s+)?(.+)$', low)
        if dbl_m:
            return self._pw_send("double_click", dbl_m.group(1).strip(' "\''))

        # ── Right-click ────────────────────────────────────────────────────
        rc_m = re.match(r'^(?:right[\s-]?click|context\s+menu)\s+(?:on\s+)?(?:the\s+)?(.+)$', low)
        if rc_m:
            return self._pw_send("right_click", rc_m.group(1).strip(' "\''))

        # ── Hover ──────────────────────────────────────────────────────────
        hover_m = re.match(r'^hover\s+(?:over\s+)?(?:on\s+)?(?:the\s+)?(.+)$', low)
        if hover_m:
            return self._pw_send("hover", hover_m.group(1).strip(' "\''))

        # ── Drag ───────────────────────────────────────────────────────────
        drag_m = re.match(r'^drag\s+(?:the\s+)?["\']?(.+?)["\']?\s+(?:to|onto|into)\s+(?:the\s+)?["\']?(.+?)["\']?$', low)
        if drag_m:
            return self._pw_send("drag", drag_m.group(1).strip(' "\''), drag_m.group(2).strip(' "\''))

        # ── Type into field ────────────────────────────────────────────────
        type_m = re.match(r'^(?:type|write|enter|input|fill)\s+["\']?(.+?)["\']?\s+(?:in(?:to)?|on|inside)\s+(?:the\s+)?(.+)$', low)
        if type_m:
            return self._pw_send("type", type_m.group(2).strip(' "\''), type_m.group(1).strip(' "\''))

        # ── Type bare (type/write/enter without a target field) ───────────
        type_bare = re.match(r'^(?:type|enter|write)\s+["\']?(.+?)["\']?$', low)
        if type_bare:
            return self._pw_send("keyboard_type", type_bare.group(1))

        # ── Keyboard shortcuts ─────────────────────────────────────────────
        # "press ctrl a" / "ctrl+c" / "select all" / "copy" / "paste" / "undo"
        if re.match(r'^(?:select\s+all|ctrl\s*\+?\s*a)\s*$', low):
            return self._pw_send("key_combo", "Control+a")
        if re.match(r'^(?:copy|ctrl\s*\+?\s*c)\s*$', low):
            return self._pw_send("key_combo", "Control+c")
        if re.match(r'^(?:paste|ctrl\s*\+?\s*v)\s*$', low):
            return self._pw_send("key_combo", "Control+v")
        if re.match(r'^(?:undo|ctrl\s*\+?\s*z)\s*$', low):
            return self._pw_send("key_combo", "Control+z")
        if re.match(r'^(?:redo|ctrl\s*\+?\s*y)\s*$', low):
            return self._pw_send("key_combo", "Control+y")
        if re.match(r'^(?:save|ctrl\s*\+?\s*s)\s*$', low):
            return self._pw_send("key_combo", "Control+s")
        if re.match(r'^(?:find|ctrl\s*\+?\s*f)\s*$', low):
            return self._pw_send("key_combo", "Control+f")
        if re.match(r'^(?:refresh|reload|f5)\s*$', low):
            return self._pw_send("refresh")
        # Generic "press ctrl+X" or "press alt+F4" etc
        combo_m = re.match(r'^press\s+((?:ctrl|alt|shift|meta|control)\s*[+\s]\s*\w+|\w+(?:\s*[+]\s*\w+)+)$', low)
        if combo_m:
            combo_raw = combo_m.group(1).strip()
            combo_norm = re.sub(r'\s*\+\s*', '+', combo_raw).replace('ctrl','Control').replace('alt','Alt').replace('shift','Shift').replace('meta','Meta')
            combo_norm = combo_norm.title().replace('Control','Control').replace('Alt','Alt')
            return self._pw_send("key_combo", combo_norm)

        # ── Tab navigation ─────────────────────────────────────────────────
        if re.match(r'^(?:tab|next\s+field|press\s+tab)\s*$', low):
            return self._pw_send("tab_next")
        if re.match(r'^(?:shift\s+tab|previous\s+field|prev\s+field)\s*$', low):
            return self._pw_send("tab_prev")

        # ── Clear / reset input ────────────────────────────────────────────
        clear_m = re.match(r'^(?:clear|reset|empty)\s+(?:the\s+)?(.+)$', low)
        if clear_m:
            return self._pw_send("clear_input", clear_m.group(1).strip(' "\''))

        # ── Page scan — "what's on this page?" / "show me the buttons" ────
        if re.search(r"what(?:'s| is)?\s+(?:on\s+)?(?:this|the)\s+page|scan\s+(?:the\s+)?page|list\s+(?:the\s+)?(?:buttons?|links?|elements?|fields?)|show\s+(?:me\s+)?(?:the\s+)?(?:buttons?|links?|elements?|menu)", low):
            return self._pw_send("scan_page")

        # ── Wait for element ───────────────────────────────────────────────
        wait_m = re.match(r'^wait\s+(?:for\s+)?(?:the\s+)?["\']?(.+?)["\']?(?:\s+(\d+)s?)?\s*$', low)
        if wait_m and not re.search(r'second|minute', low.split('wait')[-1]):
            target_w = wait_m.group(1).strip(' "\'')
            timeout_ms = int(wait_m.group(2)) * 1000 if wait_m.group(2) else 5000
            return self._pw_send("wait_for", target_w, timeout_ms)

        # ── Select dropdown ───────────────────────────────────────────────
        select_m = re.match(r'^select\s+["\']?(.+?)["\']?\s+(?:from|in|on)\s+(?:the\s+)?(.+)$', low)
        if select_m:
            return self._pw_send("select", select_m.group(2).strip(' "\''), select_m.group(1).strip(' "\''))

        # ── Search / focus search box ─────────────────────────────────────
        # "search for X" → fill search box
        search_m = re.match(r'^search\s+(?:for\s+)?["\']?(.+?)["\']?$', low)
        if search_m:
            return self._pw_send("search", search_m.group(1).strip(' "\''))
        # "click search" / "open search" / "focus search" → just activate the search input
        if re.match(r'^(?:click|open|tap|focus|activate|hit)\s+(?:the\s+)?search\b', low):
            return self._pw_send("click", "search")

        # ── Scroll ────────────────────────────────────────────────────────
        if re.search(
            r'scroll\s+(?:down\s+)?to\s+(?:the\s+)?bottom'
            r'|scroll\s+all\s+the\s+way\s+down'
            r'|go\s+to\s+(?:the\s+)?bottom'
            r'|jump\s+to\s+(?:the\s+)?bottom'
            r'|\bend\s+of\s+(?:the\s+)?page\b',
            low
        ):
            return self._pw_send("scroll_to", "bottom")
        if re.search(
            r'scroll\s+(?:up\s+)?to\s+(?:the\s+)?top'
            r'|scroll\s+all\s+the\s+way\s+up'
            r'|back\s+to\s+top'
            r'|go\s+to\s+(?:the\s+)?top'
            r'|jump\s+to\s+(?:the\s+)?top'
            r'|\btop\s+of\s+(?:the\s+)?page\b',
            low
        ):
            return self._pw_send("scroll_to", "top")

        def _scroll_amt(low):
            num_m = re.search(r'(\d+)', low)
            if num_m: return int(num_m.group(1))
            if re.search(r'\b(more|further|lot|much|again|fast|big|large)\b', low): return 1200
            return 600

        if re.search(r'\bscroll\s+down\b|\bdown\s+(?:the\s+)?page\b|page\s+down\b', low):
            return self._pw_send("scroll", "down", _scroll_amt(low))
        if re.search(r'\bscroll\s+up\b|\bup\s+(?:the\s+)?page\b|page\s+up\b', low):
            return self._pw_send("scroll", "up", _scroll_amt(low))
        # Bare "down" / "up" when browser is active
        if re.match(r'^down\s*$', low):
            return self._pw_send("scroll", "down", 600)
        if re.match(r'^up\s*$', low):
            return self._pw_send("scroll", "up", 600)

        # ── Screenshots ───────────────────────────────────────────────────
        # Full-page screenshot
        if re.search(r'full[\s-]?page\s+screenshot|screenshot\s+(?:of\s+)?(?:full|entire|whole)\s+page', low):
            name_m = re.search(r'(?:save|name|as)\s+["\']?(\w[\w\s\-\.]+)["\']?', low)
            fname = name_m.group(1).strip().replace(" ", "_") if name_m else "opuntia_fullpage.png"
            return self._pw_send("screenshot", fname, fullpage=True)
        # Element screenshot
        elem_shot_m = re.match(r'(?:screenshot|capture|snap)\s+(?:of\s+)?(?:the\s+)?element\s+["\']?(.+?)["\']?(?:\s+(?:as|save\s+as)\s+["\']?(\S+)["\']?)?$', low)
        if elem_shot_m:
            sel = elem_shot_m.group(1).strip(' "\'')
            fname = elem_shot_m.group(2) or "opuntia_element.png"
            return self._pw_send("screenshot_element", sel, fname)
        # Regular screenshot
        if re.search(r'\bscreenshot\b|\bcapture\s+(?:the\s+)?(?:page|screen|browser)\b', low):
            name_m = re.search(r'(?:save|name|as)\s+["\']?(\w[\w\s\-\.]+)["\']?', low)
            fname = name_m.group(1).strip().replace(" ", "_") if name_m else "opuntia_screenshot.png"
            return self._pw_send("screenshot", fname)

        # ── Video recording ───────────────────────────────────────────────
        if re.search(r'(?:start|begin)\s+(?:video\s+)?recording|record\s+(?:video|screen|this)', low):
            return self._pw_send("record_video_start")
        if re.search(r'stop\s+recording|save\s+(?:the\s+)?(?:video|recording)', low):
            return self._pw_send("record_video_stop")

        # ── Network interception ──────────────────────────────────────────
        if re.search(r'intercept\s+(?:network\s+)?requests?|monitor\s+(?:network|requests?)|watch\s+(?:network|requests?)', low):
            return self._pw_send("intercept_start")
        if re.search(r'show\s+(?:intercepted|captured|network)\s+requests?|stop\s+intercept', low):
            return self._pw_send("intercept_stop")

        # ── JavaScript execution ──────────────────────────────────────────
        js_m = re.match(r'^(?:run|execute|eval(?:uate)?)\s+(?:js|javascript|script)\s*[:\-]?\s*(.+)$', low, re.DOTALL)
        if js_m:
            code_raw = user_input.strip()
            # Extract actual code from original casing
            code_start = re.search(r'(?:run|execute|eval(?:uate)?)\s+(?:js|javascript|script)\s*[:\-]?\s*', code_raw, re.IGNORECASE)
            code = code_raw[code_start.end():].strip().strip('`') if code_start else js_m.group(1)
            return self._pw_send("run_js", code)

        # ── Read page ─────────────────────────────────────────────────────
        if re.match(r'^(?:read|extract|get|show)\s+(?:the\s+)?(?:page|content|text)', low):
            text = self._pw_send("read_page")
            return f"**Page content:**\n{text}"

        # ── Page info ─────────────────────────────────────────────────────
        if re.search(r"(?:what'?s?\s+(?:the\s+)?(?:page\s+)?title|get\s+(?:the\s+)?title)", low):
            return self._pw_send("get_title")
        if re.search(r"(?:what'?s?\s+(?:the\s+)?(?:current\s+)?url|get\s+(?:the\s+)?url|current\s+url)", low):
            return self._pw_send("get_url")

        # ── Press key ─────────────────────────────────────────────────────
        key_m = re.match(r'^press\s+(?:the\s+)?(\w+)(?:\s+key)?$', low)
        if key_m:
            return self._pw_send("press_key", key_m.group(1).capitalize())

        # ── Refresh ────────────────────────────────────────────────────────
        if re.match(r'^(?:refresh|reload)\s*(?:the\s+)?(?:page)?\s*$', low):
            return self._pw_send("refresh")

        # ── Wait for page / element ────────────────────────────────────────
        if re.match(r'^wait\s+(?:for\s+)?(?:the\s+)?(?:page\s+to\s+)?(?:load|finish)\s*$', low):
            return self._pw_send("wait_for_nav")

        # ── Navigation ────────────────────────────────────────────────────
        if re.match(r'^go\s+back', low):
            self._pw_page_cache_ts = 0.0
            return self._pw_send("go_back")
        if re.match(r'^go\s+forward', low):
            self._pw_page_cache_ts = 0.0
            return self._pw_send("go_forward")

        # ── New tab ───────────────────────────────────────────────────────
        if re.search(r'new\s+tab|open\s+(?:a\s+)?(?:new\s+)?tab', low):
            return self._pw_send("new_tab")

        # ── Close browser ─────────────────────────────────────────────────
        if re.match(r'^(?:close|quit|stop)\s+(?:the\s+)?(?:browser|playwright|chromium|firefox|webkit)', low):
            self._pw_close_session()
            return "Browser closed."

        return None

    def _inject_opuntia_banner(self, page, action_label="Browsing"):
        """Inject a floating Opuntia HUD banner into the Playwright page."""
        import json as _json
        label_js = _json.dumps(str(action_label))
        try:
            page.evaluate(f"""
                (() => {{
                    if (document.getElementById('__opuntia_hud__')) return;
                    const actionLabel = {label_js};
                    const hud = document.createElement('div');
                    hud.id = '__opuntia_hud__';
                    hud.style.cssText = [
                        'position:fixed',
                        'top:0','left:0','right:0',
                        'z-index:2147483647',
                        'background:linear-gradient(90deg,#0d0d0d 0%,#1a1a2e 100%)',
                        'color:#ffffff',
                        'font-family:system-ui,sans-serif',
                        'font-size:13px',
                        'font-weight:500',
                        'padding:6px 16px',
                        'display:flex',
                        'align-items:center',
                        'gap:10px',
                        'border-bottom:1px solid rgba(120,180,255,0.25)',
                        'box-shadow:0 2px 12px rgba(0,0,0,0.5)',
                        'letter-spacing:0.01em',
                    ].join(';');
                    const shortUrl = window.location.hostname || window.location.href.slice(0,60);
                    hud.innerHTML =
                        '<span style="background:linear-gradient(135deg,#4f8ef7,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:700;font-size:14px;letter-spacing:0.04em;">⬡ OPUNTIA</span>' +
                        '<span style="color:rgba(255,255,255,0.35);">|</span>' +
                        '<span style="color:rgba(200,220,255,0.85);">' + actionLabel + '</span>' +
                        '<span style="margin-left:auto;color:rgba(255,255,255,0.3);font-size:11px;">' + shortUrl + '</span>';
                    document.body.prepend(hud);
                    document.body.style.marginTop = (parseInt(document.body.style.marginTop||0) + 36) + 'px';
                }})();
            """)
        except Exception:
            pass

    def _fetch_with_playwright(self, url):
        """Fetch page content using Playwright (handles JavaScript)."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.browser_headless)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle', timeout=15000)
                self._inject_opuntia_banner(page, f"Reading · {url[:80]}")

                # Get page content
                html = page.content()
                title = page.title()

                browser.close()
                
                if SOUP_AVAILABLE:
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                        script.decompose()
                    
                    # Get text
                    text = soup.get_text(separator=' ', strip=True)
                    
                    # Clean up whitespace
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    text = ' '.join(lines)
                    
                    return {'title': title, 'content': text, 'html': html}
        except Exception as e:
            print(f"[WebFetch] Playwright error: {e}")
        return None

    def _fetch_with_requests(self, url):
        """Fetch page content using requests + BeautifulSoup."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            body = response.text or ""
            if "unusual traffic" in body.lower() or "solve the captcha" in body.lower():
                self.google_blocked_until_ts = time.time() + 60 * 20
                return None
            
            if SOUP_AVAILABLE:
                soup = BeautifulSoup(body, 'html.parser')
                
                # Get title
                title = soup.title.string if soup.title else url
                
                # Remove script and style elements
                for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                    script.decompose()
                
                # Get text
                text = soup.get_text(separator=' ', strip=True)
                
                # Clean up whitespace
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = ' '.join(lines)
                
                return {'title': title, 'content': text, 'html': response.text}
        except Exception as e:
            print(f"[WebFetch] Requests error: {e}")
        return None

    def _format_web_content(self, content, url, max_length=3000):
        """Format web content for display with citation."""
        if not content:
            return "No content retrieved."
        
        title = content.get('title', 'Unknown')
        text = content.get('content', '')
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length] + "..."
        
        # Format with citation
        result = f"**{title}**\n\n"
        result += f"{text}\n\n"
        result += f"*Source: [{url}]({url})*"
        
        return result

    def browse_and_research(self, query, max_sites=5):
        """
        Research a topic by searching and browsing multiple sources.
        Returns comprehensive answer with citations.
        """
        # Step 1: Search for relevant sites
        search_results = self._web_search(query, num_results=max_sites)
        
        if not search_results:
            return f"I couldn't find information about: {query}"
        
        # Step 2: Browse top results and extract content
        contents = []
        for i, result in enumerate(search_results[:max_sites], 1):
            url = result.get('link', result.get('url', ''))
            if url:
                content = self.open_and_read_url(url)
                if content and "Error" not in content:
                    contents.append({
                        'title': result.get('title', 'Unknown'),
                        'url': url,
                        'content': content
                    })
        
        if not contents:
            return f"I found links but couldn't extract content. Try: {search_results[0].get('link', '')}"

        # Step 3: Synthesize answer using AI with full content
        context_parts = []
        for i, src in enumerate(contents, 1):
            # Use up to 1500 chars per source for AI context
            text = src['content'][:1500]
            context_parts.append(
                f"[{i}] {src['title']}\nURL: {src['url']}\n{text}"
            )
        context = "\n\n---\n\n".join(context_parts)

        msgs = [
            {
                "role": "system",
                "content": (
                    "You are Opuntia, an intelligent research assistant.\n\n"
                    "## Answer structure (always follow this)\n"
                    "1. **Direct answer first** Ã¢Â€Â” open with the key fact, date, or result. No preamble.\n"
                    "2. **Scale depth to the question:**\n"
                    "   - Simple fact ? 1-3 sentences with inline citations [1][2].\n"
                    "   - Technical/complex ? ## Overview + sections (explanation, examples, comparison table if useful, implications).\n"
                    "3. **Bold** key facts, names, numbers. Bullet points for 3+ items. Tables when comparing options.\n"
                    "4. Logical flow: definition ? explanation ? examples/applications ? implications.\n"
                    "5. Cite sources inline as [1][2]. If sources conflict, note it clearly.\n"
                    "6. No filler: never start with 'Great question!', 'Certainly!', 'Based on the provided information'."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Research query: {query}\n\n"
                    f"Sources:\n{context}\n\n"
                    "Answer directly Ã¢Â€Â” structured, with headings if the topic has multiple parts, bullet points for lists, and a comparison table if comparing options. Start with the direct answer."
                ),
            },
        ]
        try:
            answer = self._strip_ai_sources(self._call_ai(msgs))
            # Append top 3 sources only
            top3 = contents[:3]
            if top3:
                answer += "\n\n**Sources:** " + " Ã‚Â· ".join(
                    f"[{i}] {src.get('url', '')}" for i, src in enumerate(top3, 1)
                )
            return answer
        except Exception:
            # Fallback to plain listing
            lines = [f"**Research: {query}**\n"]
            for i, src in enumerate(contents, 1):
                lines.append(f"**[{i}] {src['title']}** Ã¢Â€Â” {src['url']}")
                lines.append(src['content'][:500])
                lines.append("")
            return "\n".join(lines)

    def _web_search(self, query, num_results=5):
        """Perform web search and return results."""
        try:
            # Use existing search infrastructure
            results = []
            
            # Try DuckDuckGo HTML search
            try:
                from urllib.parse import quote_plus
                search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(search_url, headers=headers, timeout=10)
                
                if SOUP_AVAILABLE:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    # DuckDuckGo HTML: each result is an <a class="result__a"> for title/link
                    # and a separate <a class="result__url"> for the display URL
                    result_anchors = soup.find_all('a', class_='result__a')[:num_results]
                    for anchor in result_anchors:
                        href = anchor.get('href', '')
                        # DDG wraps redirect URLs Ã¢Â€Â” extract the real URL
                        if href.startswith('//duckduckgo.com/l/?') or 'uddg=' in href:
                            from urllib.parse import parse_qs, urlparse
                            try:
                                parsed = urlparse('https:' + href if href.startswith('//') else href)
                                qs = parse_qs(parsed.query)
                                href = qs.get('uddg', [href])[0]
                            except Exception:
                                pass
                        title = anchor.get_text(strip=True)
                        if href and title:
                            results.append({'title': title, 'link': href})
            except Exception as e:
                print(f"[WebSearch] DuckDuckGo error: {e}")
            
            # Fallback to Google search links
            if not results:
                for i in range(num_results):
                    results.append({
                        'title': f'Result {i+1} for {query}',
                        'link': f'https://www.google.com/search?q={quote_plus(query)}'
                    })
            
            return results
        except Exception as e:
            print(f"[WebSearch] Error: {e}")
            return []

    def _normalize_intent_text(self, text):
        """Normalize common multilingual task verbs/prepositions into English intent words."""
        raw = (text or "").strip().lower()
        if not raw:
            return ""

        replacements = [
            # Open / launch verbs.
            (r"\b(ouvre|ouvrir|abre|abrir|avvia|lancer|lance)\b", "open"),
            # Close verbs.
            (r"\b(ferme|fermer|cerrar|cierra|chiudi)\b", "close"),
            # Search verbs.
            (r"\b(recherche|rechercher|cherche|buscar|busca|cerca|look\s*for|look\s*up)\b", "search"),
            # Navigation verbs.
            (r"\b(visite|visitar|visitare|aller\s+a|ir\s+a|ve\s+a|vai\s+a)\b", "go to"),
            # Browser prepositions.
            (r"\b(sur|en|con|avec)\b", "on"),
            # Common polite prefixes.
            (r"^\s*(stp|svp|por favor|please)\s+", ""),
        ]
        out = raw
        for pattern, replacement in replacements:
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        out = re.sub(r"\s+", " ", out).strip()
        return out

    def _extract_search_intent(self, raw_input):
        """Extract 'search X on browser/app' intents in normalized form."""
        text = self._normalize_intent_text(raw_input)
        if not text:
            return None, None

        # "open brave and search instagram"
        m = re.search(r"\bopen\s+(.+?)\s+(?:and\s+)?search(?:\s+for)?\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            browser = (m.group(1) or "").strip(" ,.?")
            query = (m.group(2) or "").strip(" ,.?")
            if query:
                return query, browser

        # "search instagram on brave"
        m = re.search(r"\bsearch(?:\s+for)?\s+(.+?)\s+(?:on|in|using|with)\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            query = (m.group(1) or "").strip(" ,.?")
            browser = (m.group(2) or "").strip(" ,.?")
            if query:
                return query, browser

        # "search instagram"
        m = re.search(r"\bsearch(?:\s+for)?\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            query = (m.group(1) or "").strip(" ,.?")
            if query:
                return query, None

        return None, None

    def _search_query_url(self, query):
        q = (query or "").strip()
        if not q:
            return ""
        return f"https://www.google.com/search?q={quote_plus(q)}"

    def _strip_html_tags(self, text):
        raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text or "")
        raw = re.sub(r"(?is)<[^>]+>", " ", raw)
        raw = html.unescape(raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw

    def _search_google_results(self, query, limit=5):
        """Search Google with improved HTML parsing."""
        q = (query or "").strip()
        if not q:
            return []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
        try:
            url = f"https://www.google.com/search?q={quote_plus(q)}&hl=en&num={int(limit) * 2}"
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec + 5)
            if r.status_code >= 400:
                return []
            body = r.text or ""
            if "unusual traffic" in body.lower() or "solve the captcha" in body.lower():
                self.google_blocked_until_ts = time.time() + 60 * 20
                return []
            out = []
            seen = set()
            
            # Multiple patterns for Google results
            patterns = [
                r'(?is)href="(https?://[^"]*?\.google\.com/url\?q=([^"&]+)[^"]*)"[^>]*>(.*?)</a>',
                r'(?is)href="(/url\?q=([^"&]+)[^"]*)"[^>]*>(.*?)</a>',
                r'(?is)<a[^>]*href="(https?://(?!google\.com)[^"]+)"[^>]*>([^<]{3,100})</a>',
            ]
            
            for pattern in patterns:
                hits = re.findall(pattern, body)
                for hit in hits:
                    if len(hit) >= 2:
                        if 'google.com/url?q=' in hit[0]:
                            raw_link = html.unescape(hit[1])
                            title_html = hit[2] if len(hit) > 2 else ''
                        else:
                            raw_link = html.unescape(hit[0])
                            title_html = hit[2] if len(hit) > 2 else hit[1]
                        
                        link = raw_link.split('&')[0] if '&' in raw_link else raw_link
                        if not link.startswith("http"):
                            continue
                        if "google." in link and "/search" in link:
                            continue
                        if link in seen:
                            continue
                        seen.add(link)
                        title = self._strip_html_tags(title_html)[:180] or link
                        out.append({"title": title, "url": link})
                        if len(out) >= max(1, int(limit)):
                            break
                if out:
                    break
            
            return out
        except Exception as e:
            print(f"Google search error: {e}")
            return []

    def _search_duckduckgo_lite(self, query, limit=5):
        """Search DuckDuckGo using lite version (more reliable)."""
        q = (query or "").strip()
        if not q:
            return []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(q)}"
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec + 5)
            if r.status_code < 400:
                body = r.text or ""
                out = []
                seen = set()

                # DuckDuckGo Lite result links
                links = re.findall(r'(?is)href="(https?://[^"]+)"', body)
                for link in links:
                    link = html.unescape(link)
                    if not link.startswith('http') or 'duckduckgo' in link:
                        continue
                    if link in seen:
                        continue
                    seen.add(link)
                    out.append({"title": link[:80], "url": link})
                    if len(out) >= limit:
                        break
                
                # Also try result table parsing
                rows = re.findall(r'(?is)<tr><td[^>]*>(\d+)\.</td><td><a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', body)
                for num, link, title in rows:
                    link = html.unescape(link)
                    if link not in seen and 'duckduckgo' not in link:
                        seen.add(link)
                        out.append({"title": self._strip_html_tags(title)[:180], "url": link})
                        if len(out) >= limit:
                            break
                
                return out
        except Exception as e:
            print(f"DuckDuckGo error: {e}")
        return []

    def _search_bing_simple(self, query, limit=5):
        """Search Bing with simple parsing."""
        q = (query or "").strip()
        if not q:
            return []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            url = f"https://www.bing.com/search?q={quote_plus(q)}&count={int(limit) * 2}"
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec + 5)
            if r.status_code < 400:
                body = r.text or ""
                out = []
                seen = set()

                # Bing result links
                links = re.findall(r'(?is)<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', body)
                for link, title in links:
                    link = html.unescape(link)
                    if not link.startswith('http') or 'bing.com' in link:
                        continue
                    if link in seen:
                        continue
                    seen.add(link)
                    out.append({"title": self._strip_html_tags(title)[:180], "url": link})
                    if len(out) >= limit:
                        break
                
                return out
        except Exception as e:
            print(f"Bing error: {e}")
        return []

    def _search_serpapi_results(self, query, limit=5):
        if not self.serpapi_key:
            return []
        q = (query or "").strip()
        if not q:
            return []
        try:
            url = (
                "https://serpapi.com/search.json"
                f"?engine=google&q={quote_plus(q)}&api_key={quote_plus(self.serpapi_key)}&num={max(1, int(limit))}"
            )
            r = requests.get(url, timeout=self.web_search_timeout_sec)
            if r.status_code >= 400:
                return []
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            organic = data.get("organic_results") or []
            out = []
            seen = set()
            for it in organic:
                link = (it.get("link") or "").strip()
                title = (it.get("title") or "").strip()
                if not link or not link.startswith("http") or link in seen:
                    continue
                seen.add(link)
                out.append({"title": title[:180] or link, "url": link})
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception:
            return []

    def _search_google_cse_results(self, query, limit=5):
        if not self.google_cse_key or not self.google_cse_cx:
            return []
        q = (query or "").strip()
        if not q:
            return []
        try:
            url = (
                "https://www.googleapis.com/customsearch/v1"
                f"?key={quote_plus(self.google_cse_key)}&cx={quote_plus(self.google_cse_cx)}"
                f"&q={quote_plus(q)}&num={max(1, min(10, int(limit)))}"
            )
            r = requests.get(url, timeout=self.web_search_timeout_sec)
            if r.status_code >= 400:
                return []
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            items = data.get("items") or []
            out = []
            seen = set()
            for it in items:
                link = (it.get("link") or "").strip()
                title = (it.get("title") or "").strip()
                if not link or not link.startswith("http") or link in seen:
                    continue
                seen.add(link)
                out.append({"title": title[:180] or link, "url": link})
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception:
            return []

    def _search_brave_api_results(self, query, limit=5):
        """Brave Search API Ã¢Â€Â” free tier: 2000 req/month. Set BRAVE_SEARCH_API_KEY in .env"""
        if not self.brave_search_api_key:
            return []
        q = (query or "").strip()
        if not q:
            return []
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": self.brave_search_api_key,
                },
                params={"q": q, "count": max(1, min(20, int(limit))), "search_lang": "en"},
                timeout=self.web_search_timeout_sec,
            )
            if r.status_code >= 400:
                return []
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            results = (data.get("web") or {}).get("results") or []
            out = []
            seen = set()
            for item in results:
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("description") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append({"title": title[:200] or url, "url": url, "snippet": snippet[:400]})
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception:
            return []

    def _search_tavily_results(self, query, limit=5):
        """Tavily Search API Ã¢Â€Â” designed for AI agents. Free tier: 1000 req/month. Set TAVILY_API_KEY in .env"""
        if not self.tavily_api_key:
            return []
        q = (query or "").strip()
        if not q:
            return []
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_api_key,
                    "query": q,
                    "max_results": max(1, min(10, int(limit))),
                    "search_depth": "basic",
                    "include_answer": False,
                },
                timeout=self.web_search_timeout_sec,
            )
            if r.status_code >= 400:
                return []
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            results = data.get("results") or []
            out = []
            seen = set()
            for item in results:
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append({"title": title[:200] or url, "url": url, "snippet": snippet[:400]})
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception:
            return []

    def _search_bing_rss_results(self, query, limit=5):
        q = (query or "").strip()
        if not q:
            return []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
            )
        }
        try:
            rss_url = f"https://www.bing.com/search?q={quote_plus(q)}&format=rss"
            r = requests.get(rss_url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code >= 400:
                return []
            body = r.text or ""
            items = re.findall(r"(?is)<item>(.*?)</item>", body)
            out = []
            seen = set()
            for item in items:
                title_m = re.search(r"(?is)<title>(.*?)</title>", item)
                link_m = re.search(r"(?is)<link>(.*?)</link>", item)
                if not link_m:
                    continue
                link = html.unescape((link_m.group(1) or "").strip())
                if not link.startswith("http") or link in seen:
                    continue
                seen.add(link)
                title = self._strip_html_tags(title_m.group(1) if title_m else "")[:180] or link
                out.append({"title": title, "url": link})
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception:
            return []

    def _normalize_web_query(self, query):
        q = (query or "").strip()
        low = q.lower()
        current_year = datetime.now().year

        # Disambiguate common AI product names.
        if re.search(r"\bgemini\b", low) and "google" not in low:
            q += " Google AI"
        if re.search(r"\bclaude\b", low) and "anthropic" not in low:
            q += " Anthropic"
        if re.search(r"\bgpt\b", low) and "openai" not in low:
            q += " OpenAI"

        # For update/news intents, bias toward official announcements/changelog.
        if re.search(r"\b(update|updates|latest|news|release|changelog)\b", low):
            q += " official announcement changelog"

        # Sports: add current year/season so search engine returns the latest results.
        if re.search(r"\b(ucl|champions league|europa league|premier league|la liga|serie a|bundesliga|world cup|euro|nba|nfl|nhl|mlb|copa|superbowl|super bowl)\b", low):
            if not re.search(r"\b(202[0-9]|203[0-9])\b", low):
                q += f" {current_year}"

        # "Who won / who is champion" Ã¢Â€Â” tell the engine we want the winner/result.
        if re.search(r"\b(who\s+won|who\s+is\s+the\s+champion|last\s+winner|current\s+champion)\b", low):
            q += " winner result"

        # Person queries Ã¢Â€Â” add full name context cues.
        if re.search(r"\b(ceo|president|prime minister|manager|coach|director)\b", low):
            q += " current"

        return q

    def _keyword_set(self, text):
        toks = re.findall(r"[a-z0-9]+", (text or "").lower())
        stop = {
            "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "at",
            "is", "are", "was", "were", "be", "been", "from", "with", "about",
            "latest", "recent", "today", "now", "news", "update", "updates",
        }
        return {t for t in toks if len(t) > 2 and t not in stop}

    def _rank_filter_web_results(self, query, results):
        qk = self._keyword_set(query)
        if not qk:
            return results
        scored = []
        for r in (results or []):
            title = (r.get("title") or "").lower()
            url = (r.get("url") or "").lower()
            text = title + " " + url
            overlap = sum(1 for k in qk if k in text)
            # Boost trusted/official sources.
            domain_boost = 0
            if any(d in url for d in ["openai.com", "anthropic.com", "blog.google", "ai.google.dev", "developers.google.com"]):
                domain_boost = 2
            score = overlap + domain_boost
            if score > 0:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        filtered = [r for _, r in scored]
        if filtered:
            return filtered
        # If query has enough signal and nothing matches, treat as no relevant results.
        return [] if len(qk) >= 2 else results

    def _search_web_results(self, query, limit=5):
        """Provider-routed live web search with fallbacks."""
        q = self._normalize_web_query(query)
        if not q:
            return []
        now = time.time()
        if self._last_web_search_ts and (now - self._last_web_search_ts) < self.web_search_min_pause_sec:
            time.sleep(max(0.0, self.web_search_min_pause_sec - (now - self._last_web_search_ts)))
        self._last_web_search_ts = time.time()
        cache_key = f"{q.lower()}|{int(limit)}"
        cached = self._web_search_cache.get(cache_key)
        if cached and (time.time() - float(cached.get("ts", 0)) <= max(5, int(self.web_search_cache_ttl_sec))):
            self.last_live_web_error = ""
            return list(cached.get("results") or [])
        self.last_live_web_error = ""
        
        # Provider map with all available search methods
        provider_map = {
            "brave": lambda: self._search_brave_api_results(q, limit=limit * 2),
            "tavily": lambda: self._search_tavily_results(q, limit=limit * 2),
            "serpapi": lambda: self._search_serpapi_results(q, limit=limit * 2),
            "google_cse": lambda: self._search_google_cse_results(q, limit=limit * 2),
            "google_html": lambda: self._search_google_results(q, limit=limit * 2),
            "ddg": lambda: self._search_ddg_results(q, limit=limit * 2),
            "ddg_lite": lambda: self._search_duckduckgo_lite(q, limit=limit * 2),
            "bing_rss": lambda: self._search_bing_rss_results(q, limit=limit * 2),
            "bing": lambda: self._search_bing_simple(q, limit=limit * 2),
        }

        # Build provider priority: API-key providers first (reliable), then scrapers as fallback
        api_providers = []
        if self.brave_search_api_key:
            api_providers.append("brave")
        if self.tavily_api_key:
            api_providers.append("tavily")
        if self.serpapi_key:
            api_providers.append("serpapi")
        if self.google_cse_key and self.google_cse_cx:
            api_providers.append("google_cse")

        scraper_providers = self.web_search_providers or ["ddg_lite", "bing", "ddg", "bing_rss"]
        if time.time() < self.google_blocked_until_ts:
            scraper_providers = [p for p in scraper_providers if p not in {"google_html", "google_cse"}]
        # Deduplicate: API providers first, then scrapers
        providers_to_try = api_providers + [p for p in scraper_providers if p not in api_providers]
        
        tried = []
        all_results = []
        
        for provider in providers_to_try:
            fn = provider_map.get(provider)
            if fn is None:
                continue
            tried.append(provider)
            try:
                out = fn()
                if out:
                    ranked = self._rank_filter_web_results(q, out)
                    if ranked:
                        all_results.extend(ranked)
                        # If we have enough results, stop
                        if len(all_results) >= limit:
                            self.last_live_web_error = ""
                            final = all_results[:max(1, int(limit))]
                            self._web_search_cache[cache_key] = {"ts": time.time(), "results": final}
                            if len(self._web_search_cache) > 120:
                                oldest = sorted(self._web_search_cache.items(), key=lambda kv: kv[1].get("ts", 0))[:30]
                                for k, _ in oldest:
                                    self._web_search_cache.pop(k, None)
                            return final
            except Exception as e:
                print(f"Provider {provider} error: {e}")
                continue
        
        # Return whatever we got if anything
        if all_results:
            self.last_live_web_error = ""
            final = all_results[:max(1, int(limit))]
            self._web_search_cache[cache_key] = {"ts": time.time(), "results": final}
            return final
        
        self.last_live_web_error = f"No relevant results from providers: {', '.join(tried) if tried else 'none'}"
        return []

    def _search_ddg_results(self, query, limit=5):
        q = (query or "").strip()
        if not q:
            return []
        url = f"https://duckduckgo.com/html/?q={quote_plus(q)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
            )
        }
        try:
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code >= 400:
                return []
            body = r.text or ""
            hits = re.findall(r'(?is)<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body)
            out = []
            seen = set()
            for href, title_html in hits:
                href = html.unescape(href or "").strip()
                if not href:
                    continue
                m = re.search(r"[?&]uddg=([^&]+)", href)
                if m:
                    href = unquote(m.group(1))
                if not href.startswith("http") or href in seen:
                    continue
                seen.add(href)
                title = self._strip_html_tags(title_html)[:180] or href
                out.append({"title": title, "url": href})
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception:
            return []

    def _is_fetch_allowed(self, url, user_agent="Mozilla/5.0"):
        if not self.web_respect_robots:
            return True
        try:
            parsed = urlsplit(url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
            origin = f"{parsed.scheme}://{parsed.netloc}"
            now = time.time()
            cached = self._robots_cache.get(origin)
            parser = None
            if cached and (now - cached.get("ts", 0) <= max(60, int(self.robots_cache_ttl_sec))):
                parser = cached.get("parser")
            if parser is None:
                robots_url = f"{origin}/robots.txt"
                parser = robotparser.RobotFileParser()
                parser.set_url(robots_url)
                parser.read()
                self._robots_cache[origin] = {"ts": now, "parser": parser}
            return bool(parser.can_fetch(user_agent, url))
        except Exception:
            # Fail-open to avoid hard blocking when robots endpoint is unreachable.
            return True

    def _fetch_url_excerpt(self, url):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
            )
        }
        if not self._is_fetch_allowed(url, headers["User-Agent"]):
            return ""
        if self.web_use_playwright and sync_playwright is not None and self.web_search_timeout_sec >= 8:
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=self.browser_headless)
                    page = browser.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=9000)
                    self._inject_opuntia_banner(page, f"Reading · {url[:80]}")
                    html_body = page.content() or ""
                    browser.close()
                text = self._strip_html_tags(html_body)
                if text:
                    return text[:3000]
            except Exception:
                pass
        try:
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code >= 400:
                return ""
            text = self._strip_html_tags(r.text or "")
            return text[:3000]
        except Exception:
            return ""

    def _needs_live_web_research(self, user_input):
        """Check if query needs live internet research."""
        t = (user_input or "").strip().lower()
        if not t:
            return False

        # File/document creation â€” never needs live web research
        _doc_block = [
            r"\b(pdf|\.pdf|docx?|\.docx?|word\s+doc)\b",
            r"^(create|make|write|save|generate|build)\b.{0,60}\b(pdf|doc|word|folder|file)\b",
            r"\b(?:write|create)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))\b",
            r"\bwrite\s+(the\s+)?(last|previous)\b",
            r"\bnamed?\s+\w",
            r"\bcalled\s+\w",
            r"\b(inside|in|as|into)\s+(?:a\s+)?pdf\b",
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in _doc_block):
            return False

        # Explicit web search requests
        explicit_patterns = [
            r'\b(search (the )?web|look up|find online|from internet|from the internet)\b',
            r'\b(website|link|links|sources?)\b',
            r'\b(news|price|prices|stock|crypto|weather|score|result|update)\b.*\b(today|now|current|latest|live)\b',
            r'\b(bring|get|fetch|search)\b.*\b(internet|web)\b',
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in explicit_patterns):
            return True
        
        # Follow-up information requests (how many, what is, who has, etc.)
        info_patterns = [
            r'\b(how many|how much|how old|when|where|who|what)\b',
            r'\b(how many (sons|daughters|children|kids|brothers|sisters))\b',
            r'\b(does he|does she|did he|did she|has he|has she)\b',
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in info_patterns):
            # Check if there's conversation history (follow-up question)
            if self.conversation_history:
                return True  # Search for updated info
        
        return False

    def _build_live_web_context(self, query, limit=3):
        results = self._search_web_results(query, limit=limit)
        if not results:
            return ""
        lines = []
        for i, item in enumerate(results, start=1):
            title = item.get("title", "")
            url = item.get("url", "")
            excerpt = self._fetch_url_excerpt(url)
            lines.append(f"{i}. {title}\nURL: {url}")
            if excerpt:
                lines.append(f"Snippet: {excerpt}")
        return "Live web results:\n" + "\n".join(lines)[:3400]

    def _format_live_links(self, query, with_snippets=False, limit=6):
        results = self._search_web_results(query, limit=limit)
        if not results:
            why = self.last_live_web_error or "live search provider unavailable"
            return f"I could not fetch live web results right now. Reason: {why}."
        lines = [f"Live links for: {query}"]
        for i, item in enumerate(results, start=1):
            title = item.get("title", "")
            url = item.get("url", "")
            lines.append(f"{i}. {title}\n   {url}")
            if with_snippets:
                excerpt = self._fetch_url_excerpt(url)
                if excerpt:
                    lines.append(f"   Snippet: {excerpt[:260]}")
        self.last_live_web_query = query
        return "\n".join(lines)

    def _should_auto_web_research(self, cmd_lower):
        if not self.web_research_auto:
            return False
        t = (cmd_lower or "").strip().lower()
        if not t:
            return False
        if re.search(
            r"\b(explain|clarify|what\s+(did|have)\s+you\s+(write|say|send)|what\s+you\s+(wrote|said|sent)|previous\s+(answer|reply|response)|last\s+(answer|reply|response))\b",
            t,
            re.IGNORECASE,
        ):
            return False
        if self._is_smalltalk_query(t):
            return False
        # Avoid hijacking normal conversation into web research unless explicitly web-like.
        if len(t.split()) <= 8 and not re.search(r"\b(internet|web|online|latest|today|current|news|price|weather|update)\b", t):
            return False
        # Vague "do research on internet" requests without a concrete topic.
        if re.search(r"\b(research|reserach|reseach|resarch|search)\b", t) and re.search(r"\b(internet|web|online)\b", t):
            generic_only = re.sub(r"[^a-z0-9\s]", " ", t)
            generic_only = re.sub(
                r"\b(can|you|do|please|make|making|some|on|the|internet|web|online|research|reserach|reseach|resarch|search|for|me|a)\b",
                " ",
                generic_only,
            )
            generic_only = re.sub(r"\s+", " ", generic_only).strip()
            if not generic_only:
                return False
        # Capability/meta questions should not trigger a live search directly.
        if (
            re.search(r"\b(can you|do you)\b", t)
            and re.search(r"\b(search|research|reserach|reseach|look up|find)\b", t)
            and re.search(r"\b(internet|web|online)\b", t)
        ):
            return False
        # Skip command-like/system intents handled elsewhere.
        block_patterns = [
            r"^\s*(hi|hello|hey)\b",
            r"\b(open|close|launch|run|quit|exit|shutdown|restart|sleep|lock)\b",
            r"\b(file|folder|desktop items|running apps|app status|settings)\b",
            r"\b(salat|salah|prayer)\b",
            r"\b(crypto|bitcoin|btc|ethereum|eth)\b",
            # File/document creation â€” always handled by local handlers, never web search
            r"\b(pdf|\.pdf|docx?|\.docx?|word\s+doc)\b",
            r"^(create|make|write|save|generate|build)\b.{0,60}\b(pdf|doc|word|folder|file)\b",
            r"\b(?:write|create)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))\b",
            r"\bwrite\s+(the\s+)?(last|previous)\b",
            r"\bnamed?\s+\w",
            r"\bcalled\s+\w",
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in block_patterns):
            return False
        # Positive cues for factual internet lookup.
        info_patterns = [
            r"\b(latest|recent|today|now|current|breaking|live)\b",
            r"\b(news|update|updates|price|prices|score|result|weather|release|changelog)\b",
            r"\b(internet|web|online)\b",
            r"\b(find|check|give|tell|bring|research|look up|information|info|details)\b",
            r"^(who|what|when|where|why|how)\b",
        ]
        hits = sum(1 for p in info_patterns if re.search(p, t, flags=re.IGNORECASE))
        return hits >= 2

    def _should_force_universal_web_research(self, user_input, cmd_lower):
        if not self.web_universal_mode:
            return False
        t = (cmd_lower or "").strip().lower()
        if not t:
            return False
        if self._is_smalltalk_query(t):
            return False
        # Keep ordinary chat on the normal assistant path.
        if len(t.split()) <= 8 and not re.search(r"\b(internet|web|online|latest|today|current|news|price|weather|update)\b", t):
            return False
        # Keep local/system/app controls out of universal web routing.
        blocked = [
            r"^\s*(hi|hello|hey)\b",
            r"\b(open|close|launch|run|quit|exit|shutdown|restart|sleep|lock)\b",
            r"\b(file|folder|desktop items|running apps|app status|settings|screenshot)\b",
            r"\b(memory|training|prompt|trace|debug|plan)\b",
            r"\b(wifi|bluetooth|brightness|volume|luminosity)\b",
            r"\b(internet|online)\s+status\b",
            r"\b(date|today'?s date|what(?:'s| is)\s+the\s+date)\b",
            r"\b(time|what(?:'s| is)\s+the\s+time)\b",
            # File/document creation â€” always handled locally, never via web search
            r"\b(pdf|\.pdf|docx?|\.docx?|word\s+doc)\b",
            r"^(create|make|write|save|generate|build)\b.{0,60}\b(pdf|doc|word|folder|file)\b",
            r"\b(?:write|create)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))\b",
            r"\bwrite\s+(the\s+)?(last|previous)\b",
            r"\bnamed?\s+\w",
            r"\bcalled\s+\w",
        ]
        if any(re.search(p, t, flags=re.IGNORECASE) for p in blocked):
            return False
        # Always search when comparing tools/products/AI assistants â€” the other
        # tool may be unknown to the model and must be looked up.
        if re.search(r'\b(difference|compare|comparison|vs\.?|versus|between)\b', t):
            topic = self._extract_research_topic(user_input)
            if topic:
                return True
        # Factual/query-like signals.
        factual = [
            r"^(who|what|when|where|why|how)\b",
            r"\b(latest|recent|today|now|current|breaking|live)\b",
            r"\b(news|update|updates|price|prices|weather|forecast|war|release|changelog|facts?)\b",
            r"\b(internet|web|online)\b",
            r"\?$",
        ]
        hits = sum(1 for p in factual if re.search(p, t, flags=re.IGNORECASE))
        if hits < 2:
            return False
        topic = self._extract_research_topic(user_input)
        return bool(topic)

    def _get_followup_context(self, user_input):
        """
        Detect whether the current message depends on previous context.
        Returns a system-hint string, or "" when it looks standalone.
        """
        q = (user_input or "").strip()
        words = q.split()
        if len(words) > 18:
            return ""
        _has_data_kw = bool(re.search(
            r"\b(numbers?|data|statistics?|stats?|more|details?|info(?:rmation)?|"
            r"examples?|specific|exact|precise|figures?|percentages?|breakdown|"
            r"deeper|elaborate|expand|latest|recent|current|update)\b",
            q, re.IGNORECASE,
        ))
        _is_vague_followup = (
            len(words) <= 12
            and bool(re.match(r"^(?:and\s+)?(where|what|when|how|which|who|should|is|are|can|do|does|explain|clarify)\b", q, re.IGNORECASE))
            and bool(re.search(r"\b(first|second|third|next|best|top|worst|one|it|this|that|there|them|see|visit|go|do|start|begin|recommend|previous|last)\b", q, re.IGNORECASE))
        )
        if (not _is_vague_followup) and bool(re.match(r"^\s*and\s+what\s+about\b", q, re.IGNORECASE)):
            _is_vague_followup = True
        _is_explain_prev = bool(re.search(
            r"\b(explain|clarify|elaborate|summari[sz]e|what\s+(did|have)\s+you\s+(write|say|send)|"
            r"what\s+you\s+(wrote|write|said|sent)|that\s+answer|previous\s+(answer|reply|response|message)|"
            r"last\s+(answer|reply|response|message))\b",
            q, re.IGNORECASE,
        ))
        if not (_has_data_kw or _is_vague_followup or _is_explain_prev):
            return ""
        if re.search(r"https?://", q):
            return ""
        hist = list(getattr(self, "task_conversation_history", []) or getattr(self, "conversation_history", []))
        if not hist:
            hist = list(getattr(self, "conversation_history", []))
        last_user_q = ""
        if hist:
            for turn in reversed(hist[-8:]):
                u = (turn.get("user") or "").strip()
                if u and len(u.split()) >= 2 and not self._is_smalltalk_query(u.lower()):
                    last_user_q = u
                    break
        if not last_user_q:
            last_user_q = (getattr(self, "last_user_message", "") or "").strip()
        if not last_user_q or last_user_q.lower() == q.lower():
            return ""
        if _is_explain_prev:
            last_reply = (getattr(self, "last_assistant_message", "") or "").strip()
            return (
                "FOLLOW-UP ALERT: The user asks about your previous response. "
                f"Previous user prompt: \"{last_user_q}\". "
                f"Previous assistant response excerpt: \"{last_reply[:700]}\". "
                "Explain/refine THAT response, do not switch topics."
            )
        return (
            "FOLLOW-UP ALERT: The user message continues the previous topic. "
            f"Previous user prompt: \"{last_user_q}\". "
            "Interpret this as continuation, not a new independent query."
        )

    def _expand_query_with_context(self, user_input):
        """
        For web search routing: if the current query is a metric/data follow-up,
        return a version of it expanded with the last conversation topic so the
        search engine gets a useful query instead of bare 'numbers data 2026'.
        """
        hint = self._get_followup_context(user_input)
        if not hint:
            return user_input
        hist = list(getattr(self, 'task_conversation_history', []) or getattr(self, 'conversation_history', []))
        if not hist:
            hist = list(getattr(self, 'conversation_history', []))
        last_user_q = ''
        for turn in reversed(hist[-8:]):
            u = (turn.get('user') or '').strip()
            if u and len(u.split()) >= 4 and not self._is_smalltalk_query(u.lower()):
                last_user_q = u
                break
        if not last_user_q:
            last_user_q = (getattr(self, "last_user_message", "") or "").strip()
        if not last_user_q:
            return user_input
        # Append the last topic to the current query
        return f"{user_input} - context: {last_user_q}"

    def _resolve_pronoun_query(self, query):
        """If query is mostly pronouns, resolve the actual topic from conversation history."""
        q = (query or "").strip()
        # Strip pronouns and see what's left
        stripped = re.sub(
            r'\b(it|this|that|them|those|these|he|she|they|him|her|its|their|the)\b',
            ' ', q.lower()
        )
        stripped = re.sub(r'\s+', ' ', stripped).strip(' ,.')
        # If almost nothing remains (short vague query), pull topic from recent history
        if len(stripped.split()) <= 2 and self.conversation_history:
            for turn in reversed(self.conversation_history[-6:]):
                user_msg = (turn.get('user') or '').strip()
                if not user_msg or len(user_msg.split()) < 3:
                    continue
                if self._is_smalltalk_query(user_msg.lower()):
                    continue
                # Build a concrete search query from keywords of the last relevant turn
                kws = self._extract_keywords(user_msg)
                if kws:
                    return ' '.join(kws[:6])
        return q

    def _answer_from_live_web(self, query):
        q = self._sanitize_search_query(query)
        if not q:
            q = (query or "").strip()
        # Resolve pronoun-heavy queries (e.g. "find it", "search that") using context
        q = self._resolve_pronoun_query(q)
        # Prefer provider-native built-in search tool when configured.
        if self.use_openai_builtin_search:
            answer = self._call_openai_builtin_web_search(q)
            if answer:
                self.last_live_web_query = q
                self.last_live_web_error = ""
                return answer
        return self._answer_from_research_loop(q)

    def _sanitize_search_query(self, text):
        q = (text or "").strip()
        if not q:
            return ""
        q = re.sub(
            r"^(?:please\s+)?(?:can|could|would|do)\s+you\s+",
            "",
            q,
            flags=re.IGNORECASE,
        ).strip(" ,.?")
        q = re.sub(
            r"^(?:search|research|find|look up|check|bring|give|tell me|show me)\s+(?:for me\s+)?",
            "",
            q,
            flags=re.IGNORECASE,
        ).strip(" ,.?")
        q = re.sub(r"\b(?:on|from)\s+(?:the\s+)?(?:internet|web|online)\b", " ", q, flags=re.IGNORECASE)
        q = re.sub(r"\b(?:right now|for me|please)\b", " ", q, flags=re.IGNORECASE)
        q = re.sub(r"\s+", " ", q).strip(" ,.?")
        if len(q.split()) <= 2 and re.search(r"\b(news|updates?)\b", q, flags=re.IGNORECASE):
            q = "latest world news"
        return q

    def _extract_research_topic(self, user_input):
        t = (user_input or "").strip()
        if not t:
            return ""
        if self._is_smalltalk_query(t):
            return ""
        cleaned = self._sanitize_search_query(t)
        # Remove generic shells that do not carry a topic.
        probe = re.sub(r"[^a-z0-9\s]", " ", cleaned.lower())
        probe = re.sub(
            r"\b(can|you|do|please|make|making|some|on|the|internet|web|online|research|reserach|reseach|resarch|search|for|me|a)\b",
            " ",
            probe,
        )
        probe = re.sub(r"\s+", " ", probe).strip()
        if not probe:
            return ""
        return cleaned

    def _is_smalltalk_query(self, text):
        t = (text or "").strip().lower().strip("\"'")
        if not t:
            return False
        patterns = [
            # Pure greetings
            r"^\s*(hi|hello|hey|yo|sup|good\s+(morning|afternoon|evening|night))\s*[!.,?]*\s*$",
            # Pure wellbeing questions
            r"^\s*(hru|how\s+r\s+u|how\s+r\s+you|how\s+are\s+u|how\s+are\s+you|how\s+u|how\s+you\s+doing|how\s+are\s+you\s+doing|how\s+do\s+you\s+do)\s*[!.,?]*\s*$",
            # Combined greeting + wellbeing: "hey how are you", "hi, how are you doing?"
            r"^\s*(hi|hello|hey|yo)\s*[,!]?\s*(how\s+(are\s+you|r\s+u|are\s+u|you\s+doing|r\s+u\s+doing|is\s+it\s+going)[!.,?]*)\s*$",
            # What's up variants
            r"^\s*(what'?s\s+up|wassup|was\s+up|how'?s\s+it\s+going|how'?s\s+everything|all\s+good)\s*[!.,?]*\s*$",
            # Acknowledgements
            r"^\s*(thanks|thank\s+you|thank\s+u|thx|ty|ok|okay|cool|nice|great|got\s+it|understood|perfect|awesome)\s*[!.,?]*\s*$",
            # Farewells
            r"^\s*(bye|goodbye|good\s+bye|see\s+you|see\s+ya|later|cya|take\s+care)\s*[!.,?]*\s*$",
        ]
        return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)

    def _call_openai_builtin_web_search(self, query):
        if not self.openai_api_key:
            return ""
        q = (query or "").strip()
        if not q:
            return ""
        try:
            payload = {
                "model": self.openai_search_model,
                "input": q,
                "tools": [{"type": "web_search_preview"}],
                "temperature": 0.2,
            }
            r = requests.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=max(12, self.web_search_timeout_sec + 2),
            )
            if r.status_code >= 400:
                self.last_live_web_error = f"OpenAI built-in search HTTP {r.status_code}"
                return ""
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            text = (data.get("output_text") or "").strip()
            if text:
                return text
            # Fallback parser for structured response output.
            output = data.get("output") or []
            chunks = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "message":
                    continue
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "output_text":
                        t = (c.get("text") or "").strip()
                        if t:
                            chunks.append(t)
            return "\n".join(chunks).strip()
        except Exception as e:
            self.last_live_web_error = f"OpenAI built-in search error: {type(e).__name__}"
            return ""

    def _expand_research_queries(self, query):
        q = self._sanitize_search_query(query)
        if not q:
            return []
        variants = [self._normalize_web_query(q)]
        low = q.lower()
        if len(q.split()) >= 2:
            variants.append(self._normalize_web_query(f"{q} official source"))
            variants.append(self._normalize_web_query(f"{q} site:gov OR site:edu OR site:org"))
        if re.search(r"\b(latest|recent|today|now|current|update|updates|news)\b", low):
            variants.append(self._normalize_web_query(q + " official"))
            variants.append(self._normalize_web_query(q + " release notes"))
            variants.append(self._normalize_web_query(q + " announcement"))
        if re.search(r"\b(price|prices|stock|crypto|weather|score|results?)\b", low):
            variants.append(self._normalize_web_query(q + " live data"))
        if re.search(r"\b(who|what|when|where|why|how)\b", low):
            variants.append(self._normalize_web_query("fact check " + q))
        # Sports winner queries Ã¢Â€Â” add a direct "result" variant
        if re.search(r"\b(won|winner|champion|champions|title|cup|trophy|final|finals)\b", low):
            variants.append(self._normalize_web_query(q + f" {datetime.now().year} result"))
        # Match schedule queries Ã¢Â€Â” add competition + year context to surface exact dates/times
        year = datetime.now().year
        if re.search(r"\bvs\.?\b|\bversus\b|\bmatch\b|\bgame\b|\bfixture\b", low):
            variants.append(self._normalize_web_query(q + f" {year} date time"))
            variants.append(self._normalize_web_query(q + f" {year} schedule kick off"))
            # CAF-specific expansion for North-African clubs
            if re.search(r"\b(est|espÃƒÂ©rance|taraji|ahly|al ahly|zamalek|wydad|raja|sfaxien|usm alger)\b", low):
                variants.append(self._normalize_web_query(q + f" CAF Champions League {year} quarter final"))
        # "when is X vs Y" / "next match X" Ã¢Â€Â” same treatment
        if re.search(r"\b(when|next match|next game|next fixture)\b", low) and re.search(r"\bvs\.?\b|\bversus\b|taraji|ahly|est\b", low):
            variants.append(self._normalize_web_query(q + f" {year} CAF Champions League schedule"))
        out = []
        seen = set()
        for v in variants:
            key = re.sub(r"\s+", " ", v.lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(v)
        return out[: max(1, self.web_research_max_passes)]

    def _collect_research_evidence(self, query):
        queries = self._expand_research_queries(query)
        qk = self._keyword_set(query)
        # Step 1: Run all search queries (these are fast API calls)
        pending = []   # list of (search_result_dict, query_string)
        seen_urls = set()
        trace = []
        for q in queries:
            results = self._search_web_results(q, limit=max(3, self.web_research_results_per_pass))
            trace.append({"query": q, "raw_results": len(results)})
            for r in results:
                url = (r.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                pending.append((r, q))

        # Step 2: Fetch URL excerpts IN PARALLEL Ã¢Â€Â” massive speedup vs sequential
        # Skip fetching if the search API already returned a good snippet (Brave/Tavily do this).
        _GOOD_SNIPPET_MIN = 180  # chars Ã¢Â€Â” if snippet is this long, skip URL fetch
        _URL_FETCH_WORKERS = 6   # fetch up to 6 URLs simultaneously
        _URL_FETCH_TIMEOUT = 6   # seconds per URL

        def _fetch_one(item):
            r, q = item
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip()
            existing_snippet = (r.get("snippet") or r.get("text") or "").strip()
            # If search API already gave a good snippet, skip the slow URL fetch
            if len(existing_snippet) >= _GOOD_SNIPPET_MIN:
                excerpt = existing_snippet
            else:
                try:
                    excerpt = self._fetch_url_excerpt(url) or existing_snippet
                except Exception:
                    excerpt = existing_snippet
            return r, q, title, excerpt

        evidence = []
        if pending:
            with ThreadPoolExecutor(max_workers=_URL_FETCH_WORKERS) as pool:
                futures = {pool.submit(_fetch_one, item): item for item in pending}
                overall_timeout = _URL_FETCH_TIMEOUT * min(len(pending), _URL_FETCH_WORKERS) + 5
                try:
                    for future in as_completed(futures, timeout=overall_timeout):
                        try:
                            r, q, title, excerpt = future.result(timeout=_URL_FETCH_TIMEOUT)
                            url = (r.get("url") or "").strip()
                            text = (title + " " + excerpt).lower()
                            overlap = sum(1 for k in qk if k in text)
                            evidence.append({
                                "query": q,
                                "title": title[:180],
                                "url": url,
                                "excerpt": (excerpt or "")[:2500],
                                "score": overlap,
                            })
                        except Exception:
                            pass
                except Exception:
                    # Overall timeout expired Ã¢Â€Â” return whatever evidence collected so far
                    pass

        evidence.sort(key=lambda x: (x.get("score", 0), len(x.get("excerpt", ""))), reverse=True)
        if self.web_research_trace:
            try:
                top_preview = []
                for e in evidence[:10]:
                    top_preview.append(
                        {
                            "score": e.get("score", 0),
                            "query": e.get("query", ""),
                            "title": e.get("title", ""),
                            "url": e.get("url", ""),
                        }
                    )
                trace_blob = {
                    "query": query,
                    "passes": trace,
                    "evidence_count": len(evidence),
                    "top": top_preview,
                }
                self._audit("web_research_trace", "ok", trace_blob)
            except Exception:
                pass
        return evidence

    def _format_research_trace_for_chat(self, query):
        evidence = self._collect_research_evidence(query)
        if not evidence:
            why = self.last_live_web_error or "no relevant sources"
            return f"Research trace: no results.\nReason: {why}"
        lines = [f"Research trace for: {query}"]
        by_query = {}
        for e in evidence:
            by_query.setdefault(e.get("query", ""), []).append(e)
        for q, arr in list(by_query.items())[: self.web_research_max_passes]:
            lines.append(f"- Query: {q} -> {len(arr)} scored sources")
            for i, e in enumerate(arr[:3], start=1):
                lines.append(f"  {i}. score={e.get('score',0)} | {e.get('title','')}")
                lines.append(f"     {e.get('url','')}")
        return "\n".join(lines)

    def _answer_from_research_loop(self, query):
        evidence = self._collect_research_evidence(query)
        if not evidence:
            why = self.last_live_web_error or "no relevant sources"
            return f"I could not fetch live web results right now. Reason: {why}."
        top = evidence[:10]
        unique_domains = set()
        for e in top:
            u = (e.get("url") or "").lower()
            try:
                domain = re.sub(r"^https?://", "", u).split("/")[0]
            except Exception:
                domain = ""
            if domain:
                unique_domains.add(domain)
        confidence = "High" if len(unique_domains) >= 4 else ("Medium" if len(unique_domains) >= 2 else "Low")
        lines = []
        for i, e in enumerate(top, start=1):
            lines.append(
                f"{i}. [{e.get('query','')}] {e.get('title','')}\n"
                f"URL: {e.get('url','')}\n"
                f"Snippet: {e.get('excerpt','')}"
            )
        now_str = datetime.now().strftime("%A, %B %d, %Y")
        web_context = "=== LIVE WEB SEARCH RESULTS (fetched right now) ===\n" + "\n\n".join(lines)
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are Opuntia, an intelligent assistant. Today is {now_str}.\n\n"
                        "You have just performed a real-time web search. Use BOTH the web results AND your training knowledge.\n\n"
                        "## Answer structure (always follow this)\n"
                        "1. **Direct answer first** Ã¢Â€Â” open with the key fact, date, name, or result. No preamble.\n"
                        "2. **Scale depth to the question:**\n"
                        "   - Simple fact ? 1-3 sentences with inline citations [1][2].\n"
                        "   - Technical/complex ? ## Overview + sections (explanation, examples, comparison table if useful, implications).\n"
                        "   - Match/fixture/schedule query ? **always use a Markdown table** with columns: Match, Date, Kick-off Time (GMT), Venue. Then add local time notes as bullet points.\n"
                        "3. **Bold** key facts, names, numbers. Bullet points for 3+ items. Tables when comparing options or listing fixtures.\n"
                        "4. Flow: definition ? explanation ? examples/applications ? implications.\n"
                        "5. If results conflict, note it clearly.\n"
                        "6. No filler: never start with 'Great question!', 'Certainly!', 'Based on the provided information', 'Let me search', '[Searching...]'.\n"
                        "7. Do NOT write a Sources or References section Ã¢Â€Â” sources are appended automatically.\n"
                        "8. **CRITICAL Ã¢Â€Â” Never deflect when results exist:** If the exact answer isn't in the results, present the closest available information. NEVER say 'I couldn't find', 'I don't have information', 'I was unable to locate', or 'please check manually' when search results are present. Commit to an answer using what was found."
                    ),
                },
                {"role": "system", "content": web_context[:12000]},
                {"role": "user", "content": query},
            ]
            answer = self._strip_ai_sources(self._call_ai(messages))
            src_urls = []
            for e in top[:3]:
                u = e.get("url", "")
                if u and u not in src_urls:
                    src_urls.append(u)
            if src_urls:
                answer += "\n\n**Sources:** " + " Ã‚Â· ".join(f"[{i}] {u}" for i, u in enumerate(src_urls, 1))
            self.last_live_web_query = query
            return answer
        except Exception:
            return self._format_live_links(query, with_snippets=True, limit=6)

    def _extract_live_update_topic(self, user_input):
        t = (user_input or "").strip()
        low = t.lower()
        if not t:
            return ""
        if not re.search(r"\b(update|updates|latest|recent|news|release|release notes|changelog|announcement|announcements)\b", low):
            return ""
        # Don't hijack writing/composing requests
        if re.search(r"\b(write|compose|draft|create|make|prepare|send|format)\b", low) and \
           re.search(r"\b(mail|email|message|letter|text|note|report|document|memo)\b", low):
            return ""
        # Remove leading request verbs.
        cleaned = re.sub(
            r"^(?:please\s+)?(?:bring|give|find|search|look up|show|tell me|i want|i need|get)\s+",
            "",
            t,
            flags=re.IGNORECASE,
        ).strip(" ,.?")
        cleaned = re.sub(r"^(?:information|infos?|details)\s+(?:about|on)\s+", "", cleaned, flags=re.IGNORECASE).strip(" ,.?")
        cleaned = re.sub(r"\b(on|from)\s+(the\s+)?internet\b", "", cleaned, flags=re.IGNORECASE).strip(" ,.?")
        # normalize "last update(s) of X"
        m = re.search(r"\b(?:last|latest|recent)\s+updates?\s+(?:of|for|on)\s+(.+)$", cleaned, flags=re.IGNORECASE)
        if m:
            topic = m.group(1).strip(" ,.?")
            return f"latest updates {topic}"
        m = re.search(r"\b(?:last|latest|recent)\s+update\s+(?:of|for|on)\s+(.+)$", cleaned, flags=re.IGNORECASE)
        if m:
            topic = m.group(1).strip(" ,.?")
            return f"latest update {topic}"
        m = re.search(r"\bupdates?\s+(?:of|for|on)\s+(.+)$", cleaned, flags=re.IGNORECASE)
        if m:
            topic = m.group(1).strip(" ,.?")
            return f"latest updates {topic}"
        if re.search(r"\bgpt\b", low):
            return "latest updates GPT"
        return cleaned if len(cleaned.split()) >= 2 else ""

    def search_web_on_app(self, query, app_hint=None):
        """Search the web, optionally forcing a specific browser/app."""
        url = self._search_query_url(query)
        if not url:
            return "Tell me what to search for."

        if app_hint:
            if self._open_url_in_browser(url, app_hint):
                return f"Searched for '{query}' on {app_hint}."
            # Fallback: try opening app, then default browser search.
            self.open_app(app_hint)
        if self._open_url_in_browser(url, None):
            return f"Searched for: {query}"
        return f"Could not search for: {query}"

    def _is_generic_web_target(self, target_text):
        t = (target_text or "").strip().lower()
        if not t:
            return False
        generic = {
            "internet",
            "the internet",
            "web",
            "the web",
            "online",
            "browser",
            "default browser",
            "google",
            "search engine",
        }
        return t in generic or any(x in t for x in ["internet", "web", "online", "browser"])

    def _extract_location_from_text(self, text):
        t = (text or "").strip()
        if not t:
            return None
        m = re.search(r"\b(?:in|for|at)\s+([A-Za-z][A-Za-z .'-]{1,40})$", t, flags=re.IGNORECASE)
        if not m:
            m = re.search(r"\b(?:in|for|at)\s+([A-Za-z][A-Za-z .'-]{1,40})\b", t, flags=re.IGNORECASE)
        if not m:
            return None
        loc = (m.group(1) or "").strip(" ,.?")
        return loc if loc else None

    def _get_prayer_times_today(self, user_input):
        """Fetch today's prayer times from AlAdhan API."""
        city = self._extract_location_from_text(user_input) or os.getenv("DEFAULT_PRAYER_CITY", "Tunis")
        country = os.getenv("DEFAULT_PRAYER_COUNTRY", "Tunisia")
        method = os.getenv("PRAYER_METHOD", "3").strip()
        today = datetime.now().strftime("%d-%m-%Y")
        try:
            url = (
                "https://api.aladhan.com/v1/timingsByCity"
                f"?city={quote_plus(city)}&country={quote_plus(country)}&method={quote_plus(method)}&date={quote_plus(today)}"
            )
            r = requests.get(url, timeout=12)
            if r.status_code >= 400:
                return f"Could not fetch prayer times right now (HTTP {r.status_code})."
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            timings = (((data or {}).get("data") or {}).get("timings") or {})
            if not timings:
                return "Could not fetch prayer times right now."
            keys = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
            lines = [f"Prayer times for {city}, {country} ({today}):"]
            for k in keys:
                v = (timings.get(k) or "").strip()
                if v:
                    lines.append(f"  - {k}: {v}")
            lines.append(f"Source: {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Could not fetch prayer times: {e}"

    def _get_local_username(self):
        try:
            name = os.getlogin().strip()
            if name:
                return name
        except Exception:
            pass
        name = (os.getenv("USERNAME") or os.getenv("USER") or "").strip()
        return name or "Unknown"

    def _resolve_location_coords(self, user_input):
        city = self._extract_location_from_text(user_input) or os.getenv("DEFAULT_WEATHER_CITY", "Tunis")
        if not city:
            city = "Tunis"
        try:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={quote_plus(city)}&count=1&language=en&format=json"
            r = requests.get(geo_url, timeout=10)
            if r.status_code >= 400:
                return None
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            results = data.get("results") or []
            if not results:
                return None
            g = results[0]
            return {
                "name": g.get("name") or city,
                "country": g.get("country") or "",
                "lat": float(g.get("latitude")),
                "lon": float(g.get("longitude")),
                "timezone": g.get("timezone") or "auto",
            }
        except Exception:
            return None

    def _get_weather_now_and_next_hours(self, user_input, hours=12):
        loc = self._resolve_location_coords(user_input)
        if not loc:
            return "Could not resolve location for weather. Try: 'weather now in Tunis'."
        h = max(1, min(24, int(hours)))
        lat = loc["lat"]
        lon = loc["lon"]
        tz = "auto"
        try:
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                "&current=temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
                "&hourly=temperature_2m,precipitation_probability,wind_speed_10m,weather_code"
                "&forecast_days=2"
                f"&timezone={quote_plus(tz)}"
            )
            r = requests.get(url, timeout=12)
            if r.status_code >= 400:
                return f"Could not fetch weather right now (HTTP {r.status_code})."
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else {}
            current = data.get("current") or {}
            hourly = data.get("hourly") or {}
            times = hourly.get("time") or []
            temps = hourly.get("temperature_2m") or []
            pops = hourly.get("precipitation_probability") or []
            winds = hourly.get("wind_speed_10m") or []
            if not times:
                return "Could not fetch hourly weather data."

            lines = [f"Weather for {loc['name']}{', ' + loc['country'] if loc['country'] else ''}:"]
            if current:
                lines.append(
                    "Now: "
                    f"{current.get('temperature_2m', 'N/A')}Ã‚Â°C, "
                    f"feels {current.get('apparent_temperature', 'N/A')}Ã‚Â°C, "
                    f"wind {current.get('wind_speed_10m', 'N/A')} km/h, "
                    f"precip {current.get('precipitation', 'N/A')} mm"
                )
            lines.append(f"Next {h} hours:")
            for i in range(min(h, len(times))):
                t = str(times[i]).split("T")[-1][:5]
                temp = temps[i] if i < len(temps) else "N/A"
                pop = pops[i] if i < len(pops) else "N/A"
                wind = winds[i] if i < len(winds) else "N/A"
                lines.append(f"  - {t}: {temp}Ã‚Â°C, rain {pop}%, wind {wind} km/h")
            lines.append(f"Source: {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Could not fetch weather: {e}"

    # =========================================================================
    # ADVANCED INTERNET BROWSING & SEARCH TOOLS
    # =========================================================================
    
    def _get_source_credibility_score(self, url):
        """Calculate credibility score for a source URL."""
        if not url:
            return 0.0
        url_lower = url.lower()
        
        # High credibility domains
        high_credibility = [
            'wikipedia.org', 'britannica.com', 'scholar.google', 'arxiv.org',
            '.gov', '.edu', '.ac.', 'nih.gov', 'ncbi.nlm.nih.gov',
            'reuters.com', 'apnews.com', 'bbc.co.uk', 'npr.org',
            'nature.com', 'science.org', 'ieee.org', 'acm.org',
            'github.com', 'stackoverflow.com', 'medium.com',
            'openai.com', 'anthropic.com', 'google.ai', 'deepmind.com',
        ]
        
        # Low credibility indicators
        low_credibility = [
            'blogspot.com', 'wordpress.com', 'medium.com/@',
            'reddit.com/r/', 'quora.com', 'yahoo.com/answers',
        ]
        
        # Check high credibility
        for domain in high_credibility:
            if domain in url_lower:
                return 0.85 + (0.15 * (1.0 / (1.0 + url_lower.count('blog'))))
        
        # Check low credibility
        for domain in low_credibility:
            if domain in url_lower:
                return 0.35
        
        # Default moderate score
        return 0.55

    def _classify_search_intent(self, query):
        """Classify user query into search tool types."""
        q = (query or "").lower()
        
        # Company/tech news detection - Anthropic, OpenAI, Google, etc.
        company_news_patterns = [
            r'\b(anthropic|openai|google|microsoft|meta|apple|amazon|tesla|spacex)\b.*\b(ai|news|update|release|launch)\b',
            r'\b(ai|tech|technology|startup)\b.*\b(news|update|announcement)\b',
            r'\b(anthropic|claude|gpt|gemini|llama)\b.*\b(latest|new|update)\b',
        ]
        if any(re.search(p, q, flags=re.IGNORECASE) for p in company_news_patterns):
            return ['news', 'info']

        classifications = {
            'news': [
                r'\b(news|headlines|breaking|latest|today|current events)\b',
                r'\b(happened|announced|released|published)\b.*\b(today|yesterday|this week)\b',
            ],
            'research': [
                r'\b(research|study|paper|academic|scholarly|journal)\b',
                r'\b(evidence|data|analysis|findings|methodology)\b',
            ],
            'image': [
                r'\b(image|picture|photo|diagram|chart|graph|screenshot)\b',
                r'\b(show|display|visualize|see)\b.*\b(what|how|looks)\b',
            ],
            'video': [
                r'\b(video|tutorial|demo|demonstration|walkthrough)\b',
                r'\b(youtube|vimeo|watch)\b',
            ],
            'data': [
                r'\b(data|dataset|statistics|numbers|figures|table)\b',
                r'\b(json|csv|xml|api|structured)\b',
            ],
            'api': [
                r'\b(api|endpoint|sdk|library|integration)\b',
                r'\b(developer|documentation|reference|swagger)\b',
            ],
            'tool': [
                r'\b(tool|calculator|converter|generator|simulator)\b',
                r'\b(online|free|web-based)\b.*\b(tool|app)\b',
            ],
            'shopping': [
                r'\b(price|cost|buy|purchase|deal|discount|review)\b',
                r'\b(amazon|ebay|shop|store|product)\b',
            ],
        }

        scores = {}
        for tool_type, patterns in classifications.items():
            if not self.search_tool_types.get(tool_type, False):
                continue
            score = sum(1 for p in patterns if re.search(p, q, flags=re.IGNORECASE))
            if score > 0:
                scores[tool_type] = score / len(patterns)
        
        if not scores:
            return ['info']  # Default to general web search
        
        # Return types with score above threshold
        threshold = 0.3
        return [t for t, s in scores.items() if s >= threshold] or ['info']

    def _search_with_tool_type(self, query, tool_type, limit=5):
        """Execute search with specific tool type."""
        if tool_type == 'news':
            return self._search_news(query, limit)
        elif tool_type == 'image':
            return self._search_images(query, limit)
        elif tool_type == 'research':
            return self._search_research_papers(query, limit)
        elif tool_type == 'video':
            return self._search_videos(query, limit)
        elif tool_type == 'data':
            return self._search_datasets(query, limit)
        elif tool_type == 'api':
            return self._search_apis(query, limit)
        elif tool_type == 'shopping':
            return self._search_products(query, limit)
        else:
            return self._search_web_results(query, limit)

    def _search_news(self, query, limit=5):
        """Search news sources with multiple fallbacks."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        
        # Try Google News RSS
        try:
            url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec + 5)
            if r.status_code == 200:
                items = re.findall(r'(?is)<item>(.*?)</item>', r.text)
                for item in items[:limit * 2]:
                    title_m = re.search(r'(?is)<title>(.*?)</title>', item)
                    link_m = re.search(r'(?is)<link>(.*?)</link>', item)
                    desc_m = re.search(r'(?is)<description>(.*?)</description>', item)
                    if link_m:
                        link = html.unescape((link_m.group(1) or "").strip())
                        if link.startswith("http") and 'google.com' not in link.split('/')[2]:
                            results.append({
                                'title': html.unescape((title_m.group(1) or "").strip())[:180] if title_m else link,
                                'url': link,
                                'snippet': html.unescape(re.sub(r'<[^>]+>', '', (desc_m.group(1) or "")[:200])) if desc_m else "",
                                'source_type': 'news',
                            })
                            if len(results) >= limit:
                                break
        except Exception as e:
            print(f"Google News error: {e}")
        
        # Fallback: Regular web search with news keywords
        if not results:
            web_results = self._search_web_results(f"{q} news latest updates", limit)
            for r in web_results:
                r['source_type'] = 'news'
                results.append(r)
        
        return results[:limit]

    def _search_images(self, query, limit=5):
        """Search for images."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        # Use Google Images search (HTML parsing)
        try:
            url = f"https://www.google.com/search?q={quote_plus(q)}&tbm=isch&hl=en"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code == 200:
                # Extract image links from search results
                img_urls = re.findall(r'(?is)https://[^"\s]+\.(?:jpg|jpeg|png|gif|webp)[^"\s]*', r.text[:200000])
                seen = set()
                for img_url in img_urls[:limit * 2]:
                    if img_url not in seen and 'http' in img_url:
                        seen.add(img_url)
                        results.append({
                            'title': f"Image: {q}",
                            'url': img_url,
                            'source_type': 'image',
                        })
        except Exception:
            pass
        
        # Fallback: return search results about images
        if not results:
            web_results = self._search_web_results(f"{q} images diagrams", limit)
            for r in web_results:
                r['source_type'] = 'image'
                results.append(r)
        
        return results[:limit]

    def _search_research_papers(self, query, limit=5):
        """Search academic papers and research."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        # Google Scholar / arXiv / Semantic Scholar
        sources = [
            f"https://arxiv.org/search/?query={quote_plus(q)}&searchtype=all&abstracts=show&order=-announced_date_first&size=10",
            f"https://www.google.com/search?q={quote_plus(q)}+research+paper+pdf&hl=en",
        ]
        
        for url in sources:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
                if r.status_code == 200:
                    links = re.findall(r'(?is)href="(https?://[^"]+)"', r.text)
                    for link in links[:limit * 3]:
                        if any(x in link.lower() for x in ['arxiv', 'pdf', 'doi.org', 'researchgate', 'academia.edu']):
                            if link not in [r['url'] for r in results]:
                                results.append({
                                    'title': f"Research: {q[:60]}...",
                                    'url': link,
                                    'source_type': 'research',
                                })
                        if len(results) >= limit:
                            break
            except Exception:
                continue
            if results:
                break
        
        return results[:limit]

    def _search_videos(self, query, limit=5):
        """Search for videos."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        # YouTube search via Google
        try:
            url = f"https://www.google.com/search?q={quote_plus(q)}+site:youtube.com&hl=en"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code == 200:
                links = re.findall(r'(?is)href="(https?://www\.youtube\.com/watch[^"]+)"', r.text)
                seen = set()
                for link in links[:limit * 2]:
                    link = html.unescape(link)
                    if link not in seen:
                        seen.add(link)
                        results.append({
                            'title': f"Video: {q}",
                            'url': link,
                            'source_type': 'video',
                        })
        except Exception:
            pass
        
        return results[:limit]

    def _search_datasets(self, query, limit=5):
        """Search for datasets and structured data."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        # Dataset repositories
        dataset_sources = [
            f"https://www.google.com/search?q={quote_plus(q)}+dataset+json+csv&hl=en",
            f"https://www.google.com/search?q={quote_plus(q)}+site:kaggle.com+dataset&hl=en",
            f"https://www.google.com/search?q={quote_plus(q)}+site:data.gov&hl=en",
        ]
        
        for url in dataset_sources:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
                if r.status_code == 200:
                    links = re.findall(r'(?is)href="(https?://[^"]+\.(?:json|csv|xml|data)[^"]*)"', r.text)
                    for link in links[:limit]:
                        link = html.unescape(link)
                        if link not in [r['url'] for r in results]:
                            results.append({
                                'title': f"Dataset: {q[:50]}",
                                'url': link,
                                'source_type': 'data',
                            })
            except Exception:
                continue
        
        return results[:limit]

    def _search_apis(self, query, limit=5):
        """Search for APIs and developer resources."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        # API directories and documentation
        try:
            url = f"https://www.google.com/search?q={quote_plus(q)}+api+documentation+developer&hl=en"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code == 200:
                links = re.findall(r'(?is)href="(https?://[^"]+)"', r.text)
                seen = set()
                for link in links[:limit * 3]:
                    link = html.unescape(link)
                    if any(x in link.lower() for x in ['api', 'docs', 'developer', 'swagger', 'reference']):
                        if link not in seen and link.startswith('http'):
                            seen.add(link)
                            results.append({
                                'title': f"API: {q[:50]}",
                                'url': link,
                                'source_type': 'api',
                            })
        except Exception:
            pass
        
        return results[:limit]

    def _search_products(self, query, limit=5):
        """Search for products and shopping results."""
        q = (query or "").strip()
        if not q:
            return []
        
        results = []
        # Shopping search
        try:
            url = f"https://www.google.com/search?q={quote_plus(q)}+buy+price+review&tbm=shop&hl=en"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            r = requests.get(url, headers=headers, timeout=self.web_search_timeout_sec)
            if r.status_code == 200:
                links = re.findall(r'(?is)href="(https?://[^"]+)"', r.text)
                seen = set()
                for link in links[:limit * 2]:
                    link = html.unescape(link)
                    if any(x in link.lower() for x in ['amazon', 'ebay', 'shop', 'store', 'price']):
                        if link not in seen and link.startswith('http'):
                            seen.add(link)
                            results.append({
                                'title': f"Product: {q[:50]}",
                                'url': link,
                                'source_type': 'shopping',
                            })
        except Exception:
            pass
        
        return results[:limit]

    def _browse_url_deep(self, url, extract_text=True, extract_links=True, extract_images=False):
        """Deep browse a URL using Playwright for JavaScript-heavy sites."""
        if not self.web_use_playwright or sync_playwright is None:
            text = self._fetch_url_excerpt(url)
            return {'url': url, 'title': '', 'text': text or '', 'links': [], 'images': [], 'success': bool(text)}
        
        result = {
            'url': url,
            'title': '',
            'text': '',
            'links': [],
            'images': [],
            'success': False,
        }
        
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=self.browser_headless)
                page = browser.new_page()

                # Navigate with timeout
                page.goto(url, wait_until='domcontentloaded', timeout=self.browser_timeout_ms)

                # Wait for content to load
                page.wait_for_timeout(self.browser_wait_load_ms)
                self._inject_opuntia_banner(page, f"Browsing · {url[:80]}")

                # Extract title
                try:
                    result['title'] = page.title()[:200]
                except Exception:
                    pass
                
                # Extract text content
                if extract_text:
                    try:
                        text_content = page.content()
                        result['text'] = self._strip_html_tags(text_content)[:4000]
                    except Exception:
                        pass
                
                # Extract links
                if extract_links and self.browser_extract_links:
                    try:
                        links = page.query_selector_all('a[href]')
                        for link in links[:50]:
                            try:
                                href = link.get_attribute('href')
                                text = link.inner_text()[:100]
                                if href and href.startswith('http'):
                                    result['links'].append({'url': href, 'text': text})
                            except Exception:
                                continue
                    except Exception:
                        pass
                
                # Extract images
                if extract_images and self.browser_extract_images:
                    try:
                        images = page.query_selector_all('img[src]')
                        for img in images[:30]:
                            try:
                                src = img.get_attribute('src')
                                alt = img.get_attribute('alt') or ''
                                if src and src.startswith('http'):
                                    result['images'].append({'url': src, 'alt': alt[:100]})
                            except Exception:
                                continue
                    except Exception:
                        pass
                
                browser.close()
                result['success'] = True
                
        except Exception as e:
            result['error'] = str(e)[:200]
            # Fallback to requests
            result['text'] = self._fetch_url_excerpt(url)
        
        return result

    def _synthesize_search_results(self, query, results_by_type, messages):
        """Synthesize search results from multiple tool types into coherent answer."""
        all_results = []
        for tool_type, results in results_by_type.items():
            for r in results:
                r['tool_type'] = tool_type
                r['credibility'] = self._get_source_credibility_score(r.get('url', ''))
                all_results.append(r)
        
        # Sort by credibility and relevance
        all_results.sort(key=lambda x: (x.get('credibility', 0.5), len(x.get('text', ''))), reverse=True)
        
        # Filter by minimum credibility
        all_results = [r for r in all_results if r.get('credibility', 0) >= self.source_min_credibility_score]
        
        # Update metadata
        self.last_search_metadata = {
            'sources_used': [r.get('url', '') for r in all_results[:10]],
            'search_type': ','.join(results_by_type.keys()),
            'confidence': sum(r.get('credibility', 0.5) for r in all_results[:5]) / max(1, len(all_results[:5])),
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'iterations': 1,
        }
        
        # Format results for AI synthesis
        context_parts = []
        for i, r in enumerate(all_results[:15], 1):
            source_info = f"[{i}] {r.get('title', 'Source')}"
            if self.source_attribution_enabled:
                source_info += f"\n    URL: {r.get('url', 'N/A')}"
                source_info += f"\n    Type: {r.get('tool_type', 'web')}"
                if self.source_show_confidence:
                    source_info += f" (Credibility: {r.get('credibility', 0.5):.2f})"
            
            snippet = r.get('text', r.get('snippet', ''))[:1200]
            if snippet:
                source_info += f"\n    Content: {snippet}"
            
            context_parts.append(source_info)
        
        context = "\n\n".join(context_parts)
        
        # Generate synthesized answer
        now_str = datetime.now().strftime("%A, %B %d, %Y")


        # Build recent conversation context so follow-ups resolve correctly
        _conv_ctx = ""
        if messages:
            _recent_turns = []
            for _m in messages[-6:]:
                _role = _m.get("role", "")
                _content = _m.get("content", "") or _m.get("text", "")
                if _role == "user":
                    _recent_turns.append("User: " + str(_content)[:300])
                elif _role == "assistant":
                    _recent_turns.append("Opuntia: " + str(_content)[:300])
            if _recent_turns:
                _conv_ctx = (
                    "=== RECENT CONVERSATION ===\n"
                    + "\n".join(_recent_turns)
                    + "\n=== END ===\n\n"
                    "FOLLOW-UP RULE: Short queries about numbers/data/stats/details/of 20XX "
                    "are ALWAYS follow-ups about the topic above. "
                    "NEVER respond with generic date/time info just because a year appears.\n\n"
                )

        system_prompt = (
            f"You are Opuntia, a smart Windows desktop AI assistant created by the Opuntia Team. Today is {now_str}.\n\n"
            "## Who you are (use when asked about yourself or compared to other AI tools)\n"
            "Opuntia is a full-featured Windows AI agent: desktop automation, app management, real-time web search, "
            "URL browsing, weather, file & folder management, screen capture & vision, voice input (EN/FR/AR), "
            "memory & learning, document generation (PDF/Word/Excel/PowerPoint), system controls, advanced AI reasoning, "
            "and a full data & analytics engine: "
            "load CSV/Excel files with pandas, compute statistics (mean, variance, correlation, regression), "
            "generate charts (bar, line, pie, scatter, histogram, heatmap, boxplot) using matplotlib, "
            "export analytics Excel workbooks with multi-sheet reports and conditional formatting, "
            "fetch live data from public APIs using requests. "
            "When comparing yourself to another AI, describe YOUR capabilities above accurately -- never invent Opuntia features.\n\n"
            + _conv_ctx
            + "You have performed a live web search. Combine the results with your training knowledge.\n\n"
            "## Answer format\n"
            "1. Direct answer first -- no preamble.\n"
            "2. Depth: simple query -> 1-3 sentences [1][2]; complex -> ## headings; "
            "comparison between 2+ things -> **Markdown table** (Feature | Item1 | Item2); "
            "fixtures/schedules -> Markdown table.\n"
            "3. **Bold** key names/numbers. Bullets for 3+ items. Tables for comparisons.\n\n"
            "Do NOT write 'Based on...', 'Certainly!', '[Searching...]', 'Let me check'. Just answer. "
            "Do NOT write a Sources section -- appended automatically. "
            "NEVER say 'I could not find' or 'I don't have information' when results exist. Commit to an answer."
        )


        user_prompt = (
            f"Question: {query}\n\n"
            f"Live search results:\n{context}\n\n"
            "Answer directly and clearly using both the search results and your knowledge."
        )
        
        synthesis_messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        
        try:
            answer = self._strip_ai_sources(self._call_ai(synthesis_messages))

            # Append top 3 sources only Ã¢Â€Â” clean, compact footer
            if self.source_attribution_enabled and all_results:
                top3 = [r for r in all_results[:3] if r.get('url')]
                if top3:
                    answer += "\n\n**Sources:** " + " Ã‚Â· ".join(
                        f"[{i}] {r.get('url', '')}" for i, r in enumerate(top3, 1)
                    )

            return answer
            
        except Exception:
            # Fallback: return formatted results
            return self._format_search_results_list(query, all_results)

    def _format_search_results_list(self, query, results):
        """Format search results as a readable list."""
        if not results:
            return f"No relevant results found for: {query}"
        
        lines = [f"**Search Results for: {query}**\n"]
        
        by_type = {}
        for r in results:
            t = r.get('tool_type', 'info')
            by_type.setdefault(t, []).append(r)
        
        type_names = {
            'info': 'General Web',
            'news': 'News',
            'research': 'Research Papers',
            'image': 'Images',
            'video': 'Videos',
            'data': 'Datasets',
            'api': 'APIs',
            'shopping': 'Products',
        }
        
        for tool_type, items in by_type.items():
            type_label = type_names.get(tool_type, tool_type.title())
            lines.append(f"**{type_label}**:")
            for i, r in enumerate(items[:5], 1):
                lines.append(f"  {i}. {r.get('title', 'Link')[:100]}")
                lines.append(f"     {r.get('url', 'N/A')}")
                if r.get('snippet'):
                    lines.append(f"     {r['snippet'][:150]}...")
            lines.append("")
        
        return "\n".join(lines)

    def _execute_multi_tool_search(self, query, tool_types=None, max_iterations=3):
        """Execute search across multiple tool types with iterative refinement."""
        if tool_types is None:
            tool_types = self._classify_search_intent(query)
        
        results_by_type = {}
        iterations = 0
        
        for iteration in range(min(max_iterations, self.search_max_iterations)):
            iterations += 1
            for tool_type in tool_types:
                if not self.search_tool_types.get(tool_type, False):
                    continue
                
                # Build query variant for this iteration
                if iteration == 0:
                    q = query
                elif iteration == 1:
                    q = f"{query} detailed analysis"
                else:
                    q = f"{query} official source documentation"
                
                results = self._search_with_tool_type(q, tool_type, limit=5)
                
                if tool_type not in results_by_type:
                    results_by_type[tool_type] = []
                
                # Merge results, avoiding duplicates
                existing_urls = {r.get('url') for r in results_by_type[tool_type]}
                for r in results:
                    if r.get('url') not in existing_urls:
                        results_by_type[tool_type].append(r)
                        existing_urls.add(r.get('url'))
            
            # Check if we have enough results
            total_results = sum(len(v) for v in results_by_type.values())
            if total_results >= 10:
                break
        
        self.last_search_metadata['iterations'] = iterations
        
        return results_by_type

    def advanced_internet_search(self, query, auto_synthesize=True):
        """
        Advanced internet search with multiple tool types and intelligent routing.
        
        This implements the full pipeline:
        1. Query formulation and intent classification
        2. Multi-tool search invocation
        3. Information retrieval and deep browsing
        4. Result synthesis with source attribution
        
        Args:
            query: User's search query
            auto_synthesize: Whether to auto-synthesize results using AI
        
        Returns:
            Synthesized answer or formatted search results
        """
        # Resolve pronouns from conversation history
        resolved_query = self._resolve_pronouns_from_context(query)
        # Track last query so follow-ups like "check it yourself" can retry it
        self.last_live_web_query = resolved_query

        # Step 1: Classify search intent
        tool_types = self._classify_search_intent(resolved_query)
        
        # Step 2: Execute multi-tool search
        results_by_type = self._execute_multi_tool_search(
            resolved_query, 
            tool_types,
            max_iterations=self.search_max_iterations
        )
        
        # Step 3: Deep browse top results if enabled Ã¢Â€Â” fetch ALL in parallel
        if self.search_deep_browse:
            # Collect (result_dict, url) pairs that need deep browsing
            to_browse = []
            for tool_type, results in results_by_type.items():
                for r in results[:3]:
                    url = r.get('url', '')
                    # Skip if we already have good text content from the API
                    existing = (r.get('text') or r.get('snippet') or '').strip()
                    if url and self._is_fetch_allowed(url) and len(existing) < 200:
                        to_browse.append(r)

            def _deep_one(r):
                try:
                    return r, self._browse_url_deep(r.get('url', ''))
                except Exception:
                    return r, {}

            if to_browse:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    futs = {pool.submit(_deep_one, r): r for r in to_browse}
                    for fut in as_completed(futs, timeout=10):
                        try:
                            r, deep_content = fut.result(timeout=8)
                            if deep_content.get('text'):
                                r['text'] = deep_content['text'][:2000]
                            if deep_content.get('title'):
                                r['title'] = deep_content['title']
                        except Exception:
                            pass
        
        # Step 4: Synthesize or return formatted results
        if auto_synthesize:
            messages = []  # Context from conversation if available
            return self._synthesize_search_results(resolved_query, results_by_type, messages)
        else:
            all_results = []
            for tool_type, results in results_by_type.items():
                all_results.extend(results)
            return self._format_search_results_list(resolved_query, all_results)

    def _resolve_pronouns_from_context(self, query):
        """Resolve pronouns (he, she, it, they) to actual entities from conversation history."""
        if not self.conversation_history:
            return query
        
        # Check for pronouns
        pronouns = {
            'he': None, 'she': None, 'it': None, 'they': None,
            'him': None, 'her': None, 'his': None, 'their': None,
        }
        
        query_lower = query.lower()
        found_pronoun = None
        for pronoun in pronouns:
            if re.search(rf'\b{pronoun}\b', query_lower):
                found_pronoun = pronoun
                break
        
        if not found_pronoun:
            return query
        
        # Look in recent conversation for the subject
        _filter_words = {'the', 'and', 'but', 'for', 'with', 'have', 'has', 'was', 'were', 'been', 'being'}
        for item in reversed(self.conversation_history[-5:]):
            # Search original (non-lowercased) messages so capital-letter regex works
            user_msg = item.get('user', '')
            assistant_msg = item.get('assistant', '')

            # Extract person/entity names from previous messages
            # Look for proper nouns and names
            for msg in [user_msg, assistant_msg]:
                # Find capitalized words (potential names)
                names = re.findall(r'\b([A-Z][a-z]{2,15})\b', msg)
                # Filter common non-name words
                names = [n for n in names if n.lower() not in _filter_words]

                if names:
                    # Return the most likely subject
                    return query.replace(found_pronoun, names[0], 1).replace(found_pronoun.capitalize(), names[0], 1)
        
        return query

    def _needs_advanced_search(self, user_input):
        """Determine if query needs advanced internet search vs simple lookup."""
        t = (user_input or "").lower()

        if re.search(
            r"\b(explain|clarify|elaborate|what\s+(did|have)\s+you\s+(write|say|send)|"
            r"what\s+you\s+(wrote|said|sent)|that\s+answer|previous\s+(answer|reply|response)|"
            r"last\s+(answer|reply|response))\b",
            t,
            flags=re.IGNORECASE,
        ) and not re.search(r"\b(search|internet|web|online|sources?|latest|news|current)\b", t, flags=re.IGNORECASE):
            return False
        
        # Check for explicit search requests
        explicit_patterns = [
            r'\b(search|research|find|look up|investigate)\b.*\b(internet|web|online)\b',
            r'\b(show|give|bring)\b.*\b(sources|links|references|evidence)\b',
            r'\b(real[- ]?time|live|current|latest|breaking)\b',
            r'\b(verify|fact[- ]?check|validate|confirm)\b',
        ]
        
        if any(re.search(p, t, flags=re.IGNORECASE) for p in explicit_patterns):
            return True
        
        # Check for topic complexity
        if len(t.split()) >= 6 and any(re.search(p, t) for p in [
            r'\b(explain|analyze|compare|evaluate)\b',
            r'\b(what|who|when|where|why|how)\b',
        ]):
            return True
        
        return False

    def _determine_search_or_internal(self, user_input):
        """
        Intelligent decision system: Internal Knowledge vs Internet Search.
        
        Returns:
            tuple: (use_internet: bool, confidence: float, reason: str, search_type: str)
        """
        t = (user_input or "").lower()
        
        # ===== PHASE 1: ALWAYS INTERNAL - No search needed =====
        
        # Greetings and small talk
        if self._is_smalltalk_query(t):
            return False, 0.95, "smalltalk", "none"
        
        # Questions ABOUT the AI itself Ã¢Â€Â” answer from self-knowledge, never search internet
        ai_self_patterns = [
            r'\b(what (llm|model|ai|gpt|gemini|qwen)|which (model|ai)|what (kind|type) of (ai|model|assistant))\b',
            r'\b(who (made|created|built|developed) you|your (creator|developer|company|maker))\b',
            r'\b(what are you|who are you|what do you do|tell me about yourself)\b',
            r'\b(your (name|version|capabilities|abilities|features|skills|tasks|functions|tech))\b',
            r'\b(what (can|could) you (do|help|perform|handle|assist))\b',
            r'\b(what (tasks?|things?|features?|tech|automation|tools?|commands?) (can you|do you|are you able|you can|you support|you have))\b',
            r'\bpÃƒÂ©ar\b',
            r'\bopuntia\b',  # Any question mentioning Opuntia by name is about THIS assistant
            r'\b(about you|about yourself|your main|your purpose|your role)\b',
            r'\b(how (do|does|did) you work|how you work|explain (how|the way) you work|how are you (built|made|designed|working))\b',
            r'\b(explain (yourself|to me how you|your (working|function|system|design)))\b',
            r'\b(what (task|tasks|thing|things|area|areas|stuff) (are|is|r) you (good|best|special|great|expert|skilled) (at|with|in|for))\b',
            r'\b(what (are|r) you (good|best|special|great|expert|skilled) (at|with|in|for))\b',
            r'\b(what you (are|r).{0,10}(good|best|special|great|expert|skilled) (at|with|in|for))\b',
            r'\b(what (do|can) you (speciali[sz]e|excel|focus|handle|perform|help) (in|at|with|on))\b',
            r'\b(your (specialty|specialt|strengths?|expertise|strong points?|best (at|for)))\b',
            r'\b(what (tasks?|things?|stuff) (you are|you.?re|you can be) (special|good|great|best|expert) (with|at|in|for))\b',
        ]
        if any(re.search(p, t) for p in ai_self_patterns):
            return False, 0.90, "ai_self_reference", "none"

        # Questions about the current conversation Ã¢Â€Â” use conversation history, never search
        conversation_self_patterns = [
            r'\b(this conversation|our conversation|what (we|i) (said|talked|discussed|asked|mentioned))\b',
            r'\b(what did (we|i|you) (talk|say|discuss|ask|mention))\b',
            r'\b(from (this|our|the) conversation|in (this|our) chat|based on (what|what we))\b',
            r'\b(understand from|remember from|recall from|see in) (this|our|the) (conversation|chat|chat history)\b',
            r'\b(what (are|do) you (understand|get|see|read) from (this|our))\b',
            r'\b(summarize (this|our) (conversation|chat)|summary of (this|our))\b',
        ]
        if any(re.search(p, t) for p in conversation_self_patterns):
            return False, 0.95, "conversation_context", "none"

        # System commands Ã¢Â€Â” only block if it's clearly a desktop action, not an information question
        system_action_patterns = [
            r'\b(open|close|launch|run|quit|exit|stop|start)\s+(the\s+)?(app|application|program|file|folder|window|chrome|firefox|notepad|explorer|task\s*manager)\b',
            r'\b(take\s+a?\s*screenshot|capture\s+(screen|display))\b',
            r'\b(set\s+brightness|change\s+volume|turn\s+(on|off)\s+(wifi|bluetooth))\b',
            # Word/document creation - never web-search these
            r'\b(creat\w*|make|write|save|put)\b.{0,40}\b(word\s+doc\w*|\.docx?|word\s+file|document)\b',
            r'\b(word\s+doc\w*|\.docx?)\b.{0,30}\b(named?|called|titled?)\b',
            r'\b(creat\w*|make|write|save|put)\b.{0,60}\bpdf\b',
            r'\bpdf\b.{0,30}\b(named?|called|titled?)\b',
            r'\b(pdf\s+doc\w*|\.pdf)\b.{0,30}\b(named?|called|titled?)\b',
            # File/folder creation on desktop
            r'\b(creat\w*|make|new)\b.{0,30}\b(file|folder|directory)\b.{0,30}\b(desktop|named?|called)\b',
            # "write what you sent/have sent last" - always local
            r'\bwrite\b.{0,30}\b(last|previous)\b',
            r'\bwrite\b.{0,10}what\s+(?:(?:you|u)(?:\'?ve)?\s+(?:have\s+)?|(?:have|had)\s+(?:you|u)\s+)(?:just\s+)?(?:sent|said|wrote|written)\b',
            r'\b(inside|in|as|into)\s+(?:a\s+)?pdf\b',
            r'\bpdf\b.{0,40}\b(desktop|named?|called)\b',
        ]
        if any(re.search(p, t) for p in system_action_patterns):
            return False, 0.90, "system_command", "none"
        
        # ===== PHASE 2: Check for REAL need for internet =====
        
        has_temporal_marker = any(re.search(p, t) for p in [
            r'\b(today|yesterday|this week|now|current|latest|breaking|live|recent)\b',
            r'\b(202[4-9]|203[0-9])\b',
        ])
        
        # Time-sensitive topics (REAL-TIME needed)
        # Note: use independent checks so word order doesn't matter ("current price" OR "price current")
        def _has_all(*pats):
            return all(re.search(p, t) for p in pats)

        if re.search(r'\b(news|headlines|breaking|updates)\b', t):
            return True, 0.95, "time_sensitive", "realtime"
        if re.search(r'\b(weather|forecast|temperature)\b', t):
            return True, 0.95, "time_sensitive", "realtime"
        if _has_all(r'\b(stock|crypto|bitcoin|price|market|share)\b', r'\b(now|today|current|live|latest)\b'):
            return True, 0.95, "time_sensitive", "realtime"
        # "current/live/latest price of X" Ã¢Â€Â” works regardless of word order
        if _has_all(r'\b(price|cost|rate|value)\b', r'\b(current|now|today|live|latest)\b'):
            return True, 0.95, "time_sensitive", "realtime"
        if _has_all(r'\b(score|result|game|match)\b', r'\b(live|today|yesterday|current)\b'):
            return True, 0.95, "time_sensitive", "realtime"

        # Volatile information Ã¢Â€Â” any mention of price/availability without time marker still needs web
        volatile_patterns = [
            (r'\b(stock price|share price|crypto price|bitcoin price|ethereum price)\b', "lookup"),
            (r'\b(availability|status|open|closed)\b', "lookup"),
            (r'\b(how much (does|is|are|cost)|what (does|is) .{1,25} (cost|price|worth))\b', "lookup"),
        ]
        for pattern, search_type in volatile_patterns:
            if re.search(pattern, t):
                return True, 0.85, "volatile_info", search_type

        # Product/service info: pricing plans, subscriptions, features, versions
        # These change often and internal knowledge is unreliable
        product_patterns = [
            r'\b(plan|plans|pricing|subscription|tier|tiers)\b',
            r'\b(how much (does|is|are)|what (does|is) .{2,30} cost)\b',
            r'\b(free plan|pro plan|enterprise|business plan)\b',
        ]
        if any(re.search(p, t) for p in product_patterns):
            return True, 0.85, "product_info", "lookup"

        # Explicit search requests
        if self._needs_advanced_search(user_input):
            return True, 0.90, "explicit_request", "comprehensive"

        # Sports, competitions, tournaments Ã¢Â€Â” always need internet (results change every week)
        sports_patterns = [
            r'\b(who|which)\b.{0,40}\b(won|win|winner|champion|champions|beat|defeated|title|trophy|cup|league|tournament|championship)\b',
            r'\b(last|latest|recent|current|2024|2025|2026)\b.{0,40}\b(champion|winner|winners|champions|ucl|nba|nfl|premier league|la liga|serie a|bundesliga|ligue 1|world cup|euros|nhl|mlb)\b',
            r'\b(ucl|champions league|europa league|premier league|la liga|serie a|bundesliga|world cup|euro|copa|superbowl|super bowl|nba finals|stanley cup)\b',
            r'\b(score|scores|result|results|standings|table|ranking|fixtures|transfer|transfers|signing)\b',
            r'\b(who (is|was) (playing|leading|managing|coaching))\b',
        ]
        if any(re.search(p, t) for p in sports_patterns):
            return True, 0.92, "sports_realtime", "realtime"

        # People, celebrities, public figures â€” ALWAYS search internet.
        # Even if training data has info, internet may have more current/accurate data.
        person_patterns = [
            r'\b(how old is|age of|born in|birthday of|net worth of|salary of)\b',
            r'\b(who is|who was|who are)\b',
            r'\b(tell me about|info about|information about|facts about)\b',
            r'\b(what (happened|did).{0,30}(do|say|announce|release|launch))\b',
            r'\b(more (info|information|details?)|tell me more|expand (on|that)|elaborate|not enough)\b',
        ]
        if any(re.search(p, t) for p in person_patterns):
            return True, 0.88, "people_facts", "lookup"

        # Comparison / difference queries â€” always search
        if re.search(
            r'\b(diffr?e?r?e?n[cs]e?s?|compar\w*|versus|vs\.?|contrast|similarities|pros\s+and\s+cons)\b',
            t, re.IGNORECASE
        ):
            return True, 0.88, "comparison_lookup", "lookup"

        # Any question that contains what looks like a proper name (2+ capitalized words)
        # that isn't a common word â€” search internet
        proper_names = re.findall(r'\b[A-Z][a-z]{2,}\b', user_input)
        common_words = {
            'The', 'What', 'Who', 'How', 'When', 'Where', 'Why', 'Is', 'Are', 'Was',
            'Were', 'Can', 'Could', 'Please', 'Tell', 'Show', 'Find', 'Give', 'Get',
            'My', 'Your', 'His', 'Her', 'Its', 'Our', 'Their', 'This', 'That', 'These',
        }
        real_names = [n for n in proper_names if n not in common_words]
        if len(real_names) >= 1 and re.search(
            r'\b(who|what|whats?|tell|about|is|was|are|give|show|explain|describe|compare|differ|between|versus|diffr?e?r?e?nce?)\b',
            t
        ):
            return True, 0.85, "entity_lookup", "lookup"

        # ===== PHASE 3: Default to INTERNAL knowledge =====

        # General knowledge questions Ã¢Â€Â” search if temporal marker present, else use training data
        general_patterns = [
            r'\b(what (is|are)|when|where|why|how)\b',
            r'\b(explain|define|describe)\b',
            r'\b(history|historical|science|math|physics|chemistry|biology)\b',
        ]

        if any(re.search(p, t) for p in general_patterns):
            if has_temporal_marker:
                return True, 0.75, "temporal_relevance", "lookup"
            else:
                return False, 0.80, "general_knowledge", "none"

        # Default: Use internal knowledge
        return False, 0.75, "general_knowledge", "none"

    def intelligent_respond(self, user_input, messages=None, has_live_screen=False):
        """
        Main entry point for intelligent response with hybrid knowledge system.
        Accepts an optional pre-built messages list with full context (history,
        facts, screen context, etc.) from process_command.
        When has_live_screen=True, skips internet routing and answers from the
        pre-built messages which already contain the live screen context.
        """
        # When live screen is active, ALWAYS use the pre-built context Ã¢Â€Â” never search the internet
        if has_live_screen and messages is not None:
            try:
                return self._call_ai(messages)
            except Exception:
                return "I encountered an error processing your request."

        # Step 1: Analyze and route
        use_internet, confidence, reason, search_type = self._determine_search_or_internal(user_input)
        _messages = messages if isinstance(messages, list) else []
        _followup_locked = any(
            isinstance(m, dict) and m.get("role") == "system" and ("FOLLOW-UP ALERT" in str(m.get("content") or ""))
            for m in _messages
        ) or bool(
            re.search(
                r"\b(explain|clarify|elaborate|what\s+(did|have)\s+you\s+(write|say|send)|"
                r"what\s+you\s+(wrote|said|sent)|that\s+answer|previous\s+(answer|reply|response)|"
                r"last\s+(answer|reply|response))\b",
                str(user_input or ""),
                flags=re.IGNORECASE,
            )
        )
        _anchor_locked = bool(self._topic_anchor_hint(user_input))
        _explicit_web = bool(
            re.search(r"\b(search|internet|web|online|sources?|latest|news|current)\b", str(user_input or ""), flags=re.IGNORECASE)
        )
        if (_followup_locked or _anchor_locked) and not _explicit_web:
            use_internet = False
            reason = "followup_context"
            search_type = "none"

        # Step 2: Override with explicit user request Ã¢Â€Â” but never override self-reference or smalltalk
        if reason not in ("ai_self_reference", "smalltalk", "followup_context") and self._needs_advanced_search(user_input):
            use_internet = True
            confidence = 0.90
            search_type = "comprehensive"

        # Step 3: Execute based on search type
        if use_internet:
            if search_type in ["realtime", "lookup", "verify", "comprehensive"]:
                try:
                    result = self.advanced_internet_search(user_input, auto_synthesize=True)
                    return result
                except Exception:
                    use_internet = False
            else:
                try:
                    return self._answer_from_live_web(user_input)
                except Exception:
                    use_internet = False

        # Step 4: Use internal knowledge with full context
        if messages is None:
            messages = self._build_standard_messages(user_input)
        try:
            _internal_answer = self._call_ai(messages)
        except Exception:
            return "I encountered an error processing your request."

        # Step 5: Uncertain-answer retry â€” if the LLM answered with hedged/unknown language,
        # it means it didn't know the topic. Automatically retry with web search.
        _uncertainty_phrases = [
            "not a well-known", "not widely recognized", "without specific information",
            "without clear information", "cannot be directly compared",
            "unclear", "further research", "no information about",
            "limited information", "not enough information", "hypothetical",
            "doesn't exist", "does not exist", "no record of", "cannot find",
            "I don't have", "I do not have", "unknown entity", "not familiar with",
            "existence and development status are unclear",
        ]
        _ans_lower = _internal_answer.lower()
        if (not _followup_locked) and (not _anchor_locked) and any(ph.lower() in _ans_lower for ph in _uncertainty_phrases):
            try:
                _web_result = self.advanced_internet_search(user_input, auto_synthesize=True)
                if _web_result and len(_web_result.strip()) > 80:
                    return _web_result
            except Exception:
                pass
        return _internal_answer

    def _build_standard_messages(self, user_input):
        """Fallback message builder used when no pre-built context is available."""
        now = datetime.now().strftime("%A, %B %d, %Y at %H:%M:%S")
        msgs = [
            {
                "role": "system",
                "content": (
                    f"You are Opuntia, a smart Windows desktop AI assistant created by the Opuntia Team.\n"
                    f"Current date and time: {now}.\n\n"
                    "Opuntia's capabilities: desktop automation, app management, real-time web search, URL browsing, weather, file/folder management, screen capture & vision, voice input, conversation memory, skills system, system controls (volume/brightness/WiFi/Bluetooth).\n\n"
                    "## Response format & style\n"
                    "**Structure every answer like this:**\n"
                    "- **Direct answer first** Ã¢Â€Â” open with the key fact or result, no preamble.\n"
                    "- **Headings** (##) for multi-section answers; skip for short factual replies.\n"
                    "- **Bullet points** for lists of 3+ items; **tables** when comparing options.\n"
                    "- **Bold** key facts, names, numbers, and important terms.\n"
                    "- Logical flow: definition ? explanation ? examples/implications.\n"
                    "- **Adapt depth**: short query = concise direct answer; complex query = structured breakdown with sections.\n"
                    "- **No filler** Ã¢Â€Â” never start with 'Great question!', 'Certainly!', 'Of course!', or 'Based on the information provided'.\n"
                    "- Cite web sources inline as [1][2] when live results are in context.\n"
                    "- NEVER say you cannot search the internet. NEVER say 'shutting down' unless asked to close.\n"
                    "- When asked about your own features or capabilities, answer from your built-in knowledge above Ã¢Â€Â” do NOT search the internet."
                ),
            }
        ]
        _mode = getattr(self, "input_mode", "chat")
        _hist = self.task_conversation_history if _mode == "task" else self.conversation_history
        recent = list(_hist[-5:])
        if not recent and self.conversation_history:
            recent = self.conversation_history[-5:]
        if recent:
            ctx = self._format_memory_context(recent)
            if ctx:
                msgs.append({"role": "system", "content": "Recent conversation:\n" + ctx})
        elif (self.last_user_message or self.last_assistant_message):
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "Recent turn fallback:\n"
                        f"User: {self.last_user_message[:500]}\n"
                        f"Assistant: {self.last_assistant_message[:900]}"
                    ),
                }
            )
        recap_ctx = self._build_session_recap_context(user_input, limit=1)
        if recap_ctx:
            msgs.append({"role": "system", "content": recap_ctx[:700]})
        traj_ctx = self._build_trajectory_context(user_input, limit=1)
        if traj_ctx:
            msgs.append({"role": "system", "content": traj_ctx[:750]})
        anchor_hint = self._topic_anchor_hint(user_input)
        if anchor_hint:
            msgs.append({"role": "system", "content": anchor_hint})
        msgs.append({"role": "user", "content": user_input})
        return msgs

    def get_search_metadata(self):
        """Get metadata about the last search operation."""
        return dict(self.last_search_metadata)

    def clear_search_cache(self):
        """Clear search-related caches."""
        self._web_search_cache.clear()
        self.last_search_metadata = {
            'sources_used': [],
            'search_type': 'none',
            'confidence': 0.0,
            'timestamp': None,
            'query': '',
            'iterations': 0,
        }

    # =========================================================================
    # END ADVANCED INTERNET BROWSING & SEARCH TOOLS
    # =========================================================================

    def _extract_top_n(self, text, default=10, min_value=1, max_value=25):
        m = re.search(r"\btop\s+(\d{1,2})\b", (text or ""), flags=re.IGNORECASE)
        if not m:
            m = re.search(r"\b(\d{1,2})\s+(?:crypto|cryptos|coins?)\b", (text or ""), flags=re.IGNORECASE)
        if not m:
            return max(min_value, min(max_value, int(default)))
        return max(min_value, min(max_value, int(m.group(1))))

    def _get_top_crypto_prices(self, limit=10, currency="usd"):
        n = max(1, min(25, int(limit)))
        vs = (currency or "usd").strip().lower()
        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency={quote_plus(vs)}&order=market_cap_desc&per_page={n}&page=1&sparkline=false&price_change_percentage=24h"
        )
        try:
            r = requests.get(url, timeout=12)
            if r.status_code >= 400:
                self.last_structured_intent = ""
                self.last_structured_payload = {}
                return f"Could not fetch crypto prices right now (HTTP {r.status_code})."
            data = r.json() if "application/json" in (r.headers.get("Content-Type", "")) else []
            if not isinstance(data, list) or not data:
                self.last_structured_intent = ""
                self.last_structured_payload = {}
                return "Could not fetch crypto prices right now."
            now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            lines = [f"Top {n} crypto prices now ({vs.upper()}) - {now_ts}:"]
            for idx, item in enumerate(data[:n], start=1):
                name = (item.get("name") or item.get("symbol") or "Unknown").strip()
                symbol = (item.get("symbol") or "").upper()
                price = item.get("current_price")
                chg = item.get("price_change_percentage_24h")
                price_txt = f"{price}" if isinstance(price, (int, float)) else "N/A"
                if isinstance(price, (int, float)):
                    price_txt = f"{price:,.8f}".rstrip("0").rstrip(".")
                chg_txt = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "N/A"
                label = f"{name} ({symbol})" if symbol else name
                lines.append(f"{idx}. {label}: {price_txt} {vs.upper()} (24h {chg_txt})")
            lines.append(f"Source: {url}")
            self.last_structured_intent = "crypto_prices"
            self.last_structured_payload = {"limit": n, "currency": vs}
            return "\n".join(lines)
        except Exception as e:
            self.last_structured_intent = ""
            self.last_structured_payload = {}
            return f"Could not fetch crypto prices: {e}"

    def _extract_news_topic(self, text):
        t = (text or "").strip()
        if not t:
            return ""
        low = t.lower()
        if not re.search(r"\b(news|new|headlines?|updates?)\b", low):
            return ""
        cleaned = re.sub(
            r"^(?:please\s+)?(?:give|bring|show|find|search|tell me|i want|i need|can you|are you able to)\s+",
            "",
            t,
            flags=re.IGNORECASE,
        ).strip(" ,.?")
        cleaned = re.sub(r"^(?:can|could|would)\s+you\s+", "", cleaned, flags=re.IGNORECASE).strip(" ,.?")
        cleaned = re.sub(r"^(?:search|research|look up|find)\s+(?:for\s+me\s+)?", "", cleaned, flags=re.IGNORECASE).strip(" ,.?")
        cleaned = re.sub(r"\b(?:latest|last|today|current|from)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:internet|web|online)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(news|new|headlines?|updates?)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:can|you|your|for|me|about|main|the|of)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.?")
        # Guard against malformed residuals like "can your search ...".
        if len(cleaned.split()) <= 2:
            return ""
        return cleaned

    def _get_latest_news(self, user_input, limit=6):
        topic = self._extract_news_topic(user_input)
        n = max(3, min(12, int(limit)))
        if topic:
            feed_url = (
                "https://news.google.com/rss/search"
                f"?q={quote_plus(topic)}&hl=en-US&gl=US&ceid=US:en"
            )
            title = f"Latest news about {topic}:"
        else:
            feed_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
            title = "Latest top news:"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
            )
        }
        try:
            r = requests.get(feed_url, headers=headers, timeout=12)
            if r.status_code >= 400:
                return f"Could not fetch latest news right now (HTTP {r.status_code})."
            body = r.text or ""
            items = re.findall(r"(?is)<item>(.*?)</item>", body)
            rows = []
            for item in items:
                t_m = re.search(r"(?is)<title>(.*?)</title>", item)
                l_m = re.search(r"(?is)<link>(.*?)</link>", item)
                p_m = re.search(r"(?is)<pubDate>(.*?)</pubDate>", item)
                if not t_m or not l_m:
                    continue
                t = self._strip_html_tags(t_m.group(1))
                l = html.unescape((l_m.group(1) or "").strip())
                p = self._strip_html_tags(p_m.group(1) if p_m else "")
                if t and l:
                    rows.append((t[:180], l, p))
                if len(rows) >= n:
                    break
            if not rows:
                return "Could not fetch latest news right now."
            lines = [title]
            for i, (t, l, p) in enumerate(rows, start=1):
                lines.append(f"{i}. {t}")
                if p:
                    lines.append(f"   {p}")
                lines.append(f"   {l}")
            lines.append(f"Source feed: {feed_url}")
            self.last_live_web_query = f"latest news {topic}".strip()
            self.last_structured_intent = "news"
            self.last_structured_payload = {"topic": topic, "limit": n}
            return "\n".join(lines)
        except Exception as e:
            return f"Could not fetch latest news: {e}"

    def _clean_path_input(self, raw_path):
        return (raw_path or "").strip().strip("`\"' ")

    def _resolve_workspace_path(self, raw_path, allow_desktop=False):
        path_text = self._clean_path_input(raw_path)
        if not path_text:
            return None, "Please provide a file path."
        candidate = path_text.replace("/", os.sep)
        if not os.path.isabs(candidate):
            candidate = os.path.join(self.workspace_root, candidate)
        resolved = os.path.abspath(candidate)
        resolved_real = os.path.realpath(resolved)
        allowed = [self.workspace_root]
        if allow_desktop:
            allowed.append(self.desktop_root)
        resolved_cmp = os.path.normcase(resolved_real)
        ok = False
        for root in allowed:
            root_cmp = os.path.normcase(os.path.realpath(root))
            if resolved_cmp == root_cmp or resolved_cmp.startswith(root_cmp + os.sep):
                ok = True
                break
        if not ok:
            self._audit(
                "path_sandbox",
                "blocked",
                {"raw": raw_path, "resolved": resolved_real, "allow_desktop": bool(allow_desktop)},
            )
            if allow_desktop:
                return None, "For safety, operations are limited to project folder and Desktop."
            return None, "For safety, operations are limited to the project folder."
        return resolved_real, None

    def _write_text_file(self, path, content, append=False):
        try:
            os.makedirs(os.path.dirname(path) or self.workspace_root, exist_ok=True)
            # Normalise \n escape sequences the user may type literally
            decoded = content.replace("\\n", "\n").replace("\\t", "\t") if content else ""
            with open(path, "a" if append else "w", encoding="utf-8") as f:
                f.write(decoded)
            fname = os.path.basename(path)
            location = "Desktop" if os.path.normcase(os.path.dirname(path)) == os.path.normcase(self.desktop_root) else os.path.dirname(path)
            word_count = len(decoded.split()) if decoded.strip() else 0
            detail = f" ({word_count} words)" if word_count else ""
            action = "Updated file" if append else "Saved file"
            return (
                f"**{action}** `{fname}` on {location}{detail}.\n"
                f"Say **\"open {fname}\"** if you want to view it."
            )
        except Exception as e:
            return f"Could not write file: {e}"

    # ------------------------------------------------------------------
    # Complex multi-step folder/file tree creation
    # ------------------------------------------------------------------
    def _is_complex_creation_cmd(self, text):
        """Return True if the command describes a multi-step nested create operation."""
        low = (text or "").lower()
        if not re.search(r"\b(create|make)\b", low):
            return False
        if re.search(r"\b(inside|in each|in every|in all)\b", low):
            return True
        if len(re.findall(r"\b(create|make)\b", low)) >= 2:
            return True
        if re.search(r"\bcreate\s+\d+\s+(folders?|files?|sub-?folders?)\b", low):
            return True
        return False

    def _parse_file_tree_with_ai(self, user_input, base_path):
        """Ask AI to convert a natural-language tree description into a JSON operations list."""
        parse_prompt = (
            f"Convert this request into a JSON array of file/folder operations.\n"
            f"Base directory (root): {base_path}\n"
            f"Request: {user_input}\n\n"
            "Return ONLY a valid JSON array, no explanation, no markdown fences.\n"
            "Each element must be exactly one of:\n"
            '  {"type":"create_folder","path":"<absolute_windows_path>"}\n'
            '  {"type":"create_file","path":"<absolute_windows_path>","content":"<text or empty>"}\n\n'
            "Rules:\n"
            "- Use the base directory as root unless the user explicitly says 'desktop'.\n"
            "- 'inside [folder]' means place items directly inside that folder.\n"
            "- 'in each' / 'in every folder' means repeat the sub-operation for every sibling folder just created.\n"
            "- 'create N folders named A, B, C' means N separate create_folder entries.\n"
            "- Auto-add .txt extension to files that have no extension.\n"
            "- Use Windows backslash paths.\n"
            "- Preserve file content exactly as the user wrote it.\n"
            "- Output ONLY the JSON array, nothing else."
        )
        try:
            messages = [{"role": "user", "content": parse_prompt}]
            raw = self._call_ai(messages)
            m = re.search(r"\[[\s\S]*\]", raw)
            if not m:
                return None
            ops = json.loads(m.group(0))
            if not isinstance(ops, list):
                return None
            return ops
        except Exception:
            return None

    def _execute_file_tree(self, operations, allow_desktop=False):
        """Execute a list of create_folder / create_file operations safely."""
        allowed_roots = [os.path.normcase(os.path.realpath(self.workspace_root))]
        if allow_desktop:
            allowed_roots.append(os.path.normcase(os.path.realpath(self.desktop_root)))

        results = []
        for op in (operations or []):
            op_type = (op.get("type") or "").strip()
            raw_path = (op.get("path") or "").strip()
            content = op.get("content") or ""
            if not raw_path or op_type not in ("create_folder", "create_file"):
                continue
            abs_path = os.path.normcase(os.path.realpath(os.path.abspath(raw_path)))
            if not any(abs_path == r or abs_path.startswith(r + os.sep) for r in allowed_roots):
                results.append(f"Blocked (outside workspace): {os.path.basename(raw_path)}")
                continue
            real_path = os.path.abspath(raw_path)
            try:
                if op_type == "create_folder":
                    os.makedirs(real_path, exist_ok=True)
                    results.append(f"[folder] {os.path.basename(real_path)}")
                elif op_type == "create_file":
                    os.makedirs(os.path.dirname(real_path) or self.workspace_root, exist_ok=True)
                    decoded = content.replace("\\n", "\n").replace("\\t", "\t")
                    with open(real_path, "w", encoding="utf-8") as f:
                        f.write(decoded)
                    results.append(f"[file]   {os.path.basename(real_path)}")
            except Exception as e:
                results.append(f"[error]  {os.path.basename(raw_path)}: {e}")
        return results

    def _handle_complex_creation_command(self, user_input, allow_desktop=False, allow_mutation=False):
        """Entry point for multi-step nested folder/file tree creation from a single prompt."""
        if not self._is_complex_creation_cmd(user_input):
            return None

        base_path = self.desktop_root if allow_desktop else self.workspace_root

        if not allow_mutation:
            ops = self._parse_file_tree_with_ai(user_input, base_path)
            if not ops:
                return None
            folders = [o for o in ops if o.get("type") == "create_folder"]
            files   = [o for o in ops if o.get("type") == "create_file"]
            parts = []
            if folders:
                names = ", ".join(os.path.basename(o["path"]) for o in folders[:6])
                parts.append(f"{len(folders)} folder(s): {names}")
            if files:
                names = ", ".join(os.path.basename(o["path"]) for o in files[:6])
                parts.append(f"{len(files)} file(s): {names}")
            summary = " + ".join(parts) or "items"
            self._audit("file_mutation", "permission_requested", {"command": user_input[:300]})
            return self._set_pending_confirmation(
                "file_tree_creation",
                {"operations": ops, "allow_desktop": allow_desktop},
                f"I'll create {summary}. Confirm?",
            )

        # Already authorized Ã¢Â€Â” parse and execute
        ops = self._parse_file_tree_with_ai(user_input, base_path)
        if not ops:
            return None
        results = self._execute_file_tree(ops, allow_desktop=allow_desktop)
        if not results:
            return None
        return "Done! Created:\n" + "\n".join(f"  {r}" for r in results)

    # -------------------------------------------------------------------------
    # PDF Document Engine
    # -------------------------------------------------------------------------

    def _make_chart_png(self, headers, rows, title='', width_in=6.2, height_in=3.6):
        """
        Generate a professional bar / grouped-bar / pie chart from table data.
        headers : list of column-name strings
        rows    : list of lists of strings (data rows only, no header row)
        Returns PNG bytes, or None if matplotlib is unavailable or the table
        has no numeric data worth charting.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker
            import io as _io
        except ImportError:
            return None

        if not headers or len(rows) < 2:
            return None

        def _to_num(v):
            try:
                return float(str(v).replace(',', '').replace('%', '')
                             .replace('$', '').replace('â‚¬', '').strip())
            except Exception:
                return None

        ncols = max(len(r) for r in rows)

        # Identify numeric columns
        num_cols = []
        for ci in range(ncols):
            vals = [_to_num(rows[ri][ci] if ci < len(rows[ri]) else '') for ri in range(len(rows))]
            num_vals = [v for v in vals if v is not None]
            if len(num_vals) >= max(1, len(rows) * 0.5):
                num_cols.append(ci)

        if not num_cols:
            return None

        # Label column = first non-numeric column (usually column 0)
        label_col = next((ci for ci in range(ncols) if ci not in num_cols), None)
        if label_col is not None:
            raw_labels = [str(rows[ri][label_col]).strip() if label_col < len(rows[ri]) else '' for ri in range(len(rows))]
        else:
            raw_labels = [str(ri + 1) for ri in range(len(rows))]

        MAX_LBL = 16
        labels = [l[:MAX_LBL] + 'â€¦' if len(l) > MAX_LBL else l for l in raw_labels]

        # Professional colour palette
        BLUE   = ['#2563EB', '#1B2B4B', '#60A5FA', '#3B82F6', '#93C5FD', '#1D4ED8', '#BFDBFE']
        ACCENT = '#2563EB'

        def _style_ax(ax, fig):
            ax.set_facecolor('#F8FAFC')
            fig.patch.set_facecolor('white')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#CBD5E1')
            ax.spines['bottom'].set_color('#CBD5E1')
            ax.yaxis.grid(True, linestyle='--', alpha=0.55, color='#E2E8F0', zorder=0)
            ax.set_axisbelow(True)
            ax.tick_params(colors='#475569', labelsize=8)

        try:
            if len(num_cols) == 1:
                ci = num_cols[0]
                col_name = headers[ci] if ci < len(headers) else ''
                values = [(_to_num(rows[ri][ci] if ci < len(rows[ri]) else '') or 0) for ri in range(len(rows))]

                is_pct = (
                    all(0 <= v <= 100 for v in values)
                    and 80 <= sum(values) <= 120
                    and len(values) >= 3
                )

                fig, ax = plt.subplots(figsize=(width_in, height_in))
                _style_ax(ax, fig)

                if is_pct:
                    colors = BLUE[:len(labels)]
                    wedges, texts, autotexts = ax.pie(
                        values, labels=labels, colors=colors,
                        autopct='%1.1f%%', startangle=90,
                        wedgeprops={'linewidth': 1.2, 'edgecolor': 'white'},
                        textprops={'fontsize': 8},
                        pctdistance=0.78,
                    )
                    for at in autotexts:
                        at.set_fontsize(7.5)
                        at.set_fontweight('bold')
                        at.set_color('white')
                    ax.set_facecolor('white')
                else:
                    bar_colors = [BLUE[j % len(BLUE)] for j in range(len(labels))]
                    bars = ax.bar(range(len(labels)), values, color=bar_colors,
                                  width=0.55, edgecolor='white', linewidth=0.5, zorder=3)
                    ax.set_xticks(range(len(labels)))
                    max_lbl_len = max((len(l) for l in labels), default=0)
                    ax.set_xticklabels(
                        labels,
                        rotation=30 if max_lbl_len > 10 else 0,
                        ha='right' if max_lbl_len > 10 else 'center',
                        fontsize=8,
                    )
                    ax.set_ylabel(col_name, fontsize=9, color='#475569')
                    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                        lambda x, _: f'{x:,.0f}' if x == int(x) else f'{x:.1f}'
                    ))
                    mx = max(values, default=1) or 1
                    for bar, val in zip(bars, values):
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + mx * 0.018,
                            f'{val:,.0f}' if val == int(val) else f'{val:.1f}',
                            ha='center', va='bottom', fontsize=7.5,
                            color='#1E3A5F', fontweight='bold',
                        )

            else:
                # Grouped bar chart for multiple numeric columns
                fig, ax = plt.subplots(figsize=(width_in, height_in))
                _style_ax(ax, fig)

                n_groups = len(num_cols)
                bar_w = min(0.65 / n_groups, 0.25)
                x = list(range(len(labels)))

                for gi, ci in enumerate(num_cols):
                    col_name = headers[ci] if ci < len(headers) else f'Series {gi+1}'
                    values = [(_to_num(rows[ri][ci] if ci < len(rows[ri]) else '') or 0) for ri in range(len(rows))]
                    offset = (gi - n_groups / 2 + 0.5) * bar_w
                    ax.bar(
                        [xv + offset for xv in x], values,
                        width=bar_w, color=BLUE[gi % len(BLUE)],
                        label=col_name, edgecolor='white', linewidth=0.4, zorder=3,
                    )

                ax.set_xticks(x)
                max_lbl_len = max((len(l) for l in labels), default=0)
                ax.set_xticklabels(
                    labels,
                    rotation=30 if max_lbl_len > 10 else 0,
                    ha='right' if max_lbl_len > 10 else 'center',
                    fontsize=8,
                )
                ax.legend(fontsize=8, framealpha=0.9, edgecolor='#CBD5E1')
                ax.yaxis.set_major_formatter(mticker.FuncFormatter(
                    lambda x, _: f'{x:,.0f}' if x == int(x) else f'{x:.1f}'
                ))

            if title:
                ax.set_title(title, fontsize=10.5, fontweight='bold',
                             color='#1B2B4B', pad=10)

            plt.tight_layout(pad=0.6)
            buf = _io.BytesIO()
            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            plt.close(fig)
            buf.seek(0)
            return buf.read()

        except Exception:
            try:
                plt.close('all')
            except Exception:
                pass
            return None

    def _generate_doc_title(self, content, fallback='Response'):
        """Derive a short, meaningful document title from content."""
        import re as _re
        if not content:
            return fallback
        text = content.strip()
        lines = text.split('\n')

        # 0. Keyword-based formal document type detection (French & English)
        #    Runs before word-counting so common pronouns ("Nous", "Je"â€¦) don't become titles.
        _tl = _re.sub(r'\s+', ' ', text.lower())
        if _re.search(r'\battestati[o0]n\s+de\s+prise\s+en\s+charge\b', _tl):
            return 'Attestation de Prise en Charge'
        if _re.search(r'\bprise\s+en\s+charge\b', _tl) and _re.search(r"s[''']engage|prendre\s+en\s+charge", _tl):
            return 'Attestation de Prise en Charge'
        if _re.search(r'\bordre\s+de\s+mission\b', _tl):
            return 'Ordre de Mission'
        if _re.search(r'\bmission\s+professionnelle\b', _tl) and _re.search(r'\bcertifi|mandat[eÃ©]|missionnaire\b', _tl):
            return 'Lettre de Mission'
        if _re.search(r'\bmission\s+professionnelle\b', _tl):
            return 'Lettre de Mission'
        if _re.search(r'\batteste\s+que\b', _tl) and not _re.search(r'\bmission\b', _tl):
            return 'Attestation'
        if _re.search(r'\bcertifions\s+que\b|\bnous\s+certifions\b', _tl):
            return 'Certification'
        if _re.search(r'\bcontrat\s+de\b', _tl):
            return 'Contrat'
        if _re.search(r'\bfacture\s+n[Â°o]|\binvoice\b', _tl):
            return 'Facture'

        # 1. Markdown heading in first 6 lines
        for line in lines[:6]:
            line = line.strip()
            m = _re.match(r'^#{1,3}\s+(.+)', line)
            if m:
                title = _re.sub(r'\*+([^*]+)\*+', r'\1', m.group(1)).strip(' #')
                if 3 < len(title) < 80:
                    return title[:70]
            m = _re.match(r'^\*{2}([^*]{3,60})\*{2}\s*$', line)
            if m:
                return m.group(1).strip()

        # 2. ALL-CAPS prefix (e.g. "ORDRE DE MISSION", "ATTESTATION", "CERTIFICATE")
        #    Grab consecutive words that are fully uppercase (ignoring punctuation/accents).
        #    Stop at the first word that is NOT all-uppercase.
        first_line = _re.sub(r'[*#_`\[\]>]', '', lines[0]).strip()
        if first_line:
            words = first_line.split()
            caps_words = []
            for w in words:
                # Strip punctuation around the word to check casing
                core = _re.sub(r'[^\w\u00C0-\u00DC]', '', w)
                if core and core == core.upper() and len(core) >= 1:
                    caps_words.append(w)
                else:
                    break
            if 1 <= len(caps_words) <= 7:
                title = ' '.join(caps_words).strip('.,;:â€“-')
                if len(title) > 2:
                    return title

        # Pronouns/articles/auxiliary verbs that are never document titles
        _BAD_STARTERS = {
            'je', 'nous', 'le', 'la', 'les', 'un', 'une', 'des', 'du',
            'the', 'this', 'that', 'it', 'i', 'we', 'a', 'an',
            'tu', 'il', 'elle', 'ils', 'elles', 'vous', 'on',
            'par', 'pour', 'dans', 'en', 'et', 'ou', 'de',
            # auxiliary verbs that slip through after skipping pronouns
            'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'can', 'could',
            'will', 'would', 'shall', 'should', 'may', 'might', 'must',
            'suis', 'es', 'sommes', 'Ãªtes', 'sont', 'Ã©tait', 'serait',
        }

        # 3. First short non-empty plain-text line (â‰¤ 70 chars, take first 6 words)
        #    Skip lines that start with a pronoun or article.
        for line in lines[:4]:
            plain = _re.sub(r'[*#_`\[\]>]', '', line).strip()
            plain = _re.sub(r'[^\x00-\x7F\u00C0-\u024F]+', '', plain).strip()
            if 5 < len(plain) < 70:
                first_word = plain.split()[0].strip('.,;:â€“-').lower() if plain.split() else ''
                if first_word in _BAD_STARTERS:
                    continue
                words = plain.split()[:6]
                title = ' '.join(words)
                if title:
                    return title

        # 4. First 5 meaningful words from content (skip pronoun starters)
        flat = _re.sub(r'[*#_`\[\]>]', '', text).strip()
        all_words = [w for w in flat.split() if len(w) > 1]
        # If first word is a bad starter, skip it and try next words for a meaningful title
        skip = 0
        while skip < min(4, len(all_words)) and all_words[skip].strip('.,;:â€“-').lower() in _BAD_STARTERS:
            skip += 1
        words = all_words[skip:skip + 5]
        candidate = ' '.join(words)
        if not candidate:
            return fallback
        return candidate if candidate else fallback

    def _analyze_and_structure_content(self, content):
        """
        Intelligently structure plain/unformatted content into markdown-ready text.
        Handles:
          - Formal legal documents (Ordre de Mission, Attestation, Letter, Certificate)
          - Business letters
          - Any flat prose with no markdown markers
        Returns the same content if it already has markdown structure.
        """
        import re as _r

        text = content.strip()
        if not text:
            return text

        # Arabic content â€” handled by dedicated Arabic renderer, don't touch
        if self._is_arabic_content(text):
            return text

        # Already has markdown structure â€” leave untouched
        if _r.search(r'^#{1,4} |^\*\* |^\* |^- |\|.+\|', text, _r.MULTILINE):
            return text

        # Already multi-line with proper paragraph breaks â€” just fix the title
        lines_raw = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines_raw) >= 4:
            # Multi-line content: check if first line is ALL-CAPS title
            first = lines_raw[0]
            words = first.split()
            caps = [w for w in words if _r.sub(r'[^\w\u00C0-\u00DC]', '', w) == _r.sub(r'[^\w\u00C0-\u00DC]', '', w).upper() and len(w) > 0]
            if len(caps) == len(words) and 1 <= len(words) <= 7:
                # Promote the title to a markdown H1
                rest = '\n\n'.join(lines_raw[1:])
                return f'# {first}\n\n{rest}'
            return text  # already structured enough

        # â”€â”€ FLAT TEXT: single paragraph or short text with no breaks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Step 1: Protect known abbreviations that contain periods
        #         so sentence splitting doesn't break them.
        ABBREV_MAP = {}
        _abbrev_counter = [0]

        def _protect(pattern, flags=0):
            for m in _r.finditer(pattern, text, flags):
                ph = f'\x02{_abbrev_counter[0]}\x03'
                ABBREV_MAP[ph] = m.group()
                _abbrev_counter[0] += 1
            return _r.sub(pattern, lambda m: [k for k, v in ABBREV_MAP.items() if v == m.group()][0] if [k for k, v in ABBREV_MAP.items() if v == m.group()] else m.group(), text, flags=flags)

        # Simpler: do replacement inline
        protected = text
        _abbrevs = [
            r'\bM\.\s+(?=[A-ZÀ-ÖØ-Þ])',      # M. <Name>
            r'\bMme\.\s+',
            r'\bMr\.\s+',
            r'\bMs\.\s+',
            r'\bDr\.\s+',
            r'\bProf\.\s+',
            r'\bNÂ°\s*\d',                  # NÂ°123
            r'\bnÂ°\s*\d',
            r'C\.I\.N\.\s+',
            r'\bSt\.\s+',
            r'\be\.g\.\s+',
            r'\bi\.e\.\s+',
            r'\betc\.\s+',
            r'\bvs\.\s+',
            r'\b[A-Z]\.[A-Z]\.\s+',        # initials like C.I.N.
        ]
        _ph_counter = [0]
        _ph_map = {}

        def _sub_abbrev(m):
            ph = f'\x02{_ph_counter[0]}\x03'
            _ph_map[ph] = m.group()
            _ph_counter[0] += 1
            return ph

        for pat in _abbrevs:
            protected = _r.sub(pat, _sub_abbrev, protected)

        # Step 2: Split into sentences at ". " / "! " / "? " before uppercase
        sentences = _r.split(r'(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ])', protected)

        # Also split at known paragraph-starting phrases mid-sentence (no period before them)
        PARA_STARTERS = [
            r'(Fait\s+[àa]\b)',
            r'(Signature\s+et\b)',
            r'(Done\s+at\b)',
            r'(Signed\s+at\b)',
            r'(Nous\s+confirmons?\b)',   # full word â€” avoid splitting "confirmons" mid-word
            r'(We\s+confirm\b)',
        ]
        expanded = []
        for sent in sentences:
            did_split = False
            for pat in PARA_STARTERS:
                parts = _r.split(pat, sent, maxsplit=1)
                if len(parts) >= 3:
                    before = parts[0].strip()
                    match_part = parts[1]
                    # Keep raw suffix (do NOT strip â€” stripping removes the space
                    # between the captured group and the next word, e.g. "Fait Ã " + " Nice")
                    after_raw = parts[2] if len(parts) > 2 else ''
                    after = after_raw.strip()
                    if before:
                        expanded.append(before)
                    # Re-add the space that was between match_part and after
                    expanded.append((match_part + ' ' + after).strip() if after else match_part)
                    did_split = True
                    break
            if not did_split:
                expanded.append(sent)
        sentences = [s.strip() for s in expanded if s.strip()]

        # Step 3: Restore abbreviations
        def _restore(s):
            for ph, orig in _ph_map.items():
                s = s.replace(ph, orig)
            return s

        sentences = [_restore(s) for s in sentences]

        # Step 4: Group sentences into logical paragraphs
        # Rules:
        #  - Sentence containing "certifions que" / "hereby certify" â†’ break AFTER it
        #  - Sentence starting with "La mission" â†’ its own paragraph
        #  - "Fait Ã " / closing phrase â†’ its own paragraph
        #  - "Signature" â†’ its own paragraph
        #  - Trailing name + role â†’ their own lines (bold name)
        paragraphs = []
        i = 0
        while i < len(sentences):
            s = sentences[i]
            sl = s.lower()

            # Closing phrase â€” standalone paragraph
            if _r.match(r'fait\s+[àa]\b|done\s+in\b|signed\s+at\b', sl):
                # Split "Signature et cachet" out if it's embedded in the same sentence
                _sig_m = _r.search(r'\s+(Signature\s+et\b)', s, _r.IGNORECASE)
                if _sig_m:
                    _closing_part = s[:_sig_m.start()].strip()
                    _sig_part = s[_sig_m.start():].strip()
                    if _closing_part:
                        paragraphs.append(('closing', _closing_part))
                    paragraphs.append(('signature', [_sig_part]))
                else:
                    paragraphs.append(('closing', s))
                i += 1
                continue

            # Signature block
            if _r.match(r'signature\s+|cachet\s+|stamp\s+', sl):
                # Collect rest as signature block
                sig_lines = [s]
                i += 1
                while i < len(sentences):
                    sig_lines.append(sentences[i])
                    i += 1
                paragraphs.append(('signature', sig_lines))
                continue

            # Group 2-3 related sentences unless next sentence starts a new section
            group = [s]
            i += 1
            while i < len(sentences) and len(group) < 3:
                ns = sentences[i]
                nsl = ns.lower()
                # Stop grouping if next sentence is a new section
                if _r.match(r'fait\s+[àa]\b|done\s+in\b|signature\s+et\b|nous\s+confirmons?\b|we\s+confirm\b', nsl):
                    break
                group.append(ns)
                i += 1

            paragraphs.append(('body', ' '.join(group)))

        # Step 5: Extract ALL-CAPS title from very first sentence/paragraph
        title_text = None
        first_body = ''
        if paragraphs and paragraphs[0][0] == 'body':
            first_text = paragraphs[0][1]
            words = first_text.split()
            caps_words = []
            for w in words:
                core = _r.sub(r'[^\w\u00C0-\u00DC]', '', w)
                if core and core == core.upper() and len(core) >= 2:
                    caps_words.append(w)
                else:
                    break
            if 1 <= len(caps_words) <= 7:
                title_text = ' '.join(caps_words).strip('.,;:â€“-')
                first_body = first_text[len(' '.join(caps_words)):].strip().lstrip('.,;:â€“ ')
                paragraphs[0] = ('body', first_body) if first_body else None

        # Step 6: Build structured output
        out_lines = []
        if title_text:
            out_lines.append(f'# {title_text}')
            out_lines.append('')

        for item in paragraphs:
            if item is None:
                continue
            kind = item[0]
            body = item[1]

            if kind == 'body':
                if body:
                    out_lines.append(body)
                    out_lines.append('')

            elif kind == 'closing':
                out_lines.append('')
                out_lines.append(body)
                out_lines.append('')

            elif kind == 'signature':
                sig_lines = item[1]
                out_lines.append('')
                for _sl in sig_lines:
                    if not _sl:
                        continue
                    # Split "Signature et cachet de la sociÃ©tÃ© M. PrÃ©nom NOM RÃ´le â€“ SociÃ©tÃ©"
                    # into: label line / name line / role line
                    _name_m = _r.search(
                        r'\s+((?:M\.|Mme\.|Dr\.|Me\.)\s+\S+\s+[A-ZÀ-ÖØ-Þ]\S+)',
                        _sl)
                    if _name_m:
                        _label = _sl[:_name_m.start()].strip()
                        _rest_sig = _sl[_name_m.start():].strip()
                        # Further split name from role: "M. PrÃ©nom NOM RÃ´le"
                        # Role usually starts after the last ALL-CAPS word of the name
                        _role_m = _r.search(
                            r'^((?:M\.|Mme\.|Dr\.|Me\.)\s+\S+\s+[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ]+)\s+(.+)$',
                            _rest_sig)
                        if _label:
                            out_lines.append(_label)
                        if _role_m:
                            out_lines.append(_role_m.group(1))   # "M. Hichem KABOUDI"
                            out_lines.append(_role_m.group(2))   # "GÃ©rant â€“ Liberty Com System Tunisie"
                        else:
                            out_lines.append(_rest_sig)
                    else:
                        out_lines.append(_sl)
                out_lines.append('')

        return '\n'.join(out_lines).strip()

    def _create_pptx_document(self, filepath, content, doc_title=None):
        """Create a professional PowerPoint presentation from markdown-style content."""
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor
            from pptx.enum.text import PP_ALIGN
            import re as _re

            # â”€â”€ Palette â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            C_DARK   = RGBColor(0x0F, 0x20, 0x44)   # deep navy
            C_ACC    = RGBColor(0x25, 0x63, 0xEB)   # electric blue
            C_TEAL   = RGBColor(0x06, 0xB6, 0xD4)   # teal accent stripe
            C_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
            C_OFFWH  = RGBColor(0xF8, 0xFA, 0xFF)   # slide background
            C_TEXT   = RGBColor(0x1E, 0x29, 0x3B)   # body text
            C_MUTED  = RGBColor(0x64, 0x74, 0x8B)   # captions / page numbers
            C_SUB    = RGBColor(0xA0, 0xB8, 0xD8)   # title slide subtitle
            C_SECT_BG= RGBColor(0x1A, 0x35, 0x6E)   # section slide right panel
            FONT = 'Calibri'

            # â”€â”€ Geometry (16:9 widescreen) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            W, H = Inches(13.33), Inches(7.5)

            prs = Presentation()
            prs.slide_width  = W
            prs.slide_height = H
            BLANK = prs.slide_layouts[6]

            # â”€â”€ Low-level helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def rect(sl, l, t, w, h, col):
                shp = sl.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
                shp.fill.solid(); shp.fill.fore_color.rgb = col
                shp.line.fill.background()
                return shp

            def txb(sl, l, t, w, h):
                tb = sl.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
                tb.word_wrap = True
                tf = tb.text_frame; tf.word_wrap = True
                return tf

            def plain_run(para, text, size, col, bold=False, italic=False):
                r = para.add_run(); r.text = text
                r.font.name = FONT; r.font.size = Pt(size)
                r.font.color.rgb = col
                r.font.bold = bold; r.font.italic = italic
                return r

            def inline(para, text, size, col, bold_base=False):
                """Render **bold** and *italic* inline markers."""
                for seg in _re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', text):
                    if not seg: continue
                    if seg.startswith('**') and seg.endswith('**'):
                        plain_run(para, seg[2:-2], size, col, bold=True)
                    elif seg.startswith('*') and seg.endswith('*'):
                        plain_run(para, seg[1:-1], size, col, italic=True)
                    else:
                        plain_run(para, seg, size, col, bold=bold_base)

            # â”€â”€ Content parser â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Each # heading â†’ new slide.  ## / ### â†’ sub-heading in slide.
            # If NO # headings exist, ## headings are promoted to slide titles.
            # Bullets, numbered lists, body text â†’ blocks inside current slide.
            # Tuple format: (kind, text, level)

            # Strip Sources / References lines â€” they don't belong on presentation slides
            _src_pat = _re.compile(
                r'^\s*\*{0,2}(?:sources?|references?|bibliography|footnotes?|citations?)\*{0,2}\s*[:\-]',
                _re.IGNORECASE,
            )
            _clean_lines = []
            _in_sources = False
            for _sl in (content or '').split('\n'):
                if _src_pat.match(_sl):
                    _in_sources = True
                elif _in_sources and _sl.strip() and not _sl.strip().startswith('['):
                    _in_sources = False
                if not _in_sources:
                    _clean_lines.append(_sl)
            content = '\n'.join(_clean_lines)

            lines = content.split('\n')
            slides_raw = []   # [{'title': str, 'blocks': [(kind, text, level)]}]
            cur = None
            _has_h1 = any(_re.match(r'^#\s+', ln) for ln in lines)

            def _push():
                if cur is not None:
                    slides_raw.append(dict(cur))

            for raw in lines:
                ln = raw.rstrip()
                m1 = _re.match(r'^#\s+(.+)', ln)
                if m1:
                    _push(); cur = {'title': m1.group(1).strip(), 'blocks': []}
                    continue
                if cur is None:
                    cur = {'title': doc_title or '', 'blocks': []}
                m2 = _re.match(r'^##\s+(.+)', ln)
                if m2:
                    if not _has_h1:
                        # No H1 in content â€” promote H2 to slide title
                        _push(); cur = {'title': m2.group(1).strip(), 'blocks': []}
                    else:
                        cur['blocks'].append(('h2', m2.group(1).strip(), 0))
                    continue
                m3 = _re.match(r'^###\s+(.+)', ln)
                if m3:
                    cur['blocks'].append(('h3', m3.group(1).strip(), 0)); continue
                mb = _re.match(r'^(\s*)[\-\*â€¢]\s+(.+)', ln)
                if mb:
                    lvl = len(mb.group(1)) // 2
                    cur['blocks'].append(('bullet', mb.group(2).strip(), lvl)); continue
                mn = _re.match(r'^(\s*)\d+[\.\)]\s+(.+)', ln)
                if mn:
                    lvl = len(mn.group(1)) // 2
                    cur['blocks'].append(('num', mn.group(2).strip(), lvl)); continue
                if _re.match(r'^[-_*]{3,}$', ln.strip()):
                    continue
                if ln.strip():
                    cur['blocks'].append(('body', ln.strip(), 0))
                else:
                    cur['blocks'].append(('blank', '', 0))
            _push()

            if not slides_raw:
                slides_raw = [{'title': doc_title or 'PrÃ©sentation', 'blocks':
                    [('body', l.strip(), 0) for l in lines if l.strip()]}]

            main_title = doc_title or (slides_raw[0]['title'] or 'PrÃ©sentation')

            # â”€â”€ Flat-text restructure: convert dense body paragraphs to bullets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # When the entire presentation collapses to 1 slide of body lines,
            # split long sentences into bullet points for readability.
            for _sd in slides_raw:
                _nb = [(k, t, l) for k, t, l in _sd['blocks'] if k not in ('blank',)]
                _all_body = _nb and all(k == 'body' for k, _, _ in _nb)
                if _all_body:
                    # If a body line is very long (single-paragraph), split at sentence boundaries
                    _expanded_blocks = []
                    for _bk, _bt, _bl in _sd['blocks']:
                        if _bk == 'body' and len(_bt) > 120:
                            # Split into sentences on '. ', '! ', '? ' boundaries
                            _sents = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', _bt) if s.strip()]
                            for _s in _sents:
                                _expanded_blocks.append(('bullet', _s, 0))
                        elif _bk == 'body' and _nb:
                            _expanded_blocks.append(('bullet', _bt, 0))
                        else:
                            _expanded_blocks.append((_bk, _bt, _bl))
                    _sd['blocks'] = _expanded_blocks

            # â”€â”€ Auto-split slides that overflow the content area â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _BLOCK_H = {'blank': 0.10, 'h2': 0.88, 'h3': 0.62, 'bullet': 0.58, 'num': 0.58, 'body': 0.68}
            _CONTENT_AREA = 7.18 - 1.50  # MAX_Y - TOP
            _MAX_BLOCKS = 5              # hard cap: max non-blank blocks per slide

            def _split_overflow(sd):
                """Return list of slide dicts, splitting blocks across slides when they overflow.
                Enforces both a height cap and a hard block-count cap per slide.
                Balances the last two pages so the final slide has at least 3 items."""
                blocks = [b for b in sd['blocks'] if b[0] != 'blank']  # ignore blanks for split calc
                title = sd['title']
                if not blocks:
                    return [sd]
                out, part, cur_b, cur_h, nb = [], 1, [], 0.0, 0
                for bk, bt, bl in blocks:
                    bh = _BLOCK_H.get(bk, 0.68)
                    over_h = cur_h + bh > _CONTENT_AREA
                    over_n = nb >= _MAX_BLOCKS
                    if (over_h or over_n) and cur_b:
                        t = title if part == 1 else f"{title} ({part})"
                        out.append({'title': t, 'blocks': cur_b})
                        cur_b, cur_h, nb, part = [], 0.0, 0, part + 1
                    cur_b.append((bk, bt, bl))
                    cur_h += bh
                    nb += 1
                if cur_b:
                    t = title if part == 1 else f"{title} ({part})"
                    out.append({'title': t, 'blocks': cur_b})
                # Balance: if last slide has < 3 items and there are >= 2 slides, redistribute
                if len(out) >= 2 and len(out[-1]['blocks']) < 3:
                    prev = out[-2]
                    last = out[-1]
                    combined = prev['blocks'] + last['blocks']
                    mid = len(combined) // 2
                    prev['blocks'] = combined[:mid]
                    last['blocks'] = combined[mid:]
                return out or [sd]

            _expanded = []
            for _sd in slides_raw:
                _expanded.extend(_split_overflow(_sd))
            slides_raw = _expanded

            # Re-derive main_title after potential restructure
            main_title = doc_title or (slides_raw[0]['title'] or main_title)


            # â”€â”€ TITLE SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def make_title_slide(title, subtitle=''):
                sl = prs.slides.add_slide(BLANK)
                # Full dark background
                rect(sl, 0, 0, 13.33, 7.5, C_DARK)
                # Bold left accent (blue + thin teal stripe)
                rect(sl, 0,    0, 0.40, 7.5, C_ACC)
                rect(sl, 0.40, 0, 0.06, 7.5, C_TEAL)
                # Bottom bar
                rect(sl, 0, 6.75, 13.33, 0.75, C_ACC)
                # Decorative horizontal line above title
                rect(sl, 1.1, 2.45, 11.0, 0.05, C_ACC)
                # Title
                tf_ = txb(sl, 1.1, 1.2, 11.2, 1.4)
                p_ = tf_.paragraphs[0]; p_.alignment = PP_ALIGN.LEFT
                plain_run(p_, title, 46, C_WHITE, bold=True)
                # Sub-title
                if subtitle:
                    tf2 = txb(sl, 1.1, 2.65, 11.0, 1.1)
                    p2 = tf2.paragraphs[0]; p2.alignment = PP_ALIGN.LEFT
                    plain_run(p2, subtitle, 22, C_SUB, italic=True)
                # Slide count label
                tf3 = txb(sl, 0.5, 6.82, 12.5, 0.4)
                p3 = tf3.paragraphs[0]; p3.alignment = PP_ALIGN.RIGHT
                plain_run(p3, f'{len(slides_raw)} sections', 11, C_WHITE)

            # â”€â”€ SECTION DIVIDER SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def make_section_slide(title, num_str=''):
                sl = prs.slides.add_slide(BLANK)
                # Left panel: dark
                rect(sl, 0,    0, 5.6, 7.5, C_DARK)
                # Right panel: slightly lighter navy
                rect(sl, 5.6,  0, 7.73, 7.5, C_SECT_BG)
                # Accent vertical bar at split
                rect(sl, 5.52, 0, 0.16, 7.5, C_ACC)
                rect(sl, 5.68, 0, 0.05, 7.5, C_TEAL)
                # Large section number (ghost, left panel)
                if num_str:
                    tf_n = txb(sl, 0.3, 0.2, 5.0, 2.5)
                    p_n = tf_n.paragraphs[0]
                    plain_run(p_n, num_str.zfill(2), 110, RGBColor(0x1A, 0x30, 0x60), bold=True)
                # Section title (left panel, white)
                tf_t = txb(sl, 0.4, 2.8, 5.0, 2.8)
                tf_t.word_wrap = True
                p_t = tf_t.paragraphs[0]; p_t.alignment = PP_ALIGN.LEFT
                plain_run(p_t, title, 34, C_WHITE, bold=True)
                # Accent underline under title
                rect(sl, 0.4, 5.55, 3.5, 0.05, C_ACC)

            # â”€â”€ CONTENT SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def make_content_slide(title, blocks, slide_num, total):
                sl = prs.slides.add_slide(BLANK)
                # Background
                rect(sl, 0, 0, 13.33, 7.5, C_OFFWH)
                # Header bar (dark navy)
                rect(sl, 0, 0, 13.33, 1.35, C_DARK)
                # Left accent bar
                rect(sl, 0,    0, 0.22, 7.5, C_ACC)
                rect(sl, 0.22, 0, 0.06, 7.5, C_TEAL)
                # Bottom accent line
                rect(sl, 0.28, 7.30, 13.05, 0.04, C_ACC)
                # Slide title
                tf_t = txb(sl, 0.55, 0.15, 12.3, 1.08)
                p_t = tf_t.paragraphs[0]; p_t.alignment = PP_ALIGN.LEFT
                plain_run(p_t, title, 30, C_WHITE, bold=True)
                # Page number
                tf_pg = txb(sl, 12.0, 7.15, 1.1, 0.28)
                p_pg = tf_pg.paragraphs[0]; p_pg.alignment = PP_ALIGN.RIGHT
                plain_run(p_pg, f'{slide_num}/{total}', 9, C_MUTED)

                # â”€â”€ Layout decision â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                pure_bullets = [(k, t, l) for k, t, l in blocks if k in ('bullet', 'num')]
                others       = [(k, t, l) for k, t, l in blocks if k not in ('bullet', 'num', 'blank')]
                use_two_col  = len(pure_bullets) >= 6 and len(others) <= 1

                CL  = 0.55   # content left
                CW  = 12.45  # content width
                TOP = 1.50   # content top
                MAX_Y = 7.18

                def _render_blocks(items, x, w, y_start, y_max):
                    y = y_start
                    for bk, bt, bl in items:
                        if y >= y_max: break
                        if bk == 'blank':
                            y += 0.10; continue

                        if bk == 'h2':
                            tf_ = txb(sl, x, y, w, 0.72)
                            p_ = tf_.paragraphs[0]
                            inline(p_, bt, 24, C_ACC, bold_base=True)
                            # Short accent bar under h2
                            bar_w = min(max(len(bt) * 0.14, 1.5), w * 0.6)
                            rect(sl, x, y + 0.66, bar_w, 0.04, C_ACC)
                            y += 0.88

                        elif bk == 'h3':
                            tf_ = txb(sl, x, y, w, 0.56)
                            p_ = tf_.paragraphs[0]
                            inline(p_, bt, 20, C_TEXT, bold_base=True)
                            y += 0.62

                        elif bk in ('bullet', 'num'):
                            indent = bl * 0.40
                            bx = x + 0.10 + indent
                            bw = w - 0.10 - indent
                            tf_ = txb(sl, bx, y, bw, 0.55)
                            tf_.word_wrap = True
                            p_ = tf_.paragraphs[0]
                            # Dot prefix
                            dot = p_.add_run()
                            dot.text = ('â–¸  ' if bk == 'num' else
                                        ('â—  ' if bl == 0 else 'â—‹  '))
                            dot.font.name = FONT; dot.font.size = Pt(17)
                            dot.font.color.rgb = C_ACC if bl == 0 else C_TEAL
                            dot.font.bold = True
                            inline(p_, bt, 18, C_TEXT)
                            y += 0.58

                        elif bk == 'body':
                            tf_ = txb(sl, x, y, w, 0.64)
                            tf_.word_wrap = True
                            p_ = tf_.paragraphs[0]
                            p_.alignment = (PP_ALIGN.JUSTIFY if len(bt) > 90 else PP_ALIGN.LEFT)
                            inline(p_, bt, 18, C_TEXT)
                            y += 0.68
                    return y

                if use_two_col:
                    # Full-width headers/body first
                    y = _render_blocks(others, CL, CW, TOP, MAX_Y)
                    if y > TOP + 0.1:
                        rect(sl, CL, y, CW, 0.035, C_MUTED)  # divider
                        y += 0.12
                    # Two-column bullets
                    mid = len(pure_bullets) // 2 + len(pure_bullets) % 2
                    col_w = CW / 2 - 0.2
                    col2_x = CL + col_w + 0.4
                    rect(sl, CL + col_w + 0.18, y, 0.035, MAX_Y - y, C_MUTED)  # column divider
                    y1 = y; y2 = y
                    for bi, (bk, bt, bl) in enumerate(pure_bullets):
                        if bi < mid:
                            _render_blocks([(bk, bt, bl)], CL,     col_w, y1, MAX_Y)
                            y1 += 0.46
                        else:
                            _render_blocks([(bk, bt, bl)], col2_x, col_w, y2, MAX_Y)
                            y2 += 0.46
                else:
                    _render_blocks(blocks, CL, CW, TOP, MAX_Y)

            # â”€â”€ CLOSING SLIDE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def make_closing_slide(title):
                sl = prs.slides.add_slide(BLANK)
                rect(sl, 0, 0, 13.33, 7.5, C_DARK)
                rect(sl, 0,    0, 0.40, 7.5, C_ACC)
                rect(sl, 0.40, 0, 0.06, 7.5, C_TEAL)
                rect(sl, 0, 6.75, 13.33, 0.75, C_ACC)
                rect(sl, 3.8, 4.05, 5.8, 0.05, C_ACC)  # decorative line
                tf_ = txb(sl, 1.1, 2.05, 11.2, 1.7)
                p_ = tf_.paragraphs[0]; p_.alignment = PP_ALIGN.CENTER
                plain_run(p_, 'Merci', 64, C_WHITE, bold=True)
                tf2 = txb(sl, 1.1, 4.2, 11.2, 0.9)
                p2 = tf2.paragraphs[0]; p2.alignment = PP_ALIGN.CENTER
                plain_run(p2, title, 20, C_SUB, italic=True)

            # â”€â”€ ASSEMBLE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Title slide subtitle = first body block of slide[0]
            subtitle = next(
                (bt for bk, bt, _ in slides_raw[0]['blocks'] if bk == 'body'), ''
            ) if slides_raw else ''
            make_title_slide(main_title, subtitle)

            # Decide which slides become content vs section-divider
            # A slide with ONLY body/h2/h3 items and no bullets â†’ section divider
            section_count = 0
            content_slides = []
            for sd in slides_raw:
                non_blank = [(k, t, l) for k, t, l in sd['blocks'] if k != 'blank']
                # Skip first slide if it's purely the subtitle
                if sd is slides_raw[0] and all(k == 'body' and t == subtitle for k, t, _ in non_blank):
                    continue
                content_slides.append(sd)

            total_content = len(content_slides)
            for ci, sd in enumerate(content_slides):
                non_blank = [(k, t, l) for k, t, l in sd['blocks'] if k != 'blank']
                has_bullets = any(k in ('bullet', 'num') for k, _, _ in non_blank)
                # Use section divider if: no bullets AND very few body lines (intro slide)
                if not has_bullets and len(non_blank) <= 2:
                    section_count += 1
                    make_section_slide(sd['title'], str(section_count))
                else:
                    make_content_slide(sd['title'], sd['blocks'], ci + 1, total_content)

            make_closing_slide(main_title)

            prs.save(filepath)
            return filepath, None

        except Exception as _exc:
            import traceback as _tb
            return None, f"PPTX error: {_exc}\n{_tb.format_exc()}"

    def _create_excel_document(self, filepath, content, doc_title=None):
        """Create a styled Excel (.xlsx) file from text/markdown/table content."""
        try:
            import openpyxl as _xl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            import re as _re

            # â”€â”€ Palette (matches PPTX theme) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            C_HDR_BG  = '0F2044'   # dark navy header
            C_HDR_FG  = 'FFFFFF'   # white text
            C_ACC1    = '2563EB'   # blue
            C_ACC2    = '06B6D4'   # teal
            C_ROW_ALT = 'EEF4FF'   # light blue alternate rows
            C_BORDER  = 'C4D4F0'   # thin border
            C_DIM     = '64748B'   # dim/grey text

            def _side(c=C_BORDER): return Side(style='thin', color=c)
            def _border(): return Border(left=_side(), right=_side(), top=_side(), bottom=_side())
            def _hdr_font(sz=11): return Font(name='Calibri', bold=True, color=C_HDR_FG, size=sz)
            def _body_font(bold=False, sz=11, color='1E293B'): return Font(name='Calibri', bold=bold, color=color, size=sz)
            def _fill(color): return PatternFill('solid', fgColor=color)
            def _alt(ri): return _fill(C_ROW_ALT if ri % 2 == 0 else 'FFFFFF')
            def _align(h='left', v='center', wrap=False, indent=0):
                return Alignment(horizontal=h, vertical=v, wrap_text=wrap, indent=indent)

            # â”€â”€ Content parsers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def _is_table(ln): return '|' in ln and ln.strip().startswith('|')

            def _parse_table(tlines):
                rows = []
                for ln in tlines:
                    if _re.match(r'^\|[\s\-:|]+\|?\s*$', ln): continue
                    cells = [c.strip() for c in ln.strip().strip('|').split('|')]
                    if any(cells): rows.append(cells)
                return rows

            def _parse_bullet(ln):
                m = _re.match(r'^(\s*)[-*â€¢]\s+(.+)', ln)
                if m: return len(m.group(1)) // 2, m.group(2).strip()
                m = _re.match(r'^(\s*)\d+[.)]\s+(.+)', ln)
                if m: return len(m.group(1)) // 2, m.group(2).strip()
                return None

            def _is_kv(ln):
                return bool(_re.match(r'^[\w\s\-/À-ÿ]{2,40}:\s+\S', ln))

            def _detect_type(slines):
                tc = sum(1 for ln in slines if _is_table(ln))
                kc = sum(1 for ln in slines if _is_kv(ln))
                bc = sum(1 for ln in slines if _parse_bullet(ln) is not None)
                if tc >= 2: return 'table'
                if kc >= 3 and kc > bc: return 'kv'
                if bc >= 2: return 'list'
                return 'text'

            # â”€â”€ Split content into sections (H1/H2 â†’ separate sheets) â”€â”€â”€â”€â”€â”€â”€â”€
            raw_lines = (content or '').splitlines()
            sections = []
            cur_title = doc_title or 'Sheet 1'
            cur_lines = []
            for ln in raw_lines:
                m1 = _re.match(r'^#\s+(.+)', ln)
                m2 = _re.match(r'^##\s+(.+)', ln)
                if m1 or m2:
                    if cur_lines: sections.append((cur_title, cur_lines))
                    cur_title = (m1 or m2).group(1).strip()
                    cur_lines = []
                else:
                    cur_lines.append(ln)
            sections.append((cur_title, cur_lines))
            if not any(s[1] for s in sections):
                sections = [(doc_title or 'Sheet 1', raw_lines)]

            # â”€â”€ Write one worksheet â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def _write_sheet(ws, title, slines):
                row = 1
                # Title banner
                ws.merge_cells(f'A{row}:F{row}')
                c = ws.cell(row, 1, title)
                c.font = Font(name='Calibri', bold=True, color='FFFFFF', size=14)
                c.fill = _fill(C_ACC1)
                c.alignment = _align('left', 'center', indent=1)
                ws.row_dimensions[row].height = 30
                row += 1

                dtype = _detect_type(slines)

                if dtype == 'table':
                    # Collect table blocks and inter-table text
                    blocks = []
                    buf_table, buf_text = [], []
                    for ln in slines:
                        if _is_table(ln):
                            if buf_text: blocks.append(('text', buf_text[:])); buf_text = []
                            buf_table.append(ln)
                        else:
                            if buf_table: blocks.append(('table', buf_table[:])); buf_table = []
                            if ln.strip(): buf_text.append(ln)
                    if buf_table: blocks.append(('table', buf_table))
                    if buf_text: blocks.append(('text', buf_text))

                    for btype, blines in blocks:
                        if btype == 'table':
                            trows = _parse_table(blines)
                            if not trows: continue
                            headers, data = trows[0], trows[1:]
                            # Header row
                            ws.row_dimensions[row].height = 22
                            for ci, h in enumerate(headers, 1):
                                c = ws.cell(row, ci, h)
                                c.font = _hdr_font(); c.fill = _fill(C_HDR_BG)
                                c.alignment = _align('center', 'center', wrap=True)
                                c.border = _border()
                            row += 1
                            for ri, dr in enumerate(data):
                                ws.row_dimensions[row].height = 18
                                for ci, val in enumerate(dr, 1):
                                    c = ws.cell(row, ci, val)
                                    c.font = _body_font(bold=(ci == 1))
                                    c.fill = _alt(ri)
                                    c.alignment = _align('left', 'center', wrap=True, indent=1)
                                    c.border = _border()
                                row += 1
                            row += 1
                        else:
                            for ln in blines:
                                ws.merge_cells(f'A{row}:F{row}')
                                c = ws.cell(row, 1, ln.strip())
                                c.font = _body_font(sz=10); c.alignment = _align(wrap=True)
                                row += 1

                elif dtype == 'kv':
                    # Two-column: Field | Value
                    ws.row_dimensions[row].height = 22
                    for ci, lbl in enumerate(['Field', 'Value'], 1):
                        c = ws.cell(row, ci, lbl)
                        c.font = _hdr_font(); c.fill = _fill(C_HDR_BG)
                        c.alignment = _align('center', 'center'); c.border = _border()
                    row += 1
                    ri = 0
                    for ln in slines:
                        if not ln.strip(): continue
                        if _is_kv(ln):
                            parts = ln.split(':', 1)
                            key, val = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else '')
                        else:
                            key, val = ln.strip(), ''
                        ws.row_dimensions[row].height = 18
                        for ci, txt, bold in [(1, key, True), (2, val, False)]:
                            c = ws.cell(row, ci, txt)
                            c.font = _body_font(bold=bold); c.fill = _alt(ri)
                            c.alignment = _align('left', 'center', wrap=True, indent=1)
                            c.border = _border()
                        row += 1; ri += 1

                elif dtype == 'list':
                    # Three-column: # | Item | Parent category
                    ws.row_dimensions[row].height = 22
                    ws.column_dimensions['A'].width = 6
                    ws.column_dimensions['B'].width = 55
                    ws.column_dimensions['C'].width = 22
                    for ci, lbl in enumerate(['#', 'Item', 'Category'], 1):
                        c = ws.cell(row, ci, lbl)
                        c.font = _hdr_font(); c.fill = _fill(C_HDR_BG)
                        c.alignment = _align('center', 'center'); c.border = _border()
                    row += 1
                    n, ri, cat = 1, 0, ''
                    for ln in slines:
                        b = _parse_bullet(ln)
                        if b is not None:
                            level, text = b
                            if level == 0: cat = text
                            ws.row_dimensions[row].height = 18
                            c1 = ws.cell(row, 1, str(n))
                            c1.font = _body_font(sz=10); c1.fill = _alt(ri)
                            c1.alignment = _align('center', 'center'); c1.border = _border()
                            c2 = ws.cell(row, 2, ('   ' * level) + text)
                            c2.font = _body_font(bold=(level == 0)); c2.fill = _alt(ri)
                            c2.alignment = _align('left', 'center', wrap=True, indent=1); c2.border = _border()
                            c3 = ws.cell(row, 3, cat if level > 0 else '')
                            c3.font = _body_font(sz=10, color=C_DIM); c3.fill = _alt(ri)
                            c3.alignment = _align('left', 'center'); c3.border = _border()
                            row += 1; ri += 1; n += 1
                        elif ln.strip():
                            ws.merge_cells(f'A{row}:C{row}')
                            c = ws.cell(row, 1, ln.strip())
                            c.font = _body_font(sz=10); c.alignment = _align(wrap=True)
                            row += 1

                else:  # plain text
                    for ln in slines:
                        if not ln.strip(): row += 1; continue
                        ws.row_dimensions[row].height = 18
                        ws.merge_cells(f'A{row}:F{row}')
                        c = ws.cell(row, 1, ln.strip())
                        c.font = _body_font(sz=10)
                        c.alignment = _align('left', 'center', wrap=True, indent=1)
                        row += 1

                # Auto-fit column widths (cap 8â€“60)
                for col_cells in ws.columns:
                    col_letter = get_column_letter(col_cells[0].column)
                    if ws.column_dimensions[col_letter].width > 8:
                        continue  # already manually set
                    max_len = max((len(str(cell.value or '')) for cell in col_cells), default=0)
                    ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 60)

                ws.freeze_panes = 'A3'
                ws.sheet_properties.tabColor = C_ACC1

            # â”€â”€ Build workbook â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            wb = _xl.Workbook()
            wb.remove(wb.active)
            seen: dict = {}
            for s_title, s_lines in sections:
                safe = _re.sub(r'[\\/*?:\[\]]', '', s_title)[:31].strip() or 'Sheet'
                if safe in seen:
                    seen[safe] += 1
                    safe = safe[:27] + f' ({seen[safe]})'
                else:
                    seen[safe] = 1
                _write_sheet(wb.create_sheet(title=safe), s_title, s_lines)

            wb.save(filepath)
            return filepath, None

        except Exception as _exc:
            import traceback as _tb
            return None, f"Excel error: {_exc}\n{_tb.format_exc()}"

    def _create_pdf_document(self, filepath, content, doc_title=None):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
            from reportlab.lib.colors import HexColor, white
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                Table, TableStyle, KeepTogether,
            )
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except Exception:
            return None, "reportlab not installed. Run: pip install reportlab"
        try:
            import html as _html, os as _os

            # â”€â”€ Content analysis & structuring â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Never fail PDF generation because the formatter hit malformed text.
            # If structuring crashes, keep original content and proceed.
            _raw_content = content or ''
            try:
                content = self._analyze_and_structure_content(_raw_content)
            except Exception:
                content = _raw_content

            # Strip leading title from body (avoids rendering it twice)
            if doc_title:
                import re as _re2
                _t = doc_title.strip()
                _c = content.strip()
                # Case 1: body starts with plain title text
                if _c.lower().startswith(_t.lower()):
                    _rest = _c[len(_t):].lstrip(' .,;:â€“-\n')
                    if _rest:
                        content = _rest
                else:
                    # Case 2: body starts with "# Heading" that matches doc_title
                    _hm = _re2.match(r'^#{1,3}\s+(.+?)[\r\n]', _c)
                    if _hm and _hm.group(1).strip().lower() == _t.lower():
                        content = _c[_hm.end():].lstrip('\n')

            # â”€â”€ Arabic / RTL detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            is_arabic = self._is_arabic_content(content or '')

            # â”€â”€ Font registration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Try professional Windows fonts; fall back to built-in Helvetica
            FN = 'Helvetica'
            FB = 'Helvetica-Bold'
            FI = 'Helvetica-Oblique'
            FM = 'Courier'

            _wf = r'C:\Windows\Fonts'
            for _rn, _rb, _ri, _f, _fb2, _fi in [
                ('CalibriR', 'CalibriB', 'CalibriI', 'calibri.ttf',  'calibrib.ttf',  'calibrii.ttf'),
                ('SegoeR',   'SegoeB',   'SegoeI',   'segoeui.ttf',  'segoeuib.ttf',  'segoeuii.ttf'),
                ('ArialR',   'ArialB',   'ArialI',   'arial.ttf',    'arialbd.ttf',   'ariali.ttf'),
            ]:
                _fp = _os.path.join(_wf, _f)
                _fpb = _os.path.join(_wf, _fb2)
                if _os.path.exists(_fp) and _os.path.exists(_fpb):
                    try:
                        pdfmetrics.registerFont(TTFont(_rn, _fp))
                        pdfmetrics.registerFont(TTFont(_rb, _fpb))
                        FN, FB = _rn, _rb
                        _fpi = _os.path.join(_wf, _fi)
                        if _os.path.exists(_fpi):
                            pdfmetrics.registerFont(TTFont(_ri, _fpi))
                            FI = _ri
                        break
                    except Exception:
                        pass

            # Arabic-capable font (Tahoma supports Arabic)
            FAR, FARB = FN, FB
            if is_arabic:
                for _rn, _rb, _f, _fb2 in [
                    ('TahomaR', 'TahomaB', 'tahoma.ttf', 'tahomabd.ttf'),
                    ('ArialAR', 'ArialAB', 'arial.ttf',  'arialbd.ttf'),
                ]:
                    _fp = _os.path.join(_wf, _f)
                    _fpb = _os.path.join(_wf, _fb2)
                    if _os.path.exists(_fp) and _os.path.exists(_fpb):
                        try:
                            pdfmetrics.registerFont(TTFont(_rn, _fp))
                            pdfmetrics.registerFont(TTFont(_rb, _fpb))
                            FAR, FARB = _rn, _rb
                        except Exception:
                            pass
                        break

            _fn  = FAR  if is_arabic else FN
            _fb  = FARB if is_arabic else FB
            _al  = TA_RIGHT   if is_arabic else TA_JUSTIFY
            _alh = TA_RIGHT   if is_arabic else TA_LEFT
            # Always use LTR wordWrap: _shape_arabic already applies get_display()
            # which produces visual LTR order; RTL wrap on top would reverse words.
            _wrap = 'LTR'

            def _shape_arabic(text):
                """Shape a single line / short phrase of Arabic text for ReportLab."""
                try:
                    import arabic_reshaper
                    from bidi.algorithm import get_display
                    return get_display(arabic_reshaper.reshape(text))
                except Exception:
                    return text

            _AR_BR = '\x00\x01'  # placeholder replaced with <br/> after HTML-escaping

            def _shape_arabic_para(text):
                """
                Shape Arabic paragraph text with per-line get_display().
                get_display() on the FULL paragraph reverses word order across all lines,
                making the paragraph read bottom-to-top.  Splitting into lines first and
                applying get_display() per line keeps correct top-to-bottom paragraph flow.
                Returns lines joined with _AR_BR (converted to <br/> after HTML-escaping).
                """
                try:
                    import arabic_reshaper
                    from bidi.algorithm import get_display
                    words = text.split()
                    if not words:
                        return text
                    if len(words) == 1:
                        return get_display(arabic_reshaper.reshape(text))
                    # Target ~93 % of text width so lines fill the column well
                    _txt_w = (PW - LM - RM) * 0.93
                    _fsize = 11
                    _fname = _fn
                    try:
                        _sp_w = pdfmetrics.stringWidth('\u0020', _fname, _fsize)
                        def _ww(w):
                            return pdfmetrics.stringWidth(
                                arabic_reshaper.reshape(w), _fname, _fsize)
                    except Exception:
                        _sp_w = _fsize * 0.30
                        def _ww(w):
                            return len(w) * _fsize * 0.45
                    lines, cur, cur_w = [], [], 0.0
                    for word in words:
                        ww = _ww(word)
                        if cur and cur_w + _sp_w + ww > _txt_w:
                            lines.append(get_display(arabic_reshaper.reshape(' '.join(cur))))
                            cur, cur_w = [word], ww
                        else:
                            cur_w = (cur_w + _sp_w + ww) if cur else ww
                            cur.append(word)
                    if cur:
                        lines.append(get_display(arabic_reshaper.reshape(' '.join(cur))))
                    return _AR_BR.join(lines)
                except Exception:
                    return text

            # â”€â”€ Colour palette â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            C_NAVY    = HexColor('#1B2B4B')
            C_BLUE    = HexColor('#2563EB')
            C_BLUE2   = HexColor('#1D4ED8')
            C_H2      = HexColor('#3B5998')
            C_H3      = HexColor('#1e3a5f')
            C_BODY    = HexColor('#1F2937')
            C_MUTED   = HexColor('#6B7280')
            C_DIVIDER = HexColor('#D1D5DB')
            C_CODE_BG = HexColor('#F3F4F6')
            C_TBL_HDR = HexColor('#1B2B4B')
            C_TBL_ALT = HexColor('#F0F4FF')

            # â”€â”€ Page & margins â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            PW, PH = letter
            LM = 1.1 * inch
            RM = 1.1 * inch
            TM = 1.0 * inch
            BM = 0.9 * inch

            # â”€â”€ Footer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _ft_raw = (doc_title or '')[:55]
            # Shape Arabic title for footer (canvas drawString doesn't auto-shape)
            _ft = _shape_arabic(_ft_raw) if (is_arabic and self._is_arabic_content(_ft_raw)) else _ft_raw
            def _footer(canvas_obj, doc_obj):
                canvas_obj.saveState()
                canvas_obj.setStrokeColor(C_BLUE)
                canvas_obj.setLineWidth(0.6)
                canvas_obj.line(LM, 0.62 * inch, PW - RM, 0.62 * inch)
                canvas_obj.setFont(_fn, 8)
                canvas_obj.setFillColor(C_MUTED)
                page_str = f'Page {canvas_obj.getPageNumber()}'
                if is_arabic:
                    # RTL layout: page number on left, title on right
                    canvas_obj.drawString(LM, 0.40 * inch, page_str)
                    if _ft:
                        canvas_obj.drawRightString(PW - RM, 0.40 * inch, _ft)
                else:
                    if _ft:
                        canvas_obj.drawString(LM, 0.40 * inch, _ft)
                    canvas_obj.drawRightString(PW - RM, 0.40 * inch, page_str)
                canvas_obj.restoreState()

            # â”€â”€ Document â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            doc = SimpleDocTemplate(
                filepath, pagesize=letter,
                leftMargin=LM, rightMargin=RM,
                topMargin=TM, bottomMargin=BM,
                title=doc_title or '', author='Opuntia AI',
            )

            # â”€â”€ Styles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def _S(name, **kw):
                return ParagraphStyle(name, **kw)

            ST_TITLE = _S('DocTitle',
                fontName=_fb, fontSize=16, textColor=C_NAVY,
                spaceBefore=0, spaceAfter=4, leading=22, alignment=TA_CENTER)
            ST_H1 = _S('H1',
                fontName=_fb, fontSize=17, textColor=C_NAVY,
                spaceBefore=20, spaceAfter=2, leading=24, alignment=_alh)
            ST_H2 = _S('H2',
                fontName=_fb, fontSize=13, textColor=C_H2,
                spaceBefore=14, spaceAfter=2, leading=20, alignment=_alh)
            ST_H3 = _S('H3',
                fontName=_fb, fontSize=11, textColor=C_H3,
                spaceBefore=10, spaceAfter=2, leading=17, alignment=_alh)
            ST_BODY = _S('Body',
                fontName=_fn, fontSize=11, textColor=C_BODY,
                leading=20, spaceAfter=8 if is_arabic else 5,
                alignment=_al, wordWrap=_wrap)
            ST_BULLET = _S('Bullet',
                fontName=_fn, fontSize=11, textColor=C_BODY,
                leading=18, spaceAfter=3,
                leftIndent=0 if is_arabic else 18,
                rightIndent=18 if is_arabic else 0,
                alignment=TA_RIGHT if is_arabic else TA_LEFT,
                wordWrap=_wrap)
            ST_NUM = _S('Num',
                fontName=_fn, fontSize=11, textColor=C_BODY,
                leading=18, spaceAfter=3,
                leftIndent=0 if is_arabic else 22,
                rightIndent=22 if is_arabic else 0,
                alignment=TA_RIGHT if is_arabic else TA_LEFT,
                wordWrap=_wrap)
            ST_CODE = _S('Code',
                fontName=FM, fontSize=9, textColor=HexColor('#374151'),
                leading=14, spaceAfter=1,
                leftIndent=8, rightIndent=8,
                backColor=C_CODE_BG, alignment=TA_LEFT)
            ST_SRC = _S('Source',
                fontName=_fn, fontSize=9, textColor=C_MUTED,
                leading=13, spaceAfter=2, leftIndent=10)

            # â”€â”€ Inline markdown â†’ ReportLab XML â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def _esc(t):
                return _html.escape(str(t), quote=False)

            def _prep(t):
                if is_arabic and self._is_arabic_content(t):
                    shaped = _shape_arabic_para(t)
                    # _AR_BR placeholder must survive HTML-escaping â†’ swap after
                    return _esc(shaped).replace(_AR_BR, '<br/>')
                return _esc(t)

            def md_to_rl(text):
                # Preserve inline code with placeholder to avoid re-escaping
                _codes = {}
                def _save_code(m):
                    ph = f'\x02C{len(_codes)}\x03'
                    _codes[ph] = (
                        f'<font name="{FM}" size="9" color="#374151">'
                        f'{_esc(m.group(1))}</font>'
                    )
                    return ph
                text = re.sub(r'`([^`\n]+)`', _save_code, text)
                parts = re.split(
                    r'(\*\*\*[^*\n]+\*\*\*|\*\*[^*\n]+\*\*|\*[^*\n]+\*|__[^_\n]+__)',
                    text,
                )
                out = []
                for seg in parts:
                    if seg.startswith('***') and seg.endswith('***') and len(seg) > 6:
                        out.append(f'<b><i>{_prep(seg[3:-3])}</i></b>')
                    elif (seg.startswith('**') and seg.endswith('**') and len(seg) > 4) or \
                         (seg.startswith('__') and seg.endswith('__') and len(seg) > 4):
                        inner = seg[2:-2]
                        out.append(f'<b>{_prep(inner)}</b>')
                    elif seg.startswith('*') and seg.endswith('*') and len(seg) > 2:
                        out.append(f'<i>{_prep(seg[1:-1])}</i>')
                    else:
                        escaped = _prep(seg)
                        for ph, repl in _codes.items():
                            escaped = escaped.replace(ph, repl)
                        out.append(escaped)
                return ''.join(out)

            # â”€â”€ Markdown table â†’ ReportLab Table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            def _flush_table(tlines, section_title=''):
                # Keep raw text cells for chart generation + Paragraph cells for table
                raw_rows  = []   # [[str, str, ...], ...]
                para_rows = []   # [[Paragraph, ...], ...]
                for tl in tlines:
                    tl = tl.strip().strip('|')
                    if re.match(r'^[\s\-:|]+$', tl):
                        continue
                    raw_cells  = [c.strip() for c in tl.split('|')]
                    para_cells = [Paragraph(md_to_rl(c), ST_BODY) for c in raw_cells]
                    raw_rows.append(raw_cells)
                    para_rows.append(para_cells)
                if not para_rows:
                    return []
                ncols = max(len(r) for r in para_rows)
                cw = (PW - LM - RM) / ncols
                tbl = Table(para_rows, colWidths=[cw] * ncols, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ('BACKGROUND',    (0, 0), (-1, 0),  C_TBL_HDR),
                    ('TEXTCOLOR',     (0, 0), (-1, 0),  white),
                    ('FONTNAME',      (0, 0), (-1, 0),  _fb),
                    ('FONTSIZE',      (0, 0), (-1, -1), 10),
                    ('FONTNAME',      (0, 1), (-1, -1), _fn),
                    ('ROWBACKGROUNDS',(0, 1), (-1, -1), [white, C_TBL_ALT]),
                    ('GRID',          (0, 0), (-1, -1), 0.4, C_DIVIDER),
                    ('ALIGN',         (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING',    (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING',   (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
                ]))
                result = [Spacer(1, 8), tbl, Spacer(1, 12)]

                # Auto-generate chart when the table has numeric data
                if len(raw_rows) >= 3:   # at least header + 2 data rows
                    _hdr  = raw_rows[0]
                    _data = raw_rows[1:]
                    _chart_bytes = self._make_chart_png(_hdr, _data, title=section_title)
                    if _chart_bytes:
                        import io as _cio, tempfile as _tmp, os as _cos
                        from reportlab.platypus import Image as _RLImg
                        _tf = _tmp.NamedTemporaryFile(suffix='.png', delete=False)
                        _tf.write(_chart_bytes)
                        _tf.close()
                        try:
                            _chart_w = PW - LM - RM
                            _chart_h = _chart_w * 0.56
                            _img = _RLImg(_tf.name, width=_chart_w, height=_chart_h)
                            result += [Spacer(1, 4), _img, Spacer(1, 10)]
                        except Exception:
                            pass
                        finally:
                            try:
                                _cos.unlink(_tf.name)
                            except Exception:
                                pass
                return result

            # â”€â”€ Build story â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            story = []

            # Title block
            if doc_title:
                _dt = _shape_arabic(doc_title) if (is_arabic and self._is_arabic_content(doc_title)) else doc_title
                story.append(Paragraph(_esc(_dt), ST_TITLE))
                story.append(Spacer(1, 16))

            lines = (content or '').split('\n')
            i = 0
            in_sources   = False
            in_code_blk  = False
            code_acc     = []
            tbl_acc      = []
            last_heading = doc_title or ''   # for chart titles

            while i < len(lines):
                line    = lines[i]
                stripped = line.strip()

                # â”€ Code fences â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if stripped.startswith('```'):
                    if not in_code_blk:
                        in_code_blk = True
                        code_acc = []
                    else:
                        in_code_blk = False
                        if code_acc:
                            story.append(Spacer(1, 6))
                            for cl in code_acc:
                                story.append(Paragraph(_esc(cl) or '&nbsp;', ST_CODE))
                            story.append(Spacer(1, 6))
                        code_acc = []
                    i += 1
                    continue
                if in_code_blk:
                    code_acc.append(line.rstrip())
                    i += 1
                    continue

                # â”€ Tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if stripped.startswith('|'):
                    tbl_acc.append(stripped)
                    i += 1
                    continue
                if tbl_acc:
                    story += _flush_table(tbl_acc, section_title=last_heading)
                    tbl_acc = []

                # â”€ Sources section â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if re.match(r'^\*?\*?sources?\*?\*?\s*:?\s*$', stripped, re.IGNORECASE):
                    in_sources = True
                    story.append(Spacer(1, 10))
                    story.append(HRFlowable(width='100%', thickness=0.5, color=C_DIVIDER, spaceAfter=4))
                    story.append(Paragraph(f'<b>Sources</b>', ST_SRC))
                    i += 1
                    continue
                if in_sources:
                    if stripped:
                        story.append(Paragraph(_esc(stripped), ST_SRC))
                    i += 1
                    continue

                # â”€ Blank line â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if not stripped:
                    story.append(Spacer(1, 6))
                    i += 1
                    continue

                # â”€ Horizontal rule â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if re.match(r'^[-*_]{3,}$', stripped):
                    story.append(HRFlowable(width='100%', thickness=0.7, color=C_DIVIDER, spaceAfter=6))
                    i += 1
                    continue

                # â”€ Headings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if stripped.startswith('#### '):
                    last_heading = stripped[5:].strip()
                    story.append(Paragraph(md_to_rl(last_heading), ST_H3))
                    i += 1
                    continue
                if stripped.startswith('### '):
                    last_heading = stripped[4:].strip()
                    story.append(Paragraph(md_to_rl(last_heading), ST_H3))
                    i += 1
                    continue
                if stripped.startswith('## '):
                    last_heading = stripped[3:].strip()
                    story.append(Paragraph(md_to_rl(last_heading), ST_H2))
                    i += 1
                    continue
                if stripped.startswith('# '):
                    last_heading = stripped[2:].strip()
                    story.append(Paragraph(md_to_rl(last_heading), ST_H1))
                    story.append(HRFlowable(width='40%', thickness=1.5, color=C_BLUE, spaceAfter=4))
                    i += 1
                    continue

                # â”€ Checkbox / checklist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                _cbm = re.match(r'^[-*+]\s+\[( |x|X)\]\s+(.+)$', stripped)
                if _cbm:
                    done = _cbm.group(1).lower() == 'x'
                    box  = '\u2611' if done else '\u2610'
                    story.append(Paragraph(f'{_esc(box)}\u00a0{md_to_rl(_cbm.group(2))}', ST_BULLET))
                    i += 1
                    continue

                # â”€ Bullet list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                bm = re.match(r'^[\*\-\+\u2022\u25aa]\s+(.+)$', stripped)
                if bm:
                    story.append(Paragraph(
                        f'<font color="#2563EB">\u2022</font>\u00a0{md_to_rl(bm.group(1))}',
                        ST_BULLET,
                    ))
                    i += 1
                    continue

                # â”€ Numbered list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                nm = re.match(r'^(\d+)[.)]\s+(.+)$', stripped)
                if nm:
                    story.append(Paragraph(
                        f'<b><font color="#2563EB">{_esc(nm.group(1))}.</font></b>\u00a0{md_to_rl(nm.group(2))}',
                        ST_NUM,
                    ))
                    i += 1
                    continue

                # â”€ Tree-style lines (â”œâ”€ â””â”€ â”‚) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if re.match(r'^[\u251c\u2514\u2502\u2500â”œâ””â”‚]', stripped):
                    story.append(Paragraph(_esc(stripped), ST_CODE))
                    i += 1
                    continue

                # â”€ Regular paragraph â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                story.append(Paragraph(md_to_rl(stripped), ST_BODY))
                i += 1

            # Flush any remaining table or code block
            if tbl_acc:
                story += _flush_table(tbl_acc, section_title=last_heading)
            if in_code_blk and code_acc:
                for cl in code_acc:
                    story.append(Paragraph(_esc(cl) or '&nbsp;', ST_CODE))

            doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
            return filepath, None
        except Exception as e:
            return None, f"PDF creation failed: {e}"

    def _handle_pdf_command(self, user_input, allow_desktop=False, allow_mutation=False):
        """
        Handle commands like:
          'create pdf called X and write: ...'
          'make a PDF file named X'
        """
        raw = (user_input or "").strip()
        if not raw:
            return None

        low = raw.lower()
        _has_pdf_ref = bool(re.search(r'\b(pdf|\.pdf)\b', low.split(':')[0][:300]))
        if not _has_pdf_ref:
            return None
        # Capability question without filename -> let AI answer conversationally.
        _is_pdf_question = bool(re.search(r'\b(can you|could you|do you|are you able|what is|is it possible)\b', low))
        _has_explicit_name = bool(re.search(r'\b(called|named|titled?)\s+\S', low))
        if _is_pdf_question and not _has_explicit_name:
            return None

        # Must have a creation/action verb â€” accept typos like "creat", "crete"
        if not re.search(
            r'\b(creat\w*|make|open|write|save|put|add|start|new|build|generat\w*|produc\w*)\b',
            low
        ):
            return None

        name = None
        content = ""

        # "write what you sent/said/have sent last" â†’ use last AI response as content
        _last_resp_pat = re.compile(
            r'\b(?:write|put|save|add|create)\s+'
            r'(?:what\s+(?:(?:you|u)(?:\'?ve)?\s+(?:have\s+)?|(?:have|had)\s+(?:you|u)\s+)(?:just\s+)?(?:sent|said|wrote|written|replied?|gave|given)'
            r'|(?:the\s+)?(?:last|previous|latest)\s+(?:response|answer|message|reply|result|thing)'
            r'|your\s+(?:last|previous|latest)\s+(?:response|answer|message|reply)'
            r'|(?:last|previous)\s+(?:answer|response|message|reply))',
            re.IGNORECASE,
        )
        if _last_resp_pat.search(low):
            # Search in mode-specific history first, then fall back to combined history
            _mode_hist = getattr(self, 'task_conversation_history', []) if getattr(self, 'input_mode', 'chat') == 'task' else []
            _all_hist = _mode_hist or getattr(self, 'conversation_history', [])
            for msg in reversed(_all_hist):
                last_ai = (msg.get('assistant') or msg.get('content') or '').strip()
                if last_ai:
                    content = self._strip_ai_sources(last_ai)
                    break
            # Only search conversation_history again if we were using task history and found nothing
            if not content and _mode_hist:
                for msg in reversed(getattr(self, 'conversation_history', [])):
                    last_ai = (msg.get('assistant') or msg.get('content') or '').strip()
                    if last_ai:
                        content = self._strip_ai_sources(last_ai)
                        break

        name_m = re.search(
            r'\b(?:called|named|titled?|name(?:d)?(?:\s+it)?|file\s+name(?:d)?)\s+["\']?([^"\',:]+?)["\']?\s*(?:and|with|write|$)',
            raw, re.IGNORECASE
        )
        if name_m and not name:
            name = name_m.group(1).strip(" \"'.,")
            name = re.sub(r'[\\/*?:"<>|]', '', name).strip()[:100]

        content_markers = [
            r'\bwrite\s+this\s+inside\s+[^:\n]+[:\-]\s*',
            r'\bwrite\s+this\s+in\s+[^:\n]+[:\-]\s*',
            r'\bwrite\s+this\s+inside\s*[:\-]?\s*',
            r'\bwrite\s+inside\s+it\s+this\s*[:\-]?\s*',
            r'\bwrite\s+inside\s+this\s*[:\-]?\s*',
            r'\bwrite\s+inside\s*[:\-]?\s*',
            r'\bwrite\s+this\s+\w{1,12}\s*[:\-]\s*',
            r'\bwrite\s+this\s*[:\-]\s*',
            r'\bwrite\s+this\s+(?:with\s+(?:\w+\s+)*?)?(?:good\s+)?(?:layout|format|formatting)\s*[:\-]?\s*',
            r'\bwrite\s+(?:this\s+)?(?:with\s+(?:\w+\s+)*?)?(?:good\s+)?(?:layout|format|formatting)\s*[:\-]?\s*',
            r'\bwrite\s*[:\-]\s*',
            r'\bcontent\s*[:\-]\s*',
            r'\binside\s+(?:this|it|that)\s*[:\-]\s*',
            r'\binside\s*[:\-]\s*',
            r'\bwith\s+(?:the\s+)?following\s+(?:content|text|information|details?)\s*[:\-]?\s*',
            r'\b(?:the\s+)?following\s*[:\-]\s*',
            r'\b(?:put|add)\s+(?:this\s+)?inside\s*[:\-]?\s*',
            r'\bwith\s+(?:the\s+)?(?:content|text)\s*[:\-]\s*',
        ]
        if not content:
            for marker_pat in content_markers:
                m = re.search(marker_pat + r'(.+)$', raw, re.IGNORECASE | re.DOTALL)
                if m and m.group(1).strip():
                    content = m.group(1).strip()
                    break

        if self._is_capability_question(raw) and not name and not content:
            return (
                "Yes â€” I can create a PDF, but I won't do it without explicit approval. "
                "If you want me to create one, say for example: "
                "\"Create a PDF called X and write: ...\""
            )

        # Guard: if a content marker was found but nothing followed it, don't create a blank document.
        _has_content_marker = any(re.search(mp, raw, re.IGNORECASE) for mp in content_markers)
        if _has_content_marker and not content:
            return "What would you like me to write inside the PDF? Please include the content after the colon."

        if content:
            if '\n' not in content:
                content = self._reformat_flat_document_text(content)

        if not name:
            smart_name = None
            if content:
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('## '):
                        smart_name = line[3:].strip()
                    elif line.startswith('# '):
                        smart_name = line[2:].strip()
                    elif len(line) <= 60:
                        smart_name = line
                    else:
                        # Long line â€” truncate at word boundary
                        truncated = line[:50].rsplit(' ', 1)[0].rstrip('.,;:')
                        if len(truncated) >= 8:
                            smart_name = truncated
                    if smart_name:
                        smart_name = re.sub(r'[\\/*?:"<>|,]', '', smart_name).strip()[:50]
                        break
            if not smart_name and content:
                smart_name = self._generate_doc_title(content, fallback='')
                if smart_name:
                    smart_name = re.sub(r'[\\/*?:"<>|,]', '', smart_name).strip()[:50]
            name = smart_name if smart_name else f"Document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if not name.lower().endswith('.pdf'):
            name = name + '.pdf'

        if not allow_mutation:
            preview = ""
            if content:
                snippet = content.strip().splitlines()[0][:80]
                if snippet:
                    preview = f' Preview: "{snippet}..."'
            self._audit("file_mutation", "permission_requested", {"command": raw[:300], "type": "pdf"})
            return self._set_pending_question(
                "Permission Required",
                f"Create PDF `{name}`?{preview}",
                [
                    {"label": "Allow once", "description": "Create this PDF now", "value": "allow"},
                    {"label": "Deny", "description": "Do not create the PDF", "value": "deny"},
                ],
                action="create_pdf_confirm",
                payload={"user_input": raw, "allow_desktop": True},
                on_deny="PDF creation cancelled.",
            )

        _cmd_head = raw
        for _mp in content_markers:
            _lm = re.search(_mp, raw, re.IGNORECASE | re.DOTALL)
            if _lm:
                _cmd_head = raw[:_lm.start()]
                break
        _inline_folder, _inline_err = self._parse_save_location(_cmd_head)
        if not _inline_err and _inline_folder:
            try:
                os.makedirs(_inline_folder, exist_ok=True)
            except Exception:
                pass
            final_path = os.path.join(_inline_folder, name)
            saved_path, create_err = self._create_pdf_document(final_path, content, doc_title=name.replace('.pdf', ''))
            if create_err:
                return f"Could not create PDF: {create_err}"
            try:
                os.startfile(saved_path)
            except Exception:
                pass
            return f"**Saved and opened** `{name}` in `{_inline_folder}`"

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        try:
            os.makedirs(desktop, exist_ok=True)
        except Exception:
            pass
        final_path = os.path.join(desktop, name)
        saved_path, create_err = self._create_pdf_document(final_path, content, doc_title=name.replace('.pdf', ''))
        if create_err:
            self._pending_pdf_save = {"content": content, "name": name, "doc_title": name.replace('.pdf', '')}
            return (
                f"Ready to create **`{name}`**. Where do you want to save it?\n"
                f"Say: *desktop* Â· *documents* Â· *downloads* Â· *D drive* Â· "
                f"a folder name Â· or a full path."
            )
        try:
            os.startfile(saved_path)
        except Exception:
            pass
        return f"**Saved and opened** `{name}` on your Desktop"

    # -------------------------------------------------------------------------
    # Word Document Engine
    # -------------------------------------------------------------------------

    def _add_formatted_runs(self, para, text):
        """Parse inline **bold**, *italic*, ***bold-italic*** and add runs to a paragraph."""
        parts = re.split(r'(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*)', text)
        for part in parts:
            if part.startswith('***') and part.endswith('***') and len(part) > 6:
                run = para.add_run(part[3:-3])
                run.bold = True
                run.italic = True
            elif part.startswith('**') and part.endswith('**') and len(part) > 4:
                run = para.add_run(part[2:-2])
                run.bold = True
            elif part.startswith('*') and part.endswith('*') and len(part) > 2:
                run = para.add_run(part[1:-1])
                run.italic = True
            else:
                if part:
                    para.add_run(part)

    @staticmethod
    def _is_arabic_content(text):
        """Return True if text is predominantly Arabic (>30% Arabic chars among letters)."""
        if not text:
            return False
        arabic_chars = sum(
            1 for c in text
            if '\u0600' <= c <= '\u06FF'
            or '\u0750' <= c <= '\u077F'
            or '\uFB50' <= c <= '\uFDFF'
            or '\uFE70' <= c <= '\uFEFF'
        )
        total_letters = sum(1 for c in text if c.isalpha())
        return total_letters > 0 and arabic_chars / total_letters > 0.3

    def _apply_arabic_paragraph(self, para, font_name="Arabic Typesetting", justify=False):
        """Apply RTL direction, Arabic font, and explicit sizing to a paragraph and its runs."""
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        pPr = para._p.get_or_add_pPr()

        # Set paragraph bidi (RTL direction)
        if pPr.find(qn('w:bidi')) is None:
            bidi = OxmlElement('w:bidi')
            pPr.insert(0, bidi)

        # Force alignment Ã¢Â€Â” always set right or both for Arabic paragraphs.
        # Only preserve 'center' if it was explicitly intended (title/centered heading).
        jc = pPr.find(qn('w:jc'))
        _cur_jc = jc.get(qn('w:val')) if jc is not None else None
        if _cur_jc != 'center':
            if jc is None:
                jc = OxmlElement('w:jc')
                pPr.append(jc)
            jc.set(qn('w:val'), 'both' if justify else 'right')

        # Determine explicit font size for runs.
        # Headings and Title keep their style-defined sizes; body text gets 16pt
        # (32 half-points) explicitly on every run because Arabic complex-script
        # text uses w:szCs which is NOT set by python-docx's font.size shortcut.
        _style_name = (para.style.name if para.style else '') or ''
        _is_heading_style = 'Heading' in _style_name or _style_name == 'Title'
        if _style_name == 'Title':
            _body_sz_hpt = 40          # 20 pt - fits long Arabic titles on one line
        elif 'Heading 1' in _style_name:
            _body_sz_hpt = 44          # 22 pt
        elif 'Heading 2' in _style_name:
            _body_sz_hpt = 36          # 18 pt
        elif 'Heading 3' in _style_name:
            _body_sz_hpt = 32          # 16 pt
        else:
            _body_sz_hpt = 32          # 16 pt for body / list / default

        # Set paragraph-level default font via pPr/rPr
        ppr_rpr = pPr.find(qn('w:rPr'))
        if ppr_rpr is None:
            ppr_rpr = OxmlElement('w:rPr')
            pPr.append(ppr_rpr)
        rFonts_ppr = ppr_rpr.find(qn('w:rFonts'))
        if rFonts_ppr is None:
            rFonts_ppr = OxmlElement('w:rFonts')
            ppr_rpr.insert(0, rFonts_ppr)
        for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
            rFonts_ppr.set(qn(attr), font_name)
        # Propagate size to paragraph-level default rPr as well
        if _body_sz_hpt is not None:
            for _tag in ('w:sz', 'w:szCs'):
                _el = ppr_rpr.find(qn(_tag))
                if _el is None:
                    _el = OxmlElement(_tag)
                    ppr_rpr.append(_el)
                _el.set(qn('w:val'), str(_body_sz_hpt))

        # Apply font, RTL mark, and explicit size to each run
        for run in para.runs:
            run.font.name = font_name
            rPr = run._r.get_or_add_rPr()
            if rPr.find(qn('w:rtl')) is None:
                rtl_el = OxmlElement('w:rtl')
                rPr.append(rtl_el)
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                rFonts = OxmlElement('w:rFonts')
                rPr.insert(0, rFonts)
            for attr in ('w:ascii', 'w:hAnsi', 'w:cs'):
                rFonts.set(qn(attr), font_name)
            # Always set both w:sz and w:szCs so Arabic complex-script text
            # renders at the correct size regardless of style inheritance.
            if _body_sz_hpt is not None:
                for _tag in ('w:sz', 'w:szCs'):
                    _el = rPr.find(qn(_tag))
                    if _el is None:
                        _el = OxmlElement(_tag)
                        rPr.append(_el)
                    _el.set(qn('w:val'), str(_body_sz_hpt))
            # Arabic legal/formal documents: force heading text to black.
            # Word's default theme colors (blue, teal) are inappropriate for
            # contracts, agreements, and official Arabic documents.
            if _is_heading_style:
                _color_el = rPr.find(qn('w:color'))
                if _color_el is None:
                    _color_el = OxmlElement('w:color')
                    rPr.append(_color_el)
                _color_el.set(qn('w:val'), '000000')

    def _create_word_document(self, filepath, content, doc_title=None):
        """
        Create a polished .docx from structured or flat content.
        Supports: # headings, - bullets, 1. sections, | tables |,
                  **bold**, *italic***, legal/formal layouts, plain text.
        Arabic RTL layout is applied automatically when Arabic content is detected.
        Returns (filepath, error_message).
        """
        try:
            from docx import Document
            from docx.shared import Pt, Inches, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
        except ImportError:
            return None, "python-docx not installed. Run: pip install python-docx"

        doc = Document()

        # -- Content analysis & structuring ---------------------------------
        content = self._analyze_and_structure_content(content or '')

        # Strip leading title from body (avoids rendering it twice)
        if doc_title:
            import re as _re2
            _t = doc_title.strip()
            _c = content.strip()
            if _c.lower().startswith(_t.lower()):
                _rest = _c[len(_t):].lstrip(' .,;:â€“-\n')
                if _rest:
                    content = _rest
            else:
                _hm = _re2.match(r'^#{1,3}\s+(.+?)[\r\n]', _c)
                if _hm and _hm.group(1).strip().lower() == _t.lower():
                    content = _c[_hm.end():].lstrip('\n')

        # -- Detect language / direction ------------------------------------
        is_arabic = self._is_arabic_content(content or "")
        arabic_font = "Arabic Typesetting"  # excellent for formal Arabic docs on Windows

        # For Arabic docs, set document-level RTL in settings + larger body font
        if is_arabic:
            try:
                settings_el = doc.settings.element
                if settings_el.find(qn('w:bidi')) is None:
                    bidi_doc = OxmlElement('w:bidi')
                    settings_el.append(bidi_doc)
            except Exception:
                pass
            # Set Normal style: 14pt, Arabic font, explicit szCs (complex-script size
            # used by Arabic text Ã¢Â€Â” without it Word falls back to document default ~11pt).
            try:
                normal_style = doc.styles['Normal']
                normal_style.font.name = arabic_font
                normal_style.font.size = Pt(16)
                # python-docx font.size only sets w:sz; Arabic needs w:szCs too.
                _ns_rPr = normal_style.element.find(qn('w:rPr'))
                if _ns_rPr is None:
                    _ns_rPr = OxmlElement('w:rPr')
                    normal_style.element.append(_ns_rPr)
                _szCs = _ns_rPr.find(qn('w:szCs'))
                if _szCs is None:
                    _szCs = OxmlElement('w:szCs')
                    _ns_rPr.append(_szCs)
                _szCs.set(qn('w:val'), '32')   # 16 pt = 32 half-points
                # Line spacing: 1.5ÃƒÂ— (360 twips) + 6pt space after paragraphs
                _ns_pPr = normal_style.element.find(qn('w:pPr'))
                if _ns_pPr is None:
                    _ns_pPr = OxmlElement('w:pPr')
                    normal_style.element.insert(0, _ns_pPr)
                _ns_spacing = _ns_pPr.find(qn('w:spacing'))
                if _ns_spacing is None:
                    _ns_spacing = OxmlElement('w:spacing')
                    _ns_pPr.append(_ns_spacing)
                _ns_spacing.set(qn('w:line'),     '360')   # 1.5ÃƒÂ— line height
                _ns_spacing.set(qn('w:lineRule'), 'auto')
                _ns_spacing.set(qn('w:after'),    '120')   # 6 pt spacing after
            except Exception:
                pass

        # -- Page setup ----------------------------------------------------
        for section in doc.sections:
            section.top_margin    = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin   = Inches(1.25)
            section.right_margin  = Inches(1.25)

        # -- Detect document title from content ----------------------------
        # If first non-empty line is ALL-CAPS or starts with #, use it as title
        lines_raw = (content or "").split('\n')
        first_content = next((l.strip() for l in lines_raw if l.strip()), "")
        # Strip markdown title prefix if present
        auto_title = None
        if first_content.startswith('# '):
            auto_title = first_content[2:].strip()
        elif first_content.isupper() and len(first_content) > 4:
            auto_title = first_content
        # Arabic: isupper() never triggers Ã¢Â€Â” use first short line as title
        elif is_arabic and self._is_arabic_content(first_content) and 4 < len(first_content) <= 80:
            auto_title = first_content
        # Use auto-detected title if no explicit title provided (or title is just filename)
        effective_title = auto_title or doc_title

        if effective_title:
            tp = doc.add_paragraph(effective_title, style='Title')
            tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # Remove bottom border and tighten spacing on the Title style
            _tp_pPr = tp._p.get_or_add_pPr()
            _tp_pBdr = _tp_pPr.find(qn('w:pBdr'))
            if _tp_pBdr is not None:
                _tp_pPr.remove(_tp_pBdr)
            _tp_pBdr2 = OxmlElement('w:pBdr')
            _tp_bot = OxmlElement('w:bottom')
            _tp_bot.set(qn('w:val'), 'none')
            _tp_bot.set(qn('w:sz'), '0')
            _tp_bot.set(qn('w:space'), '0')
            _tp_bot.set(qn('w:color'), 'auto')
            _tp_pBdr2.append(_tp_bot)
            _tp_pPr.append(_tp_pBdr2)
            # Reduce the large default spacing the Title style has
            tp.paragraph_format.space_before = Pt(0)
            tp.paragraph_format.space_after = Pt(6)
            if is_arabic:
                self._apply_arabic_paragraph(tp, arabic_font, justify=False)
            # Skip the first line if it was used as title
            if auto_title and lines_raw and lines_raw[0].strip() in (auto_title, '# ' + auto_title):
                lines_raw = lines_raw[1:]

        # -- Render lines --------------------------------------------------
        lines = lines_raw
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if not s:
                i += 1
                continue

            added_para = None  # track last paragraph for Arabic post-processing

            # -- Arabic-specific patterns (before generic Latin patterns) ----
            if is_arabic and re.match(r'^\d+\.\s+[\u0600-\u06FF]', s):
                # Arabic numbered section heading: "1. ???????"
                p = doc.add_paragraph(style='Heading 2')
                self._add_formatted_runs(p, s)
                added_para = p

            elif is_arabic and re.match(r'^[IVX]+\.\s+[\u0600-\u06FF]', s):
                # Roman-numeral section heading: "I. ???????" "IV. ???..."
                p = doc.add_paragraph(style='Heading 1')
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._add_formatted_runs(p, s)
                added_para = p

            elif is_arabic and re.match(
                r'^[\u0600-\u06FF]{2,8}[\u064B-\u065F]?\s*:',
                s
            ):
                # Arabic ordinal section: "?????: ??????? ??????? ?????"
                p = doc.add_paragraph(style='Heading 1')
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._add_formatted_runs(p, s)
                added_para = p

            elif is_arabic and re.match(r'^\.\d+\s+[\u0600-\u06FF]', s):
                # Reversed Arabic sub-section numbering: ".1 ???? ????? ??????????"
                p = doc.add_paragraph(style='Heading 3')
                self._add_formatted_runs(p, s)
                added_para = p

            elif is_arabic and s and s[0] in '\u2022\u25CF\u2013\u2014':
                # Unicode bullet/dash lines: "Ã¢Â€Â¢ ?????? ?? ????? ???????"
                p = doc.add_paragraph(style='List Bullet')
                self._add_formatted_runs(p, s[1:].strip())
                added_para = p

            elif is_arabic and s.startswith('(') and s.endswith(')') and self._is_arabic_content(s):
                # Arabic parenthetical subtitle: "(?????? ???????)"
                p = doc.add_paragraph(style='Heading 2')
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._add_formatted_runs(p, s)
                added_para = p

            elif is_arabic and (s.endswith(':') or s.endswith('\u003A')) \
                    and not re.match(r'^\d', s) and 2 <= len(s) <= 80:
                # Arabic colon-header: "???:" "??? ??:" "??? ??????? ??? ???:"
                p = doc.add_paragraph(style='Heading 3')
                self._add_formatted_runs(p, s)
                added_para = p

            elif is_arabic and len(s) <= 3 and re.match(r'^[\u0600-\u06FF\s]+$', s):
                # Ultra-short Arabic connector: "?" (and), "??"
                p = doc.add_paragraph(s)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                added_para = p

            elif is_arabic and 4 <= len(s) <= 15 and not re.match(r'^\d', s) \
                    and not re.search(r'[,\u060c.\u061f!]', s):
                # Short (<=3 words, no punctuation) mostly-Arabic line -> salutation/section
                _has_quotes = any(c in s for c in ('"', '\u201c', '\u201d', "'", '\u00ab', '\u00bb'))
                _ar_count = sum(1 for c in s if '\u0600' <= c <= '\u06FF')
                _word_count = len(s.split())
                if (not _has_quotes
                        and _ar_count / max(len(s.replace(' ', '')), 1) > 0.7
                        and _word_count <= 3):
                    p = doc.add_paragraph(style='Heading 2')
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    self._add_formatted_runs(p, s)
                    added_para = p
                else:
                    para = doc.add_paragraph()
                    para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    self._add_formatted_runs(para, s)
                    added_para = para

            elif is_arabic and re.match(
                r'^[\u0600-\u06FF]{2,12}(?:\s+[\u0600-\u06FF]{2,12}){0,3}\s*(?::|_+|\.{3,})\s*$',
                s
            ):
                # Arabic signature/field line: e.g. "Ø§Ù„Ø§Ø³Ù…: ___" "Ø§Ù„ØªÙˆÙ‚ÙŠØ¹: ...."
                para = doc.add_paragraph()
                self._add_formatted_runs(para, s)
                added_para = para

            # -- Markdown headings --------------------------------------------
            elif s.startswith('### '):
                added_para = doc.add_paragraph(s[4:].strip(), style='Heading 3')
            elif s.startswith('## '):
                added_para = doc.add_paragraph(s[3:].strip(), style='Heading 2')
            elif s.startswith('# '):
                added_para = doc.add_paragraph(s[2:].strip(), style='Heading 1')

            # Bullet list
            elif s.startswith('- ') or s.startswith('* '):
                added_para = doc.add_paragraph(s[2:].strip(), style='List Bullet')

            # Horizontal rule
            elif s in ('---', '***', '___'):
                doc.add_paragraph()

            # Markdown table
            elif s.startswith('|') and i + 1 < len(lines) and re.match(r'^[\|\s\-:]+$', lines[i + 1].strip()):
                _w_headers = [c.strip() for c in s.split('|')[1:-1]]
                cols = len(_w_headers)
                if cols:
                    tbl = doc.add_table(rows=1, cols=cols)
                    tbl.style = 'Table Grid'
                    hdr_row = tbl.rows[0].cells
                    for j, h in enumerate(_w_headers):
                        hdr_row[j].text = h
                        for run in hdr_row[j].paragraphs[0].runs:
                            run.bold = True
                        if is_arabic:
                            self._apply_arabic_paragraph(hdr_row[j].paragraphs[0], arabic_font)
                    i += 2
                    _w_data_rows = []
                    while i < len(lines) and lines[i].strip().startswith('|'):
                        cells = [c.strip() for c in lines[i].strip().split('|')[1:-1]]
                        row = tbl.add_row().cells
                        for j, cv in enumerate(cells[:cols]):
                            row[j].text = cv
                            if is_arabic:
                                self._apply_arabic_paragraph(row[j].paragraphs[0], arabic_font)
                        _w_data_rows.append(cells)
                        i += 1
                    # Auto-embed chart when the table contains numeric data
                    if len(_w_data_rows) >= 2:
                        _wc_bytes = self._make_chart_png(_w_headers, _w_data_rows)
                        if _wc_bytes:
                            import tempfile as _wtmp, os as _wos
                            _wtf = _wtmp.NamedTemporaryFile(suffix='.png', delete=False)
                            _wtf.write(_wc_bytes)
                            _wtf.close()
                            try:
                                doc.add_paragraph()
                                _wpic = doc.add_picture(_wtf.name, width=Inches(5.5))
                                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                            except Exception:
                                pass
                            finally:
                                try:
                                    _wos.unlink(_wtf.name)
                                except Exception:
                                    pass
                    continue

            # Numbered section heading: "1. Title" (short line = 60 chars)
            elif re.match(r'^\d+\.\s+[A-Z]', s) and len(s) <= 60:
                p = doc.add_paragraph(style='Heading 2')
                self._add_formatted_runs(p, s)
                added_para = p

            # Numbered section heading with body merged: "1. Title Body text..."
            # Split into Heading 2 + justified body paragraph
            elif re.match(r'^\d+\.\s+[A-Z]', s) and len(s) > 60:
                hm = re.match(r'^(\d+\.\s+(?:[A-Z][a-zA-Z]*\s*){1,5}?)([A-Z][a-z].+)$', s, re.DOTALL)
                if hm:
                    p_head = doc.add_paragraph(style='Heading 2')
                    self._add_formatted_runs(p_head, hm.group(1).strip())
                    p_body = doc.add_paragraph()
                    p_body.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    self._add_formatted_runs(p_body, hm.group(2).strip())
                    if is_arabic:
                        self._apply_arabic_paragraph(p_head, arabic_font, justify=False)
                        self._apply_arabic_paragraph(p_body, arabic_font, justify=True)
                else:
                    p = doc.add_paragraph(style='Heading 2')
                    self._add_formatted_runs(p, s)
                    added_para = p

            # ALL-CAPS line that isn't the title (subtitle / section label)
            elif s.isupper() and 4 < len(s) < 100 and s != effective_title:
                p = doc.add_paragraph(style='Heading 1')
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._add_formatted_runs(p, s)
                added_para = p

            # Signature block lines Ã¢Â€Â” monospace-friendly, no justification
            elif re.match(r'^(signed\s*:|for\s+\w|name\s*:|title\s*:|date\s*:|signature\s*:)', s, re.IGNORECASE):
                para = doc.add_paragraph()
                self._add_formatted_runs(para, s)
                added_para = para

            # Title-Case section heading heuristic (English/Latin only).
            # Detects lines like "Multi-Step Plan Execution" or "Desktop Automation (Screen Vision)"
            # that look like section titles but weren't explicitly marked with # or ALL-CAPS.
            # Rules: short (=60 chars), no colon, no ?, starts with uppercase,
            # and =85% of non-first words are also Title-Cased (not a sentence).
            elif (
                not is_arabic
                and len(s) <= 60
                and not s.endswith('.')
                and ':' not in s
                and '?' not in s
                and s[0].isupper()
                and len(s.split()) >= 2
            ):
                _nonfirst_words = [w.strip('()[]{}.,;:!?&-_') for w in s.split()[1:]]
                _nonfirst_words = [w for w in _nonfirst_words if w]
                if _nonfirst_words and (
                    sum(1 for w in _nonfirst_words if w[0].isupper()) / len(_nonfirst_words) >= 0.85
                ):
                    added_para = doc.add_paragraph(style='Heading 2')
                    self._add_formatted_runs(added_para, s)
                else:
                    para = doc.add_paragraph()
                    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    self._add_formatted_runs(para, s)
                    added_para = para

            # Normal body paragraph
            else:
                para = doc.add_paragraph()
                para.alignment = WD_ALIGN_PARAGRAPH.RIGHT if is_arabic else WD_ALIGN_PARAGRAPH.JUSTIFY
                self._add_formatted_runs(para, s)
                added_para = para

            # Apply Arabic RTL to the last added paragraph.
            # Body paragraphs get justify=True (full justification from right edge).
            # Headings, titles, connectors keep justify=False (right-aligned).
            if is_arabic and added_para is not None:
                _sname = (added_para.style.name if added_para.style else '') or ''
                _is_body_para = not ('Heading' in _sname or _sname in ('Title', 'List Bullet'))
                self._apply_arabic_paragraph(added_para, arabic_font, justify=_is_body_para)

            i += 1

        # -- Final RTL enforcement pass (Arabic documents only) ----------------
        # Re-visits every paragraph in the document to guarantee that RTL
        # alignment and font settings are applied Ã¢Â€Â” catches any paragraph that
        # may have been created outside the main loop or missed the per-line call.
        if is_arabic:
            for _fp in doc.paragraphs:
                if not (_fp.text or '').strip():
                    continue   # skip blank paragraphs
                _fsn = (_fp.style.name if _fp.style else '') or ''
                # Preserve intentional center (title / roman-numeral headings)
                from docx.oxml.ns import qn as _qn
                _fpPr = _fp._p.find(_qn('w:pPr'))
                _fjc = _fpPr.find(_qn('w:jc')) if _fpPr is not None else None
                _fjc_val = _fjc.get(_qn('w:val')) if _fjc is not None else None
                if _fjc_val == 'center':
                    continue   # already explicitly centered Ã¢Â€Â” leave alone
                _fis_body = not ('Heading' in _fsn or _fsn in ('Title', 'List Bullet'))
                self._apply_arabic_paragraph(_fp, arabic_font, justify=_fis_body)

        try:
            doc.save(filepath)
            return filepath, None
        except Exception as e:
            return None, str(e)

    def _reformat_flat_document_text(self, text):
        """
        Reconstruct paragraph structure from flat (newline-collapsed) document text.
        Handles legal agreements, reports, and general structured documents.
        """
        t = (text or "").strip()
        if not t:
            return t

        # -- Arabic flat text: split at sentence boundaries -----------------
        # Arabic legal/formal text: smart restructuring even when partially structured.
        if self._is_arabic_content(t):
            # -- Ensure legal section labels are always on their own line ------
            # Patterns: "???:", "??? ??:", "???:", "?????:", "?????:", "??????:", etc.
            _ar_label_pat = (
                r'(?<!\n)'                                    # not already after newline
                r'('
                r'[\u0600-\u06FF]{2,12}(?:\s+[\u0600-\u06FF]{2,12}){0,3}\s*:'
                r'|[\u0600-\u06FF]{2,12}(?:\s+[\u0600-\u06FF]{2,12}){0,2}\s+\d+'
                r')'
            )
            t = re.sub(_ar_label_pat, r'\n\1', t)
            # -- Standalone structural "?" (AND between parties) ? own line ---
            # "??" is always inline "or" Ã¢Â€Â” never split it.
            # Only split standalone "?" surrounded by spaces (party separator),
            # not prefix "?" attached to a word (?????? ?????? etc.).
            t = re.sub(
                r'(?<!\n) ([\u0600-\u06FF]{1,6}) (?=[\u0600-\u06FF])',
                r'\n\1\n', t)
            # -- Split at sentence endings only Ã¢Â€Â” NOT at commas --------------
            # Arabic legal text uses ? heavily within sentences; splitting there
            # breaks party descriptions into many short fragments.
            if t.count('\n') < 3:
                t = re.sub(r'([.??!])\s+(?=[\u0600-\u06FF])', r'\1\n', t)
            # -- Signature / closing lines ? own line -----------------------
            t = re.sub(
                r'(?<!\n)([\u0600-\u06FF]{3,12}(?:\s+[\u0600-\u06FF]{2,12}){0,3}\s*:)',
                r'\n\1', t
            )
            t = re.sub(r'\n{3,}', '\n\n', t)
            return t.strip()

        # -- Numbered sections ---------------------------------------------
        # Split "1. Heading Body text here..." ? "1. Heading\nBody text here..."
        # Pattern: digit.space + 1-5 Title-Case words (section title) + sentence body
        def split_section(m):
            num   = m.group(1)   # e.g. "1. "
            rest  = m.group(2)   # e.g. "Background Whereas the parties..."
            # Try to split at first word boundary where body text begins
            # Heading = consecutive Title-Case or ALL-CAPS words (1-5)
            hm = re.match(r'^((?:[A-Z][a-zA-Z]*\s+){1,5}?(?:[A-Z][a-zA-Z]*))(\s+[A-Z].+)$', rest, re.DOTALL)
            if hm:
                return f'\n\n{num}{hm.group(1)}\n{hm.group(2).strip()}'
            return f'\n\n{num}{rest}'

        t = re.sub(r'\s+(\d+\.\s+)([A-Z].+?)(?=\s+\d+\.\s+[A-Z]|\s*$)',
                   lambda m: split_section(m), t, flags=re.DOTALL)

        # -- Party separator "AND Mr./Ms." ---------------------------------
        t = re.sub(r'\s+(AND\s+(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+[A-Z])', r'\n\n\1', t)

        # -- Signature block markers ---------------------------------------
        t = re.sub(
            r'\s+(Signed\s*:|For\s+(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+[A-Z]|For\s+[A-Z]{2}|'
            r'Name\s*:|Title\s*:|Date\s*:|Signature\s*:)',
            r'\n\1', t
        )

        # -- Clean up extra blank lines ------------------------------------
        t = re.sub(r'\n{3,}', '\n\n', t)

        return t.strip()

    def _is_capability_question(self, text):
        low = (text or "").strip().lower()
        if not low:
            return False
        # Must reference a file/folder concept â€” otherwise any "?" question gets hijacked.
        _has_file_concept = bool(re.search(
            r'\b(file|folder|directory|create|make|document|pdf|word|docx?|txt|copy|move|delete|rename)\b', low
        ))
        if not _has_file_concept:
            return False
        return bool(
            re.search(
                r'^\s*(can you|could you|are you able to|able to|do you know how to|is it possible to|is it possible|can i|could i)\b',
                low,
            )
            or low.endswith("?")
        )

    def _has_explicit_target(self, text):
        t = (text or "").strip()
        low = t.lower()
        if not t:
            return False
        if re.search(r'["\']\s*[^"\']+\s*["\']', t):
            return True
        if re.search(r'\b(named|called|titled?|file\s+name|folder\s+name)\b', low):
            return True
        if re.search(r'[A-Za-z]:\\', t):
            return True
        if re.search(r'\.[a-z0-9]{2,5}\b', low):
            return True
        if re.search(r'\b(on|in|inside|into)\s+(the\s+)?(desktop|documents|downloads|folder|drive|c:|d:|e:)\b', low):
            return True
        return False

    def _handle_word_command(self, user_input, allow_desktop=False, allow_mutation=False):
        """
        Handle commands like:
          'create word document called X and write: ...'
          'open word and write: ...'
          'make a Word file named X'
        """
        raw = (user_input or "").strip()
        if not raw:
            return None

        low = raw.lower()

        # Capability question without an explicit filename -> let the AI answer conversationally.
        _is_question = bool(re.search(
            r'\b(can you|could you|do you|are you able|how do you|what is|is it possible)\b', low
        ))
        _has_explicit_name = bool(re.search(r'\b(called|named|titled?)\s+\S', low))
        if _is_question and not _has_explicit_name:
            return None

        # PDF and folder requests belong to their own handlers.
        if re.search(r'\b(pdf|\.pdf)\b', low.split(':')[0][:300]):
            return None
        if re.search(r'\b(folder|directory|dir)\b', low) and not re.search(r'\b(word|docx?|\.docx?|document|report)\b', low):
            return None
        # Plain text file is not a Word doc.
        if re.search(r'\b(txt|text\s+file|\.txt|plain\s+text)\b', low) and not re.search(r'\b(word|docx?|\.docx?)\b', low):
            return None

        # Must explicitly mention Word/doc â€” "file" alone is too generic.
        _has_word_ref = bool(re.search(r'(word|docx?|\.docx?)', low))
        _has_doc_ref = bool(re.search(r'(document|report)', low))
        _has_write_intent = bool(re.search(
            r'(write|save|put|add|create|make|generate|draft|prepare|export|open|give|build|produc\w*)', low))
        if not _has_word_ref and not (_has_doc_ref and _has_write_intent):
            return None
        # Must have a creation/action verb â€” accept typos like "creat", "crete"
        if not re.search(
            r'(creat\w*|make|open|write|save|put|add|start|new|build|generat\w*|produc\w*|draft\w*|prepar\w*|export\w*|give|convert\w*)',
            low
        ):
            return None

        # Extract filename and content
        # Patterns: "create word doc called/named X and write/with content: Y"
        name = None
        content = ""

        # -- Handle "write what you sent/said/have sent" ? last AI response -----
        # Handles auxiliary verbs: "what you have sent", "what you've said", etc.
        _last_resp_pat = re.compile(
            r'\b(?:write|put|save|add|create)\s+'
            r'(?:what\s+(?:(?:you|u)(?:\'?ve)?\s+(?:have\s+)?|(?:have|had)\s+(?:you|u)\s+)(?:just\s+)?(?:sent|said|wrote|written|replied?|gave|given)'
            r'|(?:the\s+)?(?:last|previous|latest)\s+(?:response|answer|message|reply|result|thing)'
            r'|your\s+(?:last|previous|latest)\s+(?:response|answer|message|reply)'
            r'|(?:last|previous)\s+(?:answer|response|message|reply))',
            re.IGNORECASE
        )
        if _last_resp_pat.search(low) and not content:
            # Search mode-specific history first, then fall back to combined history
            _mode_hist = getattr(self, 'task_conversation_history', []) if getattr(self, 'input_mode', 'chat') == 'task' else []
            _all_hist = _mode_hist or getattr(self, 'conversation_history', [])
            for msg in reversed(_all_hist):
                last_ai = (msg.get('assistant') or msg.get('content') or '').strip()
                if last_ai:
                    content = self._strip_ai_sources(last_ai)
                    break
            if not content:
                for msg in reversed(getattr(self, 'conversation_history', [])):
                    last_ai = (msg.get('assistant') or msg.get('content') or '').strip()
                    if last_ai:
                        content = self._strip_ai_sources(last_ai)
                        break

        # -- Handle "write this inside filename.docx : content" --------------
        # e.g. "write this inside hich.docx : ?????: ???????..."
        write_into_m = re.search(
            r'\bwrite\s+(?:this\s+)?inside\s+([^\s:,]+\.docx?)\s*[:\-]?\s*',
            raw, re.IGNORECASE
        )
        if write_into_m:
            name = os.path.splitext(write_into_m.group(1))[0]
            content = raw[write_into_m.end():].strip()

        name_m = re.search(
            r'\b(?:called|named|titled?|name(?:d)?(?:\s+it)?|file\s+name(?:d)?)\s+["\']?([^"\',:]+?)["\']?\s*(?:and|with|write|$)',
            raw, re.IGNORECASE
        )
        if name_m and not name:
            name = name_m.group(1).strip(" \"'.,")
            # Sanitize illegal Windows filename characters and cap length
            name = re.sub(r'[\\/*?:"<>|]', '', name).strip()[:100]

        # Extract content Ã¢Â€Â” match the LAST occurrence of a content-start marker
        # so "write this with good layout :" correctly finds the real content start
        content_markers = [
            # "write this inside word doc on my desktop : content"
            # "write this in word doc on my desktop : content"
            # Ã¢Â€Â” skip any phrase between "inside/in" and the colon
            r'\bwrite\s+this\s+inside\s+[^:\n]+[:\-]\s*',
            r'\bwrite\s+this\s+in\s+[^:\n]+[:\-]\s*',
            r'\bwrite\s+this\s+inside\s*[:\-]?\s*',
            r'\bwrite\s+inside\s+it\s+this\s*[:\-]?\s*',
            r'\bwrite\s+inside\s+this\s*[:\-]?\s*',
            r'\bwrite\s+inside\s*[:\-]?\s*',
            # "write this content :" / "write this here :" / "write this :" etc.
            r'\bwrite\s+this\s+\w{1,12}\s*[:\-]\s*',
            r'\bwrite\s+this\s*[:\-]\s*',
            r'\bwrite\s+this\s+(?:with\s+(?:\w+\s+)*?)?(?:good\s+)?(?:layout|format|formatting)\s*[:\-]?\s*',
            r'\bwrite\s+(?:this\s+)?(?:with\s+(?:\w+\s+)*?)?(?:good\s+)?(?:layout|format|formatting)\s*[:\-]?\s*',
            r'\bwrite\s*[:\-]\s*',
            r'\bcontent\s*[:\-]\s*',
            r'\binside\s+(?:this|it|that)\s*[:\-]\s*',
            r'\binside\s*[:\-]\s*',
            # "with the following content/text/information:"
            r'\bwith\s+(?:the\s+)?following\s+(?:content|text|information|details?)\s*[:\-]?\s*',
            # "the following:" / "following:"
            r'\b(?:the\s+)?following\s*[:\-]\s*',
            # "put/add this inside:" / "put inside:"
            r'\b(?:put|add)\s+(?:this\s+)?inside\s*[:\-]?\s*',
            # "with content/text:" (without "this")
            r'\bwith\s+(?:the\s+)?(?:content|text)\s*[:\-]\s*',
        ]
        if not content:  # don't overwrite content already extracted by write_into_m
            for marker_pat in content_markers:
                m = re.search(marker_pat + r'(.+)$', raw, re.IGNORECASE | re.DOTALL)
                if m and m.group(1).strip():
                    content = m.group(1).strip()
                    break

        # Guard: if this is just a capability question (no filename/content), don't create.
        if self._is_capability_question(raw) and not name and not content:
            return (
                "Yes â€” I can create a Word document, but I won't do it without explicit approval. "
                "If you want me to create one, say for example: "
                "\"Create a Word document called X and write: ...\""
            )

        # -- Bare pronoun fallback: "write this/that/it in word doc" ------------
        # When no inline content was provided and user says "this/it/that",
        # they're referring to the previous AI response Ã¢Â€Â” pull it from history.
        if not content and re.search(
            r'\b(this|that|it|the\s+last|what\s+(?:(?:you|u)(?:\'?ve)?\s+(?:have\s+)?|(?:have|had)\s+(?:you|u)\s+)(?:sent|said|wrote|written|gave|given))\b',
            low
        ):
            _mode_hist2 = getattr(self, 'task_conversation_history', []) if getattr(self, 'input_mode', 'chat') == 'task' else []
            _all_hist2 = _mode_hist2 or getattr(self, 'conversation_history', [])
            for msg in reversed(_all_hist2):
                last_ai = (msg.get('assistant') or msg.get('content') or '').strip()
                if last_ai:
                    content = self._strip_ai_sources(last_ai)
                    break
            # Only fall back if we used task history and found nothing
            if not content and _mode_hist2:
                for msg in reversed(getattr(self, 'conversation_history', [])):
                    last_ai = (msg.get('assistant') or msg.get('content') or '').strip()
                    if last_ai:
                        content = self._strip_ai_sources(last_ai)
                        break

        # Guard: if a content marker was found but nothing followed it, don't create a blank document.
        _has_content_marker_w = any(re.search(mp, raw, re.IGNORECASE) for mp in content_markers)
        if _has_content_marker_w and not content:
            return "What would you like me to write inside the Word document? Please include the content after the colon."

        # Reconstruct structure: always run for Arabic (label detection regardless of newlines),
        # run for Latin only when content is fully flat (no newlines).
        if content:
            _is_ar_content = self._is_arabic_content(content)
            if _is_ar_content or '\n' not in content:
                content = self._reformat_flat_document_text(content)

        # Fallback name Ã¢Â€Â” try to auto-generate from first heading in content
        if not name:
            smart_name = None
            if content:
                # Look for first ## heading or first non-empty line
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('## '):
                        smart_name = line[3:].strip()
                    elif line.startswith('# '):
                        smart_name = line[2:].strip()
                    elif len(line) <= 60:
                        smart_name = line
                    else:
                        # Long body line Ã¢Â€Â” truncate at word boundary (= 50 chars)
                        truncated = line[:50].rsplit(' ', 1)[0].rstrip('.,;:')
                        if len(truncated) >= 8:
                            smart_name = truncated
                    if smart_name:
                        # Sanitize: remove chars illegal in Windows filenames + commas
                        smart_name = re.sub(r'[\\/*?:"<>|,]', '', smart_name).strip()[:50]
                        break
            if not smart_name and content:
                smart_name = self._generate_doc_title(content, fallback='')
                if smart_name:
                    smart_name = re.sub(r'[\\/*?:"<>|,]', '', smart_name).strip()[:50]
            name = smart_name if smart_name else f"Document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Ensure .docx extension
        if not name.lower().endswith('.docx'):
            name = name + '.docx'

        # Permission gate: creating Word documents requires explicit approval.
        if not allow_mutation:
            preview = ""
            if content:
                snippet = content.strip().splitlines()[0][:80]
                if snippet:
                    preview = f' Preview: "{snippet}..."'
            self._audit("file_mutation", "permission_requested", {"command": raw[:300], "type": "word_doc"})
            return self._set_pending_question(
                "Permission Required",
                f"Create Word document `{name}`?{preview}",
                [
                    {"label": "Allow once", "description": "Create this document now", "value": "allow"},
                    {"label": "Deny", "description": "Do not create the document", "value": "deny"},
                ],
                action="create_word_doc_confirm",
                payload={"user_input": raw, "allow_desktop": True},
                on_deny="Word document creation cancelled.",
            )

        # -- Try to extract save location from the command itself ------------
        # Only scan the COMMAND HEAD (before the content body begins) so that
        # location keywords like "desktop", "documents", or Windows paths that
        # appear inside the dictated content are not misinterpreted as save locations.
        _cmd_head = raw
        for _mp in content_markers:
            _lm = re.search(_mp, raw, re.IGNORECASE | re.DOTALL)
            if _lm:
                _cmd_head = raw[:_lm.start()]
                break
        _inline_folder, _inline_err = self._parse_save_location(_cmd_head)
        if not _inline_err and _inline_folder:
            # Location was specified inline Ã¢Â€Â” create immediately, no question
            try:
                os.makedirs(_inline_folder, exist_ok=True)
            except Exception:
                pass
            final_path = os.path.join(_inline_folder, name)
            saved_path, create_err = self._create_word_document(final_path, content, doc_title=name.replace('.docx', ''))
            if create_err:
                return f"Could not create document: {create_err}"
            try:
                os.startfile(saved_path)
            except Exception:
                pass
            return f"**Saved and opened** `{name}` in `{_inline_folder}`"

        # No location in command Ã¢Â€Â” default to Desktop, create immediately
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        try:
            os.makedirs(desktop, exist_ok=True)
        except Exception:
            pass
        final_path = os.path.join(desktop, name)
        saved_path, create_err = self._create_word_document(final_path, content, doc_title=name.replace('.docx', ''))
        if create_err:
            # Could not save to desktop Ã¢Â€Â” ask for location instead
            self._pending_doc_save = {"content": content, "name": name, "doc_title": name.replace('.docx', '')}
            return (
                f"Ready to create **`{name}`**. Where do you want to save it?\n"
                f"Say: *desktop* Ã‚Â· *documents* Ã‚Â· *downloads* Ã‚Â· *D drive* Ã‚Â· "
                f"a folder name Ã‚Â· or a full path."
            )
        try:
            os.startfile(saved_path)
        except Exception:
            pass
        return f"**Saved and opened** `{name}` on your Desktop"

    def _parse_save_location(self, user_input):
        """
        Convert a natural-language location answer into an absolute folder path.
        Returns (folder_path, error_message).
        """
        t = (user_input or "").strip()
        low = t.lower()

        # Cancel/discard
        if re.match(r'^(no|cancel|discard|dont save|don\'t save|nevermind|never mind)\s*$', low):
            return None, "cancelled"

        home = os.path.expanduser("~")

        # Common named locations
        loc_map = [
            (r'\bdesktop\b',        os.path.join(home, "Desktop")),
            (r'\bdocuments?\b',     os.path.join(home, "Documents")),
            (r'\bdownloads?\b',     os.path.join(home, "Downloads")),
            (r'\bpictures?\b',      os.path.join(home, "Pictures")),
            (r'\bmusic\b',          os.path.join(home, "Music")),
            (r'\bvideos?\b',        os.path.join(home, "Videos")),
            (r'\b(d\s*drive|local\s*d|d:\\?)\b', "D:\\"),
            (r'\b(c\s*drive|local\s*c|c:\\?)\b', "C:\\"),
            (r'\b(e\s*drive|local\s*e)\b',       "E:\\"),
        ]
        for pattern, path in loc_map:
            if re.search(pattern, low):
                return path, None

        # Explicit Windows path  e.g. "C:\Users\Adam\Projects"
        path_m = re.search(r'([A-Za-z]:\\[^\n"\']+)', t)
        if path_m:
            return path_m.group(1).strip().rstrip('\\'), None

        # "in the X folder" / "X folder" ? search Desktop + home for a matching dir
        folder_m = re.search(r'\b(?:in\s+(?:the\s+)?|inside\s+)?(\w[\w\s]{1,30}?)\s+folder\b', low)
        if folder_m:
            query = folder_m.group(1).strip()
            for root in (os.path.join(home, "Desktop"), home):
                try:
                    for entry in os.listdir(root):
                        if entry.lower() == query.lower() and os.path.isdir(os.path.join(root, entry)):
                            return os.path.join(root, entry), None
                except Exception:
                    pass
            return None, f"Could not find a folder named '{query}'. Please give a full path."

        # Bare word that is an existing folder on desktop
        if re.match(r'^[\w\s\-]+$', t) and len(t) <= 40:
            candidate = os.path.join(home, "Desktop", t.strip())
            if os.path.isdir(candidate):
                return candidate, None

        return None, f"I didn't understand '{t}' as a save location. Please say 'desktop', 'documents', a drive letter, or a full path."

    def _execute_word_creation(self, filepath, content, doc_title=None):
        """Create the Word doc at the given path and open it (used by legacy confirmed-action flow)."""
        saved_path, err = self._create_word_document(filepath, content, doc_title=doc_title)
        if err:
            return f"Could not create Word document: {err}"
        try:
            os.startfile(saved_path)
        except Exception:
            pass
        return f"**Word document created** and opened: `{os.path.basename(saved_path)}`"

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  DATA & ANALYTICS ENGINE
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def _is_data_analysis_intent(self, cmd_lower):
        """Detect data analysis / visualization / API fetch intents."""
        data_verbs = bool(re.search(
            r'\b(analyz[ei]|analyse|visuali[sz]|plot|chart|graph|draw|sketch'
            r'|stat(istic)?s?|describe|summar[yi][sz]|explore|inspect'
            r'|correlat[ei]|regression|trend|forecast|predict'
            r'|heatmap|histogram|scatter|boxplot|box\s+plot|violin'
            r'|bar\s+chart|pie\s+chart|line\s+chart|line\s+graph'
            r'|fetch\s+data|pull\s+data|get\s+data|retrieve\s+data'
            r'|api\s+data|live\s+data|real.?time\s+data'
            r'|load\s+csv|read\s+csv|open\s+csv|import\s+csv'
            r'|load\s+excel|read\s+excel|open\s+excel|import\s+excel'
            r'|pandas|numpy|matplotlib|seaborn|plotly'
            r'|mean|median|variance|std\s+dev|standard\s+deviation'
            r'|distribution|outlier|pivot|crosstab|group\s+by)\b',
            cmd_lower,
        ))
        data_objects = bool(re.search(
            r'\b(dataset|data\s+set|data\s+file|csv|\.csv|spreadsheet|dataframe|df)\b',
            cmd_lower,
        ))
        return data_verbs or data_objects

    def _pandas_analyze_file(self, file_path, user_request=""):
        """
        Load a CSV or Excel file with pandas and produce a comprehensive
        statistical report.  Returns (report_str, df_or_None).
        """
        try:
            import pandas as pd
            import numpy as np
        except ImportError:
            return "pandas/numpy not installed. Install them with: pip install pandas numpy", None

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".csv":
                # Try common encodings
                for enc in ("utf-8", "latin-1", "cp1252"):
                    try:
                        df = pd.read_csv(file_path, encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    return f"Could not decode CSV file: {file_path}", None
            elif ext in (".xlsx", ".xls"):
                df = pd.read_excel(file_path)
            else:
                return f"Unsupported file type for data analysis: {ext}", None
        except Exception as e:
            return f"Could not load file: {e}", None

        if df.empty:
            return "The file appears to be empty.", None

        # â”€â”€ Build report â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        lines = []
        lines.append(f"## Data Analysis: `{os.path.basename(file_path)}`\n")
        lines.append(f"**Shape:** {df.shape[0]:,} rows Ã— {df.shape[1]} columns\n")

        # Column overview
        col_types = []
        num_cols = df.select_dtypes(include=[float, int, "number"]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()
        date_cols = df.select_dtypes(include=["datetime"]).columns.tolist()
        for col in df.columns:
            dtype = str(df[col].dtype)
            nulls = df[col].isna().sum()
            null_pct = nulls / len(df) * 100
            col_types.append(f"  - **{col}** ({dtype}): {nulls:,} nulls ({null_pct:.1f}%)")
        lines.append("**Columns:**\n" + "\n".join(col_types) + "\n")

        # Numeric stats
        if num_cols:
            desc = df[num_cols].describe().round(4)
            lines.append("**Numeric Statistics:**\n```")
            lines.append(desc.to_string())
            lines.append("```\n")

            # Correlation (only if â‰¥2 numeric columns)
            if len(num_cols) >= 2:
                corr = df[num_cols].corr().round(3)
                # Show only strong correlations (|r| > 0.5)
                strong = []
                checked = set()
                for c1 in num_cols:
                    for c2 in num_cols:
                        if c1 == c2 or (c2, c1) in checked:
                            continue
                        checked.add((c1, c2))
                        r = corr.loc[c1, c2]
                        if abs(r) > 0.5:
                            direction = "positive" if r > 0 else "negative"
                            strong.append(f"  - `{c1}` â†” `{c2}`: r = {r:.3f} ({direction})")
                if strong:
                    lines.append("**Notable Correlations (|r| > 0.5):**\n" + "\n".join(strong) + "\n")

        # Categorical overview
        if cat_cols:
            cat_info = []
            for col in cat_cols[:5]:  # max 5 columns
                vc = df[col].value_counts().head(5)
                top = ", ".join([f"{v} ({c})" for v, c in vc.items()])
                cat_info.append(f"  - **{col}** â€” {df[col].nunique()} unique values. Top: {top}")
            lines.append("**Categorical Columns:**\n" + "\n".join(cat_info) + "\n")

        # Missing data summary
        total_missing = df.isna().sum().sum()
        if total_missing > 0:
            lines.append(f"**Missing Data:** {total_missing:,} total missing values across all columns.\n")
        else:
            lines.append("**Missing Data:** No missing values â€” dataset is complete.\n")

        # Dataset sample (first 3 rows)
        lines.append("**Sample (first 3 rows):**\n```")
        lines.append(df.head(3).to_string(index=False))
        lines.append("```")

        return "\n".join(lines), df

    def _generate_visualization(self, df, chart_type, x_col=None, y_col=None,
                                 title="", output_path=None):
        """
        Generate a chart from a DataFrame and save as PNG.
        Returns (saved_path, error_str).
        """
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return None, "matplotlib not installed. Install with: pip install matplotlib"

        try:
            import pandas as pd
            import numpy as np
        except ImportError:
            return None, "pandas not installed"

        num_cols = df.select_dtypes(include=[float, int, "number"]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        # Auto-select columns if not provided
        if x_col is None and cat_cols:
            x_col = cat_cols[0]
        if y_col is None and num_cols:
            y_col = num_cols[0]

        fig, ax = plt.subplots(figsize=(9, 5))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#F8FAFC")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#CBD5E1")
        ax.spines["bottom"].set_color("#CBD5E1")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5, color="#E2E8F0")
        ax.set_axisbelow(True)

        BLUE_PAL = ["#2563EB", "#60A5FA", "#1D4ED8", "#3B82F6", "#93C5FD",
                    "#1E40AF", "#BFDBFE", "#06B6D4", "#0E7490", "#38BDF8"]

        chart_type = (chart_type or "bar").lower()

        try:
            if chart_type in ("bar", "bar chart", "column chart"):
                if x_col and y_col and x_col in df.columns and y_col in df.columns:
                    data = df[[x_col, y_col]].dropna().head(20)
                    bars = ax.bar(data[x_col].astype(str), data[y_col],
                                  color=BLUE_PAL[:len(data)], edgecolor="white", linewidth=0.5)
                    ax.set_xlabel(x_col, color="#475569", fontsize=10)
                    ax.set_ylabel(y_col, color="#475569", fontsize=10)
                    for bar in bars:
                        h = bar.get_height()
                        ax.annotate(f"{h:,.1f}" if h < 1e6 else f"{h/1e6:.1f}M",
                                    xy=(bar.get_x() + bar.get_width() / 2, h),
                                    xytext=(0, 3), textcoords="offset points",
                                    ha="center", va="bottom", fontsize=8, color="#1E293B")
                    plt.xticks(rotation=30, ha="right", fontsize=8)
                elif num_cols:
                    df[num_cols[:6]].mean().plot(kind="bar", ax=ax, color=BLUE_PAL, edgecolor="white")
                    ax.set_ylabel("Mean", color="#475569", fontsize=10)
                    plt.xticks(rotation=30, ha="right", fontsize=8)

            elif chart_type in ("line", "line chart", "line graph", "trend"):
                if num_cols:
                    cols_to_plot = [y_col] if y_col and y_col in df.columns else num_cols[:4]
                    for i, col in enumerate(cols_to_plot):
                        ax.plot(df.index, df[col].ffill(),
                                label=col, color=BLUE_PAL[i % len(BLUE_PAL)],
                                linewidth=2, marker="o" if len(df) <= 30 else None,
                                markersize=4)
                    ax.legend(fontsize=9)
                    if x_col and x_col in df.columns:
                        ticks = df[x_col].astype(str).tolist()
                        step = max(1, len(ticks) // 10)
                        ax.set_xticks(df.index[::step])
                        ax.set_xticklabels(ticks[::step], rotation=30, ha="right", fontsize=8)

            elif chart_type in ("pie", "pie chart"):
                if x_col and y_col and x_col in df.columns and y_col in df.columns:
                    data = df[[x_col, y_col]].dropna().head(10)
                    ax.pie(data[y_col], labels=data[x_col].astype(str),
                           colors=BLUE_PAL[:len(data)], autopct="%1.1f%%",
                           startangle=140, pctdistance=0.85,
                           wedgeprops={"edgecolor": "white", "linewidth": 1.5})
                    ax.set_aspect("equal")
                elif num_cols and cat_cols:
                    g = df.groupby(cat_cols[0])[num_cols[0]].sum().head(8)
                    ax.pie(g.values, labels=g.index.astype(str),
                           colors=BLUE_PAL[:len(g)], autopct="%1.1f%%",
                           startangle=140, wedgeprops={"edgecolor": "white"})
                    ax.set_aspect("equal")

            elif chart_type in ("histogram", "hist"):
                col = y_col if y_col and y_col in df.columns else (num_cols[0] if num_cols else None)
                if col:
                    ax.hist(df[col].dropna(), bins=25, color="#2563EB",
                            edgecolor="white", linewidth=0.5, alpha=0.85)
                    ax.set_xlabel(col, color="#475569", fontsize=10)
                    ax.set_ylabel("Frequency", color="#475569", fontsize=10)

            elif chart_type in ("scatter", "scatter plot", "scatterplot"):
                if x_col and y_col and x_col in df.columns and y_col in df.columns:
                    ax.scatter(df[x_col], df[y_col], color="#2563EB",
                               alpha=0.6, s=40, edgecolors="white", linewidth=0.3)
                    ax.set_xlabel(x_col, color="#475569", fontsize=10)
                    ax.set_ylabel(y_col, color="#475569", fontsize=10)
                    # Add regression line
                    try:
                        m = np.polyfit(df[x_col].dropna(), df[y_col].dropna(), 1)
                        xr = np.linspace(df[x_col].min(), df[x_col].max(), 100)
                        ax.plot(xr, np.polyval(m, xr), color="#EF4444",
                                linewidth=1.5, linestyle="--", label="Trend")
                        ax.legend(fontsize=9)
                    except Exception:
                        pass

            elif chart_type in ("heatmap", "correlation"):
                if len(num_cols) >= 2:
                    corr = df[num_cols].corr().round(2)
                    im = ax.imshow(corr.values, cmap="RdYlBu_r", aspect="auto",
                                   vmin=-1, vmax=1)
                    ax.set_xticks(range(len(num_cols)))
                    ax.set_yticks(range(len(num_cols)))
                    ax.set_xticklabels(num_cols, rotation=45, ha="right", fontsize=8)
                    ax.set_yticklabels(num_cols, fontsize=8)
                    for i in range(len(num_cols)):
                        for j in range(len(num_cols)):
                            ax.text(j, i, f"{corr.values[i, j]:.2f}",
                                    ha="center", va="center", fontsize=7,
                                    color="white" if abs(corr.values[i, j]) > 0.5 else "#1E293B")
                    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

            elif chart_type in ("box", "boxplot", "box plot"):
                cols_to_box = [y_col] if y_col and y_col in df.columns else num_cols[:6]
                bp = ax.boxplot([df[c].dropna().values for c in cols_to_box],
                                labels=cols_to_box, patch_artist=True)
                for patch, color in zip(bp["boxes"], BLUE_PAL):
                    patch.set_facecolor(color)
                    patch.set_alpha(0.7)
                plt.xticks(rotation=30, ha="right", fontsize=8)

            else:
                # Fallback: bar
                if num_cols:
                    df[num_cols[:6]].mean().plot(kind="bar", ax=ax, color=BLUE_PAL, edgecolor="white")
                    ax.set_ylabel("Mean", color="#475569", fontsize=10)
                    plt.xticks(rotation=30, ha="right", fontsize=8)

        except Exception as e:
            plt.close(fig)
            return None, f"Chart rendering error: {e}"

        ax.set_title(title or chart_type.title(), color="#1E293B",
                     fontsize=13, fontweight="bold", pad=12)
        fig.tight_layout()

        if output_path is None:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title or chart_type).strip() or "Chart"
            output_path = os.path.join(desktop, f"{safe_title}.png")

        try:
            fig.savefig(output_path, dpi=150, bbox_inches="tight")
        except Exception as e:
            plt.close(fig)
            return None, f"Could not save chart: {e}"
        finally:
            plt.close(fig)

        return output_path, ""

    def _fetch_api_data(self, url, user_request="", timeout=15):
        """
        Fetch data from a public API URL and return structured content string.
        Supports JSON and plain-text responses.
        """
        try:
            import requests as _req
        except ImportError:
            return None, "requests library not installed. Install with: pip install requests"
        try:
            headers = {
                "User-Agent": "Opuntia/1.0 (data-fetch; +https://opuntia.ai)",
                "Accept": "application/json, text/plain, */*",
            }
            resp = _req.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct:
                import json as _json
                data = resp.json()
                # Summarise large JSON responses
                text = _json.dumps(data, ensure_ascii=False, indent=2)
                if len(text) > 6000:
                    text = text[:6000] + "\nâ€¦ (truncated)"
                return text, ""
            else:
                text = resp.text[:6000]
                return text, ""
        except Exception as e:
            return None, f"API fetch error: {e}"

    def _create_analytics_excel(self, df, output_path, title="Analysis"):
        """
        Create a professional Excel workbook from a pandas DataFrame:
        - Sheet 1: raw data with table formatting
        - Sheet 2: descriptive statistics
        - Sheet 3: correlation matrix (numeric columns only)
        Returns (saved_path, error_str).
        """
        try:
            import openpyxl as _xl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from openpyxl.formatting.rule import ColorScaleRule
            import pandas as pd
        except ImportError:
            return None, "openpyxl or pandas not installed"

        C_NAV  = "0F2044"
        C_WHT  = "FFFFFF"
        C_BLU  = "2563EB"
        C_ALT  = "EEF4FF"
        C_BRD  = "C4D4F0"

        def _side(c=C_BRD): return Side(style="thin", color=c)
        def _border(): return Border(left=_side(), right=_side(), top=_side(), bottom=_side())
        def _hdr_font(sz=11): return Font(name="Calibri", bold=True, color=C_WHT, size=sz)
        def _body_font(bold=False, sz=10): return Font(name="Calibri", bold=bold, size=sz)
        def _fill(color): return PatternFill("solid", fgColor=color)
        def _align(h="left", wrap=False): return Alignment(horizontal=h, vertical="center", wrap_text=wrap)

        try:
            wb = _xl.Workbook()

            # â”€â”€ Sheet 1: Raw Data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            ws_data = wb.active
            ws_data.title = "Data"
            # Write headers
            for ci, col in enumerate(df.columns, start=1):
                cell = ws_data.cell(row=1, column=ci, value=str(col))
                cell.font = _hdr_font()
                cell.fill = _fill(C_NAV)
                cell.alignment = _align("center")
                cell.border = _border()
            # Write data rows (max 5000 rows for performance)
            max_rows = min(len(df), 5000)
            for ri, row_data in enumerate(df.head(max_rows).itertuples(index=False), start=2):
                for ci, val in enumerate(row_data, start=1):
                    cell = ws_data.cell(row=ri, column=ci, value=val)
                    cell.font = _body_font()
                    cell.fill = _fill(C_ALT if ri % 2 == 0 else C_WHT)
                    cell.border = _border()
                    cell.alignment = _align()
            # Auto-width columns
            for ci, col in enumerate(df.columns, start=1):
                max_len = max(len(str(col)), *(len(str(v)) for v in df[col].head(100).fillna("")))
                ws_data.column_dimensions[get_column_letter(ci)].width = min(max_len + 2, 40)
            ws_data.freeze_panes = "A2"

            # â”€â”€ Sheet 2: Statistics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            num_cols = df.select_dtypes(include=[float, int, "number"]).columns.tolist()
            if num_cols:
                ws_stat = wb.create_sheet("Statistics")
                desc = df[num_cols].describe().reset_index()
                for ci, col in enumerate(desc.columns, start=1):
                    cell = ws_stat.cell(row=1, column=ci, value=str(col))
                    cell.font = _hdr_font()
                    cell.fill = _fill(C_NAV)
                    cell.alignment = _align("center")
                    cell.border = _border()
                for ri, row_data in enumerate(desc.itertuples(index=False), start=2):
                    for ci, val in enumerate(row_data, start=1):
                        cell = ws_stat.cell(row=ri, column=ci,
                                            value=round(float(val), 4) if isinstance(val, (int, float)) and not pd.isna(val) else val)
                        cell.font = _body_font()
                        cell.fill = _fill(C_ALT if ri % 2 == 0 else C_WHT)
                        cell.border = _border()
                        cell.alignment = _align("center")
                for ci in range(1, len(desc.columns) + 1):
                    ws_stat.column_dimensions[get_column_letter(ci)].width = 16
                ws_stat.freeze_panes = "B2"

            # â”€â”€ Sheet 3: Correlation Matrix â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if len(num_cols) >= 2:
                ws_corr = wb.create_sheet("Correlation")
                corr = df[num_cols].corr().round(3)
                # Header row
                ws_corr.cell(row=1, column=1, value="").fill = _fill(C_NAV)
                for ci, col in enumerate(num_cols, start=2):
                    cell = ws_corr.cell(row=1, column=ci, value=col)
                    cell.font = _hdr_font(sz=10)
                    cell.fill = _fill(C_NAV)
                    cell.alignment = _align("center")
                    cell.border = _border()
                for ri, row_label in enumerate(num_cols, start=2):
                    cell = ws_corr.cell(row=ri, column=1, value=row_label)
                    cell.font = Font(name="Calibri", bold=True, size=10, color="1E293B")
                    cell.fill = _fill("D1D5DB")
                    cell.alignment = _align("center")
                    cell.border = _border()
                    for ci, col in enumerate(num_cols, start=2):
                        v = corr.loc[row_label, col]
                        cell = ws_corr.cell(row=ri, column=ci, value=float(v))
                        cell.font = _body_font()
                        cell.border = _border()
                        cell.alignment = _align("center")
                        cell.number_format = "0.000"
                # Color-scale conditional formatting on the data range
                if len(num_cols) >= 2:
                    data_range = (
                        f"B2:{get_column_letter(len(num_cols) + 1)}{len(num_cols) + 1}"
                    )
                    ws_corr.conditional_formatting.add(
                        data_range,
                        ColorScaleRule(
                            start_type="num", start_value=-1, start_color="FF4444",
                            mid_type="num",   mid_value=0,   mid_color="FFFFFF",
                            end_type="num",   end_value=1,   end_color="2563EB",
                        ),
                    )
                for ci in range(1, len(num_cols) + 2):
                    ws_corr.column_dimensions[get_column_letter(ci)].width = 14

            wb.save(output_path)
            return output_path, ""
        except Exception as e:
            return None, f"Excel creation error: {e}"

    def _handle_data_command(self, user_input, cmd_lower=None):
        """
        Handle data analysis, visualization, and API fetch commands.
        Returns a response string, or None if the command is not a data intent.
        """
        if cmd_lower is None:
            cmd_lower = user_input.lower()

        if not self._is_data_analysis_intent(cmd_lower):
            return None

        # Avoid hijacking simple doc-creation commands that mention csv/excel
        # in the context of "create an excel document from this content"
        if re.search(
            r'\b(create|make|write|generate|produce)\s+(a\s+|an\s+|new\s+)?(excel|xlsx?|spreadsheet|csv)\b',
            cmd_lower,
        ) and not re.search(
            r'\b(analyz[ei]|analyse|stat|plot|chart|graph|visuali[sz]|pandas|numpy|correlat[ei])\b',
            cmd_lower,
        ):
            return None  # let word/excel handler deal with it

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

        # â”€â”€ 1. API / live-data fetch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _url_m = re.search(r'https?://[^\s<>"\']+', user_input)
        if _url_m:
            url = _url_m.group(0).rstrip(".,;!?)")
            data_text, err = self._fetch_api_data(url, user_request=user_input)
            if err:
                return f"Could not fetch data from URL: {err}"
            # Ask AI to interpret
            prompt = (
                f"The user asked: {user_input}\n\n"
                f"Here is the raw API response:\n{data_text}\n\n"
                "Please analyze and present the key information clearly."
            )
            return self._call_ai([
                {"role": "system", "content": "You are a data analyst. Interpret API responses concisely."},
                {"role": "user", "content": prompt},
            ])

        # â”€â”€ 2. Resolve data file â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        data_file = None
        # Check recently referenced attachment
        if hasattr(self, "last_attachment_paths") and self.last_attachment_paths:
            for p in self.last_attachment_paths:
                if os.path.splitext(p)[1].lower() in (".csv", ".xlsx", ".xls"):
                    data_file = p
                    break
        # Check paths mentioned in user input
        if not data_file:
            local_paths = [p for p in self._extract_local_paths(user_input) if os.path.exists(p)]
            for p in local_paths:
                if os.path.splitext(p)[1].lower() in (".csv", ".xlsx", ".xls"):
                    data_file = p
                    break
        # Check desktop for mentioned filenames
        if not data_file:
            fname_m = re.search(r'[\w\-\.]+\.(csv|xlsx?)', user_input, re.IGNORECASE)
            if fname_m:
                candidate = os.path.join(desktop, fname_m.group(0))
                if os.path.exists(candidate):
                    data_file = candidate

        # â”€â”€ 3. Run analysis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if data_file:
            report, df = self._pandas_analyze_file(data_file, user_request=user_input)

            # Detect visualization request
            chart_type = None
            ct_m = re.search(
                r'\b(bar\s+chart|bar\s+graph|line\s+chart|line\s+graph|pie\s+chart|'
                r'histogram|scatter(?:\s+plot)?|heatmap|correlation\s+(?:map|matrix)|'
                r'boxplot|box\s+plot|violin)\b',
                cmd_lower,
            )
            if ct_m:
                chart_type = ct_m.group(1)
            elif re.search(r'\b(plot|chart|graph|visuali[sz]|draw)\b', cmd_lower):
                chart_type = "bar"  # sensible default

            chart_msg = ""
            if chart_type and df is not None:
                # Try to extract column names from user request
                x_col = y_col = None
                if df is not None:
                    all_cols_lower = {c.lower(): c for c in df.columns}
                    for col_lower, col_real in all_cols_lower.items():
                        if re.search(r'\b' + re.escape(col_lower) + r'\b', cmd_lower):
                            if x_col is None:
                                x_col = col_real
                            elif y_col is None:
                                y_col = col_real
                                break

                chart_title = re.sub(r'[\\/*?:"<>|]', '', os.path.splitext(os.path.basename(data_file))[0])
                chart_title = f"{chart_type.title()} â€” {chart_title}"
                chart_path = os.path.join(desktop, re.sub(r'\s+', '_', chart_title) + ".png")
                saved_chart, cerr = self._generate_visualization(
                    df, chart_type, x_col=x_col, y_col=y_col,
                    title=chart_title, output_path=chart_path,
                )
                if saved_chart:
                    try:
                        os.startfile(saved_chart)
                    except Exception:
                        pass
                    chart_msg = f"\n\n**Chart saved:** `{os.path.basename(saved_chart)}` on your Desktop"
                elif cerr:
                    chart_msg = f"\n\n(Chart generation failed: {cerr})"

            # Detect analytics Excel export request
            excel_msg = ""
            if re.search(r'\b(excel|xlsx?|spreadsheet|export|save)\b', cmd_lower) and df is not None:
                excel_name = re.sub(r'[\\/*?:"<>|]', '',
                                    os.path.splitext(os.path.basename(data_file))[0]) + "_Analysis.xlsx"
                excel_path = os.path.join(desktop, excel_name)
                saved_xl, xl_err = self._create_analytics_excel(df, excel_path,
                                                                  title=os.path.basename(data_file))
                if saved_xl:
                    try:
                        os.startfile(saved_xl)
                    except Exception:
                        pass
                    excel_msg = f"\n\n**Analytics Excel saved:** `{excel_name}` on your Desktop"
                elif xl_err:
                    excel_msg = f"\n\n(Excel export failed: {xl_err})"

            return report + chart_msg + excel_msg

        # â”€â”€ 4. No file â€” AI-powered data question â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # If user mentions stats/analytics concept but no file, answer with AI
        return None  # let intelligent_respond handle it

    def _handle_file_command(self, user_input, allow_desktop=False, allow_mutation=False, allow_outside_mcp=False):
        text = (user_input or "").strip()
        if not text:
            return None
        text = self._rewrite_natural_desktop_file_command(text)
        if self._is_capability_question(text) and not self._has_explicit_target(text):
            return (
                "Yes â€” I can create files or folders, but I won't do it without explicit approval. "
                "Tell me the name/location, for example: "
                "\"Create a folder called X on desktop\"."
            )
        is_mutation = self._is_mutating_file_command(text)
        if is_mutation and not allow_mutation:
            self._audit("file_mutation", "permission_requested", {"command": text[:300], "allow_desktop": bool(allow_desktop)})
            return self._set_pending_question(
                "Authorization required",
                "Allow this file operation?",
                [
                    {"label": "Allow once", "description": "Execute this file operation now", "value": "allow"},
                    {"label": "Deny", "description": "Do not execute this operation", "value": "deny"},
                ],
                action="file_mutation",
                payload={"command": text, "allow_desktop": bool(allow_desktop)},
                on_deny="File operation cancelled.",
            )
        if is_mutation and allow_mutation:
            self._audit("file_mutation", "allowed", {"command": text[:300]})

        def _outside_write_guard(path_value):
            if not path_value:
                return None
            if self._mcp_write_allowed(path_value):
                return None
            if allow_outside_mcp:
                return None
            if not allow_mutation:
                return "Path is outside MCP allowed directories and needs explicit confirmation."
            return self._set_pending_confirmation(
                "file_mutation_outside_allowed",
                {"command": text, "allow_desktop": bool(allow_desktop), "allow_outside_mcp": True},
                "This write target is outside MCP allowed directories. Continue anyway? (yes/no)",
            )

        m = re.match(r"^(?:list|show)\s+(?:all\s+)?files(?:\s+in\s+(.+))?$", text, flags=re.IGNORECASE)
        if m:
            folder, err = self._resolve_workspace_path((m.group(1) or ".").strip(), allow_desktop=allow_desktop)
            if err:
                return err
            if self._prefer_mcp_for_action("list_files"):
                ok, mcp_out = self._mcp_call_filesystem_tool("list_directory", {"path": folder}, action_key="list_files")
                if ok and mcp_out:
                    return f"Files in {os.path.relpath(folder, self.workspace_root)} (via MCP):\n{mcp_out}"
            if not os.path.isdir(folder):
                self._record_file_route_result("list_files", "local", False, error_text="folder not found")
                return "Folder not found."
            entries = sorted(os.listdir(folder))
            if not entries:
                self._record_file_route_result("list_files", "local", True)
                return f"No files found in {os.path.relpath(folder, self.workspace_root)}"
            lines = []
            for name in entries[:80]:
                lines.append(f"- {name}{'/' if os.path.isdir(os.path.join(folder, name)) else ''}")
            self._record_file_route_result("list_files", "local", True)
            return f"Files in {os.path.relpath(folder, self.workspace_root)}:\n" + "\n".join(lines)

        m = re.match(r"^(?:read|open|show)\s+file\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            path, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            if self._prefer_mcp_for_action("read_file"):
                ok, mcp_out = self._mcp_call_filesystem_tool("read_text_file", {"path": path}, action_key="read_file")
                if ok and mcp_out:
                    display_name = os.path.basename(path)
                    return f"**{display_name}**\n\n{mcp_out[:6000]}" + ("\n\n... (truncated - showing first 6000 characters)" if len(mcp_out) > 6000 else "")
            if not os.path.exists(path) or os.path.isdir(path):
                self._record_file_route_result("read_file", "local", False, error_text="file not found")
                return "File not found."
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if len(content) > 6000:
                    content = content[:6000] + "\n\n... (truncated Ã¢Â€Â” showing first 6000 characters)"
                display_name = os.path.basename(path)
                self._record_file_route_result("read_file", "local", True)
                return f"**{display_name}**\n\n{content}"
            except Exception as e:
                self._record_file_route_result("read_file", "local", False, error_text=str(e))
                return f"Could not read file: {e}"

        m = re.match(r"^(?:create|make)\s+(?:folder|directory)\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            path, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(path)
            if guard:
                return guard
            if self._prefer_mcp_for_action("create_folder"):
                ok, mcp_out = self._mcp_call_filesystem_tool("create_directory", {"path": path}, action_key="create_folder")
                if ok:
                    return f"Folder ready: {os.path.relpath(path, self.workspace_root)}" if not mcp_out else str(mcp_out)
            try:
                os.makedirs(path, exist_ok=True)
                self._record_file_route_result("create_folder", "local", True)
                return f"Folder ready: {os.path.relpath(path, self.workspace_root)}"
            except Exception as e:
                self._record_file_route_result("create_folder", "local", False, error_text=str(e))
                return f"Could not create folder: {e}"

        m = re.match(r"^(?:create|make)\s+file\s+(.+?)\s+with\s+content\s*[:\-]?\s*([\s\S]+)$", text, flags=re.IGNORECASE)
        if m:
            path, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(path)
            if guard:
                return guard
            if self._prefer_mcp_for_action("write_file"):
                payload = (m.group(2) or "").replace("\\n", "\n").replace("\\t", "\t")
                ok, mcp_out = self._mcp_call_filesystem_tool("write_file", {"path": path, "content": payload}, action_key="write_file")
                if ok:
                    return mcp_out or f"Saved file `{os.path.basename(path)}`."
            out = self._write_text_file(path, m.group(2), append=False)
            self._record_file_route_result("write_file", "local", False if str(out).lower().startswith("could not") else True, error_text=str(out))
            return out

        m = re.match(r"^(?:create|make)\s+file\s+(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            path, err = self._resolve_workspace_path(m.group(1).strip(), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(path)
            if guard:
                return guard
            if self._prefer_mcp_for_action("write_file"):
                ok, mcp_out = self._mcp_call_filesystem_tool("write_file", {"path": path, "content": ""}, action_key="write_file")
                if ok:
                    return mcp_out or f"Saved file `{os.path.basename(path)}`."
            out = self._write_text_file(path, "", append=False)
            self._record_file_route_result("write_file", "local", False if str(out).lower().startswith("could not") else True, error_text=str(out))
            return out

        m = re.match(r"^(?:write|overwrite|replace)\s+(?:to\s+)?file\s+(.+?)\s*[:\-]\s*(.+)$", text, flags=re.IGNORECASE)
        if m:
            path, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(path)
            if guard:
                return guard
            if self._prefer_mcp_for_action("write_file"):
                payload = (m.group(2) or "").replace("\\n", "\n").replace("\\t", "\t")
                ok, mcp_out = self._mcp_call_filesystem_tool("write_file", {"path": path, "content": payload}, action_key="write_file")
                if ok:
                    return mcp_out or f"Updated file `{os.path.basename(path)}`."
            out = self._write_text_file(path, m.group(2), append=False)
            self._record_file_route_result("write_file", "local", False if str(out).lower().startswith("could not") else True, error_text=str(out))
            return out

        m = re.match(r"^(?:append|add)\s+(?:to\s+)?file\s+(.+?)\s*[:\-]\s*(.+)$", text, flags=re.IGNORECASE)
        if m:
            path, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(path)
            if guard:
                return guard
            if self._prefer_mcp_for_action("write_file"):
                add_text = (m.group(2) or "").replace("\\n", "\n").replace("\\t", "\t")
                ok_read, prior = self._mcp_call_filesystem_tool("read_text_file", {"path": path}, action_key="write_file")
                combined = ((prior + "\n") if (ok_read and prior) else "") + add_text
                ok_write, mcp_out = self._mcp_call_filesystem_tool("write_file", {"path": path, "content": combined}, action_key="write_file")
                if ok_write:
                    return mcp_out or f"Updated file `{os.path.basename(path)}`."
            out = self._write_text_file(path, m.group(2), append=True)
            self._record_file_route_result("write_file", "local", False if str(out).lower().startswith("could not") else True, error_text=str(out))
            return out

        m = re.match(r"^(?:delete|remove)\s+(?:file|folder|directory)?\s*(.+)$", text, flags=re.IGNORECASE)
        if m:
            path, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(path)
            if guard:
                return guard
            if not os.path.exists(path):
                self._record_file_route_result("delete_path", "local", False, error_text="path not found")
                return "Path not found."
            try:
                fname = os.path.basename(path)
                location = "Desktop" if os.path.normcase(os.path.dirname(path)) == os.path.normcase(self.desktop_root) else os.path.dirname(path)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                    self._record_file_route_result("delete_path", "local", True)
                    return f"**Deleted** folder `{fname}` from {location}."
                os.remove(path)
                self._record_file_route_result("delete_path", "local", True)
                return f"**Deleted** file `{fname}` from {location}."
            except PermissionError as e:
                if getattr(e, "winerror", None) == 32:
                    fname = os.path.basename(path)
                    self._record_file_route_result("delete_path", "local", False, error_text="file in use")
                    return f"Cannot delete `{fname}` - it is open in another program. Please close it first, then try again."
                self._record_file_route_result("delete_path", "local", False, error_text=str(e))
                return f"Could not delete: {e}"
            except Exception as e:
                self._record_file_route_result("delete_path", "local", False, error_text=str(e))
                return f"Could not delete path: {e}"

        def _friendly_path(p):
            """Return a clean display name for a path."""
            if os.path.normcase(os.path.dirname(p)) == os.path.normcase(self.desktop_root):
                return f"Desktop/{os.path.basename(p)}"
            try:
                rel = os.path.relpath(p, self.desktop_root)
                if not rel.startswith(".."):
                    return f"Desktop/{rel}"
            except ValueError:
                pass
            return os.path.basename(p)

        def _resolve_loose(raw_name, allow_desktop):
            """Resolve a bare name (no path separators) by searching Desktop first."""
            raw_name = raw_name.strip(" \"'`.,")
            if os.sep in raw_name or "/" in raw_name or (len(raw_name) > 2 and raw_name[1] == ":"):
                return self._resolve_workspace_path(raw_name, allow_desktop=allow_desktop)
            # Try Desktop first
            if allow_desktop:
                candidate = os.path.join(self.desktop_root, raw_name)
                if os.path.exists(candidate):
                    return candidate, None
                # Try finding via _find_desktop_item_path
                found = self._find_desktop_item_path(raw_name)
                if found:
                    return found, None
            return self._resolve_workspace_path(raw_name, allow_desktop=allow_desktop)

        m = re.match(r"^(?:rename)\s+(?:file|folder|directory)?\s*(.+?)\s+to\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            src, err = _resolve_loose(m.group(1), allow_desktop)
            if err:
                return err
            new_name = m.group(2).strip(" \"'`.,")
            # If new_name is just a bare name (no path), place it beside the source
            if os.sep not in new_name and "/" not in new_name and not (len(new_name) > 2 and new_name[1] == ":"):
                dst = os.path.join(os.path.dirname(src), new_name)
            else:
                dst, err = self._resolve_workspace_path(new_name, allow_desktop=allow_desktop)
                if err:
                    return err
            guard = _outside_write_guard(dst)
            if guard:
                return guard
            if not os.path.exists(src):
                self._record_file_route_result("move_file", "local", False, error_text="source not found")
                return f"Could not find `{os.path.basename(src)}`."
            if os.path.exists(dst):
                self._record_file_route_result("move_file", "local", False, error_text="destination exists")
                return f"`{os.path.basename(dst)}` already exists."
            if self._prefer_mcp_for_action("move_file"):
                ok, mcp_out = self._mcp_call_filesystem_tool("move_file", {"source": src, "destination": dst}, action_key="move_file")
                if ok:
                    return mcp_out or f"Renamed to `{os.path.basename(dst)}`."
            try:
                os.rename(src, dst)
                kind = "Folder" if os.path.isdir(dst) else "File"
                self._record_file_route_result("move_file", "local", True)
                return f"**{kind} renamed:** `{os.path.basename(src)}` ? `{os.path.basename(dst)}` on {_friendly_path(os.path.dirname(dst))}."
            except Exception as e:
                self._record_file_route_result("move_file", "local", False, error_text=str(e))
                return f"Could not rename: {e}"

        m = re.match(r"^(?:move)\s+(?:file|folder|directory)?\s*(.+?)\s+to\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            src, err = _resolve_loose(m.group(1), allow_desktop)
            if err:
                return err
            dst_raw = m.group(2).strip(" \"'`.,")
            # Destination: if bare name exists as a folder on Desktop, move into it
            if os.sep not in dst_raw and "/" not in dst_raw and not (len(dst_raw) > 2 and dst_raw[1] == ":"):
                candidate_dir = os.path.join(self.desktop_root, dst_raw) if allow_desktop else os.path.join(self.workspace_root, dst_raw)
                if os.path.isdir(candidate_dir):
                    dst = os.path.join(candidate_dir, os.path.basename(src))
                else:
                    dst, err = self._resolve_workspace_path(dst_raw, allow_desktop=allow_desktop)
                    if err:
                        return err
            else:
                dst, err = self._resolve_workspace_path(dst_raw, allow_desktop=allow_desktop)
                if err:
                    return err
            guard = _outside_write_guard(dst)
            if guard:
                return guard
            if not os.path.exists(src):
                self._record_file_route_result("move_file", "local", False, error_text="source not found")
                return f"Could not find `{os.path.basename(src)}`."
            if self._prefer_mcp_for_action("move_file"):
                ok, mcp_out = self._mcp_call_filesystem_tool("move_file", {"source": src, "destination": dst}, action_key="move_file")
                if ok:
                    return mcp_out or f"Moved to `{os.path.basename(dst)}`."
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                kind = "Folder" if os.path.isdir(dst) else "File"
                self._record_file_route_result("move_file", "local", True)
                return f"**{kind} moved:** `{os.path.basename(src)}` ? {_friendly_path(dst)}."
            except Exception as e:
                self._record_file_route_result("move_file", "local", False, error_text=str(e))
                return f"Could not move: {e}"

        m = re.match(r"^(?:copy)\s+(?:file|folder|directory)?\s*(.+?)\s+to\s+(.+)$", text, flags=re.IGNORECASE)
        if m:
            src, err = self._resolve_workspace_path(m.group(1), allow_desktop=allow_desktop)
            if err:
                return err
            dst, err = self._resolve_workspace_path(m.group(2), allow_desktop=allow_desktop)
            if err:
                return err
            guard = _outside_write_guard(dst)
            if guard:
                return guard
            if not os.path.exists(src):
                self._record_file_route_result("copy_file", "local", False, error_text="source not found")
                return "Source path not found."
            if os.path.exists(dst):
                self._record_file_route_result("copy_file", "local", False, error_text="destination exists")
                return "Destination already exists."
            try:
                os.makedirs(os.path.dirname(dst) or self.workspace_root, exist_ok=True)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                    kind = "folder"
                else:
                    shutil.copy2(src, dst)
                    kind = "file"
                self._record_file_route_result("copy_file", "local", True)
                return f"Copied {kind}: {os.path.relpath(src, self.workspace_root)} -> {os.path.relpath(dst, self.workspace_root)}"
            except Exception as e:
                self._record_file_route_result("copy_file", "local", False, error_text=str(e))
                return f"Could not copy path: {e}"

        m = re.match(r"^(?:search|find)\s+files?\s+(?:for\s+)?(.+?)(?:\s+in\s+(.+))?$", text, flags=re.IGNORECASE)
        if m:
            pattern = (m.group(1) or "").strip()
            folder, err = self._resolve_workspace_path((m.group(2) or ".").strip(), allow_desktop=allow_desktop)
            if err:
                return err
            if self._prefer_mcp_for_action("search_files"):
                ok, mcp_out = self._mcp_call_filesystem_tool(
                    "search_files",
                    {"path": folder, "pattern": pattern},
                    action_key="search_files",
                )
                if ok and mcp_out:
                    return f"Search results for `{pattern}` (via MCP):\n{mcp_out}"
            if not os.path.isdir(folder):
                self._record_file_route_result("search_files", "local", False, error_text="folder not found")
                return "Folder not found."
            hits = []
            needle = pattern.lower()
            for root, dirs, files in os.walk(folder):
                for n in dirs + files:
                    if needle in n.lower():
                        hits.append(os.path.join(root, n))
                if len(hits) >= 80:
                    break
            if not hits:
                self._record_file_route_result("search_files", "local", True)
                return f"No matches for `{pattern}`."
            lines = []
            for h in hits[:80]:
                try:
                    lines.append(f"- {os.path.relpath(h, self.workspace_root)}")
                except Exception:
                    lines.append(f"- {h}")
            self._record_file_route_result("search_files", "local", True)
            return f"Search results for `{pattern}`:\n" + "\n".join(lines)

        return None

    def _rewrite_natural_desktop_file_command(self, text):
        """Convert natural desktop file/folder requests to canonical file commands."""
        raw = (text or "").strip()
        if not raw:
            return raw
        lower = raw.lower()

        # Example: "show/list files on desktop", "what is on my desktop"
        if re.search(r"\b(list|show|see|what(?:'s| is)|give me)\b", lower) and "desktop" in lower:
            if re.search(r"\b(file|files|folder|folders|items|everything)\b", lower) or "what is on" in lower or "what's on" in lower:
                return f"list files in {self.desktop_root}"
            if "list of desktop" in lower or "desktop list" in lower:
                return f"list files in {self.desktop_root}"
        if lower in {"desktop items", "desktop files", "desktop folders", "show desktop"}:
            return f"list files in {self.desktop_root}"

        # -- Read / show file content ------------------------------------------
        # "read me X", "read X", "show me the content of X", "what's inside X",
        # "what does X say", "open X and show content", "display X"
        _read_patterns = [
            re.compile(r"^read\s+(?:me\s+)?(?:the\s+)?(?:file\s+)?(.+?)(?:\s+(?:file|please|now))?\s*$", re.IGNORECASE),
            re.compile(r"^(?:show|display)\s+(?:me\s+)?(?:the\s+)?(?:content(?:s)?\s+of\s+|inside\s+)(?:file\s+)?(.+?)(?:\s+(?:file|please|now))?\s*$", re.IGNORECASE),
            re.compile(r"^(?:what(?:'s| is)\s+(?:inside|in)\s+)(?:file\s+)?(.+?)(?:\s+(?:file|please))?\s*$", re.IGNORECASE),
            re.compile(r"^(?:what\s+does\s+)(.+?)\s+(?:say|contain|have|include)\s*\??\s*$", re.IGNORECASE),
            re.compile(r"^open\s+(?:file\s+)?(.+?)\s+and\s+(?:show|read|display)\s+(?:(?:the\s+)?content(?:s)?|it|me)\s*$", re.IGNORECASE),
        ]
        for pat in _read_patterns:
            m = pat.match(raw)
            if m:
                target = m.group(1).strip(" \"'`.,")
                target = re.sub(r"\s+(file|doc|document)s?\s*$", "", target, flags=re.IGNORECASE).strip(" \"'`.,")
                if not target:
                    continue
                # Resolve to full Desktop path if the item exists there
                file_path = self._find_desktop_item_path(target)
                if not file_path:
                    # Try adding common extensions if bare name given
                    for ext in (".txt", ".md", ".json", ".csv", ".log"):
                        candidate = os.path.join(self.desktop_root, target + ext)
                        if os.path.exists(candidate):
                            file_path = candidate
                            break
                if file_path and os.path.isfile(file_path):
                    return f"read file {file_path}"
                elif target:
                    return f"read file {self.desktop_root}\\{target}"

        # Example: "create a folder on desktop called Test"
        m = re.match(
            r"^(?:create|make)\s+(?:a|an)?\s*(?:new\s+)?(?:folder|directory)\s+(?:on|in)\s+(?:(?:the|my)\s+)?desktop(?:\s+(?:called|named)\s+)?(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if m:
            folder_name = (m.group(1) or "").strip(" \"'`.,")
            if folder_name:
                return f"create folder {self.desktop_root}\\{folder_name}"

        # Example: "create a folder called Test on my desktop"
        m = re.match(
            r"^(?:create|make)\s+(?:a|an)?\s*(?:new\s+)?(?:folder|directory)\s+(?:called|named)?\s*(.+?)\s+(?:on|in)\s+(?:(?:the|my)\s+)?desktop$",
            raw,
            flags=re.IGNORECASE,
        )
        if m:
            folder_name = (m.group(1) or "").strip(" \"'`.,")
            if folder_name:
                return f"create folder {self.desktop_root}\\{folder_name}"

        # Unified desktop file creation Ã¢Â€Â” handles all natural content phrasings
        # Pattern A: "create file on desktop called X ..."
        # Pattern B: "create file called X on desktop ..."
        # Supports: txt/doc/any extension; auto-adds .txt when no extension given
        # Content separators: "with content:", "and write inside it:", "and write this:",
        #   "write inside it this:", "containing:", "with the following:", "and put inside it:",
        #   "and add:", "with text:", "fill it with:", "inside write:", and bare ":"
        _CONTENT_SEP = re.compile(
            r"\s+(?:"
            r"(?:and\s+)?(?:write|put|add|fill\s+it\s+with)\s+(?:inside\s+(?:it\s+)?(?:this\s*)?|this\s+inside\s+(?:it\s+)?)?|"
            r"(?:and\s+)?(?:containing|with\s+(?:content|text|the\s+following)|inside\s+write)\s*|"
            r"with\s+content\s*"
            r")[:\-]?\s*",
            re.IGNORECASE,
        )

        def _auto_ext(name):
            """Add .txt if the filename has no extension."""
            if name and "." not in os.path.basename(name):
                return name + ".txt"
            return name

        # Pattern A: "create [a] [new] file [on|in] [the|my] desktop [called|named] <name> [<sep> <content>]"
        # re.DOTALL so multiline pasted content is captured in full
        m = re.match(
            r"^(?:create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?file\s+"
            r"(?:on|in)\s+(?:(?:the|my)\s+)?desktop\s+"
            r"(?:(?:called|named)\s+)?(.+)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            rest = m.group(1).strip()
            parts = _CONTENT_SEP.split(rest, maxsplit=1)
            file_name = _auto_ext(parts[0].strip(" \"'`.,"))
            content = parts[1].strip() if len(parts) > 1 else ""
            if file_name:
                canonical = f"create file {self.desktop_root}\\{file_name}"
                return f"{canonical} with content: {content}" if content else canonical

        # Pattern B: "create [a] [new] file [called|named] <name> [on|in] [the|my] desktop [<sep> <content>]"
        m = re.match(
            r"^(?:create|make)\s+(?:a\s+|an\s+)?(?:new\s+)?file\s+"
            r"(?:called|named)?\s*(.+?)\s+"
            r"(?:on|in)\s+(?:(?:the|my)\s+)?desktop\s*([\s\S]*)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            name_part = m.group(1).strip(" \"'`.,")
            after_desktop = m.group(2).strip()
            # Content may follow the desktop location
            if after_desktop:
                content_m = _CONTENT_SEP.match(" " + after_desktop)
                content = after_desktop[content_m.end() - 1:].strip() if content_m else after_desktop
            else:
                # Content might be embedded in name_part Ã¢Â€Â” try splitting there too
                parts = _CONTENT_SEP.split(name_part, maxsplit=1)
                name_part = parts[0].strip(" \"'`.,")
                content = parts[1].strip() if len(parts) > 1 else ""
            file_name = _auto_ext(name_part)
            if file_name:
                canonical = f"create file {self.desktop_root}\\{file_name}"
                return f"{canonical} with content: {content}" if content else canonical

        def _clean_delete_target(t):
            """Strip leading articles/labels and trailing type words from a delete target name."""
            t = re.sub(r"^(?:the\s+|a\s+|an\s+)?(?:called|named)\s+", "", t, flags=re.IGNORECASE).strip()
            t = re.sub(r"\s+(?:folder|file|directory|dir)s?\s*$", "", t, flags=re.IGNORECASE).strip(" \"'`.,")
            return t

        # Example: "delete/remove [the] [folder] X [on|from|in] [the|my] desktop"
        m = re.match(
            r"^(?:delete|remove)\s+(?:the\s+)?(?:file|folder|directory)?\s*(.+?)\s+(?:on|from|in)\s+(?:(?:the|my)\s+)?desktop$",
            raw,
            flags=re.IGNORECASE,
        )
        if m:
            target = _clean_delete_target((m.group(1) or "").strip(" \"'`.,"))
            if target:
                return f"delete {self.desktop_root}\\{target}"

        # Example: "remove X folder" / "delete X" Ã¢Â€Â” infer Desktop item by name
        m = re.match(r"^(?:delete|remove)\s+(.+)$", raw, flags=re.IGNORECASE)
        if m and "desktop" not in lower:
            target = _clean_delete_target((m.group(1) or "").strip(" \"'`.,"))
            if target and not re.search(r"[/\\]|[a-zA-Z]:", target):
                desktop_match = self._find_desktop_item_path(target)
                if desktop_match:
                    return f"delete {desktop_match}"

        def _looks_absolute(s):
            """True if s is already a resolved Windows absolute path Ã¢Â€Â” skip re-resolution."""
            return bool(s and ((len(s) > 2 and s[1] == ":") or s.startswith(("\\\\"))))

        # -- Rename -------------------------------------------------------------
        _RENAME_PATTERNS = [
            re.compile(
                r"^(?:rename|change\s+(?:the\s+)?name\s+of)\s+(?:(?:the|my)\s+)?(?:folder|file|directory)?\s*(.+?)\s+(?:to|as|with)\s+(.+)$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^call\s+(?:(?:the|my)\s+)?(?:folder|file)?\s*(.+?)\s+(.+?)\s+instead$",
                re.IGNORECASE,
            ),
        ]
        def _clean_target_name(raw_dst):
            """Extract the actual filename from destination, stripping quoted commentary."""
            raw_dst = (raw_dst or "").strip()
            if raw_dst and raw_dst[0] in ('"', "'"):
                # Whole name is quoted Ã¢Â€Â” strip surrounding quotes
                return raw_dst.strip("\"'`.,").strip()
            # Strip trailing quoted commentary: e.g. 'pad1 "All right."' ? 'pad1'
            raw_dst = re.sub(r'\s+["\'].+$', '', raw_dst).strip()
            # Strip trailing filler words (conversational suffixes)
            raw_dst = re.sub(
                r'\s+(?:please|now|ok|okay|thanks|done|right|great|perfect|got it|alright|all right)[.!,?]*\s*$',
                '', raw_dst, flags=re.IGNORECASE
            ).strip(" \"'`.,")
            return raw_dst

        for pat in _RENAME_PATTERNS:
            m = pat.match(raw)
            if m:
                src = m.group(1).strip(" \"'`.,")
                # Already canonical (absolute path) Ã¢Â€Â” use as-is, no fuzzy resolution
                if _looks_absolute(src):
                    dst = _clean_target_name(m.group(2))
                    if dst:
                        return f"rename {src} to {dst}"
                    continue
                src = re.sub(r"\s+(?:folder|file|directory)s?\s*$", "", src, flags=re.IGNORECASE).strip(" \"'`.,")
                dst = _clean_target_name(m.group(2))
                if src and dst:
                    src_path = self._find_desktop_item_path(src) or f"{self.desktop_root}\\{src}"
                    return f"rename {src_path} to {dst}"

        # -- Move ---------------------------------------------------------------
        _MOVE_PATTERNS = [
            re.compile(
                r"^(?:move|put|place)\s+(?:(?:the|my)\s+)?(?:folder|file|directory)?\s*(.+?)\s+(?:to|into|inside)\s+(?:(?:the|my)\s+)?(.+)$",
                re.IGNORECASE,
            ),
        ]
        for pat in _MOVE_PATTERNS:
            m = pat.match(raw)
            if m:
                src = m.group(1).strip(" \"'`.,")
                if _looks_absolute(src):
                    # Already absolute Ã¢Â€Â” use as-is, only resolve destination
                    dst_raw = _clean_target_name(m.group(2))
                    dst_raw = re.sub(r"\s+(?:folder|file|directory)s?\s*$", "", dst_raw, flags=re.IGNORECASE).strip(" \"'`.,")
                    if src and dst_raw:
                        if re.match(r"^(?:the\s+)?desktop$", dst_raw, re.IGNORECASE):
                            return f"move {src} to {self.desktop_root}"
                        dst_path = self._find_desktop_item_path(dst_raw) or f"{self.desktop_root}\\{dst_raw}"
                        return f"move {src} to {dst_path}"
                    continue
                src = re.sub(r"\s+(?:folder|file|directory)s?\s*$", "", src, flags=re.IGNORECASE).strip(" \"'`.,")
                dst_raw = _clean_target_name(m.group(2))
                dst_raw = re.sub(r"\s+(?:folder|file|directory)s?\s*$", "", dst_raw, flags=re.IGNORECASE).strip(" \"'`.,")
                if src and dst_raw:
                    src_path = self._find_desktop_item_path(src) or f"{self.desktop_root}\\{src}"
                    if re.match(r"^(?:the\s+)?desktop$", dst_raw, re.IGNORECASE):
                        dst_path = self.desktop_root
                    else:
                        dst_path = self._find_desktop_item_path(dst_raw) or f"{self.desktop_root}\\{dst_raw}"
                    return f"move {src_path} to {dst_path}"

        return raw

    def _is_non_sensitive_desktop_query(self, text):
        """Read-only desktop queries that should not require explicit sensitive auth."""
        t = (text or "").strip().lower()
        if not t:
            return False
        desktop_norm = os.path.normcase(self.desktop_root)
        if t.startswith("list files in "):
            target = os.path.normcase(os.path.abspath((text or "").split("in", 1)[1].strip()))
            return target == desktop_norm
        if re.search(r"\b(list|show|see|what(?:'s| is)|give me)\b", t) and "desktop" in t:
            return True
        # Reading file content is read-only Ã¢Â€Â” no mutation required
        if t.startswith("read file "):
            return True
        return False

    def _desktop_items_snapshot(self, limit=40):
        """Lightweight desktop listing for AI context."""
        try:
            if not os.path.isdir(self.desktop_root):
                return []
            entries = sorted(os.listdir(self.desktop_root))
            return entries[:limit]
        except Exception:
            return []

    def _desktop_entries(self, limit=120):
        """Return desktop entries with file/folder type metadata."""
        try:
            if not os.path.isdir(self.desktop_root):
                return []
            out = []
            for name in sorted(os.listdir(self.desktop_root))[:limit]:
                path = os.path.join(self.desktop_root, name)
                out.append({"name": name, "is_dir": os.path.isdir(path)})
            return out
        except Exception:
            return []

    def _normalize_destination_to_url(self, destination):
        """Convert plain destination text to a URL when possible."""
        raw = (destination or "").strip().lower().strip(" .")
        if not raw:
            return None
        aliases = {
            "gmail": "https://mail.google.com",
            "google mail": "https://mail.google.com",
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "chatgpt": "https://chatgpt.com",
            "openai": "https://openai.com",
            "github": "https://github.com",
            "linkedin": "https://www.linkedin.com",
            "facebook": "https://www.facebook.com",
            "instagram": "https://www.instagram.com",
            "notion": "https://www.notion.so",
            "drive": "https://drive.google.com",
            "google drive": "https://drive.google.com",
            "docs": "https://docs.google.com",
            "google docs": "https://docs.google.com",
        }
        if raw in aliases:
            return aliases[raw]
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        if "." in raw and " " not in raw:
            return f"https://{raw}"
        if " " not in raw and raw.isalnum():
            return f"https://www.{raw}.com"
        return f"https://www.google.com/search?q={quote_plus(raw)}"

    def _open_url_in_browser(self, url, browser_hint=None):
        """Open URL in requested browser, fallback to default browser."""
        hint = self._normalize_app_name(browser_hint or "")
        browser_alias = {
            "google": "chrome",
            "google chrome": "chrome",
            "chrome": "chrome",
            "firefox": "firefox",
            "firfox": "firefox",
            "mozila firefox": "firefox",
            "mozilla firefox": "firefox",
            "edge": "edge",
            "microsoft edge": "edge",
            "brave": "brave",
        }
        browser_key = browser_alias.get(hint, "")
        browser_exec = {
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "edge": "msedge.exe",
            "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        }

        if browser_key:
            exe = browser_exec.get(browser_key)
            try:
                if exe:
                    self._popen_allowed([exe, url])
                    return True
            except Exception:
                pass

        try:
            webbrowser.open(url)
            return True
        except Exception:
            return False

    # Destinations that start with these prepositions are descriptive geographic
    # phrases extracted from conversational sentences, never actual website targets.
    _NAV_PREPOSITION_RE = re.compile(
        r"^(in|at|near|on|around|by|from|between|across|over|through|within|about|for|with|of)\b",
        re.IGNORECASE,
    )

    def _extract_navigation_intent(self, raw_input):
        """Parse natural navigation requests like 'go to gmail on firefox'."""
        text = (raw_input or "").strip()
        lowered = text.lower()
        # Never treat conversational sentences as navigation commands.
        # "visit" often appears mid-sentence in questions/suggestions and is NOT
        # a navigation verb in those contexts.
        if re.match(
            r"^(where|what|who|when|why|how"
            r"|give|tell|show|suggest|recommend|list|provide|find\s+me"
            r"|can\s+you|could\s+you|i\s+need|i\s+want|i\s+would"
            r"|help|please\s+(?:give|show|tell|suggest|find))\b",
            lowered,
        ):
            return None, None
        # Case: "open google and go to gmail"
        m = re.search(
            r"\bopen\s+(.+?)\s+(?:and\s+)?(?:go to|navigate to|visit)\s+(.+?)(?:\s+on\s+(.+))?$",
            lowered,
        )
        if m:
            browser = (m.group(1) or "").strip(" ,.?")
            destination = (m.group(2) or "").strip(" ,.?")
            explicit_browser = (m.group(3) or "").strip(" ,.?")
            if destination and not self._NAV_PREPOSITION_RE.match(destination):
                return destination, explicit_browser or browser

        # Case: "go to gmail on google" / "visit youtube"
        # Use re.search so "I want to go to youtube" still works, but reject destinations
        # that are clearly geographic/descriptive phrases (start with a preposition).
        m = re.search(r"\b(?:go\s+to|navigate\s+to|visit)\s+(.+?)(?:\s+on\s+(.+))?\s*$", lowered)
        if m:
            destination = (m.group(1) or "").strip(" ,.?")
            browser = (m.group(2) or "").strip(" ,.?")
            if destination and not self._NAV_PREPOSITION_RE.match(destination):
                return destination, browser

        # Case: "open gmail on firefox" used as navigation
        m = re.search(r"\bopen\s+(.+?)\s+on\s+(.+)\s*$", lowered)
        if m:
            destination = (m.group(1) or "").strip(" ,.?")
            browser = (m.group(2) or "").strip(" ,.?")
            if destination and not self._NAV_PREPOSITION_RE.match(destination):
                return destination, browser
        return None, None

    @staticmethod
    def _strip_ai_sources(text):
        """Remove any Sources / References section the AI appended Ã¢Â€Â” we add our own clean footer."""
        if not text:
            return text
        # Match "Sources:", "## Sources", "References:", "---\nSources", etc. near end of response
        cut = re.split(
            r'\n+(?:---\s*\n+)?(?:#{1,3}\s*)?(?:sources?|references?|further reading)\s*:?\s*\n',
            text,
            flags=re.IGNORECASE,
        )
        if len(cut) > 1:
            return cut[0].rstrip()
        # Also strip a trailing block that starts with numbered URLs [1] or bullet URLs
        cut2 = re.split(
            r'\n+(?:\[\d+\]|\*|\-)\s*https?://',
            text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if len(cut2) > 1:
            return cut2[0].rstrip()
        return text

    def _call_ai(self, messages):
        last_error = None
        cache_key = self._cache_key_from_messages(messages)
        cached = self._get_cached_ai_response(cache_key)
        if cached:
            self._set_ai_runtime(provider="cache", model="memory", status="ok", error="")
            return cached
        provider_order = self._build_provider_order(messages)
        if not provider_order:
            self._set_ai_runtime(provider="none", model="none", status="error", error="no_provider_configured")
            raise RuntimeError(
                "No AI provider configured. Set OPENAI_COMPAT_BASE_URL (+ OPENAI_COMPAT_API_KEY unless local), "
                "and/or ANTHROPIC_API_KEY and/or GROQ_API_KEY and/or DEEPSEEK_API_KEY and/or "
                "ALIBABA_MODEL_STUDIO_API_KEY (or DASHSCOPE_API_KEY) and/or GEMINI_API_KEY (or GOOGLE_API_KEY)."
            )

        for provider in provider_order:
            if provider in {"anthropic", "claude"}:
                models = [self.anthropic_model] + [m for m in self.anthropic_fallback_models if m != self.anthropic_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_anthropic_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("anthropic", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="anthropic", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("anthropic", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            if provider in {"openai_compatible", "openai-compatible", "openai", "ollama", "openrouter"}:
                models = [self.openai_compat_model] + [m for m in self.openai_compat_fallback_models if m != self.openai_compat_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_openai_compatible_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("openai_compatible", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="openai_compatible", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("openai_compatible", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            if provider in {"gemini", "google"}:
                models = [self.gemini_model] + [m for m in self.gemini_fallback_models if m != self.gemini_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_gemini_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("gemini", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="gemini", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("gemini", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            if provider in {"qwen", "alibaba", "dashscope"}:
                models = [self.qwen_model] + [m for m in self.qwen_fallback_models if m != self.qwen_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_qwen_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("qwen", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="qwen", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("qwen", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            if provider == "deepseek":
                models = [self.deepseek_model] + [m for m in self.deepseek_fallback_models if m != self.deepseek_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_deepseek_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("deepseek", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="deepseek", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("deepseek", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            elif provider == "groq":
                models = [self.groq_model] + [m for m in self.groq_fallback_models if m != self.groq_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_groq_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("groq", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="groq", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("groq", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            elif provider == "glm":
                models = [self.glm_model] + [m for m in self.glm_fallback_models if m != self.glm_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_glm_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("glm", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="glm", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("glm", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
            elif provider == "mimo":
                models = [self.mimo_model] + [m for m in self.mimo_fallback_models if m != self.mimo_model]
                for model_name in models:
                    _t0 = time.time()
                    try:
                        answer = self._retry_invoke(
                            lambda: self._call_mimo_chat(messages, model_name),
                            self.ai_max_retries,
                        )
                        if (answer or "").strip():
                            self._record_provider_result("mimo", True, latency_ms=(time.time() - _t0) * 1000.0)
                            self._set_cached_ai_response(cache_key, answer.strip())
                            self._set_ai_runtime(provider="mimo", model=model_name, status="ok", error="")
                            return answer.strip()
                    except Exception as e:
                        self._record_provider_result("mimo", False, latency_ms=(time.time() - _t0) * 1000.0, error_text=str(e))
                        last_error = e
        self._set_ai_runtime(provider="fallback", model="n/a", status="error", error=last_error)
        raise RuntimeError(f"AI request failed: {last_error}")

    def _describe_screen_snapshot(self, image_path, user_input=""):
        if not image_path or not os.path.exists(image_path):
            return ""
        if self.client is None:
            return f"Screen snapshot available at {image_path}. Vision analysis unavailable (Groq key not configured)."
        try:
            mtime = os.path.getmtime(image_path)
        except Exception:
            mtime = 0
        cache_key = f"{image_path}:{mtime}"
        if cache_key in self._screen_summary_cache:
            return self._screen_summary_cache[cache_key]

        def _encode_image_data(pil_img, fmt="PNG", quality=90):
            buf = BytesIO()
            if fmt.upper() == "JPEG":
                pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
                mime = "image/jpeg"
            else:
                pil_img.save(buf, format="PNG", optimize=True)
                mime = "image/png"
            return mime, base64.b64encode(buf.getvalue()).decode("ascii")

        payload = []
        prompt = (
            "You are a live screen analyst. The user is sharing their Windows desktop with you in real time Ã¢Â€Â” like a screen share call.\n"
            "Give a detailed, structured analysis exactly like this format:\n\n"
            "??? Active App Overview\n"
            "- Foreground App: [app name], [what it's showing Ã¢Â€Â” page title, file name, URL, content summary]\n"
            "- Other visible app: [if any visible in background]\n\n"
            "?? App Layout & Activity\n"
            "- Taskbar Apps (list every icon/app visible in the taskbar): ...\n"
            "- Open Windows: list all visible windows, what each contains\n"
            "- Terminal/Console (if visible): exact commands, output lines, errors shown\n"
            "- Browser (if open): exact URL, page title, visible headings, links, search results\n"
            "- Code Editor (if open): file name, language, visible code snippet\n"
            "- Any notifications, popups, dialogs: describe them exactly\n\n"
            "?? System Insights\n"
            "- OS/theme: ...\n"
            "- What the user appears to be working on or doing right now\n"
            "- Any errors, warnings, or issues visible on screen\n\n"
            "IMPORTANT Ã¢Â€Â” Opuntia window recognition: you may see a floating translucent chat window or a small panel "
            "with a text input box and a green 'Live' or 'Live off' button Ã¢Â€Â” this IS the Opuntia AI assistant's own "
            "chat interface. Always refer to it as 'Opuntia chat window' (not 'a popup', 'a dialog', or 'unknown window').\n"
            "Be factual and precise. Read all visible text exactly as written. Do not guess or fabricate values.\n"
            "If something is unreadable, say 'unreadable' rather than guessing.\n"
            f"The user just said: \"{user_input[:250]}\""
        )
        payload.append({"type": "text", "text": prompt})

        # Multi-view analysis: full frame + zoomed crops improves small-text readability.
        try:
            if Image is not None:
                with Image.open(image_path) as im:
                    rgb = im.convert("RGB")
                    w, h = rgb.size
                    views = [rgb]
                    if self.screen_vision_detail_mode in {"high", "max"} and (not self.screen_vision_fast_mode) and w > 300 and h > 300:
                        # Center crop Ã¢Â€Â” main content area
                        cx, cy = w // 2, h // 2
                        cw, ch = int(w * 0.65), int(h * 0.65)
                        l = max(0, cx - cw // 2)
                        t = max(0, cy - ch // 2)
                        r = min(w, l + cw)
                        b = min(h, t + ch)
                        views.append(rgb.crop((l, t, r, b)))
                        # Top strip Ã¢Â€Â” menus, tabs, address bars, title bars
                        views.append(rgb.crop((0, 0, w, max(220, int(h * 0.28)))))
                        # Bottom strip Ã¢Â€Â” taskbar, status bars, notifications
                        views.append(rgb.crop((0, max(0, h - max(80, int(h * 0.12))), w, h)))
                    for idx, view in enumerate(views):
                        fmt = "PNG" if idx == 0 else "JPEG"
                        mime, encoded = _encode_image_data(view, fmt=fmt, quality=90)
                        payload.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{encoded}"},
                            }
                        )
            else:
                with open(image_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("ascii")
                payload.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{'jpeg' if image_path.lower().endswith(('.jpg', '.jpeg')) else 'png'};base64,{encoded}"
                        },
                    }
                )
        except Exception:
            return ""

        last_error = None
        models = [self.vision_model] + [m for m in self.vision_fallback_models if m != self.vision_model]
        for model_name in models:
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": payload}],
                    max_tokens=600 if self.screen_vision_fast_mode else 1200,
                    temperature=0.1,
                    top_p=0.95,
                )
                if response and response.choices and response.choices[0].message:
                    content = (response.choices[0].message.content or "").strip()
                    if content:
                        self._screen_summary_cache = {cache_key: content}
                        return content
            except Exception as e:
                last_error = e
                continue
        return f"Screen snapshot available at {image_path}. Vision analysis unavailable ({last_error})."

    def _describe_image_file(self, image_path, user_input=""):
        if not image_path or not os.path.exists(image_path):
            return f"Image not found: {image_path}"
        if self.client is None:
            return "Vision analysis unavailable (Groq client not configured)."
        try:
            def _encode_image_data(pil_img, fmt="PNG", quality=90):
                buf = BytesIO()
                if fmt == "JPEG":
                    pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
                    mime = "image/jpeg"
                else:
                    pil_img.save(buf, format="PNG")
                    mime = "image/png"
                data = base64.b64encode(buf.getvalue()).decode("utf-8")
                return mime, data

            prompt = (
                "You are analyzing an attached image from the user. "
                "Describe what you see clearly and answer the user's request. "
                "Be concise and factual."
            )
            if user_input:
                prompt += f"\n\nUser request: {user_input}"

            payload = [{"type": "text", "text": prompt}]
            if Image is not None:
                with Image.open(image_path) as im:
                    im = im.convert("RGB")
                    fmt = "JPEG" if image_path.lower().endswith((".jpg", ".jpeg")) else "PNG"
                    mime, encoded = _encode_image_data(im, fmt=fmt, quality=90)
                    payload.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        }
                    )
            else:
                with open(image_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                    payload.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{'jpeg' if image_path.lower().endswith(('.jpg', '.jpeg')) else 'png'};base64,{encoded}"
                            },
                        }
                    )
            models = [self.vision_model] + [m for m in self.vision_fallback_models if m != self.vision_model]
            last_error = None
            for model_name in models:
                try:
                    response = self.client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": payload}],
                        max_tokens=900,
                        temperature=0.1,
                        top_p=0.95,
                    )
                    if response and response.choices and response.choices[0].message:
                        content = (response.choices[0].message.content or "").strip()
                        if content:
                            return content
                except Exception as e:
                    last_error = e
                    continue
            return f"Vision analysis unavailable ({last_error})."
        except Exception as e:
            return f"Vision analysis failed: {e}"

    def _extract_pdf_text(self, pdf_path, max_pages=6, max_chars=8000):
        if PyPDF2 is None:
            return "", "PyPDF2 not installed. Install PyPDF2 to read PDF text."
        try:
            reader = PyPDF2.PdfReader(pdf_path)
            parts = []
            for i, page in enumerate(reader.pages[:max_pages]):
                text = page.extract_text() or ""
                if text:
                    parts.append(text.strip())
                if sum(len(p) for p in parts) > max_chars:
                    break
            text = "\n\n".join(parts).strip()
            if not text:
                return "", "No extractable text found in PDF."
            if len(text) > max_chars:
                text = text[:max_chars]
            return text, ""
        except Exception as e:
            return "", f"PDF read failed: {e}"

    def _extract_docx_text(self, docx_path, max_chars=8000):
        if docx is None:
            return "", "python-docx not installed. Install python-docx to read Word files."
        try:
            document = docx.Document(docx_path)
            parts = []
            for p in document.paragraphs:
                t = (p.text or "").strip()
                if t:
                    parts.append(t)
                if sum(len(x) for x in parts) > max_chars:
                    break
            text = "\n".join(parts).strip()
            if not text:
                return "", "Word document appears to be empty."
            if len(text) > max_chars:
                text = text[:max_chars]
            return text, ""
        except Exception as e:
            return "", f"DOCX read failed: {e}"

    def _extract_xlsx_text(self, xlsx_path, max_sheets=3, max_rows=60, max_chars=8000):
        if openpyxl is None:
            return "", "openpyxl not installed. Install openpyxl to read Excel files."
        try:
            wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
            parts = []
            for sheet in wb.worksheets[:max_sheets]:
                parts.append(f"[Sheet] {sheet.title}")
                for i, row in enumerate(sheet.iter_rows(max_rows=max_rows, values_only=True), start=1):
                    row_vals = [str(v) if v is not None else "" for v in row]
                    line = " | ".join(row_vals).strip()
                    if line:
                        parts.append(line)
                    if sum(len(x) for x in parts) > max_chars:
                        break
                if sum(len(x) for x in parts) > max_chars:
                    break
            text = "\n".join(parts).strip()
            if len(text) > max_chars:
                text = text[:max_chars]
            return text, ""
        except Exception as e:
            return "", f"XLSX read failed: {e}"

    def _extract_pptx_text(self, pptx_path, max_slides=10, max_chars=8000):
        if Presentation is None:
            return "", "python-pptx not installed. Install python-pptx to read PowerPoint files."
        try:
            prs = Presentation(pptx_path)
            parts = []
            for i, slide in enumerate(prs.slides[:max_slides], start=1):
                parts.append(f"[Slide {i}]")
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        t = (shape.text or "").strip()
                        if t:
                            parts.append(t)
                if sum(len(x) for x in parts) > max_chars:
                    break
            text = "\n".join(parts).strip()
            if len(text) > max_chars:
                text = text[:max_chars]
            return text, ""
        except Exception as e:
            return "", f"PPTX read failed: {e}"

    def _extract_html_text(self, html_path, max_chars=8000):
        if not SOUP_AVAILABLE:
            return "", "BeautifulSoup not installed. Install beautifulsoup4 to read HTML."
        try:
            with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
                html_text = f.read(max_chars * 2)
            soup = BeautifulSoup(html_text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            if len(text) > max_chars:
                text = text[:max_chars]
            return text, ""
        except Exception as e:
            return "", f"HTML read failed: {e}"

    def _read_text_file(self, path, max_chars=8000):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(max_chars + 1)
            if len(text) > max_chars:
                text = text[:max_chars]
            return text.strip(), ""
        except Exception as e:
            return "", f"Text read failed: {e}"

    def _summarize_folder(self, folder_path, max_entries=40):
        entries = []
        try:
            for root, dirs, files in os.walk(folder_path):
                for name in files:
                    if len(entries) >= max_entries:
                        break
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, folder_path)
                    entries.append(rel)
                if len(entries) >= max_entries:
                    break
        except Exception as e:
            return "", f"Folder scan failed: {e}"
        if not entries:
            return "", "Folder is empty."
        return "\n".join(f"- {e}" for e in entries), ""

    def _analyze_attachments(self, attachment_paths, user_input, shared_screen_path=""):
        if not attachment_paths:
            return ""
        img_ext = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
        text_ext = {".txt", ".md", ".log", ".json", ".csv", ".ini", ".yaml", ".yml", ".py", ".js", ".ts", ".css"}
        html_ext = {".html", ".htm"}
        docx_ext = {".docx"}
        xlsx_ext = {".xlsx"}
        pptx_ext = {".pptx"}
        notes = []
        image_summaries = []
        text_blobs = []
        for p in attachment_paths:
            p = (p or "").strip().strip("\"'")
            if not p:
                continue
            p = os.path.expandvars(os.path.expanduser(p))
            p = os.path.normpath(p)
            if os.path.isdir(p):
                listing, err = self._summarize_folder(p)
                if err:
                    notes.append(f"[Folder] {p}: {err}")
                else:
                    text_blobs.append(f"[Folder] {p}\n{listing}")
                continue
            if not os.path.exists(p):
                alt = os.path.normpath(p.replace("/", "\\"))
                if os.path.exists(alt):
                    p = alt
                else:
                    # Fallback: try resolving by basename in common roots
                    base = os.path.basename(p)
                    candidates = []
                    try:
                        if hasattr(self, "desktop_root") and self.desktop_root:
                            candidates.append(os.path.join(self.desktop_root, base))
                    except Exception:
                        pass
                    candidates.append(os.path.join(os.getcwd(), base))
                    candidates.append(os.path.join(os.path.expanduser("~"), "Desktop", base))
                    resolved = ""
                    for c in candidates:
                        if c and os.path.exists(c):
                            resolved = c
                            break
                    if resolved:
                        p = resolved
                    else:
                        notes.append(f"[Missing] {p}")
                        continue
            ext = os.path.splitext(p)[1].lower()
            if ext in img_ext:
                summary = self._describe_image_file(p, user_input=user_input)
                image_summaries.append(f"[Image] {p}\n{summary}")
                continue
            if ext == ".pdf":
                text, err = self._extract_pdf_text(p)
                if text:
                    text_blobs.append(f"[PDF] {p}\n{text}")
                else:
                    notes.append(f"[PDF] {p}: {err}")
                continue
            if ext in html_ext:
                text, err = self._extract_html_text(p)
                if text:
                    text_blobs.append(f"[HTML] {p}\n{text}")
                else:
                    notes.append(f"[HTML] {p}: {err}")
                continue
            if ext in docx_ext:
                text, err = self._extract_docx_text(p)
                if text:
                    text_blobs.append(f"[DOCX] {p}\n{text}")
                else:
                    notes.append(f"[DOCX] {p}: {err}")
                continue
            if ext in xlsx_ext or ext == ".xls":
                # Try pandas first for rich analysis, fall back to openpyxl
                pd_report, _df = self._pandas_analyze_file(p, user_request=user_input)
                if _df is not None:
                    text_blobs.append(f"[XLSX] {p}\n{pd_report}")
                else:
                    text, err = self._extract_xlsx_text(p)
                    if text:
                        text_blobs.append(f"[XLSX] {p}\n{text}")
                    else:
                        notes.append(f"[XLSX] {p}: {err}")
                continue
            if ext in pptx_ext:
                text, err = self._extract_pptx_text(p)
                if text:
                    text_blobs.append(f"[PPTX] {p}\n{text}")
                else:
                    notes.append(f"[PPTX] {p}: {err}")
                continue
            if ext in text_ext:
                # Use pandas for CSV files for richer statistical analysis
                if ext == ".csv":
                    pd_report, _df = self._pandas_analyze_file(p, user_request=user_input)
                    if _df is not None:
                        text_blobs.append(f"[CSV] {p}\n{pd_report}")
                        continue
                text, err = self._read_text_file(p)
                if text:
                    text_blobs.append(f"[File] {p}\n{text}")
                else:
                    notes.append(f"[File] {p}: {err}")
                continue
            mime = mimetypes.guess_type(p)[0] or "unknown"
            notes.append(f"[Unsupported] {p} ({mime})")

        if shared_screen_path:
            screen_summary = self._describe_screen_snapshot(shared_screen_path, user_input=user_input)
            if screen_summary:
                text_blobs.append(f"[Screen] {shared_screen_path}\n{screen_summary}")

        context_parts = []
        if image_summaries:
            context_parts.append("Image analyses:\n" + "\n\n".join(image_summaries))
        if text_blobs:
            context_parts.append("File contents:\n" + "\n\n".join(text_blobs))
        if notes:
            context_parts.append("Notes:\n" + "\n".join(notes))

        context = "\n\n".join(context_parts).strip()
        if not context:
            return "No readable attachment content found."

        prompt = (
            "You are Opuntia. The user attached files. Use the content below to answer the request. "
            "If the user asks for a description, summarize clearly. If they ask questions, answer directly."
        )
        if not user_input:
            user_input = "Describe the attached files."
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"{context}\n\nUser request: {user_input}"},
        ]
        try:
            return self._strip_ai_sources(self._call_ai(messages))
        except Exception as e:
            return f"Attachment analysis failed: {e}"

    def process_command(self, user_input):
        # ── HARD GUARD: open/browse + URL must NEVER reach doc-creation handlers ──
        _raw_stripped = (user_input or "").strip()
        # Strip mode prefixes before checking
        for _pfx in ("MODE_TASK::", "AUTH_OK::", "SCREEN_SHARE::"):
            if _raw_stripped.startswith(_pfx):
                _raw_stripped = _raw_stripped[len(_pfx):]
        # Strip surrounding quotes and trailing punctuation added by voice transcription
        # e.g. '"Scroll down."' → 'Scroll down'  /  '"Click on login"' → 'Click on login'
        _raw_stripped = _raw_stripped.strip('"\'').rstrip('.!?,;')
        _url_open_m = re.match(
            r'^(?:run|play|open|browse|visit|go\s+to|navigate\s+to|load|show\s+me|fetch)\s+(https?://\S+|www\.\S+)',
            _raw_stripped.strip(), re.IGNORECASE,
        )
        if not _url_open_m:
            # Also catch bare URL pasted alone
            _url_open_m = re.match(r'^(https?://\S+)\s*$', _raw_stripped.strip(), re.IGNORECASE)
        if _url_open_m:
            _target_url = _url_open_m.group(1).rstrip('.,;!?)')
            if not _target_url.startswith("http"):
                _target_url = "https://" + _target_url
            # Always open in Playwright so the user can continue giving commands inside the page
            if sync_playwright is not None:
                try:
                    return self._pw_navigate(_target_url)
                except Exception:
                    pass
            # Fallback: system browser
            try:
                if self._open_url_in_browser(_target_url, None):
                    return f"Opened {_target_url} in your default browser."
                import webbrowser as _wb
                _wb.open(_target_url)
                return f"Opened {_target_url}."
            except Exception:
                return f"Could not open {_target_url}."

        # ── Playwright autonomous intelligence block ──────────────────────────────
        # When browser is active, a wide range of natural language commands work:
        # explain, translate, summarize, copy, open folders, ask questions about page, etc.
        if sync_playwright is not None and self._pw_page is not None:
            _pw_low = _raw_stripped.lower()

            # ── Navigation / mechanical actions first (fast path) ────────────────
            _pw_result = self._pw_automate(_raw_stripped)
            if _pw_result is not None:
                return _pw_result

            # "open [folder/link/item]" → try clicking it in the browser
            _pw_open_m = re.match(r'^open\s+(?:the\s+)?(.+)$', _pw_low)
            if _pw_open_m and not re.search(r'https?://', _raw_stripped):
                _target = _pw_open_m.group(1).strip(' "\'.,')
                try:
                    _pw_click_result = self._pw_send("click", _target)
                    if "Could not find" not in _pw_click_result:
                        return _pw_click_result
                except Exception:
                    pass

            # ── Full autonomous Playwright intelligence ───────────────────────
            # Everything that isn't a direct mechanical command goes to the LLM
            # with full page context + playwright capabilities listed in system prompt.
            # Uses a 15-second cache so only the FIRST command after a page load
            # pays the JS-evaluation cost — subsequent commands are instant.
            try:
                _now = time.time()
                if self._pw_page_cache and (_now - self._pw_page_cache_ts) < 15.0:
                    _page_text = self._pw_page_cache.get("text", "")
                    _page_scan = self._pw_page_cache.get("scan", "")
                    _cur_url   = self._pw_page_cache.get("url", "")
                    _cur_title = self._pw_page_cache.get("title", "")
                else:
                    # Single queue round-trip instead of 4 separate calls
                    _ctx = self._pw_send("full_context")
                    if isinstance(_ctx, dict):
                        _page_text = _ctx.get("text", "")
                        _page_scan = _ctx.get("scan", "")
                        _cur_url   = _ctx.get("url", "")
                        _cur_title = _ctx.get("title", "")
                    else:
                        _page_text = _page_scan = _cur_url = _cur_title = ""
                    self._pw_page_cache = {"text": _page_text, "scan": _page_scan,
                                           "url": _cur_url, "title": _cur_title}
                    self._pw_page_cache_ts = _now
            except Exception:
                _page_text = _page_scan = _cur_url = _cur_title = ""

            _PW_SYSTEM = (
                "You are Opuntia, an autonomous AI agent currently operating in **Playwright Browser Mode**.\n"
                "You have FULL programmatic control over the web browser the user sees on the right panel.\n\n"
                "## What you can do RIGHT NOW (just say it naturally):\n"
                "- **Navigate**: `play https://...` or `go to example.com`\n"
                "- **Click**: `click on Sign In`, `click the search icon`\n"
                "- **Type / Fill forms**: `type hello@email.com into the email field`, `write Claude into the search box`\n"
                "- **Scroll**: `scroll down`, `go to the bottom`, `scroll up 500`\n"
                "- **Screenshot**: `screenshot`, `full page screenshot`, `screenshot of element .header`\n"
                "- **Scrape data**: `read page`, `scan page`, `extract all links`, `copy the table`\n"
                "- **Keyboard shortcuts**: `press Enter`, `ctrl+a`, `select all`, `copy`, `paste`\n"
                "- **Multi-step tasks**: just describe what you want achieved — I break it into steps and execute\n"
                "- **Translate / Explain**: `translate this paragraph to Arabic`, `explain the installation section`\n"
                "- **Network inspection**: `intercept requests`, `show intercepted requests`\n"
                "- **Video recording**: `start recording`, `stop recording`\n"
                "- **Run JavaScript**: `run js document.title`\n"
                "- **Switch browser**: `use firefox`, `use webkit`\n"
                "- **Wait**: `wait for Login button`, `wait for page to load`\n"
                "- **Close**: `close browser`\n\n"
                "## Current browser state:\n"
                f"- URL: {_cur_url}\n"
                f"- Title: {_cur_title}\n\n"
                "## Page scan (visible interactive elements):\n"
                f"{str(_page_scan)[:1500]}\n\n"
                "## Page text content (what the user sees):\n"
                f"{str(_page_text)[:3500]}\n\n"
                "## Instructions:\n"
                "- Answer questions about the page using the content above.\n"
                "- For multi-step tasks, describe EXACTLY what you are doing step by step.\n"
                "- For translation/explanation, be direct — return the result immediately.\n"
                "- For extraction/scraping, format data clearly (markdown table, list, JSON).\n"
                "- If you need to perform browser actions as part of your answer, state them clearly.\n"
                "- NEVER say 'I cannot browse the web' — you are IN the browser right now.\n"
                "- Keep responses concise and action-oriented."
            )
            _msgs = [
                {"role": "system", "content": _PW_SYSTEM},
                {"role": "user", "content": _raw_stripped},
            ]
            try:
                return self._call_ai(_msgs)
            except Exception:
                pass

        if not hasattr(self, "pending_question"):
            self.pending_question = None
        if not hasattr(self, "pending_confirmation"):
            self.pending_confirmation = None
        if not hasattr(self, "_pending_pdf_save"):
            self._pending_pdf_save = None
        if not hasattr(self, "_pending_doc_save"):
            self._pending_doc_save = None
        if not hasattr(self, "last_attachment_paths"):
            self.last_attachment_paths = []
        if not hasattr(self, "last_attachment_ts"):
            self.last_attachment_ts = 0.0
        if not hasattr(self, "web_universal_mode"):
            self.web_universal_mode = False
        if not hasattr(self, "web_research_auto"):
            self.web_research_auto = False
        if not hasattr(self, "last_live_web_query"):
            self.last_live_web_query = ""
        if not hasattr(self, "last_live_web_error"):
            self.last_live_web_error = ""
        if not hasattr(self, "last_structured_intent"):
            self.last_structured_intent = ""
        if not hasattr(self, "last_structured_payload"):
            self.last_structured_payload = {}
        raw_input = (user_input or "").lstrip()
        self._set_ai_runtime(provider="local", model="rules", status="processing", error="")
        auth_prefix = "AUTH_OK::"
        screen_prefix = "SCREEN_SHARE::"
        attach_prefix = "ATTACHMENTS::"
        task_mode_prefix = "MODE_TASK::"
        # Detect and strip mode prefix â€” set input_mode accordingly
        _input_mode = getattr(self, "input_mode", "chat")
        if raw_input.startswith(task_mode_prefix):
            raw_input = raw_input[len(task_mode_prefix):]
            _input_mode = "task"
            self.input_mode = "task"
        allow_sensitive_fs = False
        if raw_input.startswith(auth_prefix):
            allow_sensitive_fs = True
            raw_input = raw_input[len(auth_prefix):].lstrip()
            self._audit("authorization", "granted", {"command": raw_input[:300]})
            # AUTH_OK is an explicit one-shot approval from the UI.
            # If a prior pending permission prompt exists, do not let it
            # intercept this command; execute the authorized command directly.
            if getattr(self, "pending_question", None) is not None:
                prev_id = (self.pending_question or {}).get("id", "")
                self.pending_question = None
                self._audit("permission_request", "superseded_by_auth", {"id": prev_id, "command": raw_input[:300]})
        attachment_paths = []
        if raw_input.startswith(attach_prefix):
            raw_input = raw_input[len(attach_prefix):]
            if "::" in raw_input:
                blob, stripped_cmd = raw_input.split("::", 1)
                attachment_paths = [p for p in blob.split("|") if p.strip()]
                raw_input = stripped_cmd
            if not attachment_paths:
                return "No attachments were provided."
            self.last_attachment_paths = attachment_paths[:]
            self.last_attachment_ts = time.time()
        shared_screen_path = ""
        if raw_input.startswith(screen_prefix):
            raw_input = raw_input[len(screen_prefix):]
            if "::" in raw_input:
                maybe_path, stripped_cmd = raw_input.split("::", 1)
                shared_screen_path = maybe_path.strip()
                raw_input = stripped_cmd
        self.screen_sharing_active = bool(shared_screen_path)
        user_input = self._normalize_spoken_typos(raw_input)
        # Guarded autonomy profiles can relax sensitive confirmations in Task mode.
        _policy = self._autonomy_policy()
        if _input_mode == "task" and (not _policy.get("require_sensitive_confirmation", True)):
            allow_sensitive_fs = True
        self._update_profile_domain(user_input)
        normalized_user_input = self._normalize_intent_text(user_input)
        cmd_lower = normalized_user_input.lower()
        # Detect large write-body commands early Ã¢Â€Â” used by multiple guards below
        _has_write_body = bool(re.search(
            r'\b(write\s+this|write\s+inside|with\s+content|write:|inside\s*:|write\s+in\s+it'
            r'|(?:write|create|save|export|put)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))|write\s+what\s+(?:you|u)\s+have|write\s+the\s+last|write\s+your\s+last'
            r'|save\s+this\s+as|save\s+as|put\s+this\s+in|add\s+this\s+to'
            r'|write\s+it\s+in|write\s+that\s+in'
            r'|with\s+the\s+following|the\s+following\s+content|put\s+inside'
            r'|and\s+write\s*[:\-]|write\s+the\s+following'
            r'|export\s+(this\s+)?(as|to)|convert\s+(this\s+)?(to|into)'
            r'|generate\s+a?\s*(pdf|docx?|word|txt)|make\s+a?\s*(pdf|docx?|word\s+doc|txt)'
            r'|create\s+a?\s*(pdf|docx?|word\s+doc|txt)|produce\s+a?\s*(pdf|docx?|word|txt))\b',
            cmd_lower
        ))
        # -- ROOT FIX: truncate cmd_lower at the content-body delimiter ----------
        # When the user dictates content for a file/doc, the content body often
        # contains keywords that would hijack routing (e.g. "list", "app", "volume",
        # "sleep", "desktop", "launch", "open", etc.).
        # By stripping the content body from cmd_lower HERE, every routing handler
        # downstream automatically receives only the command part Ã¢Â€Â” no per-handler
        # guards needed. user_input (passed to _handle_word_command) is never truncated
        # so content extraction still works correctly.
        _body_split_m = re.search(
            r'\b(write\s+this|write\s+inside|with\s+content|write\s*:|inside\s*:'
            r'|write\s+in\s+it|put\s+this\s+in|add\s+this\s+to'
            r'|write\s+it\s+in|write\s+that\s+in'
            r'|with\s+the\s+following|the\s+following\s+content|put\s+inside'
            r'|and\s+write[\s:*\-]|write\s+the\s+following'
            r'|(?:write|create|save|export|put)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))|and\s+put\s+inside|write\s+content\s*:'
            r'|export\s+(this\s+)?(as|to)\s*:|convert\s+(this\s+)?(to|into)\s*:)\b',
            cmd_lower
        )
        if _body_split_m and _body_split_m.start() > 0:
            cmd_lower = cmd_lower[:_body_split_m.start()].strip()

        if not attachment_paths:
            local_paths = [p for p in self._extract_local_paths(user_input) if os.path.exists(p)]
            if local_paths:
                attachment_paths = local_paths
                self.last_attachment_paths = attachment_paths[:]
                self.last_attachment_ts = time.time()
        if not attachment_paths:
            # Don't recall last attachment when user is writing inline content Ã¢Â€Â”
            # "attached"/"file" inside written content is not a file reference.
            if not _has_write_body and re.search(r"\b(image|photo|picture|this image|attached|attachment|file)\b", cmd_lower):
                if self.last_attachment_paths and (time.time() - self.last_attachment_ts) < 600:
                    attachment_paths = self.last_attachment_paths[:]
        if attachment_paths:
            analysis = self._analyze_attachments(attachment_paths, user_input, shared_screen_path=shared_screen_path)
            return analysis

        # â”€â”€ ULTRA-EARLY FAST-PATH: authorized doc-creation bypasses ALL pending state â”€â”€
        # When the user has already been shown the UI auth prompt and clicked Allow,
        # allow_sensitive_fs=True. At that point the command MUST go straight to the
        # PDF/Word handler regardless of any leftover pending_question / pending_pdf_save
        # state that could intercept and misroute it.
        _dbg_log = self._get_pdf_debug_logger()
        _dbg_log.debug(f'process_command: allow_sensitive_fs={allow_sensitive_fs} _has_write_body={_has_write_body} cmd_lower={repr(cmd_lower[:60])}')
        if allow_sensitive_fs:
            _is_close_intent = bool(re.search(r"\b(close|quit|exit|terminate|kill)\b", cmd_lower))
            _is_doc_intent = bool(re.search(r"\b(create|make|write|generate|save|produce|build|export|prepare|draft|give|put|convert|turn)\b", cmd_lower))
            if _is_close_intent and not _is_doc_intent:
                _dbg_log.debug("  allow_sensitive_fs: close intent detected â€” skipping doc-creation fast-path")
            else:
                _ue_doc = bool(
                    re.search(r'\b(pdf|\.pdf|docx?|\.docx?|word\s+(doc(ument)?|file)|text\s+file|note\s+file|txt\s*file?\b|\.txt|\btxt\b|pptx?|\.pptx?|pow[a-z]*oint|presentation|slides?\b|slide\s+deck|xlsx?|\.xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b', cmd_lower)
                    or re.search(r'\b(?:write|create|save|export|put)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))\b', cmd_lower)
                    or re.search(r'\bwrite\s+(the\s+)?(last|previous)\b', cmd_lower)
                    or re.search(r'\b(save|export)\s+(your\s+)?last\b', cmd_lower)
                    or re.search(r'\b(generate|create|make|produce|build|export|save|write|give|prepare|draft)\s+(a\s+|an\s+|new\s+|the\s+|me\s+a?\s*)?(pdf|docx?|word\s+(doc(ument)?|file)|text\s+file|note\s+file|txt\s*file?\b|\.txt|pptx?|pow[a-z]*oint|presentation|slides?|slide\s+deck|xlsx?|excell?|spreadsheet|google\s+sheets?|gsheet)\b', cmd_lower)
                    or re.search(r'\b(convert|turn|transform|export|save)\s+(?:\S+\s+){0,5}(to|into|as)\s+(a\s+)?(pdf|docx?|word|pptx?|pow[a-z]*oint|presentation|slides?|txt|xlsx?|excell?|spreadsheet|google\s+sheets?|gsheet)\b', cmd_lower)
                )
                _dbg_log.debug(f'  _ue_doc={_ue_doc}')
                if _ue_doc:
                    try:
                        _ue_pdf = self._handle_pdf_command(
                            user_input, allow_desktop=True, allow_mutation=True
                        )
                    except Exception as _ue_exc:
                        _dbg_log.debug(f'  _handle_pdf_command EXCEPTION: {_ue_exc}')
                        _ue_pdf = None
                        self._pending_pdf_save = None
                    _dbg_log.debug(f'  _ue_pdf={repr(str(_ue_pdf)[:80]) if _ue_pdf else None}')
                    if _ue_pdf is not None:
                        return _ue_pdf
                    try:
                        _ue_word = self._handle_word_command(
                            user_input, allow_desktop=True, allow_mutation=True
                        )
                    except Exception as _ue_exc2:
                        _dbg_log.debug(f'  _handle_word_command EXCEPTION: {_ue_exc2}')
                        _ue_word = None
                        self._pending_doc_save = None
                    _dbg_log.debug(f'  _ue_word={repr(str(_ue_word)[:80]) if _ue_word else None}')
                    if _ue_word is not None:
                        return _ue_word
                # â”€â”€ DIRECT FALLBACK: both handlers returned None â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # _handle_pdf_command/_handle_word_command failed to handle the
                # "write what you sent inside PDF" case. Build the PDF directly.
                _fb_last_pat = re.compile(
                    r'\b(?:write|create|put|save|generate|make|produce|export|build)\b.{0,50}'
                    r'\b(?:what\s+(?:(?:you|u)(?:\'?ve)?\s+(?:have\s+)?|(?:have|had)\s+(?:you|u)\s+)(?:just\s+)?(?:sent|said|wrote|written|replied?|gave|given)'
                    r'|(?:the\s+)?(?:last|previous|latest)\s+(?:response|answer|message|reply)'
                    r'|your\s+(?:last|previous|latest)'
                    r'|inside\s+(?:what|it|that)\s+(?:you|u|i|we)\s+(?:have\s+)?(?:sent|said|wrote|given)'
                    r'|inside\s+(?:the\s+)?(?:last|previous)\b)',
                    re.IGNORECASE | re.DOTALL,
                )
                if _fb_last_pat.search(user_input):
                    _fb_task_hist = list(getattr(self, 'task_conversation_history', []))
                    _fb_hist = _fb_task_hist or list(getattr(self, 'conversation_history', []))
                    _fb_content = ''
                    for _fb_msg in reversed(_fb_hist):
                        _fb_ai = (_fb_msg.get('assistant') or _fb_msg.get('content') or '').strip()
                        if _fb_ai:
                            _fb_content = self._strip_ai_sources(_fb_ai)
                            break
                    # Only fall back to conversation_history if we used task history and found nothing
                    if not _fb_content and _fb_task_hist:
                        for _fb_msg in reversed(list(getattr(self, 'conversation_history', []))):
                            _fb_ai = (_fb_msg.get('assistant') or _fb_msg.get('content') or '').strip()
                            if _fb_ai:
                                _fb_content = self._strip_ai_sources(_fb_ai)
                                break
                    _dbg_log.debug(f'  FALLBACK: _fb_content={repr(_fb_content[:80]) if _fb_content else None}')
                    if _fb_content:
                        _fb_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                        _fb_name_m = re.search(
                            r'\b(?:called|named)\s+["\']?([^"\',:]+?)["\']?\s*$',
                            user_input, re.IGNORECASE,
                        )
                        _fb_base = _fb_name_m.group(1).strip(' "\'.,') if _fb_name_m else self._generate_doc_title(_fb_content)
                        _fb_base = re.sub(r'[\\/*?:"<>|]', '', _fb_base).strip() or 'Response'

                        _is_pptx = bool(re.search(r'\b(pptx?|\.pptx?|pow[a-z]*oint|presentation|slide\s+deck|slides?\b)', cmd_lower))
                        _is_xlsx = bool(re.search(r'\b(xlsx?|\.xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b', cmd_lower)) and not _is_pptx
                        _is_word = bool(re.search(r'\b(docx?|word\s+(doc(ument)?|file)|\.docx?)\b', cmd_lower)) and not _is_pptx and not _is_xlsx
                        _is_note = bool(re.search(r'\b(note\s*file|text\s*file|\.txt|txt\s*file?\b|\btxt\b|note\b)', cmd_lower)) and not _is_word and not _is_pptx and not _is_xlsx

                        if _is_pptx:
                            _fb_name = _fb_base + '.pptx'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_pptx_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create presentation: {_fb_err}"
                        elif _is_xlsx:
                            _fb_name = _fb_base + '.xlsx'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_excel_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create spreadsheet: {_fb_err}"
                        elif _is_word:
                            _fb_name = _fb_base + '.docx'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_word_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create document: {_fb_err}"
                        elif _is_note:
                            _fb_name = _fb_base + '.txt'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            try:
                                with open(_fb_path, 'w', encoding='utf-8') as _fb_f:
                                    _fb_f.write(_fb_content)
                                try:
                                    os.startfile(_fb_path)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            except Exception as _fb_te:
                                _fb_reply = f"Could not create note file: {_fb_te}"
                        else:
                            _fb_name = _fb_base + '.pdf'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_pdf_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create PDF: {_fb_err}"
                        _dbg_log.debug(f'  FALLBACK reply={repr(str(_fb_reply)[:80])}')
                        return _fb_reply
                # â”€â”€ INLINE CONTENT FALLBACK: "write this inside pdf : [content]" â”€â”€â”€â”€â”€
                else:
                    _inline_m = re.search(
                        r'(?:write\s*:|inside\s*(?:this\s*)?:|and\s+write\s*:|write\s+(?:this|it|that|inside|content)\s*:|following\s*:|put\s*:|generate\s+\w+\s+inside\s*:)\s*(.+)',
                        user_input, re.DOTALL | re.IGNORECASE,
                    )
                    if not _inline_m:
                        # plain colon with enough content after it
                        _inline_m = re.search(r':\s*(.+)$', user_input, re.DOTALL)
                    if _inline_m:
                        _fb_content = _inline_m.group(1).strip()
                        _dbg_log.debug(f'  INLINE FALLBACK: _fb_content={repr(_fb_content[:80])}')
                        _fb_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                        _fb_name_m = re.search(
                            r'\b(?:called|named)\s+["\']?([^"\',:]+?)["\']?\s*$',
                            user_input, re.IGNORECASE,
                        )
                        _fb_base = _fb_name_m.group(1).strip(' "\'.,') if _fb_name_m else self._generate_doc_title(_fb_content)
                        _fb_base = re.sub(r'[\\/*?:"<>|]', '', _fb_base).strip() or 'Response'
                        _type_str = cmd_lower[:_inline_m.start(1)]
                        _is_pptx = bool(re.search(r'\b(pptx?|\.pptx?|pow[a-z]*oint|presentation|slide\s+deck|slides?\b)', _type_str))
                        _is_xlsx = bool(re.search(r'\b(xlsx?|\.xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b', _type_str)) and not _is_pptx
                        _is_word = bool(re.search(r'\b(docx?|word\s+(doc(ument)?|file)|\.docx?)\b', _type_str)) and not _is_pptx and not _is_xlsx
                        _is_note = bool(re.search(r'\b(note\s*file|text\s*file|\.txt|txt\s*file?\b|\btxt\b|note\b)', _type_str)) and not _is_word and not _is_pptx and not _is_xlsx
                        _fb_reply = None
                        if _is_pptx:
                            _fb_name = _fb_base + '.pptx'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_pptx_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create presentation: {_fb_err}"
                        elif _is_xlsx:
                            _fb_name = _fb_base + '.xlsx'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_excel_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create spreadsheet: {_fb_err}"
                        elif _is_word:
                            _fb_name = _fb_base + '.docx'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_word_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create document: {_fb_err}"
                        elif _is_note:
                            _fb_name = _fb_base + '.txt'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            try:
                                with open(_fb_path, 'w', encoding='utf-8') as _fb_f:
                                    _fb_f.write(_fb_content)
                                try:
                                    os.startfile(_fb_path)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            except Exception as _fb_te:
                                _fb_reply = f"Could not create note file: {_fb_te}"
                        else:
                            _fb_name = _fb_base + '.pdf'
                            _fb_path = os.path.join(_fb_desktop, _fb_name)
                            _fb_saved, _fb_err = self._create_pdf_document(
                                _fb_path, _fb_content, doc_title=_fb_base
                            )
                            if not _fb_err:
                                try:
                                    os.startfile(_fb_saved)
                                except Exception:
                                    pass
                                _fb_reply = f"**Saved and opened** `{_fb_name}` on your Desktop"
                            else:
                                _fb_reply = f"Could not create PDF: {_fb_err}"
                        if _fb_reply is not None:
                            _dbg_log.debug(f'  INLINE FALLBACK reply={repr(str(_fb_reply)[:80])}')
                            return _fb_reply
                # â”€â”€ BARE COMMAND FALLBACK: “generate a pdf” with no content â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # STRICT GUARD: only fire when the command explicitly asks for a document.
                # Must have BOTH a creation verb AND a document type keyword.
                _bare_has_doc_verb = bool(re.search(
                    r'\b(generate|create|make|produce|build|export|save|write|give|prepare|draft|put|convert)\b',
                    cmd_lower,
                ))
                _bare_has_doc_type = bool(re.search(
                    r'\b(pdf|\.pdf|docx?|word|txt|text\s+file|note|pptx?|presentation|xlsx?|spreadsheet)\b',
                    cmd_lower,
                ))
                _bare_has_url = bool(re.search(r'https?://', user_input))
                _bare_task_hist = list(getattr(self, 'task_conversation_history', []))
                _bare_hist = _bare_task_hist or list(getattr(self, 'conversation_history', []))
                _bare_content = ''
                if not _bare_has_url and _bare_has_doc_verb and _bare_has_doc_type:
                    for _bare_msg in reversed(_bare_hist):
                        _bare_ai = (_bare_msg.get('assistant') or _bare_msg.get('content') or '').strip()
                        if _bare_ai:
                            _bare_content = self._strip_ai_sources(_bare_ai)
                            break
                    # Only fall back to conversation_history if we used task history and found nothing
                    if not _bare_content and _bare_task_hist:
                        for _bare_msg in reversed(list(getattr(self, 'conversation_history', []))):
                            _bare_ai = (_bare_msg.get('assistant') or _bare_msg.get('content') or '').strip()
                            if _bare_ai:
                                _bare_content = self._strip_ai_sources(_bare_ai)
                                break
                if _bare_content:
                    _dbg_log.debug(f'  BARE CMD FALLBACK: content={repr(_bare_content[:80])}')
                    _bare_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                    _bare_name_m = re.search(
                        r'\b(?:called|named)\s+["\']?([^"\',:]+?)["\']?\s*$',
                        user_input, re.IGNORECASE,
                    )
                    _bare_base = _bare_name_m.group(1).strip(' "\'.,') if _bare_name_m else self._generate_doc_title(_bare_content)
                    _bare_base = re.sub(r'[\\/*?:"<>|]', '', _bare_base).strip() or 'Response'
                    _bare_is_pptx = bool(re.search(r'\b(pptx?|\.pptx?|pow[a-z]*oint|presentation|slide\s+deck|slides?\b)', cmd_lower))
                    _bare_is_xlsx = bool(re.search(r'\b(xlsx?|\.xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b', cmd_lower)) and not _bare_is_pptx
                    _bare_is_word = bool(re.search(r'\b(docx?|word\s+(doc(ument)?|file)|\.docx?)\b', cmd_lower)) and not _bare_is_pptx and not _bare_is_xlsx
                    _bare_is_note = bool(re.search(r'\b(note\s*file|text\s*file|\.txt|txt\s*file?\b|\btxt\b|note\b)', cmd_lower)) and not _bare_is_word and not _bare_is_pptx and not _bare_is_xlsx
                    _bare_reply = None
                    if _bare_is_pptx:
                        _bare_path = os.path.join(_bare_desktop, _bare_base + '.pptx')
                        _bare_saved, _bare_err = self._create_pptx_document(_bare_path, _bare_content, doc_title=_bare_base)
                        if not _bare_err:
                            try: os.startfile(_bare_saved)
                            except Exception: pass
                            _bare_reply = f"**Saved and opened** `{_bare_base}.pptx` on your Desktop"
                        else:
                            _bare_reply = f"Could not create presentation: {_bare_err}"
                    elif _bare_is_xlsx:
                        _bare_path = os.path.join(_bare_desktop, _bare_base + '.xlsx')
                        _bare_saved, _bare_err = self._create_excel_document(_bare_path, _bare_content, doc_title=_bare_base)
                        if not _bare_err:
                            try: os.startfile(_bare_saved)
                            except Exception: pass
                            _bare_reply = f"**Saved and opened** `{_bare_base}.xlsx` on your Desktop"
                        else:
                            _bare_reply = f"Could not create spreadsheet: {_bare_err}"
                    elif _bare_is_word:
                        _bare_name = _bare_base + '.docx'
                        _bare_path = os.path.join(_bare_desktop, _bare_name)
                        _bare_saved, _bare_err = self._create_word_document(
                            _bare_path, _bare_content, doc_title=_bare_base
                        )
                        if not _bare_err:
                            try:
                                os.startfile(_bare_saved)
                            except Exception:
                                pass
                            _bare_reply = f"**Saved and opened** `{_bare_name}` on your Desktop"
                        else:
                            _bare_reply = f"Could not create document: {_bare_err}"
                    elif _bare_is_note:
                        _bare_name = _bare_base + '.txt'
                        _bare_path = os.path.join(_bare_desktop, _bare_name)
                        try:
                            with open(_bare_path, 'w', encoding='utf-8') as _bare_f:
                                _bare_f.write(_bare_content)
                            try:
                                os.startfile(_bare_path)
                            except Exception:
                                pass
                            _bare_reply = f"**Saved and opened** `{_bare_name}` on your Desktop"
                        except Exception as _bare_te:
                            _bare_reply = f"Could not create note file: {_bare_te}"
                    else:
                        _bare_name = _bare_base + '.pdf'
                        _bare_path = os.path.join(_bare_desktop, _bare_name)
                        _bare_saved, _bare_err = self._create_pdf_document(
                            _bare_path, _bare_content, doc_title=_bare_base
                        )
                        if not _bare_err:
                            try:
                                os.startfile(_bare_saved)
                            except Exception:
                                pass
                            _bare_reply = f"**Saved and opened** `{_bare_name}` on your Desktop"
                        else:
                            _bare_reply = f"Could not create PDF: {_bare_err}"
                    if _bare_reply is not None:
                        _dbg_log.debug(f'  BARE CMD FALLBACK reply={repr(str(_bare_reply)[:80])}')
                        return _bare_reply
        # â”€â”€ END ULTRA-EARLY FAST-PATH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        # -- Confirmation handlers MUST run before smalltalk so "yeah/ok/sure/1/2" work --
        if self.pending_question is not None:
            req = self.pending_question
            if time.time() > float(req.get("expires_at", time.time() + 300)):
                req_id = req.get("id", "")
                self.pending_question = None
                self._audit("permission_request", "timeout", {"id": req_id})
                return f"Permission request {req_id} timed out."
            choice = self._resolve_pending_question_choice(user_input, req)
            if choice is None:
                return self._format_pending_question_prompt(req, invalid=True)
            self.pending_question = None
            if choice in {"allow", "allow once", "allow_once", "yes", "confirm"}:
                self._audit("permission_request", "approved", {"id": req.get("id", ""), "action": req.get("action", "")})
                return self._run_confirmed_action(req.get("action"), req.get("payload"))
            self._audit("permission_request", "denied", {"id": req.get("id", ""), "action": req.get("action", "")})
            return req.get("on_deny") or "Cancelled."

        # Handle pending yes/no confirmations for ambiguous actions.
        if self.pending_confirmation is not None:
            if self._is_affirmative(cmd_lower):
                pending = self.pending_confirmation
                self.pending_confirmation = None
                return self._run_confirmed_action(pending.get("action"), pending.get("payload"))
            if self._is_negative(cmd_lower):
                pending = self.pending_confirmation
                self.pending_confirmation = None
                if (pending or {}).get("action") == "execute_plan_step":
                    return self._cancel_plan_execution()
                return "Cancelled."
            return "Please answer yes or no."

        # -- Pending doc save location -----------------------------------------
        # Opuntia asked "where to save?" Ã¢Â€Â” the user's entire next message is the answer.
        # Doc is created DIRECTLY at the final path (no temp file, no WinError 32).
        if self._pending_pdf_save is not None:
            pending = self._pending_pdf_save
            self._pending_pdf_save = None  # consume immediately
            pdf_name  = pending.get("name", "Document.pdf")
            content   = pending.get("content", "")
            doc_title = pending.get("doc_title", "")
            folder, err = self._parse_save_location(user_input)
            if err == "cancelled":
                return "Discarded Ã¢Â€Â” PDF was not saved."
            if err:
                _cmd_verbs = re.compile(
                    r"^(write|create|make|open|close|search|find|show|tell|what|who|how|can|do|go|get|send|save|delete|list|help|yo|hi|hello)\b",
                    re.IGNORECASE,
                )
                if not _cmd_verbs.match(user_input.strip()):
                    self._pending_pdf_save = pending
                    return f"{err}\nWhere do you want to save **`{pdf_name}`**? (desktop / documents / D drive / full path)"
            else:
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception:
                    pass
                final_path = os.path.join(folder, pdf_name)
                saved_path, create_err = self._create_pdf_document(final_path, content, doc_title=doc_title)
                if create_err:
                    self._pending_pdf_save = pending
                    return f"Could not create PDF: {create_err}\nTry a different location."
                try:
                    os.startfile(saved_path)
                except Exception:
                    pass
                return f"**Saved and opened** `{pdf_name}` in `{folder}`"

        if self._pending_doc_save is not None:
            pending = self._pending_doc_save
            self._pending_doc_save = None  # consume immediately
            doc_name  = pending.get("name", "Document.docx")
            content   = pending.get("content", "")
            doc_title = pending.get("doc_title", "")
            folder, err = self._parse_save_location(user_input)
            if err == "cancelled":
                return "Discarded Ã¢Â€Â” document was not saved."
            if err:
                # If the user sent a new command instead of a location, discard the
                # pending save silently and fall through to normal command routing.
                _cmd_verbs = re.compile(
                    r"^(write|create|make|open|close|search|find|show|tell|what|who|how|can|do|go|get|send|save|delete|list|help|yo|hi|hello)\b",
                    re.IGNORECASE,
                )
                if not _cmd_verbs.match(user_input.strip()):
                    # Not a command Ã¢Â€Â” re-ask once
                    self._pending_doc_save = pending
                    return f"{err}\nWhere do you want to save **`{doc_name}`**? (desktop / documents / D drive / full path)"
                # Looks like a new command Ã¢Â€Â” fall through to normal routing below
            else:
                # Valid save location Ã¢Â€Â” create the doc
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception:
                    pass
                final_path = os.path.join(folder, doc_name)
                saved_path, create_err = self._create_word_document(final_path, content, doc_title=doc_title)
                if create_err:
                    self._pending_doc_save = pending
                    return f"Could not create document: {create_err}\nTry a different location."
                try:
                    os.startfile(saved_path)
                except Exception:
                    pass
                return f"**Saved and opened** `{doc_name}` in `{folder}`"

        # -- User city setting ("my city is X" / "I live in X" / "set my city to X") --
        _city_set_m = re.match(
            r"^\s*(?:my\s+(?:city|location|home(?:\s+city)?|town)\s+is|i\s+live\s+in|i(?:'m|\s+am)\s+(?:from|in)|set\s+my\s+(?:city|location)\s+(?:to|as))\s+(.+?)\s*[.!?]*\s*$",
            cmd_lower,
        )
        if _city_set_m:
            new_city = user_input[_city_set_m.start(1):_city_set_m.end(1)].strip().title()
            self.user_city = new_city
            self._save_settings()
            return f"Got it — I'll show **{new_city}** in the greeting from now on."

        # -- Smalltalk (works in both chat and task mode) -----------------------
        if self._is_smalltalk_query(cmd_lower):
            if re.search(r"\b(hru|how\s+r\s+u|how\s+are\s+u|how\s+are\s+you|how\s+u)\b", cmd_lower):
                return "I'm good and ready to help. What do you need?"
            # Acknowledgements after a substantive reply ("great", "nice", "ok", "cool", etc.)
            # should feel natural, not restart with a cold "Hello. How can I help?".
            # Route them to the LLM so it can respond with conversation context.
            if re.search(
                r"^\s*(thanks|thank\s+you|thank\s+u|thx|ty|ok|okay|cool|nice|great|"
                r"got\s+it|understood|perfect|awesome|noted|appreciate|alright|sure)\s*[!.,?]*\s*$",
                cmd_lower, re.IGNORECASE,
            ):
                return self.intelligent_respond(user_input, has_live_screen=bool(shared_screen_path))
            return "Hello. How can I help?"

        def _ret(msg, remember=True):
            _msg = str(msg or "")
            self._capture_turn(user_input, _msg, remember=bool(remember))
            return _msg

        if re.match(r"^\s*(execute|run|start)\s+(screen\s+)?plan\s*$", cmd_lower):
            return self._start_plan_execution()

        if re.search(r"\b(close|exit|quit|turn off|shutdown)\s+(yourself|this app|the app)\b", cmd_lower):
            return "__APP_EXIT__"
        if re.match(r"^\s*(ai|llm)\s+(model|models|provider|providers?)\s+(status|stats?)\s*$", cmd_lower):
            return _ret(self._ai_model_status_text())
        if re.search(
            r"\b(what|which)\s+(model|llm|ai)\b.{0,24}\b(you|opuntia)\b|\bmodel\s+used\s+by\s+opuntia\b|\bwhat\s+about\s+the\s+model\s+used\s+by\s+opuntia\b",
            cmd_lower,
            flags=re.IGNORECASE,
        ):
            return _ret(self._ai_model_status_text())
        if re.match(r"^\s*reload\s+(training|prompt)\s+(prompts?|examples?)\s*$", cmd_lower):
            self.load_prompt_examples()
            self._audit("training_reload", "allowed", {"count": len(self.prompt_examples)})
            return f"Reloaded training prompts ({len(self.prompt_examples)} examples)."
        if re.match(r"^\s*mcp\s+reload\s*$", cmd_lower):
            if self.mcp_bridge is None:
                return _ret("MCP bridge unavailable. Install dependency with: pip install mcp", remember=False)
            self.mcp_bridge.load_config()
            self._mcp_allowed_dirs_cache = []
            self._mcp_allowed_dirs_ts = 0.0
            return _ret(self._mcp_status_text())
        if re.match(r"^\s*mcp\s+(status|stats?)\s*$", cmd_lower):
            return _ret(self._mcp_status_text())
        if re.match(r"^\s*context\s+(status|stats?)\s*$", cmd_lower):
            return _ret(self._topic_anchor_status_text())
        if re.match(r"^\s*context\s+(reset|clear)\s*$", cmd_lower):
            self._reset_topic_anchor()
            return _ret("Context anchor reset.")
        if re.match(r"^\s*mcp\s+servers?\s*$", cmd_lower):
            return _ret(self._mcp_servers_text())
        if re.match(r"^\s*mcp\s+routing\s+(status|stats?)\s*$", cmd_lower):
            return _ret(self._mcp_routing_status_text())
        _mcp_tools = re.match(r"^\s*mcp\s+tools\s+([a-zA-Z0-9_.-]+)\s*$", user_input, re.IGNORECASE)
        if _mcp_tools:
            return _ret(self._mcp_tools_text(_mcp_tools.group(1)))
        _mcp_call = re.match(
            r"^\s*mcp\s+call\s+([a-zA-Z0-9_.-]+)\s+([a-zA-Z0-9_.:\-/]+)(?:\s+(.+))?\s*$",
            user_input,
            re.IGNORECASE,
        )
        if _mcp_call:
            server_name = (_mcp_call.group(1) or "").strip()
            tool_name = (_mcp_call.group(2) or "").strip()
            args_raw = (_mcp_call.group(3) or "").strip()
            args_obj = {}
            if args_raw:
                try:
                    parsed = json.loads(args_raw)
                except Exception as e:
                    return _ret(f"Invalid MCP call JSON args: {e}", remember=False)
                if not isinstance(parsed, dict):
                    return _ret("MCP call args must be a JSON object.", remember=False)
                args_obj = parsed
            return _ret(self._mcp_call_text(server_name, tool_name, args_obj))
        if re.match(r"^\s*(ai\s+)?providers?\s+(status|stats?)\s*$", cmd_lower):
            return self._provider_stats_text()
        if re.match(r"^\s*(ai\s+)?providers?\s+reset\s*$", cmd_lower):
            self._reset_provider_stats()
            return "Provider stats reset."
        if re.match(r"^\s*(ai\s+)?providers?\s+cooldown\s+clear\s*$", cmd_lower):
            self.provider_cooldown_until = {}
            self._save_provider_stats()
            return "Provider cooldowns cleared."
        if re.match(r"^\s*autonomy\s+(status|stats?)\s*$", cmd_lower):
            return self._autonomy_status_text()
        if re.match(r"^\s*autonomy\s+(safe|balanced|autonomous)\s*$", cmd_lower):
            mode = re.sub(r"^\s*autonomy\s+", "", cmd_lower).strip()
            ok, msg = self.set_autonomy_profile(mode, persist=True)
            return msg
        if re.match(r"^\s*(plan\s+workflow|workflow\s+plan)\s+.+$", cmd_lower):
            goal = re.sub(r"^\s*(plan\s+workflow|workflow\s+plan)\s+", "", user_input, flags=re.IGNORECASE).strip()
            plan = self._build_workflow_plan(goal)
            steps = plan.get("steps") or []
            lines = [f"Workflow plan ({len(steps)} steps):"]
            for i, s in enumerate(steps[:20], start=1):
                lines.append(f"{i}. {s}")
            lines.append("Use `run workflow` to execute.")
            return "\n".join(lines)
        if re.match(r"^\s*(workflow\s+status|show\s+workflow)\s*$", cmd_lower):
            plan = self.pending_workflow_plan if isinstance(self.pending_workflow_plan, dict) else None
            if not plan:
                return "No pending workflow."
            steps = plan.get("steps") or []
            cur = int(plan.get("cursor", 0))
            return (
                f"Workflow pending: {cur}/{len(steps)} steps executed.\n"
                f"Goal: {plan.get('goal','')}\n"
                "Use `run workflow` to continue."
            )
        if re.match(r"^\s*(run|execute)\s+workflow\s*$", cmd_lower):
            return self._execute_workflow_plan(max_steps=24)
        if re.match(r"^\s*(clear|cancel)\s+workflow\s*$", cmd_lower):
            self.pending_workflow_plan = None
            return "Cleared pending workflow."
        if re.match(r"^\s*(memory|mem)\s+(status|stats?)\s*$", cmd_lower):
            return self._memory_status_text()
        if re.match(r"^\s*(memory|mem)\s+(on|off)\s*$", cmd_lower):
            target = "on" if "on" in cmd_lower else "off"
            self.set_memory_enabled(target == "on", persist=True)
            return "Memory enabled." if target == "on" else "Memory disabled."
        if re.match(r"^\s*(feedback)\s+(on|off)\s*$", cmd_lower):
            target = "on" if "on" in cmd_lower else "off"
            self.set_feedback_enabled(target == "on", persist=True)
            return "Feedback enabled." if target == "on" else "Feedback disabled."
        if re.match(r"^\s*(private)\s+(on|off)\s*$", cmd_lower):
            target = "on" if "on" in cmd_lower else "off"
            self.set_private_mode(target == "on", persist=True)
            return "Private mode enabled." if target == "on" else "Private mode disabled."
        if re.match(r"^\s*(memory|mem)\s+recent(?:\s+\d+)?\s*$", cmd_lower):
            n = 8
            m_recent = re.search(r"(\d+)\s*$", cmd_lower)
            if m_recent:
                n = max(1, min(30, int(m_recent.group(1))))
            return "Recent memory:\n" + self._memory_recent_text(limit=n)
        if re.match(r"^\s*(memory|mem)\s+facts?(?:\s+\d+)?\s*$", cmd_lower):
            n = 15
            m_facts = re.search(r"(\d+)\s*$", cmd_lower)
            if m_facts:
                n = max(1, min(50, int(m_facts.group(1))))
            return "Learned facts:\n" + self._memory_facts_text(limit=n)
        if re.match(r"^\s*(memory|mem)\s+(insights|learning|hermes)(?:\s+\d+)?\s*$", cmd_lower):
            n = 12
            m_insights = re.search(r"(\d+)\s*$", cmd_lower)
            if m_insights:
                n = max(1, min(50, int(m_insights.group(1))))
            return "Hermes learning insights:\n" + self._memory_insights_text(limit=n)
        if re.match(r"^\s*(memory|mem)\s+(recaps|recap|sessions?)(?:\s+\d+)?\s*$", cmd_lower):
            n = 8
            m_recaps = re.search(r"(\d+)\s*$", cmd_lower)
            if m_recaps:
                n = max(1, min(40, int(m_recaps.group(1))))
            return "Session recaps:\n" + self._memory_recaps_text(limit=n)
        if re.match(r"^\s*(outcomes?|tasks?)\s+(status|stats?)\s*$", cmd_lower):
            return self._task_outcomes_status_text()
        if re.match(r"^\s*(outcomes?|tasks?)\s+recent(?:\s+\d+)?\s*$", cmd_lower):
            n = 12
            m_out = re.search(r"(\d+)\s*$", cmd_lower)
            if m_out:
                n = max(1, min(80, int(m_out.group(1))))
            return "Recent task outcomes:\n" + self._task_outcomes_recent_text(limit=n)
        if re.match(r"^\s*(trajectory|trajectories|trace)\s+(status|stats?)\s*$", cmd_lower):
            return self._trajectory_status_text()
        if re.match(r"^\s*(trajectory|trajectories|trace)\s+recent(?:\s+\d+)?\s*$", cmd_lower):
            n = 6
            m_tr = re.search(r"(\d+)\s*$", cmd_lower)
            if m_tr:
                n = max(1, min(40, int(m_tr.group(1))))
            return "Recent trajectories:\n" + self._trajectory_recent_text(limit=n)
        if re.match(r"^\s*memory\s+safety\s+status\s*$", cmd_lower):
            return (
                "Memory safety:\n"
                f"  - blocked_entries: {int(self.memory_safety_block_count)}\n"
                "  - policy: injection/exfiltration patterns and invisible unicode are blocked"
            )
        if re.match(r"^\s*playbook(?:\s+.+)?\s*$", cmd_lower):
            target = re.sub(r"^\s*playbook\s*", "", user_input, flags=re.IGNORECASE).strip()
            return self._playbook_for_query_text(target)
        if re.match(r"^\s*(memory|mem)\s+export\s*$", cmd_lower):
            return self._export_memory_bundle()
        if re.match(r"^\s*(memory|mem)\s+forget\s+last\s*$", cmd_lower):
            if self.conversation_history:
                self.conversation_history.pop()
                self.save_memory()
                return "Forgot the last memory item."
            return "No memory items to forget."
        if re.match(r"^\s*(memory|mem)\s+clear\s+(.+?)\s*$", cmd_lower):
            target = re.sub(r"^\s*(memory|mem)\s+clear\s+", "", cmd_lower).strip()
            return self._clear_memory_bucket(target)
        if re.match(r"^\s*feedback\s+export\s*$", cmd_lower):
            return self._export_feedback_bundle()
        if re.match(r"^\s*(permission|permissions)\s+status\s*$", cmd_lower):
            if self.pending_question is None:
                return "No pending permission request."
            return self._format_pending_question_prompt(self.pending_question)
        if re.match(r"^\s*skills?\s+(status|list)\s*$", cmd_lower):
            return self._skills_status_text()
        if re.match(r"^\s*skills?\s+reload\s*$", cmd_lower):
            self.load_skills()
            return f"Skills reloaded: {len(self.skills)} found."
        if re.match(r"^\s*skills?\s+(on|enable)\s+(.+)$", cmd_lower):
            target = re.sub(r"^\s*skills?\s+(on|enable)\s+", "", user_input, flags=re.IGNORECASE).strip()
            ok, msg = self._set_skill_enabled(target, True)
            return msg
        if re.match(r"^\s*skills?\s+(off|disable)\s+(.+)$", cmd_lower):
            target = re.sub(r"^\s*skills?\s+(off|disable)\s+", "", user_input, flags=re.IGNORECASE).strip()
            ok, msg = self._set_skill_enabled(target, False)
            return msg

        if re.match(r"^\s*(research|web)\s+trace\s+(on|off)\s*$", cmd_lower):
            on = bool(re.search(r"\bon\b", cmd_lower))
            self.web_research_trace = on
            return f"Research trace mode: {'ON' if on else 'OFF'}"
        if re.match(r"^\s*universal\s+mode\s+(on|off)\s*$", cmd_lower):
            on = bool(re.search(r"\bon\b", cmd_lower))
            self.web_universal_mode = on
            return f"Universal web mode: {'ON' if on else 'OFF'}"
        if re.match(r"^\s*universal\s+mode\s+status\s*$", cmd_lower):
            return f"Universal web mode is {'ON' if self.web_universal_mode else 'OFF'}."
        if re.match(r"^\s*(trace|debug)\s+research\s+(.+)$", cmd_lower):
            q = re.sub(r"^\s*(trace|debug)\s+research\s+", "", user_input, flags=re.IGNORECASE).strip()
            if not q:
                return "Please provide a research query."
            return self._format_research_trace_for_chat(q)
        if re.match(
            r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening))"
            r"(?:\s+(there|assistant|ai|bot))?[.!?]*\s*$",
            cmd_lower,
        ):
            return "Hello. How can I help?"
        if re.match(r"^\s*(hru|how\s+r\s+u|how\s+are\s+you)\s*[?!.]*\s*$", cmd_lower):
            return "I'm good and ready to help. What do you need?"
        if re.search(r"\b(what'?s\s+up|was\s+up|wassup|how'?s\s+it\s+going|hows\s+it\s+going|hows\s+going\s+on)\b", cmd_lower):
            return "I'm doing well and ready to help. What do you need?"
        
        # Handle any message containing a URL Ã¢Â€Â” use original input to preserve URL case
        _urls_in_msg = re.findall(r'https?://[^\s<>"\']+', user_input)
        if not _urls_in_msg and re.search(r"\b(open|visit|read)\b.*\blink\b|\bopen link\b|\blearn more\b", cmd_lower):
            last_url = self._find_last_url_in_history()
            if last_url:
                return self._handle_url_with_question(last_url, user_input)
        if _urls_in_msg:
            url = _urls_in_msg[0].rstrip('.,;!?)')
            # Strip the URL(s) from the message to get the user's question/instruction
            _question = user_input
            for _u in _urls_in_msg:
                _question = _question.replace(_u, '')
            _question = _question.strip(' \t\n\r.,;:!?')
            # Strip bare navigation verbs that aren't real questions
            _bare_nav = re.match(
                r'^(open|browse|go\s+to|navigate\s+to|visit|load|show\s+me|fetch|read|launch)\s*$',
                _question, re.IGNORECASE,
            )
            if _bare_nav:
                _question = None
            # "open <url>" with no real question → just open it in the browser visibly
            if not _question:
                if self._open_url_in_browser(url, None):
                    return f"Opened {url}."
                return f"Could not open {url}."
            return self._handle_url_with_question(url, _question)
        
        # Handle "that's wrong / search from internet / bring from internet" corrections Ã¢Â€Â”
        # user is telling the AI its last answer was wrong and wants a real web search.
        # Extract the actual topic from conversation history, not from this complaint message.
        _correction_cues = re.search(
            r"\b(wrong|incorrect|not right|mistaken|didn'?t search|didn'?t use|from internet|from the internet|from web|bring.*internet|search.*internet|use.*internet|check.*internet|look.*internet"
            r"|make more research|more research|deeper research|search more|look more|dig deeper|find more|search again|look again|try again|search harder)\b",
            cmd_lower,
        )
        _is_direct_search_request = bool(
            re.search(r"\b(search|research|look up|find)\b", cmd_lower)
            and re.search(r"\b(internet|web|online)\b", cmd_lower)
            and not re.search(r"\b(wrong|incorrect|not right|mistaken|didn'?t|again|more research|deeper research|search more|look more|dig deeper|search again|look again|try again|search harder)\b", cmd_lower)
        )
        if _correction_cues and not _is_direct_search_request:
            # Try to find the last user question that wasn't a meta-command
            _last_real_topic = ""
            if self.conversation_history:
                for _item in reversed(self.conversation_history[-6:]):
                    _prev = (_item.get("user") or "").strip()
                    _prev_low = _prev.lower()
                    if not _prev_low or _prev_low == cmd_lower:
                        continue
                    # Skip if this is itself a correction/meta command
                    if re.search(r"\b(wrong|incorrect|didn'?t|from internet|bring.*internet|search.*internet)\b", _prev_low):
                        continue
                    if not self._is_smalltalk_query(_prev_low):
                        _last_real_topic = _prev
                        break
            if _last_real_topic:
                # If the last topic was a screen-vision query (e.g. "what do you see?"),
                # don't web-search it Ã¢Â€Â” just acknowledge the correction.
                _screen_query_pat = re.compile(
                    r"\b(what (are|do) you (see|seeing|look at|looking at)|what.?s on (my )?screen"
                    r"|what can you see|describe (my )?screen|read (my )?screen"
                    r"|what.?s (in|on) (my )?(screen|taskbar|desktop|window))\b",
                    re.I,
                )
                if _screen_query_pat.search(_last_real_topic):
                    return "Sorry about that Ã¢Â€Â” I may have misread the screen. Could you describe what you actually see, or re-enable Live so I can take another look?"
                return self._answer_from_live_web(_last_real_topic)
            else:
                # Correction cue fired but no prior topic found â€” ask clearly.
                return "I understand that was incorrect â€” could you tell me more specifically what was wrong, or rephrase your question so I can search again?"

        # Handle research requests with browsing
        if re.search(r"\b(research|browse|find info|look up)\b", cmd_lower) and re.search(r"\b(for|about|on)\b", cmd_lower):
            topic = self._extract_research_topic(user_input)
            if topic:
                return self.browse_and_research(topic)
        
        # Date/time quick-answers Ã¢Â€Â” only for short queries, not documents that contain "date:" fields
        _is_short_query = len(cmd_lower.split()) <= 12 and not _has_write_body
        if _is_short_query and re.search(r"\b(today'?s date|what(?:'s| is)\s+the\s+date|current date)\b", cmd_lower):
            now = datetime.now()
            return f"Today's date is {now.strftime('%A, %B %d, %Y')}."
        if _is_short_query and re.search(r"\bwhat(?:'s| is)\s+(?:the\s+)?(?:date|today)\b", cmd_lower):
            now = datetime.now()
            return f"Today's date is {now.strftime('%A, %B %d, %Y')}."
        if _is_short_query and re.search(
            r"\b(what(?:'s| is)\s+(?:the\s+)?(?:current\s+)?time|current\s+time|what\s+time\s+is\s+it|tell\s+me\s+the\s+time)\b",
            cmd_lower
        ) and not re.search(r"\b(prayer|salat|salah|weather|game|match|ucl|schedule|kickoff|kick.off|local\s+time|start\s+time|match\s+time)\b", cmd_lower):
            now = datetime.now()
            return f"The current time is {now.strftime('%H:%M:%S')}."
        if self._is_greeting_location_query(user_input):
            return self._greeting_location_help_text()
        if _is_short_query and self._is_reassurance_followup(cmd_lower):
            _reassure = self._handle_reassurance_followup()
            if _reassure:
                return _reassure
        if (
            re.search(r"\b(research|reserach|reseach|resarch|search)\b", cmd_lower)
            and re.search(r"\b(internet|web|online)\b", cmd_lower)
        ):
            topic = self._extract_research_topic(user_input)
            if not topic:
                return (
                    "Yes. I can research live information from the internet. "
                    "Tell me the exact topic you want, and I will bring results with links."
                )
            return self._answer_from_live_web(topic)
        
        _is_composing = bool(
            re.search(r"\b(write|compose|draft|create|make|prepare|send|format|help me write)\b", cmd_lower)
            and re.search(r"\b(mail|email|message|letter|text|note|report|document|memo)\b", cmd_lower)
        )
        if not _is_composing and re.search(r"\b(news|headlines?|updates?)\b", cmd_lower) and re.search(r"\b(latest|today|current|internet|web|online)\b", cmd_lower):
            return self._get_latest_news(user_input, limit=6)
        if (
            re.search(r"\b(can you|do you)\b", cmd_lower)
            and re.search(r"\b(search|research|reserach|reseach|look up|find)\b", cmd_lower)
            and re.search(r"\b(internet|web|online)\b", cmd_lower)
        ):
            return (
                "Yes. I can research live information from the internet and bring links. "
                "Tell me the exact topic, for example: 'latest Gemini update today with sources'."
            )
        if re.search(r"\b(computer|pc|windows|my)\s+(user\s*name|username|user name)\b", cmd_lower) or re.search(r"\bwhat('?s| is)\s+my\s+(username|user name)\b", cmd_lower):
            user = self._get_local_username()
            return f"Your current Windows username is: {user}"
        if re.search(r"\b(weather)\b", cmd_lower) and re.search(r"\b(now|right now|today|next)\b", cmd_lower):
            hrs = 12 if re.search(r"\bnext\s+12\b", cmd_lower) else 12
            return self._get_weather_now_and_next_hours(user_input, hours=hrs)
        # â”€â”€ CHAT MODE GATE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # All handlers below this point execute desktop/system tasks: doc creation,
        # app launching, navigation, file ops, system controls, screen automation.
        # In chat mode NONE of these must ever run â€” every message goes straight to
        # the LLM. Web search, conversation, and research are handled internally by
        # intelligent_respond's own routing.
        # ── CONVERSATIONAL GATE (chat mode + non-task messages in task mode) ───
        # Chat mode: ALL messages go to intelligent_respond — no task handlers.
        # Task mode: conversational messages (questions, analysis, discussion) also
        # go to intelligent_respond; only genuine task commands reach the handlers below.
        _is_task_command = bool(re.search(
            r'\b(open|launch|start|run|close|kill|quit|exit|minimize|maximise|maximize|restore'
            r'|click|type|press|scroll|drag|move\s+(?:to|the\s+cursor)|screenshot|screen\s+shot'
            r'|capture\s+(?:screen|window)|take\s+(?:a\s+)?screenshot'
            r'|create|make|write|save|generate|build|produce|export|convert'
            r'|navigate|go\s+to|open\s+(?:folder|directory|path|file)'
            r'|search\s+(?:for\s+)?(?:files?|folder|document)|search\s+\w+\s+on\s+\w+|find\s+(?:file|folder|document)'
            r'|set\s+(volume|brightness|alarm|timer|reminder)'
            r'|install|uninstall|download|upload'
            r'|send\s+(?:an?\s+)?(?:email|message|mail)'
            r'|schedule|remind\s+me|set\s+(?:an?\s+)?(?:alarm|reminder|timer)'
            r'|turn\s+(?:on|off)|enable|disable|toggle'
            r'|copy|paste|move|delete|rename|zip|extract|compress)\b',
            cmd_lower,
        ))
        if _input_mode == "chat" or (_input_mode == "task" and not _is_task_command):
            _fup = self._get_followup_context(user_input)
            # Keep original wording for follow-ups; context is provided via system hint.
            _chat_input = user_input
            _chat_msgs = self._build_standard_messages(_chat_input)
            if _fup:
                # Inject follow-up hint so the LLM knows this continues the last topic
                _chat_msgs.insert(-1, {"role": "system", "content": _fup})
            _chat_answer = self.intelligent_respond(
                _chat_input, messages=_chat_msgs, has_live_screen=bool(shared_screen_path)
            )
            self._capture_turn(user_input, _chat_answer, remember=True)
            return _chat_answer

        # â”€â”€ FAST-PATH GUARD: PDF/Word creation bypasses ALL web-research routing â”€â”€â”€â”€â”€â”€
        # This runs before _should_force_universal_web_research and _should_auto_web_research
        # to ensure doc-creation commands NEVER reach web search, regardless of any edge
        # case in the individual gate functions.
        _is_doc_cmd = bool(
            re.search(r'\b(pdf|\.pdf|docx?|\.docx?|word\s+(doc(ument)?|file)|text\s+file|note\s+file|txt\s*file?\b|\.txt|\btxt\b|pptx?|\.pptx?|pow[a-z]*oint|presentation|slides?\b|slide\s+deck|xlsx?|\.xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b', cmd_lower)
            or re.search(r'\b(?:write|create|save|export|put)\s+what\s+(?:(?:you|u)|(?:have|had)\s+(?:you|u))\b', cmd_lower)
            or re.search(r'\bwrite\s+(the\s+)?(last|previous)\b', cmd_lower)
            or re.search(r'\b(save|export)\s+(your\s+)?last\b', cmd_lower)
            or re.search(r'\b(generate|create|make|produce|build|export|save|write|give|prepare|draft)\s+(a\s+|an\s+|new\s+|the\s+|me\s+a?\s*)?(pdf|docx?|word\s+(doc(ument)?|file)|text\s+file|note\s+file|txt\s*file?\b|\.txt|pptx?|pow[a-z]*oint|presentation|slides?|slide\s+deck|xlsx?|excell?|spreadsheet|google\s+sheets?|gsheet)\b', cmd_lower)
            or re.search(r'\b(convert|turn|transform|export|save)\s+(?:\S+\s+){0,5}(to|into|as)\s+(a\s+)?(pdf|docx?|word|pptx?|pow[a-z]*oint|presentation|slides?|txt|xlsx?|excell?|spreadsheet|google\s+sheets?|gsheet)\b', cmd_lower)
        )
        if _is_doc_cmd:
            _dbg_log.debug(f'fast-path: _is_doc_cmd=True user_input={repr(user_input[:60])} allow_sensitive_fs={allow_sensitive_fs}')
            try:
                _fast_pdf = self._handle_pdf_command(
                    user_input, allow_desktop=True, allow_mutation=allow_sensitive_fs
                )
            except Exception as _fp_exc:
                _dbg_log.debug(f'  fast-path _handle_pdf_command EXCEPTION: {_fp_exc}')
                _fast_pdf = None
            _dbg_log.debug(f'  fast-path _fast_pdf={repr(str(_fast_pdf)[:80]) if _fast_pdf is not None else None}')
            if _fast_pdf is not None:
                return _fast_pdf
            try:
                _fast_word = self._handle_word_command(
                    user_input, allow_desktop=True, allow_mutation=allow_sensitive_fs
                )
            except Exception as _fw_exc:
                _dbg_log.debug(f'  fast-path _handle_word_command EXCEPTION: {_fw_exc}')
                _fast_word = None
            _dbg_log.debug(f'  fast-path _fast_word={repr(str(_fast_word)[:80]) if _fast_word is not None else None}')
            if _fast_word is not None:
                return _fast_word
            # â”€â”€ Secondary fast-path fallback (authorized only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Both handlers returned None. If user is authorized, handle directly.
            if allow_sensitive_fs:
                _sp_fb_last_pat = re.compile(
                    r'\b(?:write|create|put|save|generate|make|produce|export|build)\b.{0,50}'
                    r'\b(?:what\s+(?:(?:you|u)(?:\'?ve)?\s+(?:have\s+)?|(?:have|had)\s+(?:you|u)\s+)(?:just\s+)?(?:sent|said|wrote|written|replied?|gave|given)'
                    r'|(?:the\s+)?(?:last|previous|latest)\s+(?:response|answer|message|reply)'
                    r'|your\s+(?:last|previous|latest)'
                    r'|inside\s+(?:what|it|that)\s+(?:you|u|i|we)\s+(?:have\s+)?(?:sent|said|wrote|given)'
                    r'|inside\s+(?:the\s+)?(?:last|previous)\b)',
                    re.IGNORECASE | re.DOTALL,
                )
                _sp_inline_m = re.search(
                    r'(?:write\s*:|inside\s*(?:this\s*)?:|and\s+write\s*:|write\s+(?:this|it|that|inside|content)\s*:|following\s*:|put\s*:|generate\s+\w+\s+inside\s*:)\s*(.{5,})',
                    user_input, re.DOTALL | re.IGNORECASE,
                )
                if not _sp_inline_m:
                    _sp_inline_m = re.search(r':\s*(.{20,})$', user_input, re.DOTALL)
                if _sp_fb_last_pat.search(user_input):
                    _sp_content = ''
                    for _sp_hist in [list(getattr(self, 'task_conversation_history', [])), list(getattr(self, 'conversation_history', []))]:
                        for _sp_msg in reversed(_sp_hist):
                            _sp_ai = (_sp_msg.get('assistant') or _sp_msg.get('content') or '').strip()
                            if _sp_ai:
                                _sp_content = self._strip_ai_sources(_sp_ai)
                                break
                        if _sp_content:
                            break
                elif _sp_inline_m:
                    _sp_content = _sp_inline_m.group(1).strip()
                else:
                    # Only grab last AI response if command explicitly asks for a document type
                    _sp_wants_doc = bool(re.search(
                        r'\b(pdf|\.pdf|docx?|word|txt|text\s+file|note|pptx?|presentation|xlsx?|spreadsheet)\b',
                        cmd_lower,
                    ))
                    _sp_content = ''
                    if _sp_wants_doc:
                        for _sp_hist in [list(getattr(self, 'task_conversation_history', [])), list(getattr(self, 'conversation_history', []))]:
                            for _sp_msg in reversed(_sp_hist):
                                _sp_ai = (_sp_msg.get('assistant') or _sp_msg.get('content') or '').strip()
                                if _sp_ai:
                                    _sp_content = self._strip_ai_sources(_sp_ai)
                                    break
                            if _sp_content:
                                break
                if _sp_content:
                    _sp_desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                    _sp_nm = re.search(r'\b(?:called|named)\s+["\']?([^"\',:]+?)["\']?\s*$', user_input, re.IGNORECASE)
                    _sp_base = re.sub(r'[\\/*?:"<>|]', '', (_sp_nm.group(1).strip(' "\'.,') if _sp_nm else self._generate_doc_title(_sp_content))).strip() or 'Response'
                    _sp_is_pptx = bool(re.search(r'\b(pptx?|\.pptx?|pow[a-z]*oint|presentation|slide\s+deck|slides?\b)', cmd_lower))
                    _sp_is_xlsx = bool(re.search(r'\b(xlsx?|\.xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b', cmd_lower)) and not _sp_is_pptx
                    _sp_is_word = bool(re.search(r'\b(docx?|word(?:\s+(doc(?:ument)?|file))?|\.docx?)\b', cmd_lower)) and not _sp_is_pptx and not _sp_is_xlsx
                    _sp_is_note = bool(re.search(r'\b(note\s*file|text\s*file|\.txt|txt\s*file?\b|\btxt\b|note\b)', cmd_lower)) and not _sp_is_word and not _sp_is_pptx and not _sp_is_xlsx
                    _sp_reply = None
                    if _sp_is_pptx:
                        _sp_path = os.path.join(_sp_desktop, _sp_base + '.pptx')
                        _sp_saved, _sp_err = self._create_pptx_document(_sp_path, _sp_content, doc_title=_sp_base)
                        if not _sp_err:
                            try: os.startfile(_sp_saved)
                            except Exception: pass
                            _sp_reply = f"**Saved and opened** `{_sp_base}.pptx` on your Desktop"
                        else:
                            _sp_reply = f"Could not create presentation: {_sp_err}"
                    elif _sp_is_xlsx:
                        _sp_path = os.path.join(_sp_desktop, _sp_base + '.xlsx')
                        _sp_saved, _sp_err = self._create_excel_document(_sp_path, _sp_content, doc_title=_sp_base)
                        if not _sp_err:
                            try: os.startfile(_sp_saved)
                            except Exception: pass
                            _sp_reply = f"**Saved and opened** `{_sp_base}.xlsx` on your Desktop"
                        else:
                            _sp_reply = f"Could not create spreadsheet: {_sp_err}"
                    elif _sp_is_word:
                        _sp_path = os.path.join(_sp_desktop, _sp_base + '.docx')
                        _sp_saved, _sp_err = self._create_word_document(_sp_path, _sp_content, doc_title=_sp_base)
                        if not _sp_err:
                            try: os.startfile(_sp_saved)
                            except Exception: pass
                            _sp_reply = f"**Saved and opened** `{_sp_base}.docx` on your Desktop"
                        else:
                            _sp_reply = f"Could not create document: {_sp_err}"
                    elif _sp_is_note:
                        _sp_path = os.path.join(_sp_desktop, _sp_base + '.txt')
                        try:
                            with open(_sp_path, 'w', encoding='utf-8') as _sp_f: _sp_f.write(_sp_content)
                            try: os.startfile(_sp_path)
                            except Exception: pass
                            _sp_reply = f"**Saved and opened** `{_sp_base}.txt` on your Desktop"
                        except Exception as _sp_te:
                            _sp_reply = f"Could not create note file: {_sp_te}"
                    else:
                        _sp_path = os.path.join(_sp_desktop, _sp_base + '.pdf')
                        _sp_saved, _sp_err = self._create_pdf_document(_sp_path, _sp_content, doc_title=_sp_base)
                        if not _sp_err:
                            try: os.startfile(_sp_saved)
                            except Exception: pass
                            _sp_reply = f"**Saved and opened** `{_sp_base}.pdf` on your Desktop"
                        else:
                            _sp_reply = f"Could not create PDF: {_sp_err}"
                    if _sp_reply is not None:
                        _dbg_log.debug(f'  secondary fast-path fallback reply={repr(str(_sp_reply)[:80])}')
                        return _sp_reply
        # â”€â”€ END FAST-PATH GUARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        if self._should_force_universal_web_research(user_input, cmd_lower):
            topic = self._extract_research_topic(user_input) or user_input
            return self._answer_from_live_web(topic)
        if (
            self.last_live_web_query
            and re.search(r"\b(check|verify|refresh|update|recheck)\b", cmd_lower)
            and re.search(r"\b(for me|it|that|again|last)\b", cmd_lower)
        ):
            return self._answer_from_live_web(self.last_live_web_query)
        core_control_reply = self._handle_windows_core_command(user_input, cmd_lower)
        if core_control_reply is not None:
            return core_control_reply
        system_control_reply = self._handle_system_control_command(user_input, cmd_lower)
        if system_control_reply is not None:
            return system_control_reply
        if self._should_auto_web_research(cmd_lower):
            return self._answer_from_live_web(user_input)

        def app_status_reply(status_obj, still=False):
            self.last_status_app = status_obj["matched"]
            if status_obj["running"]:
                return f"{status_obj['matched']} is still running." if still else f"Yes, {status_obj['matched']} is currently running."
            return f"{status_obj['matched']} is now closed." if still else f"{status_obj['matched']} is installed but currently closed."

        # Smart inventory intent handling: all/apps/files/folders.
        # Keep this strict so generic prompts like "give me information about X" are not hijacked.
        explicit_inventory_shortcuts = {"apps", "app", "files", "file", "folders", "folder", "all", "everything", "desktop items"}
        has_inventory_target = bool(
            re.search(r"\b(apps?|applications?|files?|folders?|directories|desktop(?:\s+items?)?)\b", cmd_lower)
        )
        has_inventory_verb = bool(re.search(r"\b(list|show|see|give me|give|tell me|what(?:'s| is)|again|now\s+give|get)\b", cmd_lower))
        list_like = (has_inventory_verb and has_inventory_target) or (cmd_lower.strip() in explicit_inventory_shortcuts)
        # Never treat a creation/mutation command as a listing command
        is_creation_cmd = bool(re.match(
            r"^(?:create|make|write|append|add|delete|remove|rename|move|put|place|call|change\s+(?:the\s+)?name|open\s+(?:word|doc))\b",
            cmd_lower.strip()
        ))
        # _has_write_body already set near top of process_command
        # Extension-filtered file listing: "list png on desktop", "show .pdf files"
        # Only scan first 80 chars Ã¢Â€Â” avoids matching extensions buried in user-written content
        _cmd_head = cmd_lower[:80]
        ext_filter_m = re.search(
            r'\b(png|jpg|jpeg|gif|svg|ico|avif|pdf|txt|doc|docx|xls|xlsx|csv|mp4|mp3|mp4|zip|rar|py|js|ts|html|exe|lnk)\b',
            _cmd_head,
        ) if (not is_creation_cmd and not _has_write_body) else None
        ext_filter = ext_filter_m.group(1).lower() if ext_filter_m else None
        # "only .png", "just png", "no only .png" follow-up pattern
        only_ext = bool(re.search(r'\b(only|just|no only|filter|show only)\b', cmd_lower)) and ext_filter is not None

        if not is_creation_cmd and not _has_write_body and (list_like or (ext_filter and re.search(r"\b(desktop|files?|list|show|give|only|just)\b", cmd_lower))):
            wants_apps = bool(re.search(r"\bapp(s)?\b", cmd_lower))
            wants_files = bool(re.search(r"\bfile(s)?\b", cmd_lower)) or ext_filter is not None
            wants_folders = bool(re.search(r"\bfolder(s)?|director(y|ies)\b", cmd_lower))
            wants_desktop = "desktop" in cmd_lower or ext_filter is not None
            wants_all = (has_inventory_target and bool(re.search(r"\ball\b|\beverything\b", cmd_lower))) or cmd_lower.strip() in {"all", "everything"}


            q = cmd_lower.strip()
            if q in {"apps", "app"}:
                wants_apps = True
            elif q in {"files", "file"}:
                wants_files = True
                wants_desktop = True
            elif q in {"folders", "folder"}:
                wants_folders = True
                wants_desktop = True
            elif q == "desktop items":
                wants_desktop = True

            # Apps-only request.
            if wants_apps and not (wants_all or wants_files or wants_folders or wants_desktop):
                apps = self.get_running_apps()
                return "Running applications:\n" + "\n".join([f"  - {a}" for a in apps]) if apps else "No applications running."

            # Desktop-scoped inventory.
            if wants_desktop or wants_files or wants_folders or wants_all:
                entries = self._desktop_entries(limit=300)
                files = [e["name"] for e in entries if not e["is_dir"]]
                folders = [e["name"] for e in entries if e["is_dir"]]

                # Apply extension filter if requested
                if ext_filter:
                    filtered = [f for f in files if f.lower().endswith("." + ext_filter)]
                    label = f".{ext_filter.upper()} files on Desktop ({len(filtered)} found):"
                    return label + "\n" + ("\n".join([f"  - {n}" for n in filtered]) if filtered else "  - (none)")

                sections = []

                include_apps = wants_all or (wants_apps and (wants_files or wants_folders or wants_desktop))
                if include_apps:
                    apps = self.get_running_apps()
                    sections.append(
                        "Running applications:\n" + ("\n".join([f"  - {a}" for a in apps]) if apps else "  - (none)")
                    )

                if wants_all:
                    sections.append("Desktop files:\n" + ("\n".join([f"  - {n}" for n in files]) if files else "  - (none)"))
                    sections.append("Desktop folders:\n" + ("\n".join([f"  - {n}" for n in folders]) if folders else "  - (none)"))
                elif wants_files and not wants_folders:
                    sections.append("Desktop files:\n" + ("\n".join([f"  - {n}" for n in files]) if files else "  - (none)"))
                elif wants_folders and not wants_files:
                    sections.append("Desktop folders:\n" + ("\n".join([f"  - {n}" for n in folders]) if folders else "  - (none)"))
                elif wants_desktop:
                    names = [e["name"] for e in entries]
                    sections.append("Desktop items:\n" + ("\n".join([f"  - {n}" for n in names]) if names else "  - (none)"))

                if sections:
                    return "\n\n".join(sections)

        # Combined inventory intent: "list apps and desktop items".
        # Guard: skip for file/doc creation commands Ã¢Â€Â” content body often contains words
        # like "list", "app", "desktop", "running" that describe capabilities, not inventory requests.
        if not is_creation_cmd and not _has_write_body:
            if re.search(r"\b(list|show|see|give me)\b", cmd_lower) and re.search(r"\bdesktop\b", cmd_lower) and re.search(r"\bapps?\b", cmd_lower):
                apps = self.get_running_apps()
                desktop_items = self._desktop_items_snapshot(limit=80)
                app_block = "Running applications:\n" + "\n".join([f"  - {a}" for a in apps]) if apps else "Running applications:\n  - (none)"
                desk_block = "Desktop items:\n" + "\n".join([f"  - {d}" for d in desktop_items]) if desktop_items else "Desktop items:\n  - (none)"
                return app_block + "\n\n" + desk_block

            if (re.search(r"\bapps?\b", cmd_lower) and re.search(r"\brunning\b", cmd_lower)) or re.search(r"\b(list|show|see)\s+(?:all\s+)?apps?\b", cmd_lower):
                apps = self.get_running_apps()
                return "Running applications:\n" + "\n".join([f"  - {app}" for app in apps]) if apps else "No applications running."
            if re.search(r"\bclosed\s+apps?\b|\bapps?\s+closed\b|\bnot\s+running\s+apps?\b", cmd_lower):
                closed = self.get_closed_apps(limit=20)
                return "Installed but not running:\n" + "\n".join([f"  - {a}" for a in closed]) if closed else "I couldn't identify closed apps."

        rewritten_for_file = self._rewrite_natural_desktop_file_command(user_input)
        # Rename/move/delete always operate on Desktop items Ã¢Â€Â” always allow Desktop access
        _is_rename_move = bool(re.match(r"^(?:rename|move|put|place|delete|remove|copy)\b", cmd_lower.strip()))
        allow_desktop_for_file = allow_sensitive_fs or self._is_non_sensitive_desktop_query(rewritten_for_file) or _is_rename_move

        # Word document creation Ã¢Â€Â” must run before general file handler
        pdf_reply = self._handle_pdf_command(
            user_input,
            allow_desktop=True,
            allow_mutation=allow_sensitive_fs,
        )
        if pdf_reply is not None:
            return pdf_reply

        word_reply = self._handle_word_command(
            user_input,
            allow_desktop=True,
            allow_mutation=allow_sensitive_fs,
        )
        if word_reply is not None:
            return word_reply

        data_reply = self._handle_data_command(user_input, cmd_lower)
        if data_reply is not None:
            return data_reply

        # Complex/nested tree creation must be checked before simple file handler
        complex_reply = self._handle_complex_creation_command(
            user_input,
            allow_desktop=allow_desktop_for_file,
            allow_mutation=allow_sensitive_fs,
        )
        if complex_reply is not None:
            return complex_reply

        file_reply = self._handle_file_command(
            user_input,
            allow_desktop=allow_desktop_for_file,
            allow_mutation=allow_sensitive_fs,
        )
        if file_reply is not None:
            return file_reply

        # Prayer/salat times: fetch live online result directly.
        if re.search(r"\b(salat|salah|prayer)\b", cmd_lower) and re.search(r"\b(time|times|timing|today|tonight|now)\b", cmd_lower):
            return self._get_prayer_times_today(user_input)

        # Crypto live prices: deterministic API fetch.
        if re.search(r"\b(crypto|cryptocurrency|coin|coins|bitcoin|btc|ethereum|eth)\b", cmd_lower) and re.search(r"\b(price|prices|market)\b", cmd_lower):
            top_n = self._extract_top_n(cmd_lower, default=10, min_value=1, max_value=25)
            return self._get_top_crypto_prices(limit=top_n, currency="usd")
        if (
            self.last_structured_intent == "crypto_prices"
            and re.search(r"\b(check|give|bring|tell|show)\b", cmd_lower)
            and re.search(r"\b(last|latest|now|current)\b", cmd_lower)
            and re.search(r"\b(price|prices)\b", cmd_lower)
        ):
            top_n = int((self.last_structured_payload or {}).get("limit", 10))
            currency = (self.last_structured_payload or {}).get("currency", "usd")
            return self._get_top_crypto_prices(limit=top_n, currency=currency)
        if (
            self.last_structured_intent == "news"
            and re.search(r"\b(check|refresh|update|recheck|again|latest|last)\b", cmd_lower)
        ):
            topic = (self.last_structured_payload or {}).get("topic", "")
            return self._get_latest_news(topic or user_input, limit=int((self.last_structured_payload or {}).get("limit", 6)))

        # Latest/update/news requests: deterministic live web retrieval with links.
        live_update_topic = self._extract_live_update_topic(user_input)
        if live_update_topic:
            return self._format_live_links(live_update_topic, with_snippets=True, limit=6)
        if re.search(r"\b(bring|show|give)\b", cmd_lower) and re.search(r"\b(everything|all|full)\b", cmd_lower) and self.last_live_web_query:
            return self._format_live_links(self.last_live_web_query, with_snippets=True, limit=8)

        # Live web lookup intent: return links/results directly in chat.
        web_lookup_match = re.search(r"\b(?:search|look up|find)\s+(?:the\s+web\s+for\s+|web\s+for\s+|online\s+for\s+)?(.+)$", cmd_lower)
        wants_links = bool(re.search(r"\b(link|links|source|sources|website|websites)\b", cmd_lower))
        if web_lookup_match and wants_links:
            query = (web_lookup_match.group(1) or "").strip(" ,.?")
            query = re.sub(r"\b(on|in|using|with)\s+[a-z0-9 ._-]+$", "", query).strip(" ,.?")
            if query:
                return self._format_live_links(query, with_snippets=False, limit=5)

        # Generic "information about X on internet/web" -> fetch directly.
        info_online_match = re.search(
            r"\b(?:information|info|details|news|updates?)\s+(?:about|on)\s+(.+?)(?:\s+(?:on|from)\s+(?:the\s+)?(?:internet|web|online))?\s*$",
            cmd_lower,
            flags=re.IGNORECASE,
        )
        if info_online_match and re.search(r"\b(internet|web|online|latest|update|updates|news)\b", cmd_lower):
            topic = (info_online_match.group(1) or "").strip(" ,.?")
            if topic:
                return self._format_live_links(f"latest updates {topic}", with_snippets=True, limit=6)

        # Search intent: "search instagram on brave", "open brave and search instagram", multilingual variants.
        search_query, search_app = self._extract_search_intent(user_input)
        if search_query:
            if search_app and (not self._looks_like_known_app_request(search_app)) and (not self._is_generic_web_target(search_app)):
                return self._set_pending_confirmation(
                    "search_on_app",
                    {"query": search_query, "app": ""},
                    f"I am not sure about '{search_app}'. Do you want me to search '{search_query}' in your default browser instead? (yes/no)",
                )
            return self.search_web_on_app(search_query, search_app)

        # ── Playwright browse: "browse/read/open [url] with playwright / in browser / show me" ──
        _pw_browse_m = re.search(
            r"(?:browse|read|open|show\s+me|fetch|load)\s+(https?://\S+|www\.\S+)",
            cmd_lower,
        )
        if not _pw_browse_m:
            _pw_browse_m = re.search(
                r"(https?://\S+|www\.\S+)\s+(?:with\s+playwright|in\s+(?:the\s+)?browser|show\s+me|open\s+it|load\s+it)",
                cmd_lower,
            )
        if _pw_browse_m and sync_playwright is not None:
            _pw_url = _pw_browse_m.group(1)
            if not _pw_url.startswith("http"):
                _pw_url = "https://" + _pw_url
            result = self.open_and_read_url(_pw_url)
            return result or f"Could not open {_pw_url}."

        # Website navigation intent (go to X on browser).
        destination, browser_hint = self._extract_navigation_intent(normalized_user_input or user_input)
        if destination:
            url = self._normalize_destination_to_url(destination)
            if url and self._open_url_in_browser(url, browser_hint):
                msg = f"Opened {destination} on {browser_hint}." if browser_hint else f"Opened {destination}."
                self._record_task_outcome("open_url", "success", reason=msg, details={"destination": destination, "browser": browser_hint or ""})
                return msg
            fail_msg = f"Could not navigate to {destination}."
            self._record_task_outcome("open_url", "failed", reason=fail_msg, details={"destination": destination, "browser": browser_hint or ""})
            if self._autonomy_policy().get("mode") == "autonomous":
                recovered = self._attempt_recovery_chain("open_url", f"open {destination}", fail_msg)
                if recovered:
                    return recovered
            return self._maybe_attach_failure_playbook(fail_msg, action_hint="open_url", details={"destination": destination, "browser": browser_hint or ""})

        action, natural_target = self._extract_app_action(normalized_user_input or user_input)

        # Close/quit commands before status parsing.
        if action == "close" or cmd_lower.strip().startswith("close ") or cmd_lower.strip().startswith("quit "):
            target = natural_target or re.sub(r"^(close|quit)\s+", "", user_input, flags=re.IGNORECASE).strip()
            if target.lower() in {"it", "this", "that"}:
                if self.last_status_app:
                    target = self.last_status_app
                else:
                    return "Tell me which app to close. Example: close whatsapp"
            if not target:
                return "Tell me which app to close. Example: close whatsapp"
            if not allow_sensitive_fs:
                self._audit("close_app", "permission_requested", {"target": target, "command": user_input[:300]})
                prompt = self._set_pending_question(
                    "Permission Required",
                    f"Close '{target}' now?",
                    [
                        {"label": "Allow once", "description": "Close this app now", "value": "allow"},
                        {"label": "Deny", "description": "Keep app open", "value": "deny"},
                    ],
                    action="close_app",
                    payload={"target": target},
                    on_deny="Close app cancelled.",
                )
                return "Authorization required before closing apps.\n" + prompt
            result = self.close_app(target)
            msg = result or f"Could not close {target}"
            if result:
                self._record_task_outcome("close_app", "success", reason=msg, details={"target": target})
                return msg
            self._record_task_outcome("close_app", "failed", reason=msg, details={"target": target})
            if self._autonomy_policy().get("mode") == "autonomous":
                recovered = self._attempt_recovery_chain("close_app", f"close {target}", msg)
                if recovered:
                    return recovered
            return self._maybe_attach_failure_playbook(msg, action_hint="close_app", details={"target": target})
        # Prioritize launcher commands before status-intent parsing.
        # When Playwright browser is active, "open X" / "click X" should operate on the page, not launch apps.
        if self._pw_page is not None and re.match(r'^(?:open|click)\s+', cmd_lower.strip()):
            _pw_target = re.sub(r'^(?:open|click)\s+(?:on\s+)?(?:the\s+)?', '', cmd_lower.strip()).strip(' "\'')
            if _pw_target:
                _r = self._pw_send("click", _pw_target)
                return _r
        if action == "open" or cmd_lower.strip().startswith("open ") or cmd_lower.strip().startswith("launch "):
            if re.search(r"\bsearch\b", cmd_lower):
                q, app = self._extract_search_intent(normalized_user_input or user_input)
                if q:
                    return self.search_web_on_app(q, app)
                return self.search_web_on_app(re.split(r"\bsearch\b", cmd_lower, maxsplit=1)[-1].strip(), None)
            target = natural_target or self._guess_open_target(user_input)
            if not target:
                target = re.sub(r"^(open|launch)\s+", "", user_input, flags=re.IGNORECASE).strip()
            # Resolve pronoun targets from last checked app context.
            if target.lower() in {"it", "this", "that"}:
                if self.last_status_app:
                    target = self.last_status_app
                else:
                    return "Tell me which app to open. Example: open whatsapp"
            if len(self._normalize_app_name(target)) < 3:
                return "Please provide a clearer app name. Example: open discord"
            if not target:
                return "Tell me which app to open. Example: open whatsapp"
            self._audit("open_app", "requested", {"target": target})
            opened = self.open_app(target)
            if opened:
                self._record_task_outcome("open_app", "success", reason=opened, details={"target": target})
                return opened
            suggestion = self._suggest_open_target(target)
            if suggestion:
                self._record_task_outcome("open_app", "pending", reason=f"suggestion:{suggestion}", details={"target": target, "suggestion": suggestion})
                return self._set_pending_confirmation(
                    "open_app",
                    {"target": suggestion},
                    f"I couldn't confidently match '{target}'. Do you want me to open '{suggestion}'? (yes/no)",
                )
            msg = f"Could not open {target}"
            self._record_task_outcome("open_app", "failed", reason=msg, details={"target": target})
            if self._autonomy_policy().get("mode") == "autonomous":
                recovered = self._attempt_recovery_chain("open_app", f"open {target}", msg)
                if recovered:
                    return recovered
            return self._maybe_attach_failure_playbook(msg, action_hint="open_app", details={"target": target})

        short_query = re.sub(r"[?!.,]+$", "", cmd_lower).strip()
        if short_query and len(short_query.split()) <= 3 and short_query not in {"hello", "hi", "hey"}:
            st_short = self.get_app_status(short_query)
            if st_short["found"]:
                return app_status_reply(st_short)

        if re.search(r"\b(it|its|it's)\b", cmd_lower) and re.search(r"\b(open|running|closed)\b", cmd_lower):
            if self.last_status_app:
                return app_status_reply(self.get_app_status(self.last_status_app), still=True)
            return "Tell me the app name first. Example: is whatsapp open?"

        status_match = re.search(r"(?:is|check|whether)\s+(.+?)\s+(running|open|opened|closed)\b", cmd_lower)
        if not status_match:
            status_match = re.search(r"(.+?)\s+is\s+(running|open|opened|closed)\b", cmd_lower)
        if not status_match:
            status_match = re.search(r"(.+?)\s+(running|open|opened|closed)\s*\??$", cmd_lower)
        if status_match:
            app_query = status_match.group(1).strip()
            app_query = re.sub(
                r"^(is|check|whether|the|app|application|i|my|do you see|can you see|tell me if|please)\s+",
                "",
                app_query,
            ).strip()
            st = self.get_app_status(app_query)
            if not st["found"]:
                return f"I couldn't find an app named '{app_query}'."
            return app_status_reply(st)

        followup_match = re.search(r"^what about\s+(.+?)\??$", cmd_lower)
        if followup_match:
            app_query = followup_match.group(1).strip()
            st = self.get_app_status(app_query)
            if not st["found"]:
                return f"I couldn't find an app named '{app_query}'."
            return app_status_reply(st)

        if cmd_lower.strip() in {"and now?", "and now", "what now?", "what now"} and self.last_status_app:
            return app_status_reply(self.get_app_status(self.last_status_app), still=True)
        if re.search(r"\bscreenshot\b", cmd_lower) and not re.search(r"\b(don'?t|no|not|stop|cancel|avoid)\b.{0,20}\bscreenshot\b", cmd_lower) and not re.search(r"\bscreenshot\b.{0,30}\b(from|last|before|earlier|that|the|those|was|were|showed?|is)\b", cmd_lower):
            return f"Screenshot saved: {self.take_screenshot()}"
        if (
            re.search(r"\b(are you|you)\s+(online|connected to (the )?internet)\b", cmd_lower)
            or re.search(r"\b(can you|do you|you)\s+(have\s+)?(internet\s+)?access\b", cmd_lower)
            or re.search(r"\b(you)\s+have\s+access\s+to\s+(the\s+)?internet\b", cmd_lower)
            or re.search(r"\b(access\s+to\s+(the\s+)?internet)\b", cmd_lower)
            or re.search(r"\b(internet|online)\s+status\b", cmd_lower)
        ):
            net = self.get_network_info()
            online = bool(net.get("internet"))
            conn = net.get("wifi") or "Wired/Ethernet"
            ip = net.get("ip", "Unknown")
            if online:
                return f"Yes. Internet is connected.\nConnection: {conn}\nIP: {ip}"
            return f"No. Internet appears disconnected.\nConnection: {conn}\nIP: {ip}"
        if re.match(r"^\s*why\b", cmd_lower) and self.last_live_web_error:
            return f"The last live web search failed because: {self.last_live_web_error}. You can retry now."
        if (
            re.search(r"\b(can you|do you)\b", cmd_lower)
            and re.search(r"\b(search|research|look up|find)\b", cmd_lower)
            and re.search(r"\b(internet|web|online)\b", cmd_lower)
        ):
            return (
                "Yes. I can perform live internet research and bring results with links. "
                "Example: 'find today's prayer times in Tunis and include sources'."
            )
        if re.search(r"\bip\b", cmd_lower):
            return f"IP Address: {self.get_network_info().get('ip', 'Unknown')}"
        if re.search(r"\bstats?\b", cmd_lower) or re.search(r"\bsystem\b.{0,20}\b(stats?|info|status|usage|performance|resources|details)\b|\b(cpu|ram|disk|memory)\s*(usage|info|stats?|status)\b", cmd_lower):
            stats = self.get_system_stats()
            return (
                "System Statistics:\n"
                f"  CPU: {stats['cpu']}%\n"
                f"  Memory: {stats['memory']}% ({stats['memory_used']}GB/{stats['memory_total']}GB)\n"
                f"  Disk: {stats['disk']}% used ({stats['disk_free']}GB free)"
            )
        if re.search(r"\bwifi\b", cmd_lower) or re.search(r"\bnetwork\b.{0,20}\b(status|info|connection|speed|check|details)?\b|\b(connection|internet)\s+status\b", cmd_lower):
            net = self.get_network_info()
            status = "Connected" if net.get("internet") else "Disconnected"
            return f"Network: {status}\nConnection: {net.get('wifi', 'Wired/Ethernet')}\nIP: {net.get('ip', 'Unknown')}"
        # "check it by yourself", "find it yourself", "look it up yourself" ? search last topic
        if re.search(r"\b(check|find|look|search|browse)\b.{0,20}\b(yourself|by yourself|on your own|for yourself)\b", cmd_lower):
            topic = self.last_live_web_query or user_input
            return self._answer_from_live_web(topic)

        # "search in the internet" / "search it online" with no actual topic ? re-run last query
        if re.search(r"\bsearch\b", cmd_lower) and re.search(r"\b(in the internet|on the internet|online|on the web|in web)\b", cmd_lower):
            bare_search = not bool(re.sub(r"\b(search|in the|on the|internet|online|on|the|web|for me|please)\b", "", cmd_lower).strip())
            if bare_search and self.last_live_web_query:
                return self._answer_from_live_web(self.last_live_web_query)
        if re.search(r"\bsearch\b", cmd_lower):
            q, app = self._extract_search_intent(normalized_user_input or user_input)
            if q:
                return self.search_web_on_app(q, app)
            return self.search_web_on_app(cmd_lower.split("search")[-1].strip(), None)

        # If user asks what the AI is seeing but screen sharing is OFF, tell them clearly
        _asking_screen = re.search(
            r"\b(what (are|do) you (see|seeing|look at|looking at)|what.?s on (my )?screen|"
            r"what can you see|describe (my )?screen|read (my )?screen)\b",
            cmd_lower,
        )
        if _asking_screen and not self.screen_sharing_active:
            return (
                "Screen sharing is currently **off** Ã¢Â€Â” I can't see your screen. "
                "Click the **Live** button in the chat window to enable it, then ask again."
            )

        # -- Clarification guard: catch word-doc / note-file commands that slipped through --
        # When the command clearly intends to create a doc/note but fell past all handlers,
        # ask a quick clarifying question rather than giving a confusing AI response.
        _slipped_doc_intent = (
            _has_write_body
            and bool(re.search(r'\b(word\s*doc\w*|\.docx?|note\s*file|text\s*file|document)\b', cmd_lower))
            and not bool(re.search(r'\b(how|why|what|explain|tell me|describe|analyze)\b', cmd_lower))
        )
        if _slipped_doc_intent:
            # Best-effort: extract content after ":"
            _clarify_content = ""
            _cm = re.search(r'[:\-]\s*(.{10,})$', user_input, re.DOTALL)
            if _cm:
                _clarify_content = _cm.group(1).strip()[:120]
            _preview = (f' with content: "{_clarify_content[:80]}Ã¢Â€Â¦"') if _clarify_content else ""
            return self._set_pending_confirmation(
                "create_word_doc_clarify",
                {"user_input": user_input},
                f"Did you want me to create a Word document{_preview}? (yes / no)",
            )

        try:
            screen_task_intent = bool(shared_screen_path) and self.screen_task_mode and self._is_screen_task_intent(user_input)
            needs_screen_vision = bool(shared_screen_path) and self._needs_screen_vision(user_input, screen_task_intent=screen_task_intent)
            lightweight_ctx = self._should_use_lightweight_llm_context(user_input, screen_task_intent=screen_task_intent)
            recent = [] if lightweight_ctx else self.conversation_history[-3:]
            relevant = [] if lightweight_ctx else self._retrieve_relevant_memory(user_input, limit=5)
            relevant_facts = [] if lightweight_ctx else self._retrieve_relevant_facts(user_input, limit=6)
            hermes_learning_context = "" if lightweight_ctx else self._build_hermes_learning_context(user_input)
            recap_context = "" if lightweight_ctx else self._build_session_recap_context(user_input, limit=2)
            trajectory_context = "" if lightweight_ctx else self._build_trajectory_context(user_input, limit=2)
            include_live_state = self._should_include_live_state_context(user_input)
            if lightweight_ctx:
                include_live_state = False
            live_web_context = ""
            if self.live_web_prefetch_enabled and self._needs_live_web_research(user_input):
                live_web_context = self._build_live_web_context(user_input, limit=2)
            memory_context = []
            if relevant:
                memory_context.append("Relevant memory:\n" + self._format_memory_context(relevant)[:1800])
            
            # ALWAYS include recent conversation history - use mode-specific history
            _active_history = self.task_conversation_history if _input_mode == "task" else self.conversation_history
            recent = _active_history[-5:] if not lightweight_ctx else []
            
            facts_context = self._format_facts_context(relevant_facts)
            profile_prompt = self._build_profile_prompt()
            messages = [
                {
                    "role": "system",
                    "content": (
                            f"You are Opuntia, a smart Windows desktop AI assistant created by the Opuntia Team.\n"
                        f"Current date and time: {datetime.now().strftime('%A, %B %d, %Y at %H:%M:%S')}.\n"
                        + (
                            "## Active mode: TASK\n"
                            "The user is in Task mode. Focus exclusively on executing desktop tasks: "
                            "opening/closing apps, creating files/folders/documents, automation, screen control. "
                            "Do NOT give long conversational answers â€” confirm the task was done or ask only what is needed to do it.\n\n"
                            if _input_mode == "task" else
                            "## Active mode: CHAT\n"
                            "The user is in Chat mode. Focus on conversation, answering questions, web search, and general knowledge. "
                            "Do not initiate file system changes unless explicitly asked.\n\n"
                        )
                        + "## IDENTITY â€” read this first\n"
                        "**YOU ARE OPUNTIA** â€” an intelligent Windows desktop AI agent engineered by the Opuntia Team. "
                        "Opuntia is purpose-built to operate on Windows: automating workflows, controlling the PC, searching the web in real time, generating professional documents, and reasoning over complex tasks. "
                        "Whenever you introduce yourself or someone asks who you are, present yourself with confidence and precision as a professional Windows desktop AI agent.\n\n"
                        "## What you can do\n"
                        "Opuntia's core capabilities:\n"
                        "- **Desktop automation**: launch and close applications, simulate clicks, keystrokes, and keyboard shortcuts, control windows\n"
                        "- **App & process management**: list running processes, switch focus between windows, terminate applications\n"
                        "- **Real-time web search**: retrieve live news, current prices, scores, and up-to-date information from the internet\n"
                        "- **URL browsing**: open any URL, read and summarize web page content, answer questions about pages\n"
                        "- **Weather**: retrieve current conditions and multi-day forecasts for any location worldwide\n"
                        "- **File & folder management**: create, read, move, copy, rename, and delete files and folders; browse directory trees\n"
                        "- **Screen capture & vision**: take screenshots, visually analyze on-screen content, and answer questions about what is displayed\n"
                        "- **Voice input**: transcribe microphone speech in real time (English, French, Arabic)\n"
                        "- **Document generation**: produce professional PDF, Word, Excel, and PowerPoint files with structured layouts\n"
                        "- **Data & analytics**: load CSV/Excel files, compute statistics, generate charts (bar, line, pie, scatter, heatmap), export formatted Excel reports\n"
                        "- **Memory & learning**: retain facts across conversations and recall them in future sessions\n"
                        "- **Skills system**: modular, extensible automation skills that can be added and customized\n"
                        "- **System controls**: adjust volume and brightness, toggle WiFi and Bluetooth, lock or sleep the PC\n"
                        "- **Calculator & conversions**: perform math, unit conversions, and date/time calculations\n"
                        "- **Advanced AI reasoning**: powered by state-of-the-art language models for nuanced understanding and generation\n\n"
                        "When asked about your own features, capabilities, or what you can do -- answer from the description above. Do NOT search the internet for information about yourself.\n\n"
                        "When COMPARING yourself to another AI tool (ChatGPT, Claude, Gemini, Copilot, etc.): "
                        "1) Describe YOURSELF accurately as a Windows desktop AI agent using the capabilities list above. "
                        "2) For the OTHER tool â€” if web search results are in context, use them. If not, describe what you know from training data and be honest if your knowledge is limited. "
                        "3) NEVER describe Opuntia as a 'general-purpose chatbot' or 'conversational AI' â€” you are a Windows desktop automation agent. "
                        "4) NEVER invent or hallucinate facts about ANY AI product. "
                        "5) Use a Markdown comparison table to structure the differences.\n\n"
                        "## How you access knowledge (two-mode system)\n"
                        "**Mode 1 Ã¢Â€Â” Training data (built-in knowledge):** You were trained on a large text dataset with a knowledge cutoff of August 2025. "
                        "Use this for timeless facts, stable concepts, history, science, math, definitions, and anything unlikely to have changed.\n"
                        "**Mode 2 Ã¢Â€Â” Live web search:** When the context contains web search results (marked as live data), use those results as your primary source. "
                        "You have real search tools that retrieve current information Ã¢Â€Â” news, prices, scores, who currently holds a position, recent events.\n\n"
                        "## Answering rules\n"
                        "1. If live web results are in the context: answer from those results, cite sources [1][2] etc.\n"
                        "2. **Unknown person, place, or entity in your training data ? do NOT ask for more context. The internet search has already been performed Ã¢Â€Â” use those results to answer directly.**\n"
                        "3. **Even when you know something from training data ? combine it with live web results to verify and give a more complete, current answer.**\n"
                        "4. NEVER say 'I don't have information about X' Ã¢Â€Â” live search results are provided in context, use them.\n"
                        "5. NEVER say you cannot browse the internet Ã¢Â€Â” you have live search capability.\n"
                        "6. NEVER say 'shutting down' or 'goodbye' unless the user explicitly says 'close yourself' or 'exit app'.\n"
                        "7. **Structure your answer**: direct answer first -> supporting details -> sources. Use ## headings for multi-section answers, bullet points for 3+ items. "
                        "**MANDATORY: When comparing 2 or more things (tools, products, concepts, people), you MUST use a Markdown table** â€” format: | Feature | Item1 | Item2 | with a header row, a separator row (|---|---|---|), and data rows. NEVER use bullet points for comparisons â€” ALWAYS use a table.\n"
                        "8. **Adapt depth to the question**: simple query = 1-3 sentence answer; technical/complex query = full structured breakdown with sections and examples.\n"
                        "9. **Bold** key facts, names, numbers. No filler phrases like 'Great question!', 'Certainly!', 'Based on the information provided'.\n"
                        "10. For age/date calculations, use the current date shown above.\n"
                        "11. FOLLOW-UP RESOLUTION â€” CRITICAL: Short queries with words like 'numbers', 'data', 'statistics', 'more', 'details', 'examples', 'specific', 'exact', 'info', 'update', 'latest' are ALWAYS follow-ups about the LAST topic discussed â€” never treat them as new standalone questions. Example: after discussing 'Claude AI vs ChatGPT users', 'give me numbers data of 2026' = 'give me the 2026 user numbers about Claude AI vs ChatGPT'. NEVER respond with generic date/time data just because a year number appears in a follow-up. Check CONVERSATION HISTORY above for the active topic.\n"
                        "12. NEVER write '[Searching...]', 'Let me check the web', 'Let me search for you', 'I'll look that up' in your answer. The search is already done â€” just give the result.\n"
                    ),
                }
            ]
            
            # CRITICAL: Add conversation history as a separate system message BEFORE the main instructions
            if recent and len(recent) > 0:
                recent_context = "=== CONVERSATION HISTORY (Read this carefully) ===\n"
                recent_context += self._format_memory_context(recent)
                recent_context += "\n=== END CONVERSATION HISTORY ===\n"
                recent_context += "IMPORTANT: The conversation history above contains the context for the current conversation. "
                recent_context += "When the user says 'he', 'she', 'it', 'they', 'him', 'her', 'their', or asks follow-up questions, "
                recent_context += "you MUST refer to the conversation history to understand what they're talking about. "
                recent_context += "DO NOT say 'I don't know who he is' - look at the conversation history above!"
                messages.insert(0, {"role": "system", "content": recent_context})
            
            # Add remaining memory context if exists
            if memory_context:
                messages.append({"role": "system", "content": "\n\n".join(memory_context)[:2200]})
            brevity_cue = bool(re.search(
                r'\b(just\s+a\s+few\s+words?|briefly|in\s+short|keep\s+it\s+short|short\s+answer|'
                r'quick\s+answer|tldr|summarize|summary|in\s+brief|be\s+brief|concise)\b',
                user_input, re.IGNORECASE
            ))
            if shared_screen_path:
                live_screen_rules = (
                    "LIVE SCREEN MODE is active. You can see the user's screen in real time via the LIVE SCREEN context above.\n"
                    "Respond like a smart assistant on a screen-share call:\n"
                    "- Use sections with emoji headers: ??? Active App, ?? Layout & Activity, ?? Insights Ã¢Â€Â” ONLY when the user explicitly asks you to describe or explain what you see.\n"
                    "- For all other questions, answer the question directly. Reference the screen only if it's relevant.\n"
                    "- Do NOT re-describe the screen when the user asks a content question (e.g. 'explain this code', 'what are the limitations').\n"
                    "- Mention errors, warnings, or notable things visible on screen only when relevant.\n"
                    "- Suggest helpful next steps when appropriate.\n"
                    "- Do NOT say 'I cannot see your screen' Ã¢Â€Â” you CAN see it."
                )
                if brevity_cue:
                    live_screen_rules += (
                        "\n- IMPORTANT: The user asked for a SHORT answer. "
                        "Do NOT describe the screen. Give a direct, concise answer in 1-3 sentences maximum."
                    )
                messages.append({"role": "system", "content": live_screen_rules})
            if screen_task_intent:
                messages.append({"role": "system", "content": self._screen_task_prompt()})
            if include_live_state:
                running_now = self.get_running_apps()
                if running_now:
                    messages.append(
                        {
                            "role": "system",
                            "content": "Currently running apps snapshot: " + ", ".join(running_now[:20]),
                        }
                    )
                desktop_items = self._desktop_items_snapshot(limit=30)
                if desktop_items:
                    messages.append(
                        {
                            "role": "system",
                            "content": "Desktop items snapshot: " + ", ".join(desktop_items),
                        }
                    )
            if shared_screen_path:
                # In live mode, always analyze the screen Ã¢Â€Â” AI sees everything like a human
                screen_context = self._describe_screen_snapshot(shared_screen_path, user_input)
                if screen_context:
                    # Step 4: PII redaction -- scrub element-level PII before sending to LLM
                    if (scan_elements_for_pii is not None and redact_text is not None
                            and self._last_elements is not None):
                        try:
                            _pii_matches = scan_elements_for_pii(self._last_elements.elements)
                            if _pii_matches:
                                screen_context = redact_text(screen_context, _pii_matches)
                        except Exception:
                            pass
                    label = "LIVE SCREEN Ã¢Â€Â” what is currently on the user's screen:\n" if not screen_task_intent else "LIVE SCREEN (task execution context):\n"
                    messages.append(
                        {
                            "role": "system",
                            "content": label + screen_context[:4500],
                        }
                    )
                    # Step 5: Structured element context -- give LLM element IDs for precise targeting
                    if self._last_elements is not None:
                        try:
                            _elem_lines = []
                            for _el in self._last_elements.elements[:40]:
                                _act_str = ",".join(_el.actions) if _el.actions else ""
                                _elem_lines.append(
                                    f"  [{_el.id}] {_el.control_type} \"{_el.label}\" actions=[{_act_str}]"
                                )
                            if _elem_lines:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "STRUCTURED UI ELEMENTS -- reference these IDs for precise actions "
                                        "(e.g. smart_click('btn_save') instead of raw coordinates):\n"
                                        + "\n".join(_elem_lines)
                                    ),
                                })
                        except Exception:
                            pass
            if live_web_context:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            live_web_context
                            + "\nWhen using these results, cite URLs in your answer."
                        )[:3600],
                    }
                )
            if profile_prompt:
                messages.append({"role": "system", "content": profile_prompt})
            if facts_context:
                messages.append({"role": "system", "content": facts_context[:900]})
            if hermes_learning_context:
                messages.append({"role": "system", "content": hermes_learning_context[:900]})
            if recap_context:
                messages.append({"role": "system", "content": recap_context[:900]})
            if trajectory_context:
                messages.append({"role": "system", "content": trajectory_context[:1000]})
            skills_context = "" if lightweight_ctx else self._enabled_skills_prompt_for_query(user_input)
            if skills_context:
                messages.append({"role": "system", "content": skills_context})
            few_shot = [] if lightweight_ctx else self._retrieve_prompt_examples(user_input, limit=1)
            for ex in few_shot:
                messages.append({"role": "user", "content": ex["user"]})
                messages.append({"role": "assistant", "content": ex["assistant"]})
            # â”€â”€ Follow-up context injection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # When the user sends a short metric/data follow-up ("give me numbers
            # data of 2026"), the LLM can misinterpret it as a standalone question.
            # Inject an explicit hint so it understands this continues the last topic.
            _followup_hint = self._get_followup_context(user_input)
            if _followup_hint:
                messages.append({"role": "system", "content": _followup_hint})
            _anchor_hint = self._topic_anchor_hint(user_input)
            if _anchor_hint:
                messages.append({"role": "system", "content": _anchor_hint})
            # Add the actual user message last so the AI knows what to respond to
            messages.append({"role": "user", "content": user_input})
            # === INTELLIGENT ROUTING: Internal Knowledge vs Internet Search ===
            # Pass the full pre-built context messages so history/facts/screen are used
            # For follow-up queries, also expand the routing query with context so that
            # web search doesn't search for a bare "numbers data 2026" without topic.
            _routed_input = self._expand_query_with_context(user_input) if _followup_hint else user_input
            answer = self.intelligent_respond(_routed_input, messages=messages, has_live_screen=bool(shared_screen_path))
            
            if screen_task_intent and self.screen_task_json_mode:
                self.last_screen_action_plan = self._extract_json_block(answer)
                # Auto-start execution when live screen is active and plan has actions
                if (shared_screen_path and self.last_screen_action_plan
                        and isinstance(self.last_screen_action_plan, dict)
                        and self.last_screen_action_plan.get("actions")):
                    exec_prompt = self._start_plan_execution()
                    answer = answer.rstrip() + "\n\n" + exec_prompt
            elif not screen_task_intent:
                self.last_screen_action_plan = None

            # â”€â”€ Uncertainty retry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # If the AI answered with hedged/unknown phrases AND this was NOT
            # already a web-search path, automatically retry with a live search.
            _uncertainty_phrases = [
                "not a well-known", "not widely recognized", "without specific information",
                "without clear information", "cannot be directly compared",
                "further research", "no information about", "limited information",
                "not enough information", "doesn't exist", "does not exist",
                "no record of", "cannot find", "i don't have", "i do not have",
                "unknown entity", "not familiar with",
                "existence and development status are unclear",
                "i'm not familiar", "i am not familiar", "not sure about",
                "no data available", "couldn't find", "could not find",
                "may not exist", "unclear what", "without further information",
            ]
            _ans_lower = answer.lower()
            _is_info_query = bool(re.search(
                r'\b(difference|compare|comparison|what is|who is|tell me about|'
                r'explain|about|vs\.?|versus|between)\b',
                cmd_lower
            ))
            if _is_info_query and any(ph in _ans_lower for ph in _uncertainty_phrases):
                try:
                    _web_retry = self.advanced_internet_search(user_input, auto_synthesize=True)
                    if _web_retry and len(_web_retry.strip()) > 80:
                        answer = _web_retry
                except Exception:
                    pass

            self._capture_turn(user_input, answer, remember=True)
            return answer
        except Exception as e:
            return f"Error: {str(e)}"
