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
    QCheckBox,
    QHBoxLayout,
    QDialog,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread
from features.podcast_generator import PodcastGeneratorWorker
from dotenv import load_dotenv

from features.podcast import PodcastGenerator
from features.manuscript_dialog import ManuscriptReviewDialog


class PodcastGeneratorUI(QWidget):
    def __init__(self):
        super().__init__()
        load_dotenv()
        self.setWindowTitle("Podcast Generator")
        self.stop_requested = False
        self.thread = None
        self.worker = None

        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

        logo_label = QLabel()
        pixmap = QPixmap("assets/podcast_logo.png")
        if not pixmap.isNull():
            logo_label.setPixmap(pixmap.scaledToWidth(200, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(logo_label)

        self.length_dropdown = QComboBox()
        self.length_dropdown.addItem("Short (5 min)", 500)
        self.length_dropdown.addItem("Medium (10 min)", 1500)
        self.length_dropdown.addItem("Long (20 min)", 3000)
        left_layout.addWidget(QLabel("Select Podcast Length:"))
        left_layout.addWidget(self.length_dropdown)


        self.manuscript_dropdown = QComboBox()
        self.manuscript_dropdown.addItems(["OpenAI", "Hugging Face (Free)", "Gemini 2.0"])
        left_layout.addWidget(QLabel("Select Manuscript Creator:"))
        left_layout.addWidget(self.manuscript_dropdown)

        self.source_type_dropdown = QComboBox()
        self.source_type_dropdown.addItems(["Wikipedia", "PDF", "TXT", "YouTube"])
        self.source_type_dropdown.currentIndexChanged.connect(self.toggle_source_input)
        left_layout.addWidget(QLabel("Select Source Type:"))
        left_layout.addWidget(self.source_type_dropdown)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Enter Wikipedia URL or file path")
        left_layout.addWidget(QLabel("Source:"))
        left_layout.addWidget(self.source_input)

        self.browse_button = QPushButton("Browse File")
        self.browse_button.clicked.connect(self.browse_file)
        left_layout.addWidget(self.browse_button)

        self.provider_dropdown = QComboBox()
        self.provider_dropdown.addItem("pyttsx3 (Low Quality - Free)", "pyttsx3")
        self.provider_dropdown.addItem("Google (Mid Quality - API Key Required)", "google")
        self.provider_dropdown.addItem("ElevenLabs (High Quality - Account Required)", "elevenlabs")
        self.provider_dropdown.addItem("OpenAI (Mid-High Quality - API Key Required)", "openai")
        left_layout.addWidget(QLabel("Select Voice:"))
        left_layout.addWidget(self.provider_dropdown)

        self.speaker_list = QListWidget()
        self.speaker_list.setSelectionMode(QListWidget.MultiSelection)
        for name in ["Bonnie", "Clyde", "Alice", "Bob"]:
            item = QListWidgetItem(name)
            item.setSelected(name in ["Bonnie", "Clyde"])
            self.speaker_list.addItem(item)
        left_layout.addWidget(QLabel("Select Speakers:"))
        left_layout.addWidget(self.speaker_list)

        self.bg_music_checkbox = QCheckBox("Add background music")
        self.bg_music_checkbox.setChecked(True)
        left_layout.addWidget(self.bg_music_checkbox)

        self.generate_button = QPushButton("Generate Podcast")
        self.generate_button.clicked.connect(self.start_podcast_generation)
        left_layout.addWidget(self.generate_button)

        self.stop_button = QPushButton("Stop Generation")
        self.stop_button.clicked.connect(self.request_stop)
        self.stop_button.setEnabled(False)
        left_layout.addWidget(self.stop_button)

        self.play_button = QPushButton("Play Latest Podcast")
        self.play_button.clicked.connect(self.play_latest_podcast)
        left_layout.addWidget(self.play_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(QLabel("Progress:"))
        left_layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        right_layout.addWidget(QLabel("Log Output:"))
        right_layout.addWidget(self.log_output)

        self.podcast_list = QListWidget()
        self.podcast_list.setSelectionMode(QListWidget.SingleSelection)
        self.podcast_list.setMinimumHeight(150)
        self.podcast_list.itemClicked.connect(self.play_selected_podcast)
        right_layout.addWidget(QLabel("Available Podcasts:"))
        right_layout.addWidget(self.podcast_list)
        self.refresh_podcast_list()

        main_layout.addLayout(left_layout, stretch=3)
        main_layout.addLayout(right_layout, stretch=2)
        self.setLayout(main_layout)

        self.toggle_source_input(0)


    def log(self, message):
        self.log_output.append(message)
        QApplication.processEvents()

    def toggle_source_input(self, index):
        source_type = self.source_type_dropdown.currentText()
        if source_type in ["Wikipedia", "YouTube"]:
            self.browse_button.setVisible(False)
            self.source_input.setEnabled(True)
            placeholder = "Enter Wikipedia URL" if source_type == "Wikipedia" else "Enter YouTube URL"
            self.source_input.setPlaceholderText(placeholder)
            self.source_input.clear()
        else:
            self.browse_button.setVisible(True)
            self.source_input.setEnabled(False)
            self.source_input.setPlaceholderText("Selected file will appear here")
            self.source_input.clear()

    def browse_file(self):
        file_filter = "PDF files (*.pdf);;Text files (*.txt);;All files (*.*)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Source File", "", file_filter)
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
        if self.thread and self.thread.isRunning():
            self.log("❗ Please wait for current generation to finish.")
            return

        source = self.source_input.text().strip()
        source_type = self.source_type_dropdown.currentText()
        provider = self.provider_dropdown.currentData()
        manuscript_creator = self.manuscript_dropdown.currentText()
        speakers = [item.text() for item in self.speaker_list.selectedItems()]
        target_length = self.length_dropdown.currentData()

        if not source:
            self.log("❌ Please enter a valid source.")
            return
        if len(speakers) < 2:
            self.log("❌ Please select at least two speakers.")
            return

        pg = PodcastGenerator(provider, log_func=self.log, manuscript_creator=manuscript_creator)

        try:
            if source_type == "Wikipedia":
                content_text = pg.get_wikipedia_summary(source)
            elif source_type == "PDF":
                content_text = pg.extract_text_from_pdf(source)
            elif source_type == "TXT":
                content_text = pg.extract_text_from_txt(source)
            elif source_type == "YouTube":
                content_text = pg.extract_youtube_transcript(source)
            else:
                self.log("❌ Unsupported source type.")
                return
        except Exception as e:
            self.log(f"❌ Failed to extract content: {e}")
            return

        dialogues = pg.summarize_and_format_dialogue(content_text, speakers, target_length)
        manus = "\n".join(f"{speaker}: {text}" for speaker, text in dialogues)

        dialog = ManuscriptReviewDialog(manus)
        if dialog.exec() != QDialog.Accepted:
            with open("podcast/manual_edit.txt", "w", encoding="utf-8") as f:
                f.write(manus)
            self.log("📝 Script saved. You can rerun with manual=True to use it.")
            return

        final_script = dialog.get_text()
        with open("podcast/manual_edit.txt", "w", encoding="utf-8") as f:
            f.write(final_script)
        manual_mode = True

        self.stop_requested = False
        self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.generate_button.setEnabled(False)
        self.log(f"Starting podcast generation for: {source}")

        self.thread = QThread()
        background_music = self.bg_music_checkbox.isChecked()

        self.worker = PodcastGeneratorWorker(
            source,
            source_type,
            provider,
            speakers,
            target_length, 
            self.check_stop,
            background_music,
            manual=manual_mode,
            manuscript_creator=manuscript_creator,
        )
        self.worker.moveToThread(self.thread)

        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.stopped_signal.connect(lambda: self.log("🛑 Podcast generation stopped."))
        self.worker.finished.connect(self.on_generation_finished)

        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_generation_finished(self):
        self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.generate_button.setEnabled(True)
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self.log("✅ Podcast generation process finished.")
        self.refresh_podcast_list()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.log("Waiting for background task to finish...")
            self.thread.quit()
            self.thread.wait()
        event.accept()

    def play_latest_podcast(self):
        podcast_files = sorted(glob.glob("podcast/*.mp3"), key=os.path.getmtime, reverse=True)
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

    def refresh_podcast_list(self):
        self.podcast_list.clear()
        files = sorted(glob.glob("podcast/*.mp3"), key=os.path.getmtime, reverse=True)
        for f in files:
            self.podcast_list.addItem(os.path.basename(f))

    def play_selected_podcast(self, item):
        selected = item.text()
        full_path = os.path.join("podcast", selected)
        self.log(f"▶ Playing selected podcast: {selected}")
        try:
            if platform.system() == "Windows":
                os.startfile(full_path)
            elif platform.system() == "Darwin":
                subprocess.call(["open", full_path])
            else:
                subprocess.call(["xdg-open", full_path])
        except Exception as e:
            self.log(f"❌ Failed to play podcast: {str(e)}")
