"""
Base tool interface for agent tools.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from langchain_core.tools import BaseTool


class AgentTool(ABC):
    """
    Abstract base class for agent tools.
    Wraps LangChain BaseTool with additional agent-specific functionality.
    """
    
    @abstractmethod
    def get_tool(self) -> BaseTool:
        """
        Get LangChain tool instance.
        
        Returns:
            BaseTool instance
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        pass
    
    @property
    def requires_approval(self) -> bool:
        """
        Whether this tool requires human approval before execution.
        Override to return True for tools that need human-in-the-loop.
        
        Returns:
            True if tool requires approval, False otherwise (default: False)
        """
        return False
    
    def execute(self, **kwargs) -> Any:
        """
        Execute tool with given arguments.
        
        Args:
            **kwargs: Tool arguments
            
        Returns:
            Tool execution result
        """
        tool = self.get_tool()
        return tool.invoke(kwargs)
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get tool metadata.
        Override to provide additional metadata.
        """
        return {
            'name': self.name,
            'description': self.description,
        }
