from pathlib import Path

from PIL import Image


def test_menubar_icon_is_template_ready():
    icon_path = Path("menubar_icon.png")
    assert icon_path.exists(), "menubar_icon.png is missing (menu bar icon needs a template PNG)."

    img = Image.open(icon_path).convert("RGBA")
    alpha = img.getchannel("A")
    alpha_min, _alpha_max = alpha.getextrema()
    assert alpha_min < 255, "menubar_icon.png has no transparency; template icons need alpha."

    pixels = list(img.getdata())
    step = max(1, len(pixels) // 200000)
    sample = pixels[::step]
    opaque = [(r, g, b) for r, g, b, a in sample if a > 0]
    assert opaque, "menubar_icon.png is fully transparent."

    avg_brightness = sum((r + g + b) / 3 for r, g, b in opaque) / len(opaque)
    assert avg_brightness < 200, "menubar_icon.png is too bright for a light menu bar."
