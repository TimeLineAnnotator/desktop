from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMainWindow

from tilia.ui.qt.timelines.beat.toolbar import BeatTimelineToolbar


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("My App")

        label = QLabel("Hello!")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setCentralWidget(label)

        toolbar = BeatTimelineToolbar()
        self.addToolBar(toolbar)

        print(toolbar)

