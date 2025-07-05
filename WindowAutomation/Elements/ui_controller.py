# Elements/ui_controller.py
# Phiên bản 21.1: Thêm khởi tạo COM để cung cấp cho ElementFinder.

import logging
import time
import threading

# --- Thư viện cần thiết ---
try:
    import win32api
    import win32con
    import pyperclip
    from pynput import mouse, keyboard
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto import Desktop
    # *** FIX: Thêm import để khởi tạo COM ***
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    print("Gợi ý: pip install pynput pywinauto pyperclip comtypes")
    exit()

# --- Cấu hình logging ---
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# --- Import các thành phần đã tái cấu trúc từ thư mục Elements ---
try:
    from . import ui_shared_logic
    from .ui_notify import StatusNotifier
except ImportError:
    import ui_shared_logic
    try:
        from ui_notify import StatusNotifier
    except ImportError:
        StatusNotifier = None

# --- Định nghĩa Exception tùy chỉnh ---
class UIActionError(Exception): pass
class WindowNotFoundError(UIActionError): pass
class ElementNotFoundFromWindowError(UIActionError): pass
class AmbiguousElementError(UIActionError): pass

def create_notifier_callback(notifier_instance):
    if not isinstance(notifier_instance, StatusNotifier): return None
    def event_handler(event_type, message, **kwargs):
        notifier_instance.update_status(
            text=message, style=event_type, duration=kwargs.get('duration')
        )
    return event_handler

# ======================================================================
#                      CẤU HÌNH MẶC ĐỊNH
# ======================================================================
DEFAULT_CONTROLLER_CONFIG = {
    'backend': 'uia',
    'human_interruption_detection': False,
    'human_cooldown_period': 5,
    'secure_mode': False,
    'default_timeout': 10,
    'default_retry_interval': 0.5
}

class UIController:
    GETTABLE_PROPERTIES = {'text', 'texts', 'value', 'is_toggled'}.union(ui_shared_logic.SUPPORTED_FILTER_KEYS)
    BACKGROUND_SAFE_ACTIONS = {'set_text', 'send_message_text'}
    SENSITIVE_ACTIONS = {'paste_text', 'type_keys', 'set_text'}
    VALID_ACTIONS = {'click', 'double_click', 'right_click', 'focus', 'invoke', 'toggle',
                     'select', 'set_text', 'paste_text', 'type_keys', 'send_message_text'}

    def __init__(self, notifier=None, event_callback=None, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        if event_callback: self.event_callback = event_callback
        elif notifier and StatusNotifier: self.event_callback = create_notifier_callback(notifier)
        else: self.event_callback = None
        
        self.config = {**DEFAULT_CONTROLLER_CONFIG, **kwargs}
        self.desktop = Desktop(backend=self.config['backend'])
        self._last_human_activity_time = time.time() - self.config['human_cooldown_period']
        self._is_bot_acting = False
        self._bot_acting_lock = threading.Lock()
        
        # *** FIX: Khởi tạo các đối tượng COM cần thiết ***
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise
        
        # *** FIX: Truyền các đối tượng COM vào ElementFinder ***
        self.finder = ui_shared_logic.ElementFinder(
            uia_instance=self.uia,
            tree_walker=self.tree_walker,
            log_callback=self._internal_log
        )
        
        if self.config['human_interruption_detection']:
            self._start_input_listener()

    def _internal_log(self, level, message):
        self.logger.debug(f"[ElementFinder] {message}")

    def _emit_event(self, event_type, message, **kwargs):
        log_levels = {"info": logging.INFO, "success": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR, "process": logging.DEBUG, "debug": logging.DEBUG}
        self.logger.log(log_levels.get(event_type, logging.INFO), message)
        if self.event_callback and callable(self.event_callback):
            try: self.event_callback(event_type, message, **kwargs)
            except Exception as e: self.logger.error(f"Lỗi khi thực thi event_callback: {e}")

    def close(self):
        self.logger.info("Đóng UIController...")
            
    def get_next_state(self, cases, timeout=None, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else self.config['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else self.config['default_retry_interval']
        display_message = description or f"Chờ 1 trong {len(cases)} trạng thái"
        self._emit_event(notify_style if description else 'info', display_message)
        start_time = time.time()
        while time.time() - start_time < timeout:
            self._wait_for_user_idle()
            for case_name, specs in cases.items():
                self.logger.debug(f"--- Bắt đầu kiểm tra trường hợp: '{case_name}' ---")
                try:
                    self._find_target(specs.get('window_spec'), specs.get('element_spec'), timeout=0)
                    self._emit_event('success', f"Thành công: '{display_message}' -> Trạng thái '{case_name}'")
                    return case_name
                except (WindowNotFoundError, ElementNotFoundFromWindowError, AmbiguousElementError) as e:
                    self.logger.debug(f"Case '{case_name}' không khớp. Lý do: {e}")
                    continue
            time.sleep(retry_interval)
        self._emit_event('warning', f"Hết thời gian chờ: '{display_message}'")
        return None

    def run_action(self, window_spec, element_spec=None, action=None, timeout=None, auto_activate=False, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else self.config['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else self.config['default_retry_interval']
        log_action = action
        if self.config['secure_mode'] and action and ':' in action:
            command, _ = action.split(':', 1)
            if command.lower().strip() in self.SENSITIVE_ACTIONS:
                log_action = f"{command}:********"
        display_message = description or f"Thực thi tác vụ: {log_action or 'Find Only'}"
        verbose = description is None
        self._emit_event(notify_style if description else 'info', display_message)
        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
            if action:
                command = action.split(':', 1)[0].lower().strip()
                if command not in self.BACKGROUND_SAFE_ACTIONS:
                    self._handle_activation(target_element, command, auto_activate)
                if verbose: self._emit_event('process', f"Đang thực thi hành động '{log_action}'...")
                self._execute_action_safely(target_element, action)
            self._emit_event('success', f"Thành công: {display_message}")
            return True
        except (UIActionError, WindowNotFoundError, ElementNotFoundFromWindowError, AmbiguousElementError) as e:
            self.logger.error(f"Lỗi khi thực hiện '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Thất bại: {display_message}")
            return False
        except Exception as e:
            self.logger.critical(f"Lỗi không mong muốn khi thực hiện '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Thất bại: {display_message}")
            return False

    def get_property(self, window_spec, element_spec=None, property_name=None, timeout=None, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else self.config['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else self.config['default_retry_interval']
        display_message = description or f"Lấy thuộc tính '{property_name}'"
        self._emit_event(notify_style if description else 'info', display_message)
        if property_name not in self.GETTABLE_PROPERTIES:
            raise ValueError(f"Thuộc tính '{property_name}' không được hỗ trợ.")
        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
            value = ui_shared_logic.get_property_value(target_element, property_name, self.uia, self.tree_walker)
            self._emit_event('success', f"Lấy thuộc tính '{property_name}' thành công.")
            return value
        except (UIActionError, WindowNotFoundError, ElementNotFoundFromWindowError, AmbiguousElementError) as e:
            self.logger.error(f"Lỗi khi thực hiện '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Thất bại: {display_message}")
            return None
        except Exception as e:
            self.logger.critical(f"Lỗi không mong muốn khi thực hiện '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Thất bại: {display_message}")
            return None

    def _find_target(self, window_spec, element_spec=None, timeout=10, retry_interval=0.5):
        start_time = time.time()
        last_error = ""
        while True:
            windows = self.finder.find(lambda: self.desktop.windows(), window_spec)
            if len(windows) == 1:
                window = windows[0]
                self.logger.debug(f"Tìm thấy cửa sổ phù hợp: '{window.window_text()}' (Handle: {window.handle})")
                if not element_spec: return window
                elements = self.finder.find(lambda: window.descendants(), element_spec)
                if len(elements) == 1:
                    element = elements[0]
                    self.logger.debug(f"Tìm thấy element phù hợp: '{element.window_text()}'")
                    return element
                elif len(elements) > 1:
                    details = [f"'{c.window_text()}'" for c in elements[:5]]
                    raise AmbiguousElementError(f"Tìm thấy {len(elements)} elements không rõ ràng bên trong cửa sổ. Chi tiết: {details}")
                else:
                    last_error = f"Không tìm thấy element nào khớp với spec bên trong cửa sổ '{window.window_text()}'."
            elif len(windows) > 1:
                details = [f"'{c.window_text()}'" for c in windows[:5]]
                raise AmbiguousElementError(f"Tìm thấy {len(windows)} cửa sổ không rõ ràng. Chi tiết: {details}")
            else:
                last_error = "Không tìm thấy cửa sổ nào khớp với spec."
            if time.time() - start_time >= timeout:
                if not element_spec and not windows:
                    raise WindowNotFoundError(f"Hết thời gian chờ. {last_error}")
                if element_spec and not elements:
                    raise ElementNotFoundFromWindowError(f"Hết thời gian chờ. {last_error}")
                break
            time.sleep(retry_interval)
        raise UIActionError(f"Không thể tìm thấy mục tiêu sau {timeout} giây. Lỗi cuối cùng: {last_error}")

    def _execute_action(self, element, action_str):
        self.logger.debug(f"Thực thi hành động '{action_str}' trên element '{element.window_text()}'")
        parts = action_str.split(':', 1)
        command = parts[0].lower().strip()
        value = parts[1] if len(parts) > 1 else None
        try:
            if command not in self.VALID_ACTIONS:
                raise ValueError(f"Hành động '{command}' không được hỗ trợ.")
            if command == 'click': element.click_input()
            elif command == 'double_click': element.double_click_input()
            elif command == 'right_click': element.right_click_input()
            elif command == 'focus': element.set_focus()
            elif command == 'invoke': element.invoke()
            elif command == 'toggle': element.toggle()
            elif command in ('select', 'set_text', 'paste_text', 'type_keys', 'send_message_text'):
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                if command == 'select': element.select(value)
                elif command == 'set_text': element.set_edit_text(value)
                elif command == 'paste_text':
                    pyperclip.copy(value)
                    element.type_keys('^a^v', pause=0.1) 
                elif command == 'type_keys':
                    element.type_keys(value, with_spaces=True, with_newlines=True, pause=0.01)
                elif command == 'send_message_text':
                    if not element.handle: raise UIActionError("Action 'send_message_text' yêu cầu element phải có handle.")
                    win32api.SendMessage(element.handle, win32con.WM_SETTEXT, 0, value)
        except Exception as e:
            raise UIActionError(f"Thực thi hành động '{action_str}' thất bại. Lỗi gốc: {type(e).__name__} - {e}") from e
        
    def _wait_for_user_idle(self):
        if not self.config['human_interruption_detection']: return
        is_paused = False
        while time.time() - self._last_human_activity_time < self.config['human_cooldown_period']:
            if not is_paused:
                self._emit_event('warning', "Phát hiện người dùng! Tạm dừng...")
                is_paused = True
            time.sleep(1)
        if is_paused:
            self._emit_event('success', "Người dùng đã ngừng. Tiếp tục thực thi...", duration=3)

    def _handle_activation(self, target_element, command, auto_activate):
        top_window = ui_shared_logic.get_top_level_window(target_element)
        if top_window and not top_window.is_active():
            if auto_activate:
                self._emit_event('info', f"Tự động kích hoạt cửa sổ '{top_window.window_text()}'...")
                if top_window.is_minimized(): top_window.restore()
                top_window.set_focus()
                time.sleep(0.5)
            else:
                raise UIActionError(f"Cửa sổ '{top_window.window_text()}' không active. Hành động '{command}' yêu cầu kích hoạt.")

    def _execute_action_safely(self, element, action_str):
        with self._bot_acting_lock: self._is_bot_acting = True
        try: self._execute_action(element, action_str)
        finally:
            with self._bot_acting_lock: self._is_bot_acting = False

    def _start_input_listener(self):
        listener_thread = threading.Thread(target=self._run_listeners, daemon=True)
        listener_thread.start()

    def _update_last_activity(self, *args):
        with self._bot_acting_lock:
            if not self._is_bot_acting: self._last_human_activity_time = time.time()

    def _run_listeners(self):
        with mouse.Listener(on_move=self._update_last_activity, on_click=self._update_last_activity, on_scroll=self._update_last_activity) as m_listener:
            with keyboard.Listener(on_press=self._update_last_activity) as k_listener:
                m_listener.join()
                k_listener.join()
