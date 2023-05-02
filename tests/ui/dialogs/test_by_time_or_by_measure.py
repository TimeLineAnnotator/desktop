from tilia.ui.dialogs.import_markers_from_csv import ByTimeOrByMeasure


class TestByTimeOrByMeasure:
    def test_default_value(self, tkui):
        dialog = ByTimeOrByMeasure(tkui.root)
        dialog.on_ok()

        assert dialog.return_value == "time"

    def test_by_measure_select(self, tkui):
        dialog = ByTimeOrByMeasure(tkui.root)
        dialog.radio_measure.select()
        dialog.on_ok()

        assert dialog.return_value == "measure"
