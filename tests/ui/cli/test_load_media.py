from tests.mock import PatchPost
from tilia.requests import Post


def test_load_media(cli):
    with PatchPost("tilia.ui.cli.load_media", Post.REQUEST_LOAD_MEDIA) as mock_post:
        cli.run(["load-media", "test"])

    mock_post.assert_called_with(Post.REQUEST_LOAD_MEDIA, "test")
