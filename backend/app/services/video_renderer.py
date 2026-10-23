import os
import subprocess
import uuid
import time
import threading
from app.editor.context import scoped_target, workspace_id
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from app.services.media import probe_media, probe_streams, stream_duration, VIDEO_EXTENSIONS
from app.services.frame_timing import OUTPUT_FPS, frame_at, clip_frame_counts
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from app.core.config import FFMPEG_PATH, EXPORT_DIR, UPLOAD_DIR, RENDER_CONCURRENCY, RENDER_QUEUE_LIMIT, RENDER_TIMEOUT_SECONDS
from app.services import job_history
from app.schemas.editing_plan import EditingPlan, RenderJobStatus, ClipConfig, TransitionConfig, SubtitleSegment, SubtitleStyle, VisualInsert

# Active jobs registry
_JOBS: Dict[str, RenderJobStatus] = {}
_JOB_LOCK = threading.Lock()
_RENDER_SLOTS = threading.BoundedSemaphore(RENDER_CONCURRENCY)
_ACTIVE_RENDER_IDS = set()
_RENDER_DEADLINES = {}

def cancel_render_job(job_id):
    if workspace_id.get() and not job_history.get(job_id):
        return False
    with _JOB_LOCK:
        job = _JOBS.get(job_id)
        if not job or job.status not in ('queued', 'processing'):
            return False
        job.status = 'cancelled'
        return True

def _run_render(command, job_id):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = _RENDER_DEADLINES.get(job_id, time.monotonic() + RENDER_TIMEOUT_SECONDS)
    while True:
        if _JOBS[job_id].status == 'cancelled':
            process.kill()
            process.communicate()
            raise RuntimeError('Render cancelled.')
        if time.monotonic() > deadline:
            process.kill()
            process.communicate()
            raise RuntimeError('Render exceeded RENDER_TIMEOUT_SECONDS. Shorten the video or increase the backend time limit.')
        try:
            stdout, stderr = process.communicate(timeout=.25)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue

def get_job_status(job_id: str) -> Optional[RenderJobStatus]:
    if workspace_id.get() and not job_history.get(job_id):
        return None
    if job_id in _JOBS:
        return _JOBS[job_id]
    saved = job_history.get(job_id)
    if not saved or saved['kind'] != 'render':
        return None
    complete = saved['status'] == 'completed'
    return RenderJobStatus(job_id=job_id, status='failed' if saved['status'] == 'interrupted' else saved['status'],
        progress=100 if complete else 0, created_at=saved['created'],
        output_url=f'/api/exports/rayflow_{job_id}.mp4' if complete else None,
        download_url=f'/api/render/{job_id}/download' if complete else None,
        error='Processing was interrupted by a backend restart. Render again.' if saved['status'] == 'interrupted' else None)

def create_title_overlay(
    text: str,
    subtitle: Optional[str],
    width: int,
    height: int,
    output_png: str,
    gradient_colors: List[str],
    position: str = 'center',
    color: str = '#FFFFFF',
) -> str:
    """
    Renders a clean cinematic title overlay as a transparent PNG using Pillow.
    Uses Apple-inspired minimalist typography.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Simple font fallback
    font_size = max(28, int(width * 0.055))
    sub_font_size = max(14, int(width * 0.026))
    try:
        font_main = ImageFont.truetype("arialbd.ttf", font_size)
        font_sub = ImageFont.truetype("arial.ttf", sub_font_size)
    except Exception:
        font_main = ImageFont.load_default()
        font_sub = font_main

    # Measure text bounds
    bbox = draw.textbbox((0, 0), text, font=font_main)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    baseline = height * (0.15 if position == 'top' else 0.8 if position == 'bottom' else 0.45)
    y = int(baseline - font_size)

    # Soft dark glow behind text for contrast
    for offset in range(4, 0, -1):
        draw.text((x - offset, y - offset), text, font=font_main, fill=(0, 0, 0, 140))
        draw.text((x + offset, y + offset), text, font=font_main, fill=(0, 0, 0, 140))
        draw.text((x - offset, y + offset), text, font=font_main, fill=(0, 0, 0, 140))
        draw.text((x + offset, y - offset), text, font=font_main, fill=(0, 0, 0, 140))

    # Clean crisp monochrome text fill
    text_color = color
    draw.text((x, y), text, font=font_main, fill=text_color)

    if subtitle:
        s_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw, sh = s_bbox[2] - s_bbox[0], s_bbox[3] - s_bbox[1]
        sx = (width - sw) // 2
        sy = y + th + 18
        draw.text((sx, sy), subtitle, font=font_sub, fill=(240, 240, 245, 220))

    img.save(output_png, "PNG")
    return output_png

def _validate_rendered_video(
    file_path: Path,
    expected_w: int,
    expected_h: int,
    has_audio: bool,
    expected_duration: Optional[float] = None,
    expected_frames: Optional[int] = None,
    fps: int = OUTPUT_FPS,
):
    """Probe actual streams and independently decode every video/audio packet."""
    if not file_path.exists() or file_path.stat().st_size < 1000:
        raise RuntimeError(f"Export validation failed: File is missing or empty ({file_path})")
    data = probe_streams(file_path, count_frames=True)
    video = next((s for s in data['streams'] if s['codec_type'] == 'video'), {})
    audio = next((s for s in data['streams'] if s['codec_type'] == 'audio'), {})
    if (video.get('width'), video.get('height')) != (expected_w, expected_h):
        raise RuntimeError(f"Export validation failed: Expected {expected_w}x{expected_h} video.")
    if has_audio and not audio:
        raise RuntimeError("Export validation failed: Expected audio stream not present in rendered file")
    from fractions import Fraction
    if Fraction(video.get('avg_frame_rate', '0/1')) != fps:
        raise RuntimeError(f"Export validation failed: Expected {fps} fps.")
    if abs(float(video.get('start_time', 0))) > 1e-5:
        raise RuntimeError("Export validation failed: Video does not start at timeline zero.")
    duration = stream_duration(video)
    if duration <= 0:
        raise RuntimeError("Export validation failed: Rendered video has no duration")
    if expected_frames is None and expected_duration is not None:
        expected_frames = frame_at(expected_duration, fps)
    if expected_frames is not None:
        expected_duration = expected_frames / fps
        actual_frames = int(video.get('nb_read_frames', 0))
        if actual_frames != expected_frames:
            raise RuntimeError(f"Export validation failed: Decoded frame count does not match the timeline "
                               f"(expected {expected_frames}, FFprobe decoded {actual_frames}).")
        if abs(duration - expected_duration) > 1e-5:
            raise RuntimeError(f"Export validation failed: Expected duration {expected_duration:.6f}s, "
                               f"but video stream has {duration:.6f}s")
    # AAC durations can differ by one encoder packet, but cannot hide a short video.
    if audio and (abs(float(audio.get('start_time', 0))) > 1 / fps or
                  abs(stream_duration(audio) - duration) > max(1 / fps, 1024 / 48000)):
        raise RuntimeError("Export validation failed: Audio timing does not match the video.")
    decode = subprocess.run(
        [FFMPEG_PATH, "-v", "error", "-xerror", "-i", str(file_path),
         "-map", "0:v:0", "-map", "0:a:0?", "-fps_mode", "passthrough",
         "-progress", "pipe:1", "-nostats", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    if decode.returncode != 0 or decode.stderr.strip():
        raise RuntimeError(f"Export validation failed: Media could not be decoded: {decode.stderr[-500:]}")
    decoded_counts = re.findall(r"^frame=\s*(\d+)$", decode.stdout, re.MULTILINE)
    if expected_frames is not None and (not decoded_counts or int(decoded_counts[-1]) != expected_frames):
        actual = decoded_counts[-1] if decoded_counts else 'unknown'
        raise RuntimeError(f"Export validation failed: Decoded frame count does not match the timeline "
                           f"(expected {expected_frames}, FFmpeg decoded {actual}).")


def _resolve_image_path(img_path: str, fallback_paths: List[str]) -> str:
    p = Path(unquote(urlparse(img_path).path)) if '://' in img_path or img_path.startswith('/api/') else Path(img_path)
    if p.is_file():
        return str(p.resolve())
    in_upload = UPLOAD_DIR / p.name
    if in_upload.is_file():
        return str(in_upload.resolve())
    raise FileNotFoundError(f"Could not find image file: {img_path}")

def build_motion_filter(width: int, height: int, fps: int, frames: int, motion: str) -> str:
    """Supersample in RGB so zoompan's integer crop cannot jump chroma pixels."""
    progress = f"min(on/{max(1, frames - 1)},1)"
    zoom = f"1.15-0.1*{progress}" if motion == "zoom_out" else f"1.05+0.1*{progress}"
    x = "iw/2-iw/zoom/2"
    y = "ih/2-ih/zoom/2"
    if motion in ("pan_left", "pan_right"):
        zoom = "1.15"
        direction = f"1-{progress}" if motion == "pan_left" else progress
        x = f"(iw-iw/zoom)*({direction})"
    return (
        f"scale={width * 4}:{height * 4}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width * 4}:{height * 4},format=gbrp,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps}"
    )


def _render_worker(
    job_id: str,
    plan: EditingPlan,
    image_paths: List[str],
    audio_path: Optional[str],
    job_dir: Path
):
    """
    Background rendering thread that executes FFmpeg commands to produce the MP4 reel.
    Supports aspect ratios (9:16, 16:9, 1:1), fit modes (fill, fit), boundary transitions (xfade),
    head/tail fades, title overlays, soundtrack synchronization, and strict export verification.
    """
    status = _JOBS[job_id]
    try:
        with _JOB_LOCK:
            if status.status == 'cancelled':
                return
            status.status = "processing"
            job_history.started(job_id)
        status.progress = 5.0

        # 1. Output dimensions from aspect_ratio
        ratio = plan.aspect_ratio or "9:16"
        if ratio == "16:9":
            width, height = 1920, 1080
        elif ratio == "1:1":
            width, height = 1080, 1080
        else:  # "9:16"
            width, height = 1080, 1920

        fps = OUTPUT_FPS
        clips = plan.clips

        if not clips:
            raise ValueError("The timeline is empty. Add clips before exporting.")
        if ratio not in ("9:16", "16:9", "1:1"):
            raise ValueError("Unsupported aspect ratio.")
        expected_start = 0.0
        for clip in clips:
            if abs(clip.start_time - expected_start) > 0.02:
                raise ValueError("Clip start times must form a continuous timeline.")
            expected_start += clip.duration
        if abs(expected_start - plan.duration_seconds) > 0.04:
            raise ValueError("Plan duration does not match its clips.")

        status.progress = 15.0

        # 2. Color grading filter according to style
        style = (plan.style or "cinematic").lower()
        if style == "noir":
            color_filter = ",hue=s=0,eq=contrast=1.3:brightness=-0.05"
        elif style == "vintage":
            color_filter = ",colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0,eq=contrast=1.1"
        elif style == "vibrant":
            color_filter = ",eq=saturation=1.35:contrast=1.1"
        elif style == "minimal":
            color_filter = ",eq=contrast=1.05:saturation=0.9"
        else:  # cinematic
            color_filter = f",eq=contrast={1+.1*plan.color_strength:.4f}:saturation={1+.15*plan.color_strength:.4f}"

        # 3. Fit mode filter setup
        fit_mode = getattr(plan, "fit_mode", "fill")
        if fit_mode == "fit":
            # Fit mode: Scale preserving aspect ratio, pad with solid black background
            scale_filter = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
            )
        else:
            # Fill mode: Scale to cover and crop center
            scale_filter = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        rendered_clip_files: List[str] = []
        clip_frames = clip_frame_counts(clips, fps)
        clip_durations = [count / fps for count in clip_frames]
        total_clips = len(clips)

        # 4. Render individual clips (images or video clips)
        for idx, clip in enumerate(clips):
            img_file = _resolve_image_path(clip.image_url, image_paths)
            out_clip = str(job_dir / f"clip_{idx:03d}.mp4")
            # Round cumulative boundaries, avoiding per-clip duration drift.
            total_frames = clip_frames[idx]
            clip_dur = total_frames / fps
            is_video_file = clip.media_type == "video" or Path(img_file).suffix.lower() in VIDEO_EXTENSIONS
            if is_video_file:
                # Input seeking keeps a common source clock for both A/V streams.
                # CFR sampling uses timestamps, including VFR gaps. Only hold
                # EOF to cover the source's last frame/audio tail, not a bad edit.
                info = probe_media(Path(img_file))
                if clip.source_start + clip.duration > info['duration'] + 1e-5:
                    raise ValueError(f"Clip {clip.id} extends beyond its source duration.")
                vf = (f"{scale_filter},setsar=1,fps={fps}:start_time=0,"
                      f"tpad=stop_mode=clone:stop_duration={clip_dur},trim=end_frame={total_frames},"
                      f"settb=1/{fps},setpts=N,fps={fps}:eof_action=pass{color_filter},format=yuv420p")
                input_args = ["-ss", str(clip.source_start), "-i", img_file]
            elif fit_mode == "fill" and clip.motion != "static":
                vf = build_motion_filter(width, height, fps, total_frames, clip.motion) + color_filter + ",format=yuv420p,setsar=1"
                input_args = ["-i", img_file]
            else:
                vf = f"{scale_filter}{color_filter},setsar=1,format=yuv420p"
                input_args = ["-loop", "1", "-framerate", str(fps), "-i", img_file]
            cmd = [FFMPEG_PATH, "-y", "-xerror", "-filter_threads", "1", *input_args,
                   "-vf", vf, "-frames:v", str(total_frames), "-an",
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-enc_time_base:v", f"1/{fps}", "-fps_mode", "passthrough", out_clip]
            res = _run_render(cmd, job_id)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg failed to render clip {idx + 1} ({Path(img_file).name}): {res.stderr[-1500:]}")

            rendered_clip_files.append(out_clip)
            status.progress = 15.0 + (50.0 * (idx + 1) / total_clips)

        # 5. Determine boundary transitions between adjacent clips
        boundary_transitions: List[tuple] = []  # (transition_type, duration)
        has_active_transitions = False

        for i in range(len(clips) - 1):
            c_from = clips[i]
            c_to = clips[i + 1]

            matched_t = None
            if plan.transitions:
                for t in plan.transitions:
                    if t.from_clip_id == c_from.id and t.to_clip_id == c_to.id:
                        matched_t = t
                        break

            if matched_t:
                t_type = matched_t.type if matched_t.enabled else "none"
                t_dur = float(matched_t.duration) if t_type not in ("none", "cut") else 0.0
                has_active_transitions |= t_dur > 0
            elif c_from.transition and c_from.transition not in ("none", "cut"):
                t_type = c_from.transition
                t_dur = 0.5
                has_active_transitions = True
            else:
                t_type = "none"
                t_dur = 0.0

            # Leave at least one frame outside the overlap on BOTH sides.
            # A 0.1s floor can exceed a short clip and truncate an xfade chain.
            max_frames = max(0, min(clip_frames[i], clip_frames[i + 1]) - 1)
            t_dur = min(max_frames, frame_at(max(0.0, min(t_dur, min(clip_durations[i:i + 2]) - 0.1, 2.0)), fps)) / fps
            boundary_transitions.append((t_type, t_dur))

        # Check global head/tail transitions
        has_head_fade = plan.head_transition and plan.head_transition.enabled and plan.head_transition.type != "none"
        has_tail_fade = plan.tail_transition and plan.tail_transition.enabled and plan.tail_transition.type != "none"

        # 6. Build UNIFIED compositing & muxing filtergraph
        # Combines transitions, head/tail fades, title overlay, and audio in a single pass
        output_filename = f"rayflow_{job_id}.mp4"
        final_output_path = job_dir / output_filename

        inputs: List[str] = []
        for c_file in rendered_clip_files:
            inputs.extend(["-i", c_file])
        input_count = len(rendered_clip_files)

        filter_steps: List[str] = []
        # Explicitly reset timestamps and normalize the format before concat/xfade.
        # Independently encoded clips can otherwise retain different time bases,
        # causing xfade to stall or emit a short, partially playable output.
        normalized_tags: List[str] = []
        for i in range(len(rendered_clip_files)):
            tag = f"clip_norm_{i}"
            filter_steps.append(
                f"[{i}:v]setsar=1,format=yuv420p,settb=1/{fps},setpts=N,fps={fps}:eof_action=pass[{tag}]"
            )
            normalized_tags.append(tag)

        prev_tag = normalized_tags[0]
        running_dur = clip_durations[0]

        if len(clips) == 1:
            prev_tag = normalized_tags[0]
            running_dur = clip_durations[0]
        elif not has_active_transitions:
            # Fast concat filter
            concat_ins = "".join(f"[{tag}]" for tag in normalized_tags)
            filter_steps.append(f"{concat_ins}concat=n={len(clips)}:v=1:a=0,settb=1/{fps},setpts=N,fps={fps}:eof_action=pass[vconcat]")
            prev_tag = "vconcat"
            running_dur = sum(clip_durations)
        else:
            # Hold the incoming first frame during its lead-in. This preserves
            # sequential clip starts and the soundtrack/caption time axis.
            for i, (t_type, t_dur) in enumerate(boundary_transitions):
                next_tag = normalized_tags[i + 1]
                out_tag = f"vx{i + 1}"
                if t_type in ("none", "cut") or t_dur <= 0:
                    filter_steps.append(
                        f"[{prev_tag}][{next_tag}]concat=n=2:v=1:a=0,settb=1/{fps},setpts=N,fps={fps}:eof_action=pass[{out_tag}]"
                    )
                else:
                    transition = {"crossfade": "fade", "dip_black": "fadeblack",
                                  "dip_white": "fadewhite", "fade_in": "fadeblack",
                                  "fade_out": "fadeblack"}.get(t_type, "fade")
                    lead_tag = f"lead_{i + 1}"
                    filter_steps.append(
                        f"[{next_tag}]tpad=start_mode=clone:start={frame_at(t_dur, fps)},"
                        f"settb=1/{fps},setpts=N,fps={fps}:eof_action=pass[{lead_tag}]"
                    )
                    filter_steps.append(
                        f"[{prev_tag}][{lead_tag}]xfade=transition={transition}:"
                        f"duration={t_dur:.6f}:offset={running_dur - t_dur:.6f}[{out_tag}]"
                    )
                prev_tag = out_tag
                running_dur += clip_durations[i + 1]

        post_filters: List[str] = []
        timeline_duration = sum(clip_durations)

        if has_head_fade:
            head_dur = max(1 / fps, min(plan.head_transition.duration, running_dur / 3))
            head_color = "white" if "white" in plan.head_transition.type else "black"
            post_filters.append(f"fade=t=in:st=0:d={head_dur:.2f}:color={head_color}")

        if has_tail_fade:
            tail_dur = max(1 / fps, min(plan.tail_transition.duration, running_dur / 3))
            tail_color = "white" if "white" in plan.tail_transition.type else "black"
            tail_start = max(0.0, running_dur - tail_dur)
            post_filters.append(f"fade=t=out:st={tail_start:.2f}:d={tail_dur:.2f}:color={tail_color}")

        if post_filters:
            filter_steps.append(f"[{prev_tag}]{','.join(post_filters)}[vfaded]")
            prev_tag = "vfaded"

        # Apply Title Overlay in the same filtergraph
        if plan.title and plan.title.enabled and plan.title.text:
            title_png = str(job_dir / "title_overlay.png")
            create_title_overlay(
                text=plan.title.text,
                subtitle=plan.title.subtitle,
                width=width,
                height=height,
                output_png=title_png,
                gradient_colors=plan.title.gradient,
                position=plan.title.position,
                color=plan.title.color,
            )
            title_input_idx = input_count
            # Keep the overlay available for the full video. A single PNG input
            # can otherwise reach EOF while the filtered video is still active,
            # which makes FFmpeg produce no packets when audio is also mapped.
            inputs.extend(["-loop", "1", "-framerate", str(fps), "-i", title_png])
            input_count += 1
            filter_steps.append(f"[{prev_tag}][{title_input_idx}:v]overlay=0:0:enable='gte(t,0)*lt(t,4.5)'[vwithtitle]")
            prev_tag = "vwithtitle"

        # Apply Visual Inserts (Stage 6) if configured
        if plan.visual_inserts:
            for v_idx, ins in enumerate(plan.visual_inserts):
                try:
                    ins_file = _resolve_image_path(ins.asset_url, image_paths)
                    ins_input_idx = input_count
                    inputs.extend((["-stream_loop", "-1"] if Path(ins_file).suffix.lower() in VIDEO_EXTENSIONS else ["-loop", "1", "-framerate", str(fps)]) + ["-i", ins_file])
                    input_count += 1

                    st = max(0.0, float(ins.start_time))
                    et = min(running_dur, st + float(ins.duration))

                    out_tag = f"vinsert_{v_idx}"
                    scaled_tag = f"sinsert_{v_idx}"

                    from app.services.composition import insert_rect
                    rx, ry, rw, rh = insert_rect(ins.mode, ins.position)
                    iw, ih = round(width * rw), round(height * rh)
                    ox, oy = round(width * rx), round(height * ry)
                    # Reset each insert to its own source clock, then shift it to
                    # its project start. This prevents video B-roll starting late.
                    filter_steps.append(
                        f"[{ins_input_idx}:v]trim=start={ins.source_start}:duration={ins.duration},"
                        f"setpts=PTS-STARTPTS,fps={fps},scale={iw}:{ih}:force_original_aspect_ratio=increase,"
                        f"crop={iw}:{ih},setsar=1,setpts=PTS+{st}/TB[{scaled_tag}]"
                    )
                    if ins.mode == 'split':
                        # Keep the whole speaker frame visible in the left half.
                        filter_steps.append(f"[{prev_tag}]split=2[split_base_{v_idx}][split_speaker_{v_idx}]")
                        filter_steps.append(f"[split_speaker_{v_idx}]scale={width//2}:{height}:force_original_aspect_ratio=decrease,"
                                            f"pad={width//2}:{height}:(ow-iw)/2:(oh-ih)/2:black[split_fit_{v_idx}]")
                        filter_steps.append(f"[split_base_{v_idx}][split_fit_{v_idx}]overlay=0:0:enable='gte(t,{st})*lt(t,{et})'[split_left_{v_idx}]")
                        prev_tag = f'split_left_{v_idx}'
                    if ins.mode == 'background':
                        from app.services.segmentation import existing_masks, mask_duration
                        speaker = next((c for c in clips if c.start_time <= st < c.start_time+c.duration), None)
                        if not speaker or speaker.media_type != 'video' or et > speaker.start_time+speaker.duration:
                            raise ValueError('Keep a background insert within one video clip.')
                        directory = existing_masks(speaker, plan.aspect_ratio, plan.fit_mode, mask_duration(plan,speaker))
                        inputs.extend(['-framerate',str(fps),'-i',str(directory/'%05d.png')])
                        filter_steps.append(f'[{prev_tag}]split[background_base_{v_idx}][foreground_rgb_{v_idx}]')
                        filter_steps.append(f'[{input_count}:v]scale={width}:{height},format=gray,setpts=PTS+{speaker.start_time}/TB[foreground_mask_{v_idx}]')
                        input_count += 1
                        filter_steps.append(f'[foreground_rgb_{v_idx}][foreground_mask_{v_idx}]alphamerge[foreground_{v_idx}]')
                        prev_tag = f'background_base_{v_idx}'
                    filter_steps.append(
                        f"[{prev_tag}][{scaled_tag}]overlay={ox}:{oy}:eof_action=pass:"
                        f"enable='gte(t,{st})*lt(t,{et})'[{out_tag}]"
                    )

                    if ins.mode == 'background':
                        filter_steps.append(f"[{out_tag}][foreground_{v_idx}]overlay=0:0:eof_action=pass:enable='gte(t,{st})*lt(t,{et})'[retained_{v_idx}]")
                        out_tag = f'retained_{v_idx}'
                    prev_tag = out_tag
                except Exception as e:
                    raise RuntimeError(f"Could not add visual insert {ins.id}: {e}") from e

        # Genuine subject occlusion: multiply the title's alpha by the inverse
        # person matte, preserving the original speaker pixels underneath.
        for index, title in enumerate(plan.cinematic_texts):
            from app.services.cinematic import title_track
            def check_cancelled():
                if status.status == 'cancelled':
                    raise RuntimeError('Render cancelled.')
            clip = next((c for c in clips if c.id == title.source_clip_id), None)
            if not clip:
                raise ValueError('A cinematic title references a missing source clip.')
            if title.behind_subject and (title.start_time < clip.start_time or title.start_time+title.duration > clip.start_time+clip.duration+.001):
                raise ValueError('Keep text-behind-speaker within its source video clip.')
            title_path = title_track(title, width, height, job_dir / f'cinematic_{index}.ffconcat', check_cancelled)
            title_input = input_count
            inputs.extend(['-f','concat','-safe','0','-i',str(title_path)])
            input_count += 1
            title_tag = f'cinematic_{index}'
            filter_steps.append(f'[{title_input}:v]fps={fps},format=rgba,setpts=PTS+{round(title.start_time*fps)/fps}/TB[title_timed_{index}]')
            if title.behind_subject:
                from app.services.segmentation import existing_masks, mask_duration
                mask_directory = existing_masks(clip, plan.aspect_ratio, plan.fit_mode, mask_duration(plan, clip))
                mask_input = input_count
                inputs.extend(['-framerate',str(fps),'-i',str(mask_directory / '%05d.png')])
                input_count += 1
                filter_steps.append(f'[title_timed_{index}]split[title_rgb_{index}][title_a_{index}]')
                filter_steps.append(f'[title_a_{index}]alphaextract[title_alpha_{index}]')
                filter_steps.append(f'[{mask_input}:v]scale={width}:{height},format=gray,setpts=PTS+{clip.start_time}/TB[person_{index}]')
                person_tag = f'person_{index}'
                for insert_index, insert in enumerate(plan.visual_inserts):
                    if insert.mode == 'background':
                        continue
                    from app.services.composition import insert_rect
                    begin, finish = insert.start_time, insert.start_time+insert.duration
                    next_person = f'person_layout_{index}_{insert_index}'
                    if insert.mode == 'split':
                        filter_steps.append(f'[{person_tag}]split[mask_original_{index}_{insert_index}][mask_small_{index}_{insert_index}]')
                        filter_steps.append(f'[mask_small_{index}_{insert_index}]scale={width//2}:{height//2},pad={width}:{height}:0:{height//4}:black[mask_split_{index}_{insert_index}]')
                        filter_steps.append(f"[mask_original_{index}_{insert_index}][mask_split_{index}_{insert_index}]blend=all_expr='if(gte(T,{begin})*lt(T,{finish}),B,A)'[{next_person}]")
                    else:
                        x,y,w,h = insert_rect(insert.mode,insert.position)
                        filter_steps.append(f"[{person_tag}]drawbox=x={round(x*width)}:y={round(y*height)}:w={round(w*width)}:h={round(h*height)}:color=black:t=fill:enable='gte(t,{begin})*lt(t,{finish})'[{next_person}]")
                    person_tag = next_person
                filter_steps.append(f"[title_alpha_{index}][{person_tag}]blend=all_expr='A*(1-B/255)'[occlusion_{index}]")
                filter_steps.append(f'[title_rgb_{index}][occlusion_{index}]alphamerge[{title_tag}]')
            else:
                filter_steps.append(f'[title_timed_{index}]null[{title_tag}]')
            st, et = title.start_time, min(title.start_time+title.duration, running_dur)
            filter_steps.append(f"[{prev_tag}][{title_tag}]overlay=0:0:eof_action=pass:enable='gte(t,{st})*lt(t,{et})'[title_out_{index}]")
            prev_tag = f'title_out_{index}'

        # Apply Dynamic Subtitles (Stage 4) via ASS burning
        from app.services.caption_frames import caption_events, caption_track
        def check_caption_cancelled():
            if status.status == 'cancelled':
                raise RuntimeError('Render cancelled.')
        events = caption_events(plan.subtitles, width, height, check_caption_cancelled)
        if events:
            track = caption_track(events, width, height, running_dur, job_dir / 'captions.ffconcat')
            inputs.extend(['-f','concat','-safe','0','-i',track])
            filter_steps.append(f'[{input_count}:v]fps={fps},format=rgba[caption_stream]')
            filter_steps.append(f'[{prev_tag}][caption_stream]overlay=0:0:eof_action=pass[vwithcaptions]')
            input_count += 1
            prev_tag = 'vwithcaptions'

        # Every stage is already on the frame grid. Do not pad/trim the final
        # composition: missing or extra frames must fail validation.
        output_frames = sum(clip_frames)
        status.progress = 75.0

        # Audio setup
        audio_file = audio_path
        if audio_file and not os.path.isabs(audio_file):
            audio_file = str(UPLOAD_DIR / Path(audio_file).name)

        if audio_file and not os.path.isfile(audio_file):
            raise FileNotFoundError("The selected soundtrack is missing.")
        has_audio = bool(audio_file)
        total_duration = output_frames / fps

        audio_tags = []
        for i, clip in enumerate(clips):
            source = _resolve_image_path(clip.image_url, image_paths)
            info = probe_media(Path(source)) if Path(source).suffix.lower() in VIDEO_EXTENSIONS else {}
            tag = f"source_audio_{i}"
            if info.get('has_audio'):
                inputs.extend(['-ss', str(clip.source_start), '-i', source])
                filter_steps.append(f"[{input_count}:a]aresample=48000:async=1:first_pts=0,"
                    f"aformat=sample_fmts=fltp:channel_layouts=stereo,volume={clip.volume},apad,"
                    f"atrim=end_sample={clip_frames[i] * 48000 // fps},asetpts=N/SR/TB[{tag}]")
                has_audio = True
            else:
                inputs.extend(['-f','lavfi','-t',str(clip_durations[i]),'-i','anullsrc=channel_layout=stereo:sample_rate=48000'])
                filter_steps.append(f"[{input_count}:a]aformat=sample_fmts=fltp,atrim=end_sample={clip_frames[i] * 48000 // fps},asetpts=N/SR/TB[{tag}]")
            input_count += 1
            audio_tags.append(tag)
        filter_steps.append(''.join(f'[{tag}]' for tag in audio_tags) + f'concat=n={len(audio_tags)}:v=0:a=1[asource]')
        mix_tags = ['asource']
        if audio_file:
            inputs.extend(['-i', str(audio_file)])
            # A photo montage's sole soundtrack retains full volume by default.
            gain = plan.music_volume if any(c.media_type == 'video' for c in clips) else 1
            filter_steps.append(f"[{input_count}:a]asetpts=PTS-STARTPTS,aresample=48000,volume={gain},apad,"
                f"atrim=duration={total_duration},afade=t=out:st={max(0,total_duration-1.5)}:d={min(1.5,total_duration)}[amusic]")
            input_count += 1
            mix_tags.append('amusic')
        if plan.list_sounds:
            from app.core.config import ASSET_DIR
            last_cue = -1
            for index, cue in enumerate(sorted(plan.sound_cues, key=lambda c: c.start_time)):
                if cue.muted or cue.volume <= 0 or cue.start_time >= total_duration or cue.start_time - last_cue < .18:
                    continue
                last_cue = cue.start_time
                inputs.extend(['-i', str(ASSET_DIR / 'sounds' / f'{cue.sound}.wav')])
                filter_steps.append(f"[{input_count}:a]aresample=48000,volume={cue.volume},"
                    f"adelay={round(cue.start_time*48000)}S:all=1[cue_{index}]")
                input_count += 1
                mix_tags.append(f'cue_{index}')
        filter_steps.append(''.join(f'[{tag}]' for tag in mix_tags) +
            # Limit the combined speech, music and cues without auto-amplifying it.
            f'amix=inputs={len(mix_tags)}:duration=longest:normalize=0,alimiter=limit=0.95:level=0:latency=1,'
            f'apad,atrim=duration={total_duration}[afinal]')
        a_map = '[afinal]'

        status.progress = 85.0

        # Single unified encoding pass directly to output
        fc = ";".join(filter_steps)
        cmd_unified = [
            FFMPEG_PATH,
            "-y",
            "-filter_complex_threads", "1",
            *inputs,
            "-filter_complex", fc,
            "-map", f"[{prev_tag}]",
            "-map", a_map,
            # Bound looping image overlays using the exact frame-grid duration.
            "-t", str(total_duration),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-enc_time_base:v", f"1/{fps}", "-fps_mode", "passthrough",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(final_output_path)
        ]

        res_final = _run_render(cmd_unified, job_id)
        if res_final.returncode != 0:
            err_diag = res_final.stderr[-4000:] if res_final.stderr else "Unknown error"
            raise RuntimeError(f"FFmpeg unified rendering failed (code {res_final.returncode}): {err_diag}")

        status.progress = 95.0

        # 7. Strict export validation
        _validate_rendered_video(
            final_output_path,
            width,
            height,
            has_audio=has_audio,
            expected_duration=timeline_duration,
            expected_frames=output_frames, fps=fps,
        )

        with _JOB_LOCK:
            if status.status == 'cancelled':
                return
            final_output_path.replace(EXPORT_DIR / output_filename)
            status.progress = 100.0
            status.status = "completed"
            status.output_url = f"/api/exports/{output_filename}"
            status.download_url = f"/api/render/{job_id}/download"

    except Exception as e:
        if status.status != 'cancelled':
            status.status = "failed"
        status.error = str(e)
        status.progress = 0.0
    finally:
        job_history.finished(job_id, status.status, status.output_url)
        # 8. Safe cleanup of intermediate clip files
        try:
            for f in job_dir.glob("clip_*.mp4"):
                f.unlink(missing_ok=True)
            for f in job_dir.glob('rayflow_*.mp4'):
                f.unlink(missing_ok=True)
            for f in job_dir.glob("*.png"):
                f.unlink(missing_ok=True)
            for f in job_dir.glob("*.ass"):
                f.unlink(missing_ok=True)
            for f in job_dir.glob('*.ffconcat'):
                f.unlink(missing_ok=True)
            if not any(job_dir.iterdir()):
                job_dir.rmdir()
        except Exception:
            pass

def _queued_render_worker(job_id, plan, image_filenames, audio_filename, job_dir):
    try:
        with _RENDER_SLOTS:
            _RENDER_DEADLINES[job_id] = time.monotonic() + RENDER_TIMEOUT_SECONDS
            _render_worker(job_id, plan, image_filenames, audio_filename, job_dir)
    finally:
        with _JOB_LOCK:
            _ACTIVE_RENDER_IDS.discard(job_id)
            _RENDER_DEADLINES.pop(job_id, None)


def start_render_job(
    plan: EditingPlan,
    image_filenames: List[str],
    audio_filename: Optional[str] = None
) -> str:
    """
    Initiates an asynchronous video render job.
    """
    job_id = uuid.uuid4().hex
    job_dir = EXPORT_DIR / f"job_{job_id}"
    status = RenderJobStatus(
        job_id=job_id,
        status="queued",
        progress=0.0,
        created_at=time.time()
    )
    with _JOB_LOCK:
        if len(_ACTIVE_RENDER_IDS) >= RENDER_QUEUE_LIMIT:
            raise ValueError('The render queue is full. Wait for an active render to finish.')
        for key, previous in list(_JOBS.items()):
            if key not in _ACTIVE_RENDER_IDS and time.time() - previous.created_at > 3600:
                _JOBS.pop(key, None)
        job_dir.mkdir(parents=True, exist_ok=True)
        job_history.created(job_id, 'render')
        _JOBS[job_id] = status
        _ACTIVE_RENDER_IDS.add(job_id)

    # Start worker in background thread
    t = threading.Thread(
        target=scoped_target(_queued_render_worker),
        args=(job_id, plan, image_filenames, audio_filename, job_dir),
        daemon=True
    )
    try:
        t.start()
    except RuntimeError:
        with _JOB_LOCK:
            _ACTIVE_RENDER_IDS.discard(job_id)
            status.status = 'failed'
            status.error = 'The render worker could not start. Retry when resources are available.'
        job_history.finished(job_id, 'failed')
        job_dir.rmdir()
        raise ValueError(status.error) from None

    return job_id
