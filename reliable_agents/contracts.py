"""Explicit context contracts; user/tenant identity must come from trusted middleware."""

from dataclasses import dataclass
from typing import Mapping, Any


SENSITIVE_KEYS = {"token", "password", "api_key", "secret", "authorization", "access_token"}


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in SENSITIVE_KEYS or _contains_sensitive_key(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


@dataclass(frozen=True)
class TrustedIdentity:
    actor_id: str
    tenant_id: str

    def __post_init__(self) -> None:
        if not self.actor_id.strip() or not self.tenant_id.strip():
            raise ValueError("Trusted identity fields must not be empty")


@dataclass(frozen=True)
class Handoff:
    """Serializable-ish, validated agent handoff; never transfer credentials."""
    task_id: str
    target: str
    intent: str
    selected_id: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not all((self.task_id.strip(), self.target.strip(), self.intent.strip(), self.selected_id.strip())):
            raise ValueError("Handoff requires task_id, target, intent, and selected_id")
        if _contains_sensitive_key(self.metadata):
            raise ValueError("Secrets must not be transferred in handoff metadata")
