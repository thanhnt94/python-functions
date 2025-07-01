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

def _get_element_details_comprehensive(element):
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

    logging.info("Hoàn tất thu thập thông tin element.")
    return {k: v for k, v in data.items() if v is not None}

def _get_window_details(hwnd, uia_instance):
    if not win32gui.IsWindow(hwnd): return {}
    try:
        element = uia_instance.ElementFromHandle(hwnd)
        return _get_element_details_comprehensive(element)
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

# ======================================================================
#                      LỚP UIINSPECTOR CHÍNH
# ======================================================================

class UIInspector:
    def __init__(self, root_gui):
        if UIA is None: raise RuntimeError("UIAutomationClient không thể khởi tạo.")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.root_gui = root_gui
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
            window_data = _get_window_details(active_hwnd, self.uia)
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
            element_data = _get_element_details_comprehensive(element)
            if element_data:
                element_data['rel_level'] = level
                all_elements_data.append(element_data)
            child = self.tree_walker.GetFirstChildElement(element)
            while child:
                self._walk_element_tree(child, level + 1, all_elements_data, max_depth)
                try: child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError: break
        except Exception: pass

    def _run_scan_at_cursor(self):
        self.logger.info("Yêu cầu quét đã được ghi nhận từ F8.")
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            element = self.uia.ElementFromPoint(point)
            if not element: 
                self.logger.warning("Không tìm thấy element nào dưới con trỏ.")
                return

            top_level_element = element
            try:
                parent = self.tree_walker.GetParentElement(top_level_element)
                while parent:
                    if not parent or parent.CurrentNativeWindowHandle == 0: break
                    top_level_element = parent
                    parent = self.tree_walker.GetParentElement(top_level_element)
                top_level_window_handle = top_level_element.CurrentNativeWindowHandle
            except comtypes.COMError:
                top_level_window_handle = element.CurrentNativeWindowHandle

            element_details = _get_element_details_comprehensive(element)
            window_details = _get_window_details(top_level_window_handle, self.uia)
            
            coords = element_details.get('geo_bounding_rect_tuple')
            if coords: self._draw_highlight_rectangle(coords)
            
            self.root_gui.update_spec_dialog(window_details, element_details)
        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn trong quá trình quét", exc_info=True)

    def _draw_highlight_rectangle(self, rect):
        try:
            root = tk.Toplevel(self.root_gui)
            root.overrideredirect(True)
            root.wm_attributes("-topmost", True)
            root.wm_attributes("-disabled", True)
            root.wm_attributes("-transparentcolor", "white")
            root.geometry(f'{rect[2]-rect[0]}x{rect[3]-rect[1]}+{rect[0]}+{rect[1]}')
            canvas = tk.Canvas(root, bg='white', highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_rectangle(2, 2, rect[2]-rect[0]-2, rect[3]-rect[1]-2, outline='red', width=4)
            root.after(1500, root.destroy)
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
        
        self.task_queue = queue.Queue()

        style = ttk.Style(self)
        style.configure("TButton", padding=10, font=('Segoe UI', 12))
        style.configure("TLabel", padding=5, font=('Segoe UI', 10))
        style.configure("Header.TLabel", font=('Segoe UI', 16, 'bold'))
        
        self.create_main_widgets()

    def create_main_widgets(self):
        self.main_frame = ttk.Frame(self, padding="20")
        self.main_frame.pack(fill="both", expand=True)

        header_label = ttk.Label(self.main_frame, text="UI Inspector", style="Header.TLabel", anchor="center")
        header_label.pack(pady=(0, 20))

        scan_excel_btn = ttk.Button(self.main_frame, text="Quét toàn bộ cửa sổ (ra Excel)", command=self.run_full_scan)
        scan_excel_btn.pack(fill="x", pady=5)

        interactive_btn = ttk.Button(self.main_frame, text="Bắt đầu chế độ quét tương tác (F8)", command=self.run_interactive_scan)
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
        keyboard.wait('esc')
        self.task_queue.put('stop')

    def process_queue(self):
        try:
            task = self.task_queue.get_nowait()
            if task == 'scan':
                self.inspector._run_scan_at_cursor()
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

    def show_countdown_timer(self, seconds):
        timer_window = tk.Toplevel(self)
        timer_window.title("Đang chờ...")
        timer_window.geometry("300x100")
        timer_window.wm_attributes("-topmost", 1)
        timer_window.resizable(False, False)
        
        label = ttk.Label(timer_window, font=('Segoe UI', 14))
        label.pack(pady=20, expand=True)

        def update_timer(sec):
            if sec > 0:
                label.config(text=f"Bắt đầu quét sau: {sec} giây...")
                self.after(1000, update_timer, sec - 1)
            else:
                timer_window.destroy()
        
        update_timer(seconds)
        self.wait_window(timer_window)

    def show_scan_result(self, file_path):
        result_dialog = tk.Toplevel(self)
        result_dialog.title("Quét hoàn tất")
        result_dialog.geometry("600x200")
        result_dialog.wm_attributes("-topmost", 1)

        if file_path:
            label_text = "Quét thành công! File đã được lưu tại:"
            link_text = str(file_path)
            
            msg_label = ttk.Label(result_dialog, text=label_text, wraplength=580)
            msg_label.pack(padx=10, pady=5)

            link_label = ttk.Label(result_dialog, text=link_text, foreground="blue", cursor="hand2", wraplength=580)
            link_label.pack(padx=10, pady=5)
            link_font = font.Font(link_label, link_label.cget("font"))
            link_font.configure(underline=True)
            link_label.configure(font=link_font)
            link_label.bind("<Button-1>", lambda e: os.startfile(file_path))
        else:
            msg_label = ttk.Label(result_dialog, text="Quét thất bại. Vui lòng xem log để biết chi tiết.")
            msg_label.pack(padx=10, pady=20)

        close_btn = ttk.Button(result_dialog, text="Đóng", command=result_dialog.destroy)
        close_btn.pack(pady=10)
        result_dialog.transient(self)
        result_dialog.grab_set()

    def show_spec_dialog(self):
        if self.spec_dialog and self.spec_dialog.winfo_exists():
            self.spec_dialog.lift()
            return
            
        self.spec_dialog = tk.Toplevel(self)
        self.spec_dialog.title("Kết quả quét tương tác (F8)")
        self.spec_dialog.geometry("850x700")
        self.spec_dialog.wm_attributes("-topmost", 1)
        self.spec_dialog.protocol("WM_DELETE_WINDOW", self.stop_interactive_scan)

        def copy_to_clipboard(content, button):
            self.spec_dialog.clipboard_clear()
            self.spec_dialog.clipboard_append(content)
            self.spec_dialog.update()
            button.config(text="Đã copy!")
            self.spec_dialog.after(1500, lambda: button.config(text="Copy"))

        main_frame = ttk.Frame(self.spec_dialog, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)

        win_frame = ttk.LabelFrame(main_frame, text="Window Spec (Thông tin đầy đủ)", padding=10)
        win_frame.grid(row=0, column=0, sticky="ew", pady=5)
        win_frame.columnconfigure(0, weight=1)
        self.win_text = tk.Text(win_frame, height=8, wrap="word", font=("Courier New", 10))
        self.win_text.grid(row=0, column=0, sticky="nsew")
        win_copy_btn = ttk.Button(win_frame, text="Copy", command=lambda: copy_to_clipboard(self.win_text.get("1.0", "end-1c"), win_copy_btn))
        win_copy_btn.grid(row=0, column=1, padx=5, sticky='n')

        elem_frame = ttk.LabelFrame(main_frame, text="Element Spec (Thông tin đầy đủ)", padding=10)
        elem_frame.grid(row=1, column=0, sticky="ew", pady=5)
        elem_frame.columnconfigure(0, weight=1)
        self.elem_text = tk.Text(elem_frame, height=12, wrap="word", font=("Courier New", 10))
        self.elem_text.grid(row=0, column=0, sticky="nsew")
        elem_copy_btn = ttk.Button(elem_frame, text="Copy", command=lambda: copy_to_clipboard(self.elem_text.get("1.0", "end-1c"), elem_copy_btn))
        elem_copy_btn.grid(row=0, column=1, padx=5, sticky='n')
        
        quick_frame = ttk.LabelFrame(main_frame, text="Quick Spec (Gợi ý để copy nhanh)", padding=10)
        quick_frame.grid(row=2, column=0, sticky="ew", pady=5)
        quick_frame.columnconfigure(0, weight=1)
        self.quick_text = tk.Text(quick_frame, height=8, wrap="word", font=("Courier New", 10))
        self.quick_text.grid(row=0, column=0, sticky="nsew")
        quick_copy_btn = ttk.Button(quick_frame, text="Copy", command=lambda: copy_to_clipboard(self.quick_text.get("1.0", "end-1c"), quick_copy_btn))
        quick_copy_btn.grid(row=0, column=1, padx=5, sticky='n')

    def update_spec_dialog(self, window_info, element_info):
        if not self.spec_dialog or not self.spec_dialog.winfo_exists():
            return
            
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

    def hide_spec_dialog(self):
        if self.spec_dialog:
            self.spec_dialog.destroy()
            self.spec_dialog = None

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = InspectorApp()
    app.mainloop()
