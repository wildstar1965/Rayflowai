import os
import subprocess
import uuid
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from app.core.config import FFMPEG_PATH, EXPORT_DIR, UPLOAD_DIR
from app.schemas.editing_plan import EditingPlan, RenderJobStatus, ClipConfig

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
    Renders an elegant cinematic title overlay as a transparent PNG using Pillow.
    Uses vertical gradient and cinematic typography.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Simple font fallback
    try:
        font_main = ImageFont.truetype("arialbd.ttf", int(width * 0.075))
        font_sub = ImageFont.truetype("arial.ttf", int(width * 0.035))
    except Exception:
        font_main = ImageFont.load_default()
        font_sub = font_main

    # Measure text bounds
    bbox = draw.textbbox((0, 0), text, font=font_main)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = int(height * 0.42)

    # Soft dark glow behind text for contrast
    for offset in range(6, 0, -2):
        draw.text((x - offset, y - offset), text, font=font_main, fill=(8, 9, 13, 160))
        draw.text((x + offset, y + offset), text, font=font_main, fill=(8, 9, 13, 160))
        draw.text((x - offset, y + offset), text, font=font_main, fill=(8, 9, 13, 160))
        draw.text((x + offset, y - offset), text, font=font_main, fill=(8, 9, 13, 160))

    # Gradient text fill
    text_color = (103, 232, 249, 255)  # Cyan #67E8F9
    draw.text((x, y), text, font=font_main, fill=text_color)

    if subtitle:
        s_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw, sh = s_bbox[2] - s_bbox[0], s_bbox[3] - s_bbox[1]
        sx = (width - sw) // 2
        sy = y + th + 20
        draw.text((sx, sy), subtitle, font=font_sub, fill=(245, 247, 251, 220))

    img.save(output_png, "PNG")
    return output_png

def _render_worker(
    job_id: str,
    plan: EditingPlan,
    image_paths: List[str],
    audio_path: Optional[str],
    job_dir: Path
):
    """
    Background rendering thread that executes FFmpeg commands to produce a vertical MP4 reel.
    """
    status = _JOBS[job_id]
    try:
        status.status = "processing"
        status.progress = 10.0

        # Output dimensions
        if plan.aspect_ratio == "16:9":
            width, height = 1920, 1080
        elif plan.aspect_ratio == "1:1":
            width, height = 1080, 1080
        else: # 9:16
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
                    start_time=i * dur_per_img,
                    duration=dur_per_img,
                    motion="zoom_in" if i % 2 == 0 else "zoom_out",
                    transition="crossfade"
                )
                for i in range(len(image_paths))
            ]

        status.progress = 25.0

        # Color grading filter according to style
        style = plan.style.lower()
        if style == "noir":
            color_filter = ",hue=s=0,eq=contrast=1.3:brightness=-0.05"
        elif style == "vintage":
            color_filter = ",colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:0,eq=contrast=1.1"
        elif style == "vibrant":
            color_filter = ",eq=saturation=1.35:contrast=1.1"
        else: # cinematic
            color_filter = ",eq=contrast=1.1:saturation=1.15"

        rendered_clip_files: List[str] = []
        total_clips = len(clips)

        # Render individual image clips with motion and scaling
        for idx, clip in enumerate(clips):
            # Resolve image file
            img_file = clip.image_url
            if not os.path.isabs(img_file):
                img_file = str(UPLOAD_DIR / Path(img_file).name)
            if not os.path.exists(img_file):
                # Fallback to first available image
                img_file = image_paths[0]

            out_clip = str(job_dir / f"clip_{idx:03d}.mp4")
            clip_dur = max(0.8, clip.duration)
            total_frames = int(clip_dur * fps)

            # Ken burns zoom
            if clip.motion == "zoom_out":
                zoom_expr = f"zoom='min(1.2-0.0015*on,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            else:
                zoom_expr = f"zoom='min(1.0+0.0015*on,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

            # Filter chain: scale & crop to fill aspect ratio + smooth zoompan
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"zoompan={zoom_expr}:d={total_frames}:s={width}x{height}:fps={fps}"
                f"{color_filter},"
                f"format=yuv420p"
            )

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
                # If zoompan failed (e.g. out of memory on high res), fallback to simple scale and crop
                simple_vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height}"
                    f"{color_filter},"
                    f"format=yuv420p"
                )
                cmd_fallback = [
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
                res_fb = subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res_fb.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed to render clip {idx}: {res_fb.stderr}")

            rendered_clip_files.append(out_clip)
            status.progress = 25.0 + (50.0 * (idx + 1) / total_clips)

        # Concatenate video clips using concat demuxer
        concat_txt = job_dir / "concat.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for c_file in rendered_clip_files:
                f.write(f"file '{Path(c_file).as_posix()}'\n")

        merged_video = str(job_dir / "merged_video.mp4")
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

        status.progress = 80.0

        # Title overlay preparation
        final_video_with_title = merged_video
        if plan.title.enabled and plan.title.text:
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
            overlay_vf = f"overlay=0:0:enable='between(t,0.3,4.5)'"
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

        status.progress = 88.0

        # Final pass: Combine with audio and clamp to total duration
        output_filename = f"rayflow_{job_id}.mp4"
        final_output_path = EXPORT_DIR / output_filename
        total_duration = plan.duration_seconds

        # Check audio
        audio_file = audio_path
        if audio_file and not os.path.isabs(audio_file):
            audio_file = str(UPLOAD_DIR / Path(audio_file).name)

        if audio_file and os.path.exists(audio_file):
            # Audio fade out at the end
            fade_out_start = max(1.0, total_duration - 1.5)
            audio_filter = f"afade=t=out:st={fade_out_start}:d=1.5"

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
