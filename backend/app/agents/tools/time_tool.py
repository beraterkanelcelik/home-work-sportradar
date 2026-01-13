"""
Current time tool for agents.
Requires human approval before execution (human-in-the-loop).
"""
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool, BaseTool
from app.agents.tools.base import AgentTool


class TimeTool(AgentTool):
    """
    Tool that returns the current time.
    Requires human approval before execution.
    """
    
    @property
    def name(self) -> str:
        """Tool name."""
        return "get_current_time"
    
    @property
    def description(self) -> str:
        """Tool description."""
        return "Get the current date and time. This tool requires human approval before execution."
    
    @property
    def requires_approval(self) -> bool:
        """Whether this tool requires human approval."""
        return True
    
    def get_tool(self) -> BaseTool:
        """Get LangChain tool instance."""
        @tool
        def get_current_time(timezone: Optional[str] = None) -> str:
            """
            Get the current date and time.
            
            This tool requires human approval before execution.
            
            Args:
                timezone: Optional timezone (e.g., 'UTC', 'America/New_York').
                         If not provided, uses system local time.
            
            Returns:
                Current date and time as a formatted string.
            """
            now = datetime.now()
            
            if timezone:
                try:
                    import pytz
                    tz = pytz.timezone(timezone)
                    now = datetime.now(tz)
                    return now.strftime("%Y-%m-%d %H:%M:%S %Z")
                except Exception:
                    # If timezone is invalid, use local time
                    pass
            
            return now.strftime("%Y-%m-%d %H:%M:%S")
        
        return get_current_time
    
    def get_metadata(self) -> dict:
        """Get tool metadata including approval requirement."""
        metadata = super().get_metadata()
        metadata['requires_approval'] = self.requires_approval
        return metadata
