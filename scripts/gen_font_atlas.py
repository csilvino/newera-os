"""Generates a smooth anti-aliased proportional font atlas (16px + 26px) for Newera Bare-Metal OS."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CHARS = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~"
    "áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ°•–—"
)


def rasterize_font(font_path: str, size: int, prefix: str) -> str:
    font = ImageFont.truetype(font_path, size)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent

    glyph_meta = []
    bitmap_bytes = bytearray()

    for ch in CHARS:
        bbox = font.getbbox(ch)
        adv = max(1, int(round(font.getlength(ch))))
        if bbox is None:
            glyph_meta.append((ord(ch), 0, 0, 0, 0, adv, 0))
            continue
        x0, y0, x1, y1 = bbox
        w = max(1, x1 - x0)
        h = max(1, y1 - y0)
        img = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(img)
        draw.text((-x0, -y0), ch, fill=255, font=font)
        offset = len(bitmap_bytes)
        bitmap_bytes.extend(img.tobytes())
        glyph_meta.append((ord(ch), x0, y0, w, h, adv, offset))

    lines = [
        f"pub const {prefix}_LINE_HEIGHT: usize = {line_h};",
        f"pub const {prefix}_GLYPHS: &[GlyphMetric] = &[",
    ]
    for cp, xo, yo, w, h, adv, off in glyph_meta:
        lines.append(
            f"    GlyphMetric {{ codepoint: {cp}, x_off: {xo}, y_off: {yo}, width: {w}, height: {h}, advance: {adv}, offset: {off} }},"
        )
    lines.append("];")
    lines.append(f"pub const {prefix}_BITMAP: &[u8] = &[")
    for i in range(0, len(bitmap_bytes), 24):
        chunk = ", ".join(str(b) for b in bitmap_bytes[i : i + 24])
        lines.append(f"    {chunk},")
    lines.append("];")
    return "\n".join(lines)


def main() -> None:
    reg_path = r"C:\Windows\Fonts\segoeui.ttf"
    semi_path = r"C:\Windows\Fonts\seguisb.ttf"
    if not Path(semi_path).exists():
        semi_path = reg_path

    out = [
        "//! Auto-generated anti-aliased proportional font atlas (15px regular + 26px semibold).",
        "//! Supports full Portuguese accents and smooth 8-bit alpha blending in no_std bare-metal.",
        "",
        "#[derive(Clone, Copy)]",
        "pub struct GlyphMetric {",
        "    pub codepoint: u32,",
        "    pub x_off: i16,",
        "    pub y_off: i16,",
        "    pub width: u16,",
        "    pub height: u16,",
        "    pub advance: u16,",
        "    pub offset: usize,",
        "}",
        "",
        rasterize_font(reg_path, 15, "FONT_BODY"),
        "",
        rasterize_font(semi_path, 26, "FONT_TITLE"),
        "",
        "pub fn lookup(glyphs: &[GlyphMetric], ch: char) -> Option<&GlyphMetric> {",
        "    let cp = ch as u32;",
        "    glyphs.iter().find(|g| g.codepoint == cp)",
        "}",
        "",
    ]

    dest = Path(__file__).resolve().parent.parent / "microkernel" / "src" / "font_atlas.rs"
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"Generated {dest} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
