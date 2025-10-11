import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from src.config import get_settings
import logging

logger = logging.getLogger(__name__)
_settings = get_settings()
AUDIT_BASE: Path = _settings.audit_base
AUDIT_BASE.mkdir(parents=True, exist_ok=True)

def context_digest(context: Dict[str, Any]) -> str:
    try:
        packed = json.dumps(context, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(packed.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "digest_err"

def write_audit(correlation_id: str, payload: Dict[str, Any]):
    try:
        day_dir = AUDIT_BASE / datetime.utcnow().strftime('%Y-%m-%d')
        day_dir.mkdir(parents=True, exist_ok=True)
        with (day_dir / f"{correlation_id}.json").open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write audit record {correlation_id}: {e}")
