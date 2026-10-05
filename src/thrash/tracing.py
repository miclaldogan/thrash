"""Opt-in, metadata-only tracing. No ambient SDK scope or auto instrumentation.

Only this module creates telemetry payloads. Unknown fields are discarded again
at the SDK boundary. In particular, exceptions are counted, never serialized.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import atexit
import math
import os
import time
import uuid

OPERATIONS = frozenset({
    'thrash.page_fault', 'thrash.context.collect', 'thrash.privacy.filter',
    'thrash.process_image.load', 'thrash.gemma.resume', 'thrash.schema.validate',
    'thrash.drift.detect', 'thrash.restore.render', 'thrash.process.snapshot',
})
NUMBERS = frozenset({
    'duration_ms', 'inference_ms', 'model_load_ms', 'prompt_eval_ms', 'generation_ms', 'retry_count', 'decision_count', 'completed_count',
    'unresolved_count', 'drift_count', 'snapshot_age_hours', 'context_file_count',
    'context_switch_count', 'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens',
})
BOOLEANS = frozenset({'schema_valid', 'fallback_used', 'failed'})
ENUMS = {
    'model_family': {'gemma'}, 'gen_ai.system': {'ollama'},
    'gen_ai.operation.name': {'chat', 'invoke_agent'},
    'gen_ai.agent.name': {'THRASH semantic restoration'},
    'gen_ai.request.model': {'gemma3:4b', 'gemma3:12b', 'gemma3:27b', 'gemma3:1b', 'gemma4:e4b-it-qat'},
    'thrash_state': {'NORMAL', 'PRESSURE', 'THRASHING', 'PANIC'},
}
_current = ContextVar('thrash_trace', default=None)
_parent = ContextVar('thrash_span', default=None)
_client = None


def metrics(values):
    clean = {}
    for key, value in values.items():
        if key in NUMBERS and type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e15:
            clean[key] = value
        elif key in BOOLEANS and type(value) is bool:
            clean[key] = value
        elif key in ENUMS and type(value) is str and value in ENUMS[key]:
            clean[key] = value
    return clean


def _op(name):
    return 'gen_ai.invoke_agent' if name == 'thrash.page_fault' else ('gen_ai.request' if name == 'thrash.gemma.resume' else name)


def _hex(value, size):
    return isinstance(value, str) and len(value) == size and all(c in '0123456789abcdef' for c in value)


def scrub_transaction(event, hint=None):
    """Rebuild, don't redact: no SDK-added host, user, request, scope or baggage."""
    try:
        name = event['transaction']
        if name not in OPERATIONS or event.get('type') != 'transaction':
            return None
        trace = event['contexts']['trace']
        if not _hex(trace['trace_id'], 32) or not _hex(trace['span_id'], 16):
            return None
        def timing(obj):
            return {k: obj[k] for k in ('start_timestamp', 'timestamp')
                    if type(obj.get(k)) in (float, int) and math.isfinite(obj[k])}
        spans = []
        for s in event.get('spans', []):
            n = s.get('description')
            if n not in OPERATIONS or not _hex(s.get('span_id'), 16) or not _hex(s.get('parent_span_id'), 16):
                continue
            spans.append(dict(description=n, op=_op(n), trace_id=trace['trace_id'],
                              span_id=s['span_id'], parent_span_id=s['parent_span_id'],
                              data=metrics(s.get('data', {})), **timing(s)))
        clean = dict(type='transaction', transaction=name, platform='python',
                     contexts={'trace': {'trace_id': trace['trace_id'], 'span_id': trace['span_id'],
                               'op': _op(name), 'data': metrics(trace.get('data', {}))}},
                     spans=spans, **timing(event))
        if _hex(event.get('event_id'),32): clean['event_id'] = event['event_id']
        return clean
    except Exception:
        return None


def _get_client():
    global _client
    if os.environ.get('THRASH_SENTRY') != '1' or not os.environ.get('SENTRY_DSN'):
        return None
    if _client is None:
        try:
            import sentry_sdk
            _client = sentry_sdk.Client(
                dsn=os.environ['SENTRY_DSN'], default_integrations=False,
                auto_enabling_integrations=False, send_default_pii=False,
                traces_sample_rate=1.0, sample_rate=0.0, send_client_reports=False,
                auto_session_tracking=False, enable_logs=False,
                environment='local-opt-in', release='thrash', server_name='',
                before_send=lambda event, hint: None,
                before_send_transaction=scrub_transaction,
            )
            atexit.register(flush)
        except Exception:
            return None
    return _client


@contextmanager
def span(name, **values):
    """Yield a numeric metric bag; SDK failures cannot affect kernel behavior."""
    bag = metrics(values)
    parent_trace = _current.get()
    client = None
    if parent_trace is None:
        try: client = _get_client()
        except Exception: pass
        if client is None:
            yield bag
            return
    if name not in OPERATIONS:
        yield bag
        return
    root = parent_trace is None
    trace = parent_trace or {'trace_id': uuid.uuid4().hex, 'spans': []}
    sid = uuid.uuid4().hex[:16]
    record = dict(description=name, op=_op(name), trace_id=trace['trace_id'],
                  span_id=sid, parent_span_id=_parent.get(), start_timestamp=time.time(), data=bag)
    t0 = time.perf_counter()
    trace_token = _current.set(trace)
    parent_token = _parent.set(sid)
    try:
        yield bag
    except BaseException:
        bag['failed'] = True
        raise
    finally:
        record['timestamp'] = time.time()
        bag['duration_ms'] = round((time.perf_counter()-t0)*1000, 3)
        record['data'] = metrics(bag)
        _parent.reset(parent_token)
        _current.reset(trace_token)
        try:
            if root:
                event = dict(type='transaction', transaction=name,
                    start_timestamp=record['start_timestamp'], timestamp=record['timestamp'],
                    contexts={'trace': {'trace_id': trace['trace_id'], 'span_id': sid,
                                       'op': _op(name), 'data': record['data']}}, spans=trace['spans'])
                # Private Scope avoids global user, tags, attachments or breadcrumbs.
                from sentry_sdk import Scope
                client.capture_event(scrub_transaction(event), scope=Scope())
            else:
                trace['spans'].append(record)
        except Exception:
            pass


def traced(name):
    def decorate(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            with span(name) as data:
                result = fn(*args, **kwargs)
                try:
                    if name == "thrash.page_fault":
                        data.update(fallback_used=bool(result.error and result.image), failed=bool(result.error))
                        if result.age_s is not None:
                            data["snapshot_age_hours"] = result.age_s / 3600
                except Exception:
                    pass
                return result
        return call
    return decorate


def flush():
    """Explicit CLI/demo flush; normal kernel operations never wait on the network."""
    try:
        if _client is not None: _client.flush(timeout=2)
    except Exception:
        pass
