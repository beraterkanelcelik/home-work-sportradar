"""
Event callback handler for streaming LLM tokens and task events.

Used by the StateGraph workflow to stream tokens and status updates to the frontend.
"""
from typing import Dict, Any, Optional
from queue import Queue, Full as QueueFull
from langchain_core.callbacks import BaseCallbackHandler
from app.core.logging import get_logger

logger = get_logger(__name__)


class EventCallbackHandler(BaseCallbackHandler):
    """
    Callback handler that captures LLM tokens and task events,
    writing them to a thread-safe queue for consumption by the workflow.
    """

    def __init__(self, event_queue: Queue, status_messages: Optional[Dict[str, str]] = None):
        """
        Initialize the callback handler.

        Args:
            event_queue: Thread-safe queue to write events to
            status_messages: Optional mapping of node/task names to status messages
        """
        super().__init__()
        self.event_queue = event_queue
        self.status_messages = status_messages or {}
        self.active_tasks = {}

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Capture LLM token chunks for streaming."""
        if token:
            try:
                self.event_queue.put_nowait({
                    "type": "token",
                    "value": token
                })
            except QueueFull:
                logger.debug("Event queue full, dropping token")
            except Exception as e:
                logger.error(f"[TOKEN_CALLBACK] Error queuing token: {e}", exc_info=True)

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs) -> None:
        """Capture chain/task start events for status updates."""
        try:
            # Extract chain name from various sources
            chain_name = ""
            name_from_kwargs = kwargs.get("name", "")

            if serialized and isinstance(serialized, dict):
                chain_name = serialized.get("name", "")
                if not chain_name:
                    chain_id = serialized.get("id")
                    if isinstance(chain_id, list) and chain_id:
                        chain_name = chain_id[-1]
                    elif isinstance(chain_id, str):
                        chain_name = chain_id

            if not chain_name and name_from_kwargs:
                chain_name = name_from_kwargs

            run_name = kwargs.get("run_name", "")
            effective_name = run_name or chain_name or ""

            # Check if this matches a known status message
            task_name = None
            for known_task in self.status_messages.keys():
                if known_task.lower() in effective_name.lower() or effective_name.lower() in known_task.lower():
                    task_name = known_task
                    break

            # Send status update if task identified
            if task_name and task_name in self.status_messages:
                status = self.status_messages[task_name]

                if task_name not in self.active_tasks:
                    self.active_tasks[task_name] = {"status": status}
                    try:
                        self.event_queue.put_nowait({
                            "type": "update",
                            "data": {"status": status, "task": task_name}
                        })
                    except QueueFull:
                        logger.debug("Event queue full, dropping status update")
                    except Exception as e:
                        logger.debug(f"Error queuing status update: {e}")
        except Exception as e:
            logger.error(f"Error in on_chain_start: {e}", exc_info=True)

    def on_chain_end(self, outputs: Any, **kwargs) -> None:
        """Track chain end for status updates."""
        pass  # Status completion handled implicitly when next task starts

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Capture tool execution start."""
        try:
            if serialized is None:
                return
            tool_name = serialized.get("name", "") if isinstance(serialized, dict) else ""
            if tool_name:
                try:
                    self.event_queue.put_nowait({
                        "type": "update",
                        "data": {"status": f"Executing {tool_name}...", "tool": tool_name}
                    })
                except QueueFull:
                    logger.debug("Event queue full, dropping tool start update")
                except Exception as e:
                    logger.debug(f"Error queuing tool start: {e}")
        except Exception as e:
            logger.error(f"Error in on_tool_start: {e}", exc_info=True)

    def on_tool_end(self, output: Any, **kwargs) -> None:
        """Tool execution completed."""
        try:
            tool_name = None
            if isinstance(kwargs.get("name"), str):
                tool_name = kwargs["name"]
            elif isinstance(kwargs.get("serialized"), dict):
                tool_name = kwargs["serialized"].get("name", "")

            if tool_name:
                try:
                    self.event_queue.put_nowait({
                        "type": "update",
                        "data": {"status": f"Executed {tool_name}", "tool": tool_name}
                    })
                except QueueFull:
                    logger.debug("Event queue full, dropping tool end update")
                except Exception as e:
                    logger.debug(f"Error queuing tool end: {e}")
        except Exception as e:
            logger.error(f"Error in on_tool_end: {e}", exc_info=True)
