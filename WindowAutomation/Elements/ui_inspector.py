# Elements/ui_inspector.py
# Phiên bản 2.7: Khôi phục logic quét con (F9) gốc của bạn để đảm bảo độ mượt.
# Công cụ "Tất cả trong một" để kiểm tra và khám phá giao diện người dùng.

import logging
import re
import time
import os
import sys
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font
from ctypes import wintypes

# --- Thư viện cần thiết ---
try:
    import pandas as pd
    import win32gui
    import win32process
    import comtypes
    import comtypes.client
    import keyboard
    from comtypes.gen import UIAutomationClient as UIA
    from pywinauto import uia_defines # Import để lấy tên control type
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    print("Gợi ý: pip install pandas openpyxl pywin32 comtypes keyboard pywinauto")
    exit()

# --- Import các thành phần dùng chung (Đã sửa lỗi) ---
try:
    # Cách import này dùng khi chạy file như một phần của package lớn hơn
    from . import ui_shared_logic
except ImportError:
    # Cách import này dùng khi chạy file ui_inspector.py trực tiếp
    import ui_shared_logic

# ======================================================================
#                      BỘ ĐỊNH NGHĨA VÀ HÀM LÕI
# ======================================================================

HIGHLIGHT_DURATION_MS = 2500
INTERACTIVE_DIALOG_WIDTH = 450
INTERACTIVE_DIALOG_HEIGHT = 500

QUICK_SPEC_WINDOW_KEYS = [
    'win32_handle',
    'pwa_title',
    'pwa_class_name',
    'proc_name'
]
QUICK_SPEC_ELEMENT_KEYS = [
    'pwa_auto_id',
    'pwa_title',
    'pwa_control_type',
    'pwa_class_name'
]

# Tạo một bảng tra cứu ngược từ ID sang Tên cho ControlType
_CONTROL_TYPE_ID_TO_NAME = {v: k for k, v in uia_defines.IUIA().known_control_types.items()}

def get_parameter_definitions_as_dataframe():
    items = []
    for key, description in ui_shared_logic.PARAMETER_DEFINITIONS.items():
        category = key.split('_')[0].upper()
        items.append((category, key, description))
    return pd.DataFrame(items, columns=['Loại thông số', 'Thông số', 'Ý nghĩa'])

def _get_element_details_comprehensive(com_element, uia_instance, tree_walker):
    """
    Lấy thông tin chi tiết của một COM element bằng cách sử dụng logic chung.
    """
    if not com_element:
        logging.warning("Đối tượng com_element không hợp lệ.")
        return {}

    class FakePwaElement:
        """Một lớp giả để chứa com_element và các thuộc tính cơ bản."""
        def __init__(self, element):
            self.element_info = self
            self.element = element
            self._handle = None
            self._pid = None

        @property
        def handle(self):
            if self._handle is None:
                try: self._handle = self.element.CurrentNativeWindowHandle
                except comtypes.COMError: self._handle = 0
            return self._handle

        @property
        def process_id(self):
            if self._pid is None:
                try: self._pid = self.element.CurrentProcessId
                except comtypes.COMError: self._pid = 0
            return self._pid

    fake_element = FakePwaElement(com_element)
    
    all_props = {}
    for key in ui_shared_logic.SUPPORTED_FILTER_KEYS:
        value = ui_shared_logic.get_property_value(fake_element, key, uia_instance, tree_walker)
        if value is not None and value != '':
            all_props[key] = value

    # Bổ sung các thuộc tính cơ bản trực tiếp từ com_element một cách an toàn
    try: all_props['pwa_title'] = com_element.CurrentName
    except comtypes.COMError: pass
    try: all_props['pwa_auto_id'] = com_element.CurrentAutomationId
    except comtypes.COMError: pass
    try: all_props['pwa_class_name'] = com_element.CurrentClassName
    except comtypes.COMError: pass
    try:
        control_type_id = com_element.CurrentControlType
        all_props['pwa_control_type'] = _CONTROL_TYPE_ID_TO_NAME.get(control_type_id, f"UnknownID_{control_type_id}")
    except comtypes.COMError: pass
    try: all_props['pwa_framework_id'] = com_element.CurrentFrameworkId
    except comtypes.COMError: pass
    try: all_props['state_is_enabled'] = bool(com_element.CurrentIsEnabled)
    except comtypes.COMError: pass
    try:
        rect = com_element.CurrentBoundingRectangle
        if rect: all_props['geo_bounding_rect_tuple'] = (rect.left, rect.top, rect.right, rect.bottom)
    except comtypes.COMError: pass
    
    return {k: v for k, v in all_props.items() if v is not None and v != ''}


def _get_window_details(hwnd, uia_instance, tree_walker):
    if not win32gui.IsWindow(hwnd): return {}
    try:
        element = uia_instance.ElementFromHandle(hwnd)
        return _get_element_details_comprehensive(element, uia_instance, tree_walker)
    except comtypes.COMError:
        data = {}
        data['win32_handle'] = hwnd
        data['pwa_title'] = win32gui.GetWindowText(hwnd)
        data['pwa_class_name'] = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        data['proc_pid'] = pid
        data.update(ui_shared_logic.get_process_info(pid))
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
    
    return f"{win_str}\n\n{elem_str}"

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
        
        try:
            window_data = _get_window_details(active_hwnd, self.uia, self.tree_walker)
            all_elements_data = []
            root_element = self.uia.ElementFromHandle(active_hwnd)
            if root_element: self._walk_element_tree(root_element, 0, all_elements_data)
        except comtypes.COMError as e:
            self.logger.error(f"Lỗi COM khi quét cửa sổ. Lỗi: {e}")
            return None
        
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
            element_data = _get_element_details_comprehensive(element, self.uia, self.tree_walker)
            if element_data:
                all_elements_data.append(element_data)
            child = self.tree_walker.GetFirstChildElement(element)
            while child:
                self._walk_element_tree(child, level + 1, all_elements_data, max_depth)
                try: child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError: break
        except Exception as e:
            self.logger.warning(f"Lỗi khi duyệt cây element: {e}")

    def _run_scan_at_cursor(self):
        self.logger.info("Yêu cầu quét (F8) đã được ghi nhận.")
        self.root_gui.destroy_highlight()
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            element = self.uia.ElementFromPoint(point)
            if not element: 
                self.logger.warning("Không tìm thấy element nào dưới con trỏ.")
                return

            self.current_element = element
            self._inspect_element(self.current_element)

        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn trong quá trình quét: {e}", exc_info=True)

    def _scan_parent_element(self):
        self.logger.info("Yêu cầu quét phần tử cha (F7) đã được ghi nhận.")
        if not self.current_element:
            self.logger.warning("Chưa có element nào được quét. Vui lòng nhấn F8 trước.")
            return
        
        try:
            parent = self.tree_walker.GetParentElement(self.current_element)
            if parent:
                self.current_element = parent
                self._inspect_element(self.current_element)
            else:
                self.logger.warning("Không tìm thấy phần tử cha hợp lệ.")
        except Exception as e:
            self.logger.error(f"Lỗi khi quét phần tử cha: {e}", exc_info=True)
    
    # **SỬA LỖI**: Khôi phục logic quét con (F9) gốc của bạn để đảm bảo độ mượt.
    def _scan_child_element(self):
        self.logger.info("Yêu cầu quét phần tử con (F9) đã được ghi nhận.")
        if not self.current_element:
            self.logger.warning("Chưa có element nào được quét. Vui lòng nhấn F8 trước.")
            return
        
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            
            # An toàn lấy phần tử con đầu tiên
            try:
                child = self.tree_walker.GetFirstChildElement(self.current_element)
            except comtypes.COMError:
                self.logger.warning("Element hiện tại không có con hoặc không thể truy cập.")
                return

            # Lặp qua các phần tử con trực tiếp để tìm phần tử dưới con trỏ
            found_child = None
            while child:
                try:
                    child_rect = child.CurrentBoundingRectangle
                    if (child_rect and
                        point.x >= child_rect.left and point.x <= child_rect.right and
                        point.y >= child_rect.top and point.y <= child_rect.bottom):
                        
                        found_child = child
                        break # Tìm thấy con trực tiếp đầu tiên dưới con trỏ và dừng lại
                    
                    child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError:
                    break # Dừng nếu có lỗi khi lấy sibling tiếp theo
            
            if found_child:
                self.logger.info(f"Đi vào con: '{found_child.CurrentName}'. Đang cập nhật...")
                self.current_element = found_child
                self._inspect_element(self.current_element)
            else:
                self.logger.warning("Không tìm thấy element con nào dưới con trỏ.")

        except Exception as e:
            self.logger.error(f"Lỗi không mong muốn khi quét phần tử con: {e}", exc_info=True)


    def _inspect_element(self, element):
        element_details = _get_element_details_comprehensive(element, self.uia, self.tree_walker)
        
        top_level_window_handle = 0
        current = element
        try:
            while True:
                parent = self.tree_walker.GetParentElement(current)
                if not parent or parent.CurrentNativeWindowHandle == 0:
                    top_level_window_handle = current.CurrentNativeWindowHandle
                    break
                current = parent
        except comtypes.COMError:
             try:
                 top_level_window_handle = element.CurrentNativeWindowHandle
             except comtypes.COMError:
                 top_level_window_handle = 0


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
            highlight_window.wm_attributes("-topmost", True, "-disabled", True, "-transparentcolor", "white")
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
        self.title("UI Inspector v2.7 (Final)")
        self.geometry("450x300")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.inspector = UIInspector(self)
        self.spec_dialog = None
        self.highlight_window = None
        self.listener_thread = None
        self.is_interactive_mode = False
        
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

        self.interactive_btn = ttk.Button(self.main_frame, text="Bắt đầu chế độ quét tương tác", command=self.run_interactive_scan)
        self.interactive_btn.pack(fill="x", pady=5)

    def run_full_scan(self):
        self.withdraw()
        file_path = self.inspector.scan_window_to_excel()
        self.deiconify()
        self.show_scan_result(file_path)

    def run_interactive_scan(self):
        self.withdraw()
        self.show_spec_dialog()
        self.is_interactive_mode = True
        self.listener_thread = threading.Thread(target=self.keyboard_listener_thread, daemon=True)
        self.listener_thread.start()

    def keyboard_listener_thread(self):
        logging.info("Bắt đầu lắng nghe phím nóng: F7 (cha), F8 (quét), F9 (con), ESC (thoát).")
        keyboard.add_hotkey('f8', self.inspector._run_scan_at_cursor)
        keyboard.add_hotkey('f7', self.inspector._scan_parent_element)
        keyboard.add_hotkey('f9', self.inspector._scan_child_element)
        keyboard.wait('esc')
        if self.is_interactive_mode:
            self.after(0, self.stop_interactive_scan)

    def stop_interactive_scan(self):
        logging.info("Phím ESC được nhấn, thoát chế độ tương tác.")
        self.is_interactive_mode = False
        keyboard.unhook_all()
        self.hide_spec_dialog()
        self.deiconify()

    def on_closing(self):
        if self.is_interactive_mode:
            self.stop_interactive_scan()
        self.destroy()

    def show_countdown_timer(self, duration):
        countdown_win = tk.Toplevel(self)
        countdown_win.title("Đang đếm ngược")
        countdown_win.overrideredirect(True)
        countdown_win.wm_attributes("-topmost", True)
        
        style = ttk.Style(countdown_win)
        style.configure("Countdown.TLabel", font=('Segoe UI', 16, 'bold'), padding=25)
        
        label = ttk.Label(countdown_win, text=f"Bắt đầu sau {duration} giây...", style="Countdown.TLabel")
        label.pack()
        
        countdown_win.update_idletasks()
        width = countdown_win.winfo_width()
        height = countdown_win.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        countdown_win.geometry(f'{width}x{height}+{x}+{y}')
        
        for i in range(duration, 0, -1):
            label.config(text=f"Bắt đầu quét trong {i}...")
            self.update()
            time.sleep(1)
            
        countdown_win.destroy()

    def show_scan_result(self, file_path):
        result_win = tk.Toplevel(self)
        result_win.title("Kết quả quét")
        result_win.transient(self)
        result_win.grab_set()

        if file_path and os.path.exists(file_path):
            message = f"Quét thành công!\n\nKết quả đã được lưu tại:\n{file_path}"
        else:
            message = "Quét thất bại.\nVui lòng kiểm tra log để biết thêm chi tiết."
            
        label = ttk.Label(result_win, text=message, padding=20, wraplength=450, justify='center')
        label.pack(pady=10, padx=10, fill='x')
        
        button_frame = ttk.Frame(result_win)
        button_frame.pack(pady=10)

        if file_path and os.path.exists(file_path):
            open_btn = ttk.Button(button_frame, text="Mở thư mục", command=lambda: os.startfile(os.path.dirname(file_path)))
            open_btn.pack(side='left', padx=10)

        ok_btn = ttk.Button(button_frame, text="OK", command=result_win.destroy)
        ok_btn.pack(side='left', padx=10)
        
        result_win.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (result_win.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (result_win.winfo_height() // 2)
        result_win.geometry(f"+{x}+{y}")

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
            original_text = button.cget("text")
            button.config(text="Đã sao chép!")
            self.spec_dialog.after(1500, lambda: button.config(text=original_text))

        main_frame = ttk.Frame(self.spec_dialog, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1) 
        main_frame.rowconfigure(1, weight=1) 
        main_frame.rowconfigure(2, weight=1) 

        win_frame = ttk.LabelFrame(main_frame, text="Window Spec (Thông tin đầy đủ)", padding=10)
        win_frame.grid(row=0, column=0, sticky="nsew", pady=5)
        win_frame.columnconfigure(0, weight=1)
        win_frame.rowconfigure(0, weight=1)
        self.win_text = tk.Text(win_frame, wrap="word", font=("Courier New", 10))
        self.win_text.grid(row=0, column=0, sticky="nsew")
        win_copy_btn = ttk.Button(win_frame, text="Copy", style="Small.TButton", command=lambda: copy_to_clipboard(self.win_text.get("1.0", "end-1c"), win_copy_btn))
        win_copy_btn.grid(row=0, column=1, padx=5, sticky='n')

        elem_frame = ttk.LabelFrame(main_frame, text="Element Spec (Thông tin đầy đủ)", padding=10)
        elem_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        elem_frame.columnconfigure(0, weight=1)
        elem_frame.rowconfigure(0, weight=1)
        self.elem_text = tk.Text(elem_frame, wrap="word", font=("Courier New", 10))
        self.elem_text.grid(row=0, column=0, sticky="nsew")
        elem_copy_btn = ttk.Button(elem_frame, text="Copy", style="Small.TButton", command=lambda: copy_to_clipboard(self.elem_text.get("1.0", "end-1c"), elem_copy_btn))
        elem_copy_btn.grid(row=0, column=1, padx=5, sticky='n')
        
        quick_frame = ttk.LabelFrame(main_frame, text="Quick Spec (Gợi ý để copy nhanh)", padding=10)
        quick_frame.grid(row=2, column=0, sticky="nsew", pady=5)
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
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = InspectorApp()
    app.mainloop()
