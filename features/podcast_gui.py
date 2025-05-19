import os, platform, subprocess, glob
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread
from features.podcast_generator import PodcastGeneratorWorker


class PodcastGeneratorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Podcast Generator")
        self.stop_requested = False
        self.thread = None
        self.worker = None

        layout = QVBoxLayout()

        logo_label = QLabel()
        pixmap = QPixmap("assets/podcast_logo.png")
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToWidth(200, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        self.length_dropdown = QComboBox()
        self.length_dropdown.addItems(
            ["Short (5 min)", "Medium (10 min)", "Long (20 min)"]
        )
        layout.addWidget(QLabel("Select Podcast Length:"))
        layout.addWidget(self.length_dropdown)

        self.source_type_dropdown = QComboBox()
        self.source_type_dropdown.addItems(["Wikipedia", "PDF", "TXT"])
        self.source_type_dropdown.currentIndexChanged.connect(self.toggle_source_input)
        layout.addWidget(QLabel("Select Source Type:"))
        layout.addWidget(self.source_type_dropdown)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Enter Wikipedia URL or file path")
        layout.addWidget(QLabel("Source:"))
        layout.addWidget(self.source_input)

        self.browse_button = QPushButton("Browse File")
        self.browse_button.clicked.connect(self.browse_file)
        layout.addWidget(self.browse_button)

        self.provider_dropdown = QComboBox()
        self.provider_dropdown.addItem("pyttsx3 (Low Quality - Free)", "pyttsx3")
        self.provider_dropdown.addItem(
            "Google (Mid Quality - API Key Required)", "google"
        )
        self.provider_dropdown.addItem(
            "ElevenLabs (High Quality - Account Required)", "elevenlabs"
        )
        self.provider_dropdown.addItem("OpenAI (Mid-High Quality - API Key Required)", "openai")

        layout.addWidget(QLabel("Select Voice:"))
        layout.addWidget(self.provider_dropdown)

        self.speaker_list = QListWidget()
        self.speaker_list.setSelectionMode(QListWidget.MultiSelection)
        for name in ["Bonnie", "Clyde", "Alice", "Bob"]:
            item = QListWidgetItem(name)
            item.setSelected(name in ["Bonnie", "Clyde"])
            self.speaker_list.addItem(item)
        layout.addWidget(QLabel("Select Speakers:"))
        layout.addWidget(self.speaker_list)

        self.generate_button = QPushButton("Generate Podcast")
        self.generate_button.clicked.connect(self.start_podcast_generation)
        layout.addWidget(self.generate_button)

        self.stop_button = QPushButton("Stop Generation")
        self.stop_button.clicked.connect(self.request_stop)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)

        self.play_button = QPushButton("Play Latest Podcast")
        self.play_button.clicked.connect(self.play_latest_podcast)
        layout.addWidget(self.play_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(QLabel("Progress:"))
        layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(QLabel("Log Output:"))
        layout.addWidget(self.log_output)

        self.setLayout(layout)
        self.toggle_source_input(0)

    def log(self, message):
        self.log_output.append(message)
        QApplication.processEvents()

    def toggle_source_input(self, index):
        source_type = self.source_type_dropdown.currentText()
        if source_type == "Wikipedia":
            self.browse_button.setVisible(False)
            self.source_input.setEnabled(True)
            self.source_input.setPlaceholderText("Enter Wikipedia URL")
            self.source_input.clear()
        else:
            self.browse_button.setVisible(True)
            self.source_input.setEnabled(False)
            self.source_input.setPlaceholderText("Selected file will appear here")
            self.source_input.clear()

    def browse_file(self):
        file_filter = "PDF files (*.pdf);;Text files (*.txt);;All files (*.*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Source File", "", file_filter
        )
        if file_path:
            self.source_input.setText(file_path)

    def request_stop(self):
        self.stop_requested = True
        self.log("🛑 Stop requested by user.")

    def check_stop(self):
        return self.stop_requested

    def update_progress(self, current, total):
        percentage = int((current / total) * 100)
        self.progress_bar.setValue(percentage)
        QApplication.processEvents()

    def start_podcast_generation(self):
        if self.thread is not None and self.thread.isRunning():
            self.log(
                "❗ Please wait for current generation to finish before starting a new one."
            )
            return

        source = self.source_input.text().strip()
        source_type = self.source_type_dropdown.currentText()
        provider = self.provider_dropdown.currentData()
        speakers = [item.text() for item in self.speaker_list.selectedItems()]
        target_length = self.length_dropdown.currentText()

        if not source:
            self.log("Please enter a valid source.")
            return
        if len(speakers) < 2:
            self.log("❌ Please select at least two speakers.")
            return

        self.stop_requested = False
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.generate_button.setEnabled(False)
        self.log(f"Starting podcast generation for: {source}")

        self.thread = QThread()
        self.worker = PodcastGeneratorWorker(
            source, source_type, provider, speakers, target_length, self.check_stop
        )
        self.worker.moveToThread(self.thread)

        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.stopped_signal.connect(
            lambda: self.log("🛑 Podcast generation stopped.")
        )
        self.worker.finished.connect(self.on_generation_finished)

        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_generation_finished(self):
        self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.generate_button.setEnabled(True)

        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

        self.log("✅ Podcast generation process finished.")

    def closeEvent(self, event):
        if hasattr(self, "thread") and self.thread and self.thread.isRunning():
            self.log("Waiting for background task to finish...")
            self.thread.quit()
            self.thread.wait()
        event.accept()

    def play_latest_podcast(self):
        podcast_files = sorted(
            glob.glob("podcast/*.mp3"), key=os.path.getmtime, reverse=True
        )
        if not podcast_files:
            self.log("❌ No podcast files found.")
            return

        latest_podcast = podcast_files[0]
        self.log(f"▶ Opening: {latest_podcast}")

        try:
            if platform.system() == "Windows":
                os.startfile(latest_podcast)
            elif platform.system() == "Darwin":
                subprocess.call(["open", latest_podcast])
            else:
                subprocess.call(["xdg-open", latest_podcast])
        except Exception as e:
            self.log(f"❌ Failed to open podcast: {str(e)}")