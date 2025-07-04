# Elements/spec_tester.py
# Phiên bản 5.0: Khôi phục và cải tiến log gỡ lỗi chi tiết cho từng bộ lọc.
# Công cụ gỡ lỗi (debugger) độc lập để kiểm tra và trực quan hóa các bộ chọn.

import tkinter as tk
from tkinter import ttk, scrolledtext, font
import threading
import ast # Để phân tích chuỗi thành dictionary một cách an toàn

try:
    from pywinauto import Desktop
    from pywinauto.findwindows import ElementNotFoundError
    import psutil
    import win32gui
    import win32process
    import win32con
    import re
    from datetime import datetime
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    print("Gợi ý: pip install pywinauto psutil")
    exit()

# ======================================================================
#                      ĐỊNH NGHĨA CÁC THUỘC TÍNH (Đầy đủ và rõ nghĩa hơn)
# ======================================================================
PARAMETER_DEFINITIONS = {
    # PWA Properties
    "pwa_title": "Tên/văn bản hiển thị của element (quan trọng nhất).", "pwa_auto_id": "Automation ID, một ID duy nhất để xác định element trong ứng dụng.",
    "pwa_control_type": "Loại control của element (ví dụ: Button, Edit, Tree).", "pwa_class_name": "Tên lớp Win32 của element (hữu ích cho các app cũ).",
    "pwa_framework_id": "Framework tạo ra element (ví dụ: UIA, Win32, WPF).", 
    # WIN32 Properties
    "win32_handle": "Handle (ID duy nhất) của cửa sổ do Windows quản lý.",
    "win32_styles": "Các cờ kiểu dáng của cửa sổ (dạng hexa).", "win32_extended_styles": "Các cờ kiểu dáng mở rộng của cửa sổ (dạng hexa).",
    # State Properties
    "state_is_visible": "Trạng thái hiển thị (True nếu đang hiển thị).", "state_is_enabled": "Trạng thái cho phép tương tác (True nếu được kích hoạt).",
    "state_is_active": "Trạng thái hoạt động (True nếu là cửa sổ/element đang được focus).", "state_is_minimized": "Trạng thái thu nhỏ (True nếu cửa sổ đang bị thu nhỏ).",
    "state_is_maximized": "Trạng thái phóng to (True nếu cửa sổ đang được phóng to).", "state_is_focusable": "Trạng thái có thể nhận focus bàn phím.",
    "state_is_password": "Trạng thái là ô nhập mật khẩu.", "state_is_offscreen": "Trạng thái nằm ngoài màn hình hiển thị.",
    "state_is_content_element": "Là element chứa nội dung chính, không phải control trang trí.", "state_is_control_element": "Là element có thể tương tác (ngược với content).",
    # Geometry Properties
    "geo_rectangle_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của cửa sổ.", "geo_bounding_rect_tuple": "Tuple tọa độ (Left, Top, Right, Bottom) của element.",
    "geo_center_point": "Tọa độ điểm trung tâm của element.", 
    # Process Properties
    "proc_pid": "Process ID (ID của tiến trình sở hữu cửa sổ).",
    "proc_thread_id": "Thread ID (ID của luồng sở hữu cửa sổ).", "proc_name": "Tên của tiến trình (ví dụ: 'notepad.exe').",
    "proc_path": "Đường dẫn đầy đủ đến file thực thi của tiến trình.", "proc_cmdline": "Dòng lệnh đã dùng để khởi chạy tiến trình.",
    "proc_create_time": "Thời gian tiến trình được tạo (dạng timestamp hoặc chuỗi).", "proc_username": "Tên người dùng đã khởi chạy tiến trình.",
    # Relational Properties
    "rel_level": "Cấp độ sâu của element trong cây giao diện (0 là root).", "rel_parent_handle": "Handle của cửa sổ cha (nếu có, 0 là Desktop).",
    "rel_parent_title": "Tên/tiêu đề của element cha.", "rel_labeled_by": "Tên của element nhãn (label) liên kết với element này.",
    "rel_child_count": "Số lượng element con trực tiếp.", 
    # UIA Pattern Properties
    "uia_value": "Giá trị của element nếu hỗ trợ ValuePattern.", 
    "uia_toggle_state": "Trạng thái của element nếu hỗ trợ TogglePattern (On, Off, Indeterminate).",
    # Sorting / Selector Keys
    "sort_by_creation_time": "Sắp xếp theo thời gian tạo. Dùng số dương (1, 2,...) cho cũ nhất, số âm (-1, -2,...) cho mới nhất.",
    "sort_by_title_length": "Sắp xếp theo độ dài tiêu đề. Dùng số dương (1, 2,...) cho ngắn nhất, số âm (-1, -2,...) cho dài nhất.",
    "sort_by_child_count": "Sắp xếp theo số lượng element con. Dùng số dương (1, 2,...) cho ít con nhất, số âm (-1, -2,...) cho nhiều con nhất.",
    "sort_by_y_pos": "Sắp xếp theo vị trí trục Y (từ trên xuống). Dùng số dương (1, 2,...) cho đối tượng ở trên cùng.",
    "sort_by_x_pos": "Sắp xếp theo vị trí trục X (từ trái sang). Dùng số dương (1, 2,...) cho đối tượng bên trái nhất.",
    "sort_by_width": "Sắp xếp theo chiều rộng. Dùng số dương (1, 2,...) cho hẹp nhất, số âm (-1, -2,...) cho rộng nhất.",
    "sort_by_height": "Sắp xếp theo chiều cao. Dùng số dương (1, 2,...) cho thấp nhất, số âm (-1, -2,...) cho cao nhất.",
    "z_order_index": "Chọn đối tượng theo thứ tự Z (độ sâu). Hiếm dùng. Giá trị là index (0, 1, ...).",
}

# ======================================================================
#                      LỚP CHÍNH CỦA ỨNG DỤNG
# ======================================================================
class SpecTesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Selector Debugger v5.0")
        self.geometry("850x750")

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TLabel", font=('Segoe UI', 10))
        style.configure("TButton", font=('Segoe UI', 10, 'bold'), padding=5)
        style.configure("TLabelframe.Label", font=('Segoe UI', 11, 'bold'))
        style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'))

        self.highlighter = None
        self.test_thread = None
        self.debugger = SelectorDebugger(self.log_message)
        
        self.create_widgets()

    def create_widgets(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        debugger_tab, properties_tab = ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(debugger_tab, text="Debugger"); notebook.add(properties_tab, text="Thuộc tính hỗ trợ")
        self.create_debugger_tab(debugger_tab); self.create_properties_tab(properties_tab)

    def create_debugger_tab(self, parent):
        parent.rowconfigure(2, weight=1); parent.columnconfigure(0, weight=1)
        input_frame = ttk.Frame(parent); input_frame.grid(row=0, column=0, sticky="ew", pady=5); input_frame.columnconfigure(1, weight=1)
        ttk.Label(input_frame, text="Window Spec:").grid(row=0, column=0, sticky="nw", padx=5)
        self.window_spec_text = tk.Text(input_frame, height=5, font=("Courier New", 10)); self.window_spec_text.grid(row=0, column=1, sticky="ew")
        self.window_spec_text.insert("1.0", "{'pwa_class_name': 'Notepad', 'sort_by_creation_time': -1}")
        ttk.Label(input_frame, text="Element Spec:").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self.element_spec_text = tk.Text(input_frame, height=5, font=("Courier New", 10)); self.element_spec_text.grid(row=1, column=1, sticky="ew", pady=5)
        self.element_spec_text.insert("1.0", "{'pwa_control_type': 'Document'}")
        button_frame = ttk.Frame(parent); button_frame.grid(row=1, column=0, pady=10)
        self.run_button = ttk.Button(button_frame, text="🔎 Chạy gỡ lỗi (Debug)", command=self.run_test); self.run_button.pack(side="left", padx=10)
        self.clear_button = ttk.Button(button_frame, text="✨ Xóa Log", command=self.clear_log); self.clear_button.pack(side="left", padx=10)
        log_frame = ttk.LabelFrame(parent, text="Báo cáo chi tiết"); log_frame.grid(row=2, column=0, sticky="nsew"); log_frame.rowconfigure(0, weight=1); log_frame.columnconfigure(0, weight=1)
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap="word", font=("Consolas", 10), state="disabled", bg="#2B2B2B"); self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_area.tag_config('INFO', foreground='#87CEEB'); self.log_area.tag_config('DEBUG', foreground='#D3D3D3')
        self.log_area.tag_config('FILTER', foreground='#FFD700'); self.log_area.tag_config('SUCCESS', foreground='#90EE90')
        self.log_area.tag_config('ERROR', foreground='#F08080'); self.log_area.tag_config('HEADER', foreground='#FFFFFF', font=("Consolas", 11, "bold", "underline"))

    def create_properties_tab(self, parent):
        tree_frame = ttk.Frame(parent, padding=10); tree_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_frame, columns=("Property", "Description"), show="headings"); tree.heading("Property", text="Tên thuộc tính"); tree.heading("Description", text="Ý nghĩa")
        tree.column("Property", width=250, anchor='w'); tree.column("Description", width=500, anchor='w')
        categories = {
            "Lọc (Filter) - PWA": self.debugger.PWA_PROPS, "Lọc (Filter) - WIN32": self.debugger.WIN32_PROPS, "Lọc (Filter) - State": self.debugger.STATE_PROPS, "Lọc (Filter) - Geometry": self.debugger.GEO_PROPS,
            "Lọc (Filter) - Process": self.debugger.PROC_PROPS, "Lọc (Filter) - Relational": self.debugger.REL_PROPS, "Lọc (Filter) - UIA Patterns": self.debugger.UIA_PROPS, 
            "Sắp xếp & Lựa chọn (Selectors)": self.debugger.SORTING_KEYS,
        }
        for category_name, prop_set in categories.items():
            category_id = tree.insert("", "end", values=(f"--- {category_name} ---", ""), tags=('category',))
            for prop in sorted(list(prop_set)):
                tree.insert(category_id, "end", values=(prop, PARAMETER_DEFINITIONS.get(prop, "")))
        tree.tag_configure('category', background='#3E4145', font=('Segoe UI', 10, 'bold')); tree.pack(fill="both", expand=True)

    def log_message(self, level, message):
        self.log_area.config(state="normal"); self.log_area.insert(tk.END, f"[{level}] {message}\n", level); self.log_area.config(state="disabled"); self.log_area.see(tk.END)
    def clear_log(self):
        self.log_area.config(state="normal"); self.log_area.delete("1.0", tk.END); self.log_area.config(state="disabled")

    def run_test(self):
        self.clear_log(); self.run_button.config(state="disabled")
        try:
            win_spec = ast.literal_eval(self.window_spec_text.get("1.0", "end-1c") or '{}')
            elem_spec = ast.literal_eval(self.element_spec_text.get("1.0", "end-1c") or '{}')
            if not isinstance(win_spec, dict) or not isinstance(elem_spec, dict): raise ValueError("Spec phải là dictionary.")
        except (ValueError, SyntaxError) as e:
            self.log_message('ERROR', f"Lỗi cú pháp trong spec: {e}"); self.run_button.config(state="normal"); return
        self.test_thread = threading.Thread(target=self.debugger.run_debug_session, args=(win_spec, elem_spec, self.on_test_complete), daemon=True); self.test_thread.start()

    def on_test_complete(self, result_element):
        self.run_button.config(state="normal");
        if result_element: self.highlight_element(result_element)

    def highlight_element(self, element):
        if self.highlighter: self.highlighter.destroy()
        rect = element.rectangle(); self.highlighter = tk.Toplevel(self); self.highlighter.overrideredirect(True)
        self.highlighter.wm_attributes("-topmost", True, "-disabled", True, "-transparentcolor", "white")
        self.highlighter.geometry(f'{rect.width()}x{rect.height()}+{rect.left}+{rect.top}')
        canvas = tk.Canvas(self.highlighter, bg='white', highlightthickness=0); canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(2, 2, rect.width()-2, rect.height()-2, outline="red", width=4); self.highlighter.after(2500, self.highlighter.destroy)

# ======================================================================
#                      LỚP LOGIC GỠ LỖI (Nâng cấp)
# ======================================================================
class SelectorDebugger:
    def __init__(self, log_callback):
        self.log = log_callback; self.desktop = Desktop(backend='uia'); self._proc_info_cache = {}

    PWA_PROPS = {"pwa_title", "pwa_auto_id", "pwa_control_type", "pwa_class_name", "pwa_framework_id"}
    WIN32_PROPS = {"win32_handle", "win32_styles", "win32_extended_styles"}
    STATE_PROPS = {"state_is_visible", "state_is_enabled", "state_is_active", "state_is_minimized", "state_is_maximized", "state_is_focusable", "state_is_password", "state_is_offscreen", "state_is_content_element", "state_is_control_element"}
    GEO_PROPS = {"geo_rectangle_tuple", "geo_bounding_rect_tuple", "geo_center_point"}
    PROC_PROPS = {"proc_pid", "proc_thread_id", "proc_name", "proc_path", "proc_cmdline", "proc_create_time", "proc_username"}
    REL_PROPS = {"rel_level", "rel_parent_handle", "rel_parent_title", "rel_labeled_by", "rel_child_count"}
    UIA_PROPS = {"uia_value", "uia_toggle_state"}
    SUPPORTED_KEYS = PWA_PROPS | WIN32_PROPS | STATE_PROPS | GEO_PROPS | PROC_PROPS | REL_PROPS | UIA_PROPS
    SORTING_KEYS = {'sort_by_creation_time', 'sort_by_title_length', 'sort_by_child_count', 'sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height', 'z_order_index'}
    STRING_OPERATORS = {'equals', 'iequals', 'contains', 'icontains', 'in', 'regex', 'not_equals', 'not_iequals', 'not_contains', 'not_icontains'}
    NUMERIC_OPERATORS = {'>', '>=', '<', '<='}; VALID_OPERATORS = STRING_OPERATORS.union(NUMERIC_OPERATORS)

    def run_debug_session(self, window_spec, element_spec, on_complete_callback):
        self.log('HEADER', "--- BẮT ĐẦU PHIÊN GỠ LỖI ---"); found_element = None
        try:
            target_window = self._debug_find_one(self.desktop.windows, window_spec, "Cửa sổ")
            if target_window and element_spec: found_element = self._debug_find_one(target_window.descendants, element_spec, "Element")
            elif target_window: found_element = target_window
        except Exception as e: self.log('ERROR', f"Đã xảy ra lỗi không mong muốn: {e}")
        self.log('HEADER', "--- KẾT THÚC PHIÊN GỠ LỖI ---"); on_complete_callback(found_element)

    def _debug_find_one(self, search_func, spec, search_type):
        self.log('INFO', f"Bắt đầu tìm kiếm đối tượng: '{search_type}'"); candidates = search_func()
        self.log('DEBUG', f"Tìm thấy tổng cộng {len(candidates)} ứng viên '{search_type}' ban đầu.")
        if not candidates: self.log('ERROR', f"Không tìm thấy bất kỳ ứng viên '{search_type}' nào."); return None
        filter_spec = {k: v for k, v in spec.items() if k not in self.SORTING_KEYS}; selector_spec = {k: v for k, v in spec.items() if k in self.SORTING_KEYS}
        if filter_spec:
            self.log('INFO', f"Áp dụng bộ lọc (filters) cho {len(candidates)} ứng viên..."); candidates = self._apply_filters_debug(candidates, filter_spec)
            if not candidates: self.log('ERROR', f"Không còn ứng viên nào sau khi lọc."); return None
            self.log('SUCCESS', f"Còn lại {len(candidates)} ứng viên sau khi lọc.")
        if selector_spec:
            self.log('INFO', f"Áp dụng bộ chọn (selectors) cho {len(candidates)} ứng viên..."); candidates = self._apply_selectors_debug(candidates, selector_spec)
            if not candidates: self.log('ERROR', f"Không còn ứng viên nào sau khi chọn."); return None
        if len(candidates) == 1: self.log('SUCCESS', f"Tìm thấy ĐÚNG 1 đối tượng '{search_type}'!"); self._log_element_details(candidates[0]); return candidates[0]
        elif len(candidates) > 1: self.log('ERROR', f"Tìm thấy {len(candidates)} đối tượng không rõ ràng."); [self.log('DEBUG', f"  #{i+1}: '{e.window_text()}'") for i, e in enumerate(candidates[:5])]
        else: self.log('ERROR', f"Không tìm thấy đối tượng '{search_type}' nào phù hợp.")
        return None

    def _apply_filters_debug(self, elements, spec):
        current_elements = list(elements)
        for key, criteria in spec.items():
            self.log('FILTER', f"Lọc theo: {{'{key}': {repr(criteria)}}}")
            
            initial_count = len(current_elements)
            kept_elements = []
            log_limit = 50 
            logged_count = 0

            for elem in current_elements:
                actual_value = self._get_actual_value(elem, key)
                matches = self._check_condition(actual_value, criteria)
                
                if logged_count < log_limit:
                    status = "[GIỮ LẠI]" if matches else "[LOẠI BỎ]"
                    reason = "khớp" if matches else "không khớp"
                    self.log('DEBUG', f"  {status} '{elem.window_text()}' vì '{key}' có giá trị '{actual_value}' {reason}.")
                    logged_count += 1
                
                if matches:
                    kept_elements.append(elem)

            if logged_count >= log_limit and initial_count > log_limit:
                 self.log('DEBUG', f"  ... và {initial_count - log_limit} ứng viên khác được xử lý (log chi tiết đã được giới hạn).")

            self.log('INFO', f"  -> Kết quả: Giữ lại {len(kept_elements)}/{initial_count} ứng viên.")
            
            if not kept_elements:
                self.log('ERROR', f"Bộ lọc này đã loại bỏ tất cả ứng viên.");
                return []
            
            current_elements = kept_elements
        return current_elements

    def _apply_selectors_debug(self, candidates, selectors):
        sorted_candidates = list(candidates)
        for key, index in selectors.items():
            if key == 'z_order_index': continue
            self.log('FILTER', f"Sắp xếp theo: '{key}' (Thứ tự: {'Giảm dần' if index < 0 else 'Tăng dần'})")
            sort_key_func = self._get_sort_key_function(key)
            if sort_key_func: sorted_candidates.sort(key=sort_key_func, reverse=(index < 0))
        final_index = selectors.get('z_order_index', list(selectors.values())[-1] if selectors else 0)
        if final_index > 0: final_index -= 1
        self.log('FILTER', f"Chọn phần tử tại index: {final_index}")
        try: return [sorted_candidates[final_index]]
        except IndexError: self.log('ERROR', f"Index={final_index} nằm ngoài phạm vi."); return []
            
    def _log_element_details(self, element):
        self.log('DEBUG', "--- Chi tiết đối tượng được tìm thấy ---")
        for prop in sorted(list(self.SUPPORTED_KEYS)):
            val = self._get_actual_value(element, prop)
            if val or isinstance(val, (bool, int)): self.log('DEBUG', f"  - {prop}: {val}")
        self.log('DEBUG', "------------------------------------")

    def _get_process_info(self, pid):
        if pid in self._proc_info_cache: return self._proc_info_cache[pid]
        if pid > 0:
            try:
                p = psutil.Process(pid); info = {'proc_name': p.name(), 'proc_path': p.exe(), 'proc_cmdline': ' '.join(p.cmdline()), 'proc_create_time': datetime.fromtimestamp(p.create_time()), 'proc_username': p.username()}; self._proc_info_cache[pid] = info; return info
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        return {}

    def _get_actual_value(self, element, key):
        prop = key.lower()
        try:
            if prop in self.PWA_PROPS:
                if prop == 'pwa_title': return element.window_text()
                if prop == 'pwa_class_name': return element.class_name()
                if prop == 'pwa_auto_id': return element.automation_id()
                if prop == 'pwa_control_type': return element.control_type
                if prop == 'pwa_framework_id': return element.framework_id()
            if prop in self.WIN32_PROPS:
                handle = element.handle
                if not handle: return None
                if prop == 'win32_handle': return handle
                if prop == 'win32_styles': return win32gui.GetWindowLong(handle, win32con.GWL_STYLE)
                if prop == 'win32_extended_styles': return win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)
            if prop in self.STATE_PROPS:
                if prop == 'state_is_visible': return element.is_visible()
                if prop == 'state_is_enabled': return element.is_enabled()
                if prop == 'state_is_active': return element.is_active()
                if prop == 'state_is_minimized': return element.is_minimized()
                if prop == 'state_is_maximized': return element.is_maximized()
                if prop == 'state_is_focusable': return element.is_focusable()
                if prop == 'state_is_password': return element.is_password()
                if prop == 'state_is_offscreen': return element.is_offscreen()
                if prop == 'state_is_content_element': return element.is_content_element()
                if prop == 'state_is_control_element': return element.is_control_element()
            if prop in self.GEO_PROPS:
                rect = element.rectangle();
                if prop == 'geo_bounding_rect_tuple': return (rect.left, rect.top, rect.right, rect.bottom)
                if prop == 'geo_center_point': return rect.mid_point()
            if prop in self.PROC_PROPS:
                pid = element.process_id()
                if prop == 'proc_pid': return pid
                if prop == 'proc_thread_id': return win32process.GetWindowThreadProcessId(element.handle)[0] if element.handle else None
                proc_info = self._get_process_info(pid); return proc_info.get(prop.replace('proc_',''))
            if prop in self.REL_PROPS:
                if prop == 'rel_child_count': return len(element.children())
                if prop == 'rel_parent_handle': return win32gui.GetParent(element.handle) if element.handle else None
                if prop == 'rel_parent_title': return element.parent().window_text() if element.parent() else ''
                if prop == 'rel_labeled_by': return element.labeled_by() if hasattr(element, 'labeled_by') else ''
                if prop == 'rel_level':
                    level = 0; current = element
                    while current.parent(): level += 1; current = current.parent()
                    return level
            if prop in self.UIA_PROPS:
                if prop == 'uia_value': return element.get_value() if element.has_value() else None
                if prop == 'uia_toggle_state': return element.get_toggle_state() if element.has_toggle() else None
            if key in ['sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height']:
                rect = element.rectangle();
                if not rect: return 0
                if key == 'sort_by_y_pos': return rect.top
                if key == 'sort_by_x_pos': return rect.left
                if key == 'sort_by_width': return rect.width()
                if key == 'sort_by_height': return rect.height()
            return None
        except Exception: return None

    def _check_condition(self, actual_value, criteria):
        if not isinstance(criteria, tuple): return actual_value == criteria
        if len(criteria) != 2: return False
        op, target = str(criteria[0]).lower(), criteria[1]
        if op not in self.VALID_OPERATORS or actual_value is None: return False
        str_actual = str(actual_value)
        if op in self.STRING_OPERATORS:
            if op == 'equals': return str_actual == target
            if op == 'iequals': return str_actual.lower() == str(target).lower()
            if op == 'contains': return str(target) in str_actual
            if op == 'icontains': return str(target).lower() in str_actual.lower()
            if op == 'regex': return re.search(str(target), str_actual) is not None
        if op in self.NUMERIC_OPERATORS:
            try:
                num_actual, num_target = float(actual_value), float(target)
                if op == '>': return num_actual > num_target
                if op == '>=': return num_actual >= num_target
                if op == '<': return num_actual < num_target
                if op == '<=': return num_actual <= num_target
            except (ValueError, TypeError): return False
        return False

    def _get_sort_key_function(self, key):
        if key == 'sort_by_creation_time': return lambda e: self._get_actual_value(e, 'proc_create_time') or datetime.min
        if key == 'sort_by_title_length': return lambda e: len(self._get_actual_value(e, 'pwa_title') or '')
        if key == 'sort_by_child_count': return lambda e: self._get_actual_value(e, 'rel_child_count') or 0
        if key in ['sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height']: return lambda e: self._get_actual_value(e, key) or 0
        return None

if __name__ == "__main__":
    app = SpecTesterApp()
    app.mainloop()
