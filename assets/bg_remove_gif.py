from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence


# ============================================================
# SETTINGS
# ============================================================

INPUT_GIF = Path("assets/happy mode.gif")
OUTPUT_GIF = Path("assets/happy mode transparent.gif")

# Background checkerboard grayscale hai, isliye R/G/B usually close honge.
# Agar grid residue bache toh 18 ko 25 karo.
NEUTRAL_TOLERANCE = 18

# Character edge ke around 1-pixel grey/white outline remove karne ke liye.
# Normally 1 enough hai. Character cut ho toh 0 kar do.
EDGE_CLEANUP_PASSES = 1

# Debug PNG frames save karne hain ya nahi
SAVE_DEBUG_FRAMES = True
DEBUG_FOLDER = Path("assets/debug_transparent_frames")


# ============================================================
# BACKGROUND DETECTION
# ============================================================

def is_neutral_pixel(rgb, tolerance=18):
    """
    Checkerboard grey, black aur white pixels mein R, G, B values
    approximately equal hoti hain.

    Examples:
        (150, 150, 150) -> neutral background
        (10, 10, 9)     -> neutral background
        (245, 245, 245)  -> neutral background/grid line
        (20, 35, 70)     -> navy character, neutral nahi
        (15, 140, 220)   -> blue water effect, neutral nahi
    """

    r, g, b = map(int, rgb)

    return (
        max(r, g, b) - min(r, g, b)
        <= tolerance
    )


def create_border_background_mask(
    rgba_array,
    neutral_tolerance=18,
):
    """
    Image border se connected neutral pixels ko background maankar
    mask create karta hai.

    8-direction flood fill use hota hai, jisse diagonal checkerboard
    cells aur thin grid lines bhi connect ho sakein.
    """

    height, width = rgba_array.shape[:2]
    rgb = rgba_array[:, :, :3]

    neutral = (
        np.max(rgb, axis=2).astype(np.int16)
        - np.min(rgb, axis=2).astype(np.int16)
        <= neutral_tolerance
    )

    background = np.zeros(
        (height, width),
        dtype=bool,
    )

    visited = np.zeros(
        (height, width),
        dtype=bool,
    )

    queue = deque()

    def add_border_pixel(x, y):
        if visited[y, x]:
            return

        # Only neutral border pixels background traversal start karenge
        if neutral[y, x]:
            queue.append((x, y))

    # Top and bottom borders
    for x in range(width):
        add_border_pixel(x, 0)
        add_border_pixel(x, height - 1)

    # Left and right borders
    for y in range(height):
        add_border_pixel(0, y)
        add_border_pixel(width - 1, y)

    directions = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )

    while queue:
        x, y = queue.popleft()

        if visited[y, x]:
            continue

        visited[y, x] = True

        if not neutral[y, x]:
            continue

        background[y, x] = True

        for dx, dy in directions:
            nx = x + dx
            ny = y + dy

            if (
                0 <= nx < width
                and 0 <= ny < height
                and not visited[ny, nx]
                and neutral[ny, nx]
            ):
                queue.append((nx, ny))

    return background, neutral


def clean_background_edges(
    background_mask,
    neutral_mask,
    passes=1,
):
    """
    Flood-filled background ke immediately adjacent neutral pixels ko
    remove karta hai.

    Isse character ke around bachne wali white/grey grid outline clean
    hoti hai.
    """

    cleaned = background_mask.copy()

    height, width = cleaned.shape

    directions = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )

    for _ in range(passes):
        expanded = cleaned.copy()

        background_y, background_x = np.where(cleaned)

        for y, x in zip(background_y, background_x):
            for dx, dy in directions:
                nx = x + dx
                ny = y + dy

                if (
                    0 <= nx < width
                    and 0 <= ny < height
                    and neutral_mask[ny, nx]
                ):
                    expanded[ny, nx] = True

        cleaned = expanded

    return cleaned


# ============================================================
# FRAME PROCESSING
# ============================================================

def remove_checkerboard_from_frame(
    frame,
    neutral_tolerance=18,
    edge_cleanup_passes=1,
):
    rgba_frame = frame.convert("RGBA")
    rgba_array = np.array(rgba_frame)

    background_mask, neutral_mask = (
        create_border_background_mask(
            rgba_array,
            neutral_tolerance=neutral_tolerance,
        )
    )

    if edge_cleanup_passes > 0:
        background_mask = clean_background_edges(
            background_mask,
            neutral_mask,
            passes=edge_cleanup_passes,
        )

    output_array = rgba_array.copy()

    # Detected background fully transparent
    output_array[background_mask, 3] = 0

    # Transparent pixels ka RGB bhi zero karo.
    # Isse GIF edge halos reduce hote hain.
    output_array[background_mask, 0] = 0
    output_array[background_mask, 1] = 0
    output_array[background_mask, 2] = 0

    output_image = Image.fromarray(
        output_array,
        mode="RGBA",
    )

    removed_pixels = int(
        np.count_nonzero(background_mask)
    )

    return output_image, removed_pixels


# ============================================================
# GIF TRANSPARENCY CONVERSION
# ============================================================

def convert_rgba_to_gif_frame(rgba_frame):
    """
    RGBA image ko GIF-compatible paletted frame mein convert karta hai.

    Palette index 255 transparency ke liye reserve hota hai.
    """

    rgba_frame = rgba_frame.convert("RGBA")

    rgba_array = np.array(rgba_frame)
    alpha_array = rgba_array[:, :, 3]

    rgb_image = Image.fromarray(
        rgba_array[:, :, :3],
        mode="RGB",
    )

    # 255 visible colors, index 255 transparency ke liye
    palette_frame = rgb_image.quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )

    indexed_array = np.array(
        palette_frame,
        dtype=np.uint8,
    )

    indexed_array[alpha_array == 0] = 255

    output_frame = Image.fromarray(
        indexed_array,
        mode="P",
    )

    source_palette = (
        palette_frame.getpalette() or []
    )

    source_palette = source_palette[:765]

    while len(source_palette) < 765:
        source_palette.extend([0, 0, 0])

    # Transparency index 255 ka RGB
    source_palette.extend([0, 0, 0])

    output_frame.putpalette(
        source_palette[:768]
    )

    output_frame.info["transparency"] = 255
    output_frame.info["disposal"] = 2

    return output_frame


# ============================================================
# MAIN FUNCTION
# ============================================================

def remove_background_and_rebuild_gif(
    input_path,
    output_path=None,
    neutral_tolerance=18,
    edge_cleanup_passes=1,
    save_debug_frames=True,
):
    input_path = Path(input_path).resolve()

    if not input_path.exists():
        raise FileNotFoundError(
            f"Input GIF nahi mili:\n{input_path}"
        )

    if output_path is None:
        output_path = input_path.with_name(
            f"{input_path.stem} transparent.gif"
        )
    else:
        output_path = Path(output_path).resolve()

    if save_debug_frames:
        DEBUG_FOLDER.mkdir(
            parents=True,
            exist_ok=True,
        )

    print("=" * 65)
    print("CHECKERBOARD GIF BACKGROUND REMOVAL")
    print("=" * 65)
    print(f"Input : {input_path}")
    print(f"Output: {output_path}")
    print()

    source_gif = Image.open(input_path)

    total_frames = getattr(
        source_gif,
        "n_frames",
        1,
    )

    default_duration = source_gif.info.get(
        "duration",
        100,
    )

    loop_value = source_gif.info.get(
        "loop",
        0,
    )

    output_frames = []
    durations = []

    for frame_number, source_frame in enumerate(
        ImageSequence.Iterator(source_gif),
        start=1,
    ):
        duration = source_frame.info.get(
            "duration",
            default_duration,
        )

        durations.append(duration)

        transparent_frame, removed_pixels = (
            remove_checkerboard_from_frame(
                source_frame,
                neutral_tolerance=neutral_tolerance,
                edge_cleanup_passes=edge_cleanup_passes,
            )
        )

        if save_debug_frames:
            debug_path = (
                DEBUG_FOLDER
                / f"frame_{frame_number:02d}.png"
            )

            transparent_frame.save(debug_path)

        gif_frame = convert_rgba_to_gif_frame(
            transparent_frame
        )

        output_frames.append(gif_frame)

        print(
            f"Frame {frame_number}/{total_frames}: "
            f"{removed_pixels:,} background pixels removed"
        )

    if not output_frames:
        raise RuntimeError(
            "GIF se koi frame read nahi hua."
        )

    print()
    print("saving Transparent background gifs...")

    output_frames[0].save(
        output_path,
        save_all=True,
        append_images=output_frames[1:],
        duration=durations,
        loop=loop_value,
        disposal=2,
        transparency=255,
        optimize=False,
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Output create nahi hui:\n{output_path}"
        )

    print()
    print("=" * 65)
    print("DONE")
    print("=" * 65)
    print(f"Saved GIF: {output_path}")
    print(
        f"Size: "
        f"{output_path.stat().st_size / 1024:.2f} KB"
    )

    if save_debug_frames:
        print(
            f"Debug PNG frames: "
            f"{DEBUG_FOLDER.resolve()}"
        )

    return output_path


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    gifs = [
        "walk in.gif",
        "reminder mode.gif",
        "happy mode.gif",
        "sad mode.gif",
        "hydration legend mode.gif",
    ]

    for gif_name in gifs:

        input_path = Path("assets") / gif_name

        output_path = (
            Path("assets")
            / gif_name.replace(
                ".gif",
                " transparent.gif"
            )
        )

        print()
        print("=" * 80)
        print(f"Processing: {gif_name}")
        print("=" * 80)

        remove_background_and_rebuild_gif(
            input_path=input_path,
            output_path=output_path,
            neutral_tolerance=NEUTRAL_TOLERANCE,
            edge_cleanup_passes=EDGE_CLEANUP_PASSES,
            save_debug_frames=False,
        )

    print()
    print("🎉 All GIFs completed!")