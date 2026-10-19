from PIL import Image, ImageSequence
from pathlib import Path

input_gif = Path("assets/walk out.gif")
output_gif = Path("assets/walk in.gif")

gif = Image.open(input_gif)

frames = []
durations = []

for frame in ImageSequence.Iterator(gif):

    frame = frame.convert("RGBA")

    # Horizontal flip
    frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    frames.append(frame)

    durations.append(
        frame.info.get(
            "duration",
            gif.info.get("duration", 100)
        )
    )

frames[0].save(
    output_gif,
    save_all=True,
    append_images=frames[1:],
    duration=durations,
    loop=gif.info.get("loop", 0),
    disposal=2,
)

print("✅ Saved:", output_gif)