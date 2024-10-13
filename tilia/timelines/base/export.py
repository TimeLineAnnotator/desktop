from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


def get_base_export_attributes(cls: type[TimelineComponent]) -> list[str]:
    ui_attributes = ['color']

    return [x for x in cls.SERIALIZABLE_BY_VALUE if x not in ui_attributes]


def get_export_attributes_point_like(cls: type[TimelineComponent]) -> list[str]:
    base = get_base_export_attributes(cls)

    return base + ['metric_pos']


def get_export_attributes_extended(cls: type[TimelineComponent]) -> list[str]:
    base = get_base_export_attributes(cls)

    return base + ['start_metric_pos', 'end_metric_pos', 'length', 'length_in_measures']
