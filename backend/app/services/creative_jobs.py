"""Bounded local work queue for Auto Reel and subject-matte preparation."""
import threading
import time
import uuid
from app.services.processing import check_cancel, ProcessingCancelled

JOBS = {}
_slots = threading.BoundedSemaphore(1)
_events = {}

def start_job(work):
    if sum(job['status'] in ('queued', 'processing') for job in JOBS.values()) >= 4:
        raise ValueError('The local processing queue is full. Wait for the active job.')
    # Keep only recent completed results; projects retain their own edit plans.
    for key, job in list(JOBS.items()):
        if job['status'] in ('completed', 'failed') and time.time() - job['created_at'] > 3600:
            JOBS.pop(key, None)
    identity = uuid.uuid4().hex
    job = {'id': identity, 'status': 'queued', 'stage': 'Waiting for the local processor', 'created_at': time.time()}
    JOBS[identity] = job
    event = threading.Event()
    _events[identity] = event
    def execute():
        with _slots:
            def report(stage):
                check_cancel(event)
                job['stage'] = stage
            report.cancel = event
            try:
                check_cancel(event)
                job['status'] = 'processing'
                job['result'] = work(report)
                check_cancel(event)
                job['status'] = 'completed'
                job['stage'] = 'Ready'
            except ProcessingCancelled:
                job['status'] = 'cancelled'
                job.pop('result', None)
            except Exception as exc:
                job['status'] = 'failed'
                job['error'] = str(exc) if isinstance(exc, ValueError) else 'Local processing failed. Check model installation and source media.'
            finally:
                _events.pop(identity, None)
    threading.Thread(target=execute, daemon=True).start()
    return identity


def cancel_job(identity):
    event = _events.get(identity)
    if event is None:
        return False
    event.set()
    JOBS[identity]['status'] = 'cancelled'
    return True
