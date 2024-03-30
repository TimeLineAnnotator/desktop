from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.components import Hierarchy


def update_component_genealogy(parent: Hierarchy, children: list[Hierarchy]):
    """Changes parent and child atributes of the units
    that are arguments of the relation as to end with the parent/child
    structure given."""

    parent.children = []
    for child in children:
        parent.children.append(child)
        child.parent = parent
