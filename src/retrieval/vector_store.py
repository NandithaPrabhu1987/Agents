import json
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
import math

import numpy as np

# Attempt to use fastembed for higher quality embeddings; fallback to simple hashing vector
try:  # lightweight dependency if installed
    from fastembed import TextEmbedding
    _FASTEMBED_AVAILABLE = True
except Exception:  # pragma: no cover
    TextEmbedding = None
    _FASTEMBED_AVAILABLE = False


class VectorStore:
    """Very small persistent vector store for Phase 2 (RAG foundation).
    Persists documents and embeddings under logs/vector_store/.
    """
    def __init__(self, base_dir: Path = Path("logs/vector_store")):
        self.base_dir = base_dir
        self.docs_path = self.base_dir / "documents.json"
        self.emb_path = self.base_dir / "embeddings.npy"
        self.meta_path = self.base_dir / "meta.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.documents: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        self.embedding_dim: Optional[int] = None
        self._embedder = None
        self._load()
        self._init_embedder()

    def _init_embedder(self):
        if _FASTEMBED_AVAILABLE:
            try:
                self._embedder = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            except Exception:  # fallback gracefully
                self._embedder = None
        # If fastembed not available, we will use hashing fallback

    def _load(self):
        if self.docs_path.exists():
            try:
                self.documents = json.loads(self.docs_path.read_text(encoding="utf-8"))
            except Exception:
                self.documents = []
        if self.emb_path.exists():
            try:
                self.embeddings = np.load(self.emb_path)
                if self.embeddings.ndim == 1:
                    self.embeddings = self.embeddings.reshape(1, -1)
                self.embedding_dim = self.embeddings.shape[1]
            except Exception:
                self.embeddings = None
        if self.meta_path.exists():
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                self.embedding_dim = meta.get("embedding_dim", self.embedding_dim)
            except Exception:
                pass

    def _persist(self):
        try:
            self.docs_path.write_text(json.dumps(self.documents, ensure_ascii=False, indent=2), encoding="utf-8")
            if self.embeddings is not None:
                np.save(self.emb_path, self.embeddings)
            meta = {"embedding_dim": self.embedding_dim, "doc_count": len(self.documents)}
            self.meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass  # swallow persistence errors for now

    # ---- Embedding strategies ----
    def _embed_fast(self, texts: List[str]) -> np.ndarray:
        vectors: List[List[float]] = []
        for emb in self._embedder.embed(texts):  # type: ignore
            vectors.append(emb)
        return np.array(vectors, dtype=np.float32)

    @staticmethod
    def _embed_hash(texts: List[str], dim: int = 384) -> np.ndarray:
        # Very simple hashing vectorizer (bag-of-words hashed) for fallback
        vecs = np.zeros((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for token in t.lower().split():
                h = hash(token) % dim
                vecs[i, h] += 1.0
            norm = np.linalg.norm(vecs[i])
            if norm > 0:
                vecs[i] /= norm
        return vecs

    def embed(self, texts: List[str]) -> np.ndarray:
        if self._embedder is not None:
            try:
                embs = self._embed_fast(texts)
                if self.embedding_dim is None:
                    self.embedding_dim = embs.shape[1]
                return embs
            except Exception:
                pass
        # fallback
        if self.embedding_dim is None:
            self.embedding_dim = 384
        return self._embed_hash(texts, self.embedding_dim)

    # ---- CRUD ----
    def add_document(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not content or not content.strip():
            raise ValueError("content_empty")
        with self._lock:
            doc_id = str(uuid.uuid4())
            meta = metadata or {}
            record = {"id": doc_id, "content": content.strip(), "metadata": meta}
            new_emb = self.embed([record["content"]])  # shape (1, D)
            if self.embeddings is None:
                self.embeddings = new_emb
            else:
                self.embeddings = np.vstack([self.embeddings, new_emb])
            self.documents.append(record)
            self._persist()
            return {"id": doc_id, "metadata": meta}

    def list_documents(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        subset = self.documents[offset: offset + limit]
        return {"count": len(self.documents), "results": [ {"id": d["id"], "metadata": d["metadata"], "preview": d["content"][:180]} for d in subset ]}

    def similarity_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.documents or self.embeddings is None:
            return []
        q_emb = self.embed([query])[0]
        # cosine similarity
        docs_emb = self.embeddings
        norms = np.linalg.norm(docs_emb, axis=1) * (np.linalg.norm(q_emb) + 1e-9)
        sims = (docs_emb @ q_emb) / (norms + 1e-9)
        ranked = np.argsort(-sims)[: top_k]
        results: List[Dict[str, Any]] = []
        for idx in ranked:
            d = self.documents[idx]
            results.append({
                "id": d["id"],
                "score": round(float(sims[idx]), 4),
                "content_snippet": d["content"][:240],
                "metadata": d["metadata"],
            })
        return results

# Singleton accessor
_VECTOR_STORE: Optional[VectorStore] = None

def get_vector_store() -> VectorStore:
    global _VECTOR_STORE
    if _VECTOR_STORE is None:
        _VECTOR_STORE = VectorStore()
    return _VECTOR_STORE
