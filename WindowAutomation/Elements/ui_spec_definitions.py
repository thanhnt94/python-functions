# Elements/ui_spec_definitions.py
# Nguồn chân lý duy nhất cho tất cả các thuộc tính có thể quét và lọc.

PARAMETER_DEFINITIONS = {
    # --- Tiền tố 'pwa_': Thuộc tính gốc của Pywinauto ---
    "pwa_title": "Tên/văn bản hiển thị của element (quan trọng nhất).",
    "pwa_auto_id": "Automation ID, một ID duy nhất để xác định element trong ứng dụng.",
    "pwa_control_type": "Loại control của element (ví dụ: Button, Edit, Tree).",
    "pwa_class_name": "Tên lớp Win32 của element (hữu ích cho các app cũ).",
    "pwa_framework_id": "Framework tạo ra element (ví dụ: UIA, Win32, WPF).",

    # --- Tiền tố 'win32_': Thuộc tính từ Win32 API ---
    "win32_handle": "Handle (ID duy nhất) của cửa sổ do Windows quản lý.",
    "win32_styles": "Các cờ kiểu dáng của cửa sổ (dạng hexa).",
    "win32_extended_styles": "Các cờ kiểu dáng mở rộng của cửa sổ (dạng hexa).",

    # --- Tiền tố 'state_': Các trạng thái của element ---
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

    # --- Tiền tố 'geo_': Thuộc tính về hình học và vị trí ---
    "geo_rectangle_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của cửa sổ.",
    "geo_bounding_rect_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của element.",
    "geo_center_point": "Tọa độ điểm trung tâm của element.",

    # --- Tiền tố 'proc_': Thuộc tính về tiến trình (Process) ---
    "proc_pid": "Process ID (ID của tiến trình sở hữu cửa sổ).",
    "proc_thread_id": "Thread ID (ID của luồng sở hữu cửa sổ).",
    "proc_name": "Tên của tiến trình (ví dụ: 'notepad.exe').",
    "proc_path": "Đường dẫn đầy đủ đến file thực thi của tiến trình.",
    "proc_cmdline": "Dòng lệnh đã dùng để khởi chạy tiến trình.",
    "proc_create_time": "Thời gian tiến trình được tạo (dạng timestamp hoặc chuỗi).",
    "proc_username": "Tên người dùng đã khởi chạy tiến trình.",

    # --- Tiền tố 'rel_': Thuộc tính về mối quan hệ phân cấp ---
    "rel_level": "Cấp độ sâu của element trong cây giao diện (0 là root).",
    "rel_parent_handle": "Handle của cửa sổ cha (nếu có, 0 là Desktop).",
    "rel_parent_title": "Tên/tiêu đề của element cha.",
    "rel_labeled_by": "Tên của element nhãn (label) liên kết với element này.",
    "rel_child_count": "Số lượng element con trực tiếp.",

    # --- Tiền tố 'uia_': Thuộc tính dành riêng cho UI Automation ---
    "uia_help_text": "Văn bản trợ giúp ngắn gọn cho element.",
    "uia_item_status": "Trạng thái của một item (ví dụ: 'Online', 'Busy').",
    "uia_supported_patterns": "Các Pattern tự động hóa được hỗ trợ (ví dụ: Invoke, Value, Toggle).",
    "uia_value": "Giá trị của element nếu hỗ trợ ValuePattern.",
    "uia_toggle_state": "Trạng thái của element nếu hỗ trợ TogglePattern (On, Off, Indeterminate).",
    "uia_expand_state": "Trạng thái nếu hỗ trợ ExpandCollapsePattern (Collapsed, Expanded, LeafNode).",
    "uia_selection_items": "Các item đang được chọn nếu hỗ trợ SelectionPattern.",
    "uia_range_value_info": "Thông tin (Min, Max, Value) nếu hỗ trợ RangeValuePattern.",
    "uia_grid_cell_info": "Thông tin (Row, Col, RowSpan, ColSpan) nếu hỗ trợ GridItemPattern.",
    "uia_table_row_headers": "Tiêu đề của hàng nếu hỗ trợ TableItemPattern.",
}


def get_all_supported_keys():
    """Trả về một set chứa tất cả các key thuộc tính được hỗ trợ."""
    return set(PARAMETER_DEFINITIONS.keys())

def get_parameter_definitions_as_dataframe():
    """Trả về một Pandas DataFrame từ định nghĩa các tham số để dễ dàng xuất ra Excel."""
    import pandas as pd
    items = []
    for key, description in PARAMETER_DEFINITIONS.items():
        category = key.split('_')[0].upper()
        items.append((category, key, description))
    return pd.DataFrame(items, columns=['Loại thông số', 'Thông số', 'Ý nghĩa'])
