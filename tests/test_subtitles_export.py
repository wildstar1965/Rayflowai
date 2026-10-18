import os
import sys
import time
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.schemas.editing_plan import EditingPlan, ClipConfig, SubtitleSegment, WordTiming, SubtitleStyle, VisualInsert
from app.services.video_renderer import start_render_job, get_job_status
from app.core.config import UPLOAD_DIR, EXPORT_DIR

def test_subtitles_and_inserts_export():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Create 2 test images
    img1 = UPLOAD_DIR / "test_sub_1.jpg"
    img2 = UPLOAD_DIR / "test_sub_2.jpg"
    insert_img = UPLOAD_DIR / "test_insert.jpg"

    Image.new("RGB", (1080, 1920), color=(30, 40, 60)).save(img1)
    Image.new("RGB", (1080, 1920), color=(60, 30, 40)).save(img2)
    Image.new("RGB", (400, 400), color=(255, 120, 50)).save(insert_img)

    # 2. Build editing plan with dynamic subtitles and visual insert
    plan = EditingPlan(
        duration_seconds=4.0,
        aspect_ratio="9:16",
        clips=[
            ClipConfig(id="c1", image_url=str(img1), start_time=0.0, duration=2.0, motion="static"),
            ClipConfig(id="c2", image_url=str(img2), start_time=2.0, duration=2.0, motion="static")
        ],
        visual_inserts=[
            VisualInsert(
                id="ins-1",
                asset_id="asset-1",
                asset_url=str(insert_img),
                start_time=0.5,
                duration=1.5,
                mode="pip",
                position="top_right"
            )
        ],
        subtitles=[
            SubtitleSegment(
                id="sub-1",
                text="TRANSFORM YOUR FITNESS",
                start_time=0.2,
                end_time=1.8,
                words=[
                    WordTiming(word="TRANSFORM", start=0.2, end=0.7, emphasis=True),
                    WordTiming(word="YOUR", start=0.7, end=1.1, emphasis=False),
                    WordTiming(word="FITNESS", start=1.1, end=1.8, emphasis=True)
                ],
                style=SubtitleStyle(preset="bold_pop", caption_mode="word_by_word")
            ),
            SubtitleSegment(
                id="sub-2",
                text="RESULTS ARE GUARANTEED",
                start_time=2.0,
                end_time=3.8,
                words=[
                    WordTiming(word="RESULTS", start=2.0, end=2.6, emphasis=True),
                    WordTiming(word="ARE", start=2.6, end=3.0, emphasis=False),
                    WordTiming(word="GUARANTEED", start=3.0, end=3.8, emphasis=True)
                ],
                style=SubtitleStyle(preset="fitness_energy", caption_mode="phrase")
            )
        ]
    )

    t0 = time.time()
    job_id = start_render_job(plan, [str(img1), str(img2)], None)
    print(f"Started job: {job_id}")

    # Wait for completion
    for _ in range(40):
        st = get_job_status(job_id)
        if st.status in ("completed", "failed"):
            break
        time.sleep(0.5)

    duration = time.time() - t0
    final_st = get_job_status(job_id)
    print(f"Status: {final_st.status}, progress: {final_st.progress}%, error: {final_st.error}, elapsed: {duration:.2f}s")
    assert final_st.status == "completed", f"Render failed: {final_st.error}"
    assert final_st.output_url is not None

    out_file = EXPORT_DIR / f"rayflow_{job_id}.mp4"
    assert out_file.exists(), f"Output file does not exist: {out_file}"
    file_size = out_file.stat().st_size
    print(f"Output verified: {out_file} ({file_size} bytes)")
    assert file_size > 10000
    print("SUCCESS: Subtitles and Visual Inserts rendered into MP4 successfully!")

if __name__ == "__main__":
    test_subtitles_and_inserts_export()
