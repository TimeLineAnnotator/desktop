from __future__ import annotations

from typing import NamedTuple

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.components import Hierarchy
    from tilia.ui.timelines.hierarchy import HierarchyUI


import logging

logger = logging.getLogger(__name__)


class ParentChildRelation(NamedTuple):
    """Named tuple to facilitate the handling of parent and children attribute of hierarchies."""

    parent: Hierarchy | HierarchyUI
    children: list[Hierarchy | HierarchyUI]


def process_parent_child_relation(relation: ParentChildRelation):
    """Changes parent and child atributes of the units
    that are arguments of the relation as to end with the parent/child
    structure given."""

    logger.debug(f"Processing parent/child relation '{relation}'")

    parent, children = relation

    logger.debug(f"Clearing children list of {parent}.")
    parent.children = []
    for child in children:
        logger.debug(f"Appending {child} to children list.")
        parent.children.append(child)
        logger.debug(f"Setting {parent} as parent of {child}")
        child.parent = parent
