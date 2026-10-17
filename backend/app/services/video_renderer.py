import os
import subprocess
import uuid
import time
import threading
import re
from pathlib import Path
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from app.core.config import FFMPEG_PATH, EXPORT_DIR, UPLOAD_DIR
from app.schemas.editing_plan import EditingPlan, RenderJobStatus, ClipConfig, TransitionConfig

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
    gradient_colors: List[str]
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
    y = int(height * 0.42)

    # Soft dark glow behind text for contrast
    for offset in range(4, 0, -1):
        draw.text((x - offset, y - offset), text, font=font_main, fill=(0, 0, 0, 140))
        draw.text((x + offset, y + offset), text, font=font_main, fill=(0, 0, 0, 140))
        draw.text((x - offset, y + offset), text, font=font_main, fill=(0, 0, 0, 140))
        draw.text((x + offset, y - offset), text, font=font_main, fill=(0, 0, 0, 140))

    # Clean crisp monochrome text fill
    text_color = (255, 255, 255, 255)
    draw.text((x, y), text, font=font_main, fill=text_color)

    if subtitle:
        s_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw, sh = s_bbox[2] - s_bbox[0], s_bbox[3] - s_bbox[1]
        sx = (width - sw) // 2
        sy = y + th + 18
        draw.text((sx, sy), subtitle, font=font_sub, fill=(240, 240, 245, 220))

    img.save(output_png, "PNG")
    return output_png

def _validate_rendered_video(file_path: Path, expected_w: int, expected_h: int, has_audio: bool):
    """
    Validates output MP4 file exists, has content, matches requested dimensions, and has required streams.
    """
    if not file_path.exists() or file_path.stat().st_size < 1000:
        raise RuntimeError(f"Export validation failed: File is missing or empty ({file_path})")

    res = subprocess.run([FFMPEG_PATH, "-i", str(file_path)], capture_output=True, text=True)
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

def _resolve_image_path(img_path: str, fallback_paths: List[str]) -> str:
    p = Path(img_path)
    if p.is_file():
        return str(p.resolve())
    in_upload = UPLOAD_DIR / p.name
    if in_upload.is_file():
        return str(in_upload.resolve())
    for fb in fallback_paths:
        fb_p = Path(fb)
        if fb_p.is_file():
            return str(fb_p.resolve())
        fb_in_up = UPLOAD_DIR / fb_p.name
        if fb_in_up.is_file():
            return str(fb_in_up.resolve())
    raise FileNotFoundError(f"Could not find image file: {img_path}")

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

        # If clips not specified, generate default clips
        if not clips and image_paths:
            dur_per_img = max(1.5, plan.duration_seconds / len(image_paths))
            clips = [
                ClipConfig(
                    id=f"clip-{i}",
                    image_url=image_paths[i],
                    start_time=round(i * dur_per_img, 2),
                    duration=round(dur_per_img, 2),
                    motion="zoom_in" if i % 2 == 0 else "zoom_out",
                    transition="crossfade"
                )
                for i in range(len(image_paths))
            ]

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

        # 4. Render individual image clips
        for idx, clip in enumerate(clips):
            # Resolve image file
            img_file = _resolve_image_path(clip.image_url, image_paths)

            out_clip = str(job_dir / f"clip_{idx:03d}.mp4")
            clip_dur = max(0.5, clip.duration)
            clip_durations.append(clip_dur)
            total_frames = int(clip_dur * fps)

            # Motion configuration
            if fit_mode == "fill" and clip.motion in ("zoom_in", "zoom_out"):
                if clip.motion == "zoom_out":
                    zoom_expr = "zoom='min(1.15-0.001*on,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                else:
                    zoom_expr = "zoom='min(1.0+0.001*on,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                vf = (
                    f"{scale_filter},"
                    f"zoompan={zoom_expr}:d={total_frames}:s={width}x{height}:fps={fps}"
                    f"{color_filter},"
                    f"format=yuv420p"
                )
            else:
                vf = f"{scale_filter}{color_filter},format=yuv420p"

            cmd = [
                FFMPEG_PATH,
                "-y",
                "-loop", "1",
                "-t", str(clip_dur),
                "-i", img_file,
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                out_clip
            ]

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                # Fallback to simple static scale
                simple_vf = f"{scale_filter}{color_filter},format=yuv420p"
                cmd_fb = [
                    FFMPEG_PATH,
                    "-y",
                    "-loop", "1",
                    "-t", str(clip_dur),
                    "-i", img_file,
                    "-vf", simple_vf,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    out_clip
                ]
                res_fb = subprocess.run(cmd_fb, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res_fb.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed to render clip {idx}: {res_fb.stderr}")

            rendered_clip_files.append(out_clip)
            status.progress = 15.0 + (50.0 * (idx + 1) / total_clips)

        # 5. Composite clips with transitions
        # Determine boundary transitions between adjacent clips
        boundary_transitions: List[tuple] = []  # (transition_type, duration)
        has_active_transitions = False

        for i in range(len(clips) - 1):
            c_from = clips[i]
            c_to = clips[i + 1]

            # Find matching TransitionConfig
            matched_t = None
            if plan.transitions:
                for t in plan.transitions:
                    if t.from_clip_id == c_from.id and t.to_clip_id == c_to.id:
                        matched_t = t
                        break

            if matched_t and matched_t.enabled and matched_t.type != "none":
                t_type = matched_t.type
                t_dur = float(matched_t.duration)
                has_active_transitions = True
            elif c_from.transition and c_from.transition != "none":
                t_type = c_from.transition
                t_dur = 0.5
                has_active_transitions = True
            else:
                t_type = "none"
                t_dur = 0.001

            # Clamp transition duration to fit within adjacent clips
            max_dur = min(clip_durations[i], clip_durations[i + 1]) - 0.1
            t_dur = max(0.001, min(t_dur, max_dur, 2.0))
            boundary_transitions.append((t_type, t_dur))

        merged_video = str(job_dir / "merged_video.mp4")
        current_video_duration = sum(clip_durations)

        # Check global head/tail transitions
        has_head_fade = plan.head_transition and plan.head_transition.enabled and plan.head_transition.type != "none"
        has_tail_fade = plan.tail_transition and plan.tail_transition.enabled and plan.tail_transition.type != "none"

        if len(clips) == 1:
            # Single clip
            merged_video = rendered_clip_files[0]
            current_video_duration = clip_durations[0]
        elif not has_active_transitions and not has_head_fade and not has_tail_fade:
            # All direct cuts with no head/tail fades: Fast concat demuxer
            concat_txt = job_dir / "concat.txt"
            with open(concat_txt, "w", encoding="utf-8") as f:
                for c_file in rendered_clip_files:
                    f.write(f"file '{Path(c_file).as_posix()}'\n")

            concat_cmd = [
                FFMPEG_PATH,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_txt),
                "-c", "copy",
                merged_video
            ]
            subprocess.run(concat_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            # Build multi-input xfade filtergraph
            inputs = []
            for c_file in rendered_clip_files:
                inputs.extend(["-i", c_file])

            filter_steps = []
            prev_tag = "0:v"
            running_dur = clip_durations[0]

            for i in range(len(boundary_transitions)):
                t_type, t_dur = boundary_transitions[i]
                next_tag = f"{i + 1}:v"
                out_tag = f"vx{i + 1}"

                # Map transition name to FFmpeg xfade transition name
                if t_type == "crossfade":
                    xfade_trans = "fade"
                elif t_type == "dip_black":
                    xfade_trans = "fadeblack"
                elif t_type == "dip_white":
                    xfade_trans = "fadewhite"
                elif t_type in ("fade_in", "fade_out"):
                    xfade_trans = "fadeblack"
                else:  # none
                    xfade_trans = "fade"
                    t_dur = 0.001

                offset = max(0.0, running_dur - t_dur)
                filter_steps.append(
                    f"[{prev_tag}][{next_tag}]xfade=transition={xfade_trans}:duration={t_dur:.3f}:offset={offset:.3f}[{out_tag}]"
                )
                prev_tag = out_tag
                running_dur = offset + clip_durations[i + 1]

            current_video_duration = running_dur

            # Apply head and tail fade if requested
            post_filters = []
            if has_head_fade:
                head_dur = min(plan.head_transition.duration, current_video_duration / 3)
                head_color = "white" if "white" in plan.head_transition.type else "black"
                post_filters.append(f"fade=t=in:st=0:d={head_dur:.2f}:color={head_color}")

            if has_tail_fade:
                tail_dur = min(plan.tail_transition.duration, current_video_duration / 3)
                tail_color = "white" if "white" in plan.tail_transition.type else "black"
                tail_start = max(0.0, current_video_duration - tail_dur)
                post_filters.append(f"fade=t=out:st={tail_start:.2f}:d={tail_dur:.2f}:color={tail_color}")

            if post_filters:
                filter_steps.append(f"[{prev_tag}]{','.join(post_filters)}[vfinal]")
                final_map = "[vfinal]"
            else:
                final_map = f"[{prev_tag}]"

            fc = ";".join(filter_steps)
            trans_cmd = [
                FFMPEG_PATH,
                "-y",
                *inputs,
                "-filter_complex", fc,
                "-map", final_map,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                merged_video
            ]
            res_trans = subprocess.run(trans_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_trans.returncode != 0:
                raise RuntimeError(f"FFmpeg transition compositing failed: {res_trans.stderr}")

        status.progress = 75.0

        # 6. Apply head/tail fade if single clip had them
        if len(clips) == 1 and (has_head_fade or has_tail_fade):
            faded_video = str(job_dir / "faded_video.mp4")
            fade_list = []
            if has_head_fade:
                head_dur = min(plan.head_transition.duration, current_video_duration / 3)
                head_color = "white" if "white" in plan.head_transition.type else "black"
                fade_list.append(f"fade=t=in:st=0:d={head_dur:.2f}:color={head_color}")
            if has_tail_fade:
                tail_dur = min(plan.tail_transition.duration, current_video_duration / 3)
                tail_color = "white" if "white" in plan.tail_transition.type else "black"
                tail_start = max(0.0, current_video_duration - tail_dur)
                fade_list.append(f"fade=t=out:st={tail_start:.2f}:d={tail_dur:.2f}:color={tail_color}")

            fade_cmd = [
                FFMPEG_PATH,
                "-y",
                "-i", merged_video,
                "-vf", ",".join(fade_list),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                faded_video
            ]
            res_fade = subprocess.run(fade_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res_fade.returncode == 0:
                merged_video = faded_video

        # 7. Title overlay preparation
        final_video_with_title = merged_video
        if plan.title and plan.title.enabled and plan.title.text:
            title_png = str(job_dir / "title_overlay.png")
            create_title_overlay(
                text=plan.title.text,
                subtitle=plan.title.subtitle,
                width=width,
                height=height,
                output_png=title_png,
                gradient_colors=plan.title.gradient
            )

            titled_video = str(job_dir / "titled_video.mp4")
            # Show title with smooth fade-in and fade-out over first 4 seconds
            overlay_vf = "overlay=0:0:enable='between(t,0.3,4.5)'"
            title_cmd = [
                FFMPEG_PATH,
                "-y",
                "-i", merged_video,
                "-i", title_png,
                "-filter_complex", overlay_vf,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                titled_video
            ]
            res_title = subprocess.run(title_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res_title.returncode == 0:
                final_video_with_title = titled_video

        status.progress = 85.0

        # 8. Audio muxing and final container export
        output_filename = f"rayflow_{job_id}.mp4"
        final_output_path = EXPORT_DIR / output_filename
        total_duration = round(current_video_duration, 2)

        audio_file = audio_path
        if audio_file and not os.path.isabs(audio_file):
            audio_file = str(UPLOAD_DIR / Path(audio_file).name)

        has_audio = bool(audio_file and os.path.exists(audio_file))

        if has_audio:
            # Audio fade out at the end
            fade_out_start = max(1.0, total_duration - 1.5)
            audio_filter = f"afade=t=out:st={fade_out_start:.2f}:d=1.5"

            final_cmd = [
                FFMPEG_PATH,
                "-y",
                "-ss", "0",
                "-t", str(total_duration),
                "-i", final_video_with_title,
                "-ss", "0",
                "-t", str(total_duration),
                "-i", audio_file,
                "-af", audio_filter,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(final_output_path)
            ]
        else:
            # Silent audio track
            final_cmd = [
                FFMPEG_PATH,
                "-y",
                "-ss", "0",
                "-t", str(total_duration),
                "-i", final_video_with_title,
                "-f", "lavfi",
                "-t", str(total_duration),
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(final_output_path)
            ]

        res_final = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_final.returncode != 0:
            raise RuntimeError(f"FFmpeg final muxing failed: {res_final.stderr}")

        status.progress = 95.0

        # 9. Strict export validation
        _validate_rendered_video(final_output_path, width, height, has_audio=has_audio)

        status.progress = 100.0
        status.status = "completed"
        status.output_url = f"/api/exports/{output_filename}"
        status.download_url = f"/api/render/{job_id}/download"

    except Exception as e:
        status.status = "failed"
        status.error = str(e)
        status.progress = 0.0

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
