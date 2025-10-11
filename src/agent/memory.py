import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
from dataclasses import dataclass, asdict

from src.config import get_settings

@dataclass
class MemoryItem:
    id: str
    ts: float
    type: str  # tool_result | summary | user_goal
    importance: float  # 0-1
    content: str
    metadata: Dict[str, Any]

class MemoryStore:
    """Lightweight append + prune memory store for Phase 4 / extended in Phase 5."""
    def __init__(self, base: Optional[Path] = None, capacity: Optional[int] = None):
        settings = get_settings()
        self.base = base or settings.memory_dir
        self.capacity = capacity or settings.memory_max_items
        self.base.mkdir(parents=True, exist_ok=True)
        self.file = self.base / "memory.jsonl"
        self._lock = threading.Lock()
        self._items: List[MemoryItem] = []
        self._load()

    def _load(self):
        if not self.file.exists():
            return
        try:
            with self.file.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    self._items.append(MemoryItem(**obj))
        except Exception:
            self._items = []

    def _persist_append(self, item: MemoryItem):
        try:
            with self.file.open('a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _prune(self):
        if len(self._items) <= self.capacity:
            return
        # simple importance + recency ranking
        ranked = sorted(self._items, key=lambda x: (x.importance, x.ts), reverse=True)
        keep = ranked[: self.capacity]
        self._items = keep
        # rewrite file
        try:
            with self.file.open('w', encoding='utf-8') as f:
                for it in self._items:
                    f.write(json.dumps(asdict(it), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def add(self, item: MemoryItem):
        with self._lock:
            self._items.append(item)
            self._persist_append(item)
            self._prune()

    def add_tool_result(self, tool_name: str, result: Dict[str, Any], importance: float = 0.4, goal: Optional[str] = None):
        snippet = json.dumps(result, ensure_ascii=False)[:400]
        self.add(MemoryItem(
            id=f"mem_{int(time.time()*1000)}",
            ts=time.time(),
            type="tool_result",
            importance=importance,
            content=snippet,
            metadata={"tool": tool_name, "goal": goal}
        ))

    def add_summary(self, text: str, importance: float = 0.6, goal: Optional[str] = None):
        self.add(MemoryItem(
            id=f"mem_{int(time.time()*1000)}",
            ts=time.time(),
            type="summary",
            importance=importance,
            content=text[:600],
            metadata={"goal": goal}
        ))

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return [asdict(it) for it in sorted(self._items, key=lambda x: x.ts, reverse=True)[:limit]]

    def query(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        k = keyword.lower()
        matches = [it for it in self._items if k in it.content.lower() or any(k in str(v).lower() for v in it.metadata.values())]
        return [asdict(it) for it in sorted(matches, key=lambda x: (x.importance, x.ts), reverse=True)[:limit]]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._items)
            if not self._items:
                return {"total_items": 0, "avg_importance": 0, "type_breakdown": {}, "last_added_ts": None}
            avg_importance = sum(it.importance for it in self._items) / total
            breakdown = {}
            for it in self._items:
                breakdown[it.type] = breakdown.get(it.type, 0) + 1
            last_ts = max(it.ts for it in self._items)
            return {"total_items": total, "avg_importance": round(avg_importance, 3), "type_breakdown": breakdown, "last_added_ts": last_ts}

    def select_relevant(self, goal: str, limit: int, max_chars: int, half_life_hours: float) -> List[Dict[str, Any]]:
        """Heuristic relevance ranking: type weight * recency decay * goal overlap."""
        now = time.time()
        goal_tokens = {t.lower() for t in goal.split() if len(t) > 3}
        scored = []
        for it in self._items:
            age_hours = (now - it.ts) / 3600.0
            decay = 0.5 ** (age_hours / max(half_life_hours, 1e-3))
            type_weight = 1.3 if it.type == 'summary' else 1.0
            overlap = 1.0 + 0.4 * sum(1 for tok in goal_tokens if tok in it.content.lower())
            dynamic_score = it.importance * type_weight * decay * overlap
            scored.append((dynamic_score, it))
        ranked = [it for _, it in sorted(scored, key=lambda x: x[0], reverse=True)[:limit]]
        assembled = []
        used_chars = 0
        for it in ranked:
            snippet = it.content[:200]
            if used_chars + len(snippet) > max_chars:
                break
            used_chars += len(snippet)
            assembled.append({
                "id": it.id,
                "type": it.type,
                "importance": it.importance,
                "snippet": snippet,
                "goal": it.metadata.get('goal')
            })
        return assembled

# Singleton accessor
_MEMORY: Optional[MemoryStore] = None

def get_memory() -> MemoryStore:
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = MemoryStore()
    return _MEMORY
