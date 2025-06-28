# ui_controller.py
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
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.application import Application
    from pywinauto import clipboard
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

    def __init__(self, backend='uia'):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.desktop = Desktop(backend=backend)
        self.logger.info(f"UIController đã khởi tạo với backend '{backend}'.")

    def run_action(self, window_spec, element_spec=None, action=None, timeout=10):
        """Tìm một element và thực hiện một hành động trên nó."""
        self.logger.info(f"Bắt đầu tác vụ: action='{action or 'Find Only'}'")
        self.logger.debug(f"  - Window Spec: {window_spec}")
        self.logger.debug(f"  - Element Spec: {element_spec}")
        try:
            self.logger.info("-> Bước 1: Bắt đầu tìm kiếm mục tiêu...")
            target_element = self._find_target(window_spec, element_spec, timeout)
            self.logger.info(f"-> Bước 1: THÀNH CÔNG. Đã tìm thấy mục tiêu: '{target_element.window_text()}'")

            if action:
                self.logger.info(f"-> Bước 2: Bắt đầu thực thi hành động '{action}'...")
                self._execute_action(target_element, action)
                self.logger.info(f"-> Bước 2: THÀNH CÔNG. Đã thực thi hành động '{action}'.")

            self.logger.info(f"--- TÁC VỤ '{action or 'Find Only'}' HOÀN TẤT THÀNH CÔNG ---\n")
            return True
        except (WindowNotFoundError, ElementNotFoundError, AmbiguousElementError) as e:
            self.logger.error(f"Lỗi tìm kiếm: {e}")
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
        """Tách spec thành các tiêu chí pwa gốc và các tiêu chí lọc tinh."""
        pwa_native_spec = {}
        other_filters = {}
        base_map = {'pwa_title': 'title', 'pwa_class_name': 'class_name', 'pwa_control_type': 'control_type'}
        win_only_map = {'pwa_auto_id': 'automation_id', 'win32_handle': 'handle'}

        for key, value in spec.items():
            if isinstance(value, tuple):
                other_filters[key] = value
                continue

            if key in base_map:
                mapped_key = base_map[key]
                final_value = value
                if mapped_key == 'control_type' and isinstance(value, str):
                    final_value = value.capitalize()
                    self.logger.debug(f"Đã chuẩn hóa control_type từ '{value}' thành '{final_value}'.")
                pwa_native_spec[mapped_key] = final_value
            elif search_type == "Window" and key in win_only_map:
                pwa_native_spec[win_only_map[key]] = value
            else:
                other_filters[key] = value
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
                self.logger.debug(f"  -> Bỏ qua: {key}='{actual_value}' không khớp '{criteria}'")
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
            if key.endswith('tuple') and selector in ('topmost', 'bottommost'):
                return _val[1]
            if key.endswith('tuple') and selector in ('leftmost', 'rightmost'):
                return _val[0]
            if key == 'pwa_title' and selector in ('longest', 'shortest'):
                return len(str(_val))
            return _val

        sorted_candidates = sorted(valid_candidates, key=get_sort_key, reverse=use_max)
        
        return [sorted_candidates[0][0]]

    def _get_actual_value(self, element, prefixed_key):
        """Lấy giá trị thực tế của một thuộc tính từ element một cách an toàn."""
        if prefixed_key.startswith('pwa_'):
            prop_map = {
                'pwa_title': 'name', 'pwa_auto_id': 'automation_id',
                'pwa_class_name': 'class_name', 'pwa_control_type': 'control_type',
                'pwa_framework_id': 'framework_id'
            }
            prop = prop_map.get(prefixed_key)
            return getattr(element.element_info, prop, None) if prop else None

        if prefixed_key.startswith('state_'):
            try:
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
            except Exception:
                return None

        if prefixed_key.startswith('win32_'):
            handle = element.handle
            if not handle: return None
            try:
                if prefixed_key == 'win32_handle': return handle
                if prefixed_key == 'win32_styles': return hex(win32gui.GetWindowLong(handle, win32con.GWL_STYLE))
                if prefixed_key == 'win32_extended_styles': return hex(win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE))
            except Exception:
                return None

        if prefixed_key.startswith('geo_'):
            try:
                rect = element.rectangle()
                if prefixed_key in ['geo_rectangle_tuple', 'geo_bounding_rect_tuple']:
                    return rect.left, rect.top, rect.right, rect.bottom
                if prefixed_key == 'geo_center_point':
                    return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
            except Exception:
                return None

        if prefixed_key.startswith('proc_'):
            try:
                p = psutil.Process(element.process_id())
                if prefixed_key == 'proc_pid': return p.pid
                if prefixed_key == 'proc_name': return p.name()
                if prefixed_key == 'proc_create_time': return p.create_time()
                if prefixed_key == 'proc_path': return p.exe()
                if prefixed_key == 'proc_cmdline': return ' '.join(p.cmdline())
                if prefixed_key == 'proc_username': return p.username()
                if prefixed_key == 'proc_thread_id' and element.handle:
                    return win32process.GetWindowThreadProcessId(element.handle)[0]
            except Exception:
                return None

        if prefixed_key.startswith('rel_'):
            try:
                if prefixed_key == 'rel_level':
                    level, current = 0, element
                    for _ in range(50):
                        parent = current.parent()
                        if not parent or parent == current: return level
                        current, level = parent, level + 1
                    return level
                if prefixed_key == 'rel_child_count': return len(element.children())
                if prefixed_key == 'rel_parent_handle' and element.handle: return win32gui.GetParent(element.handle)
                if prefixed_key == 'rel_parent_title': return element.parent().window_text()
                if prefixed_key == 'rel_labeled_by': return element.labeled_by().window_text()
            except Exception:
                return None

        if prefixed_key.startswith('uia_'):
            try:
                if prefixed_key == 'uia_supported_patterns':
                    patterns = [
                        p for p in ['Value', 'Toggle', 'Selection', 'ExpandCollapse', 'Grid',
                                    'Table', 'RangeValue', 'Invoke', 'SelectionItem']
                        if hasattr(element, 'is_pattern_supported') and element.is_pattern_supported(p)
                    ]
                    return ', '.join(patterns)
                if prefixed_key == 'uia_help_text': return element.help_text()
                if prefixed_key == 'uia_item_status': return getattr(element.element_info, 'item_status', '')
                if prefixed_key == 'uia_value' and hasattr(element, 'get_value'): return element.get_value()
                if prefixed_key == 'uia_toggle_state' and hasattr(element, 'get_toggle_state'):
                    return element.get_toggle_state()
            except Exception:
                return None

        self.logger.warning(f"Thuộc tính '{prefixed_key}' không được hỗ trợ hoặc không thể lấy giá trị.")
        return None

    def _check_condition(self, actual_value, criteria):
        """So sánh giá trị thực tế với điều kiện đưa ra."""
        if not isinstance(criteria, tuple):
            return actual_value == criteria
        if len(criteria) != 2:
            self.logger.error(f"Criteria '{criteria}' không hợp lệ.")
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
        """Thực thi một chuỗi hành động trên element."""
        self.logger.debug(f"Thực thi hành động '{action_str}' trên element '{element.window_text()}'")
        parts = action_str.split(':', 1)
        command = parts[0].lower().strip()
        value = parts[1] if len(parts) > 1 else None

        if command == 'click': element.click_input()
        elif command == 'double_click': element.double_click_input()
        elif command == 'right_click': element.right_click_input()
        elif command == 'focus': element.set_focus()
        elif command == 'invoke':
            if hasattr(element, 'invoke'): element.invoke()
            else: raise UIActionError("Hành động 'invoke' thất bại: Element không hỗ trợ InvokePattern.")
        elif command == 'toggle':
            if hasattr(element, 'toggle'): element.toggle()
            else: raise UIActionError("Hành động 'toggle' thất bại: Element không có phương thức toggle.")
        elif command == 'set_text':
            if value is None: raise ValueError("Hành động 'set_text' cần có giá trị.")
            try:
                if hasattr(element, 'set_text'): element.set_text(value)
                else: element.type_keys(value, with_spaces=True, pause=0.05)
            except Exception as e: raise UIActionError(f"Hành động set_text thất bại: {e}")
        elif command in ('type_keys', 'send_keys'):
            if value is None: raise ValueError(f"Hành động '{command}' cần có giá trị.")
            element.type_keys(value, with_spaces=True, pause=0.05)
        elif command == 'paste':
            if value is None: raise ValueError("Hành động 'paste' cần có giá trị.")
            clipboard.SetClipboardText(value)
            element.type_keys('^v', pause=0.1)
        elif command == 'select':
            if value is None: raise ValueError("Hành động 'select' cần có giá trị.")
            try: element.select(value)
            except (ValueError, RuntimeError) as e: raise UIActionError(f"Hành động 'select' thất bại: {e}")
        else: raise ValueError(f"Hành động '{command}' không được hỗ trợ.")

    def _get_property_value(self, element, property_name):
        """Lấy giá trị của một thuộc tính cụ thể từ element."""
        prop = property_name.lower()
        try:
            if prop == 'text': return element.window_text()
            if prop == 'texts': return element.texts()
            if prop == 'value':
                return element.get_value() if hasattr(element, 'get_value') else None
            if prop == 'is_toggled':
                return element.get_toggle_state() == 1 if hasattr(element, 'get_toggle_state') else None
            if prop == 'is_selected':
                return element.is_selected() if hasattr(element, 'is_selected') else None
            if prop == 'is_expanded':
                return element.get_expand_state() == 1 if hasattr(element, 'get_expand_state') else None
            if prop == 'selected_text':
                return element.selected_text() if hasattr(element, 'selected_text') else None
            if prop == 'item_count':
                return element.item_count() if hasattr(element, 'item_count') else None

            self.logger.debug(f"Thuộc tính '{prop}' không phổ biến, thử lấy qua _get_actual_value...")
            return self._get_actual_value(element, prop)
        except Exception as e:
            self.logger.error(f"Lỗi khi lấy thuộc tính '{prop}': {e}", exc_info=True)
            return None

if __name__ == '__main__':
    def demo_notepad():
        """Một ví dụ hoàn chỉnh về cách sử dụng UIController để tự động hóa Notepad."""
        logging.info("===== BẮT ĐẦU DEMO VỚI NOTEPAD =====")
        try:
            Application(backend='uia').start("notepad.exe")
            time.sleep(1.5)
        except Exception as e:
            logging.error(f"Không thể khởi động notepad.exe: {e}")
            return
            
        controller = UIController()
        
        notepad_window_spec = {
            'pwa_class_name': 'Notepad',
            'pwa_title': ('regex', '.*Notepad'),
            'proc_create_time': 'latest'
        }
        
        editor_element_spec = {'pwa_control_type': 'Document'}

        text_to_type = f"Xin chào từ UIController!\nThời gian bây giờ là: {datetime.now()}"
        action_string = f"set_text:{text_to_type}"
        
        success = controller.run_action(
            window_spec=notepad_window_spec,
            element_spec=editor_element_spec,
            action=action_string,
            timeout=5
        )
        
        if not success:
            logging.error("Gõ văn bản vào Notepad thất bại.")
            return

        time.sleep(1)

        retrieved_text = controller.get_property(
            window_spec=notepad_window_spec,
            element_spec=editor_element_spec,
            property_name='texts',
            timeout=5
        )
        
        if retrieved_text:
            text_content = '\n'.join(retrieved_text).strip()
            if text_content == text_to_type.strip():
                logging.info("XÁC THỰC THÀNH CÔNG: Văn bản khớp.")
            else:
                logging.error("XÁC THỰC THẤT BẠI: Văn bản không khớp.")
        else:
            logging.error("Lấy lại văn bản thất bại.")
            
        logging.info("Sẵn sàng đóng Notepad...")
        
        controller.run_action(notepad_window_spec, action="type_keys:^w")
        time.sleep(0.5)

        dont_save_button_spec = {
            "pwa_control_type": "Button",
            "pwa_auto_id": "SecondaryButton"
        }

        controller.run_action(
            window_spec=notepad_window_spec,
            element_spec=dont_save_button_spec,
            action='invoke',
            timeout=3
        )

        logging.info("===== DEMO KẾT THÚC =====")

    demo_notepad()
