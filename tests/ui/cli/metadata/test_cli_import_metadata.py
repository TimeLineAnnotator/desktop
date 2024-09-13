import argparse
from tests.mock import PatchPost
from tilia.requests.post import Post

from tilia.ui.cli.metadata.imp import import_metadata


class TestCLIImportMetadata:
    def test_import_metadata(self):
        with PatchPost(
            "tilia.ui.cli.metadata.imp",
            Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH,
        ) as post_mock:
            import_metadata(
                argparse.Namespace(path="test.json")
            )  # path will be ignored since open is mocked

        post_mock.assert_called_with(
            Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "test.json"
        )
