import argparse

import pytest
from tests.mock import Serve
from tilia.requests.get import Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.components.add import add


class TestAddBeat:
    def test_wrong_timeline_kind_raises_error(self, cli, tls):
        tls.create_timeline(kind=TimelineKind.HIERARCHY_TIMELINE)

        namespace = argparse.Namespace(tl_ordinal=1, tl_name="")
        with pytest.raises(ValueError):
            add(TimelineKind.BEAT_TIMELINE, namespace)

    def test_bad_ordinal_raises_error(self, cli, tls):
        with Serve(Get.FROM_USER_BEAT_PATTERN, [4]):
            tls.create_timeline(kind=TimelineKind.BEAT_TIMELINE)

        namespace = argparse.Namespace(tl_ordinal=0, tl_name="")
        with pytest.raises(ValueError):
            add(TimelineKind.BEAT_TIMELINE, namespace)

    def test_bad_name_raises_error(self, cli, tls):
        with Serve(Get.FROM_USER_BEAT_PATTERN, [4]):
            tls.create_timeline(kind=TimelineKind.BEAT_TIMELINE, name="this")

        namespace = argparse.Namespace(tl_ordinal=None, tl_name="other")
        with pytest.raises(ValueError):
            add(TimelineKind.BEAT_TIMELINE, namespace)

    def test_add_single(self, cli, tls):
        with Serve(Get.FROM_USER_BEAT_PATTERN, [4]):
            tls.create_timeline(kind=TimelineKind.BEAT_TIMELINE)

        namespace = argparse.Namespace(tl_ordinal=1, tl_name=None, time=1)
        add(TimelineKind.BEAT_TIMELINE, namespace)

        assert tls[0].components[0].time == 1

    def test_add_multiple(self, cli, tls):
        with Serve(Get.FROM_USER_BEAT_PATTERN, [4]):
            tls.create_timeline(kind=TimelineKind.BEAT_TIMELINE)

        for i in range(10):
            namespace = argparse.Namespace(tl_ordinal=1, tl_name=None, time=i)
            add(TimelineKind.BEAT_TIMELINE, namespace)

        assert len(tls[0].components) == 10
        for i in range(10):
            assert i in tls[0].component_manager.beat_times
