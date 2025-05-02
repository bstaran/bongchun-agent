import os
import traceback
import queue
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSpacerItem,
)
from PyQt6.QtGui import (
    QTextCursor,
    QColor,
    QAction,
    QKeySequence,
    QTextBlockFormat,
    QTextCharFormat,
    QColor,
    QFont,
)
from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QThread,
    QSize,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import QKeyEvent


class ChatInputLineEdit(QLineEdit):
    """파일 붙여넣기 기능을 지원하는 QLineEdit"""

    file_pasted = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        print("[DEBUG] ChatInputLineEdit initialized")

    def keyPressEvent(self, event: QKeyEvent):
        """키 입력 이벤트 처리 (붙여넣기 감지)"""
        if event.matches(QKeySequence.StandardKey.Paste):
            print("[DEBUG] Paste event detected in ChatInputLineEdit")
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()

            if mime_data.hasUrls():
                print("[DEBUG] Clipboard has URLs (potential files)")
                file_paths = []
                for url in mime_data.urls():
                    if url.isLocalFile():
                        file_paths.append(url.toLocalFile())
                if file_paths:
                    print(
                        f"[DEBUG] Emitting file_pasted signal with paths: {file_paths}"
                    )
                    self.file_pasted.emit(file_paths)
                    event.accept()
                    return
                else:
                    print(
                        "[DEBUG] URLs are not local files, proceeding with default paste."
                    )
            else:
                print(
                    "[DEBUG] Clipboard does not contain URLs, proceeding with default paste."
                )
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)


STYLESHEET = """
QWidget {
    background-color: #2E2E2E; /* 전체 배경색 */
    color: #E0E0E0; /* 기본 텍스트 색상 */
    font-family: "Malgun Gothic", sans-serif; /* 기본 폰트 */
    font-size: 14pt; /* 기본 폰트 크기 증가 */
}

QMainWindow {
    background-color: #2E2E2E;
}

/* QTextEdit (응답 영역) */
QTextEdit#responseArea {
    background-color: #3C3C3C; /* 응답 영역 배경 */
    color: #E0E0E0;
    border: 1px solid #555555; /* 테두리 */
    border-radius: 8px; /* 둥근 모서리 */
    padding: 8px; /* 내부 여백 */
}

/* QLineEdit (입력 영역) */
QLineEdit#requestEntry {
    background-color: #3C3C3C; /* 입력 필드 배경 */
    color: #E0E0E0;
    border: 1px solid #555555;
    border-radius: 15px; /* 둥근 모서리 */
    padding: 8px 15px; /* 내부 여백 (좌우 더 넓게) */
    min-height: 20px; /* 최소 높이 */
}

QLineEdit#requestEntry:focus {
    border: 1px solid #77A4EE; /* 포커스 시 테두리 색상 */
}

/* QPushButton (기본 버튼) */
QPushButton {
    background-color: #555555; /* 버튼 배경 */
    color: #E0E0E0;
    border: 1px solid #666666;
    border-radius: 5px; /* 살짝 둥근 모서리 */
    padding: 8px 12px; /* 내부 여백 */
    min-width: 60px; /* 최소 너비 */
}

QPushButton:hover {
    background-color: #666666; /* 호버 시 배경 */
    border: 1px solid #777777;
}

QPushButton:pressed {
    background-color: #444444; /* 클릭 시 배경 */
}

/* 아이콘 버튼 스타일 (전송, 음성) */
QPushButton#sendButton, QPushButton#sttButton {
    background-color: #4A4A4A;
    border: 1px solid #666666;
    border-radius: 18px; /* 원형에 가까운 둥근 모서리 */
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    padding: 0px; /* 아이콘만 표시될 것이므로 패딩 제거 */
    /* 아이콘 설정은 코드에서 진행 */
}

QPushButton#sendButton:hover, QPushButton#sttButton:hover {
    background-color: #5A5A5A;
}

QPushButton#sendButton:pressed, QPushButton#sttButton:pressed {
    background-color: #3A3A3A;
}

/* QPushButton (파일 첨부 버튼) */
QPushButton#attachButton {
    background-color: #4A4A4A;
    border: 1px solid #666666;
    border-radius: 18px; /* 원형에 가까운 둥근 모서리 */
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    padding: 0px;
    font-size: 14pt; /* 아이콘 크기 조정 */
}

QPushButton#attachButton:hover {
    background-color: #5A5A5A;
}

QPushButton#attachButton:pressed {
    background-color: #3A3A3A;
}

/* QListWidget (첨부 파일 목록) */
QListWidget#attachmentListWidget {
    background-color: #3C3C3C;
    border: 1px solid #555555;
    border-radius: 8px;
    padding: 5px;
    /* max-height 제거 또는 주석 처리 - 고정 높이 사용 */
    /* max-height: 60px; */
}

QListWidget#attachmentListWidget::item {
    color: #D0D0D0;
    padding: 3px 5px;
    margin: 2px 0;
    border-radius: 4px;
}

QListWidget#attachmentListWidget::item:selected {
    background-color: #555555; /* 선택 시 배경 */
    color: #FFFFFF;
}

/* QScrollBar 스타일 */
QScrollBar:vertical {
    border: none;
    background: #3C3C3C; /* 스크롤바 배경 */
    width: 10px; /* 스크롤바 너비 */
    margin: 0px 0px 0px 0px;
}

QScrollBar::handle:vertical {
    background: #666666; /* 스크롤바 핸들 색상 */
    min-height: 20px; /* 핸들 최소 높이 */
    border-radius: 5px; /* 핸들 둥근 모서리 */
}

QScrollBar::handle:vertical:hover {
    background: #777777; /* 호버 시 핸들 색상 */
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: #3C3C3C;
    height: 10px;
    margin: 0px 0px 0px 0px;
}

QScrollBar::handle:horizontal {
    background: #666666;
    min-width: 20px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #777777;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    border: none;
    background: none;
    width: 0px;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
"""


class BongchunAgentGUI(QMainWindow):
    """메인 GUI 창 클래스"""

    def __init__(self, client, prompt_manager, hotkey_manager, app_controller):
        super().__init__()
        self.client = client
        self.prompt_manager = prompt_manager
        self.hotkey_manager = hotkey_manager
        self.app_controller = app_controller
        self.attached_files = []
        self.processing_message_block = None
        print("[DEBUG] BongchunAgentGUI initialized")

        self.setWindowTitle("봉춘 로컬 에이전트")
        self.setGeometry(100, 100, 700, 800)
        self.setStyleSheet(STYLESHEET)

        self._init_ui()
        self._connect_signals()
        self._setup_hotkeys()

        # 응답 큐 처리를 위한 타이머 설정
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self._process_response_queue)
        self.queue_timer.start(100)
        print("[DEBUG] Response queue timer started.")

    def _init_ui(self):
        """UI 요소 초기화 및 배치"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # --- 응답 영역 ---
        self.responseArea = QTextEdit()
        self.responseArea.setObjectName("responseArea")
        self.responseArea.setReadOnly(True)
        self.responseArea.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.responseArea, 1)

        # --- 프롬프트 선택 영역 ---
        prompt_layout = QHBoxLayout()
        prompt_label = QLabel("프롬프트:")
        self.promptComboBox = QComboBox()
        self.promptComboBox.setObjectName("promptComboBox")
        prompt_layout.addWidget(prompt_label)
        prompt_layout.addWidget(self.promptComboBox, 1)

        # 새 대화 버튼 추가
        self.newChatButton = QPushButton("새 대화")
        self.newChatButton.setObjectName("newChatButton")
        self.newChatButton.setToolTip("새로운 대화를 시작합니다 (Ctrl+N)")
        prompt_layout.addWidget(self.newChatButton)

        main_layout.addLayout(prompt_layout)

        # 프롬프트 목록 로드
        try:
            from .app_config import (
                NO_PROMPT_OPTION,
            )

            available_prompts = self.prompt_manager.available_prompts
            print(f"[DEBUG] Available prompts from attribute: {available_prompts}")
            self.promptComboBox.addItems(available_prompts)
            if NO_PROMPT_OPTION in available_prompts:
                self.promptComboBox.setCurrentText(NO_PROMPT_OPTION)
            elif available_prompts:
                self.promptComboBox.setCurrentIndex(0)

        except AttributeError:
            print(
                "[DEBUG] Error: prompt_manager does not have 'available_prompts' attribute or it's not ready."
            )
            traceback.print_exc()
            self.promptComboBox.addItem("오류: 프롬프트 속성 접근 불가")
            self.promptComboBox.setEnabled(False)
        except Exception as e:
            print(f"[DEBUG] Error loading prompts: {e}")
            traceback.print_exc()
            self.promptComboBox.addItem("오류: 프롬프트 로드 실패")
            self.promptComboBox.setEnabled(False)

        # --- 하단 입력 영역 ---
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        # --- 첨부 파일 목록 (응답 영역 아래, 입력 영역 위) ---
        self.attachmentListWidget = QListWidget()
        self.attachmentListWidget.setObjectName("attachmentListWidget")
        self.attachmentListWidget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.attachmentListWidget.setFixedHeight(40)
        self.attachmentListWidget.setVisible(False)
        # Flow layout 설정 (가로 스크롤)
        self.attachmentListWidget.setFlow(QListWidget.Flow.LeftToRight)
        self.attachmentListWidget.setWrapping(False)
        self.attachmentListWidget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.attachmentListWidget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        main_layout.addWidget(self.attachmentListWidget, 0)

        # --- 하단 입력 영역 ---
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        # 파일 첨부 버튼 (왼쪽)
        self.attachButton = QPushButton("📎")
        self.attachButton.setObjectName("attachButton")
        self.attachButton.setToolTip("파일 첨부")
        # 아이콘 크기 등 스타일은 스타일시트에서 설정
        input_layout.addWidget(self.attachButton, 0)

        # 텍스트 입력 필드 (중앙) - 커스텀 위젯 사용
        self.requestEntry = ChatInputLineEdit()
        self.requestEntry.setObjectName("requestEntry")
        self.requestEntry.setPlaceholderText("Gemini에게 물어보기 (파일 붙여넣기 가능)")
        self.requestEntry.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        input_layout.addWidget(self.requestEntry, 1)

        self.sttButton = QPushButton("🎤")
        self.sttButton.setObjectName("sttButton")
        self.sttButton.setToolTip("음성으로 입력 (단축키: Ctrl+Shift+S)")
        input_layout.addWidget(self.sttButton, 0)

        # 전송 버튼 (오른쪽)
        self.sendButton = QPushButton("➤")
        self.sendButton.setObjectName("sendButton")
        self.sendButton.setToolTip("전송 (Enter)")
        input_layout.addWidget(self.sendButton, 0)

        main_layout.addLayout(input_layout)

        # --- 메뉴바 ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("파일")

        # 새 대화 시작 액션 추가
        self.new_chat_action = QAction("새 대화 시작", self)
        self.new_chat_action.setShortcut(QKeySequence("Ctrl+N"))
        file_menu.addAction(self.new_chat_action)

        file_menu.addSeparator()

        # 종료 액션 추가
        exit_action = QAction("종료", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        print("[DEBUG] UI initialized with menubar")

    def _connect_signals(self):
        """시그널과 슬롯 연결"""
        self.sendButton.clicked.connect(self._send_request)
        self.requestEntry.returnPressed.connect(self._send_request)
        self.sttButton.clicked.connect(self._start_stt)
        self.attachButton.clicked.connect(self._attach_file)
        self.attachmentListWidget.itemDoubleClicked.connect(self._remove_attachment)
        self.requestEntry.file_pasted.connect(self._handle_pasted_files)
        self.new_chat_action.triggered.connect(self._start_new_chat)
        self.newChatButton.clicked.connect(self._start_new_chat)

        if self.hotkey_manager:
            print("[DEBUG] Connecting hotkey_manager signals...")
            try:
                self.hotkey_manager.show_window_signal.connect(self._toggle_window)
                print("[DEBUG] show_window_signal connected to _toggle_window")
                self.hotkey_manager.activate_signal.connect(self._start_stt)
                print("[DEBUG] activate_signal connected to _start_stt")
            except AttributeError as e:
                print(
                    f"[DEBUG] Error connecting hotkey signals: {e} - HotkeyManager or signals might not be ready."
                )
            except Exception as e:
                print(f"[DEBUG] Unexpected error connecting hotkey signals: {e}")
                traceback.print_exc()
        else:
            print("[DEBUG] HotkeyManager not available, skipping signal connection.")

        print("[DEBUG] Signals connected")

    def _setup_hotkeys(self):
        """전역 단축키 설정 (AppController에서 처리하므로 내용은 비움)"""
        print("[DEBUG] _setup_hotkeys called (registration handled by AppController).")

    def _toggle_window(self):
        """창 보이기/숨기기 토글 (AppController의 HotkeyManager가 호출)"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()
            self.requestEntry.setFocus()

    def _send_request(self):
        """사용자 요청 전송"""
        print("[DEBUG] _send_request called")
        request_text = self.requestEntry.text().strip()
        if not request_text and not self.attached_files:
            print("[DEBUG] No text or files to send.")
            return

        selected_prompt = self.promptComboBox.currentText()

        self._append_message(f"나: {request_text}")
        self._disable_ui_elements()
        self._append_message("⏳ AI 처리 중...", is_processing=True)
        self.requestEntry.clear()

        print(
            "[DEBUG] User message shown, UI disabled, processing message shown, calling app_controller.process_user_request"
        )

        if self.app_controller:
            self.app_controller.process_user_request(request_text, selected_prompt)
        else:
            print("[DEBUG] Error: AppController not available.")
            self._append_message(
                "<font color='red'>오류: AppController가 연결되지 않았습니다.</font>"
            )
            self._enable_ui_elements()

    def _enable_ui_elements(self):
        """UI 입력 요소 활성화"""
        print("[DEBUG] Enabling UI elements")
        self.requestEntry.setEnabled(True)
        self.sendButton.setEnabled(True)
        self.sttButton.setEnabled(True)
        self.requestEntry.setFocus()

    def _disable_ui_elements(self):
        """UI 입력 요소 비활성화"""
        print("[DEBUG] Disabling UI elements")
        self.requestEntry.setEnabled(False)
        self.sendButton.setEnabled(False)
        self.sttButton.setEnabled(False)

    def _append_message(self, message, is_processing=False):
        """응답 영역에 메시지 추가 (QTextBlockFormat 및 QTextCharFormat 사용)"""
        cursor = self.responseArea.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        is_user_message = message.startswith("나:") and not is_processing
        is_ai_message = message.startswith("Agent:") and not is_processing
        is_system_message = message.startswith("<font color=") and not is_processing

        if (
            is_ai_message
            and self.processing_message_block
            and self.processing_message_block.isValid()
        ):
            print(
                f"[DEBUG] AI message received. Attempting to remove processing block: {self.processing_message_block.blockNumber()} (valid: {self.processing_message_block.isValid()})"
            )
            temp_cursor = QTextCursor(self.processing_message_block)
            temp_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            temp_cursor.removeSelectedText()
            print(
                f"[DEBUG] Successfully removed processing message block using stored object: {self.processing_message_block.blockNumber()}"
            )
            self.processing_message_block = None
            cursor.movePosition(QTextCursor.MoveOperation.End)
            print("[DEBUG] Cursor moved to end after attempting removal.")

        block_format = QTextBlockFormat()
        block_format.setBottomMargin(8)

        char_format = QTextCharFormat()
        char_format.setFont(self.responseArea.font())
        char_format.setForeground(QColor("#E0E0E0"))

        message_content = message

        if is_user_message:
            message_content = message[len("나:") :].strip()
            block_format.setAlignment(Qt.AlignmentFlag.AlignRight)
            cursor.insertBlock(block_format)
            html_content = f"""
            <div style='display: inline-block; max-width: 80%; color: #FFFFFF;'>
                {message_content.replace('<', '<').replace('>', '>').replace('\\n', '<br>')}
            </div>
            """
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.insertHtml(html_content)

        elif is_ai_message:
            parts = message.split("\n", 1)
            if len(parts) > 1:
                prefix = parts[0]
                content = parts[1].strip()
                bold_format = QTextCharFormat()
                bold_format.setFontWeight(QFont.Weight.Bold)
                cursor.insertBlock(block_format, char_format)
                cursor.insertText(prefix + "\n", bold_format)
                cursor.insertText(content)
            else:
                message_content = message[len("Agent:") :].strip()
                cursor.insertBlock(block_format, char_format)
                cursor.insertText(f"Gemini:\n{message_content}")

            block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
        elif is_system_message:
            cursor.insertHtml(message + "<br>")
            self.responseArea.ensureCursorVisible()
            return
        elif is_processing:
            print(f"[DEBUG] Appending processing message: '{message}'")
            if (
                self.processing_message_block
                and self.processing_message_block.isValid()
            ):
                print(
                    f"[DEBUG] Removing previous processing block before adding new one: {self.processing_message_block.blockNumber()}"
                )
                prev_cursor = QTextCursor(self.processing_message_block)
                prev_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                prev_cursor.removeSelectedText()
                self.processing_message_block = None
            cursor.movePosition(QTextCursor.MoveOperation.End)

            message_content = message
            block_format.setAlignment(Qt.AlignmentFlag.AlignCenter)
            char_format.setForeground(QColor("#AAAAAA"))
            cursor.insertBlock(block_format, char_format)
            cursor.insertText(message_content)
            self.processing_message_block = cursor.block()
            print(
                f"[DEBUG] Stored new processing message block: {self.processing_message_block.blockNumber()} (valid: {self.processing_message_block.isValid()})"
            )
        else:
            block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
            cursor.insertBlock(block_format, char_format)
            cursor.insertText(message_content)
        if (
            not is_user_message
            and not is_ai_message
            and not is_system_message
            and not is_processing
        ):
            cursor.insertBlock(block_format, char_format)
            cursor.insertText(message_content)

        self.responseArea.ensureCursorVisible()

    def _process_response_queue(self):
        """AppController의 응답 큐를 처리하여 GUI 업데이트"""
        try:
            while not self.app_controller.response_queue.empty():
                message = self.app_controller.response_queue.get_nowait()
                print(f"[DEBUG] Processing queue message: '{message}'")

                if message.startswith("User"):
                    print(f"[DEBUG] Ignoring User message from queue: '{message}'")
                    continue

                elif message.startswith("AI\n"):
                    ai_msg = message[len("AI\n") :]
                    self._append_message(f"Agent:\n{ai_msg}")
                elif message.startswith("System:"):
                    system_msg = message[len("System: ") :]
                    if system_msg == "AI 처리 중...":
                        print(
                            "[DEBUG] Ignoring 'System: AI 처리 중...' message from queue."
                        )
                        continue
                    elif system_msg == "Buttons enabled":
                        self._enable_ui_elements()
                    elif system_msg == "Buttons disabled":
                        self._disable_ui_elements()
                    elif system_msg == "Clear chat display":
                        self.responseArea.clear()
                    elif system_msg == "Clear attachment label":
                        self.attachmentListWidget.clear()
                        self.attachmentListWidget.setVisible(False)
                    elif system_msg == "Show recording status":
                        print("[UI HINT] Show recording status indicator")
                        self._append_message("<i>음성 녹음 중...</i>")
                    elif system_msg == "Hide recording status":
                        print("[UI HINT] Hide recording status indicator")
                    else:
                        color = (
                            "orange"
                            if "경고" in system_msg
                            else "red" if "오류" in system_msg else "#AAAAAA"
                        )
                        self._append_message(
                            f"<font color='{color}'><i>{system_msg}</i></font>"
                        )
                else:
                    print(f"[DEBUG] Unknown message format in queue: '{message}'")
                    if "⏳ AI 처리 중..." not in message:
                        print(f"[DEBUG] Appending unknown message: '{message}'")
                        self._append_message(
                            f"<font color='gray'><i>알 수 없는 시스템 메시지: {message}</i></font>"
                        )
                    else:
                        print(
                            f"[DEBUG] Skipped displaying unknown message containing processing indicator: '{message}'"
                        )

        except queue.Empty:
            pass
        except Exception as e:
            print(f"[DEBUG] Error processing response queue: {e}")
            traceback.print_exc()
            self._append_message(
                f"<font color='red'>오류: 응답 처리 중 문제 발생 - {e}</font>"
            )

    def _attach_file(self):
        """파일 첨부 대화상자 열기"""
        print("[DEBUG] _attach_file called")
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "파일 첨부", "", "모든 파일 (*.*)"
        )
        if file_paths:
            print(f"[DEBUG] Files selected: {file_paths}")
            for file_path in file_paths:
                if file_path not in self.attached_files:
                    if self.app_controller.attach_file(file_path):
                        item = QListWidgetItem(os.path.basename(file_path))
                        item.setData(Qt.ItemDataRole.UserRole, file_path)
                        item.setToolTip(file_path)
                        self.attachmentListWidget.addItem(item)
                    else:
                        print(f"[DEBUG] File not added by AppController: {file_path}")
            if self.attachmentListWidget.count() > 0:
                self.attachmentListWidget.setVisible(True)
                QApplication.processEvents()
                print(
                    f"[DEBUG] _attach_file: attachmentListWidget visibility after setVisible(True): {self.attachmentListWidget.isVisible()}"
                )
                print(
                    f"[DEBUG] _attach_file: attachmentListWidget size: {self.attachmentListWidget.size()}"
                )

    def _handle_pasted_files(self, file_paths):
        """붙여넣기된 파일 처리"""
        print(f"[DEBUG] _handle_pasted_files called with: {file_paths}")
        if file_paths:
            for file_path in file_paths:
                if file_path not in self.attached_files:
                    if self.app_controller.attach_file(file_path):
                        item = QListWidgetItem(os.path.basename(file_path))
                        item.setData(Qt.ItemDataRole.UserRole, file_path)
                        item.setToolTip(file_path)
                        self.attachmentListWidget.addItem(item)
                        print(f"[DEBUG] File attached via paste: {file_path}")
                    else:
                        print(
                            f"[DEBUG] File not added by AppController (paste): {file_path}"
                        )
            if self.attachmentListWidget.count() > 0:
                self.attachmentListWidget.setVisible(True)
                QApplication.processEvents()
                print(
                    f"[DEBUG] _handle_pasted_files: attachmentListWidget visibility after setVisible(True): {self.attachmentListWidget.isVisible()}"
                )
                print(
                    f"[DEBUG] _handle_pasted_files: attachmentListWidget size: {self.attachmentListWidget.size()}"
                )

    def _remove_attachment(self, item):
        """첨부 파일 목록에서 항목 제거"""
        file_path_to_remove = item.data(Qt.ItemDataRole.UserRole)
        print(f"[DEBUG] _remove_attachment called for: {file_path_to_remove}")
        row = self.attachmentListWidget.row(item)
        self.attachmentListWidget.takeItem(row)
        if self.app_controller:
            self.app_controller.remove_attachment(file_path_to_remove)
        else:
            print("[DEBUG] Error: AppController not available to remove attachment.")

        if self.attachmentListWidget.count() == 0:
            self.attachmentListWidget.setVisible(False)

    def _start_stt(self):
        """음성-텍스트 변환 시작 (AppController 호출)"""
        print("[DEBUG] _start_stt called")

        if self.app_controller:
            print("[DEBUG] Calling app_controller.handle_voice_input()")
            self.app_controller.handle_voice_input()
        else:
            print("[DEBUG] Error: AppController not available for STT.")
            self._append_message(
                "<font color='red'>오류: AppController가 연결되지 않아 음성 입력을 시작할 수 없습니다.</font>"
            )

    def _start_new_chat(self):
        """새로운 대화 시작 (AppController 호출)"""
        print("[DEBUG] _start_new_chat called")
        if self.app_controller:
            self.app_controller.start_new_chat_session()
        else:
            print("[DEBUG] Error: AppController not available to start new chat.")
            self._append_message(
                "<font color='red'>오류: AppController가 연결되지 않아 새 대화를 시작할 수 없습니다.</font>"
            )

    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
        print("[DEBUG] closeEvent called")
        event.accept()
