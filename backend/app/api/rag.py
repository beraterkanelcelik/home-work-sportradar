"""
RAG query endpoint.
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from app.core.dependencies import get_current_user
from app.rag.pipelines.query_pipeline import query_rag
from app.core.logging import get_logger

logger = get_logger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def rag_query(request):
    """
    Query RAG pipeline.
    
    Request body:
    {
        "query": "search query",
        "top_k": 30,  # optional
        "top_n": 8,   # optional
        "document_ids": [1, 2]  # optional, filter by specific documents
    }
    
    Returns:
    {
        "items": [
            {
                "doc_id": 12,
                "doc_title": "spec.pdf",
                "chunk_id": 331,
                "chunk_index": 5,
                "content": "...",
                "score": 0.95,
                "metadata": {"page": 4}
            }
        ],
        "debug": {
            "retrieved": 30,
            "reranked": 20,
            "returned": 8,
            "latency_ms": 250
        }
    }
    """
    user = get_current_user(request)
    if not user:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        data = json.loads(request.body)
        query = data.get('query', '').strip()
        
        if not query:
            return JsonResponse({'error': 'Query is required'}, status=400)
        
        top_k = data.get('top_k')
        top_n = data.get('top_n')
        document_ids = data.get('document_ids')
        
        # Query RAG pipeline
        result = query_rag(
            user_id=user.id,
            query=query,
            top_k=top_k,
            top_n=top_n,
            document_ids=document_ids
        )
        
        return JsonResponse(result)
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in RAG query: {str(e)}")
        return JsonResponse({'error': f'Query failed: {str(e)}'}, status=500)
