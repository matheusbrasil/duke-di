#!/usr/bin/env python3
"""Create the dark Duke DI ZIC icon and inspectable source PNG frames."""
from pathlib import Path
import sys

from PIL import ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zic  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "embedded" / "effects" / "duke" / "icon"


def draw_tube(img, g):
    """Draw a robust, deliberately simple 12AU7 symbol in the art area."""
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = g["art"]
    cx = (x0 + x1) // 2
    scale = 1 if g["border"] == 2 else 2

    # Glass envelope: rounded enough to read as a valve at thumbnail size.
    half = 10 * scale
    top = y0 + (1 * scale)
    bottom = min(y1 - (3 * scale), top + (17 * scale))
    left, right = cx - half, cx + half
    draw.rounded_rectangle((left, top, right, bottom), radius=4 * scale, outline=0, width=scale)

    # Twin-triode plates and common heater/grid.  These survive the LCD's 1-bit grid.
    plate_top, plate_bottom = top + 4 * scale, bottom - 5 * scale
    for centre in (cx - 4 * scale, cx + 4 * scale):
        draw.line((centre - scale, plate_top, centre - scale, plate_bottom), fill=0, width=scale)
        draw.line((centre + scale, plate_top, centre + scale, plate_bottom), fill=0, width=scale)
    draw.line((cx, plate_top - scale, cx, plate_bottom + scale), fill=0, width=scale)
    draw.line((left + 3 * scale, bottom - 2 * scale, right - 3 * scale, bottom - 2 * scale), fill=0, width=scale)

    # Pins identify it instantly as a tube rather than a generic bottle.
    pin_y0, pin_y1 = bottom + scale, min(y1, bottom + 4 * scale)
    for x in (cx - 5 * scale, cx - 2 * scale, cx + 2 * scale, cx + 5 * scale):
        draw.line((x, pin_y0, x, pin_y1), fill=0, width=scale)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, g in enumerate(zic.GEOM["standard"]):
        light = zic.draw_furniture(g)
        zic.draw_name(light, g, "DUKE DI")
        draw_tube(light, g)
        dark = zic.make_dark(light, gap=True)
        dark.save(OUT / f"duke_di_{i}.png")
        frames.append(dark)

    target = OUT / "MBDUKE.ZIC"
    target.write_bytes(zic.encode(frames, invert=1, layout=0))
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
