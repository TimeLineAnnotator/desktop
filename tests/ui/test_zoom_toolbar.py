import pytest

from tilia.requests import Get, Post, get, post
from tilia.ui import commands
from tilia.ui.zoom_toolbar import (
    _MAX,
    _MIN,
    _SLIDER_STEPS,
    ZoomToolbar,
    _ratio_to_slider,
    _slider_to_ratio,
)


class TestSliderMapping:
    def test_endpoints_map_to_slider_bounds(self):
        assert _ratio_to_slider(_MIN) == 0
        assert _ratio_to_slider(_MAX) == _SLIDER_STEPS

    def test_slider_bounds_map_to_ratio_endpoints(self):
        assert _slider_to_ratio(0) == pytest.approx(_MIN)
        assert _slider_to_ratio(_SLIDER_STEPS) == pytest.approx(_MAX)

    @pytest.mark.parametrize("ratio", [0.05, 0.2, 0.5, 1.0, 2.0, 5.0, 9.0])
    def test_log_scale_roundtrip(self, ratio):
        # round() to the nearest of _SLIDER_STEPS steps loses precision; the
        # log spacing keeps the relative error well under 2% across the range.
        assert _slider_to_ratio(_ratio_to_slider(ratio)) == pytest.approx(
            ratio, rel=0.03
        )

    def test_ratio_below_min_clamps_instead_of_raising(self):
        assert _ratio_to_slider(0.0) == 0
        assert _ratio_to_slider(-5.0) == 0


@pytest.fixture
def zoom_toolbar(tluis):
    return ZoomToolbar()


class TestZoomToolbar:
    def test_spinbox_value_commits_zoom(self, tilia_state, zoom_toolbar):
        tilia_state.duration = 100
        commands.execute("view.zoom.set", 1.0)
        zoom_toolbar._edit.setValue(200)  # 200% == ratio 2.0
        assert get(Get.CURRENT_ZOOM) == pytest.approx(2.0)

    def test_update_post_syncs_slider_and_spinbox(self, zoom_toolbar):
        post(Post.ZOOM_TOOLBAR_UPDATE, 2.0)
        assert zoom_toolbar._edit.value() == pytest.approx(200.0)
        assert zoom_toolbar._slider.value() == _ratio_to_slider(2.0)

    def test_rejected_zoom_reverts_widgets_to_current(self, tilia_state, zoom_toolbar):
        tilia_state.duration = 100
        commands.execute("view.zoom.set", 1.0)
        # A ratio whose resulting width exceeds MAX_PLAYBACK_WIDTH is rejected
        # by _apply_zoom; the toolbar must snap back to the current zoom.
        zoom_toolbar._edit.setValue(100_000_000)
        assert get(Get.CURRENT_ZOOM) == pytest.approx(1.0)
        assert zoom_toolbar._edit.value() == pytest.approx(100.0)
