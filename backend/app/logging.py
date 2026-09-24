import json
import logging
import time

logger = logging.getLogger("drive")


def event(name: str, call_id: str | None = None, **fields):
    # Only explicitly selected metadata; never exception messages, request bodies, or transcripts.
    logger.info(json.dumps({"event": name, "time": time.time(), "call_id": call_id, **fields}))
