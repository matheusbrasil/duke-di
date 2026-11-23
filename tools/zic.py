#!/usr/bin/env python3
"""Read, write and draw Zoom MS+ effect icons (.ZIC files).

Adapted verbatim in format behaviour from the supplied ms-plus-zic-icons guide.
Black pixels are ink (set bits); white pixels are paper (clear bits).
"""
import glob
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

MAGIC = b"ZBMP"
TABLE_LEN = 0x18


def decode(data):
    if data[:4] != MAGIC:
        raise ValueError("not a ZIC: magic is %r" % data[:4])
    (tlen,) = struct.unpack_from("<I", data, 4)
    sizes, off = [], 8
    while off + 4 <= 8 + tlen:
        w, h = struct.unpack_from("<HH", data, off)
        if w == 0 or h == 0:
            break
        sizes.append((w, h))
        off += 4
    flag_off = 8 + 4 * len(sizes)
    word = struct.unpack_from("<H", data, flag_off)[0] if flag_off + 2 <= 8 + tlen else 0
    pos, frames = 8 + tlen, []
    for w, h in sizes:
        stripes, n = (h + 7) // 8, w * ((h + 7) // 8)
        chunk = data[pos:pos + n]
        if len(chunk) != n:
            raise ValueError("truncated pixel data for %dx%d frame" % (w, h))
        img = Image.new("1", (w, h), 1)
        px = img.load()
        for s in range(stripes):
            for x in range(w):
                byte = chunk[s * w + x]
                for k in range(8):
                    y = s * 8 + k
                    if y < h and (byte >> k) & 1:
                        px[x, y] = 0
        frames.append(img)
        pos += n
    if pos != len(data):
        raise ValueError("file is %d bytes, frames end at %d" % (len(data), pos))
    return frames, word & 0xFF, word >> 8, tlen


def _grey(img):
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        rgba = img.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
    return img.convert("L")


def to_1bit(img):
    if img.mode == "1":
        return img
    return _grey(img).point(lambda v: 255 if v >= 128 else 0).convert("1")


def grey_count(img):
    return 0 if img.mode == "1" else sum(_grey(img).histogram()[1:255])


def encode(frames, invert=0, layout=0, table_len=TABLE_LEN):
    if not 4 * len(frames) + 2 <= table_len:
        raise ValueError("frame table too small for %d frames" % len(frames))
    head = bytearray(MAGIC + struct.pack("<I", table_len))
    table = bytearray(table_len)
    for i, f in enumerate(frames):
        struct.pack_into("<HH", table, 4 * i, f.size[0], f.size[1])
    struct.pack_into("<H", table, 4 * len(frames), (layout << 8) | (invert & 0xFF))
    body = bytearray()
    for f in frames:
        f = to_1bit(f)
        w, h, px = f.size[0], f.size[1], f.load()
        for s in range((h + 7) // 8):
            for x in range(w):
                byte = 0
                for k in range(8):
                    y = s * 8 + k
                    if y < h and px[x, y] == 0:
                        byte |= 1 << k
                body.append(byte)
    return bytes(head + table + body)


def _knob(n, r2, slot_w, slot_top):
    c, rows = n // 2, []
    for y in range(n):
        row = ""
        for x in range(n):
            dx, dy = x - c, y - c
            slot = abs(dx) <= slot_w and slot_top <= y <= c
            row += "#" if dx * dx + dy * dy <= r2 and not slot else "."
        rows.append(row)
    return tuple(rows)


KNOB_S = _knob(15, 40, 0, 3)
KNOB_L = _knob(21, 90, 1, 4)
DOT_S = ("..#####..", ".#######.", "#########", "#########", "#########", "#########", "#########", ".#######.", "..#####..")
DOT_L = ("...####...", ".########.", ".########.", "##########", "##########", "##########", "##########", ".########.", ".########.", "...####...")
DOT_A = (".#####.", "#######", "#######", "#######", "#######", "#######", ".#####.")


def _g(size, border, dot, knob_y, knob_xs, fsw, name, art):
    return dict(size=size, border=border, dot=dot, knob_y=knob_y, knob_xs=knob_xs, fsw=fsw, name=name, art=art)


GEOM = {
    "standard": (
        _g((72, 97), 2, (31, 5, DOT_S), 25, (11, 27, 43, 59), (71, 170), (6, 35, 65, 49), (6, 51, 65, 76)),
        _g((102, 128), 3, (46, 7, DOT_L), 33, (16, 39, 62, 85), (104, 224), (8, 46, 93, 69), (8, 71, 93, 98)),
    ),
    "amp": (
        _g((97, 97), 2, (45, 3, DOT_A), 26, (18, 38, 58, 78), (96, 170), (6, 36, 90, 50), (6, 52, 90, 76)),
        _g((128, 128), 3, (59, 5, DOT_L), 33, (25, 51, 77, 103), (128, 222), (8, 46, 119, 69), (8, 71, 119, 97)),
    ),
    "wide80": (
        _g((102, 97), 2, None, 22, (20, 40, 60, 80), None, (6, 32, 95, 46), (6, 48, 95, 90)),
        _g((134, 128), 3, None, 30, (29, 54, 79, 104), None, (8, 43, 125, 66), (8, 68, 125, 119)),
    ),
}
KNOWN_SIZES = {tuple(g["size"] for g in v): k for k, v in GEOM.items()}
CORNER_CLEAR = {2: [(0, 0), (1, 0), (0, 1)], 3: [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (0, 2)]}
CORNER_INNER = {2: [(2, 2)], 3: [(3, 3)]}
FSW_RINGS = {2: [(132, 182), (46, 77)], 3: [(361, 520), (125, 219)]}


def _mirror(w, h, pts):
    out = set()
    for x, y in pts:
        out |= {(x, y), (w - 1 - x, y), (x, h - 1 - y), (w - 1 - x, h - 1 - y)}
    return out


def _border_w(h):
    return 2 if h < 100 else 3


def edge_sets(w, h, b):
    outside = _mirror(w, h, CORNER_CLEAR[b])
    border = {(x, y) for x in range(w) for y in range(h) if min(x, y, w - 1 - x, h - 1 - y) < b}
    return outside, (border - outside) | _mirror(w, h, CORNER_INNER[b])


def _stamp(px, glyph, x0, y0):
    for dy, row in enumerate(glyph):
        for dx, ch in enumerate(row):
            px[x0 + dx, y0 + dy] = 0 if ch == "#" else 255


def draw_furniture(g, footswitch=True, dot=True):
    w, h, b = g["size"][0], g["size"][1], g["border"]
    img = Image.new("L", (w, h), 255)
    px = img.load()
    for x, y in edge_sets(w, h, b)[1]:
        px[x, y] = 0
    if dot and g["dot"]:
        _stamp(px, g["dot"][2], g["dot"][0], g["dot"][1])
    knob, r = (KNOB_S if b == 2 else KNOB_L), (len(KNOB_S) // 2 if b == 2 else len(KNOB_L) // 2)
    for cx in g["knob_xs"]:
        _stamp(px, knob, cx - r, g["knob_y"] - r)
    if footswitch and g["fsw"]:
        cx2, cy2 = g["fsw"]
        for y in range(h):
            for x in range(w):
                d = (2 * x - cx2) ** 2 + (2 * y - cy2) ** 2
                if any(lo <= d <= hi for lo, hi in FSW_RINGS[b]):
                    px[x, y] = 0
    return img


def _font(font_file, size):
    if font_file:
        return ImageFont.truetype(font_file, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError as exc:
        raise ValueError("Pillow >=10.1 required unless --font is supplied") from exc


def _line(text, font, strikes, track):
    scratch = Image.new("L", (40 * len(text) + 80, 120), 0)
    d, x = ImageDraw.Draw(scratch), 20
    d.fontmode = "1"
    for ch in text:
        for k in range(strikes):
            d.text((x + k, 20), ch, font=font, fill=255)
        x += int(round(d.textlength(ch, font=font))) + strikes - 1 + track
    box = scratch.getbbox()
    return scratch.crop(box) if box else None


def draw_name(img, g, text, font_file=None, max_size=None):
    lines = [t for t in text.split("|") if t.strip()]
    x0, y0, x1, y1 = g["name"]
    if len(lines) > 1:
        y1 = g["art"][3]
    small, gap = g["border"] == 2, (2 if g["border"] == 2 else 3)
    for size in range(max_size or (20 if small else 28), 6, -1):
        font, strikes = _font(font_file, size), max(1, min(2 if small else 3, size // 5))
        for track in (1, 0):
            masks = [_line(t, font, strikes, track) for t in lines]
            if any(m is None for m in masks):
                raise ValueError("name %r has nothing to draw" % text)
            tw = max(m.size[0] for m in masks)
            th = sum(m.size[1] for m in masks) + gap * (len(masks) - 1)
            if tw > x1 - x0 + 1 or th > y1 - y0 + 1:
                continue
            y = top = y0 + ((y1 - y0 + 1 - th) // 2 if len(masks) == 1 else 0)
            for m in masks:
                img.paste(0, (x0 + (x1 - x0 + 1 - m.size[0]) // 2, y), m)
                y += m.size[1] + gap
            return size, top, y - gap - 1
    raise ValueError("name %r does not fit" % text)


def make_dark(light, gap=False):
    w, h = light.size
    b = _border_w(h)
    outside, border = edge_sets(w, h, b)
    gapset = _mirror(w, h, [(b + 1, b + 1)]) if gap else set()
    src = to_1bit(light).load()
    out = Image.new("1", (w, h), 1)
    px = out.load()
    for x in range(w):
        for y in range(h):
            if (x, y) in outside:
                px[x, y] = 1
            elif (x, y) in border:
                px[x, y] = 0
            elif gap and (min(x, y, w - 1 - x, h - 1 - y) == b or (x, y) in gapset):
                px[x, y] = 1
            else:
                px[x, y] = 0 if src[x, y] else 1
    return out


def lift(img, y0, y1):
    img, out = to_1bit(img), to_1bit(img).copy()
    out.paste(img.crop((0, y0, img.size[0], y1 + 1)), (0, y0 - 1))
    out.paste(img.crop((0, y0 - 1, img.size[0], y0)), (0, y1))
    return out


def lint(frames, invert, layout):
    notes, kind = [], KNOWN_SIZES.get(tuple(f.size for f in frames))
    if kind is None:
        return ["unusual frame sizes %s" % [f.size for f in frames]]
    if kind == "wide80" and layout == 0:
        notes.append("wide MS-80IR+ frames with layout 0")
    if kind != "wide80" and layout not in (0, 4):
        notes.append("layout %d on %s frames" % (layout, kind))
    for i, f in enumerate(frames):
        w, h, px = f.size[0], f.size[1], to_1bit(f).load()
        ink = sum(px[x, y] == 0 for x in range(w) for y in range(h)) / float(w * h)
        if ink > 0.6 and not invert:
            notes.append("frame %d mostly ink but invert=0" % i)
        if ink < 0.4 and invert:
            notes.append("frame %d mostly paper but invert=1" % i)
    return notes


def _arg(argv, flag, default=None):
    if flag in argv:
        i, val = argv.index(flag), argv[argv.index(flag) + 1]
        del argv[i:i + 2]
        return val
    return default


def _flag(argv, flag):
    if flag in argv:
        argv.remove(flag)
        return True
    return False


def _report(frames, invert, layout):
    for note in lint(frames, invert, layout):
        print("  note: " + note)


def main(argv):
    if not argv:
        return 2
    cmd, argv = argv[0], list(argv[1:])
    if cmd == "decode":
        scale = int(_arg(argv, "--scale", "1"))
        frames, inv, lay, _ = decode(open(argv[0], "rb").read())
        print("%s: %s invert=%d layout=%d" % (argv[0], [f.size for f in frames], inv, lay))
        for i, f in enumerate(frames):
            if scale > 1:
                f = f.resize((f.size[0] * scale, f.size[1] * scale), Image.Resampling.NEAREST)
            f.save("%s_%d.png" % (argv[1], i))
        return 0
    if cmd == "encode":
        dark, force = _flag(argv, "--dark"), _flag(argv, "--force")
        layout, rows = int(_arg(argv, "--layout", "0")), _arg(argv, "--lift")
        out, pngs = argv[0], argv[1:]
        frames = [Image.open(p) for p in pngs]
        if tuple(f.size for f in frames) not in KNOWN_SIZES and not force:
            raise ValueError("invalid ZIC frame sizes")
        if rows:
            frames[-1] = lift(frames[-1], *(int(v) for v in rows.split("-")))
        open(out, "wb").write(encode(frames, 1 if dark else 0, layout))
        print("%s: %d bytes, invert=%d layout=%d" % (out, os.path.getsize(out), dark, layout))
        _report(frames, 1 if dark else 0, layout)
        return 0
    if cmd == "template":
        geom, name, font = _arg(argv, "--geom", "standard"), _arg(argv, "--name"), _arg(argv, "--font")
        dark, gap = _flag(argv, "--dark"), _flag(argv, "--gap")
        nofsw, nodot = _flag(argv, "--no-footswitch"), _flag(argv, "--no-dot")
        layout = int(_arg(argv, "--layout", "3" if geom == "wide80" else "0"))
        prefix, frames = argv[0], []
        for g in GEOM[geom]:
            img = draw_furniture(g, footswitch=not nofsw, dot=not nodot)
            if name:
                draw_name(img, g, name, font)
            img = make_dark(img, gap) if dark else to_1bit(img)
            img.save("%s_%d.png" % (prefix, len(frames)))
            frames.append(img)
        open(prefix + ".ZIC", "wb").write(encode(frames, 1 if dark else 0, layout))
        print("%s.ZIC + %d PNGs, invert=%d layout=%d" % (prefix, len(frames), dark, layout))
        return 0
    if cmd == "darken":
        gap, prefix, pngs = _flag(argv, "--gap"), argv[0], argv[1:]
        for i, p in enumerate(pngs):
            make_dark(Image.open(p), gap).save("%s_%d.png" % (prefix, i))
        return 0
    if cmd == "check":
        bad = 0
        for p in argv:
            try:
                frames, inv, lay, _ = decode(open(p, "rb").read())
                print("OK   %s %s invert=%d layout=%d" % (p, [f.size for f in frames], inv, lay))
                _report(frames, inv, lay)
            except Exception as exc:
                print("BAD  %s: %s" % (p, exc))
                bad += 1
        return 1 if bad else 0
    if cmd == "roundtrip":
        bad = 0
        for p in sorted(glob.glob(os.path.join(argv[0], "*.ZIC"))):
            data = open(p, "rb").read()
            frames, inv, lay, tlen = decode(data)
            if encode(frames, inv, lay, tlen) != data:
                print("DIFF", p)
                bad += 1
        return 1 if bad else 0
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (IndexError, ValueError, OSError) as exc:
        print("error: %s" % exc)
        sys.exit(2)
