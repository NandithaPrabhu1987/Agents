Phase 2: Retrieval (RAG Foundation)
===================================
Endpoints / Tools Added:
- Tool add_document: Add a document into vector store
- Tool retrieve_relevant: Similarity search over stored documents
- Endpoint POST /api/chat/plan+retrieve: Retrieval-augmented planning

Vector Store Implementation:
- File: src/retrieval/vector_store.py
- Persists under logs/vector_store/ (documents.json, embeddings.npy, meta.json)
- Uses fastembed if available; fallback to simple hashing vector (384-dim)

Usage Examples (curl):
1. Add Document:
   curl -X POST http://localhost:8000/api/agent/tools/invoke \
     -F tool_name=add_document \
     -F 'payload={"content":"Monsoon demand expected +30% in Bangalore due to forecast rains","source":"forecast_sep","doc_type":"forecast"}'

2. Retrieve Relevant:
   curl -X POST http://localhost:8000/api/agent/tools/invoke \
     -F tool_name=retrieve_relevant \
     -F 'payload={"query":"monsoon gear demand bangalore","top_k":3}'

3. Retrieval-Augmented Plan:
   curl -X POST http://localhost:8000/api/chat/plan+retrieve \
     -F 'query=Plan transfers for monsoon gear considering recent demand forecasts'

Design Notes:
- Retrieval augmentation adds field retrieved_docs to context provided to LLM.
- Plan response now can leverage additional factual snippets.
- All retrieval operations are synchronous & lightweight (small data volume).
- Embedding fallback ensures zero external dependency requirement.

Next Steps (Potential Phase 3):
- Add metadata filters to retrieval (e.g., by source or doc_type)
- Track embedding costs / token usage in audit
- Implement recursive summarization for long documents
- Introduce conversation-grounded retrieval for chat endpoint
