import argparse
from unittest.mock import patch
from tests.mock import PatchPost
from tilia.requests.post import Post
from tilia.ui.cli.metadata.set_media_length import set_media_length


class TestCLISetMediaLength:
    def test_set_media_length(self):
        with PatchPost(
            "tilia.ui.cli.metadata.set_media_length",
            Post.APP_SET_MEDIA_LENGTH,
        ) as post_mock:
            set_media_length(argparse.Namespace(value=123.45))

        post_mock.assert_called_with(Post.APP_SET_MEDIA_LENGTH, 123.45)

    def test_set_media_length_value_not_a_float(self):
        with PatchPost(
            "tilia.ui.cli.metadata.set_media_length",
            Post.APP_SET_MEDIA_LENGTH,
        ) as post_mock:
            set_media_length(argparse.Namespace(value="invalid"))

        post_mock.assert_not_called()

    def test_set_media_length_value_value_is_negative(self):
        with PatchPost(
            "tilia.ui.cli.metadata.set_media_length",
            Post.APP_SET_MEDIA_LENGTH,
        ) as post_mock:
            set_media_length(argparse.Namespace(value=-1))

        post_mock.assert_not_called()
