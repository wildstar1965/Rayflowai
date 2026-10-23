# Measured production activity

`GET /api/analytics` reads one SQLite snapshot from `STORAGE_DIR/jobs.sqlite3`.
Render, standalone transcription and creative workers record queued, processing,
and terminal lifecycle events. Repeated completion events cannot rewrite history.
On backend startup, unfinished jobs become interrupted; they are not resumed.

| Metric | Formula / source |
| --- | --- |
| Recorded jobs | Count of all persisted job records |
| Active jobs | Count with queued or processing status |
| Completed exports | Completed jobs of kind render |
| Caption jobs | Completed standalone transcription jobs, including no-speech results |
| Failed / cancelled / interrupted | Count of each terminal status |
| Processing success | 100 × completed / (completed + failed); unknown when denominator is zero |
| Average render time | Mean finished minus started for completed renders; excludes queue time |
| Last seven days | Completed, failed and successful render counts by finish date in UTC |

The dashboard refreshes every five seconds, on window focus and cross-tab storage
changes, and via its Refresh action. A failed refresh retains the last values with
an error message. Empty averages and rates are unknown, never fabricated zeroes.
Saved project name, clip count and caption count come from this browser's existing
`rayflow_project_state_v3` entry. This is one saved timeline, not a global project count.

Tracking starts when job history was enabled; older exports are not backfilled with
invented durations. Transcription inside Auto Reel is counted as creative activity,
not a second standalone caption job. Records are backend-wide, not per-user.
The reference `src/portal/pages/Analytics.tsx` shows usage rows from `fetchUsage`;
it contains no suitable render-duration or success-rate calculation to copy.
