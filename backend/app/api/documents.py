"""
Document management endpoints (upload, list, delete).
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

# TODO: Implement document endpoints
# - GET /api/documents (list user's documents)
# - POST /api/documents (upload and ingest document)
# - DELETE /api/documents/{document_id} (delete document)
# - GET /api/documents/{document_id} (get document metadata)


@require_http_methods(["GET", "POST"])
def documents(request):
    """List or upload documents."""
    # TODO: Implement documents
    return JsonResponse({"message": "Documents endpoint - to be implemented"})


@require_http_methods(["GET", "DELETE"])
def document_detail(request, document_id):
    """Get or delete specific document."""
    # TODO: Implement document detail
    return JsonResponse({"message": f"Document {document_id} - to be implemented"})
