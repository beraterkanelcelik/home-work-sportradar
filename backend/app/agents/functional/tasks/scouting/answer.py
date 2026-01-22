"""
Answer Generation Task with Streaming.

Generates a final answer using LLM with token streaming.
Supports both:
- RAG queries (info_query): Synthesizes answer from retrieved documents
- General chat: Conversational responses using chat history
"""

from typing import Optional, List, Dict, Any, Tuple
from queue import Queue
from langgraph.func import task
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.agents.functional.streaming import EventCallbackHandler
from app.agents.config import OPENAI_MODEL, get_model_context_window
from app.rag.chunking.tokenizer import count_tokens
from app.core.logging import get_logger

logger = get_logger(__name__)


RAG_ANSWER_SYSTEM_PROMPT = """You are a helpful sports knowledge assistant. Based on the retrieved documents, answer the user's question clearly and concisely.

Guidelines:
- Synthesize information from the provided context
- If the context doesn't contain enough information, say so honestly
- Be factual and cite specific details from the documents when possible
- Keep responses focused and well-organized
- Use bullet points or short paragraphs for readability"""

CHAT_SYSTEM_PROMPT = """You are a helpful sports scouting assistant. You help users with questions about sports, players, and scouting.

Guidelines:
- Be conversational and helpful
- If asked about previous conversation, refer to the chat history
- Keep responses concise but informative
- If you don't know something, say so honestly"""


@task
def generate_answer(
    question: str,
    context: str,
    chat_history: Optional[List[dict]] = None,
    api_key: Optional[str] = None,
    event_queue: Optional[Queue] = None,
    is_general_chat: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate an answer with streaming.

    Args:
        question: The user's question
        context: Accumulated RAG context (from rag_search steps), empty for general_chat
        chat_history: Optional chat history (list of {role, content} dicts)
        api_key: OpenAI API key
        event_queue: Event queue for streaming tokens
        is_general_chat: True for conversational responses, False for RAG synthesis

    Returns:
        Tuple of (answer_text, context_usage_dict)
    """
    logger.info(f"[ANSWER] Generating answer for: {question[:50]}... (is_general_chat={is_general_chat})")

    default_context_usage = {
        "total_tokens": 0,
        "context_window": get_model_context_window(OPENAI_MODEL),
        "usage_percentage": 0.0,
        "tokens_remaining": get_model_context_window(OPENAI_MODEL),
    }

    if not api_key:
        logger.warning("[ANSWER] No API key provided")
        return "I'm unable to generate a response without API access.", default_context_usage

    # Build messages based on mode
    if is_general_chat:
        # General chat mode - conversational response using history
        messages = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]

        # Add chat history (this is the context for general chat)
        if chat_history:
            for msg in chat_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" and content:
                    messages.append(HumanMessage(content=content))
                elif role == "assistant" and content:
                    messages.append(AIMessage(content=content))

        # Add current question
        messages.append(HumanMessage(content=question))
    else:
        # RAG mode - synthesize answer from documents
        messages = [SystemMessage(content=RAG_ANSWER_SYSTEM_PROMPT)]

        # Add chat history for conversational continuity
        if chat_history:
            for msg in chat_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" and content:
                    messages.append(HumanMessage(content=content))
                elif role == "assistant" and content:
                    messages.append(AIMessage(content=content))

        # Check if we have RAG context
        if not context.strip():
            logger.warning("[ANSWER] No RAG context available for info_query")
            return "I couldn't find relevant information in your documents to answer this question.", default_context_usage

        # Add context and question
        user_content = f"""Based on the following retrieved documents, please answer my question.

**Retrieved Documents:**
{context}

**Question:** {question}"""

        messages.append(HumanMessage(content=user_content))

    # Calculate context usage before LLM call
    total_tokens = 0
    for msg in messages:
        if hasattr(msg, 'content') and msg.content:
            total_tokens += count_tokens(str(msg.content), OPENAI_MODEL)

    context_window = get_model_context_window(OPENAI_MODEL)
    usage_percentage = (total_tokens / context_window) * 100 if context_window > 0 else 0
    tokens_remaining = max(0, context_window - total_tokens)

    context_usage = {
        "total_tokens": total_tokens,
        "context_window": context_window,
        "usage_percentage": round(usage_percentage, 1),
        "tokens_remaining": tokens_remaining,
    }

    logger.info(f"[ANSWER] Context usage: {total_tokens}/{context_window} ({usage_percentage:.1f}%)")

    # Set up LLM with streaming callback
    callbacks = []
    if event_queue:
        callback_handler = EventCallbackHandler(event_queue)
        callbacks.append(callback_handler)

    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=api_key,
        temperature=0.7 if is_general_chat else 0.3,  # Higher temp for chat, lower for RAG
        streaming=True,
        callbacks=callbacks,
    )

    try:
        # Stream the response
        response = llm.invoke(messages)
        answer = response.content

        # Update context usage with output tokens
        output_tokens = count_tokens(answer, OPENAI_MODEL)
        context_usage["total_tokens"] += output_tokens
        context_usage["usage_percentage"] = round(
            (context_usage["total_tokens"] / context_window) * 100, 1
        )
        context_usage["tokens_remaining"] = max(0, context_window - context_usage["total_tokens"])

        logger.info(f"[ANSWER] Generated answer: {len(answer)} chars, {output_tokens} output tokens")
        return answer, context_usage

    except Exception as e:
        logger.error(f"[ANSWER] Error generating answer: {e}", exc_info=True)
        return f"I encountered an error while generating a response: {str(e)}", context_usage
