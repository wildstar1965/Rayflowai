import os
import sys
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.schemas.editing_plan import (
    EditingPlan,
    ClipConfig,
    SubtitleSegment,
    WordTiming,
    SubtitleStyle,
    CommandRequest
)
from app.services.ollama_client import check_ollama_status, interpret_with_ollama
from app.services.visual_inserts import suggest_contextual_inserts, extract_transcript_keywords
from app.services.command_interpreter import interpret_command
from app.core.config import UPLOAD_DIR

class TestAutoEditAndOllama(unittest.TestCase):
    def test_ollama_offline_resilience(self):
        """Ollama client should handle offline server without raising exceptions"""
        status = check_ollama_status(host="http://127.0.0.1:9999", timeout=0.5)
        self.assertFalse(status.available)
        self.assertEqual(len(status.models), 0)

        plan = EditingPlan(clips=[ClipConfig(id="c1", image_url="img1.jpg", start_time=0.0, duration=2.0)])
        res = interpret_with_ollama("make it 16:9", plan, host="http://127.0.0.1:9999")
        self.assertIsNone(res)

    def test_contextual_visual_inserts_matching(self):
        """Contextual visual inserts matches transcript keywords to available images"""
        subs = [
            SubtitleSegment(
                id="s1",
                text="Focus on your protein intake and daily workout",
                start_time=1.0,
                end_time=3.5,
                words=[
                    WordTiming(word="Focus", start=1.0, end=1.3),
                    WordTiming(word="protein", start=1.4, end=1.9, emphasis=True),
                    WordTiming(word="workout", start=2.5, end=3.2, emphasis=True)
                ]
            )
        ]
        assets = [
            {"id": "a1", "filename": "protein_shake.jpg", "url": "/media/protein_shake.jpg"},
            {"id": "a2", "filename": "gym_workout.jpg", "url": "/media/gym_workout.jpg"},
            {"id": "a3", "filename": "unrelated.jpg", "url": "/media/unrelated.jpg"}
        ]

        suggested = suggest_contextual_inserts(subs, assets, default_mode="pip")
        self.assertGreaterEqual(len(suggested), 1)
        # Should match protein_shake to 'protein'
        self.assertTrue(any("protein" in ins.asset_url for ins in suggested))

    def test_nl_commands_regression(self):
        """Verify natural language commands from prompt requirements"""
        # Create plan with 8 clips
        clips = [
            ClipConfig(id=f"c{i+1}", image_url=f"img{i+1}.jpg", start_time=float(i*2), duration=2.0)
            for i in range(8)
        ]
        plan = EditingPlan(clips=clips, subtitles=[
            SubtitleSegment(
                id="sub1",
                text="The secret to massive results",
                start_time=0.0,
                end_time=3.0,
                words=[
                    WordTiming(word="The", start=0.0, end=0.3),
                    WordTiming(word="secret", start=0.3, end=0.8),
                    WordTiming(word="to", start=0.8, end=1.0),
                    WordTiming(word="massive", start=1.0, end=1.6),
                    WordTiming(word="results", start=1.6, end=2.4)
                ]
            )
        ])

        # 1. "Make the second image last three seconds."
        req1 = CommandRequest(command="Make the second image last three seconds.", current_plan=plan)
        res1 = interpret_command(req1)
        self.assertEqual(res1.plan.clips[1].duration, 3.0)

        # 2. "Move the fifth photo to the beginning."
        req2 = CommandRequest(command="Move the fifth photo to the beginning.", current_plan=res1.plan)
        res2 = interpret_command(req2)
        self.assertEqual(res2.plan.clips[0].id, "c5")

        # 3. "Add a fade-in between the second and third photos."
        req3 = CommandRequest(command="Add a fade-in between the second and third photos.", current_plan=res2.plan)
        res3 = interpret_command(req3)
        self.assertTrue(any(t.type == "fade_in" for t in res3.plan.transitions))

        # 4. "Emphasize important words."
        req4 = CommandRequest(command="Emphasize important words.", current_plan=res3.plan)
        res4 = interpret_command(req4)
        sub_words = res4.plan.subtitles[0].words
        # 'secret', 'massive', 'results' are high-energy keywords and should be emphasized
        emphasized = [w.word for w in sub_words if w.emphasis]
        self.assertIn("secret", emphasized)
        self.assertIn("results", emphasized)

        # 5. "Remove the eighth photo." (Preserved fix regression test)
        req5 = CommandRequest(command="Remove the eighth photo.", current_plan=res4.plan)
        res5 = interpret_command(req5)
        self.assertEqual(len(res5.plan.clips), 7)

        # 6. "Turn this talking-head video into a dynamic reel."
        req6 = CommandRequest(command="Turn this talking-head video into a dynamic reel.", current_plan=res5.plan)
        res6 = interpret_command(req6)
        self.assertEqual(res6.plan.aspect_ratio, "9:16")
        self.assertEqual(res6.plan.subtitles[0].style.preset, "bold_pop")
        self.assertEqual(res6.plan.subtitles[0].style.caption_mode, "word_by_word")

if __name__ == "__main__":
    unittest.main()
