# Elements/ui_controller.py
import logging
import re
import time
from datetime import datetime

# --- Thư viện cần thiết ---
try:
    import psutil
    import win32gui
    import win32process
    import win32con
    import win32api
    import pyperclip
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.application import Application
    from pywinauto import Desktop
except ImportError as e:
    if 'pyperclip' in str(e):
        print("Lỗi: Thiếu thư viện 'pyperclip'. Vui lòng cài đặt bằng lệnh: pip install pyperclip")
    else:
        print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# --- Import từ các module tùy chỉnh ---
from ui_spec_definitions import get_all_supported_keys

# --- Cấu hình logging ---
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# --- Định nghĩa Exception tùy chỉnh ---
class UIActionError(Exception):
    """Lỗi chung cho các hành động trên UI."""
    pass

class WindowNotFoundError(UIActionError):
    """Ném ra khi không tìm thấy cửa sổ sau một khoảng thời gian."""
    pass

class AmbiguousElementError(UIActionError):
    """Ném ra khi tìm thấy nhiều hơn một element thỏa mãn."""
    pass

class UIController:
    """
    Lớp đóng gói logic để tìm kiếm, tương tác, và lấy thuộc tính
    từ các thành phần giao diện người dùng trên Windows.
    """
    SELECTOR_KEYWORDS = [
        'latest', 'oldest', 'deepest', 'shallowest', 'most', 'fewest',
        'topmost', 'bottommost', 'leftmost', 'rightmost', 'longest', 'shortest'
    ]
    SUPPORTED_KEYS = get_all_supported_keys()

    # --- THAY ĐỔI 1: Liệt kê các action KHÔNG cần activate ---
    # Bất kỳ action nào không có trong danh sách này sẽ mặc định yêu cầu activate.
    BACKGROUND_SAFE_ACTIONS = {
        'set_text', 
        'send_message_text'
    }

    def __init__(self, backend='uia'):
        """
        Khởi tạo UIController.
        
        Args:
            backend (str): Backend của pywinauto ('uia' hoặc 'win32').
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.desktop = Desktop(backend=backend)
        self.logger.info(f"UIController đã khởi tạo với backend '{backend}'.")

    def _find_target(self, window_spec, element_spec=None, timeout=10):
        """Vòng lặp chính để tìm kiếm cửa sổ và element với cơ chế chờ đợi."""
        self.logger.info(f"Đang chờ và tìm kiếm mục tiêu trong tối đa {timeout} giây...")
        start_time = time.time()
        last_error = ""

        while time.time() - start_time < timeout:
            try:
                window = self._find_unique_element(
                    spec=window_spec,
                    find_func=lambda **kwargs: self.desktop.windows(**kwargs),
                    search_type="Window"
                )
                
                self.logger.info(f"Tìm thấy cửa sổ đích: Title='{window.window_text()}', Handle='{window.handle}'")
                
                if not element_spec:
                    return window

                element = self._find_unique_element(
                    spec=element_spec,
                    find_func=window.descendants,
                    search_type="Element"
                )
                return element
            except (ElementNotFoundError, AmbiguousElementError) as e:
                last_error = str(e)
                time.sleep(0.5)
                continue
        raise WindowNotFoundError(f"Không thể tìm thấy mục tiêu sau {timeout} giây. Lỗi cuối cùng: {last_error}")

    def _find_unique_element(self, spec, find_func, search_type):
        """Quy trình: Lọc thô -> Lọc tinh -> Lựa chọn."""
        filter_spec, selector_spec = self._split_spec(spec)
        pwa_native_spec, other_filters = self._split_pwa_native_spec(filter_spec, search_type)

        self.logger.debug(f"[{search_type}] Lọc thô với tiêu chí PWA: {pwa_native_spec}")
        candidates = find_func(**pwa_native_spec)

        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Lọc thô thất bại với: {pwa_native_spec}")

        self.logger.debug(f"[{search_type}] Tìm thấy {len(candidates)} ứng viên. Lọc tinh với: {other_filters}")
        candidates = self._apply_filters(candidates, other_filters)

        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Lọc tinh thất bại với: {other_filters}")

        if len(candidates) > 1 and selector_spec:
            self.logger.debug(f"[{search_type}] Còn {len(candidates)} ứng viên. Áp dụng lựa chọn: {selector_spec}")
            for key, selector in selector_spec.items():
                candidates = self._apply_selector(candidates, key, selector)
                if len(candidates) <= 1:
                    break

        if not candidates:
            raise ElementNotFoundError(f"[{search_type}] Không còn ứng viên sau khi lựa chọn.")
        if len(candidates) > 1:
            self.logger.warning(f"Tìm thấy {len(candidates)} ứng viên không thể phân biệt:")
            for i, c in enumerate(candidates[:5]):
                self.logger.warning(f"  - Ứng viên {i+1}: name='{c.window_text()}', class='{c.class_name()}'")
            raise AmbiguousElementError(f"[{search_type}] Tìm thấy {len(candidates)} ứng viên không thể phân biệt.")

        return candidates[0]

    def _split_spec(self, spec):
        """Tách spec thành filter_spec và selector_spec."""
        filter_spec, selector_spec = {}, {}
        if not spec:
            return {}, {}
        for key, value in spec.items():
            if isinstance(value, str) and value.lower() in self.SELECTOR_KEYWORDS:
                selector_spec[key] = value.lower()
            else:
                filter_spec[key] = value
        return filter_spec, selector_spec

    def _split_pwa_native_spec(self, spec, search_type):
        """
        Tách spec thành các tiêu chí pwa gốc và các tiêu chí lọc tinh.
        Hàm này giờ sẽ phân biệt giữa việc tìm Window và Element.
        """
        pwa_native_spec = {}
        other_filters = {}

        key_map = {
            'pwa_title': 'title',
            'pwa_class_name': 'class_name',
            'pwa_control_type': 'control_type',
            'pwa_auto_id': 'automation_id',
            'win32_handle': 'handle'
        }

        for key, value in spec.items():
            if key not in key_map:
                other_filters[key] = value
                continue
            
            if key in ['pwa_auto_id', 'win32_handle'] and search_type != "Window":
                other_filters[key] = value
                continue

            mapped_key = key_map[key]

            if isinstance(value, tuple) and len(value) == 2 and value[0].lower() == 'regex':
                if search_type == "Window":
                    pwa_native_spec[mapped_key + '_re'] = value[1]
                else:
                    other_filters[key] = value
            else:
                pwa_native_spec[mapped_key] = value

        return pwa_native_spec, other_filters

    def _apply_filters(self, elements, spec):
        """Áp dụng các bộ lọc nâng cao trên danh sách elements."""
        if not spec:
            return elements
        return [elem for elem in elements if self._element_matches_spec(elem, spec)]

    def _element_matches_spec(self, elem, spec):
        """Kiểm tra một element có khớp với tất cả tiêu chí trong spec không."""
        for key, criteria in spec.items():
            actual_value = self._get_actual_value(elem, key)
            if not self._check_condition(actual_value, criteria):
                return False
        return True

    def _apply_selector(self, candidates, key, selector):
        """Áp dụng bộ chọn để tìm ra element tốt nhất."""
        if not candidates:
            return []
        
        use_max = selector in ['latest', 'deepest', 'most', 'bottommost', 'rightmost', 'longest']
        
        valid_candidates = []
        for c in candidates:
            val = self._get_actual_value(c, key)
            if val is not None:
                valid_candidates.append((c, val))
        
        if not valid_candidates:
            return []

        def get_sort_key(item):
            _key, _val = item[0], item[1]
            if key.endswith('tuple') and selector in ('topmost', 'bottommost'): return _val[1]
            if key.endswith('tuple') and selector in ('leftmost', 'rightmost'): return _val[0]
            if key == 'pwa_title' and selector in ('longest', 'shortest'): return len(str(_val))
            return _val

        try:
            sorted_candidates = sorted(valid_candidates, key=get_sort_key, reverse=use_max)
            return [sorted_candidates[0][0]]
        except Exception as e:
            self.logger.warning(f"Lỗi khi sắp xếp selector '{key}': {e}", exc_info=True)
            return []

    def _get_actual_value(self, element, prefixed_key):
        """Lấy giá trị thực tế của một thuộc tính từ element một cách an toàn."""
        if prefixed_key not in self.SUPPORTED_KEYS:
            self.logger.warning(f"Thuộc tính '{prefixed_key}' không được hỗ trợ. Bỏ qua.")
            return None
        
        try:
            if prefixed_key.startswith('pwa_'):
                prop_map = {
                    'pwa_title': 'name', 'pwa_auto_id': 'automation_id',
                    'pwa_class_name': 'class_name', 'pwa_control_type': 'control_type',
                    'pwa_framework_id': 'framework_id'
                }
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
                if prefixed_key in ['geo_rectangle_tuple', 'geo_bounding_rect_tuple']:
                    return rect.left, rect.top, rect.right, rect.bottom
                if prefixed_key == 'geo_center_point':
                    return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
            
            if prefixed_key.startswith('proc_'):
                p = psutil.Process(element.process_id())
                if prefixed_key == 'proc_pid': return p.pid
                if prefixed_key == 'proc_name': return p.name()
                if prefixed_key == 'proc_create_time': return p.create_time()
                if prefixed_key == 'proc_path': return p.exe()
                if prefixed_key == 'proc_cmdline': return ' '.join(p.cmdline())
                if prefixed_key == 'proc_username': return p.username()

            if prefixed_key.startswith('rel_'):
                if prefixed_key == 'rel_level':
                    level, current = 0, element
                    for _ in range(50): 
                        parent = current.parent()
                        if not parent or parent == current: return level
                        current, level = parent, level + 1
                    return level
                if prefixed_key == 'rel_child_count': return len(element.children())
                if prefixed_key == 'rel_parent_title': return element.parent().window_text()
                if prefixed_key == 'rel_labeled_by': return element.labeled_by().window_text()

            if prefixed_key.startswith('uia_'):
                pass
        except Exception as e:
            self.logger.error(f"Lỗi khi lấy giá trị cho thuộc tính '{prefixed_key}' của element '{element.window_text()}'.", exc_info=True)
            return None
        
        self.logger.debug(f"Thuộc tính '{prefixed_key}' không có giá trị hoặc không áp dụng cho element này.")
        return None

    def _check_condition(self, actual_value, criteria):
        """So sánh giá trị thực tế với điều kiện đưa ra."""
        if not isinstance(criteria, tuple):
            return actual_value == criteria
        if len(criteria) != 2:
            self.logger.error(f"Criteria '{criteria}' không hợp lệ. Phải là một tuple (operator, value).")
            return False

        operator, target_value = criteria
        if actual_value is None:
            return False

        op = str(operator).lower()
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
            except (ValueError, TypeError):
                return False
        if op == 'in':
            return actual_value in target_value

        self.logger.warning(f"Toán tử '{operator}' chưa được hỗ trợ.")
        return False

    def _execute_action(self, element, action_str):
        """Thực thi một chuỗi hành động trên element với các action riêng biệt."""
        self.logger.debug(f"Thực thi hành động '{action_str}' trên element '{element.window_text()}'")
        parts = action_str.split(':', 1)
        command = parts[0].lower().strip()
        value = parts[1] if len(parts) > 1 else None

        try:
            # Các hành động cơ bản
            if command == 'click': element.click_input()
            elif command == 'double_click': element.double_click_input()
            elif command == 'right_click': element.right_click_input()
            elif command == 'focus': element.set_focus()
            elif command == 'invoke': element.invoke()
            elif command == 'toggle': element.toggle()
            elif command == 'select':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                element.select(value)
            
            # --- CÁC ACTION NHẬP LIỆU RIÊNG BIỆT ---
            elif command == 'set_text':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                self.logger.debug("Thực hiện action 'set_text' (phương pháp set_edit_text).")
                element.set_edit_text(value)

            elif command == 'paste_text':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                self.logger.debug("Thực hiện action 'paste_text' (phương pháp pyperclip).")
                pyperclip.copy(value)
                element.type_keys('^a^v', pause=0.1) 

            elif command == 'type_keys':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                self.logger.debug("Thực hiện action 'type_keys' (phương pháp mô phỏng gõ phím).")
                element.type_keys(value, with_spaces=True, with_newlines=True, pause=0.01)

            elif command == 'send_message_text':
                if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
                self.logger.debug("Thực hiện action 'send_message_text' (phương pháp SendMessage).")
                if not element.handle:
                    raise UIActionError("Action 'send_message_text' yêu cầu element phải có handle.")
                win32api.SendMessage(element.handle, win32con.WM_SETTEXT, 0, value)

            else:
                raise ValueError(f"Hành động '{command}' không được hỗ trợ.")

        except Exception as e:
            error_message = f"Thực thi hành động '{action_str}' thất bại. Lỗi gốc: {type(e).__name__} - {e}"
            raise UIActionError(error_message) from e

    def _get_property_value(self, element, property_name):
        """Lấy giá trị của một thuộc tính cụ thể từ element."""
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

    # --- THAY ĐỔI 2: Đưa auto_activate vào làm tham số của hàm run_action ---
    def run_action(self, window_spec, element_spec=None, action=None, timeout=10, auto_activate=False):
        """
        Tìm một element và thực hiện một hành động trên nó.

        Args:
            window_spec (dict): Tiêu chí tìm cửa sổ.
            element_spec (dict, optional): Tiêu chí tìm element con. Defaults to None.
            action (str, optional): Chuỗi hành động cần thực thi. Defaults to None.
            timeout (int, optional): Thời gian chờ tối đa. Defaults to 10.
            auto_activate (bool, optional): Nếu True, sẽ tự động kích hoạt cửa sổ. 
                                            Nếu False, sẽ chờ người dùng. Defaults to False.
        """
        self.logger.info(f"Bắt đầu tác vụ: action='{action or 'Find Only'}'")
        self.logger.debug(f"  - Window Spec: {window_spec}")
        self.logger.debug(f"  - Element Spec: {element_spec}")
        self.logger.debug(f"  - Auto Activate: {auto_activate}")
        try:
            self.logger.info("-> Bước 1: Bắt đầu tìm kiếm mục tiêu...")
            target_element = self._find_target(window_spec, element_spec, timeout)
            if element_spec is None:
                 self.logger.info(f"-> Bước 1: THÀNH CÔNG. Đã tìm thấy mục tiêu (Cửa sổ): '{target_element.window_text()}'")
            else:
                 self.logger.info(f"-> Bước 1: THÀNH CÔNG. Đã tìm thấy mục tiêu (Element): '{target_element.window_text()}'")

            if action:
                # --- CƠ CHẾ CHỜ HOẶC TỰ ĐỘNG KÍCH HOẠT ---
                command = action.split(':', 1)[0].lower().strip()
                # Nếu action không nằm trong danh sách an toàn, nó cần được kích hoạt
                if command not in self.BACKGROUND_SAFE_ACTIONS:
                    top_window = target_element.top_level_parent()
                    if not top_window.is_active():
                        if auto_activate:
                            self.logger.info(f"Tự động kích hoạt cửa sổ '{top_window.window_text()}'...")
                            top_window.set_focus()
                            time.sleep(0.5) 
                            if not top_window.is_active():
                                raise UIActionError("Nỗ lực tự động kích hoạt cửa sổ thất bại.")
                        else:
                            self.logger.info(f"Hành động '{command}' yêu cầu cửa sổ '{top_window.window_text()}' được kích hoạt.")
                            self.logger.info(f"Đang chờ người dùng kích hoạt cửa sổ (tối đa {timeout} giây)...")
                            
                            wait_start_time = time.time()
                            while time.time() - wait_start_time < timeout:
                                if top_window.is_active():
                                    self.logger.info("Cửa sổ đã được kích hoạt. Tiếp tục thực thi.")
                                    break
                                time.sleep(0.5)
                            else:
                                raise UIActionError(f"Hết thời gian chờ. Cửa sổ không được kích hoạt trong {timeout} giây.")

                self.logger.info(f"-> Bước 2: Bắt đầu thực thi hành động '{action}'...")
                self._execute_action(target_element, action)
                self.logger.info(f"-> Bước 2: THÀNH CÔNG. Đã thực thi hành động '{action}'.")

            self.logger.info(f"--- TÁC VỤ '{action or 'Find Only'}' HOÀN TẤT THÀNH CÔNG ---\n")
            return True
        except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError, UIActionError) as e:
            self.logger.error(f"Lỗi trong quá trình thực thi: {type(e).__name__} - {e}")
            self.logger.error("--- TÁC VỤ THẤT BẠI ---\n")
            return False
        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn trong run_action: {type(e).__name__} - {e}", exc_info=True)
            self.logger.error("--- TÁC VỤ THẤT BẠI ---\n")
            return False

    def get_property(self, window_spec, element_spec, property_name, timeout=10):
        """Tìm một element và lấy giá trị của một thuộc tính cụ thể."""
        self.logger.info(f"Bắt đầu lấy thuộc tính: '{property_name}'")
        try:
            target_element = self._find_target(window_spec, element_spec, timeout)
            value = self._get_property_value(target_element, property_name)
            self.logger.info(f"Lấy thuộc tính '{property_name}' thành công, giá trị = {repr(value)}\n")
            return value
        except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError) as e:
            self.logger.error(f"Lỗi tìm kiếm khi lấy thuộc tính: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Lỗi khi lấy thuộc tính '{property_name}': {type(e).__name__} - {e}", exc_info=True)
            return None

