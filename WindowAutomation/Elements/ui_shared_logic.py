# Elements/ui_shared_logic.py
# Version 1.2: Added a public spec formatter function.

import logging
import re
from datetime import datetime

# --- Required Libraries ---
try:
    import psutil
    import win32gui
    import win32process
    import win32con
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
    from pywinauto import uia_defines
    from pywinauto.findwindows import ElementNotFoundError
except ImportError as e:
    print(f"Error importing libraries: {e}")
    print("Suggestion: pip install psutil pywin32 comtypes pywinauto")
    exit()

# Khởi tạo logger cho module này
logger = logging.getLogger(__name__)

# ======================================================================
#                      BỘ ĐỊNH NGHĨA TRUNG TÂM
# ======================================================================

# --- Định nghĩa thuộc tính ---
PARAMETER_DEFINITIONS = {
    "pwa_title": "Tên/văn bản hiển thị của element (quan trọng nhất).",
    "pwa_auto_id": "Automation ID, một ID duy nhất để xác định element trong ứng dụng.",
    "pwa_control_type": "Loại control của element (ví dụ: Button, Edit, Tree).",
    "pwa_class_name": "Tên lớp Win32 của element (hữu ích cho các app cũ).",
    "pwa_framework_id": "Framework tạo ra element (ví dụ: UIA, Win32, WPF).",
    "win32_handle": "Handle (ID duy nhất) của cửa sổ do Windows quản lý.",
    "win32_styles": "Các cờ kiểu dáng của cửa sổ (dạng hexa).",
    "win32_extended_styles": "Các cờ kiểu dáng mở rộng của cửa sổ (dạng hexa).",
    "state_is_visible": "Trạng thái hiển thị (True nếu đang hiển thị).",
    "state_is_enabled": "Trạng thái cho phép tương tác (True nếu được kích hoạt).",
    "state_is_active": "Trạng thái hoạt động (True nếu là cửa sổ/element đang được focus).",
    "state_is_minimized": "Trạng thái thu nhỏ (True nếu cửa sổ đang bị thu nhỏ).",
    "state_is_maximized": "Trạng thái phóng to (True nếu cửa sổ đang được phóng to).",
    "state_is_focusable": "Trạng thái có thể nhận focus bàn phím.",
    "state_is_password": "Trạng thái là ô nhập mật khẩu.",
    "state_is_offscreen": "Trạng thái nằm ngoài màn hình hiển thị.",
    "state_is_content_element": "Là element chứa nội dung chính, không phải control trang trí.",
    "state_is_control_element": "Là element có thể tương tác (ngược với content).",
    "geo_bounding_rect_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của element.",
    "geo_center_point": "Tọa độ điểm trung tâm của element.",
    "proc_pid": "Process ID (ID của tiến trình sở hữu cửa sổ).",
    "proc_thread_id": "Thread ID (ID của luồng sở hữu cửa sổ).",
    "proc_name": "Tên của tiến trình (ví dụ: 'notepad.exe').",
    "proc_path": "Đường dẫn đầy đủ đến file thực thi của tiến trình.",
    "proc_cmdline": "Dòng lệnh đã dùng để khởi chạy tiến trình.",
    "proc_create_time": "Thời gian tiến trình được tạo (dạng timestamp hoặc chuỗi).",
    "proc_username": "Tên người dùng đã khởi chạy tiến trình.",
    "rel_level": "Cấp độ sâu của element trong cây giao diện (0 là root).",
    "rel_parent_handle": "Handle của cửa sổ cha (nếu có, 0 là Desktop).",
    "rel_parent_title": "Tên/tiêu đề của element cha.",
    "rel_labeled_by": "Tên của element nhãn (label) liên kết với element này.",
    "rel_child_count": "Số lượng element con trực tiếp.",
    "uia_value": "Giá trị của element nếu hỗ trợ ValuePattern.",
    "uia_toggle_state": "Trạng thái của element nếu hỗ trợ TogglePattern (On, Off, Indeterminate).",
    "uia_expand_state": "Trạng thái nếu hỗ trợ ExpandCollapsePattern (Collapsed, Expanded, LeafNode).",
    "uia_selection_items": "Các item đang được chọn nếu hỗ trợ SelectionPattern.",
    "uia_range_value_info": "Thông tin (Min, Max, Value) nếu hỗ trợ RangeValuePattern.",
    "uia_grid_cell_info": "Thông tin (Row, Col, RowSpan, ColSpan) nếu hỗ trợ GridItemPattern.",
    "uia_table_row_headers": "Tiêu đề của hàng nếu hỗ trợ TableItemPattern.",
}

# --- Phân loại các bộ thuộc tính ---
PWA_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('pwa_')}
WIN32_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('win32_')}
STATE_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('state_')}
GEO_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('geo_')}
PROC_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('proc_')}
REL_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('rel_')}
UIA_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('uia_')}

# --- Định nghĩa các bộ chọn (Selectors) và toán tử (Operators) ---
SORTING_KEYS = {'sort_by_creation_time', 'sort_by_title_length', 'sort_by_child_count',
                'sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height', 'z_order_index'}
STRING_OPERATORS = {'equals', 'iequals', 'contains', 'icontains', 'in', 'regex',
                    'not_equals', 'not_iequals', 'not_contains', 'not_icontains'}
NUMERIC_OPERATORS = {'>', '>=', '<', '<='}
VALID_OPERATORS = STRING_OPERATORS.union(NUMERIC_OPERATORS)

# Tập hợp tất cả các key được hỗ trợ để lọc
SUPPORTED_FILTER_KEYS = PWA_PROPS | WIN32_PROPS | STATE_PROPS | GEO_PROPS | PROC_PROPS | REL_PROPS | UIA_PROPS

# Tạo một bảng tra cứu ngược từ ID sang Tên cho ControlType để tiện sử dụng
_CONTROL_TYPE_ID_TO_NAME = {v: k for k, v in uia_defines.IUIA().known_control_types.items()}

# Cache cho thông tin tiến trình để tăng tốc độ
PROC_INFO_CACHE = {}

# ======================================================================
#                      PUBLIC UTILITY FUNCTIONS
# ======================================================================

def format_spec_to_string(spec_dict, spec_name="spec"):
    """
    *** NEW: Public function to format a spec dictionary into a copyable string. ***
    """
    if not spec_dict:
        return f"{spec_name} = {{}}"
    
    dict_to_format = {k: v for k, v in spec_dict.items() if not k.startswith('sys_') and (v or v is False or v == 0)}
    if not dict_to_format:
        return f"{spec_name} = {{}}"
        
    items_str = [f"    '{k}': {repr(v)}," for k, v in sorted(dict_to_format.items())]
    content = "\n".join(items_str)
    return f"{spec_name} = {{\n{content}\n}}"

# ======================================================================
#                      CÁC HÀM LẤY THÔNG TIN CƠ BẢN
# ======================================================================

def get_process_info(pid):
    """Lấy thông tin tiến trình và cache lại để tăng tốc độ."""
    if pid in PROC_INFO_CACHE:
        return PROC_INFO_CACHE[pid]
    if pid > 0:
        try:
            p = psutil.Process(pid)
            info = {
                'proc_name': p.name(),
                'proc_path': p.exe(),
                'proc_cmdline': ' '.join(p.cmdline()),
                'proc_create_time': datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S'),
                'proc_username': p.username()
            }
            PROC_INFO_CACHE[pid] = info
            return info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {}

def get_property_value(pwa_element, key, uia_instance=None, tree_walker=None):
    """
    Hàm trung tâm để lấy giá trị của một thuộc tính từ một element của pywinauto.
    """
    prop = key.lower()
    
    if hasattr(pwa_element, 'element_info'):
        com_element = getattr(pwa_element.element_info, 'element', None)
    else:
        com_element = getattr(pwa_element, 'element', pwa_element)

    try:
        # --- PWA Properties ---
        if prop in PWA_PROPS:
            if prop == 'pwa_title': return pwa_element.window_text()
            if prop == 'pwa_class_name': return pwa_element.class_name()
            if prop == 'pwa_auto_id': return pwa_element.automation_id()
            if prop == 'pwa_control_type': return pwa_element.control_type()
            if prop == 'pwa_framework_id': return pwa_element.framework_id()

        # --- WIN32 Properties ---
        handle = pwa_element.handle
        if handle:
            if prop in WIN32_PROPS:
                if prop == 'win32_handle': return handle
                if prop == 'win32_styles': return win32gui.GetWindowLong(handle, win32con.GWL_STYLE)
                if prop == 'win32_extended_styles': return win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)
            if prop == 'proc_thread_id': return win32process.GetWindowThreadProcessId(handle)[0]
            if prop == 'rel_parent_handle': return win32gui.GetParent(handle)

        # --- State Properties ---
        if prop in STATE_PROPS:
            if prop == 'state_is_visible': return pwa_element.is_visible()
            if prop == 'state_is_enabled': return pwa_element.is_enabled()
            if prop == 'state_is_active': return pwa_element.is_active()
            if prop == 'state_is_minimized': return pwa_element.is_minimized()
            if prop == 'state_is_maximized': return pwa_element.is_maximized()
            if prop == 'state_is_focusable': return pwa_element.is_focusable()
            if prop == 'state_is_password': return pwa_element.is_password()
            if prop == 'state_is_offscreen': return pwa_element.is_offscreen()
            if prop == 'state_is_content_element': return pwa_element.is_content_element()
            if prop == 'state_is_control_element': return pwa_element.is_control_element()

        # --- Geometry Properties ---
        if prop in GEO_PROPS:
            try:
                rect = pwa_element.rectangle()
                if prop == 'geo_bounding_rect_tuple': return (rect.left, rect.top, rect.right, rect.bottom)
                if prop == 'geo_center_point':
                    mid_point = rect.mid_point()
                    return (mid_point.x, mid_point.y)
            except Exception:
                logger.debug(f"pwa_element.rectangle() thất bại. Thử truy cập COM trực tiếp.")
                if com_element:
                    try:
                        com_rect = com_element.CurrentBoundingRectangle
                        if prop == 'geo_bounding_rect_tuple':
                            return (com_rect.left, com_rect.top, com_rect.right, com_rect.bottom)
                        if prop == 'geo_center_point':
                            return ((com_rect.left + com_rect.right) // 2, (com_rect.top + com_rect.bottom) // 2)
                    except (comtypes.COMError, AttributeError):
                        logger.debug(f"Truy cập COM trực tiếp cho BoundingRectangle cũng thất bại.")
                        return None
        
        # --- Process Properties ---
        if prop in PROC_PROPS:
            pid = pwa_element.process_id()
            if prop == 'proc_pid': return pid
            proc_info = get_process_info(pid)
            return proc_info.get(prop)

        # --- Relational Properties ---
        if prop in REL_PROPS:
            if prop == 'rel_child_count': return len(pwa_element.children())
            parent = pwa_element.parent()
            if prop == 'rel_parent_title': return parent.window_text() if parent else ''
            if prop == 'rel_labeled_by': return pwa_element.labeled_by() if hasattr(pwa_element, 'labeled_by') else ''
            
            if prop == 'rel_level' and com_element and tree_walker and uia_instance:
                level = 0
                root = uia_instance.GetRootElement()
                if comtypes.client.GetBestInterface(com_element) == comtypes.client.GetBestInterface(root):
                    return 0

                current = com_element
                while True:
                    parent = tree_walker.GetParentElement(current)
                    if not parent: break
                    level += 1
                    if comtypes.client.GetBestInterface(parent) == comtypes.client.GetBestInterface(root):
                        break
                    current = parent
                    if level > 50:
                        logger.warning("Đã đạt đến độ sâu tối đa (50) khi tính rel_level.")
                        break
                return level

        # --- UIA Properties ---
        if prop in UIA_PROPS and com_element and uia_instance:
            if prop == 'uia_value':
                pattern = com_element.GetCurrentPattern(UIA.UIA_ValuePatternId)
                if pattern: return pattern.QueryInterface(UIA.IUIAutomationValuePattern).CurrentValue
            if prop == 'uia_toggle_state':
                pattern = com_element.GetCurrentPattern(UIA.UIA_TogglePatternId)
                if pattern: return pattern.QueryInterface(UIA.IUIAutomationTogglePattern).CurrentToggleState.name
            if prop == 'uia_expand_state':
                pattern = com_element.GetCurrentPattern(UIA.UIA_ExpandCollapsePatternId)
                if pattern: return pattern.QueryInterface(UIA.IUIAutomationExpandCollapsePattern).CurrentExpandCollapseState.name
            
        return None
    except (comtypes.COMError, AttributeError, Exception) as e:
        logger.debug(f"Lỗi khi lấy thuộc tính '{prop}': {type(e).__name__} - {e}")
        return None

def get_all_properties(pwa_element, uia_instance=None, tree_walker=None):
    all_props = {}
    for key in SUPPORTED_FILTER_KEYS:
        value = get_property_value(pwa_element, key, uia_instance, tree_walker)
        if value or value is False or value == 0:
            all_props[key] = value
    if 'pwa_title' not in all_props:
        try: all_props['pwa_title'] = pwa_element.window_text()
        except Exception: pass
    if 'pwa_class_name' not in all_props:
        try: all_props['pwa_class_name'] = pwa_element.class_name()
        except Exception: pass
    return all_props

def get_top_level_window(pwa_element):
    try:
        return pwa_element.top_level_parent()
    except (AttributeError, RuntimeError):
        return None

# ======================================================================
#                      LỚP TÌM KIẾM ELEMENT TRUNG TÂM
# ======================================================================

class ElementFinder:
    def __init__(self, uia_instance, tree_walker, log_callback=None):
        def dummy_log(level, message): pass
        self.log = log_callback if callable(log_callback) else dummy_log
        self.uia = uia_instance
        self.tree_walker = tree_walker

    def find(self, search_pool, spec):
        self.log('DEBUG', f"Bắt đầu tìm kiếm với spec: {spec}")
        try:
            candidates = search_pool()
        except Exception as e:
            self.log('ERROR', f"Lỗi khi lấy danh sách ứng viên ban đầu: {e}")
            return []
        self.log('DEBUG', f"Tìm thấy {len(candidates)} ứng viên ban đầu.")
        if not candidates: return []
        filter_spec, selector_spec = self._split_spec(spec)
        if filter_spec:
            self.log('INFO', f"Áp dụng bộ lọc (filters) cho {len(candidates)} ứng viên...")
            candidates = self._apply_filters(candidates, filter_spec)
            if not candidates:
                self.log('INFO', "Không còn ứng viên nào sau khi lọc.")
                return []
            self.log('SUCCESS', f"Còn lại {len(candidates)} ứng viên sau khi lọc.")
        if selector_spec:
            self.log('INFO', f"Áp dụng bộ chọn (selectors) cho {len(candidates)} ứng viên...")
            candidates = self._apply_selectors(candidates, selector_spec)
            if not candidates:
                self.log('INFO', "Không còn ứng viên nào sau khi chọn.")
                return []
        return candidates

    def _split_spec(self, spec):
        filter_spec = {k: v for k, v in spec.items() if k not in SORTING_KEYS}
        selector_spec = {k: v for k, v in spec.items() if k in SORTING_KEYS}
        return filter_spec, selector_spec

    def _apply_filters(self, elements, spec):
        if not spec: return elements
        current_elements = list(elements)
        for key, criteria in spec.items():
            self.log('FILTER', f"Lọc theo: {{'{key}': {repr(criteria)}}}")
            initial_count = len(current_elements)
            kept_elements = []
            for elem in current_elements:
                actual_value = get_property_value(elem, key, self.uia, self.tree_walker)
                matches = self._check_condition(actual_value, criteria)
                log_msg_parts = []
                if matches:
                    log_msg_parts.append(("[GIỮ LẠI] ", 'KEEP'))
                    log_msg_parts.append((f"'{elem.window_text()}' vì '{key}' có giá trị '{actual_value}' khớp.", 'DEBUG'))
                else:
                    log_msg_parts.append(("[LOẠI BỎ] ", 'DISCARD'))
                    log_msg_parts.append((f"'{elem.window_text()}' vì '{key}' có giá trị '{actual_value}' không khớp.", 'DEBUG'))
                self.log('DEBUG', log_msg_parts)
                if matches: kept_elements.append(elem)
            self.log('INFO', f"  -> Kết quả: Giữ lại {len(kept_elements)}/{initial_count} ứng viên.")
            if not kept_elements: return []
            current_elements = kept_elements
        return current_elements

    def _check_condition(self, actual_value, criteria):
        is_operator_syntax = (isinstance(criteria, tuple) and 
                              len(criteria) == 2 and 
                              str(criteria[0]).lower() in VALID_OPERATORS)
        if is_operator_syntax:
            operator, target_value = criteria
            op = str(operator).lower()
            if actual_value is None: return False
            if op in STRING_OPERATORS:
                str_actual, str_target = str(actual_value), str(target_value)
                if op == 'equals': return str_actual == str_target
                if op == 'iequals': return str_actual.lower() == str_target.lower()
                if op == 'contains': return str_target in str_actual
                if op == 'icontains': return str_target.lower() in str_actual.lower()
                if op == 'in': return str_actual in target_value
                if op == 'regex': return re.search(str_target, str_actual) is not None
                if op == 'not_equals': return str_actual != str_target
                if op == 'not_iequals': return str_actual.lower() != str_target.lower()
                if op == 'not_contains': return str_target not in str_actual
                if op == 'not_icontains': return str_target.lower() not in str_actual.lower()
            if op in NUMERIC_OPERATORS:
                try:
                    num_actual, num_target = float(actual_value), float(target_value)
                    if op == '>': return num_actual > num_target
                    if op == '>=': return num_actual >= num_target
                    if op == '<': return num_actual < num_target
                    if op == '<=': return num_actual <= num_target
                except (ValueError, TypeError): return False
        else:
            return actual_value == criteria
        return False

    def _apply_selectors(self, candidates, selectors):
        if not candidates: return []
        sorted_candidates = list(candidates)
        for key in [k for k in selectors if k != 'z_order_index']:
            index = selectors[key]
            self.log('FILTER', f"Sắp xếp theo: '{key}' (Thứ tự: {'Giảm dần' if index < 0 else 'Tăng dần'})")
            sort_key_func = self._get_sort_key_function(key)
            if sort_key_func:
                sorted_candidates.sort(key=lambda e: (sort_key_func(e) is None, sort_key_func(e)), reverse=(index < 0))
        final_index = 0
        if 'z_order_index' in selectors:
            final_index = selectors['z_order_index']
        elif selectors:
            last_selector_key = list(selectors.keys())[-1]
            final_index = selectors[last_selector_key]
            final_index = final_index - 1 if final_index > 0 else final_index
        self.log('FILTER', f"Chọn phần tử tại index: {final_index}")
        try:
            selected = sorted_candidates[final_index]
            self.log('SUCCESS', f"Đã chọn được ứng viên: '{selected.window_text()}'")
            return [selected]
        except IndexError:
            self.log('ERROR', f"Lựa chọn index={final_index} nằm ngoài phạm vi ({len(sorted_candidates)} ứng viên).")
            return []

    def _get_sort_key_function(self, key):
        if key == 'sort_by_creation_time':
            return lambda e: get_property_value(e, 'proc_create_time') or datetime.min.strftime('%Y-%m-%d %H:%M:%S')
        if key == 'sort_by_title_length':
            return lambda e: len(get_property_value(e, 'pwa_title') or '')
        if key == 'sort_by_child_count':
            return lambda e: get_property_value(e, 'rel_child_count') or 0
        if key in ['sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height']:
            def get_rect_prop(elem, prop_key):
                rect = get_property_value(elem, 'geo_bounding_rect_tuple')
                if not rect: return 0
                if prop_key == 'sort_by_y_pos': return rect[1]
                if prop_key == 'sort_by_x_pos': return rect[0]
                if prop_key == 'sort_by_width': return rect[2] - rect[0]
                if prop_key == 'sort_by_height': return rect[3] - rect[1]
            return lambda e: get_rect_prop(e, key)
        return None
