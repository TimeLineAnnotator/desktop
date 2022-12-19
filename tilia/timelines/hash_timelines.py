from tilia.timelines.timeline_kinds import TimelineKind
import hashlib


def hash_function(string: str) -> str:
    return hashlib.md5(string.encode('utf-8')).hexdigest()


def hash_timeline_collection_data(timeline_collection_data: dict):
    sorted_tlcoll_data = sorted(timeline_collection_data.values(), key=lambda x: x['display_position'])

    str_to_hash = '|'
    for tl_data in sorted_tlcoll_data:
        str_to_hash += hash_timeline_data(tl_data['kind'], tl_data) + '|'
        print(tl_data['display_position'], hash_timeline_data(tl_data['kind'], tl_data))

    return hash_function(str_to_hash)


def hash_timeline_data(kind: TimelineKind, tl_data: dict):
    if kind == TimelineKind.SLIDER_TIMELINE.name:
        return hash_slider_timeline_data(tl_data)
    elif kind == TimelineKind.HIERARCHY_TIMELINE.name:
        return hash_hierarchy_timeline_data(tl_data)
    else:
        return 'NOT IMPLEMENTED'


def hash_slider_timeline_data(tl_data: dict):
    HASH_ATTRIBUTES = ['is_visible', 'display_position', 'height']

    str_to_hash = '|'
    for attr in HASH_ATTRIBUTES:
        str_to_hash += str(tl_data[attr]) + "|"

    return hash_function(str_to_hash)


def hash_hierarchy_timeline_data(tl_data: dict):
    HASH_ATTRIBUTES = ['height', 'is_visible', 'name']

    str_to_hash = '|'
    for attr in HASH_ATTRIBUTES:
        str_to_hash += str(tl_data[attr]) + "|"

    str_to_hash += hash_hierarchies_data(tl_data['components']) + "|"

    return hash_function(str_to_hash)


def hash_hierarchies_data(hierarchies_data: dict) -> str:
    HASH_ATTRIBUTES = ['start', 'end', 'level', 'label', 'formal_type', 'formal_function', 'comments', 'color']
    sorted_hierarchies_data = sorted(hierarchies_data.values(), key=lambda x: (x['start'], x['level']))

    str_to_hash = '|'
    for hierarchy_data in sorted_hierarchies_data:
        for attr in HASH_ATTRIBUTES:
            str_to_hash += str(hierarchy_data[attr]) + "|"

    return hash_function(str_to_hash)

