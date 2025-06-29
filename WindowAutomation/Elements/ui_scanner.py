# Elements/ui_scanner.py
import logging
import re
import time
from pathlib import Path

# --- Thư viện cần thiết ---
try:
    import pandas as pd
    import win32gui
    import comtypes
    import comtypes.client
    # Thư viện để tìm kiếm và sắp xếp
    from pywinauto import Desktop
    import psutil
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# --- Import từ các module tùy chỉnh ---
from ui_core import get_window_details, get_element_details_comprehensive, format_dict_as_pep8_string
from ui_spec_definitions import get_parameter_definitions_as_dataframe

try:
    from comtypes.gen import UIAutomationClient as UIA
except (ImportError, ModuleNotFoundError):
    UIA = None

def setup_logging(log_filename="full_scan.log"):
    """Cấu hình logging."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format,
                        filename=log_filename, filemode='w')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger('').addHandler(console_handler)

class UIScanner:
    """Lớp đóng gói chức năng quét giao diện người dùng, hoạt động độc lập."""

    def __init__(self):
        if UIA is None: raise RuntimeError("UIAutomationClient không thể khởi tạo.")
        self.logger = logging.getLogger(self.__class__.__name__)
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
            self.desktop = Desktop(backend='uia')
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise

    def _find_window_by_spec(self, spec, timeout=10):
        """
        Hàm nội bộ để tìm cửa sổ bằng bộ lọc, độc lập với UIController.
        """
        self.logger.info(f"Đang tìm cửa sổ với spec: {spec}")
        
        # Tách bộ lọc gốc và bộ lọc tùy chỉnh
        native_spec = {}
        custom_filters = {}
        selectors = {}

        for key, value in spec.items():
            if key == 'pwa_class_name':
                native_spec['class_name'] = value
            elif key == 'pwa_title':
                native_spec['title'] = value
            elif key.startswith('sort_by'):
                selectors[key] = value
            else:
                custom_filters[key] = value

        start_time = time.time()
        while time.time() - start_time < timeout:
            candidates = self.desktop.windows(**native_spec)

            # Áp dụng các bộ lọc tùy chỉnh (ví dụ: proc_pid)
            if 'proc_pid' in custom_filters:
                pid_to_find = custom_filters['proc_pid']
                candidates = [c for c in candidates if c.process_id() == pid_to_find]

            if not candidates:
                time.sleep(0.5)
                continue

            # Áp dụng bộ chọn sắp xếp
            if 'sort_by_creation_time' in selectors:
                try:
                    pids = {c.process_id() for c in candidates}
                    proc_times = {pid: psutil.Process(pid).create_time() for pid in pids}
                    candidates.sort(key=lambda w: proc_times.get(w.process_id(), float('inf')))
                    
                    index = selectors['sort_by_creation_time']
                    final_index = index - 1 if index > 0 else index
                    
                    return candidates[final_index].handle
                except (psutil.Error, IndexError) as e:
                    self.logger.warning(f"Lỗi khi sắp xếp cửa sổ: {e}, thử lại...")
                    time.sleep(0.5)
                    continue
            
            if len(candidates) > 1:
                self.logger.error(f"Tìm thấy {len(candidates)} cửa sổ không thể phân biệt. Vui lòng cung cấp spec chi tiết hơn.")
                return None
            
            if candidates:
                return candidates[0].handle

        self.logger.error("Không tìm thấy cửa sổ nào khớp với spec trong thời gian chờ.")
        return None

    def _walk_element_tree(self, element, level, all_elements_data, max_depth=25):
        if element is None or level > max_depth: return
        try:
            element_data = get_element_details_comprehensive(element)
            if element_data:
                element_data['rel_level'] = level
                all_elements_data.append(element_data)

            child = self.tree_walker.GetFirstChildElement(element)
            while child:
                self._walk_element_tree(child, level + 1, all_elements_data, max_depth)
                try:
                    child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError:
                    break
        except Exception:
            pass

    def scan_and_save_to_excel(self, window_spec=None, wait_time=3, output_dir=None):
        active_hwnd = None
        if window_spec:
            active_hwnd = self._find_window_by_spec(window_spec)
        else:
            self.logger.info(f"Vui lòng chuyển sang cửa sổ muốn quét. Bắt đầu sau {wait_time} giây...")
            time.sleep(wait_time)
            active_hwnd = win32gui.GetForegroundWindow()
        
        if not active_hwnd:
            self.logger.error("Không tìm thấy cửa sổ nào để quét.")
            return None

        window_title_for_file = win32gui.GetWindowText(active_hwnd)
        self.logger.info(f"Bắt đầu quét cửa sổ: '{window_title_for_file}' (Handle: {active_hwnd})")
        window_data = get_window_details(active_hwnd)
        all_elements_data = []

        try:
            root_element = self.uia.ElementFromHandle(active_hwnd)
            if root_element:
                self._walk_element_tree(root_element, 0, all_elements_data)
        except comtypes.COMError:
            self.logger.error(f"Lỗi COM khi lấy root element từ handle {active_hwnd}.")
            return None

        if not all_elements_data and not window_data:
            self.logger.warning("Không thu thập được thông tin nào.")
            return None

        save_folder = Path(output_dir) if output_dir else Path.home() / "UiScannerResults"
        save_folder.mkdir(exist_ok=True)
        sanitized_title = re.sub(r'[\\/:*?"<>|]', '_', window_title_for_file)[:100] or "ScannedWindow"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"Scan_{sanitized_title}_{timestamp}.xlsx"
        full_output_path = save_folder / output_filename

        self.logger.info(f"Tổng hợp và lưu kết quả vào: {full_output_path}")
        try:
            if window_data: window_data['spec_to_copy'] = format_dict_as_pep8_string(window_data)
            for item in all_elements_data: item['spec_to_copy'] = format_dict_as_pep8_string(item)
            
            df_window = pd.DataFrame([window_data]) if window_data else pd.DataFrame()
            df_elements = pd.DataFrame(all_elements_data) if all_elements_data else pd.DataFrame()
            df_lookup = get_parameter_definitions_as_dataframe()

            with pd.ExcelWriter(full_output_path, engine='openpyxl') as writer:
                if not df_window.empty:
                    if 'geo_rectangle_tuple' in df_window.columns: df_window['geo_rectangle_tuple'] = df_window['geo_rectangle_tuple'].astype(str)
                    df_window.to_excel(writer, sheet_name='Windows Info', index=False)
                if not df_elements.empty:
                    cols_to_str = ['geo_bounding_rect_tuple', 'geo_center_point']
                    for col in cols_to_str:
                        if col in df_elements.columns: df_elements[col] = df_elements[col].astype(str)
                    df_elements.to_excel(writer, sheet_name='Elements Details', index=False)
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
