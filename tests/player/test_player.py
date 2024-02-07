import time

import pygame
import pytest
from pathlib import Path

from tests.mock import PatchPost
from tilia.requests import Post, post
from tilia import globals_
from tilia.media.player import PygamePlayer, VlcPlayer
from tilia.media.player.base import NoMediaLoadedError

AUDIO_FORMATS = tuple(globals_.SUPPORTED_AUDIO_FORMATS)
SEEKABLE_AUDIO_FORMATS = tuple([f for f in AUDIO_FORMATS if f != "wav"])

VIDEO_FORMATS = tuple(globals_.SUPPORTED_VIDEO_FORMATS)


# FIXTURES
@pytest.fixture
def pygame_player_notloaded():
    player = PygamePlayer()
    pygame.mixer.music.set_volume(0)
    yield player
    player.destroy()


@pytest.fixture
def pygame_player(pygame_player_notloaded, request):
    path = Path(__file__).parent / ("test." + request.param)
    pygame_player_notloaded.load_media(path)
    yield pygame_player_notloaded


@pytest.fixture
def pygame_play_media(pygame_player):
    player = pygame_player
    player.toggle_play()
    yield player


@pytest.fixture
def vlc_player_notloaded():
    player = VlcPlayer()
    yield player
    player.destroy()


@pytest.fixture
def vlc_player(vlc_player_notloaded, request):
    path = Path(__file__).parent / ("test." + request.param)
    vlc_player_notloaded.load_media(path)
    yield vlc_player_notloaded


@pytest.fixture
def vlc_play_media(vlc_player):
    player = vlc_player
    player.toggle_play()
    yield player


# noinspection PyUnresolvedReferences
class TestPygamePlayer:
    def test_startup(self):
        player = PygamePlayer()
        assert player
        player.destroy()

    @pytest.mark.parametrize("file_format", AUDIO_FORMATS)
    def test_media_load(self, file_format):
        player = PygamePlayer()
        path = Path(__file__).parent / ("test." + file_format)
        player.load_media(str(path))
        assert player.media_path == str(path)
        player.destroy()

    def test_media_load_failed(self, pygame_player_notloaded):
        player = pygame_player_notloaded
        with pytest.raises(FileNotFoundError):
            player.load_media("invalid.ogg")

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_media_unload(self, pygame_player):
        pygame_player.unload_media()
        assert not pygame_player.playing
        assert not pygame_player.media_path

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_play(self, pygame_player):
        pygame_player.toggle_play()
        assert pygame_player.playing

    def test_play_no_media_loaded(self, pygame_player_notloaded):
        player = pygame_player_notloaded
        with pytest.raises(NoMediaLoadedError):
            player.toggle_play()

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_pause_media(self, pygame_player, pygame_play_media):
        pygame_player.toggle_play()
        assert not pygame_player.playing

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_unpause_media(self, pygame_player, pygame_play_media):
        pygame_player.toggle_play()
        pygame_player.toggle_play()
        assert pygame_player.playing

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_pause_preserves_playback_time(self, pygame_player):
        pygame_player.toggle_play()
        time.sleep(1)
        time1 = pygame_player.current_time
        pygame_player.toggle_play()
        pygame_player.toggle_play()
        time.sleep(0.5)
        assert time1 * 2 >= pygame_player.current_time >= time1

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_stop_media(self, pygame_player, pygame_play_media):
        post(Post.PLAYER_REQUEST_TO_STOP)
        assert not pygame_player.playing
        assert pygame_player.current_time == 0.0

    @pytest.mark.parametrize("pygame_player", AUDIO_FORMATS, indirect=True)
    def test_stop_media_when_paused(self, pygame_player, pygame_play_media):
        pygame_player.toggle_play()
        pygame_player.stop()
        assert not pygame_player.playing
        assert pygame_player.current_time == 0.0

    @pytest.mark.parametrize("pygame_player", SEEKABLE_AUDIO_FORMATS, indirect=True)
    def test_seek_playing_media(self, pygame_play_media, pygame_player):
        player = pygame_play_media
        post(Post.PLAYER_REQUEST_TO_SEEK, 5)
        assert player.current_time == pytest.approx(5)

    @pytest.mark.parametrize("pygame_player", SEEKABLE_AUDIO_FORMATS, indirect=True)
    def test_seek_media_stopped(self, pygame_player):
        post(Post.PLAYER_REQUEST_TO_SEEK, 5)
        assert pygame_player.current_time == pytest.approx(5)

    @pytest.mark.parametrize("pygame_player", SEEKABLE_AUDIO_FORMATS, indirect=True)
    def test_seek_media_paused(self, pygame_play_media, pygame_player):
        player = pygame_play_media
        player.toggle_play()
        post(Post.PLAYER_REQUEST_TO_SEEK, 5)
        assert player.current_time == pytest.approx(5)


# noinspection PyUnresolvedReferences
class TestVlcPlayer:
    def test_constructor(self):
        player = VlcPlayer()
        assert player
        player.destroy()

    @pytest.mark.parametrize("file_format", VIDEO_FORMATS)
    def test_media_load(self, vlc_player_notloaded, file_format):
        player = vlc_player_notloaded
        path = Path(__file__).parent / ("test." + file_format)
        player.load_media(str(path))
        assert player.media_path == str(path)

    def test_media_load_failed(self, vlc_player_notloaded):
        player = vlc_player_notloaded

        with PatchPost(
            "tilia.media.player.base", Post.REQUEST_DISPLAY_ERROR
        ) as post_mock:
            player.load_media("invalid media")

            post_mock.assert_called_once()

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_media_unload(self, vlc_player):
        vlc_player.unload_media()
        assert not vlc_player.playing
        assert not vlc_player.media_path

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_play(self, vlc_player):
        vlc_player.toggle_play()
        assert vlc_player.playing

    def test_play_no_media_loaded(self, vlc_player_notloaded):
        player = vlc_player_notloaded
        with pytest.raises(NoMediaLoadedError):
            player.toggle_play()

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_pause_media(self, vlc_player, vlc_play_media):
        vlc_player.toggle_play()
        assert not vlc_player.playing

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_unpause_media(self, vlc_player, vlc_play_media):
        vlc_player.toggle_play()
        vlc_player.toggle_play()
        assert vlc_player.playing

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_stop_media(self, vlc_player):
        time.sleep(0.5)
        vlc_player.stop()
        assert not vlc_player.playing
        assert vlc_player.current_time == 0.0

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_stop_media_when_paused(self, vlc_player):
        vlc_player.toggle_play()
        time.sleep(0.5)
        vlc_player.toggle_play()
        vlc_player.stop()
        assert not vlc_player.playing
        assert vlc_player.current_time == 0.0

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_seek_playing_media(self, vlc_play_media, vlc_player):
        player = vlc_play_media
        post(Post.PLAYER_REQUEST_TO_SEEK, 5.0)
        assert player.current_time == pytest.approx(5.0)

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_seek_media_stopped(self, vlc_player):
        post(Post.PLAYER_REQUEST_TO_SEEK, 5.0)
        assert vlc_player.current_time == pytest.approx(5.0)

    @pytest.mark.parametrize("vlc_player", VIDEO_FORMATS, indirect=True)
    def test_seek_media_paused(self, vlc_play_media, vlc_player):
        player = vlc_play_media
        player.toggle_play()
        post(Post.PLAYER_REQUEST_TO_SEEK, 5.0)
        assert player.current_time == pytest.approx(5.0)
