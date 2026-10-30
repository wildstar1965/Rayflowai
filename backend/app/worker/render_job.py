"""Cloud Run Job entrypoint for rendering a RayFlow export off the request path.

Flow (matches the architecture in the task spec):

  backend  -> persists a render task record (plan + filenames + workspace) via
              the shared store, marks the render job 'queued', then triggers this
              Cloud Run Job with RENDER_TASK_ID / RENDER_WORKSPACE_ID set.
  worker   -> loads the task, scopes to the workspace, pulls source media from
              the store (GCS in production), renders with the EXISTING FFmpeg
              pipeline, uploads the MP4 to the store, and marks the job done.
  frontend -> keeps polling /api/render/{job_id}; status is read from persistent
              job history, so it survives backend restarts and is independent of
              any single instance's memory.

The backend and worker do NOT share a filesystem; Cloud Storage is the handoff.
Temporary FFmpeg files live on the Job's own ephemeral disk and are cleaned up.
"""
from __future__ import annotations

import os
import sys
import time

RENDER_TASK_COLLECTION = 'render_tasks'


def _log(message: str) -> None:
    print(f'[render-worker] {message}', flush=True)


def run(task_id: str, workspace: str) -> int:
    # Imports are deferred so `--help`/diagnostics do not require the full stack.
    from app.editor.context import workspace_id
    from app.editor.store import store
    from app.schemas.editing_plan import EditingPlan
    from app.services import job_history
    from app.services.video_renderer import start_render_job, get_job_status

    token = workspace_id.set(workspace)
    try:
        task = store.get(RENDER_TASK_COLLECTION, task_id, workspace)
        if not task:
            _log(f'No render task {task_id} for workspace {workspace}.')
            return 2
        job_id = task['render_job_id']
        plan = EditingPlan.model_validate(task['plan'])
        image_filenames = task.get('image_filenames', [])
        audio_filename = task.get('audio_filename')

        _log(f'Rendering job {job_id} ({len(plan.clips)} clips).')
        # Reuse the exact in-process renderer; in a Job it owns the whole CPU.
        started = start_render_job(plan=plan, image_filenames=image_filenames, audio_filename=audio_filename)

        # Block until the background render thread finishes (the Job stays alive).
        deadline = time.monotonic() + int(os.getenv('RENDER_TIMEOUT_SECONDS', '1800')) + 120
        while time.monotonic() < deadline:
            status = get_job_status(started)
            if status and status.status in ('completed', 'failed', 'cancelled'):
                break
            time.sleep(2)
        else:
            status = get_job_status(started)

        final = status.status if status else 'failed'
        # Mirror the worker's result onto the caller-facing job id in history so
        # the frontend's /api/render/{job_id} reflects the outcome.
        if job_id != started:
            job_history.finished(job_id, 'completed' if final == 'completed' else 'failed')
        _log(f'Render finished with status: {final}')

        # One-shot task record; remove so retries are explicit and idempotent.
        try:
            store.delete(RENDER_TASK_COLLECTION, task_id, workspace)
        except Exception:
            pass
        return 0 if final == 'completed' else 1
    finally:
        workspace_id.reset(token)


def main() -> int:
    task_id = os.getenv('RENDER_TASK_ID', '').strip()
    workspace = os.getenv('RENDER_WORKSPACE_ID', '').strip()
    if not task_id or not workspace:
        _log('RENDER_TASK_ID and RENDER_WORKSPACE_ID are required.')
        return 2
    try:
        return run(task_id, workspace)
    except Exception as exc:  # pragma: no cover - top-level safety net
        _log(f'Fatal error: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
