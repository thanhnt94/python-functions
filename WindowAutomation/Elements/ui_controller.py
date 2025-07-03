# Elements/ui_controller.py
import logging
import re
import time
import math
import threading
from datetime import datetime
import tkinter as tk
import queue

# --- Thư viện cần thiết ---
try:
    import psutil
    import win32gui
    import win32process
    import win32con
    import win32api
    import pyperclip
    from pynput import mouse, keyboard
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto import Desktop
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# --- Cấu hình logging ---
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# --- Định nghĩa Exception tùy chỉnh ---
class UIActionError(Exception): pass
class WindowNotFoundError(UIActionError): pass
class AmbiguousElementError(UIActionError): pass

# ======================================================================
#                      CẤU HÌNH MẶC ĐỊNH
# ======================================================================
DEFAULT_CONTROLLER_CONFIG = {
    'backend': 'uia',
    'human_interruption_detection': False,
    'human_cooldown_period': 5,
    'show_status_window': False,
    'notifier_style': {
        'bg_color': 'black',
        'fg_color': 'white',
        'font_family': 'Segoe UI',
        'font_size': 10
    },
    'secure_mode': False,
    'default_timeout': 10,
    'default_retry_interval': 0.5
}

class UIController:
    # ======================================================================
    #                      BỘ TỪ KHÓA VÀ THAM SỐ HỢP LỆ
    # ======================================================================

    PWA_PROPS = {"pwa_title", "pwa_auto_id", "pwa_control_type", "pwa_class_name", "pwa_framework_id"}
    WIN32_PROPS = {"win32_handle", "win32_styles", "win32_extended_styles"}
    STATE_PROPS = {"state_is_visible", "state_is_enabled", "state_is_active", "state_is_minimized", "state_is_maximized",
                   "state_is_focusable", "state_is_password", "state_is_offscreen", "state_is_content_element", "state_is_control_element"}
    GEO_PROPS = {"geo_rectangle_tuple", "geo_bounding_rect_tuple", "geo_center_point"}
    PROC_PROPS = {"proc_pid", "proc_thread_id", "proc_name", "proc_path", "proc_cmdline", "proc_create_time", "proc_username"}
    REL_PROPS = {"rel_level", "rel_parent_handle", "rel_parent_title", "rel_labeled_by", "rel_child_count"}
    SUPPORTED_KEYS = PWA_PROPS | WIN32_PROPS | STATE_PROPS | GEO_PROPS | PROC_PROPS | REL_PROPS
    
    GETTABLE_PROPERTIES = {'text', 'texts', 'value', 'is_toggled'}.union(SUPPORTED_KEYS)
    BACKGROUND_SAFE_ACTIONS = {'set_text', 'send_message_text'}
    SENSITIVE_ACTIONS = {'paste_text', 'type_keys', 'set_text'}
    SORTING_KEYS = {'sort_by_creation_time', 'sort_by_title_length', 'sort_by_child_count',
                    'sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height', 'z_order_index'}
    STRING_OPERATORS = {'equals', 'iequals', 'contains', 'icontains', 'in', 'regex'}
    NUMERIC_OPERATORS = {'>', '>=', '<', '<='}
    VALID_OPERATORS = STRING_OPERATORS.union(NUMERIC_OPERATORS)
    VALID_ACTIONS = {'click', 'double_click', 'right_click', 'focus', 'invoke', 'toggle',
                     'select', 'set_text', 'paste_text', 'type_keys', 'send_message_text'}

    # ======================================================================
    #                           KHỞI TẠO VÀ CÁC HÀM CHÍNH
    # ======================================================================

    def __init__(self, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.backend = kwargs.get('backend', DEFAULT_CONTROLLER_CONFIG['backend'])
        self.human_interruption_detection = kwargs.get('human_interruption_detection', DEFAULT_CONTROLLER_CONFIG['human_interruption_detection'])
        self.human_cooldown_period = kwargs.get('human_cooldown_period', DEFAULT_CONTROLLER_CONFIG['human_cooldown_period'])
        self.secure_mode = kwargs.get('secure_mode', DEFAULT_CONTROLLER_CONFIG['secure_mode'])
        
        self.desktop = Desktop(backend=self.backend)
        self._last_human_activity_time = 0
        self._is_bot_acting = False
        self._bot_acting_lock = threading.Lock()
        self._proc_info_cache = {}
        
        self.notifier = None
        show_status = kwargs.get('show_status_window', DEFAULT_CONTROLLER_CONFIG['show_status_window'])
        if show_status:
            try:
                from ui_notify import StatusNotifier
                notifier_style = kwargs.get('notifier_style', DEFAULT_CONTROLLER_CONFIG['notifier_style'])
                self.notifier = StatusNotifier(notifier_style)
            except ImportError as e:
                self.logger.warning(f"Không thể import StatusNotifier, tính năng thông báo trạng thái sẽ bị vô hiệu hóa. Lỗi: {e}")
        
        if self.human_interruption_detection:
            self._start_input_listener()

    def _update_status(self, message):
        if self.notifier:
            self.notifier.update_status(message)

    def close(self):
        self.logger.info("Đóng UIController...")
        if self.notifier:
            self.notifier.stop()
            
    def show_custom_status(self, message, log_level="INFO"):
        """Hiển thị một thông báo tùy chỉnh lên cửa sổ trạng thái và ghi log."""
        self.logger.log(logging.getLevelName(log_level), message)
        self._update_status(message)

    def get_next_state(self, cases, timeout=None, retry_interval=None, description=None):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        log_message = description or f"Chờ 1 trong {len(cases)} trạng thái..."
        self.logger.info(log_message)
        self._update_status(log_message)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            for case_name, specs in cases.items():
                self.logger.debug(f"--- Đang kiểm tra trường hợp: '{case_name}' ---")
                try:
                    self._find_target(specs.get('window_spec'), specs.get('element_spec'), timeout=0)
                    self.logger.info(f"-> Đã xác định trạng thái: '{case_name}'")
                    self._update_status(f"Trạng thái: {case_name}")
                    return case_name
                except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError):
                    continue
            time.sleep(retry_interval)
        
        self.logger.warning(f"Hết thời gian chờ. Không có trường hợp nào xảy ra trong {timeout} giây.")
        self._update_status("Hết thời gian chờ.")
        return None

    def select_element(self, window_spec, element_spec=None, timeout=None, retry_interval=None, description=None):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        log_message = description or "Đang tìm kiếm element..."
        self.logger.info(log_message)
        self._update_status(log_message)
        
        target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
        
        success_message = f"Tìm thấy: '{target_element.window_text()}'"
        self.logger.info(f"-> Lựa chọn THÀNH CÔNG. {success_message}\n")
        self._update_status(success_message)
        return target_element

    def run_action(self, window_spec, element_spec=None, action=None, timeout=None, auto_activate=False, retry_interval=None, description=None):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        log_action = action
        if self.secure_mode and action and ':' in action:
            command, _ = action.split(':', 1)
            if command.lower().strip() in self.SENSITIVE_ACTIONS:
                log_action = f"{command}:********"
        
        log_message = description or f"Bắt đầu tác vụ: run_action='{log_action or 'Find Only'}'"
        self.logger.info(log_message)
        self._update_status(log_message)
        
        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
            if action:
                command = action.split(':', 1)[0].lower().strip()
                if command not in self.BACKGROUND_SAFE_ACTIONS:
                    self._handle_activation(target_element, command, timeout, auto_activate)
                
                self.logger.info(f"-> Bắt đầu thực thi hành động '{log_action}'...")
                self._execute_action_safely(target_element, action)
            
            self.logger.info("--- TÁC VỤ HOÀN TẤT THÀNH CÔNG ---\n")
            self._update_status("Thành công!")
            return True
        except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError, UIActionError) as e:
            self.logger.error(f"Lỗi trong quá trình thực thi: {type(e).__name__} - {e}")
            self.logger.error("--- TÁC VỤ THẤT BẠI ---\n")
            self._update_status(f"Thất bại: {type(e).__name__}")
            return False
        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn trong run_action: {e}", exc_info=True)
            self.logger.error("--- TÁC VỤ THẤT BẠI ---\n")
            self._update_status("Lỗi không mong muốn!")
            return False

    def get_property(self, window_spec, element_spec=None, property_name=None, timeout=None, retry_interval=None, description=None):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        log_message = description or f"Đang lấy thuộc tính: '{property_name}'"
        self.logger.info(log_message)
        self._update_status(log_message)

        if property_name not in self.GETTABLE_PROPERTIES:
            raise ValueError(f"Thuộc tính '{property_name}' không được hỗ trợ.")

        self._wait_for_user_idle()
        target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
        value = self._get_actual_value(target_element, property_name)
        
        success_message = f"Lấy được '{property_name}' = {repr(value)}"
        self.logger.info(f"-> THÀNH CÔNG. {success_message}\n")
        self._update_status(success_message)
        return value

    # ======================================================================
    #                           CÁC HÀM NỘI BỘ (Không đổi)
    # ======================================================================
    
    def _get_process_info(self, pid):
        if pid in self._proc_info_cache: return self._proc_info_cache[pid]
        if pid > 0:
            try:
                p = psutil.Process(pid)
                info = {'proc_name': p.name(), 'proc_path': p.exe(), 'proc_cmdline': ' '.join(p.cmdline()),
                        'proc_create_time': p.create_time(), 'proc_username': p.username()}
                self._proc_info_cache[pid] = info
                return info
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        return {}

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

    def _wait_for_user_idle(self):
        if not self.human_interruption_detection: return
        idle_since = self._last_human_activity_time
        if time.time() - idle_since < self.human_cooldown_period:
            self.logger.info("Phát hiện người dùng đang hoạt động. Chương trình sẽ tạm dừng...")
            self._update_status("Phát hiện người dùng, đang tạm dừng...")
            while True:
                if self._last_human_activity_time > idle_since: idle_since = self._last_human_activity_time
                idle_duration = time.time() - idle_since
                if idle_duration >= self.human_cooldown_period:
                    self.logger.info("Người dùng đã ngừng hoạt động. Tiếp tục thực thi...")
                    print()
                    break
                remaining = self.human_cooldown_period - idle_duration
                print(f"\rChờ người dùng... tiếp tục sau {remaining:.1f} giây. ", end="", flush=True)
                time.sleep(0.5)

    def _execute_action_safely(self, element, action_str):
        with self._bot_acting_lock: self._is_bot_acting = True
        try: self._execute_action(element, action_str)
        finally:
            with self._bot_acting_lock: self._is_bot_acting = False

    def _find_target(self, window_spec, element_spec=None, timeout=10, retry_interval=0.5):
        start_time = time.time()
        last_error = ""
        while time.time() - start_time < timeout:
            try:
                window = self._find_unique_element(window_spec, self.desktop.windows, "Window", timeout)
                if not element_spec: return window
                return self._find_unique_element(element_spec, window.descendants, "Element", timeout)
            except (ElementNotFoundError, AmbiguousElementError) as e:
                if isinstance(e, AmbiguousElementError): raise e
                last_error = str(e)
                time.sleep(retry_interval)
        raise WindowNotFoundError(f"Không thể tìm thấy mục tiêu sau {timeout} giây. Lỗi cuối cùng: {last_error}")

    def _handle_activation(self, target_element, command, timeout, auto_activate):
        top_window = target_element.top_level_parent()
        if not top_window.is_active():
            if auto_activate:
                self.logger.info(f"Tự động kích hoạt cửa sổ '{top_window.window_text()}'...")
                self._update_status(f"Kích hoạt: {top_window.window_text()}")
                if top_window.is_minimized(): top_window.restore()
                top_window.set_focus()
                time.sleep(0.5)
                if not top_window.is_active():
                    self.logger.info("set_focus() không đủ, thử phương pháp minimize/restore...")
                    try:
                        top_window.minimize()
                        time.sleep(0.5)
                        top_window.restore()
                        time.sleep(0.5)
                        top_window.set_focus()
                    except Exception as e:
                        self.logger.warning(f"Lỗi khi thử minimize/restore: {e}")
                        top_window.set_focus()
                wait_start = time.time()
                while time.time() - wait_start < 5:
                    if top_window.is_active():
                        self.logger.info("-> Kích hoạt thành công.")
                        return
                    time.sleep(0.2)
                raise UIActionError("Nỗ lực tự động kích hoạt cửa sổ thất bại.")
            else:
                self.logger.warning(f"Cửa sổ '{top_window.window_text()}' không được active. Vui lòng click vào cửa sổ.")
                self._update_status(f"Chờ kích hoạt: {top_window.window_text()}")
                wait_start_time = time.time()
                while time.time() - wait_start_time < timeout:
                    if top_window.is_active():
                        self.logger.info("Cửa sổ đã được kích hoạt.")
                        return
                    time.sleep(0.5)
                raise UIActionError(f"Hết thời gian chờ. Cửa sổ không được kích hoạt.")

    def _find_unique_element(self, spec, find_func, search_type, timeout=10):
        filter_spec, selector_spec = self._split_spec(spec)
        native_spec, custom_filters = self._split_pwa_native_spec(filter_spec)
        candidates = find_func(**native_spec)
        if not candidates: raise ElementNotFoundError(f"[{search_type}] Lọc thô thất bại với: {native_spec}")
        candidates = self._apply_filters(candidates, custom_filters)
        if not candidates: raise ElementNotFoundError(f"[{search_type}] Lọc tinh thất bại với: {custom_filters}")
        if len(candidates) > 1 and not selector_spec:
            self.logger.debug(f"Tìm thấy nhiều ứng viên. Mặc định chọn cái mới nhất.")
            selector_spec['sort_by_creation_time'] = -1
        candidates = self._apply_selectors(candidates, selector_spec)
        if len(candidates) > 1:
            details = [f"'{c.window_text()}' (pid: {c.process_id()})" for c in candidates[:5]]
            raise AmbiguousElementError(f"[{search_type}] Tìm thấy {len(candidates)} ứng viên không rõ ràng: {details}")
        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Không còn ứng viên nào sau khi lựa chọn.")
        return candidates[0]

    def _split_spec(self, spec):
        filter_spec = {k: v for k, v in spec.items() if k not in self.SORTING_KEYS}
        selector_spec = {k: v for k, v in spec.items() if k in self.SORTING_KEYS}
        return filter_spec, selector_spec

    def _split_pwa_native_spec(self, spec):
        native_spec, custom_filters = {}, {}
        native_keys = { 'pwa_title': 'title', 'pwa_class_name': 'class_name', 'win32_handle': 'handle', 'proc_pid': 'process' }
        for key, value in spec.items():
            if key in native_keys and not isinstance(value, tuple):
                native_spec[native_keys[key]] = value
            else:
                custom_filters[key] = value
        return native_spec, custom_filters

    def _apply_filters(self, elements, spec):
        if not spec: return elements
        return [elem for elem in elements if self._element_matches_spec(elem, spec)]

    def _element_matches_spec(self, elem, spec):
        for key, criteria in spec.items():
            if key == 'pwa_control_type' and isinstance(criteria, int):
                if elem.element_info.control_id != criteria: return False
                continue
            actual_value = self._get_actual_value(elem, key)
            if not self._check_condition(actual_value, criteria): return False
        return True

    def _check_condition(self, actual_value, criteria):
        if not isinstance(criteria, tuple): return actual_value == criteria
        if len(criteria) != 2:
            self.logger.warning(f"Cú pháp bộ lọc không hợp lệ: {criteria}. Bỏ qua.")
            return False
        operator, target_value = criteria
        op = str(operator).lower()
        if op not in self.VALID_OPERATORS:
            self.logger.warning(f"Toán tử không được hỗ trợ: '{op}'. Bỏ qua.")
            return False
        if actual_value is None: return False
        if op in self.STRING_OPERATORS:
            str_actual = str(actual_value)
            if op == 'equals': return str_actual == target_value
            if op == 'iequals': return str_actual.lower() == str(target_value).lower()
            if op == 'contains': return str(target_value) in str_actual
            if op == 'icontains': return str(target_value).lower() in str_actual.lower()
            if op == 'in': return str_actual in target_value
            if op == 'regex': return re.search(str(target_value), str_actual) is not None
        if op in self.NUMERIC_OPERATORS:
            try:
                num_actual, num_target = float(actual_value), float(target_value)
                if op == '>': return num_actual > num_target
                if op == '>=': return num_actual >= num_target
                if op == '<': return num_actual < num_target
                if op == '<=': return num_actual <= num_target
            except (ValueError, TypeError): return False
        return False

    def _apply_selectors(self, candidates, selectors):
        if not selectors: return candidates
        sorted_candidates = list(candidates)
        for key, index in selectors.items():
            if key == 'z_order_index': continue
            sort_key_func = self._get_sort_key_function(key)
            if sort_key_func:
                reverse_order = (index < 0)
                sorted_candidates.sort(key=sort_key_func, reverse=reverse_order)
        final_index = 0
        if 'z_order_index' in selectors: final_index = selectors['z_order_index']
        elif selectors:
            last_selector_key = list(selectors.keys())[-1]
            final_index = selectors[last_selector_key]
            final_index = final_index - 1 if final_index > 0 else final_index
        try:
            return [sorted_candidates[final_index]]
        except IndexError:
            raise ElementNotFoundError(f"Lựa chọn index={final_index} nằm ngoài phạm vi.")
        
    def _get_sort_key_function(self, key):
        if key == 'sort_by_creation_time': return lambda e: self._get_actual_value(e, 'proc_create_time') or 0
        if key == 'sort_by_title_length': return lambda e: len(self._get_actual_value(e, 'pwa_title') or '')
        if key == 'sort_by_child_count': return lambda e: self._get_actual_value(e, 'rel_child_count') or 0
        if key in ['sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height']:
            def get_rect_prop(elem, prop_key):
                rect = self._get_actual_value(elem, 'geo_bounding_rect_tuple')
                if not rect: return 0
                if prop_key == 'sort_by_y_pos': return rect[1]
                if prop_key == 'sort_by_x_pos': return rect[0]
                if prop_key == 'sort_by_width': return rect[2] - rect[0]
                if prop_key == 'sort_by_height': return rect[3] - rect[1]
            return lambda e: get_rect_prop(e, key)
        return None

    def _get_actual_value(self, element, key):
        prop = key.lower()
        try:
            if prop in {'text', 'texts', 'value', 'is_toggled'}:
                if prop == 'text': return element.window_text()
                if prop == 'texts': return element.texts()
                if prop == 'value': return element.get_value() if hasattr(element, 'get_value') else None
                if prop == 'is_toggled': return element.get_toggle_state() == 1 if hasattr(element, 'get_toggle_state') else None
            if prop in self.PWA_PROPS:
                prop_map = {'pwa_title': 'name', 'pwa_auto_id': 'automation_id', 'pwa_class_name': 'class_name', 'pwa_control_type': 'control_type', 'pwa_framework_id': 'framework_id'}
                pwa_prop = prop_map.get(prop)
                return getattr(element.element_info, pwa_prop, None) if pwa_prop else None
            if prop in self.STATE_PROPS:
                if prop == 'state_is_visible': return element.is_visible()
                # ...
            handle = element.handle
            if handle:
                if prop in self.WIN32_PROPS:
                    if prop == 'win32_handle': return handle
                    # ...
                if prop == 'rel_parent_handle': return win32gui.GetParent(handle)
                if prop == 'proc_thread_id': return win32process.GetWindowThreadProcessId(handle)[0]
            if prop in self.GEO_PROPS:
                rect = element.rectangle()
                if prop in ['geo_rectangle_tuple', 'geo_bounding_rect_tuple']: return rect.left, rect.top, rect.right, rect.bottom
                # ...
            if prop in self.PROC_PROPS:
                pid = element.process_id()
                if prop == 'proc_pid': return pid
                proc_info = self._get_process_info(pid)
                # ...
            if prop in self.REL_PROPS:
                if prop == 'rel_child_count': return len(element.children())
                # ...
            return None
        except Exception as e:
            self.logger.debug(f"Lỗi nhỏ khi lấy thuộc tính '{prop}': {e}")
            return None

    def _execute_action(self, element, action_str):
        self.logger.debug(f"Thực thi hành động '{action_str}' trên element '{element.window_text()}'")
        parts = action_str.split(':', 1)
        command = parts[0].lower().strip()
        value = parts[1] if len(parts) > 1 else None
        try:
            if command not in self.VALID_ACTIONS:
                raise ValueError(f"Hành động '{command}' không được hỗ trợ.")
            if command == 'click': element.click_input()
            # ...
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
