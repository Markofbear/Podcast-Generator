from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout

class ManuscriptReviewDialog(QDialog):
    def __init__(self, manuscript, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review and Edit Manuscript")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)

        self.label = QLabel("📝 Review or edit the podcast manuscript below.\nClick 'Approve' to continue, or close to cancel.")
        layout.addWidget(self.label)

        self.text_edit = QTextEdit()
        self.text_edit.setText(manuscript)
        layout.addWidget(self.text_edit)

        button_layout = QHBoxLayout()
        self.approve_button = QPushButton("✅ Approve")
        self.cancel_button = QPushButton("❌ Edit Later")
        button_layout.addWidget(self.approve_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.approve_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def get_text(self):
        return self.text_edit.toPlainText()
