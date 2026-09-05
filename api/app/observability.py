"""Structured logging for context operations (phase-1-requirements §19).

Logs the fields needed to debug an ingestion failure and nothing more. Context
payloads are never logged — only identifiers, the operation, its outcome and an
error type.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("forge.context")


def log_context_op(
    *,
    operation: str,
    status: str,
    organization_id: str | None = None,
    feature_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    error_type: str | None = None,
    **extra: Any,
) -> None:
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "status": status,
        "organization_id": organization_id,
        "feature_id": feature_id,
        "session_id": session_id,
        "user_id": user_id,
    }
    if error_type:
        record["error_type"] = error_type
    # Counts and flags only; never payload content.
    record.update({k: v for k, v in extra.items() if isinstance(v, (int, float, bool, str, type(None)))})

    line = json.dumps({k: v for k, v in record.items() if v is not None})
    if status in {"failed", "rejected"}:
        logger.warning(line)
    else:
        logger.info(line)
