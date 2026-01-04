"""
Agent execution endpoints.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

# TODO: Implement agent endpoints
# - POST /api/agent/run (run agent with input)
# - GET /api/agent/stream/{run_id} (stream agent response)


@require_http_methods(["POST"])
def run_agent(request):
    """Run agent with input message."""
    # TODO: Implement agent run
    return JsonResponse({"message": "Agent run endpoint - to be implemented"})


@require_http_methods(["GET"])
def stream_agent(request, run_id):
    """
    Stream agent response using SSE (Server-Sent Events).
    """
    from django.http import StreamingHttpResponse
    import json
    
    def event_stream():
        # TODO: Implement SSE streaming
        # This should stream agent events as they occur
        yield f"data: {json.dumps({'type': 'token', 'data': 'Streaming not yet implemented'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
