from tilia.file.media_metadata import MediaMetadata


class TestMediaMetadata:
    def test_constructor(self):
        metadata = MediaMetadata()
        assert metadata["title"] == "Untitled"

    def test_from_dict(self):
        metadata = MediaMetadata.from_dict(
            {
                "title": "My Title",
                "artist": "My Artist",
                "album": "My Album",
                "year": "2020",
                "genre": "My Genre",
                "track_number": "1",
            }
        )
        assert metadata["title"] == "My Title"
        assert metadata["artist"] == "My Artist"
        assert metadata["album"] == "My Album"
        assert metadata["year"] == "2020"
        assert metadata["genre"] == "My Genre"
        assert metadata["track_number"] == "1"
