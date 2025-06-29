# tests/interactive_scanner.py
# Quét giao diện người dùng một cách tương tác với tùy chọn lọc thông tin.

import logging
import time
import tkinter as tk
from ctypes import wintypes

# --- Thư viện cần thiết ---
try:
    import win32gui
    import win32process
    import comtypes
    import comtypes.client
    import keyboard
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# Thêm đường dẫn thư mục cha để có thể import các module khác
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Elements.ui_core import get_element_details_comprehensive, get_window_details, format_dict_as_pep8_string

try:
    from comtypes.gen import UIAutomationClient as UIA
except (ImportError, ModuleNotFoundError):
    logging.error("Không tìm thấy thư viện comtypes.gen.UIAutomationClient.")
    UIA = None

# =================================================================
#                         TÙY CHỈNH
# =================================================================

# Đặt thành True để chỉ xem các thuộc tính quan trọng nhất.
# Đặt thành False để xem tất cả các thuộc tính có giá trị.
FILTER_SCAN_TO_USEFUL_PROPERTIES = False    

# Hằng số chứa các thuộc tính được cho là hữu ích nhất để định danh một element.
# Bạn có thể tự do thêm hoặc bớt các thuộc tính trong danh sách này.
USEFUL_PROPERTIES = {
    'pwa_title',
    'pwa_auto_id',
    'pwa_control_type',
    'pwa_class_name',
    'win32_handle',
    'proc_name',
    'geo_bounding_rect_tuple',
    'state_is_enabled',
}

# =================================================================
#                         HÀM HỖ TRỢ
# =================================================================

def _find_main_window_from_pid(pid):
    """
    Tìm cửa sổ chính của một tiến trình dựa trên PID.
    Ưu tiên cửa sổ có thể nhìn thấy và có tiêu đề.
    """
    def callback(hwnd, hwnds):
        # Kiểm tra xem cửa sổ có phải là một ứng dụng chính hay không
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid:
                hwnds.append(hwnd)
        return True

    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    # Lấy cửa sổ đầu tiên tìm thấy, thường là cửa sổ chính
    return hwnds[0] if hwnds else 0

# =================================================================

def setup_logging():
    """Cấu hình logging để ghi ra cả console và file."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=log_format,
                        filename='interactive_scan.log', filemode='w')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger('').addHandler(console_handler)

def print_formatted_dict(title, data_dict):
    """In một dictionary đã được định dạng ra console."""
    header = f" {title} "
    line_len = 80
    print("\n" + header.center(line_len, "="))
    # Sử dụng hàm format đã được cải tiến từ ui_core
    print(format_dict_as_pep8_string(data_dict))
    print("=" * line_len + "\n")

class InteractiveScanner:
    """Quét giao diện người dùng một cách tương tác."""

    def __init__(self):
        if UIA is None:
            raise RuntimeError("UIAutomationClient không thể khởi tạo.")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.scan_requested = False
        self.logger.info("Khởi tạo InteractiveScanner...")
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise
        self.logger.info("Sẵn sàng quét. Nhấn F8 để quét element dưới con trỏ.")

    @staticmethod
    def _draw_highlight_rectangle(rect):
        """Vẽ một hình chữ nhật tạm thời trên màn hình để làm nổi bật element."""
        try:
            left, top, right, bottom = rect
            width = right - left
            height = bottom - top
            root = tk.Tk()
            root.overrideredirect(True)
            root.wm_attributes("-topmost", True)
            root.wm_attributes("-disabled", True)
            root.wm_attributes("-transparentcolor", "white")
            root.geometry(f'{width}x{height}+{left}+{top}')
            root.configure(bg='white')
            canvas = tk.Canvas(root, bg='white', highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_rectangle(2, 2, width - 2, height - 2, outline='red', width=4)
            root.after(1500, root.destroy)
            root.mainloop()
        except Exception as e:
            logging.getLogger("Highlight").error(f"Lỗi khi vẽ hình chữ nhật: {e}", exc_info=True)

    def _request_scan(self):
        """Ghi nhận yêu cầu quét từ phím nóng."""
        self.logger.info("Yêu cầu quét đã được ghi nhận từ F8.")
        self.scan_requested = True

    def run_scan_at_cursor(self):
        """Thực hiện quét tại vị trí con trỏ chuột."""
        try:
            cursor_pos = win32gui.GetCursorPos()
            self.logger.info(f"Bắt đầu quét tại vị trí: {cursor_pos}")

            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            element = self.uia.ElementFromPoint(point)
            if not element:
                self.logger.warning("Không tìm thấy element nào dưới con trỏ.")
                return

            # Lấy thông tin đầy đủ
            full_element_details = get_element_details_comprehensive(element)
            
            # --- LOGIC THÔNG MINH MỚI ĐỂ TÌM ĐÚNG CỬA SỔ ---
            element_pid = full_element_details.get('proc_pid')
            top_level_window_handle = 0
            
            if element_pid:
                self.logger.debug(f"Đang tìm cửa sổ chính cho PID: {element_pid}")
                main_window_handle = _find_main_window_from_pid(element_pid)
                if main_window_handle:
                    self.logger.info(f"Đã tìm thấy cửa sổ chính (handle: {main_window_handle}) từ PID của element.")
                    top_level_window_handle = main_window_handle
            
            # Nếu không tìm được bằng PID, quay lại phương pháp cũ đáng tin cậy
            if not top_level_window_handle:
                self.logger.warning("Không tìm được cửa sổ chính từ PID, quay lại phương pháp duyệt cây cha.")
                top_level_element = element
                try:
                    parent = self.tree_walker.GetParentElement(top_level_element)
                    while parent:
                        if parent.CurrentNativeWindowHandle == 0:
                            break
                        top_level_element = parent
                        parent = self.tree_walker.GetParentElement(top_level_element)
                    top_level_window_handle = top_level_element.CurrentNativeWindowHandle
                except comtypes.COMError:
                    top_level_window_handle = element.CurrentNativeWindowHandle
            # --- KẾT THÚC LOGIC THÔNG MINH ---
            
            full_window_details = get_window_details(top_level_window_handle) if top_level_window_handle else {}
            
            # Làm nổi bật element
            coords = full_element_details.get('geo_bounding_rect_tuple')
            if coords:
                self._draw_highlight_rectangle(coords)

            # Lọc thông tin nếu cần
            if FILTER_SCAN_TO_USEFUL_PROPERTIES:
                window_info_to_print = {k: v for k, v in full_window_details.items() if k in USEFUL_PROPERTIES}
                element_info_to_print = {k: v for k, v in full_element_details.items() if k in USEFUL_PROPERTIES}
                window_title = "WINDOW INFO (Filtered)"
                element_title = "ELEMENT INFO (Filtered)"
            else:
                window_info_to_print = full_window_details
                element_info_to_print = full_element_details
                window_title = "WINDOW INFO (Full)"
                element_title = "ELEMENT INFO (Full)"

            # In kết quả
            print_formatted_dict(window_title, window_info_to_print)
            print_formatted_dict(element_title, element_info_to_print)

        except Exception as e:
            self.logger.error(f"Đã xảy ra lỗi không mong muốn trong quá trình quét", exc_info=True)

def main():
    setup_logging()
    try:
        scanner = InteractiveScanner()
        keyboard.add_hotkey('f8', scanner._request_scan)
        print("\nCHƯƠNG TRÌNH QUÉT TƯƠNG TÁC")
        print("-" * 40)
        print("- Di chuyển chuột đến element bạn muốn quét.")
        print("- Nhấn phím 'F8' để quét và làm nổi bật element đó.")
        print("- Chỉnh sửa hằng số 'FILTER_SCAN_TO_USEFUL_PROPERTIES' trong file để thay đổi chế độ xem.")
        print("- Nhấn phím 'ESC' để thoát chương trình.")
        while True:
            if keyboard.is_pressed('esc'):
                print("\nPhím ESC được nhấn. Đang thoát...")
                break
            if scanner.scan_requested:
                scanner.run_scan_at_cursor()
                scanner.scan_requested = False
            time.sleep(0.1)
    except Exception as e:
        logging.getLogger('main').critical(f"Không thể khởi động chương trình: {e}", exc_info=True)
    finally:
        keyboard.unhook_all()
        print("Chương trình đã thoát.")

if __name__ == '__main__':
    main()
