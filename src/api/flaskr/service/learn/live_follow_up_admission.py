"""Bounded browser-direct credential rotation without pretending to revoke tokens.

Redis is the admission authority, not a media proxy. Logical ownership may move,
but every disclosed or uncertain credential continues consuming risk capacity.
The guarded Redis instance must use noeviction. Privileged same-process RESTORE
is an operationally prohibited action unless admission is disabled and drained.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flaskr.util.datetime import to_utc_iso
from redis import ConnectionPool, Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from .live_follow_up_capacity import (
    LiveFollowUpCapacityLease,
    LiveFollowUpCapacityUnavailableError,
    _key_prefix,
    _lease_keys,
    _require_redis,
    default_live_follow_up_worker_id,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

_ERROR_UNAVAILABLE = "admission_unavailable"

# INFO and TIME are evaluated inside the same transaction as reservations. A
# preflight outside Lua would leave a restart/restore race before admission.
_RECOVERY_GUARD = r"""
local server = redis.call('INFO', 'server')
local memory = redis.call('INFO', 'memory')
local generation = string.match(server, 'run_id:([^\r\n]+)')
local policy = string.match(memory, 'maxmemory_policy:([^\r\n]+)')
if not generation or policy ~= 'noeviction' then return rejected('admission_unavailable') end
local marker = read(accounting_key)
if not marker or marker.generation ~= generation then
    marker = {generation=generation, safe_after_ms=now + 900000}
    redis.call('SET', accounting_key, cjson.encode(marker))
end
if marker.safe_after_ms > now then return rejected('admission_unavailable', marker.safe_after_ms-now) end
"""

_SCRIPT_HELPERS = r"""
local args = cjson.decode(ARGV[1])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local function read(key)
    local raw = redis.call('GET', key)
    if not raw then return nil end
    local ok, value = pcall(cjson.decode, raw)
    if not ok or type(value) ~= 'table' then error('invalid admission record') end
    return value
end
local function write(key, value, expiry)
    redis.call('SET', key, cjson.encode(value), 'PXAT', math.ceil(expiry))
end
local function rejected(code, delay)
    local value = {operation_status='rejected', error_code=code,
        request_bid=args.request_bid, rotation_enabled=args.rotation_enabled,
        server_time_ms=now}
    if delay and delay > 0 then value.retry_after_ms = math.ceil(delay) end
    return cjson.encode(value)
end
"""

_READINESS_SCRIPT = (
    _SCRIPT_HELPERS
    + "local accounting_key = KEYS[1]\n"
    + _RECOVERY_GUARD
    + "return cjson.encode({ready=true})"
)

_ADMISSION_SCRIPT = (
    _SCRIPT_HELPERS
    + r"""
local function owner_matches(head, op)
    return head and head.session_bid == op.session_bid
        and head.admission_revision == op.admission_revision
end
local function public(op, head)
    local state = op.operation_status
    if state == 'pending' and op.deadline_ms <= now then state = 'cancelled' end
    local result = {request_bid=args.request_bid, operation_status=state,
        session_bid=op.session_bid, admission_revision=op.admission_revision,
        ownership_current=owner_matches(head, op) or false,
        rotation_enabled=args.rotation_enabled}
    if state == 'pending' then result.retry_after_ms = math.min(500, op.deadline_ms-now) end
    return result
end
local head = read(KEYS[4])
local op = read(KEYS[5])

if args.action == 'owner' then
    if head and head.identity ~= args.identity then return rejected('ownership_conflict') end
    local state = head and head.state or 'missing'
    if state == 'pending' and head.deadline_ms <= now then state = 'retired' end
    local result = {operation_status=state, rotation_enabled=args.rotation_enabled,
        admission_revision=head and head.admission_revision or cjson.null}
    if state == 'pending' then result.retry_after_ms = math.min(500, head.deadline_ms-now) end
    return cjson.encode(result)
end

if args.action == 'receipt' then
    local receipt = read(KEYS[11])
    if not receipt or receipt.identity ~= args.identity then return cjson.encode({found=false}) end
    return cjson.encode({found=true, session_bid=receipt.session_bid,
        admission_revision=receipt.admission_revision,
        last_committed_index=receipt.last_committed_index})
end

if args.action == 'status' then
    if not op then
        return cjson.encode({request_bid=args.request_bid, operation_status='missing',
            ownership_current=false, rotation_enabled=args.rotation_enabled})
    end
    if op.target ~= args.target then return rejected('operation_conflict') end
    return cjson.encode(public(op, head))
end

if args.action == 'current' then
    return cjson.encode({current=head ~= nil and head.session_bid == args.session_bid
        and head.admission_revision == args.admission_revision
        and head.state == 'issued' and head.expires_at_ms > now or false,
        server_time_ms=now})
end

if args.action == 'retire' then
    local receipt = read(KEYS[11])
    if receipt and receipt.identity ~= args.identity then return rejected('ownership_conflict') end
    if not receipt then
        receipt = {session_bid=args.session_bid, admission_revision=args.admission_revision,
            identity=args.identity, target=args.target, last_committed_index=args.last_committed_index,
            expires_at_ms=args.expires_at_ms}
    else
        receipt.last_committed_index = math.max(receipt.last_committed_index or 0, args.last_committed_index)
    end
    if args.expires_at_ms + 300000 > now then write(KEYS[11], receipt, args.expires_at_ms + 300000) end
    if head and head.session_bid == args.session_bid
        and head.admission_revision == args.admission_revision then
        head.state = 'retired'
        redis.call('ZREM', KEYS[12], KEYS[4])
        write(KEYS[4], head, math.max(head.expires_at_ms + 300000, now + 1200000))
        if op and owner_matches(head, op) and op.operation_status == 'pending' then
            op.operation_status = 'cancelled'
            write(KEYS[5], op, now + 1200000)
        end
    end
    return cjson.encode({session_bid=args.session_bid, admission_revision=args.admission_revision})
end

if args.action == 'complete' or args.action == 'fail' then
    if not op or op.target ~= args.target or not owner_matches(head, op)
        or op.admission_revision ~= args.admission_revision then return cjson.encode({committed=false}) end
    if args.action == 'complete' then
        if op.operation_status ~= 'pending' or head.state ~= 'pending'
            or op.deadline_ms <= now then return cjson.encode({committed=false}) end
        if redis.call('EXISTS', KEYS[10]) == 1 then return cjson.encode({committed=false}) end
        redis.call('SET', KEYS[10], args.session_payload, 'PXAT', op.expires_at_ms + 30000)
        op.operation_status = 'issued'
        head.state = 'issued'
        redis.call('ZADD', KEYS[12], op.expires_at_ms, KEYS[4])
    else
        -- Only the originating worker can prove that its response was never
        -- disclosed. A timed-out/crashed worker leaves its reservation intact.
        if op.operation_status ~= 'pending' then return cjson.encode({committed=false}) end
        op.operation_status = 'failed'
        head.state = 'retired'
        redis.call('ZREM', KEYS[12], KEYS[4])
        if args.undisclosed then
            redis.call('ZREM', KEYS[1], op.lease_id)
            redis.call('ZREM', KEYS[2], op.lease_id)
            redis.call('ZREM', KEYS[3], op.lease_id)
            if redis.call('GET', KEYS[9]) == op.lease_id then redis.call('DEL', KEYS[9]) end
        end
    end
    write(KEYS[5], op, now + 1200000)
    write(KEYS[4], head, math.max(op.expires_at_ms + 300000, now + 1200000))
    return cjson.encode({committed=true})
end

-- An existing operation is a lookup, not another mint attempt. UUID age only
-- gates creation; even expired UUIDs can inspect their retained operation.
if op then
    if op.target ~= args.target then return rejected('operation_conflict') end
    return cjson.encode(public(op, head))
end
if args.request_time_ms < now - 120000 or args.request_time_ms > now + 30000 then
    return rejected('stale_request')
end

local accounting_key = KEYS[8]
"""
    + _RECOVERY_GUARD
    + r"""

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now/1000)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now/1000)
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now/1000)
redis.call('ZREMRANGEBYSCORE', KEYS[6], '-inf', now-60000)
redis.call('ZREMRANGEBYSCORE', KEYS[7], '-inf', now-60000)
redis.call('ZREMRANGEBYSCORE', KEYS[12], '-inf', now)

local predecessor = args.replace_session_bid ~= ''
if args.takeover then
    if not args.rotation_enabled or args.legacy then return rejected('admission_unavailable') end
    local revision = head and head.admission_revision or ''
    if revision ~= args.expected_admission_revision
        or (head and head.identity ~= args.identity) then return rejected('ownership_conflict') end
    if head and head.state == 'pending' and head.deadline_ms > now then
        return rejected('pending', math.min(500, head.deadline_ms-now))
    end
elseif predecessor then
    if not head or head.session_bid ~= args.replace_session_bid
        or head.admission_revision ~= args.expected_admission_revision
        or head.identity ~= args.identity then return rejected('ownership_conflict') end
    if head.state == 'pending' and head.deadline_ms > now then return rejected('ownership_conflict') end
    -- A retired head survives a positively undisclosed failure even though its
    -- risk was rolled back. The credential ledger below, not the head's former
    -- deadline, enforces the one-credential limit when rotation is disabled.
elseif head and head.expires_at_ms > now and head.state ~= 'retired'
    and not (head.state == 'pending' and head.deadline_ms <= now) then
    return rejected('ownership_conflict')
end

local delay = 0
local function quota(key, limit, multiplier, window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
        local item = redis.call('ZRANGE', key, count-limit, count-limit, 'WITHSCORES')
        delay = math.max(delay, tonumber(item[2])*multiplier + window-now)
    end
end
quota(KEYS[1], args.rotation_enabled and 96 or 24, 1000, 0)
if not args.rotation_enabled then quota(KEYS[2], 6, 1000, 0) end
quota(KEYS[3], args.rotation_enabled and not args.legacy and 8 or 1, 1000, 0)
if not redis.call('ZSCORE', KEYS[12], KEYS[4]) then quota(KEYS[12], 24, 1, 0) end
quota(KEYS[6], 4, 1, 60000)
quota(KEYS[7], 24, 1, 60000)
    local legacy_lease = redis.call('GET', KEYS[9])
if legacy_lease and not redis.call('ZSCORE', KEYS[3], legacy_lease) then
    local remaining = redis.call('PTTL', KEYS[9])
    if remaining < 0 then return rejected('admission_unavailable') end
    delay = math.max(delay, remaining)
end
if delay > 0 then return rejected('capacity_exceeded', delay) end

local expiry = now + 900000
op = {request_bid=args.request_bid, session_bid=args.session_bid,
    admission_revision=args.admission_revision, operation_status='pending',
    target=args.target, identity=args.identity, lease_id=args.lease_id,
    issued_at_ms=now, expires_at_ms=expiry, deadline_ms=now+15000}
head = {session_bid=args.session_bid, admission_revision=args.admission_revision,
    identity=args.identity, state='pending', deadline_ms=op.deadline_ms,
    expires_at_ms=expiry}
redis.call('ZADD', KEYS[1], expiry/1000, args.lease_id)
redis.call('ZADD', KEYS[2], expiry/1000, args.lease_id)
redis.call('ZADD', KEYS[3], expiry/1000, args.lease_id)
-- Pending ownership lasts only through provisioning; uncertain credentials
-- remain in the independent risk ledgers until their real expiry.
redis.call('ZADD', KEYS[12], op.deadline_ms, KEYS[4])
-- Retired workers receive no future admissions to prune their ledger. Preserve
-- its longest lease even if the Redis clock has moved backwards since issuance.
local worker_last = redis.call('ZRANGE', KEYS[2], -1, -1, 'WITHSCORES')
redis.call('PEXPIREAT', KEYS[2], math.ceil(tonumber(worker_last[2])*1000))
redis.call('PEXPIREAT', KEYS[3], expiry)
-- Keep the old user STRING as a compatibility guard, never as the V2 ledger.
redis.call('SET', KEYS[9], args.lease_id, 'PXAT', expiry)
redis.call('ZADD', KEYS[6], now, args.request_bid)
redis.call('ZADD', KEYS[7], now, args.identity .. ':' .. args.request_bid)
redis.call('PEXPIRE', KEYS[6], 60001)
redis.call('PEXPIRE', KEYS[7], 60001)
write(KEYS[5], op, now+1200000)
write(KEYS[4], head, now+1200000)
local result = public(op, head)
result.reserved = true
result.issued_at_ms = now
result.deadline_ms = op.deadline_ms
return cjson.encode(result)
"""
)


@dataclass(frozen=True)
class AdmissionRequest:
    """Immutable, non-content request fields bound to one client operation."""

    request_bid: str
    user_bid: str
    origin: str
    shifu_bid: str
    outline_bid: str
    anchor_element_bid: str
    preview_mode: bool
    learning_mode: str
    surface: str
    replace_session_bid: str = ""
    expected_admission_revision: str = ""
    takeover: bool = False


@dataclass(frozen=True)
class AdmissionResult:
    """Non-secret admission response and worker-private provisioning claim."""

    data: dict[str, object]
    lease: LiveFollowUpCapacityLease | None = None
    issued_at_ms: int = 0
    deadline_ms: int = 0


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _identity(user_bid: str, origin: str) -> str:
    return _digest(json.dumps([user_bid, origin], separators=(",", ":")))


def _target(request: AdmissionRequest) -> str:
    values = asdict(request)
    values.pop("request_bid")
    # Preserve existing operation hashes across compatible worker upgrades.
    if not values["takeover"]:
        values.pop("takeover")
    return _digest(json.dumps(values, sort_keys=True, separators=(",", ":")))


def _keys(
    app: Flask, request: AdmissionRequest, *, worker_id: str, session_bid: str
) -> tuple[str, ...]:
    global_key, worker_key, legacy_user_key = _lease_keys(
        app, user_bid=request.user_bid, worker_id=worker_id
    )
    prefix = _key_prefix(app)
    user = _digest(request.user_bid)
    session_prefix = prefix.removesuffix(":capacity")
    return (
        global_key,
        worker_key,
        f"{prefix}:v2:user:{user}",
        f"{prefix}:v2:owner:{user}",
        f"{prefix}:v2:operation:{_digest(request.user_bid + ':' + request.request_bid)}",
        f"{prefix}:v2:rate:user:{user}",
        f"{prefix}:v2:rate:global",
        f"{prefix}:v2:accounting",
        legacy_user_key,
        f"{session_prefix}:session:{_digest(session_bid)}",
        f"{prefix}:v2:receipt:{_digest(session_bid)}",
        f"{prefix}:v3:active",
    )


def _run(
    app: Flask,
    request: AdmissionRequest,
    *,
    action: str,
    worker_id: str = "control-plane",
    session_bid: str = "",
    **values: object,
) -> dict[str, object]:
    args = {
        "action": action,
        "request_bid": request.request_bid,
        "target": _target(request),
        "identity": _identity(request.user_bid, request.origin),
        "session_bid": session_bid,
        "rotation_enabled": False,
        "takeover": request.takeover,
        **values,
    }
    try:
        keys = _keys(app, request, worker_id=worker_id, session_bid=session_bid)
        result = _require_redis().eval(
            _ADMISSION_SCRIPT, len(keys), *keys, json.dumps(args)
        )
        data = json.loads(result)
        if isinstance(data, dict) and "server_time_ms" in data:
            data["server_time"] = to_utc_iso(
                datetime.fromtimestamp(data.pop("server_time_ms") / 1000, tz=UTC)
            )
    except LiveFollowUpCapacityUnavailableError:
        raise
    except Exception as exc:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_UNAVAILABLE) from exc
    if not isinstance(data, dict):
        raise LiveFollowUpCapacityUnavailableError(_ERROR_UNAVAILABLE)
    return data


def admission_time() -> float:
    """Read the same trusted clock for control-plane expiry admission."""
    try:
        seconds, micros = _require_redis().time()
        return int(seconds) + int(micros) / 1_000_000
    except Exception as exc:
        raise LiveFollowUpCapacityUnavailableError(_ERROR_UNAVAILABLE) from exc


@contextmanager
def live_follow_up_readiness_client() -> Iterator[Redis]:
    """Bound optional readiness/cache I/O without mutating the shared pool."""
    source = _require_redis().connection_pool
    pool = ConnectionPool(
        connection_class=source.connection_class,
        **{
            **source.connection_kwargs,
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry": Retry(NoBackoff(), 0),
            "retry_on_error": [],
        },
    )
    try:
        yield Redis(connection_pool=pool)
    finally:
        pool.disconnect()


def live_follow_up_readiness(
    app: Flask, *, enabled: bool | None = None
) -> dict[str, object]:
    """Initialize/check shared recovery without allocating any credential risk.

    Every worker and readiness probe sees the same Redis-clock deadline. Never
    shorten it or make ordinary HTTP health depend on this optional feature.
    """
    if enabled is None:
        enabled = str(app.config.get("GEMINI_LIVE_ENABLED", False)).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if not enabled:
        return {"status": "disabled"}
    try:
        with live_follow_up_readiness_client() as client:
            result = json.loads(
                client.eval(
                    _READINESS_SCRIPT, 1, f"{_key_prefix(app)}:v2:accounting", "{}"
                )
            )
        if result.get("ready") is True:
            return {"status": "ready"}
        delay = result.get("retry_after_ms")
        if isinstance(delay, (int, float)) and delay > 0:
            return {"status": "warming", "retry_after_ms": min(math.ceil(delay), 30000)}
    except Exception:
        # Do not expose Redis details or prevent normal HTTP startup.
        return {"status": "unavailable", "retry_after_ms": 30000}
    return {"status": "unavailable", "retry_after_ms": 30000}


def request_timestamp_ms(request_bid: str) -> int:
    """Validate a canonical UUIDv7 without trusting its clock for admission."""
    try:
        parsed = uuid.UUID(request_bid)
    except (ValueError, AttributeError) as exc:
        raise ValueError(_ERROR_UNAVAILABLE) from exc
    if parsed.version != 7 or str(parsed) != request_bid:
        raise ValueError(_ERROR_UNAVAILABLE)
    return parsed.int >> 80


def legacy_request_bid() -> str:
    """Create a server-time operation ID for a backward-compatible old client."""
    seconds, micros = _require_redis().time()
    millis = int(seconds) * 1000 + int(micros) // 1000
    value = (
        (millis << 80)
        | (7 << 76)
        | (secrets.randbits(12) << 64)
        | (2 << 62)
        | secrets.randbits(62)
    )
    return str(uuid.UUID(int=value))


def begin_admission(
    app: Flask,
    request: AdmissionRequest,
    *,
    session_bid: str,
    rotation_enabled: bool,
    legacy: bool = False,
    worker_id: str | None = None,
) -> AdmissionResult:
    """Atomically reserve one bounded mint after the Redis recovery guard."""
    resolved_worker = worker_id or default_live_follow_up_worker_id()
    lease = LiveFollowUpCapacityLease(
        secrets.token_urlsafe(32), request.user_bid, resolved_worker
    )
    data = _run(
        app,
        request,
        action="create",
        worker_id=resolved_worker,
        session_bid=session_bid,
        rotation_enabled=rotation_enabled,
        legacy=legacy,
        request_time_ms=request_timestamp_ms(request.request_bid),
        replace_session_bid=request.replace_session_bid,
        expected_admission_revision=request.expected_admission_revision,
        lease_id=lease.lease_id,
        admission_revision=secrets.token_urlsafe(32),
    )
    reserved = data.pop("reserved", False)
    issued_at = int(data.pop("issued_at_ms", 0))
    deadline = int(data.pop("deadline_ms", 0))
    return AdmissionResult(data, lease if reserved else None, issued_at, deadline)


def admission_status(
    app: Flask, request: AdmissionRequest, *, rotation_enabled: bool
) -> dict[str, object]:
    """Read an existing operation, including after UUID mint validity expires."""
    request_timestamp_ms(request.request_bid)
    return _run(app, request, action="status", rotation_enabled=rotation_enabled)


def discover_admission_owner(
    app: Flask, *, user_bid: str, origin: str, rotation_enabled: bool
) -> dict[str, object]:
    """Discover only the authenticated same-Origin owner's non-secret revision."""
    request = AdmissionRequest(
        request_bid="",
        user_bid=user_bid,
        origin=origin,
        shifu_bid="",
        outline_bid="",
        anchor_element_bid="",
        preview_mode=False,
        learning_mode="",
        surface="",
    )
    return _run(app, request, action="owner", rotation_enabled=rotation_enabled)


def complete_admission(
    app: Flask,
    request: AdmissionRequest,
    result: AdmissionResult,
    *,
    session_payload: str,
) -> bool:
    """Publish binding and ready ownership atomically before disclosing a token."""
    if result.lease is None:
        return False
    data = _run(
        app,
        request,
        action="complete",
        worker_id=result.lease.worker_id,
        session_bid=str(result.data["session_bid"]),
        admission_revision=result.data["admission_revision"],
        session_payload=session_payload,
    )
    return data.get("committed") is True


def fail_admission(
    app: Flask,
    request: AdmissionRequest,
    result: AdmissionResult,
    *,
    undisclosed: bool = True,
) -> None:
    """Roll back only an originating worker's positively undisclosed credential."""
    if result.lease is not None:
        _run(
            app,
            request,
            action="fail",
            worker_id=result.lease.worker_id,
            session_bid=str(result.data["session_bid"]),
            admission_revision=result.data["admission_revision"],
            undisclosed=undisclosed,
        )


def current_admission(
    app: Flask, request: AdmissionRequest, *, session_bid: str, admission_revision: str
) -> bool:
    """Check logical ownership; it is not proof of physical upstream revocation."""
    return (
        _run(
            app,
            request,
            action="current",
            session_bid=session_bid,
            admission_revision=admission_revision,
        ).get("current")
        is True
    )


def retire_admission(
    app: Flask,
    request: AdmissionRequest,
    *,
    session_bid: str,
    admission_revision: str,
    expires_at_ms: int,
    last_committed_index: int,
) -> dict[str, object]:
    """Retire only this revision, retaining a receipt without releasing risk."""
    return _run(
        app,
        request,
        action="retire",
        session_bid=session_bid,
        admission_revision=admission_revision,
        expires_at_ms=expires_at_ms,
        last_committed_index=last_committed_index,
    )


def retirement_receipt(
    app: Flask, *, user_bid: str, origin: str, session_bid: str
) -> dict[str, object] | None:
    """Acknowledge previously committed history without extending write access."""
    request = AdmissionRequest(
        "",
        user_bid,
        origin,
        "",
        "",
        "",
        preview_mode=False,
        learning_mode="read",
        surface="read_content",
    )
    data = _run(app, request, action="receipt", session_bid=session_bid)
    return data if data.get("found") is True else None
