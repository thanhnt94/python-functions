# Elements/ui_shared_logic.py
# Module trung tâm chứa các định nghĩa và logic dùng chung để lấy thuộc tính UI.
# Đây là "nguồn chân lý" cho ui_inspector, ui_controller, và spec_tester.

import logging
from datetime import datetime

# --- Thư viện cần thiết ---
try:
    import psutil
    import win32gui
    import win32process
    import win32con
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    print("Gợi ý: pip install psutil pywin32 comtypes")
    exit()

# ======================================================================
#                      BỘ ĐỊNH NGHĨA THUỘC TÍNH
# ======================================================================

PARAMETER_DEFINITIONS = {
    # PWA Properties
    "pwa_title": "Tên/văn bản hiển thị của element (quan trọng nhất).",
    "pwa_auto_id": "Automation ID, một ID duy nhất để xác định element trong ứng dụng.",
    "pwa_control_type": "Loại control của element (ví dụ: Button, Edit, Tree).",
    "pwa_class_name": "Tên lớp Win32 của element (hữu ích cho các app cũ).",
    "pwa_framework_id": "Framework tạo ra element (ví dụ: UIA, Win32, WPF).",
    # WIN32 Properties
    "win32_handle": "Handle (ID duy nhất) của cửa sổ do Windows quản lý.",
    "win32_styles": "Các cờ kiểu dáng của cửa sổ (dạng hexa).",
    "win32_extended_styles": "Các cờ kiểu dáng mở rộng của cửa sổ (dạng hexa).",
    # State Properties
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
    # Geometry Properties
    "geo_rectangle_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của cửa sổ.",
    "geo_bounding_rect_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của element.",
    "geo_center_point": "Tọa độ điểm trung tâm của element.",
    # Process Properties
    "proc_pid": "Process ID (ID của tiến trình sở hữu cửa sổ).",
    "proc_thread_id": "Thread ID (ID của luồng sở hữu cửa sổ).",
    "proc_name": "Tên của tiến trình (ví dụ: 'notepad.exe').",
    "proc_path": "Đường dẫn đầy đủ đến file thực thi của tiến trình.",
    "proc_cmdline": "Dòng lệnh đã dùng để khởi chạy tiến trình.",
    "proc_create_time": "Thời gian tiến trình được tạo (dạng timestamp hoặc chuỗi).",
    "proc_username": "Tên người dùng đã khởi chạy tiến trình.",
    # Relational Properties
    "rel_level": "Cấp độ sâu của element trong cây giao diện (0 là root).",
    "rel_parent_handle": "Handle của cửa sổ cha (nếu có, 0 là Desktop).",
    "rel_parent_title": "Tên/tiêu đề của element cha.",
    "rel_labeled_by": "Tên của element nhãn (label) liên kết với element này.",
    "rel_child_count": "Số lượng element con trực tiếp.",
    # UIA Pattern Properties
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

# Tập hợp tất cả các key được hỗ trợ để lọc
SUPPORTED_FILTER_KEYS = PWA_PROPS | WIN32_PROPS | STATE_PROPS | GEO_PROPS | PROC_PROPS | REL_PROPS | UIA_PROPS

# ======================================================================
#                      LOGIC LẤY THÔNG TIN
# ======================================================================

PROC_INFO_CACHE = {}

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

def get_property_value(pwa_element, key, uia_instance, tree_walker):
    """
    Hàm trung tâm để lấy giá trị của một thuộc tính từ một element.
    Sử dụng logic của ui_inspector để đảm bảo tính nhất quán.

    Args:
        pwa_element: Đối tượng element wrapper của pywinauto.
        key (str): Tên thuộc tính cần lấy (ví dụ: 'pwa_title').
        uia_instance: Đối tượng CUIAutomation để truy cập UIA API.
        tree_walker: Đối tượng TreeWalker để duyệt cây UI.

    Returns:
        Giá trị của thuộc tính hoặc None nếu không lấy được.
    """
    prop = key.lower()
    
    # Lấy đối tượng COM gốc từ pywinauto wrapper
    try:
        com_element = pwa_element.element_info.element
    except Exception:
        logging.debug(f"Không thể lấy com_element từ pwa_element cho key '{prop}'")
        com_element = None

    try:
        # --- PWA Properties (lấy từ pywinauto vì nhanh và đã được chuẩn hóa) ---
        if prop in PWA_PROPS:
            if prop == 'pwa_title': return pwa_element.window_text()
            if prop == 'pwa_class_name': return pwa_element.class_name()
            if prop == 'pwa_auto_id': return pwa_element.automation_id()
            if prop == 'pwa_control_type': return pwa_element.control_type
            if prop == 'pwa_framework_id': return pwa_element.framework_id()

        # --- WIN32 Properties (yêu cầu handle) ---
        handle = pwa_element.handle
        if handle:
            if prop in WIN32_PROPS:
                if prop == 'win32_handle': return handle
                if prop == 'win32_styles': return win32gui.GetWindowLong(handle, win32con.GWL_STYLE)
                if prop == 'win32_extended_styles': return win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)
            if prop == 'proc_thread_id': return win32process.GetWindowThreadProcessId(handle)[0]
            if prop == 'rel_parent_handle': return win32gui.GetParent(handle)

        # --- State Properties (lấy từ pywinauto) ---
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

        # --- Geometry Properties (lấy từ pywinauto) ---
        if prop in GEO_PROPS:
            rect = pwa_element.rectangle()
            if prop == 'geo_rectangle_tuple': return (rect.left, rect.top, rect.right, rect.bottom)
            if prop == 'geo_bounding_rect_tuple': return (rect.left, rect.top, rect.right, rect.bottom)
            if prop == 'geo_center_point': return rect.mid_point()

        # --- Process Properties ---
        if prop in PROC_PROPS:
            pid = pwa_element.process_id()
            if prop == 'proc_pid': return pid
            proc_info = get_process_info(pid)
            return proc_info.get(prop)

        # --- Relational Properties ---
        if prop in REL_PROPS:
            if prop == 'rel_child_count': return len(pwa_element.children())
            if prop == 'rel_parent_title': return pwa_element.parent().window_text() if pwa_element.parent() else ''
            if prop == 'rel_labeled_by': return pwa_element.labeled_by() if hasattr(pwa_element, 'labeled_by') else ''
            if prop == 'rel_level' and com_element and tree_walker:
                level = 0
                current = com_element
                while True:
                    parent = tree_walker.GetParentElement(current)
                    if not parent or parent.CurrentNativeWindowHandle == 0: break
                    current = parent
                    level += 1
                return level

        # --- UIA Properties (yêu cầu COM object) ---
        if prop in UIA_PROPS and com_element:
            if prop == 'uia_value':
                if bool(com_element.IsValuePatternAvailable):
                    return com_element.GetValuePattern().Current.Value
            if prop == 'uia_toggle_state':
                if bool(com_element.IsTogglePatternAvailable):
                    return com_element.GetTogglePattern().Current.ToggleState.name
            if prop == 'uia_expand_state':
                if bool(com_element.IsExpandCollapsePatternAvailable):
                    return com_element.GetExpandCollapsePattern().Current.ExpandCollapseState.name
            # Có thể thêm các pattern khác ở đây
            
        return None
    except (comtypes.COMError, AttributeError, Exception) as e:
        logging.debug(f"Lỗi khi lấy thuộc tính '{prop}': {type(e).__name__} - {e}")
        return None
