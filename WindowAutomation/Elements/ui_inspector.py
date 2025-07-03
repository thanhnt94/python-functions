# Elements/ui_inspector.py
# Công cụ "Tất cả trong một" để kiểm tra và khám phá giao diện người dùng.
# Gộp chức năng từ ui_scanner, interactive_scanner, ui_core, và ui_spec_definitions.
# File này hoạt động hoàn toàn độc lập với giao diện đồ họa.

import logging
import re
import time
import os
import sys
import threading
import queue
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, font
from ctypes import wintypes

# --- Thư viện cần thiết ---
try:
    import pandas as pd
    import psutil
    import win32gui
    import win32process
    import win32con
    import comtypes
    import comtypes.client
    import keyboard
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    print("Gợi ý: pip install pandas openpyxl psutil pywin32 comtypes keyboard")
    exit()

try:
    from comtypes.gen import UIAutomationClient as UIA
except (ImportError, ModuleNotFoundError):
    UIA = None

# ======================================================================
#                      BỘ ĐỊNH NGHĨA VÀ HÀM LÕI
# ======================================================================

HIGHLIGHT_DURATION_MS = 2500 
INTERACTIVE_DIALOG_WIDTH = 350
INTERACTIVE_DIALOG_HEIGHT = 400  

QUICK_SPEC_WINDOW_KEYS = [
    'win32_handle', 
    'pwa_title', 
    'pwa_class_name'
]
QUICK_SPEC_ELEMENT_KEYS = [
    'pwa_auto_id', 
    'pwa_title', 
    'pwa_control_type', 
    'pwa_class_name'
]

PARAMETER_DEFINITIONS = {
    "pwa_title": "Tên/văn bản hiển thị của element (quan trọng nhất).", "pwa_auto_id": "Automation ID, một ID duy nhất để xác định element trong ứng dụng.",
    "pwa_control_type": "Loại control của element (ví dụ: Button, Edit, Tree).", "pwa_class_name": "Tên lớp Win32 của element (hữu ích cho các app cũ).",
    "pwa_framework_id": "Framework tạo ra element (ví dụ: UIA, Win32, WPF).", "win32_handle": "Handle (ID duy nhất) của cửa sổ do Windows quản lý.",
    "win32_styles": "Các cờ kiểu dáng của cửa sổ (dạng hexa).", "win32_extended_styles": "Các cờ kiểu dáng mở rộng của cửa sổ (dạng hexa).",
    "state_is_visible": "Trạng thái hiển thị (True nếu đang hiển thị).", "state_is_enabled": "Trạng thái cho phép tương tác (True nếu được kích hoạt).",
    "state_is_active": "Trạng thái hoạt động (True nếu là cửa sổ/element đang được focus).", "state_is_minimized": "Trạng thái thu nhỏ (True nếu cửa sổ đang bị thu nhỏ).",
    "state_is_maximized": "Trạng thái phóng to (True nếu cửa sổ đang được phóng to).", "state_is_focusable": "Trạng thái có thể nhận focus bàn phím.",
    "state_is_password": "Trạng thái là ô nhập mật khẩu.", "state_is_offscreen": "Trạng thái nằm ngoài màn hình hiển thị.",
    "state_is_content_element": "Là element chứa nội dung chính, không phải control trang trí.", "state_is_control_element": "Là element có thể tương tác (ngược với content).",
    "geo_rectangle_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của cửa sổ.", "geo_bounding_rect_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của element.",
    "geo_center_point": "Tọa độ điểm trung tâm của element.", "proc_pid": "Process ID (ID của tiến trình sở hữu cửa sổ).",
    "proc_thread_id": "Thread ID (ID của luồng sở hữu cửa sổ).", "proc_name": "Tên của tiến trình (ví dụ: 'notepad.exe').",
    "proc_path": "Đường dẫn đầy đủ đến file thực thi của tiến trình.", "proc_cmdline": "Dòng lệnh đã dùng để khởi chạy tiến trình.",
    "proc_create_time": "Thời gian tiến trình được tạo (dạng timestamp hoặc chuỗi).", "proc_username": "Tên người dùng đã khởi chạy tiến trình.",
    "rel_level": "Cấp độ sâu của element trong cây giao diện (0 là root).", "rel_parent_handle": "Handle của cửa sổ cha (nếu có, 0 là Desktop).",
    "rel_parent_title": "Tên/tiêu đề của element cha.", "rel_labeled_by": "Tên của element nhãn (label) liên kết với element này.",
    "rel_child_count": "Số lượng element con trực tiếp.", "uia_help_text": "Văn bản trợ giúp ngắn gọn cho element.",
    "uia_item_status": "Trạng thái của một item (ví dụ: 'Online', 'Busy').", "uia_supported_patterns": "Các Pattern tự động hóa được hỗ trợ (ví dụ: Invoke, Value, Toggle).",
    "uia_value": "Giá trị của element nếu hỗ trợ ValuePattern.", "uia_toggle_state": "Trạng thái của element nếu hỗ trợ TogglePattern (On, Off, Indeterminate).",
    "uia_expand_state": "Trạng thái nếu hỗ trợ ExpandCollapsePattern (Collapsed, Expanded, LeafNode).", "uia_selection_items": "Các item đang được chọn nếu hỗ trợ SelectionPattern.",
    "uia_range_value_info": "Thông tin (Min, Max, Value) nếu hỗ trợ RangeValuePattern.", "uia_grid_cell_info": "Thông tin (Row, Col, RowSpan, ColSpan) nếu hỗ trợ GridItemPattern.",
    "uia_table_row_headers": "Tiêu đề của hàng nếu hỗ trợ TableItemPattern.",
}

def get_parameter_definitions_as_dataframe():
    import pandas as pd
    items = []
    for key, description in PARAMETER_DEFINITIONS.items():
        category = key.split('_')[0].upper()
        items.append((category, key, description))
    return pd.DataFrame(items, columns=['Loại thông số', 'Thông số', 'Ý nghĩa'])

PROC_INFO_CACHE = {}

def _get_process_info(pid):
    if pid in PROC_INFO_CACHE: return PROC_INFO_CACHE[pid]
    if pid > 0:
        try:
            p = psutil.Process(pid)
            info = {'proc_name': p.name(), 'proc_path': p.exe(), 'proc_cmdline': ' '.join(p.cmdline()),
                    'proc_create_time': datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S'), 'proc_username': p.username()}
            PROC_INFO_CACHE[pid] = info
            return info
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    return {}

def _get_element_details_comprehensive(element, tree_walker):
    if not element:
        logging.warning("Đối tượng element không hợp lệ.")
        return {}
    
    logging.info("Bắt đầu thu thập thông tin chi tiết của element...")
    data = {}

    def get_prop(prop_name, prop_func):
        logging.debug(f"  - Đang thử lấy thuộc tính: {prop_name}")
        try:
            value = prop_func()
            if value not in [None, ""]:
                data[prop_name] = value
                logging.debug(f"    -> Thành công: {repr(value)}")
        except Exception as e:
            logging.warning(f"    -> Thất bại khi lấy {prop_name}: {e}")

    get_prop('proc_pid', lambda: element.CurrentProcessId)
    if 'proc_pid' in data:
        data.update(_get_process_info(data['proc_pid']))

    for key in PARAMETER_DEFINITIONS.keys():
        if key.startswith('pwa_'):
            get_prop(key, lambda k=key: getattr(element, 'Current' + k.replace('pwa_', '').replace('_', ' ').title().replace(' ', ''), None))
        elif key.startswith('state_'):
            get_prop(key, lambda k=key: getattr(element, 'Current' + k.replace('state_', '').title().replace(' ', ''), None))
    
    get_prop('pwa_title', lambda: element.CurrentName)
    get_prop('pwa_auto_id', lambda: element.CurrentAutomationId)
    get_prop('pwa_class_name', lambda: element.CurrentClassName)
    get_prop('pwa_framework_id', lambda: element.CurrentFrameworkId)
    get_prop('win32_handle', lambda: element.CurrentNativeWindowHandle)
    get_prop('state_is_enabled', lambda: bool(element.CurrentIsEnabled))
    
    try:
        rect = element.CurrentBoundingRectangle
        if rect: data['geo_bounding_rect_tuple'] = (rect.left, rect.top, rect.right, rect.bottom)
    except Exception: pass
    
    level = 0
    current = element
    try:
        while True:
            parent = tree_walker.GetParentElement(current)
            if not parent or parent.CurrentNativeWindowHandle == 0:
                break
            current = parent
            level += 1
    except comtypes.COMError:
        pass
    data['rel_level'] = level

    logging.info("Hoàn tất thu thập thông tin element.")
    return {k: v for k, v in data.items() if v is not None}

def _get_window_details(hwnd, uia_instance, tree_walker):
    if not win32gui.IsWindow(hwnd): return {}
    try:
        element = uia_instance.ElementFromHandle(hwnd)
        return _get_element_details_comprehensive(element, tree_walker)
    except comtypes.COMError:
        data = {}
        data['win32_handle'] = hwnd
        data['pwa_title'] = win32gui.GetWindowText(hwnd)
        data['pwa_class_name'] = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        data['proc_pid'] = pid
        data.update(_get_process_info(pid))
        return data

def _format_dict_as_pep8_string(spec_dict):
    if not spec_dict: return "{}"
    dict_to_format = {k: v for k, v in spec_dict.items() if not k.startswith('sys_') and (v is False or v)}
    if not dict_to_format: return "{}"
    items_str = [f"    '{k}': {repr(v)}," for k, v in sorted(dict_to_format.items())]
    return f"{{\n" + "\n".join(items_str) + "\n}}"

def _create_quick_spec_string(window_info, element_info):
    quick_win_spec = {}
    for key in QUICK_SPEC_WINDOW_KEYS:
        if key in window_info and window_info[key]:
            quick_win_spec[key] = window_info[key]
    
    quick_elem_spec = {}
    for key in QUICK_SPEC_ELEMENT_KEYS:
        if key in element_info and element_info[key]:
            quick_elem_spec[key] = element_info[key]

    win_str = f"window_spec = {_format_dict_as_pep8_string(quick_win_spec)}"
    elem_str = f"element_spec = {_format_dict_as_pep8_string(quick_elem_spec)}"
    
    return f"{win_str}\n{elem_str}"

def _clean_element_spec(window_info, element_info):
    if not window_info or not element_info:
        return element_info
    
    cleaned_spec = element_info.copy()
    if window_info.get('proc_pid') == element_info.get('proc_pid'):
        for key in list(cleaned_spec.keys()):
            if key.startswith('proc_'):
                del cleaned_spec[key]
    return cleaned_spec

# ======================================================================
#                      LỚP UIINSPECTOR CHÍNH
# ======================================================================

class UIInspector:
    def __init__(self, root_gui):
        if UIA is None: raise RuntimeError("UIAutomationClient không thể khởi tạo.")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.root_gui = root_gui
        self.current_element = None
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Lỗi nghiêm trọng khi khởi tạo COM: {e}", exc_info=True)
            raise

    def scan_window_to_excel(self, wait_time=3):
        self.logger.info(f"Vui lòng chuyển sang cửa sổ muốn quét. Bắt đầu sau {wait_time} giây...")
        self.root_gui.show_countdown_timer(wait_time)
        
        active_hwnd = win32gui.GetForegroundWindow()
        if not active_hwnd:
            self.logger.error("Không tìm thấy cửa sổ nào đang hoạt động.")
            return None

        window_title = win32gui.GetWindowText(active_hwnd)
        self.logger.info(f"Bắt đầu quét toàn bộ cửa sổ: '{window_title}' (Handle: {active_hwnd})")
        
        original_level = logging.getLogger().getEffectiveLevel()
        logging.getLogger().setLevel(logging.INFO)
        
        try:
            window_data = _get_window_details(active_hwnd, self.uia, self.tree_walker)
            all_elements_data = []
            root_element = self.uia.ElementFromHandle(active_hwnd)
            if root_element: self._walk_element_tree(root_element, 0, all_elements_data)
        except comtypes.COMError as e:
            self.logger.error(f"Lỗi COM khi quét cửa sổ. Lỗi: {e}")
            return None
        finally:
            logging.getLogger().setLevel(original_level)
        
        self.logger.info(f"Đã quét xong. Thu thập được {len(all_elements_data)} elements.")
        if not all_elements_data and not window_data:
            self.logger.warning("Không thu thập được thông tin nào.")
            return None

        save_folder = Path.home() / "UiInspectorResults"
        save_folder.mkdir(exist_ok=True)
        sanitized_title = re.sub(r'[\\/:*?"<>|]', '_', window_title)[:100] or "ScannedWindow"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"Scan_{sanitized_title}_{timestamp}.xlsx"
        full_output_path = save_folder / output_filename
        self.logger.info(f"Đang lưu kết quả vào: {full_output_path}")

        try:
            if window_data: window_data['spec_to_copy'] = _format_dict_as_pep8_string(window_data)
            for item in all_elements_data: item['spec_to_copy'] = _format_dict_as_pep8_string(item)
            df_window = pd.DataFrame([window_data]) if window_data else pd.DataFrame()
            df_elements = pd.DataFrame(all_elements_data) if all_elements_data else pd.DataFrame()
            df_lookup = get_parameter_definitions_as_dataframe()
            with pd.ExcelWriter(full_output_path, engine='openpyxl') as writer:
                if not df_window.empty: df_window.to_excel(writer, sheet_name='Windows Info', index=False)
                if not df_elements.empty: df_elements.to_excel(writer, sheet_name='Elements Details', index=False)
                df_lookup.to_excel(writer, sheet_name='Tra cứu thông số', index=False)
            self.logger.info(f"Đã lưu thành công.")
            return full_output_path
        except Exception as e:
            self.logger.error(f"Lỗi khi ghi file Excel: {e}", exc_info=True)
            return None

    def _walk_element_tree(self, element, level, all_elements_data, max_depth=25):
        if element is None or level > max_depth: return
        try:
            element_data = _get_element_details_comprehensive(element, self.tree_walker)
            if element_data:
                all_elements_data.append(element_data)
            child = self.tree_walker.GetFirstChildElement(element)
            while child:
                self._walk_element_tree(child, level + 1, all_elements_data, max_depth)
                try: child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError: break
        except Exception: pass

    def _find_main_window_from_pid(self, pid):
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnds.append(hwnd)
            return True
        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        return hwnds[0] if hwnds else 0

    def _run_scan_at_cursor(self):
        self.logger.info("Yêu cầu quét đã được ghi nhận từ F8.")
        
        self.root_gui.destroy_highlight()
        
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            element = self.uia.ElementFromPoint(point)
            
            if not element: 
                self.logger.warning("Không tìm thấy element nào dưới con trỏ.")
                return

            smallest_element = element
            while True:
                try:
                    child = self.tree_walker.GetFirstChildElement(smallest_element)
                    found_deeper = False
                    while child:
                        child_rect = child.CurrentBoundingRectangle
                        if (point.x >= child_rect.left and point.x <= child_rect.right and
                            point.y >= child_rect.top and point.y <= child_rect.bottom):
                            smallest_element = child
                            found_deeper = True
                            break
                        child = self.tree_walker.GetNextSiblingElement(child)
                    if not found_deeper:
                        break
                except comtypes.COMError:
                    break
            
            self.current_element = smallest_element
            self._inspect_element(self.current_element)

        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn trong quá trình quét", exc_info=True)


    def _scan_parent_element(self):
        self.logger.info("Yêu cầu quét phần tử cha từ F7.")
        if not self.current_element:
            self.logger.warning("Chưa có element nào được quét. Vui lòng nhấn F8 trước.")
            return
        
        try:
            parent = self.tree_walker.GetParentElement(self.current_element)
            if parent and parent.CurrentNativeWindowHandle != 0:
                self.current_element = parent
                self._inspect_element(self.current_element)
            else:
                self.logger.warning("Không tìm thấy phần tử cha hợp lệ.")
        except Exception as e:
            self.logger.error(f"Lỗi khi quét phần tử cha: {e}", exc_info=True)
    
    def _scan_child_element(self):
        self.logger.info("Yêu cầu quét phần tử con từ F9.")
        if not self.current_element:
            self.logger.warning("Chưa có element nào được quét. Vui lòng nhấn F8 trước.")
            return
        
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            
            child = self.tree_walker.GetFirstChildElement(self.current_element)
            found_child = None
            while child:
                child_rect = child.CurrentBoundingRectangle
                if (point.x >= child_rect.left and point.x <= child_rect.right and
                    point.y >= child_rect.top and point.y <= child_rect.bottom):
                    found_child = child
                    break
                child = self.tree_walker.GetNextSiblingElement(child)
            
            if found_child:
                self.current_element = found_child
                self._inspect_element(self.current_element)
            else:
                self.logger.warning("Không tìm thấy element con nào dưới con trỏ.")

        except Exception as e:
            self.logger.error(f"Lỗi khi quét phần tử con: {e}", exc_info=True)

    def _inspect_element(self, element):
        element_details = _get_element_details_comprehensive(element, self.tree_walker)
        element_pid = element_details.get('proc_pid')
        top_level_window_handle = self._find_main_window_from_pid(element_pid) if element_pid else 0
        window_details = _get_window_details(top_level_window_handle, self.uia, self.tree_walker) if top_level_window_handle else {}
        
        coords = element_details.get('geo_bounding_rect_tuple')
        if coords:
            level = element_details.get('rel_level', 0)
            self._draw_highlight_rectangle(coords, level)
        
        cleaned_element_details = _clean_element_spec(window_details, element_details)
        self.root_gui.update_spec_dialog(window_details, cleaned_element_details)

    def _draw_highlight_rectangle(self, rect, level=0):
        try:
            self.root_gui.destroy_highlight()
            colors = ['#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF', '#4B0082', '#9400D3']
            color = colors[level % len(colors)]

            highlight_window = tk.Toplevel(self.root_gui)
            highlight_window.overrideredirect(True)
            highlight_window.wm_attributes("-topmost", True)
            highlight_window.wm_attributes("-disabled", True)
            highlight_window.wm_attributes("-transparentcolor", "white")
            highlight_window.geometry(f'{rect[2]-rect[0]}x{rect[3]-rect[1]}+{rect[0]}+{rect[1]}')
            canvas = tk.Canvas(highlight_window, bg='white', highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_rectangle(2, 2, rect[2]-rect[0]-2, rect[3]-rect[1]-2, outline=color, width=4)
            self.root_gui.highlight_window = highlight_window
            highlight_window.after(HIGHLIGHT_DURATION_MS, highlight_window.destroy)
        except Exception as e:
            self.logger.error(f"Lỗi khi vẽ hình chữ nhật: {e}")

# ======================================================================
#                      LỚP GIAO DIỆN ĐỒ HỌA
# ======================================================================

class InspectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UI Inspector")
        self.geometry("450x300")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        
        self.inspector = UIInspector(self)
        self.spec_dialog = None
        self.highlight_window = None
        
        self.task_queue = queue.Queue()

        style = ttk.Style(self)
        style.configure("TButton", padding=10, font=('Segoe UI', 12))
        style.configure("TLabel", padding=5, font=('Segoe UI', 10))
        style.configure("Header.TLabel", font=('Segoe UI', 16, 'bold'))
        style.configure("Small.TButton", padding=1, font=('Segoe UI', 8))
        
        self.create_main_widgets()

    def create_main_widgets(self):
        self.main_frame = ttk.Frame(self, padding="20")
        self.main_frame.pack(fill="both", expand=True)

        header_label = ttk.Label(self.main_frame, text="UI Inspector", style="Header.TLabel", anchor="center")
        header_label.pack(pady=(0, 20))

        scan_excel_btn = ttk.Button(self.main_frame, text="Quét toàn bộ cửa sổ (ra Excel)", command=self.run_full_scan)
        scan_excel_btn.pack(fill="x", pady=5)

        interactive_btn = ttk.Button(self.main_frame, text="Bắt đầu chế độ quét tương tác", command=self.run_interactive_scan)
        interactive_btn.pack(fill="x", pady=5)

    def run_full_scan(self):
        self.withdraw()
        file_path = self.inspector.scan_window_to_excel()
        self.deiconify()
        self.show_scan_result(file_path)

    def run_interactive_scan(self):
        self.withdraw()
        self.show_spec_dialog()
        listener_thread = threading.Thread(target=self.keyboard_listener_thread, daemon=True)
        listener_thread.start()
        self.process_queue()

    def keyboard_listener_thread(self):
        keyboard.add_hotkey('f8', lambda: self.task_queue.put('scan'))
        keyboard.add_hotkey('f7', lambda: self.task_queue.put('scan_parent'))
        keyboard.add_hotkey('f9', lambda: self.task_queue.put('scan_child'))
        keyboard.wait('esc')
        self.task_queue.put('stop')

    def process_queue(self):
        try:
            task = self.task_queue.get_nowait()
            if task == 'scan':
                self.inspector._run_scan_at_cursor()
            elif task == 'scan_parent':
                self.inspector._scan_parent_element()
            elif task == 'scan_child':
                self.inspector._scan_child_element()
            elif task == 'stop':
                self.stop_interactive_scan()
                return
        except queue.Empty:
            pass
        self.after(100, self.process_queue)

    def stop_interactive_scan(self):
        logging.info("Phím ESC được nhấn, thoát chế độ tương tác.")
        keyboard.unhook_all()
        self.hide_spec_dialog()
        self.deiconify()

    def show_spec_dialog(self):
        if self.spec_dialog and self.spec_dialog.winfo_exists():
            self.spec_dialog.lift()
            return
            
        self.spec_dialog = tk.Toplevel(self)
        self.spec_dialog.title("Kết quả quét tương tác")
        self.spec_dialog.geometry(f"{INTERACTIVE_DIALOG_WIDTH}x{INTERACTIVE_DIALOG_HEIGHT}")
        self.spec_dialog.wm_attributes("-topmost", 1)
        self.spec_dialog.protocol("WM_DELETE_WINDOW", self.stop_interactive_scan)

        def copy_to_clipboard(content, button):
            self.spec_dialog.clipboard_clear()
            self.spec_dialog.clipboard_append(content)
            self.spec_dialog.update()
            button.config(text="Copied!")
            self.spec_dialog.after(1500, lambda: button.config(text="Copy"))

        main_frame = ttk.Frame(self.spec_dialog, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1) # Sửa lỗi: Cho phép co giãn
        main_frame.rowconfigure(1, weight=1) # Sửa lỗi: Cho phép co giãn
        main_frame.rowconfigure(2, weight=1) # Sửa lỗi: Cho phép co giãn

        win_frame = ttk.LabelFrame(main_frame, text="Window Spec (Thông tin đầy đủ)", padding=10)
        win_frame.grid(row=0, column=0, sticky="nsew", pady=5)
        win_frame.columnconfigure(0, weight=1)
        win_frame.rowconfigure(0, weight=1)
        self.win_text = tk.Text(win_frame, wrap="word", font=("Courier New", 10))
        self.win_text.grid(row=0, column=0, sticky="nsew")
        win_copy_btn = ttk.Button(win_frame, text="Copy", style="Small.TButton", command=lambda: copy_to_clipboard(self.win_text.get("1.0", "end-1c"), win_copy_btn))
        win_copy_btn.grid(row=0, column=1, padx=5, sticky='n')

        elem_frame = ttk.LabelFrame(main_frame, text="Element Spec (Thông tin đầy đủ)", padding=10)
        elem_frame.grid(row=1, column=0, sticky="ew", pady=5)
        elem_frame.columnconfigure(0, weight=1)
        elem_frame.rowconfigure(0, weight=1)
        self.elem_text = tk.Text(elem_frame, wrap="word", font=("Courier New", 10))
        self.elem_text.grid(row=0, column=0, sticky="nsew")
        elem_copy_btn = ttk.Button(elem_frame, text="Copy", style="Small.TButton", command=lambda: copy_to_clipboard(self.elem_text.get("1.0", "end-1c"), elem_copy_btn))
        elem_copy_btn.grid(row=0, column=1, padx=5, sticky='n')
        
        quick_frame = ttk.LabelFrame(main_frame, text="Quick Spec (Gợi ý để copy nhanh)", padding=10)
        quick_frame.grid(row=2, column=0, sticky="ew", pady=5)
        quick_frame.columnconfigure(0, weight=1)
        quick_frame.rowconfigure(0, weight=1)
        self.quick_text = tk.Text(quick_frame, wrap="word", font=("Courier New", 10))
        self.quick_text.grid(row=0, column=0, sticky="nsew")
        quick_copy_btn = ttk.Button(quick_frame, text="Copy", style="Small.TButton", command=lambda: copy_to_clipboard(self.quick_text.get("1.0", "end-1c"), quick_copy_btn))
        quick_copy_btn.grid(row=0, column=1, padx=5, sticky='n')

    def update_spec_dialog(self, window_info, element_info):
        if not self.spec_dialog or not self.spec_dialog.winfo_exists():
            return
        
        level = element_info.get('rel_level', 0)
        self.spec_dialog.title(f"Kết quả quét tương tác (Level: {level})")
            
        win_spec_str = f"window_spec = {_format_dict_as_pep8_string(window_info)}"
        self.win_text.config(state="normal")
        self.win_text.delete("1.0", "end")
        self.win_text.insert("1.0", win_spec_str)
        self.win_text.config(state="disabled")

        elem_spec_str = f"element_spec = {_format_dict_as_pep8_string(element_info)}"
        self.elem_text.config(state="normal")
        self.elem_text.delete("1.0", "end")
        self.elem_text.insert("1.0", elem_spec_str)
        self.elem_text.config(state="disabled")
        
        quick_spec_str = _create_quick_spec_string(window_info, element_info)
        self.quick_text.config(state="normal")
        self.quick_text.delete("1.0", "end")
        self.quick_text.insert("1.0", quick_spec_str)
        self.quick_text.config(state="disabled")

    def destroy_highlight(self):
        if self.highlight_window and self.highlight_window.winfo_exists():
            self.highlight_window.destroy()
        self.highlight_window = None

    def hide_spec_dialog(self):
        if self.spec_dialog:
            self.spec_dialog.destroy()
            self.spec_dialog = None

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = InspectorApp()
    app.mainloop()
