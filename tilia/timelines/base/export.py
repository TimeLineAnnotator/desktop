from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


def get_base_export_attributes(cls: type[TimelineComponent]) -> list[str]:
    ui_attributes = ['color']

    return [x for x in cls.SERIALIZABLE_BY_VALUE if x not in ui_attributes]


def get_export_attributes_point_like(cls: type[TimelineComponent]) -> list[str]:
    base = get_base_export_attributes(cls)

    return base + ['measure', 'beat']


def get_export_attributes_extended(cls: type[TimelineComponent]) -> list[str]:
    base = get_base_export_attributes(cls)

    return base + ['start_measure', 'start_beat', 'end_measure', 'end_beat', 'length', 'length_in_measures']
