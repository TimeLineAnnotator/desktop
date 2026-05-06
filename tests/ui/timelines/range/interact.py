from tests.ui.timelines.interact import (
    click_timeline_ui_element_body,
    click_timeline_ui_view,
)
from tilia.ui.coords import time_x_converter


def click_range_ui(element, button="left", modifier=None, double=False):
    click_timeline_ui_element_body(element, button, modifier, double=double)


def click_start_handle(element):
    click_timeline_ui_view(element.timeline_ui.view, "left", 0, 0, element.start_handle)


def click_end_handle(element):
    click_timeline_ui_view(element.timeline_ui.view, "left", 0, 0, element.end_handle)


def click_join_separator(element):
    click_timeline_ui_view(
        element.timeline_ui.view, "left", 0, 0, element.join_separator
    )


def click_pre_start_handle(element):
    click_timeline_ui_view(
        element.timeline_ui.view,
        "left",
        0,
        0,
        element.pre_start_handle.vertical_line,
    )


def click_post_end_handle(element):
    click_timeline_ui_view(
        element.timeline_ui.view,
        "left",
        0,
        0,
        element.post_end_handle.vertical_line,
    )


def get_range_ui_center(element):
    start = element.get_data("start")
    end = element.get_data("end")
    row_index = element.row_index
    row_height = element.row_height
    x = time_x_converter.get_x_by_time((start + end) / 2)
    y = row_index * row_height + row_height / 2
    return x, y
