# tool_explorer.py
# A standalone and embeddable tool for full window element scanning.
# Refactored to be a modular component that can be imported.

import logging
import re
import time
import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font, filedialog, messagebox

# --- Required Libraries ---
try:
    import pandas as pd
    import comtypes
    import comtypes.client
    from comtypes.gen import UIAutomationClient as UIA
    from pywinauto import Desktop
    from pywinauto.uia_element_info import UIAElementInfo
    from pywinauto.controls.uiawrapper import UIAWrapper
except ImportError as e:
    print(f"Error importing libraries: {e}")
    sys.exit(1)

# --- Shared Logic Import ---
try:
    import core_logic
except ImportError:
    print("CRITICAL ERROR: 'core_logic.py' must be in the same directory.")
    sys.exit(1)

# ======================================================================
#                      SCANNER LOGIC CLASS (BACKEND)
# ======================================================================
class FullScanner:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.desktop = Desktop(backend='uia')
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Fatal error initializing COM: {e}", exc_info=True)
            raise

    def get_all_windows(self):
        self.logger.info("Starting to scan all windows on the desktop...")
        windows = self.desktop.windows()
        visible_windows = []
        for win in windows:
            try:
                if win.is_visible() and win.window_text():
                    info = {
                        'title': win.window_text(),
                        'handle': win.handle,
                        'process': core_logic.get_property_value(win, 'proc_name'),
                        'pwa_object': win
                    }
                    visible_windows.append(info)
            except Exception as e:
                self.logger.warning(f"Could not process window. Error: {e}")
        self.logger.info(f"Found {len(visible_windows)} valid windows.")
        return visible_windows

    def get_all_elements_from_window(self, window_pwa_object):
        if not window_pwa_object:
            self.logger.error("Invalid window object provided.")
            return []
        window_title = window_pwa_object.window_text()
        self.logger.info(f"Starting deep scan for all elements in window: '{window_title}'")
        all_elements_data = []
        root_com_element = window_pwa_object.element_info.element
        self._walk_element_tree(root_com_element, 0, all_elements_data)
        self.logger.info(f"Scan complete. Collected {len(all_elements_data)} elements.")
        return all_elements_data

    def _walk_element_tree(self, element_com, level, all_elements_data, max_depth=25):
        if element_com is None or level > max_depth:
            return
        try:
            element_pwa = UIAWrapper(UIAElementInfo(element_com))
            element_data = core_logic.get_all_properties(element_pwa, self.uia, self.tree_walker)
            if element_data:
                all_elements_data.append(element_data)
            child = self.tree_walker.GetFirstChildElement(element_com)
            while child:
                self._walk_element_tree(child, level + 1, all_elements_data, max_depth)
                try:
                    child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError:
                    break
        except Exception as e:
            self.logger.warning(f"Error walking element tree at level {level}: {e}")

# ======================================================================
#                      GUI CLASS (Embeddable Frame)
# ======================================================================
class ExplorerTab(ttk.Frame):
    def __init__(self, parent, status_label_widget):
        super().__init__(parent)
        self.pack(fill="both", expand=True) 
        
        self.status_label = status_label_widget
        self.scanner = FullScanner()
        self.selected_window_object = None
        self.selected_element_data = None
        self.element_data_cache = []
        self.window_map = {}
        self.element_map = {}
        self.highlighter_window = None

        self.ELEMENT_COLUMNS = {
            'rel_level': ('Lvl', 50), 'pwa_title': ('Title/Name', 350),
            'pwa_control_type': ('Control Type', 150), 'pwa_auto_id': ('Automation ID', 150),
            'pwa_class_name': ('Class Name', 150), 'win32_handle': ('Handle', 100),
            'state_is_enabled': ('Enabled', 60), 'state_is_visible': ('Visible', 60),
            'geo_bounding_rect_tuple': ('Rect (L,T,R,B)', 200)
        }
        self.create_widgets()

    def create_widgets(self):
        top_frame = ttk.Frame(self, padding=10)
        top_frame.pack(side='top', fill='x')

        self.scan_windows_btn = ttk.Button(top_frame, text="Scan All Windows", command=self.start_scan_windows)
        self.scan_windows_btn.pack(side='left', padx=(0, 10))

        self.scan_elements_btn = ttk.Button(top_frame, text="Scan Window's Elements", state="disabled", command=self.start_scan_elements)
        self.scan_elements_btn.pack(side='left', padx=10)
        
        self.detail_btn = ttk.Button(top_frame, text="View Element Details", state="disabled", command=self.show_detail_window)
        self.detail_btn.pack(side='left', padx=10)

        self.export_btn = ttk.Button(top_frame, text="Export to Excel...", state="disabled", command=self.export_to_excel)
        self.export_btn.pack(side='left', padx=10)

        main_paned_window = ttk.PanedWindow(self, orient='vertical')
        main_paned_window.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        windows_frame = self.create_windows_list_frame(main_paned_window)
        main_paned_window.add(windows_frame, weight=1)

        elements_frame = self.create_elements_list_frame(main_paned_window)
        main_paned_window.add(elements_frame, weight=2)

    def create_windows_list_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Running Windows List")
        frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
        cols = ("title", "handle", "process")
        self.win_tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.win_tree.heading("title", text="Title"); self.win_tree.heading("handle", text="Handle"); self.win_tree.heading("process", text="Process Name")
        self.win_tree.column("title", width=500); self.win_tree.column("handle", width=100, anchor='center'); self.win_tree.column("process", width=150)
        self.win_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.win_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.win_tree.configure(yscrollcommand=scrollbar.set)
        self.win_tree.bind("<<TreeviewSelect>>", self.on_window_select)
        return frame

    def create_elements_list_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Elements of Selected Window")
        frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
        column_keys = list(self.ELEMENT_COLUMNS.keys())
        self.elem_tree = ttk.Treeview(frame, columns=column_keys, show="headings")
        for key in column_keys:
            display_name, width = self.ELEMENT_COLUMNS[key]
            anchor = 'w' if key not in ['rel_level', 'win32_handle', 'state_is_enabled', 'state_is_visible'] else 'center'
            self.elem_tree.heading(key, text=display_name)
            self.elem_tree.column(key, width=width, anchor=anchor)
        self.elem_tree.grid(row=0, column=0, sticky="nsew")
        y_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.elem_tree.yview)
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        self.elem_tree.configure(yscrollcommand=y_scrollbar.set)
        x_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=self.elem_tree.xview)
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        self.elem_tree.configure(xscrollcommand=x_scrollbar.set)
        self.elem_tree.bind("<<TreeviewSelect>>", self.on_element_select)
        return frame

    def update_status(self, text):
        if self.status_label:
            self.status_label.config(text=text)

    def clear_treeview(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def start_scan_windows(self):
        self.scan_windows_btn.config(state="disabled"); self.scan_elements_btn.config(state="disabled")
        self.export_btn.config(state="disabled"); self.detail_btn.config(state="disabled")
        self.update_status("Scanning all windows...")
        self.clear_treeview(self.win_tree); self.clear_treeview(self.elem_tree)
        self.window_map.clear(); self.element_map.clear()
        threading.Thread(target=self._scan_windows_thread, daemon=True).start()

    def _scan_windows_thread(self):
        windows = self.scanner.get_all_windows()
        self.after(0, self.populate_windows_tree, windows)

    def populate_windows_tree(self, windows):
        for win_info in windows:
            values = (win_info['title'], win_info['handle'], win_info['process'])
            item_id = self.win_tree.insert("", "end", values=values)
            self.window_map[item_id] = win_info['pwa_object']
        self.update_status(f"Found {len(windows)} windows. Please select one to scan for elements.")
        self.scan_windows_btn.config(state="normal")

    def on_window_select(self, event):
        selected_items = self.win_tree.selection()
        if not selected_items: return
        self.selected_window_object = self.window_map.get(selected_items[0])
        if self.selected_window_object:
            self.scan_elements_btn.config(state="normal")
            self.detail_btn.config(state="disabled")
            self.update_status(f"Selected: '{self.selected_window_object.window_text()}'. Ready to scan elements.")
        else:
            self.scan_elements_btn.config(state="disabled")

    def on_element_select(self, event):
        selected_items = self.elem_tree.selection()
        if not selected_items: return
        self.selected_element_data = self.element_map.get(selected_items[0])
        if self.selected_element_data:
            self.detail_btn.config(state="normal")
            self.update_status("Element selected. Ready to view details.")
            rect = self.selected_element_data.get('geo_bounding_rect_tuple')
            if rect:
                self.draw_highlight(rect)
        else:
            self.detail_btn.config(state="disabled")

    def start_scan_elements(self):
        if not self.selected_window_object:
            messagebox.showwarning("No Window Selected", "Please select a window from the list first.")
            return
        self.scan_windows_btn.config(state="disabled"); self.scan_elements_btn.config(state="disabled")
        self.export_btn.config(state="disabled"); self.detail_btn.config(state="disabled")
        self.update_status(f"Scanning elements of '{self.selected_window_object.window_text()}'...")
        self.clear_treeview(self.elem_tree); self.element_map.clear()
        threading.Thread(target=self._scan_elements_thread, daemon=True).start()

    def _scan_elements_thread(self):
        self.element_data_cache = self.scanner.get_all_elements_from_window(self.selected_window_object)
        self.after(0, self.populate_elements_tree, self.element_data_cache)

    def populate_elements_tree(self, elements):
        column_keys = list(self.ELEMENT_COLUMNS.keys())
        for elem_info in elements:
            indent = "    " * elem_info.get('rel_level', 0)
            values = []
            for key in column_keys:
                val = elem_info.get(key, '')
                if key == 'pwa_title': val = indent + str(val)
                elif isinstance(val, (list, tuple)): val = str(val)
                values.append(val)
            item_id = self.elem_tree.insert("", "end", values=tuple(values))
            self.element_map[item_id] = elem_info
        self.update_status(f"Scan finished! Found {len(elements)} elements.")
        self.scan_windows_btn.config(state="normal"); self.scan_elements_btn.config(state="normal")
        if elements: self.export_btn.config(state="normal")

    def show_detail_window(self):
        if not self.selected_element_data:
            messagebox.showwarning("No Element Selected", "Please select an element from the table below.")
            return
        detail_win = tk.Toplevel(self)
        detail_win.title("Element Specification Details")
        detail_win.geometry("650x700+50+50")
        detail_win.transient(self)
        detail_win.grab_set()
        window_info = core_logic.get_all_properties(self.selected_window_object, self.scanner.uia, self.scanner.tree_walker)
        element_info = self.selected_element_data
        cleaned_element_info = core_logic._clean_element_spec(window_info, element_info)
        def copy_to_clipboard(content, button):
            detail_win.clipboard_clear(); detail_win.clipboard_append(content); detail_win.update()
            original_text = button.cget("text"); button.config(text="✅")
            detail_win.after(1500, lambda: button.config(text=original_text))
        main_frame = ttk.Frame(detail_win, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1); main_frame.rowconfigure(1, weight=1); main_frame.rowconfigure(2, weight=1)
        win_spec_str = core_logic.format_spec_to_string(window_info, "window_spec")
        quick_win_spec_str = core_logic._create_smart_quick_spec(window_info, 'window')
        win_frame = ttk.LabelFrame(main_frame, text="Window Specification", padding=(10, 5))
        win_frame.grid(row=0, column=0, sticky="nsew", pady=5)
        win_frame.columnconfigure(0, weight=1); win_frame.rowconfigure(0, weight=1)
        win_text = tk.Text(win_frame, wrap="word", font=("Courier New", 10)); win_text.grid(sticky="nsew")
        win_text.insert("1.0", win_spec_str); win_text.config(state="disabled")
        win_btn_frame = ttk.Frame(win_frame); win_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        copy_full_win_btn = ttk.Button(win_btn_frame, text="📋 Full", style="Copy.TButton", command=lambda: copy_to_clipboard(win_spec_str, copy_full_win_btn))
        copy_full_win_btn.pack(side='left', padx=2)
        copy_quick_win_btn = ttk.Button(win_btn_frame, text="📋 Quick", style="Copy.TButton", command=lambda: copy_to_clipboard(quick_win_spec_str, copy_quick_win_btn))
        copy_quick_win_btn.pack(side='left', padx=2)
        elem_spec_str = core_logic.format_spec_to_string(cleaned_element_info, "element_spec")
        quick_elem_spec_str = core_logic._create_smart_quick_spec(cleaned_element_info, 'element')
        elem_frame = ttk.LabelFrame(main_frame, text="Element Specification (duplicates removed)", padding=(10, 5))
        elem_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        elem_frame.columnconfigure(0, weight=1); elem_frame.rowconfigure(0, weight=1)
        elem_text = tk.Text(elem_frame, wrap="word", font=("Courier New", 10)); elem_text.grid(sticky="nsew")
        elem_text.insert("1.0", elem_spec_str); elem_text.config(state="disabled")
        elem_btn_frame = ttk.Frame(elem_frame); elem_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        copy_full_elem_btn = ttk.Button(elem_btn_frame, text="📋 Full", style="Copy.TButton", command=lambda: copy_to_clipboard(elem_spec_str, copy_full_elem_btn))
        copy_full_elem_btn.pack(side='left', padx=2)
        copy_quick_elem_btn = ttk.Button(elem_btn_frame, text="📋 Quick", style="Copy.TButton", command=lambda: copy_to_clipboard(quick_elem_spec_str, copy_quick_elem_btn))
        copy_quick_elem_btn.pack(side='left', padx=2)
        combined_quick_spec_str = f"{quick_win_spec_str}\n\n{quick_elem_spec_str}"
        quick_frame = ttk.LabelFrame(main_frame, text="Combined Quick Spec", padding=(10, 5))
        quick_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        quick_frame.columnconfigure(0, weight=1); quick_frame.rowconfigure(0, weight=1)
        quick_text = tk.Text(quick_frame, wrap="word", font=("Courier New", 10)); quick_text.grid(sticky="nsew")
        quick_text.insert("1.0", combined_quick_spec_str); quick_text.config(state="disabled")
        quick_btn_frame = ttk.Frame(quick_frame); quick_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        copy_combined_quick_btn = ttk.Button(quick_frame, text="📋 Copy All", style="Copy.TButton", command=lambda: copy_to_clipboard(combined_quick_spec_str, copy_combined_quick_btn))
        copy_combined_quick_btn.pack(side='left', padx=2)

    def export_to_excel(self):
        if not self.element_data_cache:
            messagebox.showinfo("No Data", "There is no element data to export.")
            return
        window_title = self.selected_window_object.window_text()
        sanitized_title = re.sub(r'[\\/:*?"<>|]', '_', window_title)[:50] or "ScannedWindow"
        initial_filename = f"Elements_{sanitized_title}_{time.strftime('%Y%m%d')}.xlsx"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")],
            initialfile=initial_filename, title="Save Excel File"
        )
        if not file_path:
            self.update_status("Export canceled.")
            return
        try:
            self.update_status(f"Exporting to: {os.path.basename(file_path)}...")
            df = pd.DataFrame(self.element_data_cache)
            df.to_excel(file_path, index=False, engine='openpyxl')
            self.update_status("Excel export successful!")
            messagebox.showinfo("Success", f"Data was successfully saved to:\n{file_path}")
        except Exception as e:
            self.update_status(f"Error exporting file: {e}")
            messagebox.showerror("Error", f"Could not save the Excel file.\nError: {e}")

    def draw_highlight(self, rect_tuple):
        self.destroy_highlight()
        try:
            left, top, right, bottom = rect_tuple
            width = right - left
            height = bottom - top
            self.highlighter_window = tk.Toplevel(self)
            self.highlighter_window.overrideredirect(True)
            self.highlighter_window.wm_attributes("-topmost", True, "-disabled", True, "-transparentcolor", "white")
            self.highlighter_window.geometry(f'{width}x{height}+{left}+{top}')
            canvas = tk.Canvas(self.highlighter_window, bg='white', highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_rectangle(2, 2, width - 2, height - 2, outline="red", width=4)
            self.highlighter_window.after(2500, self.destroy_highlight)
        except Exception as e:
            logging.error(f"Error drawing highlight rectangle: {e}")

    def destroy_highlight(self):
        if self.highlighter_window and self.highlighter_window.winfo_exists():
            self.highlighter_window.destroy()
        self.highlighter_window = None

# ======================================================================
#                           ENTRY POINT (for standalone execution)
# ======================================================================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    
    root = tk.Tk()
    root.title("Standalone Window Explorer")
    root.geometry("1100x700")

    status_frame = ttk.Frame(root, relief='sunken', padding=2)
    status_frame.pack(side='bottom', fill='x')
    ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
    status_label = ttk.Label(status_frame, text="Ready (Standalone Mode)")
    status_label.pack(side='left', padx=5)
    
    app_frame = ExplorerTab(root, status_label)
    
    root.mainloop()
