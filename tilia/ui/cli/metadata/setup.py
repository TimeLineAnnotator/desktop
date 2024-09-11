from .imp import setup_parser as setup_import_parser
from .show import setup_parser as setup_show_parser
from .set_media_length import setup_parser as setup_set_media_length_parser
from .set import setup_parser as setup_set_parser


def setup_parser(subparsers):
    parser = subparsers.add_parser("metadata", exit_on_error=False)

    metadata_subp = parser.add_subparsers(dest="timeline_command")

    setup_import_parser(metadata_subp)
    setup_show_parser(metadata_subp)
    setup_set_media_length_parser(metadata_subp)
    setup_set_parser(metadata_subp)
