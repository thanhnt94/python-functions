# Elements/ui_inspector.py
# Version 4.4: Moved UI settings to constants for easy configuration and fixed typo.

import logging
import re
import time
import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font
from ctypes import wintypes

# --- Required Libraries ---
try:
    import pandas as pd
    import win32gui
    import comtypes
    import comtypes.client
    import keyboard
    from comtypes.gen import UIAutomationClient as UIA
    from pywinauto.uia_element_info import UIAElementInfo
    from pywinauto.controls.uiawrapper import UIAWrapper
except ImportError as e:
    print(f"Error importing libraries: {e}")
    print("Suggestion: pip install pandas openpyxl pywin32 comtypes keyboard pywinauto")
    exit()

# --- Shared Logic Import ---
try:
    from . import ui_shared_logic
except ImportError:
    import ui_shared_logic

# ======================================================================
#                      DEFINITIONS & UTILITY FUNCTIONS
# ======================================================================

# --- UI Configuration Constants ---
HIGHLIGHT_DURATION_MS = 2500
INTERACTIVE_DIALOG_WIDTH = 350 
INTERACTIVE_DIALOG_HEIGHT = 700
INTERACTIVE_DIALOG_DEFAULT_GEOMETRY = "-10-10" # Default position on screen (e.g., "+10+10")

# --- Quick Spec Keys ---
QUICK_SPEC_WINDOW_KEYS = [
    'win32_handle', 'pwa_title', 'pwa_class_name', 'proc_name'
]
QUICK_SPEC_ELEMENT_KEYS = [
    'pwa_auto_id', 'pwa_title', 'pwa_control_type', 'pwa_class_name'
]

def _format_dict_as_pep8_string(spec_dict):
    """Formats a dictionary into a clean, copyable string's content."""
    if not spec_dict: return ""
    dict_to_format = {k: v for k, v in spec_dict.items() if not k.startswith('sys_') and (v or v is False or v == 0)}
    if not dict_to_format: return ""
    items_str = [f"    '{k}': {repr(v)}," for k, v in sorted(dict_to_format.items())]
    return "\n".join(items_str)

def _create_smart_quick_spec(info, spec_type='window'):
    """
    Creates an intelligent, minimal, and reliable quick spec.
    """
    spec = {}
    if spec_type == 'window':
        if info.get('pwa_title'):
            spec['pwa_title'] = info['pwa_title']
        if info.get('proc_name'):
            spec['proc_name'] = info['proc_name']
        if not spec and info.get('pwa_class_name'):
             spec['pwa_class_name'] = info['pwa_class_name']
    
    elif spec_type == 'element':
        if info.get('pwa_auto_id'):
            spec['pwa_auto_id'] = info['pwa_auto_id']
        elif info.get('pwa_title'):
            spec['pwa_title'] = info['pwa_title']
            if info.get('pwa_control_type'):
                spec['pwa_control_type'] = info['pwa_control_type']
        elif info.get('pwa_class_name'):
            spec['pwa_class_name'] = info['pwa_class_name']
            if info.get('pwa_control_type'):
                spec['pwa_control_type'] = info['pwa_control_type']
            
    content = _format_dict_as_pep8_string(spec)
    return f"{spec_type}_spec = {{\n{content}\n}}"


def _clean_element_spec(window_info, element_info):
    """Removes all duplicate properties from the element_spec."""
    if not window_info or not element_info: return element_info
    cleaned_spec = element_info.copy()
    for key, value in list(element_info.items()):
        if key in window_info and window_info[key] == value:
            del cleaned_spec[key]
    return cleaned_spec

# ======================================================================
#                      MAIN UIINSPECTOR CLASS
# ======================================================================

class UIInspector:
    def __init__(self, root_gui):
        if UIA is None: raise RuntimeError("UIAutomationClient could not be initialized.")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.root_gui = root_gui
        self.current_element = None
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Fatal error initializing COM: {e}", exc_info=True)
            raise

    def _create_full_pwa_wrapper(self, com_element):
        """Creates a full-featured pywinauto wrapper."""
        if not com_element: return None
        element_info = UIAElementInfo(com_element)
        return UIAWrapper(element_info)

    def scan_window_to_excel(self, wait_time=3):
        """Scans the entire element tree of a window and exports to an Excel file."""
        self.logger.info(f"Please activate the target window. Scan will begin in {wait_time} seconds...")
        self.root_gui.show_countdown_timer(wait_time)
        
        active_hwnd = win32gui.GetForegroundWindow()
        if not active_hwnd:
            self.logger.error("No active window found.")
            return None

        try:
            root_element_com = self.uia.ElementFromHandle(active_hwnd)
            root_element_pwa = self._create_full_pwa_wrapper(root_element_com)
            if not root_element_pwa: raise comtypes.COMError("Could not create PWA wrapper.")
        except comtypes.COMError as e:
            self.logger.error(f"Could not get element from handle. Error: {e}")
            return None

        window_title = root_element_pwa.window_text()
        self.logger.info(f"Starting full scan of window: '{window_title}' (Handle: {active_hwnd})")
        
        window_data = ui_shared_logic.get_all_properties(root_element_pwa, self.uia, self.tree_walker)
        all_elements_data = []
        self._walk_element_tree(root_element_com, 0, all_elements_data)
        
        self.logger.info(f"Scan complete. Collected {len(all_elements_data)} elements.")
        if not all_elements_data and not window_data:
            self.logger.warning("No information was collected.")
            return None

        save_folder = Path.home() / "UiInspectorResults"
        save_folder.mkdir(exist_ok=True)
        sanitized_title = re.sub(r'[\\/:*?"<>|]', '_', window_title)[:100] or "ScannedWindow"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_filename = f"Scan_{sanitized_title}_{timestamp}.xlsx"
        full_output_path = save_folder / output_filename
        self.logger.info(f"Saving results to: {full_output_path}")

        try:
            win_content = _format_dict_as_pep8_string(window_data)
            if window_data: window_data['spec_to_copy'] = f"window_spec = {{\n{win_content}\n}}"
            
            for item in all_elements_data:
                item_content = _format_dict_as_pep8_string(item)
                item['spec_to_copy'] = f"element_spec = {{\n{item_content}\n}}"

            df_window = pd.DataFrame([window_data]) if window_data else pd.DataFrame()
            df_elements = pd.DataFrame(all_elements_data) if all_elements_data else pd.DataFrame()
            items = [(k.split('_')[0].upper(), k, v) for k, v in ui_shared_logic.PARAMETER_DEFINITIONS.items()]
            df_lookup = pd.DataFrame(items, columns=['Category', 'Parameter', 'Description'])
            with pd.ExcelWriter(full_output_path, engine='openpyxl') as writer:
                if not df_window.empty: df_window.to_excel(writer, sheet_name='Windows Info', index=False)
                if not df_elements.empty: df_elements.to_excel(writer, sheet_name='Elements Details', index=False)
                df_lookup.to_excel(writer, sheet_name='Parameter Reference', index=False)
            self.logger.info("Successfully saved.")
            return full_output_path
        except Exception as e:
            self.logger.error(f"Error writing Excel file: {e}", exc_info=True)
            return None

    def _walk_element_tree(self, element_com, level, all_elements_data, max_depth=25):
        """Recursively walks the element tree."""
        if element_com is None or level > max_depth: return
        try:
            element_pwa = self._create_full_pwa_wrapper(element_com)
            if not element_pwa: return
            
            element_data = ui_shared_logic.get_all_properties(element_pwa, self.uia, self.tree_walker)
            if element_data: all_elements_data.append(element_data)
            
            child = self.tree_walker.GetFirstChildElement(element_com)
            while child:
                # *** FIX: Corrected the typo in the recursive call ***
                self._walk_element_tree(child, level + 1, all_elements_data, max_depth)
                try: child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError: break
        except Exception as e:
            self.logger.warning(f"Error walking element tree: {e}")

    def _run_scan_at_cursor(self):
        """Scans the element directly under the mouse cursor (F8)."""
        self.logger.info("Scan request (F8) received.")
        self.root_gui.destroy_highlight()
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            element_com = self.uia.ElementFromPoint(point)
            if not element_com: 
                self.logger.warning("No element found under the cursor.")
                return
            self.current_element = element_com
            self._inspect_element(self.current_element)
        except Exception as e:
            self.logger.error(f"Unexpected error during scan: {e}", exc_info=True)

    def _scan_parent_element(self):
        """Scans the parent of the current element (F7)."""
        self.logger.info("Scan parent request (F7) received.")
        if not self.current_element:
            self.logger.warning("No element has been scanned yet. Please press F8 first.")
            return
        try:
            parent = self.tree_walker.GetParentElement(self.current_element)
            if parent:
                self.current_element = parent
                self._inspect_element(self.current_element)
            else:
                self.logger.warning("No valid parent element found.")
        except Exception as e:
            self.logger.error(f"Error scanning parent element: {e}", exc_info=True)
    
    def _scan_child_element(self):
        """Scans a child element under the cursor (F9)."""
        self.logger.info("Scan child request (F9) received.")
        if not self.current_element:
            self.logger.warning("No element has been scanned yet. Please press F8 first.")
            return
        try:
            cursor_pos = win32gui.GetCursorPos()
            point = wintypes.POINT(cursor_pos[0], cursor_pos[1])
            found_child = None
            child = self.tree_walker.GetFirstChildElement(self.current_element)
            while child:
                try:
                    child_rect = child.CurrentBoundingRectangle
                    if (child_rect and
                        point.x >= child_rect.left and point.x <= child_rect.right and
                        point.y >= child_rect.top and point.y <= child_rect.bottom):
                        found_child = child
                        break
                    child = self.tree_walker.GetNextSiblingElement(child)
                except comtypes.COMError: break
            if found_child:
                self.logger.info(f"Entering child: '{found_child.CurrentName}'. Updating...")
                self.current_element = found_child
                self._inspect_element(self.current_element)
            else:
                self.logger.warning("No child element found under the cursor.")
        except Exception as e:
            self.logger.error(f"Unexpected error scanning for child element: {e}", exc_info=True)

    def _inspect_element(self, element_com):
        """Central function to analyze an element and update the GUI."""
        element_pwa = self._create_full_pwa_wrapper(element_com)
        if not element_pwa:
            self.logger.error("Could not create PWA wrapper for the selected element.")
            return
        
        element_details = ui_shared_logic.get_all_properties(element_pwa, self.uia, self.tree_walker)
        top_level_window_pwa = ui_shared_logic.get_top_level_window(element_pwa)

        window_details = {}
        if top_level_window_pwa:
            window_details = ui_shared_logic.get_all_properties(top_level_window_pwa, self.uia, self.tree_walker)
        else:
            self.logger.warning("Could not determine the top-level parent window.")

        coords = element_details.get('geo_bounding_rect_tuple')
        if coords:
            level = element_details.get('rel_level', 0)
            self._draw_highlight_rectangle(coords, level)
        else:
            self.logger.warning("Could not get element coordinates to draw highlight.")

        cleaned_element_details = _clean_element_spec(window_details, element_details)
        self.root_gui.update_spec_dialog(window_details, cleaned_element_details)

    def _draw_highlight_rectangle(self, rect, level=0):
        """Draws a colored rectangle to highlight the scanned element."""
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
            self.logger.error(f"Error drawing highlight rectangle: {e}")

# ======================================================================
#                      GUI CLASS
# ======================================================================

class InspectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UI Inspector v4.4 (Configurable)")
        self.geometry("450x320")
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
        style.configure("Copy.TButton", padding=2, font=('Segoe UI', 8))
        self.create_main_widgets()

    def create_main_widgets(self):
        status_frame = ttk.Frame(self, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        self.main_status_label = ttk.Label(status_frame, text="Ready")
        self.main_status_label.pack(side='left', padx=5)

        self.main_frame = ttk.Frame(self, padding="20")
        self.main_frame.pack(fill="both", expand=True)
        header_label = ttk.Label(self.main_frame, text="UI Inspector", style="Header.TLabel", anchor="center")
        header_label.pack(pady=(0, 20))
        self.scan_excel_btn = ttk.Button(self.main_frame, text="Full Window Scan (to Excel)", command=self.run_full_scan)
        self.scan_excel_btn.pack(fill="x", pady=5)
        self.interactive_btn = ttk.Button(self.main_frame, text="Start Interactive Scan", command=self.run_interactive_scan)
        self.interactive_btn.pack(fill="x", pady=5)

    def run_full_scan(self):
        self.scan_excel_btn.config(state='disabled')
        self.interactive_btn.config(state='disabled')
        self.main_status_label.config(text="Scanning, please wait...")
        self.update_idletasks()
        
        try:
            file_path = self.inspector.scan_window_to_excel()
            self.show_scan_result(file_path)
        finally:
            self.scan_excel_btn.config(state='normal')
            self.interactive_btn.config(state='normal')
            self.main_status_label.config(text="Ready")

    def run_interactive_scan(self):
        self.withdraw()
        self.show_spec_dialog()
        self.is_interactive_mode = True
        self.listener_thread = threading.Thread(target=self.keyboard_listener_thread, daemon=True)
        self.listener_thread.start()

    def keyboard_listener_thread(self):
        logging.info("Starting hotkey listener: F7 (Parent), F8 (Scan), F9 (Child), ESC (Exit).")
        keyboard.add_hotkey('f8', self.inspector._run_scan_at_cursor)
        keyboard.add_hotkey('f7', self.inspector._scan_parent_element)
        keyboard.add_hotkey('f9', self.inspector._scan_child_element)
        keyboard.wait('esc')
        if self.is_interactive_mode:
            self.after(0, self.stop_interactive_scan)

    def stop_interactive_scan(self):
        logging.info("ESC key pressed, exiting interactive mode.")
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
        countdown_win.title("Countdown")
        countdown_win.overrideredirect(True)
        countdown_win.wm_attributes("-topmost", True)
        
        style = ttk.Style(countdown_win)
        style.configure("Countdown.TLabel", font=('Segoe UI', 16, 'bold'), padding=25)
        
        status_frame = ttk.Frame(countdown_win, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        ttk.Label(status_frame, text="Scanning...").pack(side='left', padx=5)

        label_text = "Please activate the target window.\nScanning in {}..."
        label = ttk.Label(countdown_win, text=label_text.format(duration), style="Countdown.TLabel", wraplength=380, justify='center')
        label.pack(expand=True, fill='both', padx=10, pady=10)
        
        countdown_win.update_idletasks()
        width = 400
        height = countdown_win.winfo_reqheight()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        countdown_win.geometry(f'{width}x{height}+{x}+{y}')
        
        for i in range(duration, 0, -1):
            label.config(text=label_text.format(i))
            self.update()
            time.sleep(1)
            
        countdown_win.destroy()

    def show_scan_result(self, file_path):
        result_win = tk.Toplevel(self)
        result_win.title("Scan Result")
        result_win.transient(self)
        result_win.grab_set()

        status_frame = ttk.Frame(result_win, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        ttk.Label(status_frame, text="Completed").pack(side='left', padx=5)

        if file_path and os.path.exists(file_path):
            message = f"Scan successful!\n\nResults saved to:\n{file_path}"
        else:
            message = "Scan failed.\nPlease check the logs for more details."
            
        label = ttk.Label(result_win, text=message, padding=20, wraplength=450, justify='center')
        label.pack(pady=10, padx=10, fill='x')
        
        button_frame = ttk.Frame(result_win)
        button_frame.pack(pady=10)

        if file_path and os.path.exists(file_path):
            open_file_btn = ttk.Button(button_frame, text="Open File", command=lambda: os.startfile(file_path))
            open_file_btn.pack(side='left', padx=10)
            open_folder_btn = ttk.Button(button_frame, text="Open Folder", command=lambda: os.startfile(os.path.dirname(file_path)))
            open_folder_btn.pack(side='left', padx=10)

        close_btn = ttk.Button(button_frame, text="Close", command=result_win.destroy)
        close_btn.pack(side='left', padx=10)
        
        result_win.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (result_win.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (result_win.winfo_height() // 2)
        result_win.geometry(f"+{x}+{y}")

    def show_spec_dialog(self):
        if self.spec_dialog and self.spec_dialog.winfo_exists():
            self.spec_dialog.lift()
            return
        self.spec_dialog = tk.Toplevel(self)
        self.spec_dialog.title("Interactive Scan Results")
        # Use the new constant for geometry
        self.spec_dialog.geometry(f"{INTERACTIVE_DIALOG_WIDTH}x{INTERACTIVE_DIALOG_HEIGHT}{INTERACTIVE_DIALOG_DEFAULT_GEOMETRY}")
        self.spec_dialog.wm_attributes("-topmost", 1)
        self.spec_dialog.protocol("WM_DELETE_WINDOW", self.stop_interactive_scan)
        
        status_frame = ttk.Frame(self.spec_dialog, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        self.status_label = ttk.Label(status_frame, text="Status: Waiting for scan (F8)...")
        self.status_label.pack(side='left', padx=5)

        def copy_to_clipboard(content, button):
            self.spec_dialog.clipboard_clear()
            self.spec_dialog.clipboard_append(content)
            self.spec_dialog.update()
            original_text = button.cget("text")
            button.config(text="✅")
            self.spec_dialog.after(1500, lambda: button.config(text=original_text))
            
        main_frame = ttk.Frame(self.spec_dialog, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1); main_frame.rowconfigure(1, weight=1); main_frame.rowconfigure(2, weight=1)

        # --- Window Spec ---
        win_frame = ttk.LabelFrame(main_frame, text="Window Specification", padding=(10, 5))
        win_frame.grid(row=0, column=0, sticky="nsew", pady=(5, 5))
        win_frame.columnconfigure(0, weight=1); win_frame.rowconfigure(0, weight=1)
        
        self.win_text = tk.Text(win_frame, wrap="word", font=("Courier New", 10))
        self.win_text.grid(row=0, column=0, sticky="nsew")
        
        win_btn_frame = ttk.Frame(win_frame)
        win_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        self.copy_full_win_btn = ttk.Button(win_btn_frame, text="📋 Full", style="Copy.TButton", command=lambda: copy_to_clipboard(self.win_text.get("1.0", "end-1c"), self.copy_full_win_btn))
        self.copy_full_win_btn.pack(side='left', padx=2)
        self.copy_quick_win_btn = ttk.Button(win_btn_frame, text="📋 Quick", style="Copy.TButton", command=lambda: copy_to_clipboard(self.quick_win_spec_str, self.copy_quick_win_btn))
        self.copy_quick_win_btn.pack(side='left', padx=2)

        # --- Element Spec ---
        elem_frame = ttk.LabelFrame(main_frame, text="Element Specification", padding=(10, 5))
        elem_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        elem_frame.columnconfigure(0, weight=1); elem_frame.rowconfigure(0, weight=1)

        self.elem_text = tk.Text(elem_frame, wrap="word", font=("Courier New", 10))
        self.elem_text.grid(row=0, column=0, sticky="nsew")
        
        elem_btn_frame = ttk.Frame(elem_frame)
        elem_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        self.copy_full_elem_btn = ttk.Button(elem_btn_frame, text="📋 Full", style="Copy.TButton", command=lambda: copy_to_clipboard(self.elem_text.get("1.0", "end-1c"), self.copy_full_elem_btn))
        self.copy_full_elem_btn.pack(side='left', padx=2)
        self.copy_quick_elem_btn = ttk.Button(elem_btn_frame, text="📋 Quick", style="Copy.TButton", command=lambda: copy_to_clipboard(self.quick_elem_spec_str, self.copy_quick_elem_btn))
        self.copy_quick_elem_btn.pack(side='left', padx=2)

        # --- Combined Quick Spec ---
        quick_frame = ttk.LabelFrame(main_frame, text="Combined Quick Spec", padding=(10, 5))
        quick_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
        quick_frame.columnconfigure(0, weight=1); quick_frame.rowconfigure(0, weight=1)

        self.quick_text = tk.Text(quick_frame, wrap="word", font=("Courier New", 10))
        self.quick_text.grid(row=0, column=0, sticky="nsew")

        quick_btn_frame = ttk.Frame(quick_frame)
        quick_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        self.copy_combined_quick_btn = ttk.Button(quick_btn_frame, text="📋 Copy All", style="Copy.TButton", command=lambda: copy_to_clipboard(self.quick_text.get("1.0", "end-1c"), self.copy_combined_quick_btn))
        self.copy_combined_quick_btn.pack(side='left', padx=2)

    def update_spec_dialog(self, window_info, element_info):
        if not self.spec_dialog or not self.spec_dialog.winfo_exists(): return
        
        level = element_info.get('rel_level', 'N/A')
        proc_name = window_info.get('proc_name', 'Unknown')
        self.status_label.config(text=f"Level: {level} | Process: {proc_name}")

        self.quick_win_spec_str = _create_smart_quick_spec(window_info, 'window')
        self.quick_elem_spec_str = _create_smart_quick_spec(element_info, 'element')

        win_content = _format_dict_as_pep8_string(window_info)
        win_spec_str = f"window_spec = {{\n{win_content}\n}}"
        self.win_text.config(state="normal"); self.win_text.delete("1.0", "end"); self.win_text.insert("1.0", win_spec_str); self.win_text.config(state="disabled")
        
        elem_content = _format_dict_as_pep8_string(element_info)
        elem_spec_str = f"element_spec = {{\n{elem_content}\n}}"
        self.elem_text.config(state="normal"); self.elem_text.delete("1.0", "end"); self.elem_text.insert("1.0", elem_spec_str); self.elem_text.config(state="disabled")
        
        combined_quick_spec_str = f"{self.quick_win_spec_str}\n\n{self.quick_elem_spec_str}"
        self.quick_text.config(state="normal"); self.quick_text.delete("1.0", "end"); self.quick_text.insert("1.0", combined_quick_spec_str); self.quick_text.config(state="disabled")
        
    def destroy_highlight(self):
        if self.highlight_window and self.highlight_window.winfo_exists(): self.highlight_window.destroy()
        self.highlight_window = None

    def hide_spec_dialog(self):
        if self.spec_dialog: self.spec_dialog.destroy(); self.spec_dialog = None

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    app = InspectorApp()
    app.mainloop()
