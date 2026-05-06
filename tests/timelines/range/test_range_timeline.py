from tilia.timelines.component_kinds import ComponentKind


class TestRangeTimelineComponentManager:
    # TEST CLEAR
    def test_clear(self, range_tl):
        row_id = range_tl.rows[0].id
        range_tl.create_component(
            ComponentKind.RANGE, id=1, start=0, end=10, row_id=row_id
        )
        range_tl.create_component(
            ComponentKind.RANGE, id=2, start=10, end=20, row_id=row_id
        )

        range_tl.component_manager.clear()

        assert not range_tl.component_manager._components

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, range_tl):
        row_id = range_tl.rows[0].id
        r1, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=0, end=10, row_id=row_id
        )
        r2, _ = range_tl.create_component(
            ComponentKind.RANGE, id=2, start=10, end=20, row_id=row_id
        )

        serialized_components = range_tl.component_manager.serialize_components()

        assert serialized_components[r1.id]["start"] == r1.start
        assert serialized_components[r1.id]["end"] == r1.end
        assert serialized_components[r1.id]["row_id"] == r1.row_id
        assert serialized_components[r2.id]["start"] == r2.start
        assert serialized_components[r2.id]["end"] == r2.end
        assert serialized_components[r2.id]["row_id"] == r2.row_id

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, range_tl):
        row_id = range_tl.rows[0].id
        r1, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=0, end=10, row_id=row_id
        )
        r2, _ = range_tl.create_component(
            ComponentKind.RANGE, id=2, start=10, end=20, row_id=row_id
        )

        serialized_components = range_tl.component_manager.serialize_components()

        range_tl.component_manager.clear()

        range_tl.component_manager.deserialize_components(serialized_components)

        assert len(range_tl) == 2
        restored = sorted(range_tl)
        assert restored[0].start == r1.start
        assert restored[0].end == r1.end
        assert restored[0].row_id == r1.row_id
        assert restored[1].start == r2.start
        assert restored[1].end == r2.end
        assert restored[1].row_id == r2.row_id

    def test_overlap_validation(self, range_tl):
        row_id = range_tl.rows[0].id
        # Create initial range
        c, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        assert c is not None

        # Try overlapping
        c, _ = range_tl.create_component(
            ComponentKind.RANGE, id=2, start=15, end=25, row_id=row_id
        )
        assert c is not None

        # Try non-overlapping in same row
        c, _ = range_tl.create_component(
            ComponentKind.RANGE, id=3, start=20, end=30, row_id=row_id
        )
        assert c is not None

        # Try overlapping in different row (if rows > 1)
        range_tl.add_row()
        row_id_1 = range_tl.rows[1].id
        c, _ = range_tl.create_component(
            ComponentKind.RANGE, id=4, start=15, end=25, row_id=row_id_1
        )
        assert c is not None

    def test_pre_start_negative_rejected(self, range_tl):
        row_id = range_tl.rows[0].id
        c, reason = range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            pre_start=-1,
        )
        assert c is None
        assert "pre_start" in reason

    def test_post_end_past_duration_rejected(self, range_tl, tilia_state):
        row_id = range_tl.rows[0].id
        c, reason = range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            post_end=tilia_state.duration + 1,
        )
        assert c is None
        assert "post_end" in reason

    def test_join_ranges(self, range_tl):
        row_id = range_tl.rows[0].id
        # Create two ranges
        r1, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        r2, _ = range_tl.create_component(
            ComponentKind.RANGE, id=2, start=25, end=35, row_id=row_id
        )

        # Join them
        success, reason = range_tl.component_manager.join([r1, r2])
        assert success

        # r1 end should be r2 start
        assert r1.end == r2.start
        assert r1.end == 25

    def test_join_overlap_fail(self, range_tl):
        row_id = range_tl.rows[0].id
        r1, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        r2, _ = range_tl.create_component(
            ComponentKind.RANGE, id=2, start=15, end=25, row_id=row_id
        )

        success, reason = range_tl.component_manager.join([r1, r2])
        assert not success
        assert "overlap" in reason


class TestRangePrePostExtremities:
    def test_default_pre_start_equals_start(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        assert r.pre_start == r.start == 10

    def test_default_post_end_equals_end(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        assert r.post_end == r.end == 20

    def test_explicit_pre_start_post_end(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            pre_start=5,
            post_end=25,
        )
        assert r.pre_start == 5
        assert r.post_end == 25

    def test_setting_start_before_pre_start_drags_pre_start_along(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            pre_start=5,
        )
        # Move start before the existing pre_start (5). The pre_start <= start
        # invariant requires pre_start to follow.
        r.start = 3
        assert r.pre_start == 3

    def test_setting_start_with_no_extension_keeps_pre_start_pinned(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        # No explicit pre_start was set, so pre_start should track start.
        r.start = 12
        assert r.pre_start == 12

    def test_setting_start_back_keeps_extension(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            pre_start=5,
        )
        # Move start to a later value but still after pre_start. The user
        # extension should remain at 5.
        r.start = 8
        assert r.pre_start == 5

    def test_setting_end_past_post_end_drags_post_end_along(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            post_end=25,
        )
        # Move end past post_end (25). post_end follows so post_end >= end.
        r.end = 27
        assert r.post_end == 27

    def test_setting_end_with_no_extension_keeps_post_end_pinned(self, range_tl):
        row_id = range_tl.rows[0].id
        r, _ = range_tl.create_component(
            ComponentKind.RANGE, id=1, start=10, end=20, row_id=row_id
        )
        r.end = 18
        assert r.post_end == 18

    def test_serialize_round_trip(self, range_tl):
        row_id = range_tl.rows[0].id
        range_tl.create_component(
            ComponentKind.RANGE,
            id=1,
            start=10,
            end=20,
            row_id=row_id,
            pre_start=5,
            post_end=25,
        )
        serialized = range_tl.component_manager.serialize_components()
        range_tl.component_manager.clear()
        range_tl.component_manager.deserialize_components(serialized)
        r = list(range_tl)[0]
        assert r.pre_start == 5
        assert r.post_end == 25
