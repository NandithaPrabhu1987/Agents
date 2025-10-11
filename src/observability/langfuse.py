from typing import Optional, Any
from src.config import get_settings

try:
    from langfuse import Langfuse  # type: ignore
except Exception:  # pragma: no cover
    Langfuse = None  # type: ignore

import logging
logger = logging.getLogger(__name__)

_singleton: Optional[Any] = None


def get_langfuse() -> Optional[Any]:
    global _singleton
    if _singleton is not None:
        return _singleton
    if Langfuse is None:
        logger.debug("Langfuse SDK not installed; observability disabled")
        return None
    s = get_settings()
    if not (s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key):
        logger.debug("Langfuse env not fully set; observability disabled")
        return None
    try:
        _singleton = Langfuse(host=s.langfuse_host, public_key=s.langfuse_public_key, secret_key=s.langfuse_secret_key)  # type: ignore
    except Exception as e:
        logger.error(f"Langfuse init failed: {e}")
        _singleton = None
    return _singleton


def start_span(name: str, *, input=None, metadata: Optional[dict] = None):
    lf = get_langfuse()
    if not lf:
        return None
    try:
        # Attach to current span context established by middleware
        return lf.start_span(name=name, input=input, metadata=metadata or {})
    except Exception as e:
        logger.error(f"Langfuse start_span failed: {e}")
        return None


def end_span(span: Any, *, output=None, error: Optional[str] = None, metadata: Optional[dict] = None) -> None:
    if not span:
        return
    try:
        if error:
            span.end(level="ERROR", status_message=error)
        else:
            span.end(output=output, metadata=metadata or {})
    except Exception as e:
        logger.debug(f"Langfuse end_span warn: {e}")


def flush():
    lf = get_langfuse()
    if not lf:
        return
    try:
        lf.flush()
    except Exception as e:
        logger.debug(f"Langfuse flush warn: {e}")
