# LangGraph Functional API Architecture Plan for AI Agent System

## Executive Summary

This document provides a comprehensive plan to implement the AI agent system using LangGraph's **Functional API** with `@entrypoint` and `@task` decorators. The Functional API offers an imperative, procedural approach that integrates seamlessly with existing code while leveraging LangGraph's advanced features like persistence, streaming, and parallel execution.

**Key Improvement**: This plan incorporates LangGraph's built-in middleware features, particularly `SummarizationMiddleware`, to replace manual summarization logic. This reduces code complexity and leverages battle-tested, optimized implementations from the LangGraph ecosystem.

## Functional API vs Graph API

### Key Differences

| Aspect | Graph API | Functional API |
|--------|-----------|----------------|
| **Style** | Declarative (graph definition) | Imperative (procedural code) |
| **Control Flow** | Explicit edges and nodes | Standard Python if/while/for |
| **State** | TypedDict state passed between nodes | Function parameters and return values |
| **Parallelization** | Send API with worker nodes | `@task` decorator with `.result()` |
| **Best For** | Complex routing, visual graphs | Existing code, simple workflows |

### When to Use Functional API

- Existing procedural code that needs LangGraph features
- Simpler workflows with straightforward control flow
- Teams comfortable with standard Python patterns
- Need to integrate with existing functions easily

## Architecture Overview

### High-Level Flow

```mermaid
flowchart TD
    Start([Entrypoint]) --> Supervisor[Supervisor Task]
    Supervisor --> RouteCheck{Route Decision}
    RouteCheck -->|clarification| Clarification[Return Clarification]
    RouteCheck -->|config| ConfigFlow[Config Agent Flow]
    RouteCheck -->|search| SearchFlow[Search Agent Flow]
    RouteCheck -->|process| ProcessFlow[Process Agent Flow]
    RouteCheck -->|greeter| GreeterFlow[Greeter Agent Flow]
    
    ConfigFlow --> ToolCheck{Tool Calls?}
    SearchFlow --> ToolCheck
    ProcessFlow --> ToolCheck
    GreeterFlow --> Answer[Return Answer]
    
    ToolCheck -->|auto-executable| ParallelTools[Parallel Tool Tasks]
    ToolCheck -->|needs approval| PlanProposal[Return Plan]
    ToolCheck -->|answer| Answer
    
    ParallelTools --> RefineAgent[Refine Agent Task]
    RefineAgent --> ToolCheck
    
    PlanProposal --> End([END])
    Answer --> PostProcess[Post-Process Task]
    PostProcess --> End
    Clarification --> End
```

## Built-in LangGraph Features to Leverage

This section identifies LangGraph built-in features that can replace manual implementations, significantly reducing code complexity and improving reliability.

### 1. SummarizationMiddleware (PRIMARY IMPROVEMENT)

**Current Implementation**: Manual summarization in `SessionManager` with custom LLM calls, threshold checking, and database persistence.

**LangGraph Solution**: Use `SummarizationMiddleware` which automatically:
- Monitors token/message counts
- Triggers summarization at configurable thresholds
- Preserves recent messages (keeps AI/tool message pairs together)
- Handles summarization transparently

**Benefits**:
- Automatic, no manual trigger logic needed
- Optimized for performance
- Maintains message pair integrity (keeps AI/tool message pairs together)
- Reduces code complexity by ~200 lines
- Configurable triggers (tokens, messages, or custom conditions)
- Preserves recent messages automatically
- Transparent to agent (appears as system message)

**Current Manual Implementation Locations**:
- `backend/ai_new/core/session_manager.py`: `needs_summary()`, `summarize_history()`, `maybe_summarize()` (~200 lines)
- `backend/ai_new/agents/ai_agent.py`: `_maybe_summarize_history()` calls (multiple locations)
- Manual threshold checking, LLM calls, tag parsing, DB persistence

**Replacement Strategy**:
1. Remove `SessionManager.summarize_history()` and related methods
2. Wrap all agents with `SummarizationMiddleware` at creation time
3. Use `MessagesState` instead of string history
4. Remove manual `maybe_summarize()` calls throughout codebase

### 2. MessagesState for Automatic History Management

**Current Implementation**: Manual history building with string concatenation, character limits, and custom formatting.

**LangGraph Solution**: Use `MessagesState` which:
- Automatically manages message history
- Integrates with SummarizationMiddleware
- Provides built-in message reduction strategies
- Works seamlessly with checkpointing

**Benefits**:
- Type-safe message handling
- Automatic persistence via checkpoints
- Built-in message reduction options
- No manual history string building

### 3. Checkpointing for State Persistence

**Current Implementation**: Manual database persistence in Django models.

**LangGraph Solution**: Use built-in checkpointers:
- `PostgresSaver` for production
- `SqliteSaver` for development
- `InMemorySaver` for testing

**Benefits**:
- Automatic state persistence
- Thread-based conversation management
- Built-in recovery and resumption
- No custom persistence logic needed

### 4. Store Interface for Cross-Thread Memory

**Current Implementation**: Session-scoped data only.

**LangGraph Solution**: Use `BaseStore` for:
- User-level memories across conversations
- Semantic search over memories
- Persistent knowledge storage

**Benefits**:
- Long-term memory across sessions
- Semantic retrieval capabilities
- Namespaced storage per user

**Potential Use Cases**:
- Store user preferences across sessions
- Remember app configurations per user
- Semantic search over past conversations

### 5. Additional Built-in Middleware (Future Considerations)

**ToolRemover Middleware** (from langmiddle package):
- Automatically removes tool-related messages to reduce clutter
- Can be useful for cleaner conversation history

**ContextEngineer Middleware** (from langmiddle package):
- Extracts and stores semantic facts
- Retrieves relevant context automatically
- Could replace or enhance `get_app_context` tool

**Note**: These are from third-party packages but demonstrate the middleware pattern. LangGraph's built-in `SummarizationMiddleware` is the primary feature to adopt.

## Core Data Structures

### Request/Response Models

```python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Literal

class AgentRequest(BaseModel):
    """Input request for the agent."""
    query: str
    session_id: Optional[int] = None
    org_slug: Optional[str] = None
    user_id: Optional[int] = None
    org_roles: List[str] = []
    app_roles: List[str] = []
    flow: str = "main"  # main, direct

class RoutingDecision(BaseModel):
    """Supervisor routing decision."""
    agent: Literal["config", "search", "process", "greeter"]
    query: str
    require_clarification: bool = False

class ToolProposal(BaseModel):
    """Tool execution proposal."""
    tool: str
    props: Dict[str, Any]
    query: str = ""

class ToolResult(BaseModel):
    """Tool execution result."""
    tool: str
    args: Dict[str, Any]
    output: Any
    error: str = ""

class PlanProposal(BaseModel):
    """Plan proposal for user approval."""
    type: Literal["plan_proposal"] = "plan_proposal"
    plan: List[Dict[str, Any]]
    plan_index: int = 0
    plan_total: int = 0

class AgentResponse(BaseModel):
    """Final agent response."""
    type: Literal["answer", "plan_proposal"]
    reply: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None
    clarification: Optional[str] = None
    token_usage: Dict[str, int] = {}
    raw_tool_outputs: Optional[List[Dict[str, Any]]] = None
```

### Context Models

```python
from langgraph.graph import MessagesState
from typing_extensions import Annotated
from typing import List, Dict, Any, Optional
import operator

class AgentContext(BaseModel):
    """Context passed through the workflow."""
    request: AgentRequest
    # Use MessagesState for automatic history management
    messages: Annotated[List[Any], operator.add] = []  # LangChain messages
    context_snippets: List[str] = []
    retrieved_snippets: str = ""
    tool_results: List[ToolResult] = []
    tool_errors: List[str] = []
    agent_logs: List[str] = []
    token_usage: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
```

### MessagesState Integration

Instead of manual history strings, use LangGraph's `MessagesState`:

```python
from langgraph.graph import MessagesState
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

# MessagesState automatically:
# - Manages message history
# - Integrates with SummarizationMiddleware
# - Persists via checkpoints
# - Handles message reduction

# Example usage in tasks:
@task
def domain_agent_task(
    messages: List[Any],  # MessagesState messages
    context_snippets: List[str],
    # ... other params
) -> tuple[List[ToolProposal], Optional[str], List[Any]]:
    """
    Returns: (proposals, answer, new_messages)
    Messages are automatically managed by SummarizationMiddleware
    """
    # Add context as system message
    system_msg = SystemMessage(content=f"Context:\n{chr(10).join(context_snippets)}")
    
    # Invoke agent with messages
    response = agent.invoke({
        "messages": [system_msg] + messages,
        # ... other params
    })
    
    # Extract new messages (response + tool calls)
    new_messages = [response]
    if hasattr(response, 'tool_calls') and response.tool_calls:
        # Tool calls will be handled separately
        pass
    
    proposals = extract_proposals(response)
    answer = extract_render_reply(response)
    
    return proposals, answer, new_messages
```

## Task Implementations

### 1. Supervisor Task

```python
from langgraph.func import task
from langchain_openai import ChatOpenAI

@task
def supervisor_task(
    query: str,
    history: str,
    agentlog: str,
    model_name: str
) -> RoutingDecision:
    """
    Route user query to appropriate domain agent.
    
    Uses supervisor agent to analyze query and make routing decision.
    """
    supervisor = build_supervisor(model_name)
    
    response = supervisor.invoke({
        "query": query,
        "history": history,
        "agentlog": agentlog,
    })
    
    routing = parse_supervisor_routing(response)
    
    if not routing:
        # Fallback to process agent
        return RoutingDecision(agent="process", query=query)
    
    return RoutingDecision(
        agent=routing.get("agent", "process"),
        query=routing.get("query", query),
        require_clarification=routing.get("require_clarification", False),
    )
```

### 2. Domain Agent Tasks

```python
@task
def config_agent_task(
    query: str,
    history: str,
    context_snippets: List[str],
    retrieved_snippets: str,
    last_tool_output: str,
    last_tool_args: str,
    last_tool_error: str,
    model_name: str,
    org_roles: List[str],
    app_roles: List[str],
) -> tuple[List[ToolProposal], Optional[str]]:
    """
    Execute config agent and return proposals/answer.
    
    Returns:
        Tuple of (proposals list, answer string or None)
    """
    agent = build_config_agent(model_name, org_roles, app_roles)
    
    response = agent.invoke({
        "query": query,
        "history": history,
        "context_snippets": "\n".join(f"- {s}" for s in context_snippets),
        "retrieved_snippets": retrieved_snippets,
        "last_tool_output": last_tool_output,
        "last_tool_args": last_tool_args,
        "last_tool_error": last_tool_error,
        "postprocess_mode": "",
    })
    
    proposals = extract_proposals(response)
    answer = extract_render_reply(response) or extract_answer(response)
    
    return (
        [ToolProposal(tool=p.tool, props=p.props, query=query) for p in proposals],
        answer
    )

@task
def search_agent_task(
    query: str,
    history: str,
    context_snippets: List[str],
    retrieved_snippets: str,
    last_tool_output: str,
    last_tool_args: str,
    last_tool_error: str,
    model_name: str,
    org_roles: List[str],
    app_roles: List[str],
) -> tuple[List[ToolProposal], Optional[str]]:
    """Execute search agent."""
    agent = build_search_agent(model_name, org_roles, app_roles)
    # Same implementation as config_agent_task
    return _invoke_domain_agent(agent, query, history, context_snippets, 
                                retrieved_snippets, last_tool_output, 
                                last_tool_args, last_tool_error)

@task
def process_agent_task(
    query: str,
    history: str,
    context_snippets: List[str],
    retrieved_snippets: str,
    last_tool_output: str,
    last_tool_args: str,
    last_tool_error: str,
    model_name: str,
    org_roles: List[str],
    app_roles: List[str],
) -> tuple[List[ToolProposal], Optional[str]]:
    """Execute process agent."""
    agent = build_process_agent(model_name, org_roles, app_roles)
    return _invoke_domain_agent(agent, query, history, context_snippets,
                               retrieved_snippets, last_tool_output,
                               last_tool_args, last_tool_error)

@task
def greeter_agent_task(
    query: str,
    history: str,
    model_name: str,
) -> str:
    """Execute greeter agent - always returns answer."""
    agent = build_greeter_agent(model_name)
    
    response = agent.invoke({
        "query": query,
        "history": history,
        "context_snippets": "",
        "retrieved_snippets": "",
        "last_tool_output": "",
        "last_tool_args": "{}",
        "last_tool_error": "",
        "postprocess_mode": "",
    })
    
    answer = extract_render_reply(response) or extract_answer(response)
    return answer or ""

def _invoke_domain_agent(
    agent: Runnable,
    query: str,
    history: str,
    context_snippets: List[str],
    retrieved_snippets: str,
    last_tool_output: str,
    last_tool_args: str,
    last_tool_error: str,
) -> tuple[List[ToolProposal], Optional[str]]:
    """Common logic for invoking domain agents."""
    response = agent.invoke({
        "query": query,
        "history": history,
        "context_snippets": "\n".join(f"- {s}" for s in context_snippets),
        "retrieved_snippets": retrieved_snippets,
        "last_tool_output": last_tool_output,
        "last_tool_args": last_tool_args,
        "last_tool_error": last_tool_error,
        "postprocess_mode": "",
    })
    
    proposals = extract_proposals(response)
    answer = extract_render_reply(response) or extract_answer(response)
    
    return (
        [ToolProposal(tool=p.tool, props=p.props, query=query) for p in proposals],
        answer
    )
```

### 3. Tool Execution Tasks

```python
@task
def auto_execute_tool_task(
    tool_name: str,
    tool_args: Dict[str, Any],
    org_slug: Optional[str],
    user_id: Optional[int],
) -> ToolResult:
    """
    Execute a single tool (for parallel execution).
    
    This task is designed to be called in parallel for multiple tools.
    """
    tool_executor = ToolExecutor(
        tool_service=tool_service,
        org_slug=org_slug,
        user_id=user_id,
    )
    
    try:
        output = tool_executor.execute_simple(tool_name, tool_args)
        return ToolResult(
            tool=tool_name,
            args=tool_args,
            output=output,
            error="",
        )
    except Exception as exc:
        return ToolResult(
            tool=tool_name,
            args=tool_args,
            output=None,
            error=str(exc),
        )

@task
def execute_tool_with_retry_task(
    tool_name: str,
    tool_args: Dict[str, Any],
    agent_for_repairs: str,
    query: str,
    org_slug: Optional[str],
    user_id: Optional[int],
    model_name: str,
    org_roles: List[str],
    app_roles: List[str],
) -> ToolResult:
    """
    Execute tool with retry logic and agent-based repair.
    
    Used for plan execution where retry is needed.
    """
    tool_executor = ToolExecutor(
        tool_service=tool_service,
        org_slug=org_slug,
        user_id=user_id,
    )
    
    # Set repair callback
    def repair_callback(agent: str, query: str, last_error: Optional[str]):
        agent_chain = _route_to_agent(agent, model_name, org_roles, app_roles)
        proposals, _ = _invoke_agent_for_repair(
            agent_chain, query, last_error, history=""
        )
        return proposals, None
    
    tool_executor.set_repair_callback(repair_callback)
    
    try:
        output = tool_executor.execute(
            tool_name,
            tool_args,
            agent_for_repairs=agent_for_repairs,
            query=query,
        )
        return ToolResult(
            tool=tool_name,
            args=tool_args,
            output=output,
            error="",
        )
    except ToolProposalNeeded as e:
        # Convert to plan proposal
        raise e  # Will be caught by entrypoint
    except Exception as exc:
        return ToolResult(
            tool=tool_name,
            args=tool_args,
            output=None,
            error=str(exc),
        )
```

### 4. Refine Agent Task

```python
@task
def refine_agent_task(
    agent_name: str,
    query: str,
    history: str,
    context_snippets: List[str],
    tool_results: List[ToolResult],
    model_name: str,
    org_roles: List[str],
    app_roles: List[str],
) -> tuple[List[ToolProposal], Optional[str]]:
    """
    Re-invoke agent with search results.
    
    Used after auto-executing search tools to let agent decide next steps.
    """
    agent = _route_to_agent(agent_name, model_name, org_roles, app_roles)
    
    # Build tool execution context
    tool_executions = [
        {
            "tool": tr.tool,
            "args": tr.args,
            "output": tr.output,
            "error": tr.error,
        }
        for tr in tool_results
    ]
    combined_output = json.dumps(tool_executions, ensure_ascii=False)
    combined_error = "; ".join(tr.error for tr in tool_results if tr.error)
    
    last_tool_args = tool_results[-1].args if tool_results else {}
    
    response = agent.invoke({
        "query": query,
        "history": history,
        "context_snippets": "\n".join(f"- {s}" for s in context_snippets),
        "retrieved_snippets": "",
        "last_tool_output": combined_output,
        "last_tool_args": json.dumps(last_tool_args),
        "last_tool_error": combined_error,
        "postprocess_mode": "",
    })
    
    proposals = extract_proposals(response)
    answer = extract_render_reply(response)
    
    return (
        [ToolProposal(tool=p.tool, props=p.props, query=query) for p in proposals],
        answer
    )
```

### 5. Post-Process Task

```python
@task
def postprocess_task(
    agent_name: str,
    query: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_output: Any,
    tool_error: str,
    history: str,
    context_snippets: List[str],
    model_name: str,
    org_roles: List[str],
    app_roles: List[str],
) -> str:
    """
    Post-process tool output into user-friendly answer.
    
    Used after tool execution to format results.
    """
    agent = _route_to_agent(agent_name, model_name, org_roles, app_roles)
    
    tool_execution = {
        "tool": tool_name,
        "args": tool_args,
        "output": tool_output,
        "error": tool_error,
    }
    tool_output_json = json.dumps([tool_execution], ensure_ascii=False)
    
    response = agent.invoke({
        "query": f"[TOOL EXECUTED: {tool_name}] {query}",
        "history": history,
        "context_snippets": "\n".join(f"- {s}" for s in context_snippets),
        "retrieved_snippets": "",
        "last_tool_output": tool_output_json,
        "last_tool_args": json.dumps(tool_args),
        "last_tool_error": tool_error,
        "postprocess_mode": "render_tool_output",
    })
    
    answer = extract_render_reply(response)
    if not answer and tool_error:
        # Fallback error message
        if "sanitize_failed" in tool_error:
            return f"Tool ran, but its output couldn't be serialized for display. ({tool_name})"
        return f"Failed to execute {tool_name}. {tool_error}"
    
    return answer or f"⚠️ Internal formatting error while processing {tool_name}. Please retry."
```

### 6. Context Building Tasks (Refactored with Built-in Features)

```python
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import MessagesState

# Setup SummarizationMiddleware (replaces manual summarization)
def create_agent_with_summarization(
    agent: Runnable,
    model_name: str,
    checkpointer: PostgresSaver,
) -> Runnable:
    """
    Wrap agent with SummarizationMiddleware.
    
    This replaces ~200 lines of manual summarization logic in SessionManager.
    """
    return agent.with_config({
        "middleware": [
            SummarizationMiddleware(
                model=model_name,  # Use cheaper model for summarization
                trigger=("tokens", 4000),  # Trigger at 4000 tokens
                keep=("messages", 20),  # Keep last 20 messages
                # Optional: custom summarization prompt
                # summary_prompt=CustomSummaryPrompt(),
            )
        ],
        "checkpointer": checkpointer,
    })

@task
def load_messages_from_checkpoint(
    thread_id: str,
    checkpointer: PostgresSaver,
) -> List[Any]:
    """
    Load messages from checkpoint (replaces manual DB loading).
    
    SummarizationMiddleware handles summarization automatically.
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    # Load checkpoint state
    checkpoint = checkpointer.get(config)
    if checkpoint and "messages" in checkpoint:
        return checkpoint["messages"]
    
    return []

@task
def get_app_context_task(
    org_slug: Optional[str],
    user_id: Optional[int],
) -> tuple[List[str], Optional[str]]:
    """
    Get app context snippets.
    
    Returns:
        Tuple of (snippets list, error message or None)
    """
    tool_executor = ToolExecutor(
        tool_service=tool_service,
        org_slug=org_slug,
        user_id=user_id,
    )
    
    snippets, error = tool_executor.get_app_context()
    return snippets, error

# REMOVED: maybe_summarize_task - SummarizationMiddleware handles this automatically
# REMOVED: build_context_task - MessagesState handles this automatically
```

## Main Entrypoint

### Primary Workflow (Refactored with Built-in Features)

```python
from langgraph.func import entrypoint
from langgraph.checkpoint.postgres import PostgresSaver
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Literal

# Initialize checkpointer (replaces manual DB persistence)
checkpointer = PostgresSaver.from_conn_string(
    connection_string=os.getenv("DATABASE_URL")
)

# Thread ID from session
thread_id = f"session_{request.session_id}" if request.session_id else f"user_{request.user_id}"

@entrypoint(checkpointer=checkpointer)
def ai_agent_workflow(request: AgentRequest) -> AgentResponse:
    """
    Main entrypoint for AI agent workflow.
    
    Uses SummarizationMiddleware for automatic history management.
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize context
    context = AgentContext(request=request)
    
    # Load messages from checkpoint (SummarizationMiddleware handles summarization)
    messages = load_messages_from_checkpoint(
        thread_id=thread_id,
        checkpointer=checkpointer,
    ).result()
    context.messages = messages
    
    # Get app context
    context_snippets, ctx_error = get_app_context_task(
        request.org_slug,
        request.user_id,
    ).result()
    context.context_snippets = context_snippets
    
    # Build history string from messages (for supervisor - can be optimized)
    # Note: With MessagesState, we could pass messages directly to supervisor
    history_text = _messages_to_history_string(messages, max_lines=40)
    
    # Supervisor routing
    agentlog = "\n".join(context.agent_logs)
    routing = supervisor_task(
        query=request.query,
        history=history_text,  # Can be replaced with messages directly
        agentlog=agentlog,
        model_name=get_model_name(),
    ).result()
    
    # Check for clarification
    if routing.require_clarification:
        return AgentResponse(
            type="answer",
            clarification=routing.query,
        )
    
    # Route to domain agent
    if routing.agent == "greeter":
        answer = greeter_agent_task(
            query=routing.query,
            history=context.history,
            model_name=get_model_name(),
        ).result()
        return AgentResponse(type="answer", reply=answer)
    
    # Add user message to conversation
    user_message = HumanMessage(content=request.query)
    context.messages.append(user_message)
    
    # Invoke domain agent (with SummarizationMiddleware)
    proposals, answer, new_messages = _invoke_domain_agent_by_name(
        routing.agent,
        routing.query,
        context,
        request,
        checkpointer=checkpointer,
        config=config,
    ).result()
    
    # Update messages (SummarizationMiddleware will handle summarization if needed)
    context.messages.extend(new_messages)
    
    # Save checkpoint (messages automatically persisted)
    # This happens automatically via checkpointer, but we can also save explicitly
    # checkpointer.put(config, {"messages": context.messages})
    
    # Handle proposals and answer
    if answer:
        return AgentResponse(type="answer", reply=answer)
    
    if not proposals:
        return AgentResponse(type="answer", reply="")
    
    # Separate auto-executable from pending
    auto_executable = [
        p for p in proposals
        if p.tool in AUTO_EXECUTE_TOOLS
    ]
    pending = [
        p for p in proposals
        if p.tool not in AUTO_EXECUTE_TOOLS
    ]
    
    # Auto-execute search tools in parallel
    if auto_executable and routing.agent in ("config", "search"):
        tool_results = _auto_execute_tools_parallel(
            auto_executable,
            request,
        ).result()
        context.tool_results = tool_results
        
        # Refine with results
        refine_proposals, refine_answer = refine_agent_task(
            agent_name=routing.agent,
            query=routing.query,
            history=context.history,
            context_snippets=context.context_snippets,
            tool_results=tool_results,
            model_name=get_model_name(),
            org_roles=request.org_roles,
            app_roles=request.app_roles,
        ).result()
        
        if refine_answer:
            return AgentResponse(type="answer", reply=refine_answer)
        
        # Filter out auto-executable from refined proposals
        pending = [
            p for p in refine_proposals
            if p.tool not in AUTO_EXECUTE_TOOLS
        ]
    
    # Create plan proposal if pending tools
    if pending:
        plan_steps = [
            {
                "action": "tool",
                "tool": p.tool,
                "props": p.props,
                "agent": routing.agent,
                "query": routing.query,
            }
            for p in pending
        ]
        return AgentResponse(
            type="plan_proposal",
            plan={
                "type": "plan_proposal",
                "plan": plan_steps,
                "plan_index": 0,
                "plan_total": len(plan_steps),
            },
        )
    
    return AgentResponse(type="answer", reply="")

@task
def _invoke_domain_agent_by_name(
    agent_name: str,
    query: str,
    context: AgentContext,
    request: AgentRequest,
    checkpointer: PostgresSaver,
    config: Dict[str, Any],
) -> tuple[List[ToolProposal], Optional[str], List[Any]]:
    """
    Route to appropriate domain agent task.
    
    Returns: (proposals, answer, new_messages)
    Uses SummarizationMiddleware for automatic history management.
    """
    # Build agent with SummarizationMiddleware
    if agent_name == "config":
        base_agent = build_config_agent(get_model_name(), request.org_roles, request.app_roles)
    elif agent_name == "search":
        base_agent = build_search_agent(get_model_name(), request.org_roles, request.app_roles)
    elif agent_name == "process":
        base_agent = build_process_agent(get_model_name(), request.org_roles, request.app_roles)
    else:
        base_agent = build_process_agent(get_model_name(), request.org_roles, request.app_roles)
    
    # Wrap with SummarizationMiddleware
    agent = create_agent_with_summarization(
        agent=base_agent,
        model_name=get_model_name(),
        checkpointer=checkpointer,
    )
    
    # Build context messages
    system_content = f"Context snippets:\n{chr(10).join(f'- {s}' for s in context.context_snippets)}"
    if context.retrieved_snippets:
        system_content += f"\n\nRetrieved snippets:\n{context.retrieved_snippets}"
    
    # Add tool results as messages if available
    messages = list(context.messages)
    if context.tool_results:
        for tr in context.tool_results:
            tool_msg = ToolMessage(
                content=json.dumps(tr.output) if tr.output else tr.error,
                tool_call_id=f"{tr.tool}_{hash(str(tr.args))}",
            )
            messages.append(tool_msg)
    
    # Add system message with context
    system_msg = SystemMessage(content=system_content)
    messages_with_context = [system_msg] + messages
    
    # Invoke agent (SummarizationMiddleware handles history automatically)
    response = agent.invoke(
        {"messages": messages_with_context},
        config=config,
    )
    
    # Extract proposals and answer
    proposals = extract_proposals(response)
    answer = extract_render_reply(response) or extract_answer(response)
    
    # Return new messages (response will be added to state)
    new_messages = [response]
    
    return proposals, answer, new_messages

def _messages_to_history_string(messages: List[Any], max_lines: int = 40) -> str:
    """
    Convert MessagesState messages to history string.
    
    This is a compatibility layer for components that still expect string history.
    Can be removed once all components use MessagesState directly.
    """
    lines = []
    for msg in messages[-max_lines:]:
        if hasattr(msg, 'content'):
            sender = "assistant" if hasattr(msg, 'tool_calls') else "user"
            content = str(msg.content)
            if content:
                lines.append(f"{sender}: {content}")
    return "\n".join(lines)

@task
def _auto_execute_tools_parallel(
    proposals: List[ToolProposal],
    request: AgentRequest,
) -> List[ToolResult]:
    """
    Execute multiple tools in parallel.
    
    Uses @task decorator's built-in parallel execution.
    """
    # Create futures for all tools
    futures = [
        auto_execute_tool_task(
            tool_name=p.tool,
            tool_args=p.props,
            org_slug=request.org_slug,
            user_id=request.user_id,
        )
        for p in proposals
    ]
    
    # Wait for all results
    return [f.result() for f in futures]
```

### Plan Execution Entrypoint

```python
@entrypoint(checkpointer=checkpointer)
def execute_plan_workflow(
    request: AgentRequest,
    plan_steps: List[Dict[str, Any]],
) -> AgentResponse:
    """
    Execute an approved plan.
    
    Processes plan steps sequentially, executing tools and post-processing.
    """
    context = AgentContext(request=request)
    
    # Build history
    history, summary = build_context_task(
        request.session_id,
        request.org_slug,
        max_lines=8,
    ).result()
    context.history = history
    context.summary_text = summary
    
    # Get app context
    context_snippets, _ = get_app_context_task(
        request.org_slug,
        request.user_id,
    ).result()
    context.context_snippets = context_snippets
    
    results: List[str] = []
    raw_tool_outputs: List[Dict[str, Any]] = []
    
    # Process each step
    for step in plan_steps:
        action = step.get("action")
        
        if action == "answer":
            answer = step.get("answer", "")
            if answer:
                results.append(answer)
            continue
        
        if action == "tool":
            tool_name = step.get("tool")
            tool_args = step.get("props", {})
            agent_name = step.get("agent", "process")
            step_query = step.get("query", request.query)
            
            # Execute tool with retry
            try:
                tool_result = execute_tool_with_retry_task(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    agent_for_repairs=agent_name,
                    query=step_query,
                    org_slug=request.org_slug,
                    user_id=request.user_id,
                    model_name=get_model_name(),
                    org_roles=request.org_roles,
                    app_roles=request.app_roles,
                ).result()
            except ToolProposalNeeded as e:
                # Retry generated new proposals
                plan_steps_new = [
                    {
                        "action": "tool",
                        "tool": p.tool,
                        "props": p.props,
                        "agent": e.agent,
                        "query": e.query,
                    }
                    for p in e.proposals
                ]
                return AgentResponse(
                    type="plan_proposal",
                    plan={
                        "type": "plan_proposal",
                        "plan": plan_steps_new,
                        "plan_index": 0,
                        "plan_total": len(plan_steps_new),
                    },
                )
            
            # Store raw output
            raw_tool_outputs.append({
                "tool": tool_result.tool,
                "args": tool_result.args,
                "output": tool_result.output,
            })
            
            # Post-process
            if tool_result.output is not None or tool_result.error:
                answer = postprocess_task(
                    agent_name=agent_name,
                    query=step_query,
                    tool_name=tool_result.tool,
                    tool_args=tool_result.args,
                    tool_output=tool_result.output,
                    tool_error=tool_result.error,
                    history=context.history,
                    context_snippets=context.context_snippets,
                    model_name=get_model_name(),
                    org_roles=request.org_roles,
                    app_roles=request.app_roles,
                ).result()
                
                if answer:
                    results.append(answer)
    
    # Combine results
    final_text = "\n".join(results)
    
    response = AgentResponse(
        type="answer",
        reply=final_text,
        raw_tool_outputs=raw_tool_outputs if raw_tool_outputs else None,
    )
    
    return response
```

## Parallel Execution Patterns

### Pattern 1: Parallel Tool Execution

```python
# Execute multiple tools in parallel
futures = [
    auto_execute_tool_task(tool_name=p.tool, tool_args=p.props, ...)
    for p in proposals
]
results = [f.result() for f in futures]  # Waits for all
```

### Pattern 2: Parallel Agent Invocation

```python
# Invoke multiple agents in parallel (if needed)
config_future = config_agent_task(...)
search_future = search_agent_task(...)
process_future = process_agent_task(...)

# Wait for all
config_result = config_future.result()
search_result = search_future.result()
process_result = process_future.result()
```

### Pattern 3: Conditional Parallel Execution

```python
# Execute tools conditionally in parallel
if should_auto_execute(proposals):
    tool_futures = [
        auto_execute_tool_task(...)
        for p in auto_executable_proposals
    ]
    tool_results = [f.result() for f in tool_futures]
else:
    # Sequential execution or plan proposal
    pass
```

## Error Handling

### Retry Pattern

```python
@task
def execute_with_retry(
    tool_name: str,
    tool_args: Dict[str, Any],
    max_retries: int = 3,
) -> ToolResult:
    """Execute tool with retry logic."""
    for attempt in range(max_retries):
        try:
            result = tool_executor.execute_simple(tool_name, tool_args)
            return ToolResult(tool=tool_name, args=tool_args, output=result)
        except Exception as exc:
            if attempt == max_retries - 1:
                return ToolResult(
                    tool=tool_name,
                    args=tool_args,
                    output=None,
                    error=str(exc),
                )
            # Wait before retry
            time.sleep(0.5 * (attempt + 1))
    
    return ToolResult(tool=tool_name, args=tool_args, output=None, error="Max retries exceeded")
```

### Exception Handling in Entrypoint

```python
@entrypoint(checkpointer=checkpointer)
def safe_workflow(request: AgentRequest) -> AgentResponse:
    """Workflow with comprehensive error handling."""
    try:
        return ai_agent_workflow(request)
    except ToolProposalNeeded as e:
        # Convert to plan proposal
        return AgentResponse(
            type="plan_proposal",
            plan={
                "type": "plan_proposal",
                "plan": [{"action": "tool", "tool": p.tool, "props": p.props} for p in e.proposals],
            },
        )
    except Exception as exc:
        logger.error(f"Workflow error: {exc}", exc_info=True)
        return AgentResponse(
            type="answer",
            reply=f"⚠️ An error occurred: {str(exc)}. Please try again.",
        )
```

## Persistence and Checkpointing

### Setup

```python
from langgraph.checkpoint.postgres import PostgresSaver

# Initialize checkpointer
checkpointer = PostgresSaver.from_conn_string(
    connection_string="postgresql://user:pass@localhost/db"
)

# Use in entrypoint
@entrypoint(checkpointer=checkpointer)
def ai_agent_workflow(request: AgentRequest) -> AgentResponse:
    # Workflow automatically checkpoints at each task boundary
    ...
```

### Resuming from Checkpoint

```python
# Resume workflow from checkpoint
config = {"configurable": {"thread_id": f"session_{session_id}"}}
result = ai_agent_workflow.invoke(request, config=config)
```

## Streaming

### Stream Updates

```python
# Stream workflow execution
for event in ai_agent_workflow.stream(request, config=config, stream_mode="updates"):
    # Send updates to frontend
    send_update_to_frontend(event)
```

### Stream Values

```python
# Stream final values
for value in ai_agent_workflow.stream(request, config=config, stream_mode="values"):
    if "answer" in value:
        send_answer_to_frontend(value["answer"])
```

## Optimization Strategies

### 1. Lazy Context Loading

```python
@task
def get_context_if_needed(
    session_id: Optional[int],
    org_slug: Optional[str],
    force: bool = False,
) -> tuple[str, str]:
    """Only load context if needed."""
    if not force and not session_id:
        return "", ""
    return build_context_task(session_id, org_slug).result()
```

### 2. Caching Tool Results

```python
from functools import lru_cache

@lru_cache(maxsize=100)
@task
def cached_tool_execution(
    tool_name: str,
    tool_args_hash: str,  # Hash of args for cache key
) -> ToolResult:
    """Cached tool execution."""
    return auto_execute_tool_task(tool_name, tool_args, ...).result()
```

### 3. Batch Operations

```python
@task
def batch_tool_execution(
    proposals: List[ToolProposal],
) -> List[ToolResult]:
    """Execute tools in optimized batches."""
    # Group by tool type for batching
    by_tool = {}
    for p in proposals:
        by_tool.setdefault(p.tool, []).append(p)
    
    results = []
    for tool_name, tool_proposals in by_tool.items():
        # Execute batch
        batch_results = [
            auto_execute_tool_task(tool_name, p.props, ...)
            for p in tool_proposals
        ]
        results.extend([f.result() for f in batch_results])
    
    return results
```

## Testing Strategy

### Unit Testing Tasks

```python
def test_config_agent_task():
    """Test config agent task in isolation."""
    proposals, answer = config_agent_task(
        query="Create app 'Test'",
        history="",
        context_snippets=[],
        retrieved_snippets="",
        last_tool_output="",
        last_tool_args="{}",
        last_tool_error="",
        model_name="gpt-4o-mini",
        org_roles=[],
        app_roles=[],
    ).result()
    
    assert len(proposals) > 0
    assert proposals[0].tool == "manage_app"
```

### Integration Testing Entrypoint

```python
def test_ai_agent_workflow():
    """Test full workflow."""
    request = AgentRequest(
        query="Create app 'Test'",
        org_slug="test-org",
        user_id=1,
    )
    
    response = ai_agent_workflow.invoke(request)
    
    assert response.type in ("answer", "plan_proposal")
    if response.type == "plan_proposal":
        assert len(response.plan["plan"]) > 0
```

## Migration from Graph API

### Key Differences

1. **State Management**: Function parameters instead of TypedDict
2. **Control Flow**: Python if/while/for instead of conditional edges
3. **Parallelization**: `@task` futures instead of Send API
4. **Node Definition**: Functions instead of node functions

### Conversion Example

**Graph API:**
```python
def supervisor_node(state: AIAgentState) -> Dict[str, Any]:
    routing = supervisor.invoke(state["query"])
    return {"routing_decision": routing}

workflow.add_node("supervisor", supervisor_node)
workflow.add_conditional_edges("supervisor", route_decision, {...})
```

**Functional API:**
```python
@task
def supervisor_task(query: str, history: str) -> RoutingDecision:
    routing = supervisor.invoke({"query": query, "history": history})
    return RoutingDecision(**routing)

# In entrypoint:
routing = supervisor_task(query, history).result()
if routing.require_clarification:
    return clarification_response
```

## Performance Considerations

### Task Overhead

- Each `@task` creates a checkpoint opportunity
- Use tasks for significant operations, not trivial ones
- Batch small operations together

### Parallel Execution

- Tasks execute in parallel when futures are created together
- Use `.result()` to wait for completion
- Consider thread pool size for concurrent execution

### Memory Management

- Large state passed between tasks
- Consider streaming for large outputs
- Use generators for large datasets

## Security Considerations

### Input Validation

```python
@entrypoint(checkpointer=checkpointer)
def validated_workflow(request: AgentRequest) -> AgentResponse:
    """Workflow with input validation."""
    # Validate request
    if not request.query or len(request.query) > 10000:
        raise ValueError("Invalid query")
    
    # Validate permissions
    if not has_permission(request.user_id, request.org_slug):
        raise PermissionError("Access denied")
    
    return ai_agent_workflow(request)
```

### Tenant Isolation

```python
@task
def isolated_tool_execution(
    tool_name: str,
    tool_args: Dict[str, Any],
    org_slug: str,  # Required for isolation
) -> ToolResult:
    """Tool execution with tenant isolation."""
    # Always pass org_slug for tenant context
    return auto_execute_tool_task(tool_name, tool_args, org_slug, None).result()
```

## Migration from Manual to Built-in Features

### Summarization Migration

**Before (Manual - ~200 lines)**:
```python
# Manual threshold checking
if session_mgr.needs_summary():
    result = session_mgr.summarize_history(reason=reason)
    # Manual LLM call, tag parsing, DB persistence
    # Manual summary notice creation
```

**After (Built-in - ~10 lines)**:
```python
# Automatic via SummarizationMiddleware
agent = create_agent_with_summarization(
    agent=base_agent,
    model_name=model_name,
    checkpointer=checkpointer,
)
# Summarization happens automatically when threshold reached
```

### History Management Migration

**Before (Manual)**:
```python
# Manual string building
history = session_mgr.build_context_history(max_lines=40)
# Manual character counting
# Manual truncation
```

**After (Built-in)**:
```python
# Automatic via MessagesState + SummarizationMiddleware
messages = load_messages_from_checkpoint(thread_id, checkpointer).result()
# Messages automatically managed, summarized when needed
```

### Persistence Migration

**Before (Manual)**:
```python
# Manual Django ORM operations
session = AIChatSession.objects.get(id=session_id)
session.messages = messages
session.summary_text = summary
session.save()
```

**After (Built-in)**:
```python
# Automatic via checkpointer
config = {"configurable": {"thread_id": thread_id}}
# State automatically persisted at each checkpoint
```

## Code Reduction Summary

| Feature | Manual Lines | Built-in Lines | Reduction | Files Affected |
|---------|--------------|----------------|-----------|----------------|
| Summarization | ~200 | ~10 | 95% | `session_manager.py`, `ai_agent.py` |
| History Building | ~100 | ~20 | 80% | `session_manager.py`, `ai_agent.py` |
| Persistence | ~150 | ~5 | 97% | `session_manager.py`, `temporal_ai.py` |
| **Total** | **~450** | **~35** | **92%** | Multiple files |

## Implementation Priority

### Phase 1: High Impact, Low Risk (Do First)
1. **SummarizationMiddleware** - Biggest code reduction, automatic handling
2. **MessagesState** - Type safety, automatic management
3. **Checkpointing** - Automatic persistence, thread management

### Phase 2: Medium Impact (Do Next)
1. **Store Interface** - Cross-thread memory (if needed)
2. **Optimize message conversion** - Remove `_messages_to_history_string` once all components use MessagesState

### Phase 3: Future Enhancements
1. **ToolRemover Middleware** - If tool message clutter becomes an issue
2. **ContextEngineer Middleware** - If semantic fact extraction is needed

## Benefits of Using Built-in Features

1. **Reduced Complexity**: 92% less code for history management
2. **Better Performance**: Optimized implementations
3. **Automatic Handling**: No manual trigger logic needed
4. **Message Integrity**: AI/tool message pairs preserved
5. **Type Safety**: MessagesState provides type checking
6. **Battle-Tested**: Used in production by thousands of applications
7. **Maintenance**: Updates come from LangGraph team
8. **Debugging**: Better observability with built-in tools

## Areas Still Requiring Custom Logic

While built-in features handle most of the complexity, some areas still need custom implementation:

1. **App Context**: Custom tool for fetching app snippets
2. **Tool Execution**: Custom retry logic and tenant context
3. **Response Parsing**: Custom extraction for tool proposals
4. **Plan Management**: Custom plan proposal/execution flow
5. **Chat Title Generation**: Custom LLM call (can be moved to task)

## Conclusion

The Functional API provides a more intuitive, Pythonic approach to building the AI agent system while maintaining all the benefits of LangGraph. By leveraging built-in features like `SummarizationMiddleware` and `MessagesState`, we can:

- **Reduce code by 92%** for history management
- **Improve reliability** with battle-tested implementations
- **Simplify maintenance** with automatic handling
- **Enhance performance** with optimized middleware

Key advantages:

- **Familiar Syntax**: Standard Python control flow
- **Easy Integration**: Works with existing code
- **Parallel Execution**: Built-in with `@task` decorator
- **Persistence**: Automatic checkpointing
- **Streaming**: Real-time updates
- **Type Safety**: Pydantic models for validation
- **Built-in Features**: SummarizationMiddleware, MessagesState, checkpointing

This approach is ideal for teams comfortable with procedural programming who want to leverage LangGraph's advanced features without learning a new graph-based paradigm, while also benefiting from built-in optimizations and reduced code complexity.


imporant infos= https://docs.langchain.com/oss/python/langgraph/functional-api#invoke