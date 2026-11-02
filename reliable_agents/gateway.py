"""Allowlisted tool boundary with explicit approval and replay-safe demo writes.

All state here is *in memory*. Replace with durable transaction/idem storage in
a real service. This is not a substitute for authentication or authorization.
"""
from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping
from .contracts import TrustedIdentity


class PolicyError(Exception):
    """A requested operation violates the tool boundary."""


class ApprovalRequired(PolicyError):
    """A side effect has not been approved by trusted application code."""


class IdempotencyConflict(PolicyError):
    """An idempotency key was reused with different arguments."""


Handler = Callable[[dict[str, Any], TrustedIdentity], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Handler
    side_effect: bool = False


class ToolGateway:
    def __init__(self, specs: list[ToolSpec]) -> None:
        if len({s.name for s in specs}) != len(specs):
            raise ValueError("Duplicate tool names")
        self._tools = {s.name: s for s in specs}
        # Keys include tenant and actor; values store both request fingerprint and result.
        self._completed: dict[tuple[str, str, str, str], tuple[str, dict[str, Any]]] = {}

    def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        identity: TrustedIdentity,
        *,
        approved: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(identity, TrustedIdentity):
            raise PolicyError("Identity must be supplied by trusted application code")
        if name not in self._tools:
            raise PolicyError(f"Tool not allowed: {name}")
        if not isinstance(arguments, Mapping):
            raise PolicyError("Tool arguments must be a mapping")
        spec = self._tools[name]
        if spec.side_effect and not approved:
            raise ApprovalRequired(f"Approval required for: {name}")
        if spec.side_effect and (not idempotency_key or not idempotency_key.strip()):
            raise PolicyError("Idempotency key required for side effects")
        # Normalize to JSON: prevents mutable/non-serializable input from bypassing matching.
        try:
            normalized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), allow_nan=False)
            safe_arguments = json.loads(normalized)
            if not isinstance(safe_arguments, dict):
                raise ValueError("Tool arguments must be an object")
        except (TypeError, ValueError) as exc:
            raise PolicyError("Arguments must be a JSON object") from exc
        if spec.side_effect:
            replay_key = (identity.tenant_id, identity.actor_id, name, idempotency_key)
            prior = self._completed.get(replay_key)
            if prior is not None:
                fingerprint, result = prior
                if fingerprint != normalized:
                    raise IdempotencyConflict("Different arguments for the same key")
                return dict(result)
        result = spec.handler(safe_arguments, identity)
        if not isinstance(result, dict):
            raise TypeError("Tool handler must return a dictionary")
        if spec.side_effect:
            self._completed[replay_key] = (normalized, dict(result))
        return dict(result)
