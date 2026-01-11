# LangGraph Functional API - Lessons Learned

This document captures key learnings, pitfalls, and best practices from implementing the LangGraph Functional API architecture. Use this as a reference when building similar systems from scratch.

## Table of Contents

1. [Streaming Architecture](#streaming-architecture)
2. [State Extraction from Stream](#state-extraction-from-stream)
3. [Tool Call ID Management](#tool-call-id-management)
4. [Status Messages (Ephemeral UI State)](#status-messages-ephemeral-ui-state)
5. [Tool Items Visibility](#tool-items-visibility)
6. [Callback Handler Patterns](#callback-handler-patterns)
7. [Supervisor Token Filtering](#supervisor-token-filtering)
8. [Django Auto-Reload Compatibility](#django-auto-reload-compatibility)
9. [JSON Serialization](#json-serialization)
10. [Frontend State Management](#frontend-state-management)
11. [Common Pitfalls to Avoid](#common-pitfalls-to-avoid)
12. [Best Practices](#best-practices)
13. [Architecture Decisions](#architecture-decisions)

---

## Streaming Architecture

### Problem: `astream_events()` Doesn't Work with Sync Checkpointers

**Issue**: LangGraph's `astream_events()` method requires async checkpoint methods (`aget_tuple`), but `PostgresSaver` (the checkpointer) only implements synchronous methods.

**Error Encountered**:
```
NotImplementedError: PostgresSaver does not implement aget_tuple
```

**Solution**: Use `stream()` method with custom `BaseCallbackHandler` for token streaming.

**Implementation Pattern**:
```python
from langchain_core.callbacks import BaseCallbackHandler

class StreamingCallbackHandler(BaseCallbackHandler):
    def __init__(self, event_queue, content_accumulator, tokens_accumulator, status_messages, session_id=None):
        super().__init__()
        self.event_queue = event_queue
        self.content_accumulator = content_accumulator
        self.tokens_accumulator = tokens_accumulator
        self.status_messages = status_messages
        self.session_id = session_id  # None for ephemeral status messages
        self.active_tasks = {}
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Capture LLM token chunks."""
        if token:
            self.content_accumulator[0] += token
            self.event_queue.put({"type": "token", "data": token})
    
    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs) -> None:
        """Capture chain/task start events."""
        # Extract task name from kwargs or serialized
        # Send status update via event_queue
        pass
    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Send tool execution status update."""
        pass

# Usage
config['callbacks'] = [streaming_callback]
for chunk in ai_agent_workflow.stream(request, config=config):
    # Process chunks
    pass
```

**Key Points**:
- `stream()` works with sync checkpointers
- Use `BaseCallbackHandler` to capture LLM tokens via `on_llm_new_token`
- Use `on_chain_start` and `on_tool_start` for status updates
- Run stream in background thread if needed (for Django compatibility)

---

## State Extraction from Stream

### Problem: Stream Returns State Dicts, Not AgentResponse Objects

**Issue**: LangGraph Functional API `stream()` method returns state dictionaries, not the final `AgentResponse` object directly.

**What We Expected**:
```python
for chunk in ai_agent_workflow.stream(request, config=config):
    # chunk is AgentResponse
    tool_calls = chunk.tool_calls
```

**Reality**:
```python
for chunk in ai_agent_workflow.stream(request, config=config):
    # chunk is dict like {'ai_agent_workflow': AgentResponse(...)}
    # Need to extract from state
```

**Solution**: Extract response from state dictionary using workflow name as key.

**Implementation**:
```python
final_state = None
for chunk in ai_agent_workflow.stream(request, config=config):
    final_state = chunk  # Capture final state

# Extract AgentResponse from final state
if final_state and isinstance(final_state, dict):
    # Check if state has the workflow name as a key (LangGraph pattern)
    if 'ai_agent_workflow' in final_state:
        response_data = final_state['ai_agent_workflow']
    elif 'response' in final_state:
        response_data = final_state['response']
    elif 'result' in final_state:
        response_data = final_state['result']
    else:
        # State might be the response itself
        if any(key in final_state for key in ['agent_name', 'reply', 'tool_calls', 'type']):
            response_data = final_state
    
    # Extract fields
    if isinstance(response_data, dict):
        agent_name = response_data.get('agent_name')
        tool_calls = response_data.get('tool_calls')
    elif isinstance(response_data, AgentResponse):
        agent_name = response_data.agent_name
        tool_calls = response_data.tool_calls
```

**Key Points**:
- Always check for workflow name key first (e.g., `'ai_agent_workflow'`)
- Fallback to common keys: `'response'`, `'result'`, `'output'`
- Handle both dict and `AgentResponse` object formats
- Extract `agent_name` and `tool_calls` for frontend updates

---

## Tool Call ID Management

### Problem: Duplicate Tool Call IDs

**Issue**: When the same tool is called multiple times with the same arguments, hash-based ID generation can create duplicate IDs, causing OpenAI API errors.

**Error Encountered**:
```
openai.BadRequestError: Invalid parameter: Duplicate value for 'tool_call_id'
```

**Solution**: Generate truly unique IDs using UUID, and match tool calls by both name and arguments.

**Implementation**:
```python
import uuid

# Generate unique IDs for tool calls
seen_tool_call_signatures = {}  # Track (tool_name, args_hash) -> tool_call_id

for tc in response.tool_calls:
    tool_call_id = tc.get("id")
    tool_name = tc.get("name") or tc.get("tool", "")
    tool_args = tc.get("args", {})
    
    if not tool_call_id:
        # Create signature for this tool call
        args_str = str(sorted(tool_args.items())) if isinstance(tool_args, dict) else str(tool_args)
        signature = (tool_name, hash(args_str))
        
        # Check if we've seen this exact tool call before
        if signature in seen_tool_call_signatures:
            # Reuse the ID for the same tool call
            tool_call_id = seen_tool_call_signatures[signature]
        else:
            # Generate unique ID for this tool call
            tool_call_id = f"call_{uuid.uuid4().hex[:16]}"
            seen_tool_call_signatures[signature] = tool_call_id
        
        tc['id'] = tool_call_id

# When matching ToolResult to AIMessage tool calls:
for tr in tool_results:
    tool_call_id = None
    for tc in ai_message_with_tool_calls.tool_calls:
        tc_name = tc.get("name") or tc.get("tool", "")
        tc_args = tc.get("args", {})
        # Match by both tool name AND args to handle multiple calls of same tool
        if tc_name == tr.tool and tc_args == tr.args:
            tool_call_id = tc.get("id")
            break
```

**Key Points**:
- Use `uuid.uuid4().hex[:16]` for unique IDs
- Match tool calls by both `tool_name` and `args` (not just name)
- Track seen signatures to reuse IDs for identical calls
- Ensure IDs are unique even when same tool called multiple times

---

## Status Messages (Ephemeral UI State)

### Problem: Status Messages Should Not Be Persisted

**Issue**: Initially, we tried to persist status messages (e.g., "Processing with agent...", "Executing tools...") to the database. This caused:
- Database bloat with ephemeral data
- Reload issues (old status messages appearing)
- Real-time update conflicts

**Solution**: Treat status messages as ephemeral UI feedback, not historical data.

**Implementation**:
```python
# Backend: Don't persist status messages
# In StreamingCallbackHandler:
self.session_id = None  # Explicitly signal no DB persistence

def on_chain_start(self, serialized, inputs, **kwargs):
    # Track task as active (no DB persistence)
    if task_name not in self.active_tasks:
        self.active_tasks[task_name] = {"status": status}
    
    # Send as real-time event only
    self.event_queue.put({
        "type": "update",
        "data": {"status": status, "task": task_name}
    })

def on_chain_end(self, outputs, **kwargs):
    # Send update event with past tense (no DB persistence)
    self.event_queue.put({
        "type": "update",
        "data": {
            "status": past_status,
            "task": task_name,
            "is_completed": True
        }
    })
    # Remove from active tasks
    del self.active_tasks[task_name]
```

```typescript
// Frontend: Use temporary negative IDs for status messages
const tempId = -(Date.now() + Math.random() * 1000)
const newStatusMessage: Message = {
  id: tempId, // Temporary negative ID
  role: 'system',
  content: updateData.status,
  metadata: {
    task: updateData.task,
    status_type: 'task_status',
    is_completed: updateData.is_completed === true || false
  }
}

// Clear temporary status messages when starting new stream
set((state: { messages: Message[] }) => ({
  messages: state.messages.filter(
    (msg: Message) => !(msg.id < 0 && msg.role === 'system' && msg.metadata?.status_type === 'task_status')
  )
}))
```

**Key Points**:
- Status messages are ephemeral UI feedback, not historical data
- Use temporary negative IDs for real-time status messages
- Clear them when switching sessions or starting new streams
- Don't reload messages after streaming (causes flicker and overwrites)

---

## Tool Items Visibility

### Problem: Tool Items Appearing Too Early

**Issue**: Tool items (collapsible boxes with query info, args, etc.) were appearing during streaming, but they should only appear after the stream completes.

**Solution**: Use `streamComplete` flag to control visibility.

**Implementation**:
```typescript
// Track which messages have completed streaming
const [streamComplete, setStreamComplete] = useState<Set<number>>(new Set())

// Mark stream as complete when done event arrives
if (event.type === 'done') {
  if (assistantMessageId) {
    setStreamComplete(prev => new Set(prev).add(assistantMessageId))
  }
}

// Only show tool items after stream completes
{msg.role === 'assistant' && 
 msg.metadata?.tool_calls && 
 Array.isArray(msg.metadata.tool_calls) && 
 msg.metadata.tool_calls.length > 0 && 
 streamComplete.has(msg.id) && (
  // Render tool items
)}
```

**Key Points**:
- Tool_calls come via stream update event (not database fetch)
- Use `streamComplete` flag to control when tool items appear
- Tool status updates (Executing -> Executed) show during streaming
- Tool items (collapsible boxes) only appear after stream completes

---

## Callback Handler Patterns

### Problem: `on_chain_start` Receives `serialized=None` for Functional API Tasks

**Issue**: For LangGraph Functional API tasks, `on_chain_start` callback receives `serialized=None`, making it impossible to extract task names.

**Solution**: Extract task name from `kwargs.get("name")` as fallback.

**Implementation**:
```python
def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs) -> None:
    """Capture chain/task start events."""
    try:
        # For LangGraph Functional API, serialized can be None
        # Task name is often in kwargs['name'] instead
        chain_name = ""
        
        # Try to get name from kwargs first (LangGraph Functional API pattern)
        name_from_kwargs = kwargs.get("name", "")
        
        # Also try serialized if available
        if serialized and isinstance(serialized, dict):
            chain_name = serialized.get("name", "")
        
        # Use name from kwargs if chain_name is empty
        if not chain_name and name_from_kwargs:
            chain_name = name_from_kwargs
        
        # Extract function name, run_name, tags from kwargs
        run_name = kwargs.get("run_name", "")
        tags = kwargs.get("tags", [])
        
        # Use run_name if available, otherwise use chain_name
        effective_name = run_name or chain_name or ""
        
        # Match against known tasks
        task_name = None
        for known_task in self.status_messages.keys():
            if known_task.lower() in effective_name.lower():
                task_name = known_task
                break
```

**Key Points**:
- Always check `kwargs.get("name")` first for Functional API tasks
- Fallback to `serialized` if available
- Use `run_name` or `chain_name` as effective name
- Always check `isinstance(serialized, dict)` before accessing keys

---

## Supervisor Token Filtering

### Problem: Supervisor LLM Outputs Agent Names That Shouldn't Be Streamed

**Issue**: The supervisor LLM outputs agent names (e.g., "greeter", "search") as tokens, which were being streamed to the frontend before the actual agent response.

**Solution**: Use flags to detect supervisor context and skip those tokens.

**Implementation**:
```python
class StreamingCallbackHandler(BaseCallbackHandler):
    def __init__(self, ...):
        self.is_supervisor_llm = False
        self.supervisor_in_stack = False
        self.agent_names = {"greeter", "search", "gmail", "config", "process"}
    
    def on_chain_start(self, serialized, inputs, **kwargs):
        # Detect supervisor context early
        if effective_name and "supervisor" in effective_name.lower():
            self.supervisor_in_stack = True
            self.is_supervisor_llm = True
    
    def on_llm_start(self, serialized, prompts, **kwargs):
        # Check if we're in a supervisor task context
        is_supervisor_context = self.supervisor_in_stack
        if not is_supervisor_context:
            for chain in self.chain_stack:
                if chain and "supervisor" in str(chain).lower():
                    is_supervisor_context = True
                    self.supervisor_in_stack = True
                    break
        
        # Mark this LLM call as supervisor routing if in supervisor context
        self.is_supervisor_llm = is_supervisor_context
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Capture LLM token chunks, but skip supervisor routing tokens."""
        # Skip tokens from supervisor LLM (it just outputs agent name like "greeter")
        if self.is_supervisor_llm:
            return
        
        # Additional validation: supervisor only outputs short agent names
        token_lower = token.strip().lower()
        if len(token_lower) <= 10 and token_lower in self.agent_names:
            # Check if we're in supervisor context
            if self.supervisor_in_stack or (self.current_chain and "supervisor" in str(self.current_chain).lower()):
                return
            # Also check chain stack
            for chain in self.chain_stack:
                if chain and "supervisor" in str(chain).lower():
                    return
        
        # Stream token
        if token:
            self.content_accumulator[0] += token
            self.event_queue.put({"type": "token", "data": token})
    
    def on_llm_end(self, response, **kwargs):
        """Reset supervisor flag."""
        self.is_supervisor_llm = False
```

**Key Points**:
- Set `is_supervisor_llm` flag in `on_chain_start` when supervisor detected
- Check chain stack for supervisor context
- Skip tokens if `is_supervisor_llm` is True
- Also skip short tokens (1-10 chars) that match agent names in supervisor context
- Reset flag in `on_llm_end`

---

## Django Auto-Reload Compatibility

### Problem: Background Threads Cause RuntimeError During Django Reload

**Issue**: Django's development server auto-reloads when code changes. Background threads running streams can cause `RuntimeError` when trying to use thread executors that have been shut down.

**Error Encountered**:
```
RuntimeError: cannot schedule new futures after interpreter shutdown
```

**Solution**: Catch `RuntimeError` gracefully and exit thread cleanly.

**Implementation**:
```python
def run_stream_events():
    """Run stream_events in a separate thread."""
    def process_events():
        try:
            # Stream workflow
            for chunk in ai_agent_workflow.stream(request, config=config):
                # Process chunks
                pass
        except RuntimeError as e:
            # Handle Django auto-reload shutdown gracefully
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                logger.warning("Workflow stream interrupted by Django reload - this is expected during development")
                # Don't set exception - just exit gracefully
            else:
                logger.error(f"Error in process_events: {e}", exc_info=True)
                exception_holder[0] = e
        except Exception as e:
            logger.error(f"Error in process_events: {e}", exc_info=True)
            exception_holder[0] = e
        finally:
            # Signal completion
            event_queue.put(None)
    
    try:
        process_events()
    except Exception as e:
        logger.error(f"Error in run_stream_events: {e}", exc_info=True)
        exception_holder[0] = e
        event_queue.put(None)
```

**Key Points**:
- Use daemon threads for background stream processing
- Catch `RuntimeError` with "cannot schedule new futures" message
- Log warning but don't treat as error (expected during development)
- Exit thread cleanly without raising exceptions

---

## JSON Serialization

### Problem: Non-Serializable Data in Stream Events

**Issue**: Tool_calls and other data sent via stream events must be JSON serializable. Objects or complex types cause serialization errors.

**Solution**: Ensure all data is properly formatted as dicts/lists before sending.

**Implementation**:
```python
# Format tool_calls for frontend (ensure JSON serializable)
formatted_tool_calls = []
for tc in tool_calls:
    formatted_tc = {
        "name": tc.get("name") or tc.get("tool", ""),
        "tool": tc.get("name") or tc.get("tool", ""),
        "args": tc.get("args", {}),  # Ensure dict
        "status": tc.get("status", "completed"),
    }
    if tc.get("id"):
        formatted_tc["id"] = tc.get("id")  # Ensure string
    if tc.get("output"):
        formatted_tc["output"] = tc.get("output")  # Ensure serializable
    if tc.get("error"):
        formatted_tc["error"] = tc.get("error")  # Ensure string
    formatted_tool_calls.append(formatted_tc)

# Send via event queue
event_queue.put({
    "type": "update",
    "data": {
        "tool_calls": formatted_tool_calls,  # JSON serializable
        "agent_name": agent_name  # String
    }
})
```

**Key Points**:
- Always use `.get()` with defaults when accessing dict keys
- Ensure all values are JSON serializable (str, int, dict, list, None)
- Convert objects to dicts before sending
- Test serialization with `json.dumps()` if unsure

---

## Frontend State Management

### Problem: Temporary Messages Lost on Reload

**Issue**: Temporary status messages (with negative IDs) were being lost when messages were reloaded from the database, causing status updates to disappear.

**Solution**: Preserve temporary messages during merge, filter them out when loading from DB.

**Implementation**:
```typescript
// In loadMessages:
const existingMessages = state.messages || []
const dbMessages = uniqueMessages

// Find ALL temporary status messages (negative IDs) - preserve them during streaming
const tempStatusMessages = existingMessages.filter(
  (msg: Message) =>
    msg.id < 0 &&
    msg.role === 'system' &&
    msg.metadata?.status_type === 'task_status'
)

// Filter out any system status messages from DB (they shouldn't exist, but just in case)
const dbMessagesWithoutStatus = dbMessages.filter(
  (msg: Message) => !(msg.role === 'system' && msg.metadata?.status_type === 'task_status')
)

// Merge: add DB messages + temporary status messages
const mergedMessages = [...dbMessagesWithoutStatus, ...tempStatusMessages]

// Sort by created_at to maintain order
mergedMessages.sort((a, b) => {
  const timeA = new Date(a.created_at).getTime()
  const timeB = new Date(b.created_at).getTime()
  return timeA - timeB
})
```

**Key Points**:
- Temporary messages have negative IDs
- Preserve them during streaming (they have real-time updates)
- Filter out status messages from DB (they're ephemeral)
- Merge strategy: DB messages + active temporary messages
- Clear temporary status messages when starting new stream

---

## Common Pitfalls to Avoid

1. **Don't try to use `astream_events()` with sync checkpointers**
   - Use `stream()` with `BaseCallbackHandler` instead

2. **Don't persist ephemeral UI state (status messages) to database**
   - They're temporary feedback, not historical data

3. **Don't reload messages after streaming**
   - Causes flicker and overwrites real-time updates
   - All data comes from stream

4. **Don't assume `stream()` returns `AgentResponse`**
   - It returns state dicts - extract from `final_state['ai_agent_workflow']`

5. **Don't forget to extract tool_calls from state after stream completes**
   - Tool_calls are in the state, not in the stream chunks

6. **Don't create tool_calls during streaming**
   - Only create them after stream completes via update event

7. **Don't skip defensive checks for `None` in callback handlers**
   - `serialized` can be `None` for Functional API tasks
   - Always check `isinstance(serialized, dict)` before accessing keys

8. **Don't stream supervisor routing tokens**
   - Supervisor outputs agent names that shouldn't be shown to users
   - Use flags to detect and skip these tokens

9. **Don't forget to handle Django auto-reload**
   - Background threads can cause `RuntimeError` during reload
   - Catch and handle gracefully

10. **Don't use non-serializable data in stream events**
    - All data must be JSON serializable
    - Use dicts, not objects

---

## Best Practices

1. **Use `BaseCallbackHandler` for custom event capture during streaming**
   - Capture LLM tokens via `on_llm_new_token`
   - Capture task status via `on_chain_start` and `on_chain_end`
   - Capture tool status via `on_tool_start` and `on_tool_end`

2. **Track active tasks in callback handler for status updates**
   - Use `self.active_tasks` dict to track task status
   - Remove tasks when they complete

3. **Send status updates as real-time events, not database writes**
   - Use `event_queue.put()` for real-time updates
   - Don't persist to database

4. **Use temporary IDs for ephemeral UI elements**
   - Negative IDs for temporary status messages
   - Clear them when starting new streams

5. **Extract final response data from state dict after stream completes**
   - Check for workflow name key first (`'ai_agent_workflow'`)
   - Fallback to common keys (`'response'`, `'result'`, `'output'`)
   - Handle both dict and object formats

6. **Keep logs minimal - only major workflow steps and errors**
   - Remove verbose debug logs
   - Remove TEMPORARY comments
   - Keep only essential info/error logs

7. **Handle Django auto-reload gracefully in background threads**
   - Use daemon threads
   - Catch `RuntimeError` with "cannot schedule new futures" message
   - Exit cleanly without raising exceptions

8. **Ensure tool_calls are sent via stream update event**
   - Extract from final state after stream completes
   - Format as JSON-serializable dicts
   - Send via update event before done event

9. **Control tool items visibility with flags**
   - Use `streamComplete` flag to control when tool items appear
   - Tool status updates show during streaming
   - Tool items only appear after stream completes

10. **Preserve temporary messages during merge**
    - Filter out temporary messages when loading from DB
    - Merge DB messages with active temporary messages
    - Sort by timestamp to maintain order

---

## Architecture Decisions

### 1. No Database Persistence for Status Messages

**Decision**: Status messages are ephemeral UI feedback, not historical data.

**Rationale**:
- Status messages are temporary indicators of current workflow state
- They don't provide historical value
- Persisting them causes database bloat
- Real-time updates are more efficient

**Implementation**:
- Status messages use temporary negative IDs
- They're created/updated via stream events
- They're cleared when switching sessions or starting new streams
- They're filtered out when loading messages from database

### 2. Stream-Only Tool Calls

**Decision**: Tool_calls come via stream update event, not database fetch.

**Rationale**:
- Tool_calls are part of the agent response
- They're available in the final state after stream completes
- Fetching from database is unnecessary and causes delays
- Stream provides all necessary data

**Implementation**:
- Extract tool_calls from `final_state['ai_agent_workflow']` after stream completes
- Send via update event before done event
- Frontend receives and stores in message metadata
- No database fetch needed

### 3. Visibility Control via Flags

**Decision**: Use `streamComplete` flag to control when tool items appear.

**Rationale**:
- Tool items should only appear after stream completes
- Tool status updates (Executing -> Executed) show during streaming
- Flag provides clear control over visibility
- Prevents premature display of incomplete data

**Implementation**:
- Track completed streams in `Set<number>` (message IDs)
- Mark as complete when done event arrives
- Check flag before rendering tool items
- Also mark DB messages as complete when loaded

### 4. Callback-Based Streaming

**Decision**: Use callbacks instead of `astream_events()` for compatibility.

**Rationale**:
- `astream_events()` requires async checkpointers
- `PostgresSaver` is synchronous
- `BaseCallbackHandler` provides same functionality
- More compatible with existing infrastructure

**Implementation**:
- Use `stream()` method with sync checkpointer
- Implement `BaseCallbackHandler` for event capture
- Run stream in background thread if needed
- Send events via queue to main thread

---

## Implementation Checklist

When implementing LangGraph Functional API from scratch:

- [ ] Use `stream()` with `BaseCallbackHandler`, not `astream_events()`
- [ ] Extract response from state dict (`final_state['ai_agent_workflow']`)
- [ ] Generate unique tool call IDs using UUID
- [ ] Match tool calls by both name and args
- [ ] Don't persist status messages to database
- [ ] Use temporary negative IDs for status messages
- [ ] Clear temporary messages when starting new streams
- [ ] Extract task name from `kwargs.get("name")` in callbacks
- [ ] Check `isinstance(serialized, dict)` before accessing keys
- [ ] Filter supervisor tokens using flags
- [ ] Handle Django auto-reload gracefully
- [ ] Ensure all stream data is JSON serializable
- [ ] Use `streamComplete` flag for tool items visibility
- [ ] Preserve temporary messages during merge
- [ ] Don't reload messages after streaming
- [ ] Keep logs minimal (only major steps and errors)

---

## References

- [LangGraph Functional API Documentation](https://docs.langchain.com/oss/python/langgraph/functional-api#invoke)
- Original Plan: `LANGGRAPH_FUNCTIONAL_API_PLAN.md`
- Implementation Files:
  - `backend/app/agents/functional/workflow.py`
  - `backend/app/agents/functional/tasks.py`
  - `backend/app/agents/runner.py`
  - `frontend/src/app/chat/ChatPage.tsx`
