from lxml import etree

from tilia.ui.windows.svg_viewer import SvgViewer


def _make_svg(*texts):
    """Build a tiny SVG containing the given <text> elements wrapped in
    `<g class="vf-text">`. Each `texts` entry is (font_size, text)."""
    root = etree.Element("svg")
    for font_size, text in texts:
        g = etree.SubElement(root, "g", attrib={"class": "vf-text"})
        t = etree.SubElement(g, "text", attrib={"font-size": font_size, "x": "0"})
        t.text = text
    return root


class TestGetBeatXPos:
    def test_removes_three_part_marker_with_zero_font(self):
        root = _make_svg(("0.000009999999999999999px", "1␟0␟32"))
        SvgViewer._get_beat_x_pos(root)
        assert root.findall(".//g[@class='vf-text']") == []

    def test_removes_all_markers_from_fixture_shape(self):
        # Mirrors the actual file structure: many <g class='vf-text'> wrappers
        # around <text font-size='0.000009...'>m␟b␟max</text>.
        root = _make_svg(
            *[
                ("0.000009999999999999999px", f"{m}␟{b}␟32")
                for m in range(50)
                for b in range(8)
            ]
        )
        SvgViewer._get_beat_x_pos(root)
        assert root.findall(".//g[@class='vf-text']") == []

    def test_keeps_text_with_normal_font_size(self):
        root = _make_svg(("15px", "regular text"))
        SvgViewer._get_beat_x_pos(root)
        assert len(root.findall(".//g[@class='vf-text']")) == 1

    def test_bumps_font_size_for_tiny_non_marker_text(self):
        # Tiny font size but text is NOT a 3-part marker → bump to 15px,
        # keep the element so it renders at a sane size.
        root = _make_svg(("0.5px", "annotation"))
        SvgViewer._get_beat_x_pos(root)
        kept = root.findall(".//g[@class='vf-text']")
        assert len(kept) == 1
        assert kept[0][0].attrib["font-size"] == "15px"

    def test_handles_missing_font_size_attribute(self):
        root = etree.Element("svg")
        g = etree.SubElement(root, "g", attrib={"class": "vf-text"})
        etree.SubElement(g, "text").text = "anything"  # no font-size attr
        SvgViewer._get_beat_x_pos(root)
        # Should not raise; element kept since we can't tell what to do.
        assert len(root.findall(".//g[@class='vf-text']")) == 1

    def test_handles_unparseable_font_size(self):
        root = _make_svg(("not-a-number", "anything"))
        SvgViewer._get_beat_x_pos(root)
        assert len(root.findall(".//g[@class='vf-text']")) == 1

    def test_handles_empty_g_wrapper(self):
        root = etree.Element("svg")
        etree.SubElement(root, "g", attrib={"class": "vf-text"})  # no children
        SvgViewer._get_beat_x_pos(root)  # should not raise

    def test_mixed_content_keeps_only_real_glyphs(self):
        root = _make_svg(
            ("0.000009999999999999999px", "1␟0␟32"),  # marker, removed
            ("15px", "Allegro"),  # real text, kept
            ("0.5px", "annotation"),  # tiny non-marker, kept w/ 15px
            ("0.000009999999999999999px", "5␟4␟32"),  # marker, removed
        )
        SvgViewer._get_beat_x_pos(root)
        kept = root.findall(".//g[@class='vf-text']")
        assert len(kept) == 2
        kept_texts = sorted(g[0].text for g in kept)
        assert kept_texts == ["Allegro", "annotation"]
        # The bumped one should now be 15px.
        font_sizes = sorted(g[0].attrib["font-size"] for g in kept)
        assert font_sizes == ["15px", "15px"]
