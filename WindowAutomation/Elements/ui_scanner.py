# ui_scanner.py
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import comtypes
import comtypes.client
import pandas as pd
import win32con
import win32gui
import win32process

# --- Cài đặt các thư viện cần thiết ---
try:
    import psutil
except ImportError:
    print("Vui lòng cài thư viện psutil: pip install psutil")
    exit()
try:
    from pywinauto import Desktop
except ImportError:
    print("Vui lòng cài thư viện pywinauto: pip install pywinauto")
    exit()

try:
    # noinspection PyUnresolvedReferences
    from comtypes.gen import UIAutomationClient as UIA
except (ImportError, ModuleNotFoundError):
    logging.error("Không tìm thấy thư viện comtypes.gen.UIAutomationClient.")
    UIA = None

# --- Dữ liệu tra cứu cho các thông số ---
PARAMETER_DEFINITIONS = [
    # --- Thông số Cửa sổ (Window) ---
    ("Window", "win32_handle", "Handle (ID duy nhất) của cửa sổ do Windows quản lý."),
    ("Window", "pwa_title", "Tiêu đề hiển thị trên thanh cửa sổ."),
    ("Window", "pwa_class_name", "Tên lớp của cửa sổ (quan trọng để xác định loại cửa sổ)."),
    ("Window", "win32_styles", "Các cờ kiểu dáng của cửa sổ (dạng hexa)."),
    ("Window", "win32_extended_styles", "Các cờ kiểu dáng mở rộng của cửa sổ (dạng hexa)."),
    ("Window", "geo_rectangle_tuple", "Tuple tọa độ (Left, Top, Right, Bottom) của cửa sổ."),
    ("Window", "state_is_visible", "Trạng thái hiển thị (True nếu cửa sổ đang hiển thị)."),
    ("Window", "state_is_enabled", "Trạng thái cho phép tương tác (True nếu cửa sổ được kích hoạt)."),
    ("Window", "state_is_minimized", "Trạng thái thu nhỏ (True nếu cửa sổ đang bị thu nhỏ)."),
    ("Window", "state_is_maximized", "Trạng thái phóng to (True nếu cửa sổ đang được phóng to)."),
    ("Window", "state_is_active", "Trạng thái hoạt động (True nếu là cửa sổ đang được focus)."),
    ("Window", "rel_parent_handle", "Handle của cửa sổ cha (nếu có, 0 là Desktop)."),
    ("Window", "pwa_auto_id", "Automation ID, một ID duy nhất cho tự động hóa."),
    ("Window", "pwa_control_type", "Loại control của cửa sổ (ví dụ: Window, Pane)."),
    ("Window", "pwa_framework_id", "Framework tạo ra cửa sổ (ví dụ: Win32, WinForms, WPF)."),
    ("Window", "proc_pid", "Process ID (ID của tiến trình sở hữu cửa sổ)."),
    ("Window", "proc_thread_id", "Thread ID (ID của luồng sở hữu cửa sổ)."),
    ("Window", "proc_name", "Tên của tiến trình (ví dụ: 'notepad.exe')."),
    ("Window", "proc_path", "Đường dẫn đầy đủ đến file thực thi của tiến trình."),
    ("Window", "proc_cmdline", "Dòng lệnh đã dùng để khởi chạy tiến trình."),
    ("Window", "proc_create_time", "Thời gian tiến trình được tạo."),
    ("Window", "proc_username", "Tên người dùng đã khởi chạy tiến trình."),
    # --- Thông số Element ---
    ("Element", "rel_level", "Cấp độ sâu của element trong cây giao diện (0 là root)."),
    ("Element", "pwa_title", "Tên/văn bản hiển thị của element (thuộc tính quan trọng nhất)."),
    ("Element", "pwa_auto_id", "Automation ID, một ID duy nhất để xác định element trong ứng dụng."),
    ("Element", "pwa_control_type", "Loại control của element (ví dụ: Button, Edit, Tree)."),
    ("Element", "pwa_class_name", "Tên lớp Win32 của element (hữu ích cho các app cũ)."),
    ("Element", "pwa_framework_id", "Framework tạo ra element (ví dụ: UIA, Win32, WPF)."),
    ("Element", "win32_handle", "Handle của element (nếu nó là một cửa sổ riêng)."),
    ("Element", "uia_help_text", "Văn bản trợ giúp ngắn gọn cho element."),
    ("Element", "uia_item_status", "Trạng thái của một item (ví dụ: 'Online', 'Busy')."),
    ("Element", "state_is_enabled", "Trạng thái cho phép tương tác."),
    ("Element", "state_is_focusable", "Trạng thái có thể nhận focus bàn phím."),
    ("Element", "state_is_offscreen", "Trạng thái nằm ngoài màn hình hiển thị."),
    ("Element", "state_is_password", "Trạng thái là ô nhập mật khẩu."),
    ("Element", "state_is_content_element", "Là element chứa nội dung chính, không phải control trang trí."),
    ("Element", "state_is_control_element", "Là element có thể tương tác (ngược với content)."),
    ("Element", "geo_bounding_rect_tuple", "Tuple tọa độ (Left, Top, Right, Bottom) của element."),
    ("Element", "geo_center_point", "Tọa độ điểm trung tâm của element."),
    ("Element", "uia_supported_patterns", "Các Pattern tự động hóa được hỗ trợ (ví dụ: Invoke, Value, Toggle)."),
    ("Element", "uia_value", "Giá trị của element nếu hỗ trợ ValuePattern."),
    ("Element", "uia_toggle_state", "Trạng thái của element nếu hỗ trợ TogglePattern (On, Off, Indeterminate)."),
    ("Element", "uia_expand_state", "Trạng thái nếu hỗ trợ ExpandCollapsePattern (Collapsed, Expanded, LeafNode)."),
    ("Element", "uia_selection_items", "Các item đang được chọn nếu hỗ trợ SelectionPattern."),
    ("Element", "uia_range_value_info", "Thông tin (Min, Max, Value) nếu hỗ trợ RangeValuePattern."),
    ("Element", "uia_grid_cell_info", "Thông tin (Row, Col, RowSpan, ColSpan) nếu hỗ trợ GridItemPattern."),
    ("Element", "uia_table_row_headers", "Tiêu đề của hàng nếu hỗ trợ TableItemPattern."),
    ("Element", "rel_labeled_by", "Tên của element nhãn (label) liên kết với element này."),
    ("Element", "rel_parent_title", "Tên/tiêu đề của element cha."),
    ("Element", "rel_child_count", "Số lượng element con trực tiếp."),
    ("Element", "proc_pid", "Process ID của tiến trình sở hữu element."),
]


def setup_logging(log_filename="full_scan.log"):
    """Cấu hình logging để ghi ra cả console và file."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format,
                        filename=log_filename, filemode='w')

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger('').addHandler(console_handler)


def format_dict_as_pep8_string(spec_dict):
    """
    Định dạng dictionary thành chuỗi PEP8 để dễ copy-paste.
    Hàm này sẽ tự động loại bỏ các key có giá trị rỗng (None, '').
    """
    if not spec_dict:
        return "{}"

    dict_to_format = {
        k: v for k, v in spec_dict.items()
        if not k.startswith('sys_') and v is not None and v != ''
    }

    if not dict_to_format:
        return "{}"

    items_str = [f"    {repr(k)}: {repr(v)}," for k, v in sorted(dict_to_format.items())]
    return f"{{\n" + "\n".join(items_str) + "\n}"


class UIScanner:
    """Lớp đóng gói chức năng quét toàn diện giao diện người dùng."""

    def __init__(self):
        if UIA is None:
            raise RuntimeError("UIAutomationClient không thể khởi tạo.")

        self.logger = logging.getLogger(self.__class__.__name__)
        self.proc_info_cache = {}

        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
            self.desktop = Desktop(backend='uia')
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise

    def _get_process_info(self, pid):
        """Lấy thông tin tiến trình từ cache hoặc psutil."""
        if pid in self.proc_info_cache:
            return self.proc_info_cache[pid]

        if pid > 0 and psutil:
            try:
                p = psutil.Process(pid)
                info = {
                    'proc_name': p.name(),
                    'proc_path': p.exe(),
                    'proc_cmdline': ' '.join(p.cmdline()),
                    'proc_create_time': datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S'),
                    'proc_username': p.username()
                }
                self.proc_info_cache[pid] = info
                return info
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                self.logger.warning(f"Không thể truy cập tiến trình PID={pid}: {e}")
                return {}
        return {}

    def _get_window_details(self, hwnd):
        """Thu thập thông tin chi tiết đầy đủ của một cửa sổ."""
        self.logger.debug(f"Đang lấy thông tin chi tiết cho cửa sổ handle={hwnd}")
        data = {'sys_window_id': 1}
        try:
            data['win32_handle'] = hwnd
            data['pwa_title'] = win32gui.GetWindowText(hwnd)
            data['pwa_class_name'] = win32gui.GetClassName(hwnd)
            data['win32_styles'] = hex(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE))
            data['win32_extended_styles'] = hex(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE))

            rect = win32gui.GetWindowRect(hwnd)
            data['geo_rectangle_tuple'] = (rect[0], rect[1], rect[2], rect[3])

            data['state_is_visible'] = bool(win32gui.IsWindowVisible(hwnd))
            data['state_is_enabled'] = bool(win32gui.IsWindowEnabled(hwnd))

            placement = win32gui.GetWindowPlacement(hwnd)
            data['state_is_minimized'] = (placement[1] == win32con.SW_SHOWMINIMIZED)
            data['state_is_maximized'] = (placement[1] == win32con.SW_SHOWMAXIMIZED)
            data['state_is_active'] = (hwnd == win32gui.GetForegroundWindow())
            data['rel_parent_handle'] = win32gui.GetParent(hwnd)

            try:
                win_element = self.desktop.window(handle=hwnd).element_info
                data['pwa_auto_id'] = win_element.automation_id
                if win_element.control_type:
                    data['pwa_control_type'] = win_element.control_type.capitalize()
                data['pwa_framework_id'] = win_element.framework_id
            except Exception:
                pass

            thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            data['proc_pid'] = pid
            data['proc_thread_id'] = thread_id
            data.update(self._get_process_info(pid))
        except Exception as e:
            self.logger.error(f"Lỗi khi lấy thông tin cửa sổ handle={hwnd}: {e}", exc_info=True)
        return data

    def _get_element_info_comprehensive(self, element):
        """Thu thập thông tin chi tiết nhất có thể của một element."""
        if not element:
            return {}
        data = {}
        try:
            pid = element.CurrentProcessId
            data.update(self._get_process_info(pid))
            data['proc_pid'] = pid
            data['pwa_title'] = element.CurrentName
            data['pwa_auto_id'] = element.CurrentAutomationId

            control_type_str = element.CurrentLocalizedControlType or element.CurrentControlType.name.replace('Control', '')
            if control_type_str:
                data['pwa_control_type'] = control_type_str.capitalize()

            data['pwa_class_name'] = element.CurrentClassName
            data['pwa_framework_id'] = element.CurrentFrameworkId
            data['win32_handle'] = element.CurrentNativeWindowHandle
            data['uia_help_text'] = element.CurrentHelpText
            data['uia_item_status'] = element.CurrentItemStatus
            data['state_is_enabled'] = bool(element.CurrentIsEnabled)
            data['state_is_focusable'] = bool(element.CurrentIsKeyboardFocusable)
            data['state_is_offscreen'] = bool(element.CurrentIsOffscreen)
            data['state_is_password'] = bool(element.CurrentIsPassword)
            data['state_is_content_element'] = bool(element.CurrentIsContentElement)
            data['state_is_control_element'] = bool(element.CurrentIsControlElement)

            rect = element.CurrentBoundingRectangle
            if rect:
                rect_tuple = (rect.left, rect.top, rect.right, rect.bottom)
                data['geo_bounding_rect_tuple'] = rect_tuple
                data['geo_center_point'] = ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)

            patterns, pattern_map = [], {
                'Invoke': UIA.UIA_InvokePatternId, 'Toggle': UIA.UIA_TogglePatternId,
                'Value': UIA.UIA_ValuePatternId, 'Selection': UIA.UIA_SelectionPatternId,
                'ExpandCollapse': UIA.UIA_ExpandCollapsePatternId, 'Grid': UIA.UIA_GridPatternId,
                'Table': UIA.UIA_TablePatternId, 'RangeValue': UIA.UIA_RangeValuePatternId,
                'GridItem': UIA.UIA_GridItemPatternId, 'TableItem': UIA.UIA_TableItemPatternId
            }
            for name, pid_val in pattern_map.items():
                if element.GetCurrentPattern(pid_val):
                    patterns.append(name)
            data['uia_supported_patterns'] = ', '.join(patterns) if patterns else ""

            if 'Value' in data['uia_supported_patterns']:
                data['uia_value'] = element.GetCurrentPattern(UIA.UIA_ValuePatternId).Current.Value
            if 'Toggle' in data['uia_supported_patterns']:
                data['uia_toggle_state'] = element.GetCurrentPattern(UIA.UIA_TogglePatternId).Current.ToggleState.name
            if 'ExpandCollapse' in data['uia_supported_patterns']:
                state = element.GetCurrentPattern(UIA.UIA_ExpandCollapsePatternId).Current.ExpandCollapseState
                data['uia_expand_state'] = state.name

            try:
                data['rel_labeled_by'] = element.CurrentLabeledBy.CurrentName if element.CurrentLabeledBy else ""
            except comtypes.COMError:
                data['rel_labeled_by'] = "Error reading"
            
            parent_element = self.tree_walker.GetParentElement(element)
            data['rel_parent_title'] = parent_element.CurrentName if parent_element else "N/A"
            
            child_array = element.FindAll(UIA.TreeScope_Children, self.uia.CreateTrueCondition())
            data['rel_child_count'] = child_array.Length if child_array else 0

        except comtypes.COMError:
            self.logger.warning(f"Lỗi COM khi truy cập element (Name: {data.get('pwa_title', 'N/A')}).")
        except Exception as e:
            self.logger.error(f"Lỗi không xác định khi lấy thông tin element: {e}", exc_info=True)
        return data

    def _walk_element_tree(self, element, level, all_elements_data):
        """Đệ quy để duyệt cây element và thu thập dữ liệu."""
        if element is None or level > 25:
            return
        try:
            element_data = self._get_element_info_comprehensive(element)
            if element_data:
                element_data['rel_level'] = level
                all_elements_data.append(element_data)

            child = self.tree_walker.GetFirstChildElement(element)
            while child:
                self._walk_element_tree(child, level + 1, all_elements_data)
                child = self.tree_walker.GetNextSiblingElement(child)
        except comtypes.COMError:
            self.logger.warning("Lỗi COM khi duyệt cây, có thể element đã thay đổi.")
        except Exception as e:
            self.logger.error(f"Lỗi khi duyệt cây: {e}", exc_info=True)

    def scan_and_save_to_excel(self, wait_time=3, output_dir=None):
        """Chạy quá trình quét và lưu kết quả ra file Excel."""
        self.logger.info(f"Vui lòng chuyển sang cửa sổ muốn quét. Bắt đầu sau {wait_time} giây...")
        time.sleep(wait_time)
        active_hwnd = win32gui.GetForegroundWindow()
        if not active_hwnd:
            self.logger.error("Không tìm thấy cửa sổ nào đang hoạt động.")
            return None

        window_title_for_file = win32gui.GetWindowText(active_hwnd)
        self.logger.info(f"Bắt đầu quét cửa sổ: '{window_title_for_file}' (Handle: {active_hwnd})")

        window_data = self._get_window_details(active_hwnd)
        all_elements_data = []

        root_element = self.uia.ElementFromHandle(active_hwnd)
        if root_element:
            self._walk_element_tree(root_element, 0, all_elements_data)
        else:
            self.logger.error("Không thể lấy root element từ handle của cửa sổ.")
            return None

        self.logger.info(f"Đã quét xong. Thu thập được thông tin của {len(all_elements_data)} elements.")
        if not all_elements_data and not window_data:
            self.logger.warning("Không thu thập được thông tin nào.")
            return None

        save_folder = Path(output_dir) if output_dir else Path.home() / "Downloads/UiScannerResults"
        save_folder.mkdir(exist_ok=True)
        sanitized_title = re.sub(r'[\\/:*?"<>|]', '_', window_title_for_file)[:100] or "ScannedWindow"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"Scan_{sanitized_title}_{timestamp}.xlsx"
        full_output_path = save_folder / output_filename

        self.logger.info(f"Tổng hợp và lưu kết quả vào: {full_output_path}")
        try:
            window_data['spec_to_copy'] = format_dict_as_pep8_string(window_data)
            for item in all_elements_data:
                item['spec_to_copy'] = format_dict_as_pep8_string(item)

            df_window = pd.DataFrame([window_data])
            df_elements = pd.DataFrame(all_elements_data)
            df_lookup = pd.DataFrame(PARAMETER_DEFINITIONS, columns=['Loại thông số', 'Thông số', 'Ý nghĩa'])

            with pd.ExcelWriter(full_output_path, engine='openpyxl') as writer:
                if not df_window.empty:
                    df_window['geo_rectangle_tuple'] = df_window['geo_rectangle_tuple'].astype(str)
                    cols = sorted([c for c in df_window.columns if c != 'spec_to_copy']) + ['spec_to_copy']
                    df_window[cols].to_excel(writer, sheet_name='Windows Info', index=False)

                if not df_elements.empty:
                    if 'geo_bounding_rect_tuple' in df_elements.columns:
                        df_elements['geo_bounding_rect_tuple'] = df_elements['geo_bounding_rect_tuple'].astype(str)
                    if 'geo_center_point' in df_elements.columns:
                        df_elements['geo_center_point'] = df_elements['geo_center_point'].astype(str)
                    
                    for col in ['rel_level', 'proc_pid', 'win32_handle', 'rel_child_count']:
                        if col in df_elements.columns:
                            df_elements[col] = pd.to_numeric(df_elements[col], errors='coerce').astype('Int64')
                    
                    cols = sorted([c for c in df_elements.columns if c != 'spec_to_copy']) + ['spec_to_copy']
                    df_elements[cols].to_excel(writer, sheet_name='Elements Details', index=False)

                df_lookup.to_excel(writer, sheet_name='Tra cứu thông số', index=False)

            self.logger.info(f"Đã lưu thành công vào: '{full_output_path}'")
            return full_output_path
        except Exception as e:
            self.logger.error(f"Lỗi khi ghi file Excel: {e}", exc_info=True)
            return None


if __name__ == '__main__':
    setup_logging()
    scanner = UIScanner()
    scanner.scan_and_save_to_excel()
