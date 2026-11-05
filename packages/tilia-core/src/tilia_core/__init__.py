"""tilia-core: TiLiA's file format and corpus tools, without a user interface.

This package must never import PySide6 or the TiLiA app (``tilia``).
"""

import logging

# What the core logs is for programs that set up logging, such as TiLiA. In a
# program that doesn't, nothing reaches the terminal: without a handler,
# Python's last resort would print warnings to stderr, in the middle of what a
# command such as `tilia migrate` prints.
logging.getLogger(__name__).addHandler(logging.NullHandler())
