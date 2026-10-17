import sys
sys.path.insert(0, './backend')
from app.schemas.editing_plan import EditingPlan, ClipConfig, CommandRequest
from app.services.command_interpreter import interpret_command

initial_plan = EditingPlan(
    duration_seconds=8.0,
    aspect_ratio='9:16',
    fit_mode='fill',
    clips=[
        ClipConfig(id='clip-1', image_url='img1.jpg', start_time=0.0, duration=2.0, motion='zoom_in'),
        ClipConfig(id='clip-2', image_url='img2.jpg', start_time=2.0, duration=2.0, motion='zoom_out'),
        ClipConfig(id='clip-3', image_url='img3.jpg', start_time=4.0, duration=2.0, motion='zoom_in'),
        ClipConfig(id='clip-4', image_url='img4.jpg', start_time=6.0, duration=2.0, motion='zoom_out'),
    ]
)

test_commands = [
    "Add a fade-in transition between the second and third photos.",
    "Apply a crossfade between photos one and two.",
    "Make the transition between the third and fourth clips last one second.",
    "Fade out the second photo.",
    "Add a fade-in at the beginning of the entire reel.",
    "Fade out the video at the end.",
    "Replace the transition between photos two and three with a dip to black.",
    "Remove the transition between the first and second photos.",
    "Apply a 0.7-second crossfade between every adjacent photo.",
    "Change the video to landscape.",
    "Change the output ratio to square.",
    "Make the first photo last three seconds.",
    "Extend the third photo by two seconds.",
    "Move the last photo to the beginning.",
]

curr_plan = initial_plan
all_passed = True
for cmd in test_commands:
    req = CommandRequest(command=cmd, current_plan=curr_plan)
    res = interpret_command(req)
    if not res.applied_changes:
        print(f"FAILED: '{cmd}'")
        print("  Explanation:", res.explanation)
        all_passed = False
    else:
        print(f"PASSED: '{cmd}' -> {res.applied_changes[0]}")
    curr_plan = res.plan

print("\n--- Summary ---")
print("All commands passed:", all_passed)
if not all_passed:
    sys.exit(1)
