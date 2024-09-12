from tests.mock import PatchPost
from tests.ui.cli.common import cli_run
from tilia.requests import Post


def test_load_media():
    with PatchPost("tilia.ui.cli.load_media", Post.APP_MEDIA_LOAD) as mock_post:
        cli_run("load-media test")

    mock_post.assert_called_with(Post.APP_MEDIA_LOAD, "test")
