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
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# --- Import từ các module tùy chỉnh ---
from ui_core import get_window_details, get_element_details_comprehensive, format_dict_as_pep8_string
from ui_spec_definitions import get_parameter_definitions_as_dataframe

try:
    # noinspection PyUnresolvedReferences
    from comtypes.gen import UIAutomationClient as UIA
except (ImportError, ModuleNotFoundError):
    logging.error("Không tìm thấy thư viện comtypes.gen.UIAutomationClient.")
    UIA = None

def setup_logging(log_filename="full_scan.log"):
    """Cấu hình logging để ghi ra cả console và file."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format,
                        filename=log_filename, filemode='w')

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger('').addHandler(console_handler)

class UIScanner:
    """Lớp đóng gói chức năng quét toàn diện giao diện người dùng."""

    def __init__(self):
        if UIA is None:
            raise RuntimeError("UIAutomationClient không thể khởi tạo.")

        self.logger = logging.getLogger(self.__class__.__name__)
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise

    def _walk_element_tree(self, element, level, all_elements_data, max_depth=25):
        """Đệ quy để duyệt cây element và thu thập dữ liệu."""
        if element is None or level > max_depth:
            return
        try:
            # SỬ DỤNG HÀM TỪ CORE
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
                    # Lỗi này có thể xảy ra nếu cây UI thay đổi trong lúc duyệt
                    self.logger.warning("Lỗi COM khi lấy sibling, cây UI có thể đã thay đổi. Dừng duyệt nhánh này.")
                    break
        except comtypes.COMError:
            self.logger.warning("Lỗi COM khi duyệt cây, có thể element đã thay đổi.")
        except Exception as e:
            self.logger.error(f"Lỗi khi duyệt cây ở level {level}: {e}", exc_info=True)

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

        # SỬ DỤNG HÀM TỪ CORE
        window_data = get_window_details(active_hwnd)
        all_elements_data = []

        try:
            root_element = self.uia.ElementFromHandle(active_hwnd)
            if root_element:
                self._walk_element_tree(root_element, 0, all_elements_data)
            else:
                self.logger.error("Không thể lấy root element từ handle của cửa sổ.")
        except comtypes.COMError:
            self.logger.error(f"Lỗi COM khi lấy root element từ handle {active_hwnd}. Có thể cửa sổ không hỗ trợ UIA.", exc_info=True)
            return None

        self.logger.info(f"Đã quét xong. Thu thập được thông tin của {len(all_elements_data)} elements.")
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
            # Thêm cột spec để dễ copy
            window_data['spec_to_copy'] = format_dict_as_pep8_string(window_data)
            for item in all_elements_data:
                item['spec_to_copy'] = format_dict_as_pep8_string(item)

            df_window = pd.DataFrame([window_data]) if window_data else pd.DataFrame()
            df_elements = pd.DataFrame(all_elements_data) if all_elements_data else pd.DataFrame()
            # SỬ DỤNG HÀM TỪ DEFINITIONS
            df_lookup = get_parameter_definitions_as_dataframe()

            with pd.ExcelWriter(full_output_path, engine='openpyxl') as writer:
                if not df_window.empty:
                    df_window['geo_rectangle_tuple'] = df_window['geo_rectangle_tuple'].astype(str)
                    cols = sorted([c for c in df_window.columns if c != 'spec_to_copy']) + ['spec_to_copy']
                    df_window[cols].to_excel(writer, sheet_name='Windows Info', index=False)

                if not df_elements.empty:
                    for col in ['geo_bounding_rect_tuple', 'geo_center_point']:
                        if col in df_elements.columns:
                            df_elements[col] = df_elements[col].astype(str)
                    
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
