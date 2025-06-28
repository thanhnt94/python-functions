# Elements/interactive_scanner.py
import logging
import time
import tkinter as tk
from ctypes import wintypes

# --- Thư viện cần thiết ---
try:
    import win32gui
    import comtypes
    import comtypes.client
    import keyboard
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# --- Import từ các module tùy chỉnh ---
from ui_core import get_element_details_comprehensive, get_window_details, format_dict_as_pep8_string

try:
    # noinspection PyUnresolvedReferences
    from comtypes.gen import UIAutomationClient as UIA
except (ImportError, ModuleNotFoundError):
    logging.error("Không tìm thấy thư viện comtypes.gen.UIAutomationClient.")
    UIA = None

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
            canvas.create_rectangle(2, 2, width - 2, height - 2, outline='cyan', width=3)

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

            # SỬ DỤNG HÀM TỪ UI_CORE
            element_details = get_element_details_comprehensive(element)
            
            coords = element_details.get('geo_bounding_rect_tuple')
            if coords:
                self.logger.info(f"Đang vẽ hình chữ nhật tại tọa độ: {coords}")
                self._draw_highlight_rectangle(coords)

            # Tìm cửa sổ cha cấp cao nhất (top-level window)
            top_level_window_handle = 0
            try:
                current = element
                for _ in range(50): # Giới hạn để tránh vòng lặp vô hạn
                    handle = current.CurrentNativeWindowHandle
                    if handle != 0 and win32gui.IsWindow(handle) and win32gui.GetParent(handle) == 0:
                        top_level_window_handle = handle
                        break
                    parent = self.tree_walker.GetParentElement(current)
                    if not parent or parent.CurrentNativeWindowHandle == current.CurrentNativeWindowHandle:
                        # Nếu không có cha hoặc cha trùng handle thì dừng
                        top_level_window_handle = handle if handle !=0 else top_level_window_handle
                        break
                    current = parent
            except comtypes.COMError:
                self.logger.warning("Lỗi COM khi tìm cửa sổ cha, sử dụng handle của element.")
                top_level_window_handle = element.CurrentNativeWindowHandle

            # SỬ DỤNG HÀM TỪ UI_CORE
            window_details = get_window_details(top_level_window_handle) if top_level_window_handle else {}

            # In kết quả
            print_formatted_dict("WINDOW INFO", window_details)
            print_formatted_dict("ELEMENT INFO", element_details)

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
