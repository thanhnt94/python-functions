# Elements/ui_controller.py
# Phiên bản 19.0: Logging siêu chi tiết, in ra tất cả các ứng viên và các thuộc tính được lọc.

import logging
import re
import time
import math
import threading
from datetime import datetime

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
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# --- Định nghĩa Exception tùy chỉnh ---
class UIActionError(Exception): pass
class WindowNotFoundError(UIActionError): pass
class AmbiguousElementError(UIActionError): pass

# --- Import an toàn và Hàm trợ giúp ---
try:
    from .ui_notify import StatusNotifier

    def create_notifier_callback(notifier_instance):
        if not isinstance(notifier_instance, StatusNotifier):
            return None
        
        def event_handler(event_type, message, **kwargs):
            notifier_instance.update_status(
                text=message,
                style=event_type,
                duration=kwargs.get('duration')
            )
        return event_handler

except ImportError:
    logging.warning("Module 'ui_notify' không được tìm thấy. Các tính năng thông báo sẽ bị vô hiệu hóa.")
    StatusNotifier = None
    def create_notifier_callback(notifier_instance):
        return None

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
    
    STRING_OPERATORS = {'equals', 'iequals', 'contains', 'icontains', 'in', 'regex',
                        'not_equals', 'not_iequals', 'not_contains', 'not_icontains'}
    NUMERIC_OPERATORS = {'>', '>=', '<', '<='}
    VALID_OPERATORS = STRING_OPERATORS.union(NUMERIC_OPERATORS)
    VALID_ACTIONS = {'click', 'double_click', 'right_click', 'focus', 'invoke', 'toggle',
                     'select', 'set_text', 'paste_text', 'type_keys', 'send_message_text'}

    # ======================================================================
    #                           KHỞI TẠO VÀ CÁC HÀM CHÍNH
    # ======================================================================

    def __init__(self, notifier=None, event_callback=None, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        if event_callback:
            self.event_callback = event_callback
        elif notifier:
            self.event_callback = create_notifier_callback(notifier)
        else:
            self.event_callback = None
        
        self.backend = kwargs.get('backend', DEFAULT_CONTROLLER_CONFIG['backend'])
        self.human_interruption_detection = kwargs.get('human_interruption_detection', DEFAULT_CONTROLLER_CONFIG['human_interruption_detection'])
        self.human_cooldown_period = kwargs.get('human_cooldown_period', DEFAULT_CONTROLLER_CONFIG['human_cooldown_period'])
        self.secure_mode = kwargs.get('secure_mode', DEFAULT_CONTROLLER_CONFIG['secure_mode'])
        
        self.desktop = Desktop(backend=self.backend)
        self._last_human_activity_time = time.time() - self.human_cooldown_period
        self._is_bot_acting = False
        self._bot_acting_lock = threading.Lock()
        self._proc_info_cache = {}
        
        if self.human_interruption_detection:
            self._start_input_listener()

    def _emit_event(self, event_type, message, **kwargs):
        log_levels = {"info": logging.INFO, "success": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR, "process": logging.DEBUG, "debug": logging.DEBUG}
        self.logger.log(log_levels.get(event_type, logging.INFO), message)

        if self.event_callback and callable(self.event_callback):
            try:
                self.event_callback(event_type, message, **kwargs)
            except Exception as e:
                self.logger.error(f"Lỗi khi thực thi event_callback: {e}")

    def close(self):
        self.logger.info("Đóng UIController...")
            
    def get_next_state(self, cases, timeout=None, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
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
                except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError) as e:
                    self.logger.debug(f"Case '{case_name}' không khớp. Lý do: {e}")
                    continue
            time.sleep(retry_interval)
        
        self._emit_event('warning', f"Hết thời gian chờ: '{display_message}'")
        return None

    def select_element(self, window_spec, element_spec=None, timeout=None, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        display_message = description or "Tìm kiếm element"
        self._emit_event(notify_style if description else 'info', display_message)
        
        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
            return target_element
        except Exception as e:
            self._emit_event('error', f"Thất bại: {display_message}")
            self.logger.error(f"Lỗi khi thực hiện '{display_message}': {e}", exc_info=True)
            return None

    def run_action(self, window_spec, element_spec=None, action=None, timeout=None, auto_activate=False, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        log_action = action
        if self.secure_mode and action and ':' in action:
            command, _ = action.split(':', 1)
            if command.lower().strip() in self.SENSITIVE_ACTIONS:
                log_action = f"{command}:********"
        
        display_message = description or f"Thực thi tác vụ: {log_action or 'Find Only'}"
        verbose = description is None

        self._emit_event(notify_style if description else 'info', display_message)
        
        try:
            self._wait_for_user_idle()
            
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval, verbose=verbose)

            if action:
                command = action.split(':', 1)[0].lower().strip()
                if command not in self.BACKGROUND_SAFE_ACTIONS:
                    self._handle_activation(target_element, command, timeout, auto_activate, verbose=verbose)
                
                if verbose: self._emit_event('process', f"Đang thực thi hành động '{log_action}'...")
                self._execute_action_safely(target_element, action)
            
            return True
        except Exception as e:
            self.logger.error(f"Lỗi khi thực hiện '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Thất bại: {display_message}")
            return False

    def get_property(self, window_spec, element_spec=None, property_name=None, timeout=None, retry_interval=None, description=None, notify_style='info'):
        timeout = timeout if timeout is not None else DEFAULT_CONTROLLER_CONFIG['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONTROLLER_CONFIG['default_retry_interval']
        
        display_message = description or f"Lấy thuộc tính '{property_name}'"
        verbose = description is None
        self._emit_event(notify_style if description else 'info', display_message)

        if property_name not in self.GETTABLE_PROPERTIES:
            raise ValueError(f"Thuộc tính '{property_name}' không được hỗ trợ.")

        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval, verbose=verbose)
            value = self._get_actual_value(target_element, property_name)
            return value
        except Exception as e:
            self.logger.error(f"Lỗi khi thực hiện '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Thất bại: {display_message}")
            return None

    # ======================================================================
    #                           CÁC HÀM NỘI BỘ
    # ======================================================================
    
    def _find_unique_element(self, spec, find_func, search_type):
        """Hàm tìm kiếm cốt lõi với logging siêu chi tiết."""
        filter_spec, selector_spec = self._split_spec(spec)
        native_spec, custom_filters = self._split_pwa_native_spec(filter_spec)
        
        self.logger.debug(f"[{search_type}] Bắt đầu lọc thô với spec: {native_spec}")
        candidates = find_func(**native_spec)
        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Lọc thô thất bại, không tìm thấy ứng viên nào với: {native_spec}")
        
        # Cải tiến: Ghi log chi tiết các ứng viên tìm thấy
        self.logger.debug(f"[{search_type}] Tìm thấy {len(candidates)} ứng viên sau lọc thô.")
        if len(candidates) > 1 and self.logger.getEffectiveLevel() <= logging.DEBUG:
            # Lấy danh sách các key đã được dùng để lọc
            spec_keys = list(custom_filters.keys())
            
            candidate_details = []
            for i, cand in enumerate(candidates):
                details = [f"Title='{cand.window_text()}'", f"Class='{cand.class_name()}'"]
                for key in spec_keys:
                    value = self._get_actual_value(cand, key)
                    details.append(f"{key}='{value}'")
                candidate_details.append(f"    #{i}: " + ", ".join(details))

            log_message = "  --- Danh sách ứng viên ---\n" + "\n".join(candidate_details)
            self.logger.debug(log_message)

        self.logger.debug(f"[{search_type}] Bắt đầu lọc tinh với spec: {custom_filters}")
        candidates = self._apply_filters(candidates, custom_filters)
        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Lọc tinh thất bại, không còn ứng viên nào sau khi áp dụng: {custom_filters}")
        
        self.logger.debug(f"[{search_type}] Còn lại {len(candidates)} ứng viên sau lọc tinh.")
        if len(candidates) > 1 and self.logger.getEffectiveLevel() <= logging.DEBUG:
            spec_keys = list(custom_filters.keys())
            candidate_details = []
            for i, cand in enumerate(candidates):
                details = [f"Title='{cand.window_text()}'", f"Class='{cand.class_name()}'"]
                for key in spec_keys:
                    value = self._get_actual_value(cand, key)
                    details.append(f"{key}='{value}'")
                candidate_details.append(f"    #{i}: " + ", ".join(details))
            log_message = "  --- Danh sách ứng viên còn lại ---\n" + "\n".join(candidate_details)
            self.logger.debug(log_message)

        if selector_spec:
            self.logger.debug(f"[{search_type}] Bắt đầu lựa chọn với spec: {selector_spec}")
            candidates = self._apply_selectors(candidates, selector_spec)
        
        if len(candidates) > 1:
            details = [f"'{c.window_text()}' (pid: {c.process_id()})" for c in candidates[:5]]
            raise AmbiguousElementError(f"[{search_type}] Tìm thấy {len(candidates)} ứng viên không rõ ràng. Vui lòng cung cấp thêm bộ chọn (ví dụ: sort_by_...). Chi tiết: {details}")
        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Không còn ứng viên nào sau khi lựa chọn.")
        
        self.logger.debug(f"[{search_type}] Đã chọn được ứng viên duy nhất.")
        return candidates[0]

    def _wait_for_user_idle(self):
        if not self.human_interruption_detection:
            return
        
        is_paused = False
        while time.time() - self._last_human_activity_time < self.human_cooldown_period:
            if not is_paused:
                self.logger.info("Phát hiện người dùng đang hoạt động. Chương trình sẽ tạm dừng...")
                self._emit_event('warning', "Phát hiện người dùng! Tạm dừng...")
                is_paused = True

            remaining = self.human_cooldown_period - (time.time() - self._last_human_activity_time)
            countdown_message = f"Tiếp tục sau {math.ceil(remaining)} giây."
            
            self._emit_event('process', countdown_message, duration=1.5)
            print(f"\r{countdown_message} ", end="", flush=True)
            time.sleep(1)

        if is_paused:
            print() 
            self.logger.info("Người dùng đã ngừng hoạt động. Tiếp tục thực thi...")
            self._emit_event('success', "Người dùng đã ngừng. Tiếp tục thực thi...", duration=3)

    def _handle_activation(self, target_element, command, timeout, auto_activate, verbose=True):
        top_window = target_element.top_level_parent()
        if not top_window.is_active():
            if auto_activate:
                if verbose: self._emit_event('info', f"Tự động kích hoạt cửa sổ '{top_window.window_text()}'...")
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
                if verbose: self._emit_event('warning', f"Cửa sổ '{top_window.window_text()}' không active. Vui lòng click vào.")
                wait_start_time = time.time()
                while time.time() - wait_start_time < timeout:
                    if top_window.is_active():
                        self.logger.info("Cửa sổ đã được kích hoạt.")
                        return
                    time.sleep(0.5)
                raise UIActionError(f"Hết thời gian chờ. Cửa sổ không được kích hoạt.")

    def _find_target(self, window_spec, element_spec=None, timeout=10, retry_interval=0.5, verbose=True):
        start_time = time.time()
        last_error = ""
        
        if verbose: self.logger.debug(f"Bắt đầu tìm kiếm mục tiêu. Window Spec: {window_spec}, Element Spec: {element_spec}")

        while True:
            try:
                window = self._find_unique_element(window_spec, self.desktop.windows, "Window")
                if verbose: self.logger.debug(f"Tìm thấy cửa sổ phù hợp: '{window.window_text()}' (Handle: {window.handle})")
                
                if not element_spec:
                    return window
                
                if verbose: self.logger.debug(f"Bắt đầu tìm element bên trong cửa sổ '{window.window_text()}'...")
                element = self._find_unique_element(element_spec, window.descendants, "Element")
                if verbose: self.logger.debug(f"Tìm thấy element phù hợp: '{element.window_text()}'")
                return element

            except (ElementNotFoundError, AmbiguousElementError) as e:
                last_error = str(e)
                if isinstance(e, AmbiguousElementError):
                    raise e
                
                if time.time() - start_time >= timeout:
                    break
                
                time.sleep(retry_interval)
        
        raise WindowNotFoundError(f"Không thể tìm thấy mục tiêu sau {timeout} giây. Lỗi cuối cùng: {last_error}")

    def _get_process_info(self, pid):
        if pid in self._proc_info_cache: return self._proc_info_cache[pid]
        if pid > 0:
            try:
                p = psutil.Process(pid)
                info = {'proc_name': p.name(), 'proc_path': p.exe(), 'proc_cmdline': ' '.join(p.cmdline()),
                        'proc_create_time': datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S'), 'proc_username': p.username()}
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

    def _execute_action_safely(self, element, action_str):
        with self._bot_acting_lock: self._is_bot_acting = True
        try: self._execute_action(element, action_str)
        finally:
            with self._bot_acting_lock: self._is_bot_acting = False

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
            if op == 'not_equals': return str_actual != target_value
            if op == 'not_iequals': return str_actual.lower() != str(target_value).lower()
            if op == 'not_contains': return str(target_value) not in str_actual
            if op == 'not_icontains': return str(target_value).lower() not in str_actual.lower()

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
