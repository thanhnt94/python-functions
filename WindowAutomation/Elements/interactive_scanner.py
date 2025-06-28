# interactive_scanner.py
import logging
import time
import tkinter as tk

import comtypes
import comtypes.client
import win32con
import win32gui
import win32process
from ctypes import wintypes

# --- Cài đặt các thư viện cần thiết ---
try:
    import keyboard
except ImportError:
    print("Vui lòng cài thư viện keyboard: pip install keyboard")
    exit()
try:
    from pywinauto import Desktop
except ImportError:
    print("Vui lòng cài thư viện pywinauto: pip install pywinauto")
    exit()
try:
    import psutil
except ImportError:
    print("Vui lòng cài thư viện psutil: pip install psutil")
    exit()
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


def format_and_print_dict(title, data_dict):
    """Định dạng và in một dictionary theo kiểu PEP 8."""
    header = f" {title} "
    line_len = 80
    print("\n" + header.center(line_len, "="))

    if not data_dict:
        print("{}")
    else:
        print("{")
        for key, value in sorted(data_dict.items()):
            print(f"    {repr(key)}: {repr(value)},")
        print("}")
    print("=" * line_len + "\n")


class InteractiveScanner:
    """Quét giao diện người dùng một cách tương tác."""

    def __init__(self):
        if UIA is None:
            raise RuntimeError("UIAutomationClient không thể khởi tạo.")

        self.logger = logging.getLogger(self.__class__.__name__)
        self.proc_info_cache = {}
        self.scan_requested = False

        self.logger.info("Khởi tạo InteractiveScanner...")
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
            self.desktop = Desktop(backend='uia')
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise
        self.logger.info("Sẵn sàng quét. Nhấn F8 để quét element dưới con trỏ.")

    @staticmethod
    def _draw_highlight_rectangle(rect):
        """Vẽ một hình chữ nhật tạm thời trên màn hình."""
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
            logging.getLogger("Highlight").error(f"Lỗi khi vẽ hình chữ nhật: {e}")

    def _get_process_info(self, pid):
        if pid in self.proc_info_cache:
            return self.proc_info_cache[pid]
        if pid > 0 and psutil:
            try:
                p = psutil.Process(pid)
                info = {
                    'proc_name': p.name(),
                    'proc_path': p.exe(),
                    'proc_cmdline': ' '.join(p.cmdline()),
                    'proc_create_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.create_time())),
                    'proc_username': p.username()
                }
                self.proc_info_cache[pid] = info
                return info
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                self.logger.warning(f"Không thể truy cập tiến trình PID={pid}: {e}")
        return {}

    def _get_window_details(self, hwnd):
        self.logger.debug(f"Đang lấy thông tin chi tiết cho cửa sổ handle={hwnd}")
        data = {}
        try:
            data['win32_handle'] = hwnd
            data['pwa_title'] = win32gui.GetWindowText(hwnd)
            data['pwa_class_name'] = win32gui.GetClassName(hwnd)
            data['win32_styles'] = hex(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE))
            data['win32_extended_styles'] = hex(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE))
            rect = win32gui.GetWindowRect(hwnd)
            data['geo_rectangle_tuple'] = (rect[0], rect[1], rect[2], rect[3])
            
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
            data.update(self._get_process_info(pid))
        except Exception as e:
            self.logger.error(f"Lỗi khi lấy thông tin cửa sổ handle={hwnd}: {e}", exc_info=True)
        return data

    def _get_element_details_comprehensive(self, element):
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
            
            rect = element.CurrentBoundingRectangle
            if rect:
                data['geo_bounding_rect_tuple'] = (rect.left, rect.top, rect.right, rect.bottom)
        except comtypes.COMError:
            self.logger.warning(f"Lỗi COM khi truy cập element (Name: {data.get('pwa_title', 'N/A')}).")
        except Exception as e:
            self.logger.error(f"Lỗi không xác định khi lấy thông tin element: {e}", exc_info=True)
        return data

    def _request_scan(self):
        self.logger.info("Yêu cầu quét đã được ghi nhận từ F8.")
        self.scan_requested = True

    def run_scan_at_cursor(self):
        try:
            cursor_pos = win32gui.GetCursorPos()
            self.logger.info(f"Bắt đầu quét tại vị trí: {cursor_pos}")

            try:
                point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
                element = self.uia.ElementFromPoint(point)
            except Exception as e:
                self.logger.error(f"Lỗi nghiêm trọng khi gọi ElementFromPoint: {e}")
                return

            if not element:
                self.logger.warning("Không tìm thấy element nào dưới con trỏ.")
                return

            element_details = self._get_element_details_comprehensive(element)
            
            coords = element_details.get('geo_bounding_rect_tuple')
            if coords:
                self.logger.info(f"Đang vẽ hình chữ nhật tại tọa độ: {coords}")
                self._draw_highlight_rectangle(coords)

            top_level_window_handle = element.CurrentNativeWindowHandle
            parent = self.tree_walker.GetParentElement(element)
            while parent:
                handle = parent.CurrentNativeWindowHandle
                if handle != 0 and win32gui.IsWindow(handle) and win32gui.GetParent(handle) == 0:
                    top_level_window_handle = handle
                parent = self.tree_walker.GetParentElement(parent)

            window_details = self._get_window_details(top_level_window_handle) if top_level_window_handle else {}

            format_and_print_dict("WINDOW INFO", window_details)
            format_and_print_dict("ELEMENT INFO", element_details)

        except Exception as e:
            self.logger.error(f"Đã xảy ra lỗi không mong muốn trong quá trình quét: {e}", exc_info=True)


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
