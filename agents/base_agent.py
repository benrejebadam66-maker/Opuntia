"""
OPUNTIA Multi-Agent Architecture
Base Agent Class - Defines the common interface for all specialized agents.
"""

import os
import json
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime


class AgentCapability:
    """Represents a single capability of an agent."""
    
    def __init__(self, name: str, description: str, keywords: List[str]):
        self.name = name
        self.description = description
        self.keywords = keywords  # Keywords that trigger this capability


class BaseAgent(ABC):
    """
    Abstract base class for all OPUNTIA agents.
    
    Each specialized agent must implement:
    - can_handle(): Check if this agent can handle a given intent
    - execute(): Execute the command and return result
    - get_capabilities(): Return list of what this agent can do
    """
    
    # Class-level configuration
    name: str = "BaseAgent"
    description: str = "Base agent class"
    version: str = "1.0.0"
    
    # Permissions required by this agent
    permissions: List[str] = []
    
    # AI model configuration (can be overridden per agent)
    ai_model: str = "default"
    ai_temperature: float = 0.5
    ai_max_tokens: int = 1024
    
    def __init__(self, shared_context: Optional[Dict] = None, config: Optional[Dict] = None):
        """
        Initialize the agent.
        
        Args:
            shared_context: Shared memory/context accessible by all agents
            config: Agent-specific configuration
        """
        self.shared_context = shared_context or {}
        self.config = config or {}
        self._initialized = False
        self._last_error: Optional[str] = None
        self._execution_count = 0
        self._created_at = datetime.now()
        
        # Agent-specific memory (isolated from other agents)
        self.memory: Dict[str, Any] = {}
        
        # Initialize the agent
        try:
            self._initialize()
            self._initialized = True
        except Exception as e:
            self._last_error = f"Initialization failed: {e}"
            self._initialized = False
    
    @abstractmethod
    def can_handle(self, intent: str) -> Tuple[float, str]:
        """
        Check if this agent can handle the given intent/command.
        
        Args:
            intent: The user's command or intent
            
        Returns:
            Tuple of (confidence_score, matched_capability_name)
            confidence_score: 0.0 to 1.0 (1.0 = perfect match)
            matched_capability_name: Name of the capability that matched
        """
        pass
    
    @abstractmethod
    def execute(self, command: str, context: Optional[Dict] = None) -> str:
        """
        Execute the given command.
        
        Args:
            command: The command to execute
            context: Additional context for execution
            
        Returns:
            Result message (can be formatted with markdown)
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[AgentCapability]:
        """
        Return list of capabilities this agent provides.
        
        Returns:
            List of AgentCapability objects
        """
        pass
    
    def _initialize(self):
        """
        Initialize agent-specific resources.
        Override this method in subclasses for setup logic.
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current agent status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "name": self.name,
            "version": self.version,
            "initialized": self._initialized,
            "execution_count": self._execution_count,
            "last_error": self._last_error,
            "created_at": self._created_at.isoformat(),
            "memory_size": len(self.memory),
        }
    
    def reset(self):
        """Reset agent state (clear memory, errors, counters)."""
        self.memory.clear()
        self._last_error = None
        self._execution_count = 0
    
    def _log_execution(self, command: str, result: str, success: bool):
        """Log execution for debugging and learning."""
        self._execution_count += 1
        if not success:
            self._last_error = result
        
        # Store in agent memory for learning
        if "executions" not in self.memory:
            self.memory["executions"] = []
        
        self.memory["executions"].append({
            "timestamp": datetime.now().isoformat(),
            "command": command[:500],  # Truncate long commands
            "result": result[:1000],
            "success": success,
        })
        
        # Keep only last 100 executions
        if len(self.memory["executions"]) > 100:
            self.memory["executions"] = self.memory["executions"][-100:]
    
    def _get_shared_memory(self, key: str, default: Any = None) -> Any:
        """Get value from shared context."""
        return self.shared_context.get(key, default)
    
    def _set_shared_memory(self, key: str, value: Any):
        """Set value in shared context."""
        self.shared_context[key] = value
    
    def _call_ai(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Call AI model for inference.
        
        This uses the shared AI client from the orchestrator.
        Override if agent needs custom AI handling.
        """
        # Delegate to orchestrator's AI client
        ai_client = self.shared_context.get("ai_client")
        if ai_client is None:
            return "AI client not available"
        
        try:
            response = ai_client.chat.completions.create(
                model=model or self.ai_model,
                messages=messages,
                temperature=temperature or self.ai_temperature,
                max_tokens=max_tokens or self.ai_max_tokens,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI call failed: {e}"
    
    def _match_keywords(self, text: str, keywords: List[str]) -> float:
        """
        Calculate match score between text and keywords.
        
        Returns:
            Score from 0.0 to 1.0
        """
        text_lower = text.lower()
        if not keywords:
            return 0.0
        
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        return min(1.0, matches / len(keywords))
    
    def _has_permission(self, permission: str) -> bool:
        """Check if agent has a specific permission."""
        return permission in self.permissions
    
    def __repr__(self) -> str:
        return f"<{self.name} v{self.version} initialized={self._initialized}>"
