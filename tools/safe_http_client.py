"""Safe HTTP client with allowlist enforcement."""
from __future__ import annotations
import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = {
    "api.acme-corp.example.com",
    "status.acme-corp.example.com",
    "postman-echo.com",
    "httpbin.org",
}


def safe_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
) -> dict:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if domain not in ALLOWED_DOMAINS:
        raise PermissionError(
            f"Domain '{domain}' is not in the HTTP allowlist. "
            f"Allowed: {sorted(ALLOWED_DOMAINS)}"
        )

    logger.info("HTTP GET: %s", url)
    resp = httpx.get(url, headers=headers or {}, timeout=timeout, follow_redirects=False)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        return {"status": resp.status_code, "body": resp.json()}
    return {"status": resp.status_code, "body": resp.text[:2000]}
