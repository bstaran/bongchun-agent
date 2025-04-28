import os
import queue
import traceback
from .app_config import NO_PROMPT_OPTION
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import (
    Qt,
    QTimer,
    pyqtSlot,
    QEvent,
    QUrl,
)
from PyQt6.QtGui import (
    QGuiApplication,
    QTextCursor,
    QDesktopServices,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QFrame,
    QSpacerItem,
)

if TYPE_CHECKING:
    from .app_controller import AppController
from PyQt6.QtGui import QKeyEvent


class PasteAwareTextEdit(QTextEdit):
    def __init__(self, gui_instance: "ChatGUI", parent=None):
        super().__init__(parent)
        self.gui = gui_instance

    def keyPressEvent(self, event: QKeyEvent):
        """키 입력 이벤트를 재정의하여 붙여넣기 처리"""
        if event.matches(QKeySequence.StandardKey.Paste):
            print("--- PasteAwareTextEdit: Paste key detected ---")
            self.gui._handle_paste_shortcut()
            event.accept()
        else:
            super().keyPressEvent(event)


STYLESHEET = """
QMainWindow {
    background-color: #f0f0f0; /* 밝은 회색 배경 */
}

QWidget#centralWidget {
    background-color: #ffffff; /* 흰색 배경 */
    border-radius: 8px; /* 약간 줄인 모서리 둥글기 */
}

QLabel {
    font-size: 10pt;
    color: #333; /* 어두운 회색 텍스트 */
}

QLabel#statusLabel {
    font-size: 9pt;
    color: #555; /* 약간 더 밝은 회색 */
    padding: 5px 10px; /* 좌우 패딩 추가 */
    border-top: 1px solid #e0e0e0; /* 상단 구분선 */
    min-height: 25px; /* 최소 높이 */
}
QLabel#statusLabel[thinking="true"] { /* 'thinking' 속성 추가 */
    font-style: italic;
    color: #3498db; /* 파란색 */
}

QLabel#recordingStatusLabel {
    color: #e74c3c; /* 빨간색 */
    font-weight: bold;
    font-size: 10pt;
    padding-left: 10px; /* 왼쪽 패딩 */
}

QComboBox {
    padding: 6px 10px; /* 패딩 조정 */
    border: 1px solid #ccc;
    border-radius: 4px;
    background-color: #fff;
    min-height: 28px; /* 높이 조정 */
    font-size: 10pt;
}
QComboBox::drop-down {
    border: none;
    width: 20px; /* 드롭다운 버튼 영역 너비 */
}
QComboBox::down-arrow {
    /* 아이콘 사용 대신 기본 화살표 사용 */
}
QComboBox:focus {
    border-color: #3498db; /* 파란색 테두리 */
    outline: none; /* 시스템 기본 포커스 테두리 제거 */
}

QTextEdit {
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 8px;
    background-color: #fff;
    font-size: 10pt;
    color: #333;
}
QTextEdit#requestEntry {
    min-height: 80px; /* 최소 높이 설정 */
}
QTextEdit#responseArea {
    background-color: #f8f9fa; /* 약간 다른 배경색 (더 밝게) */
    border: 1px solid #e9ecef; /* 더 연한 테두리 */
}
QTextEdit:focus {
    border-color: #3498db; /* 파란색 테두리 */
    outline: none;
}

QPushButton {
    background-color: #3498db; /* 파란색 배경 */
    color: white;
    border: none;
    padding: 8px 15px;
    border-radius: 4px;
    font-size: 10pt;
    min-height: 30px; /* 높이 조정 */
    outline: none; /* 포커스 테두리 제거 */
}
QPushButton:hover {
    background-color: #2980b9; /* 약간 어두운 파란색 */
}
QPushButton:pressed {
    background-color: #1f618d; /* 더 어두운 파란색 */
}
QPushButton:disabled {
    background-color: #bdc3c7; /* 비활성화 시 회색 */
    color: #7f8c8d;
}

/* 보조 버튼 스타일 */
QPushButton#attachButton, QPushButton#sttButton, QPushButton#newChatButton {
    background-color: #ecf0f1; /* 밝은 회색 배경 */
    color: #34495e; /* 어두운 파란색 텍스트 */
    border: 1px solid #bdc3c7;
}
QPushButton#attachButton:hover, QPushButton#sttButton:hover, QPushButton#newChatButton:hover {
    background-color: #dadedf;
    border-color: #a0a6a8;
}
QPushButton#attachButton:pressed, QPushButton#sttButton:pressed, QPushButton#newChatButton:pressed {
    background-color: #c8cdcf;
}
QPushButton#attachButton:disabled, QPushButton#sttButton:disabled, QPushButton#newChatButton:disabled {
    background-color: #f4f6f6;
    color: #bdc3c7;
    border-color: #e0e0e0;
}

QListWidget#attachmentListWidget {
    border: 1px solid #ccc;
    border-radius: 4px;
    background-color: #f8f9fa; /* responseArea와 동일하게 */
    font-size: 9pt;
    padding: 5px;
    max-height: 80px; /* 최대 높이 제한 */
}
QListWidget#attachmentListWidget::item {
    padding: 4px 6px; /* 아이템 패딩 조정 */
    color: #333;
}
QListWidget#attachmentListWidget::item:hover {
    background-color: #e9ecef; /* 연한 회색 배경 */
    border-radius: 3px;
}

QFrame#attachmentFrame {
    /* border-top: 1px solid #e0e0e0; */ /* 구분선 제거, statusLabel이 대신 함 */
    padding-top: 5px; /* 위쪽 여백 */
}

/* 채팅 메시지 스타일 */
QTextEdit#responseArea p {
    margin-bottom: 8px; /* 단락 간 간격 */
    line-height: 1.4; /* 줄 간격 */
}
QTextEdit#responseArea b { /* User, AI 레이블 */
    color: #2c3e50; /* 약간 어두운 파란색/회색 */
}
QTextEdit#responseArea i { /* System 메시지 */
    color: #7f8c8d; /* 회색 */
}
QTextEdit#responseArea a { /* 링크 스타일 */
    color: #3498db;
    text-decoration: none;
}
QTextEdit#responseArea a:hover {
    text-decoration: underline;
}
"""


class ChatGUI(QMainWindow):
    def __init__(self, controller: "AppController"):
        super().__init__()
        self.controller = controller
        self.response_queue = self.controller.response_queue
        self.hotkey_manager = self.controller.hotkey_manager

        self.prompt_dropdown: Optional[QComboBox] = None
        self.request_entry: Optional[QTextEdit] = None
        self.send_button: Optional[QPushButton] = None
        self.new_chat_button: Optional[QPushButton] = None
        self.stt_button: Optional[QPushButton] = None
        self.attach_button: Optional[QPushButton] = None
        self.response_area: Optional[QTextBrowser] = None
        self.status_label: Optional[QLabel] = None
        self.recording_status_label: Optional[QLabel] = None
        self.attachment_list_widget: Optional[QListWidget] = None
        self.attachment_frame: Optional[QFrame] = None
        self.queue_timer: Optional[QTimer] = None

        self._init_ui()
        self._setup_timer()
        self._setup_shortcuts()
        self._connect_hotkey_signals()
        self.apply_styles()

        if self.controller.prompt_manager.available_prompts and self.prompt_dropdown:
            self.prompt_dropdown.setCurrentIndex(0)
            self._on_prompt_select()

        self.update_status("대기 중")

    def _init_ui(self):
        """GUI 위젯 생성 및 배치 (4단계: 최종)"""
        self.setWindowTitle("AI Agent Chat")
        self.setGeometry(100, 100, 650, 650)

        central_widget = QWidget(self)
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 10)
        main_layout.setSpacing(10)

        prompt_layout = QHBoxLayout()
        prompt_label = QLabel("추가 프롬프트:")
        self.prompt_dropdown = QComboBox()
        self.prompt_dropdown.addItems(self.controller.prompt_manager.available_prompts)
        self.prompt_dropdown.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.prompt_dropdown.currentIndexChanged.connect(self._on_prompt_select)
        prompt_layout.addWidget(prompt_label)
        prompt_layout.addWidget(self.prompt_dropdown)
        main_layout.addLayout(prompt_layout)

        self.response_area = QTextBrowser()
        self.response_area.setObjectName("responseArea")
        self.response_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.response_area.anchorClicked.connect(self._handle_anchor_clicked)
        main_layout.addWidget(self.response_area, 1)

        input_frame = QFrame()
        input_frame_layout = QVBoxLayout(input_frame)
        input_frame_layout.setContentsMargins(0, 5, 0, 0)
        input_frame_layout.setSpacing(5)

        self.request_entry = PasteAwareTextEdit(self)
        self.request_entry.setObjectName("requestEntry")
        self.request_entry.setPlaceholderText(
            "여기에 요청을 입력하세요... (Shift+Enter로 줄바꿈)"
        )
        self.request_entry.setFixedHeight(100)
        self.request_entry.installEventFilter(self)
        input_frame_layout.addWidget(self.request_entry)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)

        button_group_layout = QHBoxLayout()
        button_group_layout.setSpacing(8)

        self.attach_button = QPushButton("파일 첨부")
        self.attach_button.setObjectName("attachButton")
        self.attach_button.setToolTip(
            "파일을 첨부합니다 (Ctrl+V 또는 드래그앤드롭 가능)"
        )
        self.attach_button.clicked.connect(self._attach_file_handler)
        button_group_layout.addWidget(self.attach_button)

        if self.controller.stt_service:
            self.stt_button = QPushButton("음성 입력")
            self.stt_button.setObjectName("sttButton")
            self.stt_button.setToolTip("음성으로 요청을 입력합니다 (단축키 지원)")
            self.stt_button.clicked.connect(self._voice_input_handler)
            button_group_layout.addWidget(self.stt_button)
        else:
            self.stt_button = None

        self.new_chat_button = QPushButton("새 채팅")
        self.new_chat_button.setObjectName("newChatButton")
        self.new_chat_button.setToolTip("현재 채팅 내용을 지우고 새로 시작합니다.")
        self.new_chat_button.clicked.connect(self._start_new_chat_handler)
        button_group_layout.addWidget(self.new_chat_button)

        action_layout.addLayout(button_group_layout)
        action_layout.addSpacerItem(
            QSpacerItem(
                40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
            )
        )

        self.send_button = QPushButton("전송")
        self.send_button.setObjectName("sendButton")
        self.send_button.setToolTip("입력된 요청을 전송합니다 (Enter)")
        self.send_button.clicked.connect(self._send_prompt_handler)
        action_layout.addWidget(self.send_button)

        input_frame_layout.addLayout(action_layout)
        main_layout.addWidget(input_frame)

        self.attachment_frame = QFrame()
        self.attachment_frame.setObjectName("attachmentFrame")
        attachment_layout = QVBoxLayout(self.attachment_frame)
        attachment_layout.setContentsMargins(0, 0, 0, 0)
        attachment_layout.setSpacing(5)

        attachment_label = QLabel("첨부된 파일:")
        attachment_layout.addWidget(attachment_label)

        self.attachment_list_widget = QListWidget()
        self.attachment_list_widget.setObjectName("attachmentListWidget")
        self.attachment_list_widget.setStyleSheet("font-size: 9pt;")
        self.attachment_list_widget.itemDoubleClicked.connect(
            self._handle_attachment_double_click
        )
        attachment_layout.addWidget(self.attachment_list_widget)
        self.attachment_frame.hide()
        main_layout.addWidget(self.attachment_frame)

        status_bar_layout = QHBoxLayout()
        status_bar_layout.setContentsMargins(0, 5, 0, 0)

        self.status_label = QLabel("대기 중")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        status_bar_layout.addWidget(self.status_label)

        self.recording_status_label = QLabel("")
        self.recording_status_label.setObjectName("recordingStatusLabel")
        self.recording_status_label.hide()
        status_bar_layout.addWidget(self.recording_status_label)

        main_layout.addLayout(status_bar_layout)

        self.request_entry.setFocus()

    def apply_styles(self):
        """애플리케이션에 스타일시트 적용"""
        self.setStyleSheet(STYLESHEET)

    @pyqtSlot()
    def _on_prompt_select(self):
        """프롬프트 콤보박스 선택 변경 시 호출될 슬롯"""
        if not self.prompt_dropdown:
            return
        selected_display = self.prompt_dropdown.currentText()
        if selected_display == NO_PROMPT_OPTION:
            self.setWindowTitle("AI Agent Chat (Prompt: None)")
        else:
            self.setWindowTitle(f"AI Agent Chat (Prompt: {selected_display})")

    def eventFilter(self, source, event):
        """request_entry에서 Enter 및 Shift+Enter 키 처리"""
        if source is self.request_entry and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                if modifiers == Qt.KeyboardModifier.ShiftModifier:
                    self.request_entry.insertPlainText("\n")
                    return True
                else:
                    if self.send_button and self.send_button.isEnabled():
                        self._send_prompt_handler()
                    return True
        return super().eventFilter(source, event)

    def _setup_timer(self):
        """큐 확인을 위한 타이머 설정"""
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self._check_queue)
        self.queue_timer.start(100)

    def _connect_hotkey_signals(self):
        """HotkeyManager의 시그널을 GUI 슬롯에 연결합니다."""
        if self.hotkey_manager:
            try:
                self.hotkey_manager.activate_signal.connect(
                    self._voice_input_handler_wrapper
                )
                self.hotkey_manager.show_window_signal.connect(
                    self._toggle_window_visibility
                )
                print("GUI: HotkeyManager 시그널 (음성, 창 토글) 연결 완료.")
            except AttributeError as e:
                print(f"GUI 경고: HotkeyManager 시그널 연결 중 오류 발생 - {e}.")
            except Exception as e:
                print(f"GUI 오류: HotkeyManager 시그널 연결 중 예기치 않은 오류: {e}")
        else:
            print(
                "GUI 경고: HotkeyManager 인스턴스가 없어 시그널을 연결할 수 없습니다."
            )

    @pyqtSlot()
    def _send_prompt_handler(self):
        """전송 버튼 클릭 또는 Enter 키 입력 시 호출될 슬롯"""
        if (
            not self.request_entry
            or not self.send_button
            or not self.send_button.isEnabled()
        ):
            return

        user_request = self.request_entry.toPlainText().strip()
        if not user_request and not self.controller.get_attachment_paths():
            self.update_status(
                "오류: 요청 내용 또는 첨부 파일이 필요합니다.", is_thinking=False
            )
            QTimer.singleShot(2000, lambda: self.update_status("대기 중"))
            return

        self.request_entry.clear()
        self._disable_buttons()
        self.update_status("요청 처리 중...", is_thinking=True)

        additional_prompt = ""
        if self.prompt_dropdown:
            additional_prompt = self.controller.prompt_manager.load_selected_prompt(
                self.prompt_dropdown.currentText()
            )

        self.controller.process_user_request(user_request, additional_prompt)

    @pyqtSlot()
    def _attach_file_handler(self):
        """파일 첨부 버튼 클릭 시 호출될 슬롯"""
        if not self.attach_button or not self.attach_button.isEnabled():
            return

        file_filter = "모든 파일 (*.*);;이미지 파일 (*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp);;텍스트 파일 (*.txt *.md *.py *.js *.html *.css)"
        filepaths, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", file_filter)
        if filepaths:
            attached_count = 0
            failed_count = 0
            for filepath in filepaths:
                try:
                    if self.controller.attach_file(filepath):
                        attached_count += 1
                        print(f"GUI: 파일 첨부됨 - {os.path.basename(filepath)}")
                    else:
                        failed_count += 1
                        print(
                            f"GUI: 파일 첨부 실패(중복 등) - {os.path.basename(filepath)}"
                        )
                except Exception as e:
                    failed_count += 1
                    print(
                        f"GUI Error: 파일 첨부 버튼 처리 중 오류 발생 - {filepath}: {e}"
                    )
                    traceback.print_exc()

            if attached_count > 0:
                self._update_attachment_list()
                status_msg = f"{attached_count}개 파일 첨부 완료."
                if failed_count > 0:
                    status_msg += f" ({failed_count}개 실패)"
                self.update_status(status_msg)
                QTimer.singleShot(3000, lambda: self.update_status("대기 중"))
            elif failed_count > 0:
                self.update_status(f"{failed_count}개 파일 첨부 실패.")
                QTimer.singleShot(3000, lambda: self.update_status("대기 중"))

        else:
            print("GUI: 파일 선택 취소됨.")

    @pyqtSlot()
    def _voice_input_handler(self):
        """음성 입력 버튼 클릭 시 호출될 슬롯"""
        if self.stt_button and self.stt_button.isEnabled():
            self._disable_buttons()
            self.update_status("음성 입력 준비 중...", is_thinking=True)
            self.controller.handle_voice_input()

    @pyqtSlot()
    def _voice_input_handler_wrapper(self):
        """음성 입력 단축키 처리 슬롯"""
        print("음성 입력 단축키 핸들러 호출됨")
        if (
            self.controller.stt_service
            and self.stt_button
            and self.stt_button.isEnabled()
        ):
            if not self.isVisible():
                self.show()
            self.bring_to_front()
            self._voice_input_handler()
        else:
            print("음성 입력 단축키: STT 서비스 비활성화 또는 버튼 비활성 상태")
            self.update_status("음성 입력을 사용할 수 없습니다.", is_thinking=False)
            QTimer.singleShot(2000, lambda: self.update_status("대기 중"))

    @pyqtSlot()
    def _toggle_window_visibility(self):
        """창 보이기/숨기기 토글 슬롯"""
        print("GUI: 창 표시/숨김 토글 단축키 핸들러 호출됨")
        if self.isVisible():
            print("GUI: 창 숨김.")
            self.hide()
        else:
            print("GUI: 창 표시 및 앞으로 가져오기.")
            self.show()
            self.bring_to_front()

    @pyqtSlot()
    def _handle_paste_shortcut(self):
        """PyQt 단축키(Cmd+V/Ctrl+V)로 인한 붙여넣기 처리 슬롯"""
        print("--- GUI DEBUG: _handle_paste_shortcut SLOT CALLED ---")
        print("GUI DEBUG: _handle_paste_shortcut called (PyQt Shortcut).")

        self._process_clipboard_paste()

    @pyqtSlot()
    def _handle_global_paste(self):
        """붙여넣기 (전역 단축키 - pynput) 처리 슬롯 (이제 사용되지 않음, 혹시 모르니 남겨둠)"""
        print("GUI DEBUG: _handle_global_paste called (Global Hotkey - likely unused).")
        if not self.isVisible():
            self.show()
        self.bring_to_front()

        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()
        processed = False
        attached_files_count = 0

        if mime_data.hasUrls():
            print("GUI DEBUG: Clipboard has URLs.")
            for url in mime_data.urls():
                if url.isLocalFile():
                    filepath = url.toLocalFile()
                    print(f"GUI DEBUG: Processing local file URL: {filepath}")
                    if os.path.exists(filepath):
                        try:
                            if self.controller.attach_file(filepath):
                                print(f"GUI: Successfully attached file: {filepath}")
                                attached_files_count += 1
                                processed = True
                            else:
                                print(
                                    f"GUI WARNING: Controller failed to attach file: {filepath}"
                                )
                        except Exception as e:
                            print(f"GUI ERROR: Error attaching file {filepath}: {e}")
                            self.update_status(
                                f"오류: 파일 첨부 실패 - {os.path.basename(filepath)}"
                            )
                            QTimer.singleShot(
                                3000, lambda: self.update_status("대기 중")
                            )
                    else:
                        print(
                            f"GUI WARNING: File path from URL does not exist: {filepath}"
                        )
                else:
                    print(f"GUI DEBUG: Skipping non-local URL: {url.toString()}")

        elif mime_data.hasText() and self.request_entry:
            print("GUI DEBUG: Clipboard has text.")
            pasted_text = mime_data.text().strip()
            print(f"GUI DEBUG: Pasted text (first 100 chars): {pasted_text[:100]!r}")

            if os.path.exists(pasted_text):
                print(f"GUI DEBUG: Pasted text is an existing file path: {pasted_text}")
                try:
                    if self.controller.attach_file(pasted_text):
                        print(
                            f"GUI: Successfully attached file from text path: {pasted_text}"
                        )
                        attached_files_count += 1
                        processed = True
                    else:
                        print(
                            f"GUI WARNING: Controller failed to attach file from text path: {pasted_text}"
                        )
                        self.request_entry.insertPlainText(pasted_text)
                        print("GUI: Pasting as plain text after attachment failure.")
                        processed = True
                except Exception as e:
                    print(
                        f"GUI ERROR: Error attaching file from text path {pasted_text}: {e}"
                    )
                    self.update_status(
                        f"오류: 파일 첨부 실패 - {os.path.basename(pasted_text)}"
                    )
                    QTimer.singleShot(3000, lambda: self.update_status("대기 중"))
                    self.request_entry.insertPlainText(pasted_text)
                    print("GUI: Pasting as plain text after error during attachment.")
                    processed = True
            else:
                self.request_entry.insertPlainText(pasted_text)
                self.request_entry.moveCursor(QTextCursor.MoveOperation.End)
                print("GUI: Pasted text into request entry (not a file path).")
                processed = True

        if attached_files_count > 0:
            self._update_attachment_list()
            self.update_status(f"{attached_files_count}개 파일 첨부 완료.")
            QTimer.singleShot(2000, lambda: self.update_status("대기 중"))

        if not processed:
            print("GUI DEBUG: No processable data (URLs or text) found in clipboard.")
            self.update_status("붙여넣기할 내용 없음.")
            QTimer.singleShot(2000, lambda: self.update_status("대기 중"))

        self._process_clipboard_paste()

    def _process_clipboard_paste(self):
        """클립보드 내용을 처리하여 붙여넣는 공통 로직"""
        print("GUI DEBUG: _process_clipboard_paste called.")
        clipboard = QGuiApplication.clipboard()
        mime_data = clipboard.mimeData()
        processed = False
        attached_files_count = 0

        if mime_data.hasUrls():
            print("GUI DEBUG: Clipboard has URLs.")
            for url in mime_data.urls():
                if url.isLocalFile():
                    filepath = url.toLocalFile()
                    print(f"GUI DEBUG: Processing local file URL: {filepath}")
                    if os.path.exists(filepath):
                        try:
                            if self.controller.attach_file(filepath):
                                print(f"GUI: Successfully attached file: {filepath}")
                                attached_files_count += 1
                                processed = True
                            else:
                                print(
                                    f"GUI WARNING: Controller failed to attach file: {filepath}"
                                )
                        except Exception as e:
                            print(f"GUI ERROR: Error attaching file {filepath}: {e}")
                            self.update_status(
                                f"오류: 파일 첨부 실패 - {os.path.basename(filepath)}"
                            )
                            QTimer.singleShot(
                                3000, lambda: self.update_status("대기 중")
                            )
                    else:
                        print(
                            f"GUI WARNING: File path from URL does not exist: {filepath}"
                        )
                else:
                    print(f"GUI DEBUG: Skipping non-local URL: {url.toString()}")

        elif mime_data.hasText() and self.request_entry:
            print("GUI DEBUG: Clipboard has text.")
            pasted_text = mime_data.text().strip()
            print(f"GUI DEBUG: Pasted text (first 100 chars): {pasted_text[:100]!r}")

            # 1. 텍스트가 유효한 파일 경로인지 먼저 확인
            if os.path.exists(pasted_text):
                print(f"GUI DEBUG: Pasted text is an existing file path: {pasted_text}")
                try:
                    if self.controller.attach_file(pasted_text):
                        print(
                            f"GUI: Successfully attached file from text path: {pasted_text}"
                        )
                        attached_files_count += 1
                        processed = True
                    else:
                        print(
                            f"GUI WARNING: Controller failed to attach file from text path: {pasted_text}"
                        )
                        self.update_status(
                            f"파일 첨부 실패: {os.path.basename(pasted_text)}"
                        )
                        QTimer.singleShot(2000, lambda: self.update_status("대기 중"))

                except Exception as e:
                    print(
                        f"GUI ERROR: Error attaching file from text path {pasted_text}: {e}"
                    )
                    self.update_status(
                        f"오류: 파일 첨부 실패 - {os.path.basename(pasted_text)}"
                    )
                    QTimer.singleShot(3000, lambda: self.update_status("대기 중"))

            # 2. 파일 경로가 아니거나 파일 첨부에 실패했고, request_entry가 포커스 상태이면 텍스트 붙여넣기
            if not processed and self.request_entry.hasFocus():
                self.request_entry.insertPlainText(pasted_text)
                self.request_entry.moveCursor(QTextCursor.MoveOperation.End)
                print(
                    "GUI: Pasted text into focused request entry (not a file path or attachment failed)."
                )
                processed = True
            elif not processed:
                print(
                    "GUI: Pasted text ignored (not a file path and request entry not focused)."
                )
                pass

        if attached_files_count > 0:
            self._update_attachment_list()
            self.update_status(f"{attached_files_count}개 파일 첨부 완료.")
            QTimer.singleShot(2000, lambda: self.update_status("대기 중"))

        if not processed and attached_files_count == 0:
            print(
                "GUI DEBUG: No processable data (URLs or text) found or handled in clipboard."
            )

    def _prompt_for_file(self, initial_filename: str = ""):
        """파일 선택 대화상자를 열고 선택된 파일을 첨부합니다. (현재 직접 사용되지 않음)"""
        print(
            f"GUI DEBUG: _prompt_for_file called (likely unused) with: {initial_filename!r}"
        )
        self._attach_file_handler()

    @pyqtSlot()
    def _start_new_chat_handler(self):
        """새 채팅 시작 버튼 클릭 시 호출될 슬롯"""
        if not self.new_chat_button or not self.new_chat_button.isEnabled():
            return
        print("GUI: 새 채팅 시작 버튼 클릭됨")
        self.controller.start_new_chat_session()

    @pyqtSlot()
    def _check_queue(self):
        """컨트롤러의 큐를 주기적으로 확인하여 GUI 업데이트"""
        try:
            while True:
                message_data = self.response_queue.get_nowait()
                print(f"GUI Queue Received: {message_data}")

                if isinstance(message_data, tuple) and len(message_data) >= 1:
                    message_type = message_data[0]
                    payload = message_data[1] if len(message_data) > 1 else None

                    if message_type == "display":
                        self._display_response(payload)
                    elif message_type == "status":
                        is_thinking = (
                            message_data[2] if len(message_data) > 2 else False
                        )
                        self.update_status(payload, is_thinking)
                    elif message_type == "recording_status":
                        self.update_recording_status(payload)
                    elif message_type == "update_attachments":
                        self._update_attachment_list()
                    elif message_type == "clear_chat":
                        self.clear_chat_display()
                    elif message_type == "clear_attachments":
                        self.clear_attachment_list()
                    elif message_type == "set_input":
                        self.set_input_text(payload)
                    elif message_type == "enable_buttons":
                        self._enable_buttons()
                    elif message_type == "disable_buttons":
                        self._disable_buttons()
                    elif message_type == "new_chat_started":
                        self.clear_chat_display()
                        self.clear_attachment_list()
                        self._display_response(
                            "System: 새로운 채팅 세션이 시작되었습니다."
                        )
                        self.update_status("대기 중")
                        self._enable_buttons()
                    else:
                        print(
                            f"GUI Warning: Unknown message type from queue: {message_type}"
                        )
                elif isinstance(message_data, str):
                    if message_data == "System: Buttons enabled":
                        self._enable_buttons()
                    elif message_data == "System: Hide recording status":
                        self.update_recording_status(False)
                    elif message_data == "System: Clear attachment label":
                        self.clear_attachment_list()
                    elif message_data == "System: 새 채팅 시작됨.":
                        self.clear_chat_display()
                        self.clear_attachment_list()
                        self._display_response(
                            "System: 새로운 채팅 세션이 시작되었습니다."
                        )
                        self.update_status("대기 중")
                        self._enable_buttons()
                    elif message_data.startswith("System: Set input text|"):
                        text_to_set = message_data.split("|", 1)[1]
                        self.set_input_text(text_to_set)
                    elif not message_data.startswith("System:"):
                        self._display_response(message_data)
                else:
                    print(
                        f"GUI Warning: Received invalid message format from queue: {message_data}"
                    )

        except queue.Empty:
            pass
        except Exception as e:
            print(f"GUI Error: _check_queue 중 오류 발생: {e}")
            traceback.print_exc()

    def _disable_buttons(self):
        """입력 관련 버튼 비활성화"""
        if self.send_button:
            self.send_button.setEnabled(False)
        if self.stt_button:
            self.stt_button.setEnabled(False)
        if self.new_chat_button:
            self.new_chat_button.setEnabled(False)
        if self.attach_button:
            self.attach_button.setEnabled(False)
        if self.request_entry:
            self.request_entry.setReadOnly(True)

    def _enable_buttons(self):
        """입력 관련 버튼 활성화"""
        if self.send_button:
            self.send_button.setEnabled(True)
        if self.stt_button:
            self.stt_button.setEnabled(True)
        if self.new_chat_button:
            self.new_chat_button.setEnabled(True)
        if self.attach_button:
            self.attach_button.setEnabled(True)
        if self.request_entry:
            self.request_entry.setReadOnly(False)
        if self.request_entry:
            self.request_entry.setFocus()

    def _display_response(self, text: str):
        """답변 영역에 텍스트 표시 (HTML 형식 개선)"""
        if not self.response_area or not isinstance(text, str):
            return

        cursor = self.response_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.response_area.setTextCursor(cursor)

        html_text = ""
        if text.startswith("User\n"):
            content = text.split("\n", 1)[1].replace("\n", "<br>")
            html_text = f"<p><b>User:</b><br>{content}</p>"
        elif text.startswith("AI\n"):
            content = text.split("\n", 1)[1].replace("\n", "<br>")
            html_text = f'<p style="color: #2980b9;"><b>AI:</b><br>{content}</p>'
        elif text.startswith("System:"):
            html_text = f"<p><i>{text.replace("\n", "<br>")}</i></p>"
        else:
            html_text = f"<p>{text.replace("\n", "<br>")}</p>"

        self.response_area.insertHtml(html_text + "<br>")
        self.response_area.ensureCursorVisible()

    def update_status(self, status_text: str, is_thinking: bool = False):
        """상태 레이블 업데이트 및 시각적 피드백"""
        if self.status_label:
            self.status_label.setText(status_text)
            self.status_label.setProperty("thinking", is_thinking)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

            if is_thinking:
                pass
            else:
                pass

    def update_recording_status(self, is_recording: bool):
        """녹음 상태 레이블 및 시각적 표시 업데이트"""
        if self.recording_status_label:
            if is_recording:
                self.recording_status_label.setText("🔴 녹음 중...")
                self.recording_status_label.show()
            else:
                self.recording_status_label.hide()

    def clear_chat_display(self):
        """채팅 출력 영역 초기화"""
        if self.response_area:
            self.response_area.clear()

    def clear_attachment_list(self):
        """첨부 파일 목록 위젯 초기화 및 숨김"""
        print("GUI DEBUG: clear_attachment_list() 호출됨")
        if self.attachment_list_widget:
            self.attachment_list_widget.clear()
        if self.attachment_frame:
            self.attachment_frame.hide()
            print("GUI DEBUG: Attachment frame hidden.")

    def _update_attachment_list(self):
        """첨부 파일 목록 위젯을 업데이트하고 표시/숨김 처리"""
        print("GUI DEBUG: _update_attachment_list() 시작")

        widget_exists = hasattr(self, "attachment_list_widget")
        frame_exists = hasattr(self, "attachment_frame")
        print(
            f"GUI DEBUG: Checking attributes - widget_exists: {widget_exists}, frame_exists: {frame_exists}"
        )
        widget_val = None
        frame_val = None
        if widget_exists:
            widget_val = self.attachment_list_widget
            print(f"GUI DEBUG: self.attachment_list_widget value: {widget_val}")
        if frame_exists:
            frame_val = self.attachment_frame
            print(f"GUI DEBUG: self.attachment_frame value: {frame_val}")

        widget = widget_val
        frame = frame_val

        if widget is None:
            print(f"GUI DEBUG: Condition 'widget is None' is True. Returning.")
            return
        if frame is None:
            print(f"GUI DEBUG: Condition 'frame is None' is True. Returning.")
            return

        print(
            f"GUI DEBUG: Both widget ({widget}) and frame ({frame}) are valid. Proceeding."
        )

        widget.clear()
        try:
            file_paths = self.controller.get_attachment_paths()
            filenames = [os.path.basename(p) for p in file_paths]
            print(f"GUI DEBUG: Fetched {len(filenames)} attachments: {filenames}")
        except Exception as e:
            print(f"GUI ERROR: 컨트롤러에서 첨부 파일 목록 가져오기 실패: {e}")
            filenames = []

        if filenames:
            print("GUI DEBUG: 첨부 파일 있음, 목록 업데이트 및 프레임 표시 시도...")
            for i, name in enumerate(filenames):
                item = QListWidgetItem(name)
                item.setToolTip(file_paths[i])
                widget.addItem(item)
            frame.show()
            print(
                f"GUI DEBUG: Attachment frame.show() 호출됨. frame.isVisible(): {frame.isVisible()}"
            )
            widget.scrollToBottom()
        else:
            print("GUI DEBUG: 첨부 파일 없음, 프레임 숨김 시도...")
            frame.hide()
            print(
                f"GUI DEBUG: Attachment frame.hide() 호출됨. frame.isVisible(): {frame.isVisible()}"
            )

    def set_input_text(self, text: str):
        """입력 필드에 텍스트 설정"""
        if self.request_entry:
            self.request_entry.setPlainText(text)
            self.request_entry.moveCursor(QTextCursor.MoveOperation.End)

    @pyqtSlot(QListWidgetItem)
    def _handle_attachment_double_click(self, item: QListWidgetItem):
        """첨부 파일 목록 항목 더블 클릭 시 처리 (예: 경로 복사)"""
        filepath = item.toolTip()
        if filepath:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(filepath)
            self.update_status(f"경로 복사됨: {os.path.basename(filepath)}")
            QTimer.singleShot(2000, lambda: self.update_status("대기 중"))
            print(f"GUI: Copied attachment path to clipboard: {filepath}")

    @pyqtSlot(QUrl)
    def _handle_anchor_clicked(self, url: QUrl):
        """response_area의 링크 클릭 시 처리"""
        print(f"GUI: Link clicked: {url.toString()}")
        QDesktopServices.openUrl(url)

    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
        reply = QMessageBox.question(
            self,
            "종료 확인",
            "애플리케이션을 종료하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            print("GUI: 종료 요청됨. main 루프 중지 예정...")
            if self.hotkey_manager:
                print("GUI: HotkeyManager 리스너 중지 시도...")
                self.hotkey_manager.stop_listener()
            self.controller.request_shutdown()
            event.accept()
        else:
            event.ignore()

    def bring_to_front(self):
        """애플리케이션 창을 맨 앞으로 가져오고 활성화합니다."""
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        print("GUI: 창을 앞으로 가져왔습니다.")

    def run(self):
        """GUI 표시 (main.py에서 호출될 것으로 예상)"""
        self.show()
