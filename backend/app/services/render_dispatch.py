"""Dispatch a render either in-process (local/dev) or to a Cloud Run Job (prod).

Selection is by environment:
  * If RENDER_CLOUD_RUN_JOB is set (Cloud Run deployment), the backend persists a
    render task to the shared store and triggers a Cloud Run Job execution with
    RENDER_TASK_ID / RENDER_WORKSPACE_ID overrides. The worker renders and uploads
    the MP4 to Cloud Storage; the frontend polls persistent job status.
  * Otherwise (local Docker / dev), the existing in-process threaded renderer runs
    exactly as before, so nothing changes for local use.

This keeps long-running FFmpeg work off normal HTTP requests in production while
preserving the simple local experience.
"""
from __future__ import annotations

import os
import uuid
from typing import List, Optional

from app.schemas.editing_plan import EditingPlan

RENDER_TASK_COLLECTION = 'render_tasks'


def cloud_run_render_enabled() -> bool:
    return bool(os.getenv('RENDER_CLOUD_RUN_JOB', '').strip())


def dispatch_render(plan: EditingPlan, image_filenames: List[str],
                    audio_filename: Optional[str] = None) -> str:
    """Start a render and return the caller-facing render job id.

    In Cloud Run mode this creates a persistent job + task and triggers a Job
    execution. Locally it delegates to the existing in-process renderer.
    """
    if not cloud_run_render_enabled():
        from app.services.video_renderer import start_render_job
        return start_render_job(plan=plan, image_filenames=image_filenames, audio_filename=audio_filename)

    from app.editor.context import owner
    from app.editor.store import store
    from app.services import job_history

    workspace = owner()
    render_job_id = uuid.uuid4().hex
    task_id = uuid.uuid4().hex

    # Persist a job record so status survives across services/instances.
    job_history.created(render_job_id, 'render')

    store.put(RENDER_TASK_COLLECTION, task_id, workspace, {
        'render_job_id': render_job_id,
        'plan': plan.model_dump(mode='json'),
        'image_filenames': image_filenames,
        'audio_filename': audio_filename,
    })

    _trigger_cloud_run_job(task_id, workspace)
    return render_job_id


def _trigger_cloud_run_job(task_id: str, workspace: str) -> None:
    """Trigger a Cloud Run Job execution with per-run env overrides.

    Uses the metadata-server access token available to the Cloud Run service's
    service account. Raises a clear error if triggering fails so the caller can
    surface it; the task record remains for manual/retry execution.
    """
    import requests

    project = os.getenv('GCP_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT', '')
    region = os.getenv('GCP_REGION', 'asia-south1')
    job = os.getenv('RENDER_CLOUD_RUN_JOB', '')
    if not project:
        raise RuntimeError('GCP_PROJECT_ID is required to trigger the render job.')

    token = _access_token()
    url = (f'https://run.googleapis.com/v2/projects/{project}/locations/{region}'
           f'/jobs/{job}:run')
    body = {
        'overrides': {
            'containerOverrides': [{
                'env': [
                    {'name': 'RENDER_TASK_ID', 'value': task_id},
                    {'name': 'RENDER_WORKSPACE_ID', 'value': workspace},
                ],
            }],
        }
    }
    response = requests.post(url, json=body, headers={'Authorization': f'Bearer {token}'},
                             timeout=(5, 30))
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f'Could not start the render job (HTTP {response.status_code}).')


def _access_token() -> str:
    import requests
    response = requests.get(
        'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',
        headers={'Metadata-Flavor': 'Google'}, timeout=(2, 5))
    response.raise_for_status()
    return response.json()['access_token']
