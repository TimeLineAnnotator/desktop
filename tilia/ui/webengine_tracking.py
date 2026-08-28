from PySide6.QtWebEngineWidgets import QWebEngineView

# Patched once, at import time, so any QWebEngineView subclass constructed
# anywhere (YouTubePlayer, musicxml_to_svg, or a future feature) is caught
# automatically -- no per-call-site opt-in to remember or forget.
_any_web_engine_view_created = False
_original_init = QWebEngineView.__init__


def _tracked_init(self, *args, **kwargs) -> None:
    global _any_web_engine_view_created
    _any_web_engine_view_created = True
    _original_init(self, *args, **kwargs)


QWebEngineView.__init__ = _tracked_init


def any_web_engine_view_created() -> bool:
    return _any_web_engine_view_created
