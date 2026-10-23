"""Durable job admission with per-workspace ownership and isolated execution."""
import base64
import hashlib
import json
import os
import threading
import time
import uuid
from contextvars import copy_context
from .context import owner
from .store import store
from .providers import proxy_request
from .security import encrypt, decrypt
from .results import persist_result, provider_receipt

_lock = threading.RLock()
_slots = threading.BoundedSemaphore(int(os.getenv('EDITOR_JOB_CONCURRENCY', '2')))
_cancelled = {}
_processes = {}


def submit(kind, payload, submission_key):
    identity = owner()
    if kind not in ('provider', 'provider-status', 'gemini', 'cloud', 'mcp', 'export', 'audio-mastering', 'audio-remaster', 'surface-map', 'corridor-key'):
        raise ValueError('Unsupported editor operation.')
    if not submission_key or len(submission_key) > 128:
        raise ValueError('A submission key is required.')
    digest = hashlib.sha256((identity + ':' + submission_key).encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps([kind, payload], sort_keys=True).encode()).hexdigest()
    with _lock:
        existing = store.get('jobs', digest, identity)
        if existing:
            if existing['fingerprint'] != fingerprint:
                raise ValueError('The submission key was already used for a different request.')
            return public_job(existing)
        active = [job for job in store.list('jobs', identity) if job['status'] in ('queued', 'processing')]
        if len(active) >= int(os.getenv('EDITOR_QUEUE_LIMIT', '4')):
            raise ValueError('Your processing queue is full. Wait for a job to finish.')
        if len(_cancelled) >= int(os.getenv('EDITOR_GLOBAL_QUEUE_LIMIT', '32')):
            raise ValueError('The backend processing queue is full. Retry shortly.')
        record = store.put('jobs', digest, identity, {'kind': kind, 'status': 'queued', 'created': time.time(),
                           'progress': 0, 'fingerprint': fingerprint, 'submission_key': submission_key,
                           'encrypted_payload': encrypt(json.dumps(payload), identity, 'job:' + digest),
                           'retryable': kind in ('provider-status', 'export', 'audio-mastering', 'audio-remaster', 'surface-map', 'corridor-key') or
                                        (kind == 'provider' and payload.get('method', 'GET') == 'GET')})
        event = threading.Event()
        _cancelled[digest] = event
        context = copy_context()
        threading.Thread(target=context.run, args=(_execute, digest, identity, kind, payload, event), daemon=True).start()
        return public_job(record)


def public_job(record):
    return {key: value for key, value in record.items() if key not in ('fingerprint', 'submission_key', 'encrypted_payload', 'encrypted_result')}


def _execute(identity, workspace, kind, payload, event):
    with _slots:
        record = store.get('jobs', identity, workspace)
        if event.is_set():
            with _lock:
                _cancelled.pop(identity, None)
            return
        record.update(status='processing', started=time.time())
        store.put('jobs', identity, workspace, record)
        try:
            if record.get('encrypted_result'):
                result = json.loads(decrypt(record['encrypted_result'], workspace, 'result:' + identity))
            elif kind == 'mcp':
                from .mcp import call
                result = call(**payload)
            elif kind == 'cloud':
                from .cloud import cloud_request
                result = cloud_request(**payload)
                result = persist_result(result, payload['provider'], workspace, identity)
            elif kind == 'provider-status':
                source = store.get('jobs', payload.get('source_job_id', ''), workspace)
                if not source or not source.get('poll_url'):
                    raise ValueError('No recoverable provider operation was recorded for this job.')
                record.update({key: source[key] for key in ('provider', 'provider_id', 'poll_url', 'response_url') if source.get(key)})
                target = source.get('response_url') if str(source.get('provider_status', '')).lower() == 'completed' and source.get('response_url') else source['poll_url']
                result = proxy_request(source['provider'], target, method='GET')
            elif kind == 'provider':
                result = proxy_request(**payload)
            else:
                from .runtime import run_operation
                result = run_operation(kind, payload, identity, event, lambda progress: update_progress(identity, workspace, progress))
            if event.is_set():
                record.update(status='cancelled')
            else:
                if kind in ('provider', 'provider-status', 'gemini'):
                    provider = record.get('provider') or payload.get('provider', 'gemini')
                    record.update({key: value for key, value in provider_receipt(result, provider).items() if value is not None})
                    # Store the receipt before downloading output. A save retry never resubmits a paid request.
                    record['encrypted_result'] = encrypt(json.dumps(result), workspace, 'result:' + identity)
                    record['retryable'] = True
                    store.put('jobs', identity, workspace, record)
                    result = persist_result(result, provider, workspace, identity)
                    if kind == 'provider-status':
                        source.update({key: record[key] for key in ('provider_status', 'provider_id', 'poll_url', 'response_url') if record.get(key)})
                        source['latest_status_job'] = identity
                        store.put('jobs', source['id'], workspace, source)
                    if result.get('status', 200) in (502, 504) and payload.get('method', 'GET') != 'GET':
                        record.update(status='interrupted', retryable=False, result=result,
                                      error='Provider submission has an unknown outcome. Check provider history before starting another generation.')
                    else:
                        record.update(status='completed', progress=100, result=result)
                else:
                    record.update(status='completed', progress=100, result=result)
        except Exception as exc:
            # Never echo provider request payloads, credentials, or native command lines.
            record.update(status='cancelled' if event.is_set() else 'failed',
                          error=str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else 'Processing failed. Check the configured service and retry.')
        record['finished'] = time.time()
        store.put('jobs', identity, workspace, record)
        with _lock:
            _cancelled.pop(identity, None)
            _processes.pop(identity, None)


def update_progress(identity, workspace, value):
    record = store.get('jobs', identity, workspace)
    if record and record['status'] == 'processing':
        record['progress'] = max(0, min(99, value))
        store.put('jobs', identity, workspace, record)


def cancel(identity):
    record = store.get('jobs', identity, owner())
    if not record:
        raise FileNotFoundError('Job not found.')
    with _lock:
        event = _cancelled.get(identity)
        if event:
            event.set()
        process = _processes.get(identity)
        if process:
            from .runtime import stop_process
            stop_process(process)
    if record['status'] in ('queued', 'processing'):
        record.update(status='cancelled', finished=time.time())
        store.put('jobs', identity, owner(), record)
    return public_job(record)


def recover_for_workspace():
    for record in store.list('jobs', owner()):
        if record['status'] in ('queued', 'processing') and record['id'] not in _cancelled:
            record.update(status='interrupted', error='The backend restarted. Check the provider history before resubmitting a generation.', finished=time.time())
            store.put('jobs', record['id'], owner(), record)


def retry(identity):
    workspace = owner()
    with _lock:
        record = store.get('jobs', identity, workspace)
        if not record:
            raise FileNotFoundError('Job not found.')
        if record['status'] not in ('failed', 'interrupted', 'cancelled') or not record.get('retryable'):
            raise ValueError('This job cannot be safely retried. Check its provider history before starting another generation.')
        if identity in _cancelled:
            raise ValueError('This worker is still stopping. Wait for it to finish before retrying.')
        active = [job for job in store.list('jobs', workspace) if job['status'] in ('queued', 'processing')]
        if len(active) >= int(os.getenv('EDITOR_QUEUE_LIMIT', '4')) or len(_cancelled) >= int(os.getenv('EDITOR_GLOBAL_QUEUE_LIMIT', '32')):
            raise ValueError('The processing queue is full. Retry shortly.')
        payload = json.loads(decrypt(record['encrypted_payload'], workspace, 'job:' + identity))
        record.update(status='queued', progress=0, error=None, finished=None)
        store.put('jobs', identity, workspace, record)
        event = threading.Event()
        _cancelled[identity] = event
        context = copy_context()
        threading.Thread(target=context.run, args=(_execute, identity, workspace, record['kind'], payload, event), daemon=True).start()
        return public_job(record)


def refresh_provider(identity):
    record = store.get('jobs', identity, owner())
    if not record:
        raise FileNotFoundError('Job not found.')
    if not record.get('poll_url'):
        raise ValueError('This provider did not return a recoverable operation. Check its history before generating again.')
    return submit('provider-status', {'source_job_id': identity}, str(uuid.uuid4()))
