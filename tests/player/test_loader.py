from tilia.media.loader import MediaLoader, get_media_type_from_path
from tilia.media.player import PygamePlayer, VlcPlayer

from pathlib import Path

OGG_PATH = Path(__file__).parent / "test.ogg"
MP4_PATH = Path(__file__).parent / "test.mp4"


class TestMediaLoader:
    def test_create(self):
        player = PygamePlayer()
        MediaLoader(player)
        player.destroy()  # must destroy so it doesn't leak
        # by staying referenced in requests.post

    def test_get_media_type_from_path(self):
        assert get_media_type_from_path(Path("test.ogg")) == ("ogg", "audio")
        assert get_media_type_from_path(Path("test.mp4")) == ("mp4", "video")
        assert get_media_type_from_path(Path("test.xyz")) == ("xyz", "unsupported")

    def test_load_audio(self):
        player = PygamePlayer()
        player = MediaLoader(player).load(OGG_PATH)
        assert isinstance(player, PygamePlayer)
        player.destroy()  # see comment above

    def test_load_video(self):
        player = VlcPlayer()
        player = MediaLoader(player).load(MP4_PATH)
        assert isinstance(player, VlcPlayer)
        player.destroy()  # see comment above

    def test_change_to_audio_player_when_loading(self):
        player = VlcPlayer()
        player = MediaLoader(player).load(OGG_PATH)
        assert isinstance(player, PygamePlayer)
        player.destroy()  # see comment above

    def test_change_to_video_player_when_loading(self):
        player = PygamePlayer()
        player = MediaLoader(player).load(MP4_PATH)
        assert isinstance(player, VlcPlayer)
        player.destroy()  # see comment above
