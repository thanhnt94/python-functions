# Elements/spec_tester.py
# Phiên bản 9.1: Sửa lỗi import để có thể chạy trực tiếp.
# Công cụ gỡ lỗi (debugger) độc lập để kiểm tra và trực quan hóa các bộ chọn.

import tkinter as tk
from tkinter import ttk, scrolledtext, font
import threading
import ast # Để phân tích chuỗi thành dictionary một cách an toàn
import re
from datetime import datetime

try:
    from pywinauto import Desktop
    from pywinauto.findwindows import ElementNotFoundError
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    print("Gợi ý: pip install pywinauto comtypes")
    exit()

# --- Import các thành phần dùng chung (Đã sửa lỗi) ---
try:
    # Cách import này dùng khi chạy file như một phần của package lớn hơn
    from . import ui_shared_logic
except ImportError:
    # Cách import này dùng khi chạy file spec_tester.py trực tiếp
    import ui_shared_logic

# ======================================================================
#                      LỚP CHÍNH CỦA ỨNG DỤNG
# ======================================================================
class SpecTesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Selector Debugger v9.1 (Synced)")
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
        notebook.add(debugger_tab, text="Debugger")
        notebook.add(properties_tab, text="Thuộc tính hỗ trợ")
        self.create_debugger_tab(debugger_tab)
        self.create_properties_tab(properties_tab)

    def create_debugger_tab(self, parent):
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        input_frame = ttk.Frame(parent)
        input_frame.grid(row=0, column=0, sticky="ew", pady=5)
        input_frame.columnconfigure(1, weight=1)
        ttk.Label(input_frame, text="Window Spec:").grid(row=0, column=0, sticky="nw", padx=5)
        self.window_spec_text = tk.Text(input_frame, height=5, font=("Courier New", 10))
        self.window_spec_text.grid(row=0, column=1, sticky="ew")
        self.window_spec_text.insert("1.0", """window_spec = {
    'proc_name': 'explorer.exe',
    'pwa_class_name': ('icontains', 'CabinetWClass')
}""")
        ttk.Label(input_frame, text="Element Spec:").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self.element_spec_text = tk.Text(input_frame, height=5, font=("Courier New", 10))
        self.element_spec_text.grid(row=1, column=1, sticky="ew", pady=5)
        self.element_spec_text.insert("1.0", "")
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=1, column=0, pady=10)
        self.run_button = ttk.Button(button_frame, text="🔎 Chạy gỡ lỗi (Debug)", command=self.run_test)
        self.run_button.pack(side="left", padx=10)
        self.clear_button = ttk.Button(button_frame, text="✨ Xóa Log", command=self.clear_log)
        self.clear_button.pack(side="left", padx=10)
        log_frame = ttk.LabelFrame(parent, text="Báo cáo chi tiết")
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap="word", font=("Consolas", 10), state="disabled", bg="#2B2B2B")
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Cấu hình màu sắc cho log
        self.log_area.tag_config('INFO', foreground='#87CEEB')
        self.log_area.tag_config('DEBUG', foreground='#D3D3D3')
        self.log_area.tag_config('FILTER', foreground='#FFD700')
        self.log_area.tag_config('SUCCESS', foreground='#90EE90')
        self.log_area.tag_config('ERROR', foreground='#F08080')
        self.log_area.tag_config('HEADER', foreground='#FFFFFF', font=("Consolas", 11, "bold", "underline"))
        self.log_area.tag_config('KEEP', foreground='#76D7C4', font=("Consolas", 10, "bold"))
        self.log_area.tag_config('DISCARD', foreground='#E59866', font=("Consolas", 10, "bold"))

    def create_properties_tab(self, parent):
        tree_frame = ttk.Frame(parent, padding=10)
        tree_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_frame, columns=("Property", "Description"), show="headings")
        tree.heading("Property", text="Tên thuộc tính")
        tree.heading("Description", text="Ý nghĩa")
        tree.column("Property", width=250, anchor='w')
        tree.column("Description", width=500, anchor='w')
        
        categories = {
            "Lọc (Filter) - PWA": ui_shared_logic.PWA_PROPS,
            "Lọc (Filter) - WIN32": ui_shared_logic.WIN32_PROPS,
            "Lọc (Filter) - State": ui_shared_logic.STATE_PROPS,
            "Lọc (Filter) - Geometry": ui_shared_logic.GEO_PROPS,
            "Lọc (Filter) - Process": ui_shared_logic.PROC_PROPS,
            "Lọc (Filter) - Relational": ui_shared_logic.REL_PROPS,
            "Lọc (Filter) - UIA Patterns": ui_shared_logic.UIA_PROPS,
            "Sắp xếp & Lựa chọn (Selectors)": self.debugger.SORTING_KEYS,
        }
        for category_name, prop_set in categories.items():
            category_id = tree.insert("", "end", values=(f"--- {category_name} ---", ""), tags=('category',))
            for prop in sorted(list(prop_set)):
                description = ui_shared_logic.PARAMETER_DEFINITIONS.get(prop, "")
                tree.insert(category_id, "end", values=(prop, description))
        tree.tag_configure('category', background='#3E4145', font=('Segoe UI', 10, 'bold'))
        tree.pack(fill="both", expand=True)

    def log_message(self, level, message):
        self.log_area.config(state="normal")
        if isinstance(message, list):
            self.log_area.insert(tk.END, f"[{level}] ")
            for text, tag in message:
                self.log_area.insert(tk.END, text, tag)
            self.log_area.insert(tk.END, "\n")
        else:
            self.log_area.insert(tk.END, f"[{level}] {message}\n", level)
        self.log_area.config(state="disabled")
        self.log_area.see(tk.END)

    def clear_log(self):
        self.log_area.config(state="normal")
        self.log_area.delete("1.0", tk.END)
        self.log_area.config(state="disabled")

    def _extract_and_parse_spec(self, spec_string):
        spec_string = spec_string.strip()
        if not spec_string: return {}
        start_brace = spec_string.find('{')
        if start_brace == -1: raise ValueError("Không tìm thấy ký tự '{' để bắt đầu dictionary.")
        dict_str = spec_string[start_brace:]
        try:
            parsed_dict = ast.literal_eval(dict_str)
            if isinstance(parsed_dict, dict): return parsed_dict
            else: raise ValueError("Nội dung phân tích được không phải là một dictionary.")
        except (ValueError, SyntaxError) as e: raise ValueError(f"Không thể phân tích spec. Lỗi: {e}")

    def run_test(self):
        self.clear_log()
        self.run_button.config(state="disabled")
        try:
            win_spec = self._extract_and_parse_spec(self.window_spec_text.get("1.0", "end-1c"))
            elem_spec = self._extract_and_parse_spec(self.element_spec_text.get("1.0", "end-1c"))
        except ValueError as e:
            self.log_message('ERROR', f"Lỗi cú pháp trong spec: {e}")
            self.run_button.config(state="normal")
            return
        self.test_thread = threading.Thread(target=self.debugger.run_debug_session, args=(win_spec, elem_spec, self.on_test_complete), daemon=True)
        self.test_thread.start()

    def on_test_complete(self, result_element):
        self.run_button.config(state="normal")
        if result_element:
            self.highlight_element(result_element)

    def highlight_element(self, element):
        if self.highlighter: self.highlighter.destroy()
        rect = element.rectangle()
        self.highlighter = tk.Toplevel(self)
        self.highlighter.overrideredirect(True)
        self.highlighter.wm_attributes("-topmost", True, "-disabled", True, "-transparentcolor", "white")
        self.highlighter.geometry(f'{rect.width()}x{rect.height()}+{rect.left}+{rect.top}')
        canvas = tk.Canvas(self.highlighter, bg='white', highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(2, 2, rect.width()-2, rect.height()-2, outline="red", width=4)
        self.highlighter.after(2500, self.highlighter.destroy)

# ======================================================================
#                      LỚP LOGIC GỠ LỖI (Đã tái cấu trúc)
# ======================================================================
class SelectorDebugger:
    def __init__(self, log_callback):
        self.log = log_callback
        self.desktop = Desktop(backend='uia')
        
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.log('ERROR', f"Lỗi nghiêm trọng khi khởi tạo COM: {e}")
            raise

    SUPPORTED_KEYS = ui_shared_logic.SUPPORTED_FILTER_KEYS
    SORTING_KEYS = {'sort_by_creation_time', 'sort_by_title_length', 'sort_by_child_count', 'sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height', 'z_order_index'}
    
    STRING_OPERATORS = {'equals', 'iequals', 'contains', 'icontains', 'in', 'regex', 'not_equals', 'not_iequals', 'not_contains', 'not_icontains'}
    NUMERIC_OPERATORS = {'>', '>=', '<', '<='}
    VALID_OPERATORS = STRING_OPERATORS.union(NUMERIC_OPERATORS)

    def run_debug_session(self, window_spec, element_spec, on_complete_callback):
        self.log('HEADER', "--- BẮT ĐẦU PHIÊN GỠ LỖI ---")
        found_element = None
        try:
            target_window = self._debug_find_one(self.desktop.windows, window_spec, "Cửa sổ")
            if target_window and element_spec:
                found_element = self._debug_find_one(target_window.descendants, element_spec, "Element")
            elif target_window:
                found_element = target_window
        except Exception as e:
            self.log('ERROR', f"Đã xảy ra lỗi không mong muốn: {e}")
        self.log('HEADER', "--- KẾT THÚC PHIÊN GỠ LỖI ---")
        on_complete_callback(found_element)

    def _debug_find_one(self, search_func, spec, search_type):
        self.log('INFO', f"Bắt đầu tìm kiếm đối tượng: '{search_type}'")
        candidates = search_func()
        self.log('DEBUG', f"Tìm thấy tổng cộng {len(candidates)} ứng viên '{search_type}' ban đầu.")
        if not candidates:
            self.log('ERROR', f"Không tìm thấy bất kỳ ứng viên '{search_type}' nào.")
            return None
            
        filter_spec = {k: v for k, v in spec.items() if k not in self.SORTING_KEYS}
        selector_spec = {k: v for k, v in spec.items() if k in self.SORTING_KEYS}
        
        if filter_spec:
            self.log('INFO', f"Áp dụng bộ lọc (filters) cho {len(candidates)} ứng viên...")
            candidates = self._apply_filters_debug(candidates, filter_spec)
            if not candidates:
                self.log('ERROR', f"Không còn ứng viên nào sau khi lọc.")
                return None
            self.log('SUCCESS', f"Còn lại {len(candidates)} ứng viên sau khi lọc.")
            
        if selector_spec:
            self.log('INFO', f"Áp dụng bộ chọn (selectors) cho {len(candidates)} ứng viên...")
            candidates = self._apply_selectors_debug(candidates, selector_spec)
            if not candidates:
                self.log('ERROR', f"Không còn ứng viên nào sau khi chọn.")
                return None
                
        if len(candidates) == 1:
            self.log('SUCCESS', f"Tìm thấy ĐÚNG 1 đối tượng '{search_type}'!")
            self._log_element_details(candidates[0])
            return candidates[0]
        elif len(candidates) > 1:
            self.log('ERROR', f"Tìm thấy {len(candidates)} đối tượng không rõ ràng.")
            [self.log('DEBUG', f"  #{i+1}: '{e.window_text()}'") for i, e in enumerate(candidates[:5])]
        else:
            self.log('ERROR', f"Không tìm thấy đối tượng '{search_type}' nào phù hợp.")
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
                    if matches:
                        log_parts = [("  [GIỮ LẠI] ", 'KEEP'), (f"'{elem.window_text()}' vì '{key}' có giá trị '{actual_value}' khớp.", 'DEBUG')]
                    else:
                        log_parts = [("  [LOẠI BỎ] ", 'DISCARD'), (f"'{elem.window_text()}' vì '{key}' có giá trị '{actual_value}' không khớp.", 'DEBUG')]
                    self.log('DEBUG', log_parts)
                    logged_count += 1
                if matches:
                    kept_elements.append(elem)
            if logged_count >= log_limit and initial_count > log_limit:
                self.log('DEBUG', f"  ... và {initial_count - log_limit} ứng viên khác được xử lý.")
            self.log('INFO', f"  -> Kết quả: Giữ lại {len(kept_elements)}/{initial_count} ứng viên.")
            if not kept_elements:
                self.log('ERROR', f"Bộ lọc này đã loại bỏ tất cả ứng viên.")
                return []
            current_elements = kept_elements
        return current_elements

    def _apply_selectors_debug(self, candidates, selectors):
        sorted_candidates = list(candidates)
        for key, index in selectors.items():
            if key == 'z_order_index': continue
            self.log('FILTER', f"Sắp xếp theo: '{key}' (Thứ tự: {'Giảm dần' if index < 0 else 'Tăng dần'})")
            sort_key_func = self._get_sort_key_function(key)
            if sort_key_func:
                sorted_candidates.sort(key=sort_key_func, reverse=(index < 0))
        final_index = selectors.get('z_order_index', list(selectors.values())[-1] if selectors else 0)
        if final_index > 0:
            final_index -= 1
        self.log('FILTER', f"Chọn phần tử tại index: {final_index}")
        try:
            return [sorted_candidates[final_index]]
        except IndexError:
            self.log('ERROR', f"Index={final_index} nằm ngoài phạm vi.")
            return []
            
    def _log_element_details(self, element):
        self.log('DEBUG', "--- Chi tiết đối tượng được tìm thấy ---")
        for prop in sorted(list(self.SUPPORTED_KEYS)):
            val = self._get_actual_value(element, prop)
            if val or isinstance(val, (bool, int)):
                self.log('DEBUG', f"  - {prop}: {val}")
        self.log('DEBUG', "------------------------------------")

    def _get_actual_value(self, element, key):
        return ui_shared_logic.get_property_value(
            pwa_element=element,
            key=key,
            uia_instance=self.uia,
            tree_walker=self.tree_walker
        )

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
        if key in ['sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height']:
            def get_rect_prop(elem, prop_key):
                rect = self._get_actual_value(elem, 'geo_bounding_rect_tuple')
                if not rect: return 0
                if prop_key == 'sort_by_y_pos': return rect[1]
                if prop_key == 'sort_by_x_pos': return rect[0]
                if prop_key == 'sort_by_width': return rect[2] - rect[0]
                if prop_key == 'sort_by_height': return rect[3] - rect[1]
            return lambda e: get_rect_prop(e, key)
        return None

if __name__ == "__main__":
    app = SpecTesterApp()
    app.mainloop()
