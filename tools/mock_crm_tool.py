"""Mock CRM lookup tool — read-only, no approval required."""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MOCK_CRM_DATA = {
    "cust-001": {
        "id": "cust-001",
        "name": "Alice Chen",
        "email": "alice@customer.example.com",
        "plan": "Enterprise",
        "arr": 48000,
        "status": "active",
    },
    "cust-002": {
        "id": "cust-002",
        "name": "Bob Patel",
        "email": "bob@startup.example.com",
        "plan": "Starter",
        "arr": 2400,
        "status": "active",
    },
    "cust-003": {
        "id": "cust-003",
        "name": "Carol Watson",
        "email": "carol@enterprise.example.com",
        "plan": "Professional",
        "arr": 18000,
        "status": "churned",
    },
}


def lookup_customer(
    customer_id: Optional[str] = None,
    email: Optional[str] = None,
) -> dict:
    """Look up a customer by ID or email."""
    if customer_id:
        record = MOCK_CRM_DATA.get(customer_id)
        if record:
            logger.info("CRM lookup: customer_id=%s found", customer_id)
            return {"found": True, "record": record}
        return {"found": False, "customer_id": customer_id}

    if email:
        for record in MOCK_CRM_DATA.values():
            if record["email"].lower() == email.lower():
                logger.info("CRM lookup: email=%s found", email)
                return {"found": True, "record": record}
        return {"found": False, "email": email}

    raise ValueError("Either customer_id or email must be provided")
