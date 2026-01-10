"""
RAG retrieval tool for agents.
"""
from typing import Optional
from langchain_core.tools import tool, BaseTool
from app.rag.pipelines.query_pipeline import query_rag


def create_rag_tool(user_id: int) -> BaseTool:
    """
    Create a RAG tool for agent use.
    
    Args:
        user_id: User ID for multi-tenant filtering
        
    Returns:
        LangChain BaseTool instance
    """
    @tool
    def rag_retrieval_tool(query: str, document_ids: Optional[list] = None) -> str:
        """
        Retrieve relevant context from uploaded documents using RAG.
        
        Use this tool when you need to search through the user's uploaded documents
        to find relevant information to answer their question.
        
        Args:
            query: Search query to find relevant document chunks
            document_ids: Optional list of specific document IDs to search within.
                         If not provided, searches all user's documents.
        
        Returns:
            Formatted context string with relevant document chunks and citations.
        """
        try:
            # Query RAG pipeline
            result = query_rag(
                user_id=user_id,
                query=query,
                top_k=30,
                top_n=8,
                document_ids=document_ids
            )
            
            if not result.get('items'):
                return "No relevant documents found for your query."
            
            # Format context for agent
            context_parts = []
            for item in result['items']:
                doc_title = item['doc_title']
                content = item['content']
                page = item['metadata'].get('page')
                score = item.get('score', 0)
                
                citation = f"[{doc_title}"
                if page:
                    citation += f", page {page}"
                citation += "]"
                
                context_parts.append(f"{citation}\n{content}")
            
            context = "\n\n---\n\n".join(context_parts)
            
            return f"Retrieved {len(result['items'])} relevant chunks:\n\n{context}"
        
        except Exception as e:
            return f"Error retrieving context: {str(e)}"
    
    return rag_retrieval_tool
