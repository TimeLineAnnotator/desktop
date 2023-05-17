from __future__ import annotations

from typing import NamedTuple

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.components import Hierarchy
    from tilia.ui.timelines.hierarchy import HierarchyUI


import logging

logger = logging.getLogger(__name__)


def update_component_genealogy(parent: Hierarchy, children: list[Hierarchy]):
    """Changes parent and child atributes of the units
    that are arguments of the relation as to end with the parent/child
    structure given."""

    logger.debug(f"Clearing children list of {parent}.")
    parent.children = []
    for child in children:
        logger.debug(f"Appending {child} to children list.")
        parent.children.append(child)
        logger.debug(f"Setting {parent} as parent of {child}")
        child.parent = parent
