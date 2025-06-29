# Elements/ui_controller.py
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

# --- Import từ các module tùy chỉnh ---
from ui_spec_definitions import get_all_supported_keys
from ui_core import get_process_info

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

class UIController:
    SUPPORTED_KEYS = get_all_supported_keys()
    BACKGROUND_SAFE_ACTIONS = {'set_text', 'send_message_text'}
    SORTING_KEYS = {
        'sort_by_creation_time', 'sort_by_title_length', 'sort_by_child_count',
        'sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height',
        'z_order_index'
    }

    def __init__(self, backend='uia', human_interruption_detection=False, human_cooldown_period=5):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.desktop = Desktop(backend=backend)
        self.human_interruption_detection = human_interruption_detection
        self.human_cooldown_period = human_cooldown_period
        self._last_human_activity_time = 0
        self._is_bot_acting = False
        self._bot_acting_lock = threading.Lock()
        if self.human_interruption_detection:
            self._start_input_listener()

    def select_element(self, window_spec, element_spec=None, timeout=10):
        self.logger.info("Bắt đầu tác vụ: select_element (Standalone)")
        target_element = self._find_target(window_spec, element_spec, timeout)
        self.logger.info(f"-> Lựa chọn THÀNH CÔNG. Đã tìm thấy: '{target_element.window_text()}'\n")
        return target_element

    def run_action(self, window_spec, element_spec=None, action=None, timeout=10, auto_activate=False):
        self.logger.info(f"Bắt đầu tác vụ: run_action='{action or 'Find Only'}'")
        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout)
            if action:
                command = action.split(':', 1)[0].lower().strip()
                if command not in self.BACKGROUND_SAFE_ACTIONS:
                    self._handle_activation(target_element, command, timeout, auto_activate)
                self.logger.info(f"-> Bắt đầu thực thi hành động '{action}'...")
                self._execute_action_safely(target_element, action)
            self.logger.info("--- TÁC VỤ HOÀN TẤT THÀNH CÔNG ---\n")
            return True
        except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError, UIActionError) as e:
            self.logger.error(f"Lỗi trong quá trình thực thi: {type(e).__name__} - {e}")
            self.logger.error("--- TÁC VỤ THẤT BẠI ---\n")
            return False
        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn trong run_action: {e}", exc_info=True)
            self.logger.error("--- TÁC VỤ THẤT BẠI ---\n")
            return False

    def get_property(self, window_spec, element_spec=None, property_name=None, timeout=10):
        self.logger.info(f"Bắt đầu tác vụ: get_property='{property_name}'")
        self._wait_for_user_idle()
        target_element = self._find_target(window_spec, element_spec, timeout)
        value = self._get_property_value(target_element, property_name)
        self.logger.info(f"-> THÀNH CÔNG. Lấy thuộc tính '{property_name}' có giá trị = {repr(value)}\n")
        return value

    def _start_input_listener(self):
        listener_thread = threading.Thread(target=self._run_listeners, daemon=True)
        listener_thread.start()

    def _update_last_activity(self, *args):
        with self._bot_acting_lock:
            if not self._is_bot_acting:
                self._last_human_activity_time = time.time()

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
            while True:
                if self._last_human_activity_time > idle_since:
                    idle_since = self._last_human_activity_time
                
                idle_duration = time.time() - idle_since
                if idle_duration >= self.human_cooldown_period:
                    self.logger.info("Người dùng đã ngừng hoạt động. Tiếp tục thực thi...")
                    print()
                    break
                
                remaining = self.human_cooldown_period - idle_duration
                print(f"\rChờ người dùng... tiếp tục sau {remaining:.1f} giây. ", end="", flush=True)
                time.sleep(0.5)

    def _execute_action_safely(self, element, action_str):
        with self._bot_acting_lock:
            self._is_bot_acting = True
        try:
            self._execute_action(element, action_str)
        finally:
            with self._bot_acting_lock:
                self._is_bot_acting = False

    def _find_target(self, window_spec, element_spec=None, timeout=10):
        start_time = time.time()
        last_error = ""
        while time.time() - start_time < timeout:
            try:
                window = self._find_unique_element(window_spec, self.desktop.windows, "Window")
                if not element_spec:
                    return window
                return self._find_unique_element(element_spec, window.descendants, "Element")
            except ElementNotFoundError as e:
                last_error = str(e)
                time.sleep(0.5)
        raise WindowNotFoundError(f"Không thể tìm thấy mục tiêu sau {timeout} giây. Lỗi cuối cùng: {last_error}")

    def _handle_activation(self, target_element, command, timeout, auto_activate):
        top_window = target_element.top_level_parent()
        if not top_window.is_active():
            if auto_activate:
                self.logger.info(f"Tự động kích hoạt cửa sổ '{top_window.window_text()}'...")
                top_window.set_focus()
                
                wait_start = time.time()
                while time.time() - wait_start < 5:
                    if top_window.is_active():
                        self.logger.info("-> Kích hoạt thành công.")
                        return
                    time.sleep(0.2)
                raise UIActionError("Nỗ lực tự động kích hoạt cửa sổ thất bại.")
            else:
                # ===== NÂNG CẤP LOGGING THEO YÊU CẦU =====
                self.logger.info(f"Hành động '{command}' yêu cầu cửa sổ '{top_window.window_text()}' được kích hoạt.")
                self.logger.warning(f"Cửa sổ không được active. Vì 'auto_activate=False', chương trình sẽ chờ bạn click chuột vào cửa sổ.")
                self.logger.info(f"Đang chờ người dùng kích hoạt cửa sổ (tối đa {timeout} giây)...")
                # ==========================================
                
                wait_start_time = time.time()
                while time.time() - wait_start_time < timeout:
                    if top_window.is_active():
                        self.logger.info("Cửa sổ đã được kích hoạt. Tiếp tục thực thi.")
                        return
                    time.sleep(0.5)
                raise UIActionError(f"Hết thời gian chờ. Cửa sổ không được kích hoạt trong {timeout} giây.")

    def _find_unique_element(self, spec, find_func, search_type):
        filter_spec, selector_spec = self._split_spec(spec)
        native_spec, custom_filters = self._split_pwa_native_spec(filter_spec)
        
        candidates = find_func(**native_spec)
        if not candidates: raise ElementNotFoundError(f"[{search_type}] Lọc thô thất bại với: {native_spec}")
        
        candidates = self._apply_filters(candidates, custom_filters)
        if not candidates: raise ElementNotFoundError(f"[{search_type}] Lọc tinh thất bại với: {custom_filters}")
        
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
        native_keys = {
            'pwa_title': 'title', 
            'pwa_class_name': 'class_name', 
            'win32_handle': 'handle',
            'proc_pid': 'process'
        }
        
        for key, value in spec.items():
            if key in native_keys:
                mapped_key = native_keys[key]
                if isinstance(value, tuple) and value[0].lower() == 'regex' and mapped_key in ['title', 'class_name']:
                    native_spec[mapped_key + '_re'] = value[1]
                else:
                    native_spec[mapped_key] = value
            else:
                custom_filters[key] = value
                
        return native_spec, custom_filters

    def _apply_filters(self, elements, spec):
        if not spec: return elements
        return [elem for elem in elements if self._element_matches_spec(elem, spec)]

    def _element_matches_spec(self, elem, spec):
        for key, criteria in spec.items():
            actual_value = self._get_actual_value(elem, key)
            if not self._check_condition(actual_value, criteria):
                return False
        return True

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
        if 'z_order_index' in selectors:
            final_index = selectors['z_order_index']
        elif selectors:
            last_selector_key = list(selectors.keys())[-1]
            final_index = selectors[last_selector_key]
            final_index = final_index - 1 if final_index > 0 else final_index
        
        try:
            return [sorted_candidates[final_index]]
        except IndexError:
            raise ElementNotFoundError(f"Lựa chọn index={final_index} nằm ngoài phạm vi ({len(sorted_candidates)} ứng viên).")
        
    def _get_sort_key_function(self, key):
        if key == 'sort_by_creation_time':
            return lambda e: self._get_actual_value(e, 'proc_create_time') or 0
        if key == 'sort_by_title_length':
            return lambda e: len(self._get_actual_value(e, 'pwa_title') or '')
        if key == 'sort_by_child_count':
            return lambda e: self._get_actual_value(e, 'rel_child_count') or 0
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

    def _get_actual_value(self, element, prefixed_key):
        if prefixed_key not in self.SUPPORTED_KEYS: return None
        try:
            if prefixed_key.startswith('pwa_'):
                prop_map = {'pwa_title': 'name', 'pwa_auto_id': 'automation_id', 'pwa_class_name': 'class_name', 'pwa_control_type': 'control_type', 'pwa_framework_id': 'framework_id'}
                prop = prop_map.get(prefixed_key)
                return getattr(element.element_info, prop, None) if prop else None
            if prefixed_key.startswith('state_'):
                if prefixed_key == 'state_is_visible': return element.is_visible()
                if prefixed_key == 'state_is_enabled': return element.is_enabled()
                if prefixed_key == 'state_is_active': return element.is_active()
                if prefixed_key == 'state_is_minimized': return element.is_minimized()
                if prefixed_key == 'state_is_maximized': return element.is_maximized()
                if prefixed_key == 'state_is_focusable': return element.is_keyboard_focusable()
                if prefixed_key == 'state_is_password': return element.is_password()
                if prefixed_key == 'state_is_offscreen': return element.is_offscreen()
                if prefixed_key == 'state_is_content_element': return element.is_content_element()
                if prefixed_key == 'state_is_control_element': return element.is_control_element()
            handle = element.handle
            if handle:
                if prefixed_key.startswith('win32_'):
                    if prefixed_key == 'win32_handle': return handle
                    if prefixed_key == 'win32_styles': return hex(win32gui.GetWindowLong(handle, win32con.GWL_STYLE))
                    if prefixed_key == 'win32_extended_styles': return hex(win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE))
                if prefixed_key == 'rel_parent_handle': return win32gui.GetParent(handle)
                if prefixed_key == 'proc_thread_id': return win32process.GetWindowThreadProcessId(handle)[0]
            if prefixed_key.startswith('geo_'):
                rect = element.rectangle()
                if prefixed_key in ['geo_rectangle_tuple', 'geo_bounding_rect_tuple']: return rect.left, rect.top, rect.right, rect.bottom
                if prefixed_key == 'geo_center_point': return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
            if prefixed_key.startswith('proc_'):
                pid = element.process_id()
                if prefixed_key == 'proc_pid': return pid
                proc_info = get_process_info(pid)
                if prefixed_key == 'proc_name': return proc_info.get('proc_name')
                if prefixed_key == 'proc_create_time': return proc_info.get('proc_create_time')
                if prefixed_key == 'proc_path': return proc_info.get('proc_path')
                if prefixed_key == 'proc_cmdline': return proc_info.get('proc_cmdline')
                if prefixed_key == 'proc_username': return proc_info.get('proc_username')
            if prefixed_key.startswith('rel_'):
                if prefixed_key == 'rel_level':
                    level, current = 0, element
                    for _ in range(50): 
                        parent = current.parent()
                        if not parent or parent == current: return level
                        current, level = parent, level + 1
                    return level
                if prefixed_key == 'rel_child_count': return len(element.children())
                if prefixed_key == 'rel_parent_title': return element.parent().window_text() if element.parent() else None
                if prefixed_key == 'rel_labeled_by': return element.labeled_by().window_text() if hasattr(element, 'labeled_by') and element.labeled_by() else None
            return None
        except Exception as e:
            self.logger.debug(f"Lỗi nhỏ khi lấy thuộc tính '{prefixed_key}': {e}")
            return None

    def _check_condition(self, actual_value, criteria):
        if not isinstance(criteria, tuple): return actual_value == criteria
        if len(criteria) != 2: return False
        operator, target_value = criteria
        if actual_value is None: return False
        op = str(operator).lower()
        if op == 'is_within':
            l, t, r, b = actual_value
            x1, y1, x2, y2 = target_value
            return l >= x1 and t >= y1 and r <= x2 and b <= y2
        if op in ('contains', 'icontains', 'startswith', 'endswith', 'regex'):
            str_actual, str_target = str(actual_value), str(target_value)
            if op == 'contains': return str_target in str_actual
            if op == 'icontains': return str_target.lower() in str_actual.lower()
            if op == 'startswith': return str_actual.startswith(str_target)
            if op == 'endswith': return str_actual.endswith(str_target)
            if op == 'regex': return re.search(str_target, str_actual) is not None
        if op in ('>', '>=', '<', '<='):
            try:
                num_actual, num_target = float(actual_value), float(target_value)
                if op == '>': return num_actual > num_target
                if op == '>=': return num_actual >= num_target
                if op == '<': return num_actual < num_target
                if op == '<=': return num_actual <= num_target
            except (ValueError, TypeError): return False
        if op == 'in': return actual_value in target_value
        return False

    def _execute_action(self, element, action_str):
        self.logger.debug(f"Thực thi hành động '{action_str}' trên element '{element.window_text()}'")
        parts = action_str.split(':', 1)
        command = parts[0].lower().strip()
        value = parts[1] if len(parts) > 1 else None
        try:
            if command == 'click': element.click_input()
            elif command == 'double_click': element.double_click_input()
            elif command == 'right_click': element.right_click_input()
            elif command == 'focus': element.set_focus()
            elif command == 'invoke': element.invoke()
            elif command == 'toggle': element.toggle()
            elif command == 'select':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                element.select(value)
            elif command == 'set_text':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                element.set_edit_text(value)
            elif command == 'paste_text':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                pyperclip.copy(value)
                element.type_keys('^a^v', pause=0.1) 
            elif command == 'type_keys':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                element.type_keys(value, with_spaces=True, with_newlines=True, pause=0.01)
            elif command == 'send_message_text':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                if not element.handle: raise UIActionError("Action 'send_message_text' yêu cầu element phải có handle.")
                win32api.SendMessage(element.handle, win32con.WM_SETTEXT, 0, value)
            else:
                raise ValueError(f"Hành động '{command}' không được hỗ trợ.")
        except Exception as e:
            raise UIActionError(f"Thực thi hành động '{action_str}' thất bại. Lỗi gốc: {type(e).__name__} - {e}") from e

    def _get_property_value(self, element, property_name):
        prop = property_name.lower()
        try:
            if prop == 'text': return element.window_text()
            if prop == 'texts': return element.texts()
            if prop == 'value': return element.get_value() if hasattr(element, 'get_value') else None
            if prop == 'is_toggled': return element.get_toggle_state() == 1 if hasattr(element, 'get_toggle_state') else None
            return self._get_actual_value(element, prop)
        except Exception as e:
            self.logger.error(f"Lỗi khi lấy thuộc tính '{prop}': {e}", exc_info=True)
            return None
