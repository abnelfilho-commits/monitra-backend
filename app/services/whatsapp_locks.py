"""Transaction-scoped PostgreSQL coordination. Serialization is NOT identity.

Callers must declare the entire advisory plan before canonical row locks. This
module does not commit, retry, select conversations or authorize communication.
Existing row-lock helpers (including NO KEY UPDATE) remain authoritative.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from enum import IntEnum
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


class Phase(IntEnum):
    OPERATION = 10
    TRANSPORT = 20
    COMMUNICATION = 30
    CARE_IDENTITY = 40
    CONVERSATION = 50
    PERSISTENCE = 60


class LockOrderError(RuntimeError):
    pass


class LockUnavailable(RuntimeError):
    """Transaction rolled back; caller must not retry an external send."""


@dataclass(frozen=True, order=True)
class Resource:
    phase: Phase
    namespace: str
    parts: tuple

    def key(self):
        # Keep the deployed D9.2 callback/acceptance lock key compatible.
        value = (["invitation-status-v1", *self.parts] if self.namespace == "message"
                 else ["whatsapp-coordination-v1", int(self.phase), self.namespace, *self.parts])
        return int.from_bytes(hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).digest()[:8], "big", signed=True)


def transport(emitter, phone):
    if not isinstance(emitter, str) or not emitter or not isinstance(phone, str) or not re.fullmatch(r"[0-9]+", phone):
        raise ValueError("Invalid transport lock input")
    # Conservative contention only; never expose this as a lookup/identity alias.
    if len(phone) == 13 and phone.startswith("55") and phone[4] == "9":
        phone = phone[:4] + phone[5:]
    return Resource(Phase.TRANSPORT, "recipient", (emitter, phone))


def message(emitter, wamid):
    return Resource(Phase.TRANSPORT, "message", (emitter, wamid))


def acquire(db, resources, *, timeout_ms=None):
    """Sorted, deduplicated plan; reject late additions below the acquired order.

    State belongs to the current root transaction, not the Session lifetime.
    No autoflush may take row/FK locks ahead of this plan. Row locks outside this
    API cannot be detected: adoption requires an audited call-site order.
    """
    plan = sorted(set(resources))
    if timeout_ms is not None and (type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000):
        raise ValueError("Invalid lock timeout")
    if db.get_nested_transaction() is not None:
        raise LockOrderError("Acquire the plan before savepoints")
    if not db.in_transaction():
        db.begin()
    transaction = db.get_transaction()
    prior = db.info.get("whatsapp_lock_plan")
    held = prior[1] if prior and prior[0] is transaction else set()
    additions = [r for r in plan if r not in held]
    if held and additions and min(additions) < max(held):
        db.rollback()
        raise LockOrderError("Late lock acquisition violates declared order")
    previous_timeout = None
    try:
        with db.no_autoflush:
            if timeout_ms is not None:
                previous_timeout = db.scalar(text("SHOW lock_timeout"))
                db.execute(text("SELECT set_config('lock_timeout', :value, true)"), {"value": str(timeout_ms) + "ms"})
            for resource in additions:
                db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": resource.key()})
            if previous_timeout is not None:
                db.execute(text("SELECT set_config('lock_timeout', :value, true)"), {"value": previous_timeout})
        db.info["whatsapp_lock_plan"] = (transaction, held | set(plan))
    except DBAPIError as exc:
        code = getattr(exc.orig, "pgcode", None)
        db.rollback()
        if code in ("40P01", "55P03", "57014"):
            raise LockUnavailable("WhatsApp lock unavailable; transaction rolled back; no retry") from None
        raise
