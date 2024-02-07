def to_rgb(hex):
    hex = hex.lstrip("#")
    rgb = tuple(int(hex[i : i + 2], 16) for i in (0, 2, 4))
    return rgb


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def hex_to_rgb(value) -> tuple[int, int, int]:
    value = value.lstrip("#")
    lv = len(value)
    return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))


def shade_rgb_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    shade_factor = 0.2
    r = int(rgb[0] * (1 - shade_factor))
    g = int(rgb[1] * (1 - shade_factor))
    b = int(rgb[2] * (1 - shade_factor))
    return r, g, b


def hex_to_shaded_hex(rgb):
    r, g, b = shade_rgb_color(hex_to_rgb(rgb))
    return f"#{r:02x}{g:02x}{b:02x}"
