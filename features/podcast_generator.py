from PySide6.QtCore import QObject, Signal
from features.podcast import PodcastGenerator


class PodcastGeneratorWorker(QObject):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    stopped_signal = Signal()
    finished = Signal()

    def __init__(
        self,
        source,
        source_type,
        provider,
        speakers,
        target_length,
        stop_callback,
        background_music,
        manual=False,
    ):
        super().__init__()
        self.source = source
        self.source_type = source_type
        self.provider = provider
        self.speakers = speakers
        self.target_length = target_length
        self.stop_callback = stop_callback
        self.background_music = background_music
        self.manual = manual

    def log(self, message):
        self.log_signal.emit(message)

    def progress(self, current, total):
        self.progress_signal.emit(current, total)

    def run(self):
        try:
            generator = PodcastGenerator(provider=self.provider, log_func=self.log)
            generator.generate_podcast(
                self.source,
                self.source_type,
                self.speakers,
                self.target_length,
                stop_callback=self.stop_callback,
                progress_callback=self.progress,
                background_music=self.background_music,
                manual=self.manual,
            )
            if getattr(generator, "stopped_early", False):
                self.stopped_signal.emit()
        except Exception as e:
            self.log_signal.emit(f"❌ Error: {str(e)}")
        finally:
            self.finished.emit()
