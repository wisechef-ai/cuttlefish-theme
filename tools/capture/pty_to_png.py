"""pyte screen (+SGR colours) -> PNG. Block elements are drawn as geometry (like VTE/iTerm2), not font glyphs."""
from PIL import Image, ImageDraw, ImageFont

CW, CH = 9, 18
NAMED = {"black": (0, 0, 0), "red": (205, 49, 49), "green": (13, 188, 121), "brown": (229, 229, 16),
         "blue": (36, 114, 200), "magenta": (188, 63, 188), "cyan": (17, 168, 205), "white": (229, 229, 229),
         "brightblack": (102, 102, 102), "brightred": (241, 76, 76), "brightgreen": (35, 209, 139),
         "brightbrown": (245, 245, 67), "brightblue": (59, 142, 234), "brightmagenta": (214, 112, 214),
         "brightcyan": (41, 184, 219), "brightwhite": (255, 255, 255)}


def _rgb(c, default):
    if c == "default":
        return default
    if c in NAMED:
        return NAMED[c]
    if len(c) == 6:
        try:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


# block element -> list of filled rectangles as fractions (x0,y0,x1,y1)
BLOCKS = {"█": [(0, 0, 1, 1)], "▀": [(0, 0, 1, .5)], "▄": [(0, .5, 1, 1)], "▌": [(0, 0, .5, 1)], "▐": [(.5, 0, 1, 1)],
          "▖": [(0, .5, .5, 1)], "▗": [(.5, .5, 1, 1)], "▘": [(0, 0, .5, .5)], "▝": [(.5, 0, 1, .5)],
          "▙": [(0, 0, .5, 1), (.5, .5, 1, 1)], "▛": [(0, 0, 1, .5), (0, .5, .5, 1)],
          "▜": [(0, 0, 1, .5), (.5, .5, 1, 1)], "▟": [(.5, 0, 1, 1), (0, .5, .5, 1)],
          "▚": [(0, 0, .5, .5), (.5, .5, 1, 1)], "▞": [(.5, 0, 1, .5), (0, .5, .5, 1)]}


def render_png(screen, path, bg=(18, 18, 24), fg=(220, 220, 220)):
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    img = Image.new("RGB", (screen.columns * CW, screen.lines * CH), bg)
    d = ImageDraw.Draw(img)
    for y in range(screen.lines):
        row = screen.buffer[y]
        for x in range(screen.columns):
            c = row[x]
            f, b = _rgb(c.fg, fg), _rgb(c.bg, bg)
            if c.reverse:
                f, b = b, f
            px, py = x * CW, y * CH
            if b != bg:
                d.rectangle([px, py, px + CW - 1, py + CH - 1], fill=b)
            ch = c.data
            if ch in BLOCKS:
                for x0, y0, x1, y1 in BLOCKS[ch]:
                    d.rectangle([px + round(x0 * CW), py + round(y0 * CH), px + round(x1 * CW) - 1, py + round(y1 * CH) - 1], fill=f)
            elif ch.strip():
                d.text((px, py), ch, font=font, fill=f)
    img.save(path)
    return path
