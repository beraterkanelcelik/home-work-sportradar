"""
Token counting utilities using tiktoken for accurate token estimation.
"""
from typing import Optional
from django.conf import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cache for encodings
_encoding_cache = {}


def get_tokenizer(model_name: Optional[str] = None) -> Optional[object]:
    """
    Get tiktoken encoding for a model.
    
    Args:
        model_name: Model name (e.g., 'gpt-4o-mini', 'gpt-4o')
        
    Returns:
        tiktoken encoding object or None if unavailable
    """
    if model_name is None:
        model_name = getattr(settings, 'RAG_TOKENIZER_MODEL', 'gpt-4o-mini')
    
    # Check cache
    if model_name in _encoding_cache:
        return _encoding_cache[model_name]
    
    try:
        import tiktoken
        
        # Map model names to tiktoken encodings
        # Try to get encoding for the model
        try:
            encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fallback to cl100k_base (used by most OpenAI models)
            logger.warning(f"Unknown model {model_name}, using cl100k_base encoding")
            encoding = tiktoken.get_encoding("cl100k_base")
        
        _encoding_cache[model_name] = encoding
        return encoding
        
    except ImportError:
        logger.warning("tiktoken not available, falling back to character estimation")
        return None
    except Exception as e:
        logger.warning(f"Failed to get tiktoken encoding: {e}, falling back to character estimation")
        return None


def count_tokens(text: str, model_name: Optional[str] = None) -> int:
    """
    Count tokens in text using tiktoken or fallback to estimation.
    
    Args:
        text: Text to count tokens for
        model_name: Model name for tokenizer selection
        
    Returns:
        Number of tokens
    """
    tokenizer = get_tokenizer(model_name)
    
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Token counting failed: {e}, using estimation")
    
    # Fallback: rough estimation (1 token ≈ 4 characters)
    return len(text) // 4


def estimate_chunk_size_in_chars(target_tokens: int, model_name: Optional[str] = None) -> int:
    """
    Estimate character count for a target token count.
    
    Args:
        target_tokens: Target number of tokens
        model_name: Model name for tokenizer selection
        
    Returns:
        Estimated character count
    """
    tokenizer = get_tokenizer(model_name)
    
    if tokenizer is not None:
        # Use a sample text to estimate token-to-char ratio
        # This is more accurate than a fixed ratio
        sample_text = "This is a sample text to estimate the token-to-character ratio. " * 10
        try:
            sample_tokens = len(tokenizer.encode(sample_text))
            ratio = len(sample_text) / sample_tokens if sample_tokens > 0 else 4.0
            return int(target_tokens * ratio)
        except Exception:
            pass
    
    # Fallback: rough estimation (1 token ≈ 4 characters)
    return target_tokens * 4
