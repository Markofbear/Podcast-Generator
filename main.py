from PySide6.QtWidgets import QApplication
from features.podcast_gui import PodcastGeneratorUI

if __name__ == "__main__":
    app = QApplication([])
    window = PodcastGeneratorUI()
    window.resize(600, 800)
    window.show()
    app.exec()
