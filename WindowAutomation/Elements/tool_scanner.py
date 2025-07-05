# tool_scanner.py
# A standalone tool for interactive UI element inspection using hotkeys.
# Refactored to be launchable from the main suite and send specs to the debugger.

import logging
import re
import time
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, font, messagebox
from ctypes import wintypes

# --- Required Libraries ---
try:
    import win32gui
    import comtypes
    import comtypes.client
    import keyboard
    from comtypes.gen import UIAutomationClient as UIA
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
#                      CONFIGURATION CONSTANTS
# ======================================================================

HIGHLIGHT_DURATION_MS = 2500
DIALOG_WIDTH = 300 
DIALOG_HEIGHT = 700
DIALOG_DEFAULT_GEOMETRY = "-10-10" 

# ======================================================================
#                      SCANNER LOGIC CLASS
# ======================================================================

class InteractiveScannerLogic:
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
        if not com_element: return None
        element_info = UIAElementInfo(com_element)
        return UIAWrapper(element_info)

    def _run_scan_at_cursor(self):
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
        element_pwa = self._create_full_pwa_wrapper(element_com)
        if not element_pwa:
            self.logger.error("Could not create PWA wrapper for the selected element.")
            return
        
        element_details = core_logic.get_all_properties(element_pwa, self.uia, self.tree_walker)
        top_level_window_pwa = core_logic.get_top_level_window(element_pwa)

        window_details = {}
        if top_level_window_pwa:
            window_details = core_logic.get_all_properties(top_level_window_pwa, self.uia, self.tree_walker)
        else:
            self.logger.warning("Could not determine the top-level parent window.")

        coords = element_details.get('geo_bounding_rect_tuple')
        if coords:
            level = element_details.get('rel_level', 0)
            self.root_gui.draw_highlight(element_pwa.rectangle(), level)
        else:
            self.logger.warning("Could not get element coordinates to draw highlight.")

        cleaned_element_details = core_logic.clean_element_spec(window_details, element_details)
        self.root_gui.update_spec_dialog(window_details, element_details, cleaned_element_details)

# ======================================================================
#                      GUI CLASS
# ======================================================================

class ScannerApp(tk.Toplevel):
    def __init__(self, suite_app=None):
        # We need a root window to host this Toplevel, even if it's hidden.
        # If suite_app is provided, it's the root. Otherwise, create a dummy hidden root.
        root = suite_app if suite_app else tk.Tk()
        if not suite_app:
            root.withdraw() # Hide the dummy root in standalone mode
        
        super().__init__(root)
        self.suite_app = suite_app
        
        self.title("Interactive Scan Results")
        self.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}{DIALOG_DEFAULT_GEOMETRY}")
        self.wm_attributes("-topmost", 1)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.scanner = InteractiveScannerLogic(self)
        self.highlight_window = None
        self.listener_thread = None
        
        # To store the latest scanned info
        self.last_window_info = {}
        self.last_element_info = {}
        self.last_cleaned_element_info = {}
        
        self.create_spec_dialog_widgets()
        self.run_interactive_scan()

    def run_interactive_scan(self):
        self.listener_thread = threading.Thread(target=self.keyboard_listener_thread, daemon=True)
        self.listener_thread.start()

    def keyboard_listener_thread(self):
        logging.info("Starting hotkey listener: F7 (Parent), F8 (Scan), F9 (Child), ESC (Exit).")
        keyboard.add_hotkey('f8', lambda: self.after(0, self.scanner._run_scan_at_cursor))
        keyboard.add_hotkey('f7', lambda: self.after(0, self.scanner._scan_parent_element))
        keyboard.add_hotkey('f9', lambda: self.after(0, self.scanner._scan_child_element))
        keyboard.wait('esc')
        self.after(0, self.on_closing)

    def on_closing(self):
        logging.info("Exit command received, shutting down scanner.")
        keyboard.unhook_all()
        self.destroy_highlight()
        self.destroy()

    def create_spec_dialog_widgets(self):
        style = ttk.Style(self)
        style.configure("Copy.TButton", padding=2, font=('Segoe UI', 8))
        
        status_frame = ttk.Frame(self, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        self.status_label = ttk.Label(status_frame, text="Status: Waiting for scan (F8)...")
        self.status_label.pack(side='left', padx=5)

        def copy_to_clipboard(content, button):
            self.clipboard_clear(); self.clipboard_append(content); self.update()
            original_text = button.cget("text"); button.config(text="✅")
            self.after(1500, lambda: button.config(text=original_text))
        
        def send_specs(win_spec, elem_spec):
            if self.suite_app and hasattr(self.suite_app, 'send_specs_to_debugger'):
                self.suite_app.send_specs_to_debugger(win_spec, elem_spec)
                self.on_closing()

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1); main_frame.rowconfigure(1, weight=1); main_frame.rowconfigure(2, weight=1)

        # --- Window Spec Frame ---
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
        if self.suite_app:
            send_win_btn = ttk.Button(win_btn_frame, text="🚀 Send", style="Copy.TButton", command=lambda: send_specs(self.last_window_info, {}))
            send_win_btn.pack(side='left', padx=2)

        # --- Element Spec Frame ---
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
        if self.suite_app:
            send_elem_btn = ttk.Button(elem_btn_frame, text="🚀 Send", style="Copy.TButton", command=lambda: send_specs(self.last_window_info, self.last_cleaned_element_info))
            send_elem_btn.pack(side='left', padx=2)

        # --- Combined Quick Spec Frame ---
        quick_frame = ttk.LabelFrame(main_frame, text="Combined Quick Spec", padding=(10, 5))
        quick_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
        quick_frame.columnconfigure(0, weight=1); quick_frame.rowconfigure(0, weight=1)
        self.quick_text = tk.Text(quick_frame, wrap="word", font=("Courier New", 10))
        self.quick_text.grid(row=0, column=0, sticky="nsew")
        quick_btn_frame = ttk.Frame(quick_frame)
        quick_btn_frame.place(relx=1.0, rely=0, x=-5, y=-11, anchor='ne')
        self.copy_combined_quick_btn = ttk.Button(quick_btn_frame, text="📋 Copy All", style="Copy.TButton", command=lambda: copy_to_clipboard(self.quick_text.get("1.0", "end-1c"), self.copy_combined_quick_btn))
        self.copy_combined_quick_btn.pack(side='left', padx=2)
        if self.suite_app:
            send_quick_btn = ttk.Button(quick_btn_frame, text="🚀 Send", style="Copy.TButton", command=lambda: send_specs(self.quick_win_spec_dict, self.quick_elem_spec_dict))
            send_quick_btn.pack(side='left', padx=2)

    def update_spec_dialog(self, window_info, element_info, cleaned_element_info):
        if not self.winfo_exists(): return
        
        self.last_window_info = window_info
        self.last_element_info = element_info
        self.last_cleaned_element_info = cleaned_element_info
        
        self.quick_win_spec_dict = core_logic.create_smart_quick_spec(window_info, 'window', as_dict=True)
        self.quick_elem_spec_dict = core_logic.create_smart_quick_spec(cleaned_element_info, 'element', as_dict=True)
        
        self.quick_win_spec_str = core_logic.format_spec_to_string(self.quick_win_spec_dict, 'window_spec')
        self.quick_elem_spec_str = core_logic.format_spec_to_string(self.quick_elem_spec_dict, 'element_spec')
        
        level = element_info.get('rel_level', 'N/A')
        proc_name = window_info.get('proc_name', 'Unknown')
        self.status_label.config(text=f"Level: {level} | Process: {proc_name}")

        win_spec_str = core_logic.format_spec_to_string(window_info, "window_spec")
        self.win_text.config(state="normal"); self.win_text.delete("1.0", "end"); self.win_text.insert("1.0", win_spec_str); self.win_text.config(state="disabled")
        
        elem_spec_str = core_logic.format_spec_to_string(cleaned_element_info, "element_spec")
        self.elem_text.config(state="normal"); self.elem_text.delete("1.0", "end"); self.elem_text.insert("1.0", elem_spec_str); self.elem_text.config(state="disabled")
        
        combined_quick_spec_str = f"{self.quick_win_spec_str}\n\n{self.quick_elem_spec_str}"
        self.quick_text.config(state="normal"); self.quick_text.delete("1.0", "end"); self.quick_text.insert("1.0", combined_quick_spec_str); self.quick_text.config(state="disabled")
        
    def destroy_highlight(self):
        if self.highlight_window and self.highlight_window.winfo_exists():
            self.highlight_window.destroy()
        self.highlight_window = None

    def draw_highlight(self, rect, level=0):
        self.destroy_highlight()
        try:
            colors = ['#FF0000', '#FF7F00', '#FFFF00', '#00FF00', '#0000FF', '#4B0082', '#9400D3']
            color = colors[level % len(colors)]
            self.highlight_window = tk.Toplevel(self)
            self.highlight_window.overrideredirect(True)
            self.highlight_window.wm_attributes("-topmost", True, "-disabled", True, "-transparentcolor", "white")
            self.highlight_window.geometry(f'{rect.width()}x{rect.height()}+{rect.left}+{rect.top}')
            canvas = tk.Canvas(self.highlight_window, bg='white', highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.create_rectangle(2, 2, rect.width()-2, rect.height()-2, outline=color, width=4)
            self.highlight_window.after(HIGHLIGHT_DURATION_MS, self.destroy_highlight)
        except Exception as e:
            logging.error(f"Error drawing highlight rectangle: {e}")

# ======================================================================
#                           ENTRY POINT
# ======================================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    
    app = ScannerApp(suite_app=None)
    app.mainloop()
