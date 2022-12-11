import os

import pytest
from pathlib import Path

import tilia
from tilia.events import Event, logger
from tilia import events
from tilia import globals_
from tilia.player.player import PygamePlayer, VlcPlayer, MediaLoadError, NoMediaLoadedError

AUDIO_FORMATS = tuple(globals_.NATIVE_AUDIO_FORMATS + globals_.SUPPORTED_AUDIO_FORMATS)
SEEKABLE_AUDIO_FORMATS = tuple([f for f in AUDIO_FORMATS if f != 'wav'])

VIDEO_FORMATS = tuple(globals_.NATIVE_VIDEO_FORMATS)



# FIXTURES
@pytest.fixture
def pygame_player_notloaded():
    player = PygamePlayer()

    yield player
    player.destroy()


@pytest.fixture
def pygame_player(pygame_player_notloaded, request):
    os.chdir(Path(Path(tilia.__file__).absolute().parents[1], 'tests'))
    pygame_player_notloaded.load_media(r'testaudio_1.' + request.param)
    yield pygame_player_notloaded


@pytest.fixture
def pygame_play_media(pygame_player):
    player = pygame_player
    player.play_pause()
    yield player


@pytest.fixture
def vlc_player_notloaded():
    player = VlcPlayer()
    yield player
    player.destroy()


@pytest.fixture
def vlc_player(vlc_player_notloaded, request):
    os.chdir(Path(Path(tilia.__file__).absolute().parents[1], 'tests'))
    vlc_player_notloaded.load_media(r'testvideo_1.' + request.param)
    yield vlc_player_notloaded


@pytest.fixture
def vlc_play_media(vlc_player):
    player = vlc_player
    player.play_pause()
    yield player


class TestPygamePlayer:
    # TESTS
    def test_startup(self):
        player = PygamePlayer()
        assert player
        player.destroy()
    
    
    @pytest.mark.parametrize('file_format', AUDIO_FORMATS)
    def test_media_load(self, file_format):
        player = PygamePlayer()
        media_path = r'testaudio_1.' + file_format
        os.chdir(Path(Path(tilia.__file__).absolute().parents[1], 'tests'))
        player.load_media(media_path)
        assert player.media_path == media_path
        player.destroy()
    
    
    def test_media_load_failed(self, pygame_player_notloaded):
        player = pygame_player_notloaded
        with pytest.raises(MediaLoadError):
            player.load_media('invalid media')
    
    
    @pytest.mark.parametrize('pygame_player', AUDIO_FORMATS, indirect=True)
    def test_media_unload(self, pygame_player):
        pygame_player.unload_media()
        assert not pygame_player.playing
        assert not pygame_player.media_path
    
    
    @pytest.mark.parametrize('pygame_player', AUDIO_FORMATS, indirect=True)
    def test_play(self, pygame_player):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        assert pygame_player.playing
    
    
    def test_play_no_media_loaded(self, pygame_player_notloaded):
        player = pygame_player_notloaded
        with pytest.raises(NoMediaLoadedError):
            player.play_pause()
    
    
    @pytest.mark.parametrize('pygame_player', AUDIO_FORMATS, indirect=True)
    def test_pause_media(self, pygame_player, pygame_play_media):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        assert not pygame_player.playing
    
    
    @pytest.mark.parametrize('pygame_player', AUDIO_FORMATS, indirect=True)
    def test_unpause_media(self, pygame_player, pygame_play_media):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        assert pygame_player.playing
    
    
    @pytest.mark.parametrize('pygame_player', AUDIO_FORMATS, indirect=True)
    def test_stop_media(self, pygame_player, pygame_play_media):
        events.post(Event.PLAYER_REQUEST_TO_STOP)
        assert not pygame_player.playing

    
    @pytest.mark.parametrize('pygame_player', SEEKABLE_AUDIO_FORMATS, indirect=True)
    def test_seek_playing_media(self, pygame_play_media, pygame_player):
        player = pygame_play_media
        events.post(Event.PLAYER_REQUEST_TO_SEEK, 10.0)
        assert player.current_time == pytest.approx(10.0)
    
    
    @pytest.mark.parametrize('pygame_player', SEEKABLE_AUDIO_FORMATS, indirect=True)
    def test_seek_media_stopped(self, pygame_player):
        events.post(Event.PLAYER_REQUEST_TO_SEEK, 10.0)
        assert pygame_player.current_time == pytest.approx(10.0)
    
    
    @pytest.mark.parametrize('pygame_player', SEEKABLE_AUDIO_FORMATS, indirect=True)
    def test_seek_media_paused(self, pygame_play_media, pygame_player):
        player = pygame_play_media
        player.play_pause()
        events.post(Event.PLAYER_REQUEST_TO_SEEK, 10.0)
        assert player.current_time == pytest.approx(10.0)


class TestVlcPlayer:

    def test_constructor(self):
        player = VlcPlayer()
        assert player
        player.destroy()

    @pytest.mark.parametrize('file_format', VIDEO_FORMATS)
    def test_media_load(self, vlc_player_notloaded, file_format):
        player = vlc_player_notloaded
        media_path = 'testvideo_1.' + file_format
        player.load_media(media_path)
        assert player.media_path == media_path
        player.destroy()

    def test_media_load_failed(self, vlc_player_notloaded):
        player = vlc_player_notloaded
        with pytest.raises(MediaLoadError):
            player.load_media('invalid media')

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_media_unload(self, vlc_player):
        vlc_player.unload_media()
        assert not vlc_player.playing
        assert not vlc_player.media_path

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_play(self, vlc_player):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        assert vlc_player.playing

    def test_play_no_media_loaded(self, vlc_player_notloaded):
        player = vlc_player_notloaded
        with pytest.raises(NoMediaLoadedError):
            player.play_pause()

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_pause_media(self, vlc_player, vlc_play_media):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        assert not vlc_player.playing

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_unpause_media(self, vlc_player, vlc_play_media):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)
        assert vlc_player.playing

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_stop_media(self, vlc_player, vlc_play_media):
        events.post(Event.PLAYER_REQUEST_TO_STOP)
        assert not vlc_player.playing

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_seek_playing_media(self, vlc_play_media, vlc_player):
        player = vlc_play_media
        events.post(Event.PLAYER_REQUEST_TO_SEEK, 5.0)
        assert player.current_time == pytest.approx(5.0)

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_seek_media_stopped(self, vlc_player):
        events.post(Event.PLAYER_REQUEST_TO_SEEK, 5.0)
        assert vlc_player.current_time == pytest.approx(5.0)

    @pytest.mark.parametrize('vlc_player', VIDEO_FORMATS, indirect=True)
    def test_seek_media_paused(self, vlc_play_media, vlc_player):
        player = vlc_play_media
        player.play_pause()
        events.post(Event.PLAYER_REQUEST_TO_SEEK, 5.0)
        assert player.current_time == pytest.approx(5.0)
