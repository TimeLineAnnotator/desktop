class TestValidateComponentCreation:
    def test_allows_harmony_at_same_time_as_mode(self, harmony_tl):
        harmony_tl.create_harmony()
        harmony_tl.create_mode()

        assert len(harmony_tl) == 2

    def test_allows_mode_at_same_time_as_harmony(self, harmony_tl):
        harmony_tl.create_mode()
        harmony_tl.create_harmony()

        assert len(harmony_tl) == 2

    def test_harmony_at_same_time_fails(self, harmony_tl):
        harmony_tl.create_harmony()
        harmony_tl.create_harmony()

        assert len(harmony_tl) == 1

    def test_mode_at_same_time_fails(self, harmony_tl):
        harmony_tl.create_mode()
        harmony_tl.create_mode()

        assert len(harmony_tl) == 1
