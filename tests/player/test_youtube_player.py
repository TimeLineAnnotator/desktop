import pytest

from tilia.media.player.youtube import YouTubePlayer


class TestIsWellFormedId:
    @pytest.mark.parametrize(
        "video_id",
        ["dQw4w9WgXcQ", "zzzzzzzzzzz", "aaaaaaaaaaa", "_-_-_-_-_-_", "00000000000"],
    )
    def test_accepts_eleven_valid_characters(self, video_id):
        assert YouTubePlayer.is_well_formed_id(video_id)

    @pytest.mark.parametrize(
        "video_id",
        [
            "abc",  # too short
            "dQw4w9WgXcQQ",  # too long
            "dQw4w9WgXc!",  # invalid character
            "shorts",  # what get_id_from_url returns for a /shorts/ URL
            "live",  # ... and for a /live/ URL
            "",
            None,
        ],
    )
    def test_rejects_anything_else(self, video_id):
        assert not YouTubePlayer.is_well_formed_id(video_id)

    def test_ids_extracted_from_ordinary_urls_are_well_formed(self):
        for url in [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        ]:
            assert YouTubePlayer.is_well_formed_id(YouTubePlayer.get_id_from_url(url))
