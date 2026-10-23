"""Bounded local work queue for Auto Reel and subject-matte preparation."""
import threading
from app.editor.context import scoped_target, workspace_id
import time
import uuid
from app.services.processing import check_cancel, ProcessingCancelled
from app.services import job_history

JOBS = {}
_slots = threading.BoundedSemaphore(1)
_events = {}
_lock = threading.RLock()

def start_job(work):
    with _lock:
        # Cancelled threads still occupy admission until their worker exits.
        if len(_events) >= 4:
            raise ValueError('The local processing queue is full. Wait for the active job.')
        for key, job in list(JOBS.items()):
            if key not in _events and time.time() - job['created_at'] > 3600:
                JOBS.pop(key, None)
        identity = uuid.uuid4().hex
        job_history.created(identity, 'creative')
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
                job_history.started(identity)
                job['result'] = work(report)
                with _lock:
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
                try:
                    job_history.finished(identity, job['status'])
                finally:
                    with _lock:
                        _events.pop(identity, None)
    try:
        threading.Thread(target=scoped_target(execute), daemon=True).start()
    except RuntimeError:
        with _lock:
            job['status'] = 'failed'
            _events.pop(identity, None)
        job_history.finished(identity, 'failed')
        raise ValueError('The creative worker could not start. Retry when resources are available.') from None
    return identity


def cancel_job(identity):
    if workspace_id.get() and not job_history.get(identity):
        return False
    with _lock:
        event = _events.get(identity)
        if event is None or JOBS[identity]['status'] not in ('queued', 'processing'):
            return False
        event.set()
        JOBS[identity]['status'] = 'cancelled'
        return True
