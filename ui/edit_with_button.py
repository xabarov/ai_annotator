from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit, QFileDialog
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt


class EditWithButton(QWidget):
    def __init__(self, parent, in_separate_window=False, theme='dark_blue.xml', on_button_clicked_callback=None,
                 is_dir=False, file_type='txt',
                 dialog_text='Открытие файла', start_folder='projects', placeholder=None, title=None,
                 is_existing_file_only=True):
        """
        Поле Edit с кнопкой
        """
        super().__init__(parent)

        if in_separate_window:
            self.setWindowFlag(Qt.Tool)

        if title:
            self.setWindowTitle(title)

        self.is_dir = is_dir
        self.file_type = file_type
        self.on_button_clicked_callback = on_button_clicked_callback
        self.dialog_text = dialog_text
        self.start_folder = start_folder
        self.is_existing_file_only = is_existing_file_only

        layout = QHBoxLayout()

        self.edit = QLineEdit()
        if placeholder:
            self.edit.setPlaceholderText(placeholder)
        self.button = QPushButton()

        theme_type = theme.split('.')[0]

        self.icon_folder = "ui/icons/" + theme_type

        self.button.setIcon(QIcon(self.icon_folder + "/folder.png"))

        self.button.clicked.connect(self.on_button_clicked)

        layout.addWidget(self.edit)
        layout.addWidget(self.button)
        self.setLayout(layout)

    def getEditText(self):
        return self.edit.text()

    def showEvent(self, event):
        self.button.setMaximumHeight(self.edit.height())

    def on_button_clicked(self):

        if self.is_dir:
            dir = QFileDialog.getExistingDirectory(self,
                                                   self.dialog_text,
                                                   self.start_folder)
            if dir:
                self.edit.setText(dir)
                if self.on_button_clicked_callback:
                    self.on_button_clicked_callback()

        else:

            if self.is_existing_file_only:
                file_name, _ = QFileDialog.getOpenFileName(self,
                                                           self.dialog_text,
                                                           self.start_folder,
                                                           f'{self.file_type} File (*.{self.file_type})')

            else:
                file_name, _ = QFileDialog.getSaveFileName(self,
                                                          self.dialog_text,
                                                          self.start_folder,
                                                          f'{self.file_type} File (*.{self.file_type})')
            if file_name:
                self.edit.setText(file_name)
                if self.on_button_clicked_callback:
                    self.on_button_clicked_callback()
