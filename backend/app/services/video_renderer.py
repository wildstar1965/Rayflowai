import os
import subprocess
import uuid
import time
import threading
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from app.services.media import probe_media, VIDEO_EXTENSIONS
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from app.core.config import FFMPEG_PATH, EXPORT_DIR, UPLOAD_DIR
from app.schemas.editing_plan import EditingPlan, RenderJobStatus, ClipConfig, TransitionConfig, SubtitleSegment, SubtitleStyle, VisualInsert

# Active jobs registry
_JOBS: Dict[str, RenderJobStatus] = {}

def get_job_status(job_id: str) -> Optional[RenderJobStatus]:
    return _JOBS.get(job_id)

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
):
    """
    Validates output MP4 file exists, has content, matches requested dimensions, and has required streams.
    """
    if not file_path.exists() or file_path.stat().st_size < 1000:
        raise RuntimeError(f"Export validation failed: File is missing or empty ({file_path})")

    res = subprocess.run(
        [FFMPEG_PATH, "-hide_banner", "-i", str(file_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = res.stderr

    # Check video stream and dimensions
    dim_match = re.search(r'Stream #.*Video:.* ([0-9]{2,4})x([0-9]{2,4})', text)
    if not dim_match:
        raise RuntimeError("Export validation failed: Video stream not found in rendered file")

    actual_w = int(dim_match.group(1))
    actual_h = int(dim_match.group(2))
    if actual_w != expected_w or actual_h != expected_h:
        raise RuntimeError(
            f"Export validation failed: Expected {expected_w}x{expected_h}, but rendered file has {actual_w}x{actual_h}"
        )

    # Check audio stream if requested
    if has_audio and "Audio:" not in text:
        raise RuntimeError("Export validation failed: Expected audio stream not present in rendered file")

    # A valid stream probe alone does not catch truncated/frozen exports. Decode the
    # complete file and require a positive duration so partial MP4s cannot be marked
    # complete.
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not duration_match:
        raise RuntimeError("Export validation failed: Video duration could not be read")
    duration = (
        int(duration_match.group(1)) * 3600
        + int(duration_match.group(2)) * 60
        + float(duration_match.group(3))
    )
    if duration <= 0:
        raise RuntimeError("Export validation failed: Rendered video has no duration")
    if expected_duration is not None and abs(duration - expected_duration) > 0.25:
        raise RuntimeError(
            f"Export validation failed: Expected duration {expected_duration:.2f}s, "
            f"but rendered file has {duration:.2f}s"
        )

    decode = subprocess.run(
        [
            FFMPEG_PATH,
            "-v", "error", "-xerror",
            "-i", str(file_path),
            "-map", "0:v:0",
            "-progress", "pipe:1", "-nostats",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if decode.returncode != 0 or decode.stderr.strip():
        detail = decode.stderr[-500:] if decode.stderr else "unknown decode error"
        raise RuntimeError(f"Export validation failed: Video could not be decoded: {detail}")
    decoded_counts = re.findall(r"frame=(\d+)", decode.stdout)
    if expected_duration is not None and (not decoded_counts or int(decoded_counts[-1]) != round(expected_duration * 30)):
        raise RuntimeError("Export validation failed: Decoded frame count does not match the timeline.")

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
        status.status = "processing"
        status.progress = 5.0

        # 1. Output dimensions from aspect_ratio
        ratio = plan.aspect_ratio or "9:16"
        if ratio == "16:9":
            width, height = 1920, 1080
        elif ratio == "1:1":
            width, height = 1080, 1080
        else:  # "9:16"
            width, height = 1080, 1920

        fps = 30
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
            color_filter = ",eq=contrast=1.1:saturation=1.15"

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
        clip_durations: List[float] = []
        total_clips = len(clips)

        # 4. Render individual clips (images or video clips)
        for idx, clip in enumerate(clips):
            img_file = _resolve_image_path(clip.image_url, image_paths)
            out_clip = str(job_dir / f"clip_{idx:03d}.mp4")
            # Round cumulative boundaries, avoiding per-clip duration drift.
            total_frames = max(1, round((clip.start_time + clip.duration) * fps) - round(clip.start_time * fps))
            clip_dur = total_frames / fps
            clip_durations.append(clip_dur)
            is_video_file = clip.media_type == "video" or Path(img_file).suffix.lower() in VIDEO_EXTENSIONS
            if is_video_file:
                vf = (f"setpts=PTS-STARTPTS,{scale_filter},setsar=1,fps={fps},"
                      f"tpad=stop_mode=clone:stop_duration={clip_dur},trim=duration={clip_dur},"
                      f"setpts=PTS-STARTPTS{color_filter},format=yuv420p")
                input_args = ["-ss", str(clip.source_start), "-i", img_file]
            elif fit_mode == "fill" and clip.motion != "static":
                vf = build_motion_filter(width, height, fps, total_frames, clip.motion) + color_filter + ",format=yuv420p,setsar=1"
                input_args = ["-i", img_file]
            else:
                vf = f"{scale_filter}{color_filter},setsar=1,format=yuv420p"
                input_args = ["-loop", "1", "-framerate", str(fps), "-i", img_file]
            cmd = [FFMPEG_PATH, "-y", "-filter_threads", "1", *input_args,
                   "-vf", vf, "-frames:v", str(total_frames), "-an",
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-r", str(fps), out_clip]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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

            max_dur = max(0.1, min(clip_durations[i], clip_durations[i + 1]) - 0.1)
            t_dur = round(max(0.0, min(t_dur, max_dur, 2.0)) * fps) / fps
            boundary_transitions.append((t_type, t_dur))

        # Check global head/tail transitions
        has_head_fade = plan.head_transition and plan.head_transition.enabled and plan.head_transition.type != "none"
        has_tail_fade = plan.tail_transition and plan.tail_transition.enabled and plan.tail_transition.type != "none"

        # 6. Build UNIFIED compositing & muxing filtergraph
        # Combines transitions, head/tail fades, title overlay, and audio in a single pass
        output_filename = f"rayflow_{job_id}.mp4"
        final_output_path = EXPORT_DIR / output_filename

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
                f"[{i}:v]setsar=1,format=yuv420p,setpts=PTS-STARTPTS,fps={fps},settb=AVTB[{tag}]"
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
            filter_steps.append(f"{concat_ins}concat=n={len(clips)}:v=1:a=0[vconcat]")
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
                        f"[{prev_tag}][{next_tag}]concat=n=2:v=1:a=0,fps={fps},settb=AVTB[{out_tag}]"
                    )
                else:
                    transition = {"crossfade": "fade", "dip_black": "fadeblack",
                                  "dip_white": "fadewhite", "fade_in": "fadeblack",
                                  "fade_out": "fadeblack"}.get(t_type, "fade")
                    lead_tag = f"lead_{i + 1}"
                    filter_steps.append(
                        f"[{next_tag}]tpad=start_mode=clone:start_duration={t_dur:.6f},"
                        f"setpts=PTS-STARTPTS,fps={fps},settb=AVTB[{lead_tag}]"
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
                    et = min(running_dur, st + max(0.5, float(ins.duration)))

                    out_tag = f"vinsert_{v_idx}"
                    scaled_tag = f"sinsert_{v_idx}"

                    if ins.mode == "cutaway":
                        filter_steps.append(
                            f"[{ins_input_idx}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[{scaled_tag}]"
                        )
                        filter_steps.append(
                            f"[{prev_tag}][{scaled_tag}]overlay=0:0:enable='between(t,{st:.2f},{et:.2f})'[{out_tag}]"
                        )
                    elif ins.mode == "split":
                        hw = width // 2
                        filter_steps.append(
                            f"[{ins_input_idx}:v]scale={hw}:{height}:force_original_aspect_ratio=increase,crop={hw}:{height}[{scaled_tag}]"
                        )
                        filter_steps.append(
                            f"[{prev_tag}][{scaled_tag}]overlay={hw}:0:enable='between(t,{st:.2f},{et:.2f})'[{out_tag}]"
                        )
                    else:  # "pip" or "floating"
                        pip_w = int(width * 0.38)
                        filter_steps.append(
                            f"[{ins_input_idx}:v]scale={pip_w}:-1[scaled_raw_{v_idx}]"
                        )
                        filter_steps.append(
                            f"[scaled_raw_{v_idx}]pad=w=iw+8:h=ih+8:x=4:y=4:color=white[{scaled_tag}]"
                        )

                        if ins.position == "top_left":
                            ox, oy = str(int(width * 0.05)), str(int(height * 0.08))
                        elif ins.position == "bottom_right":
                            ox, oy = str(int(width * 0.57)), str(int(height * 0.70))
                        elif ins.position == "center":
                            ox, oy = "(W-w)/2", "(H-h)/2"
                        else:  # "top_right"
                            ox, oy = str(int(width * 0.57)), str(int(height * 0.08))

                        filter_steps.append(
                            f"[{prev_tag}][{scaled_tag}]overlay={ox}:{oy}:enable='between(t,{st:.2f},{et:.2f})'[{out_tag}]"
                        )

                    prev_tag = out_tag
                except Exception as e:
                    raise RuntimeError(f"Could not add visual insert {ins.id}: {e}") from e

        # Apply Dynamic Subtitles (Stage 4) via ASS burning
        if plan.subtitles and len(plan.subtitles) > 0:
            from app.services.subtitles import generate_ass_subtitles
            ass_path = str(job_dir / "subtitles.ass")
            generate_ass_subtitles(plan.subtitles, ass_path, width, height)
            escaped_ass = ass_path.replace('\\', '/').replace(':', '\\:')
            filter_steps.append(f"[{prev_tag}]subtitles='{escaped_ass}'[vwithsubs]")
            prev_tag = "vwithsubs"

        # Microsecond time bases at xfade boundaries can round away the last
        # frame. Quantize the final stream to the timeline's exact frame count;
        # Round at most one frame per clip boundary (never the overlap duration).
        output_frames = round(timeline_duration * fps)
        filter_steps.append(
            f"[{prev_tag}]fps=fps={fps}:eof_action=pass,tpad=stop_mode=clone:stop={len(clips)},"
            f"trim=end_frame={output_frames},setpts=N/({fps}*TB)[vexact]"
        )
        prev_tag = 'vexact'
        status.progress = 75.0

        # Audio setup
        audio_file = audio_path
        if audio_file and not os.path.isabs(audio_file):
            audio_file = str(UPLOAD_DIR / Path(audio_file).name)

        if audio_file and not os.path.isfile(audio_file):
            raise FileNotFoundError("The selected soundtrack is missing.")
        has_audio = bool(audio_file)
        total_duration = round(running_dur, 2)

        if has_audio:
            audio_input_idx = input_count
            inputs.extend(["-ss", "0", "-t", str(total_duration), "-i", str(audio_file)])
            input_count += 1
            fade_out_start = max(1.0, total_duration - 1.5)
            filter_steps.append(f"[{audio_input_idx}:a]asetpts=PTS-STARTPTS,apad,atrim=duration={total_duration},afade=t=out:st={max(0, total_duration - 1.5):.6f}:d={min(1.5, total_duration):.6f}[afinal]")
            a_map = "[afinal]"
        else:
            # Preserve source audio for video timelines, with silence in image slots.
            audio_tags = []
            for i, clip in enumerate(clips):
                source = _resolve_image_path(clip.image_url, image_paths)
                info = probe_media(Path(source)) if Path(source).suffix.lower() in VIDEO_EXTENSIONS else {}
                tag = f"source_audio_{i}"
                if info.get("has_audio"):
                    inputs.extend(["-ss", str(clip.source_start), "-i", source])
                    filter_steps.append(
                        f"[{input_count}:a]asetpts=PTS-STARTPTS,aresample=48000,"
                        f"aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                        f"atrim=duration={clip_durations[i]:.6f}[{tag}]"
                    )
                    has_audio = True
                else:
                    inputs.extend(["-f", "lavfi", "-t", str(clip_durations[i]),
                                   "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
                    filter_steps.append(f"[{input_count}:a]aformat=sample_fmts=fltp[{tag}]")
                input_count += 1
                audio_tags.append(tag)
            filter_steps.append("".join(f"[{tag}]" for tag in audio_tags) +
                                f"concat=n={len(audio_tags)}:v=0:a=1[afinal]")
            a_map = "[afinal]"

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
            "-t", str(total_duration),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(final_output_path)
        ]

        res_final = subprocess.run(cmd_unified, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
        )

        status.progress = 100.0
        status.status = "completed"
        status.output_url = f"/api/exports/{output_filename}"
        status.download_url = f"/api/render/{job_id}/download"

    except Exception as e:
        status.status = "failed"
        status.error = str(e)
        status.progress = 0.0
    finally:
        # 8. Safe cleanup of intermediate clip files
        try:
            for f in job_dir.glob("clip_*.mp4"):
                f.unlink(missing_ok=True)
            for f in job_dir.glob("*.png"):
                f.unlink(missing_ok=True)
            for f in job_dir.glob("*.ass"):
                f.unlink(missing_ok=True)
            if not any(job_dir.iterdir()):
                job_dir.rmdir()
        except Exception:
            pass

def start_render_job(
    plan: EditingPlan,
    image_filenames: List[str],
    audio_filename: Optional[str] = None
) -> str:
    """
    Initiates an asynchronous video render job.
    """
    job_id = str(uuid.uuid4())[:8]
    job_dir = EXPORT_DIR / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    status = RenderJobStatus(
        job_id=job_id,
        status="queued",
        progress=0.0,
        created_at=time.time()
    )
    _JOBS[job_id] = status

    # Start worker in background thread
    t = threading.Thread(
        target=_render_worker,
        args=(job_id, plan, image_filenames, audio_filename, job_dir),
        daemon=True
    )
    t.start()

    return job_id
