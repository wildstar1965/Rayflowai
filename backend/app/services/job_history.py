"""Persistent measurements from actual processing lifecycle events (single worker)."""
import sqlite3
import json
import time
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from app.core.config import STORAGE_DIR

DB_PATH = STORAGE_DIR / 'jobs.sqlite3'


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
            created REAL NOT NULL, started REAL, finished REAL, output TEXT)''')
        yield connection
        connection.commit()
    finally:
        connection.close()


def created(identity, kind):
    with database() as connection:
        connection.execute('INSERT INTO jobs(id,kind,status,created) VALUES (?,?,?,?)', (identity, kind, 'queued', time.time()))
    _sync_record(identity)


def started(identity):
    with database() as connection:
        connection.execute("UPDATE jobs SET status='processing', started=? WHERE id=? AND status='queued'", (time.time(), identity))
    _sync_record(identity)


def finished(identity, status, output=None):
    if status not in ('completed', 'failed', 'cancelled', 'interrupted'):
        raise ValueError('Invalid terminal job status.')
    with database() as connection:
        connection.execute('UPDATE jobs SET status=?, finished=?, output=? WHERE id=? AND finished IS NULL', (status, time.time(), output, identity))
    from app.editor.context import workspace_id
    if status == 'completed' and output and workspace_id.get():
        from app.editor.store import store
        from app.core.config import EXPORT_DIR
        from pathlib import Path
        path = EXPORT_DIR / Path(output).name
        if path.exists():
            store.put_blob(workspace_id.get(), 'exports/' + path.name, path.read_bytes())
    _sync_record(identity)


def recover_interrupted():
    with database() as connection:
        connection.execute("UPDATE jobs SET status='interrupted', finished=? WHERE status IN ('queued','processing')", (time.time(),))


def get(identity):
    from app.editor.context import workspace_id
    if workspace_id.get():
        from app.editor.store import store
        record = store.get('legacy_jobs', identity, workspace_id.get())
        if record:
            return {key: value for key, value in record.items() if key != 'revision'}
    with database() as connection:
        row = connection.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
        return dict(row) if row else None


def _sync_record(identity):
    from app.editor.context import workspace_id
    if not workspace_id.get():
        return
    from app.editor.store import store
    with database() as connection:
        row = connection.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
    if row:
        store.put('legacy_jobs', identity, workspace_id.get(), dict(row))


def analytics():
    from app.editor.context import workspace_id
    if workspace_id.get():
        return workspace_analytics(workspace_id.get())
    with database() as connection:
        # All cards and tables describe the same snapshot, even as workers finish.
        connection.execute('BEGIN')
        rows = connection.execute('''SELECT
            COUNT(*) AS total_jobs,
            COALESCE(SUM(status IN ('queued','processing')),0) AS active_jobs,
            COALESCE(SUM(status='completed'),0) AS completed_jobs,
            COALESCE(SUM(status='failed'),0) AS failed_jobs,
            COALESCE(SUM(status='cancelled'),0) AS cancelled_jobs,
            COALESCE(SUM(status='interrupted'),0) AS interrupted_jobs,
            COALESCE(SUM(kind='render' AND status='completed'),0) AS exports,
            COALESCE(SUM(kind='transcription' AND status='completed'),0) AS caption_jobs,
            AVG(CASE WHEN kind='render' AND status='completed' AND started IS NOT NULL THEN finished-started END) AS average_render_seconds
            FROM jobs''').fetchone()
        result = dict(rows)
        denominator = result['completed_jobs'] + result['failed_jobs']
        result['success_rate'] = 100 * result['completed_jobs'] / denominator if denominator else None
        result['recent_jobs'] = [dict(row) for row in connection.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 20')]
        today = datetime.now(timezone.utc).date()
        days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        daily = {row['date']: dict(row) for row in connection.execute('''SELECT
            date(finished, 'unixepoch') AS date,
            SUM(status='completed') AS completed, SUM(status='failed') AS failed,
            SUM(kind='render' AND status='completed') AS exports
            FROM jobs WHERE finished >= ? AND status IN ('completed','failed')
            GROUP BY date(finished, 'unixepoch')''',
            (datetime.combine(today - timedelta(days=6), datetime.min.time(), timezone.utc).timestamp(),))}
        result['daily_activity'] = [daily.get(day, {'date': day, 'completed': 0, 'failed': 0, 'exports': 0}) for day in days]
        return result


def workspace_analytics(workspace):
    """Both workspaces use the same durable, owner-filtered job history."""
    from app.editor.store import store
    legacy = store.list('legacy_jobs', workspace)
    editor = store.list('jobs', workspace)
    def output_url(value):
        if isinstance(value, str):
            if value.startswith('/api/editor/assets/file/'):
                return value
            if value.startswith(('{', '[')):
                try:
                    return output_url(json.loads(value))
                except ValueError:
                    return None
        if isinstance(value, dict):
            if value.get('asset_path'):
                return '/api/editor/assets/file/' + value['asset_path']
            return next((url for child in value.values() if (url := output_url(child))), None)
        if isinstance(value, list):
            return next((url for child in value if (url := output_url(child))), None)
        return None
    rows = [{**row, 'editor': True, 'output': output_url(row.get('result')),
             'can_refresh_provider': bool(row.get('poll_url'))} for row in editor]
    rows.extend(legacy)
    result = {'total_jobs': len(rows)}
    for label, statuses in {'active': ('queued', 'processing'), 'completed': ('completed',), 'failed': ('failed',),
                            'cancelled': ('cancelled',), 'interrupted': ('interrupted',)}.items():
        result[label + '_jobs'] = sum(row['status'] in statuses for row in rows)
    renders = [row for row in rows if row['kind'] in ('render', 'export') and row['status'] == 'completed']
    result['exports'] = len(renders)
    result['caption_jobs'] = sum(row['kind'] == 'transcription' and row['status'] == 'completed' for row in rows)
    durations = [row['finished'] - row['started'] for row in renders if row.get('finished') and row.get('started')]
    result['average_render_seconds'] = sum(durations) / len(durations) if durations else None
    denominator = result['completed_jobs'] + result['failed_jobs']
    result['success_rate'] = 100 * result['completed_jobs'] / denominator if denominator else None
    allowed = ('id', 'kind', 'status', 'created', 'started', 'finished', 'output', 'editor', 'retryable', 'error', 'provider_id', 'provider_status', 'can_refresh_provider')
    result['recent_jobs'] = [{key: row.get(key) for key in allowed} for row in sorted(rows, key=lambda row: row['created'], reverse=True)[:50]]
    today = datetime.now(timezone.utc).date()
    result['daily_activity'] = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        completed = [row for row in rows if row.get('finished') and datetime.fromtimestamp(row['finished'], timezone.utc).date() == day]
        result['daily_activity'].append({'date': day.isoformat(), 'completed': sum(row['status'] == 'completed' for row in completed),
            'failed': sum(row['status'] == 'failed' for row in completed),
            'exports': sum(row['kind'] in ('render', 'export') and row['status'] == 'completed' for row in completed)})
    return result
