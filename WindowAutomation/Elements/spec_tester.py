# Elements/spec_tester.py
# Version 11.3: Implemented robust results display to handle problematic elements.

import tkinter as tk
from tkinter import ttk, scrolledtext, font
import threading
import ast
import logging

# --- Required Libraries ---
try:
    from pywinauto import Desktop
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
except ImportError as e:
    print(f"Error importing libraries: {e}")
    print("Suggestion: pip install pywinauto comtypes")
    exit()

# --- Shared Logic Import ---
try:
    from . import ui_shared_logic
except ImportError:
    import ui_shared_logic

# ======================================================================
#                      MAIN APPLICATION CLASS
# ======================================================================
class SpecTesterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Selector Debugger v11.3 (Final)")
        self.geometry("950x800")

        # --- Style Configuration ---
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TLabel", font=('Segoe UI', 10))
        style.configure("TButton", font=('Segoe UI', 10, 'bold'), padding=5)
        style.configure("TLabelframe.Label", font=('Segoe UI', 11, 'bold'))
        style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'))
        style.configure("Small.TButton", padding=2, font=('Segoe UI', 8))

        # --- Instance Variables ---
        self.highlighter = None
        self.test_thread = None
        self.found_elements_map = {} # Maps treeview item ID to pywinauto element
        self.selected_element = None
        self.selected_element_type = 'element' # To track if it's a 'window' or 'element'
        
        self.debugger = SelectorDebugger(self.log_message)
        
        self.create_widgets()

    def create_widgets(self):
        """Creates the main UI components."""
        main_paned_window = ttk.PanedWindow(self, orient='vertical')
        main_paned_window.pack(fill="both", expand=True, padx=10, pady=10)

        top_frame = ttk.Frame(main_paned_window)
        main_paned_window.add(top_frame, weight=2)
        top_frame.columnconfigure(0, weight=1)
        top_frame.rowconfigure(1, weight=1)

        input_frame = self.create_input_frame(top_frame)
        input_frame.grid(row=0, column=0, sticky="ew", pady=5)
        
        results_frame = self.create_results_frame(top_frame)
        results_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        log_frame = self.create_log_frame(main_paned_window)
        main_paned_window.add(log_frame, weight=1)
        
        status_frame = ttk.Frame(self, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side='left', padx=5)

    def create_input_frame(self, parent):
        """Creates the frame for spec inputs and control buttons."""
        frame = ttk.Frame(parent)
        frame.columnconfigure(1, weight=1)
        
        ttk.Label(frame, text="Window Spec:").grid(row=0, column=0, sticky="nw", padx=5)
        self.window_spec_text = tk.Text(frame, height=5, font=("Courier New", 10))
        self.window_spec_text.grid(row=0, column=1, sticky="ew")
        self.window_spec_text.insert("1.0", "window_spec = {\n    'pwa_class_name': ('icontains', 'CabinetWClass')\n}")
        
        ttk.Label(frame, text="Element Spec:").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        self.element_spec_text = tk.Text(frame, height=5, font=("Courier New", 10))
        self.element_spec_text.grid(row=1, column=1, sticky="ew", pady=5)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=1, sticky='w')
        
        self.run_button = ttk.Button(button_frame, text="🔎 Run Debug", command=self.run_test)
        self.run_button.pack(side="left", padx=(0, 10))

        self.get_spec_button = ttk.Button(button_frame, text="📋 Get Full Spec", state="disabled", command=self.show_full_spec_window)
        self.get_spec_button.pack(side="left", padx=10)
        
        self.clear_button = ttk.Button(button_frame, text="✨ Clear Log", command=self.clear_log)
        self.clear_button.pack(side="left", padx=10)
        
        return frame

    def create_results_frame(self, parent):
        """Creates the frame to display multiple found results."""
        frame = ttk.LabelFrame(parent, text="Found Results")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.results_tree = ttk.Treeview(frame, columns=("Title", "Type", "AutoID"), show="headings")
        self.results_tree.heading("Title", text="Title/Name")
        self.results_tree.heading("Type", text="Control Type")
        self.results_tree.heading("AutoID", text="Automation ID")
        self.results_tree.column("Title", width=400)
        self.results_tree.column("Type", width=150)
        self.results_tree.column("AutoID", width=200)
        
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.results_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.bind("<<TreeviewSelect>>", self.on_result_selected)
        
        return frame

    def create_log_frame(self, parent):
        """Creates the scrolled text area for detailed logs."""
        frame = ttk.LabelFrame(parent, text="Detailed Log")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        
        self.log_area = scrolledtext.ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled", bg="#2B2B2B")
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.log_area.tag_config('INFO', foreground='#87CEEB'); self.log_area.tag_config('DEBUG', foreground='#D3D3D3'); self.log_area.tag_config('FILTER', foreground='#FFD700'); self.log_area.tag_config('SUCCESS', foreground='#90EE90'); self.log_area.tag_config('ERROR', foreground='#F08080'); self.log_area.tag_config('HEADER', foreground='#FFFFFF', font=("Consolas", 11, "bold", "underline")); self.log_area.tag_config('KEEP', foreground='#76D7C4', font=("Consolas", 10, "bold")); self.log_area.tag_config('DISCARD', foreground='#E59866', font=("Consolas", 10, "bold"))
        
        return frame

    def log_message(self, level, message):
        """Callback to write logs to the GUI."""
        self.log_area.config(state="normal")
        if isinstance(message, list):
            self.log_area.insert(tk.END, f"[{level}] ")
            for text, tag in message: self.log_area.insert(tk.END, text, tag)
            self.log_area.insert(tk.END, "\n")
        else:
            self.log_area.insert(tk.END, f"[{level}] {message}\n", level)
        self.log_area.config(state="disabled")
        self.log_area.see(tk.END)

    def clear_log(self):
        """Clears the log area and the results tree."""
        self.log_area.config(state="normal")
        self.log_area.delete("1.0", tk.END)
        self.log_area.config(state="disabled")
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.get_spec_button.config(state="disabled")
        self.selected_element = None
        self.status_label.config(text="Cleared. Ready for new test.")

    def _extract_and_parse_spec(self, spec_string):
        """Safely extracts and parses a dictionary string from a text widget."""
        spec_string = spec_string.strip()
        if not spec_string: return {}
        start_brace = spec_string.find('{')
        if start_brace == -1: raise ValueError("Could not find '{' to start dictionary.")
        dict_str = spec_string[start_brace:]
        try:
            parsed_dict = ast.literal_eval(dict_str)
            if isinstance(parsed_dict, dict): return parsed_dict
            else: raise ValueError("Parsed content is not a dictionary.")
        except (ValueError, SyntaxError) as e: raise ValueError(f"Could not parse spec. Error: {e}")

    def run_test(self):
        """Starts the debug session."""
        self.clear_log()
        self.run_button.config(state="disabled")
        self.status_label.config(text="Running test...")
        try:
            win_spec = self._extract_and_parse_spec(self.window_spec_text.get("1.0", "end-1c"))
            elem_spec = self._extract_and_parse_spec(self.element_spec_text.get("1.0", "end-1c"))
        except ValueError as e:
            self.log_message('ERROR', f"Syntax error in spec: {e}")
            self.run_button.config(state="normal")
            self.status_label.config(text="Error in spec.")
            return
            
        self.test_thread = threading.Thread(
            target=self.debugger.run_debug_session,
            args=(win_spec, elem_spec, self.on_test_complete),
            daemon=True
        )
        self.test_thread.start()

    def on_test_complete(self, result_bundle):
        """
        Callback executed when the debug session finishes.
        """
        self.after(0, self._update_gui_on_test_complete, result_bundle)
        
    def _update_gui_on_test_complete(self, result_bundle):
        """Safely updates the GUI from the main thread."""
        self.run_button.config(state="normal")
        self.found_elements_map.clear()
        
        results = result_bundle.get("results", [])
        search_level = result_bundle.get("level", "element")
        
        if not results:
            self.status_label.config(text="Test finished. No elements found.")
            return

        if len(results) == 1:
            self.selected_element = results[0]
            self.selected_element_type = search_level
            self.highlight_element(self.selected_element)
            self.get_spec_button.config(state="normal")
            self.status_label.config(text="Test finished. Found 1 unique element.")
        
        else:
            self.status_label.config(text=f"Test finished. Found {len(results)} ambiguous elements. Please select one.")
            # *** FIX: Make result population robust ***
            for elem in results:
                try:
                    title = elem.window_text()[:100]
                except Exception:
                    title = "[Error getting title]"
                
                try:
                    ctype = elem.control_type()
                except Exception:
                    ctype = "[Error]"

                try:
                    auto_id = elem.automation_id()
                except Exception:
                    auto_id = "[Error]"
                
                item_id = self.results_tree.insert("", "end", values=(title, ctype, auto_id))
                self.found_elements_map[item_id] = (elem, search_level)

    def on_result_selected(self, event):
        """Event handler for when a user clicks an item in the results list."""
        selected_items = self.results_tree.selection()
        if not selected_items: return
        
        selected_id = selected_items[0]
        element_data = self.found_elements_map.get(selected_id)
        
        if element_data:
            self.selected_element, self.selected_element_type = element_data
            self.highlight_element(self.selected_element)
            self.get_spec_button.config(state="normal")
            self.status_label.config(text=f"Selected: {self.selected_element.window_text()[:50]}...")

    def highlight_element(self, element):
        """Draws a red rectangle around the specified element."""
        if self.highlighter: self.highlighter.destroy()
        try: rect = element.rectangle()
        except Exception as e:
            self.log_message('ERROR', f"Could not get coordinates to highlight: {e}")
            return

        self.highlighter = tk.Toplevel(self)
        self.highlighter.overrideredirect(True)
        self.highlighter.wm_attributes("-topmost", True, "-disabled", True, "-transparentcolor", "white")
        self.highlighter.geometry(f'{rect.width()}x{rect.height()}+{rect.left}+{rect.top}')
        
        canvas = tk.Canvas(self.highlighter, bg='white', highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(2, 2, rect.width()-2, rect.height()-2, outline="red", width=4)
        
        self.highlighter.after(3000, self.highlighter.destroy)

    def show_full_spec_window(self):
        """Opens a new window to display the full spec of the selected element."""
        if not self.selected_element:
            self.log_message("ERROR", "No element selected to get spec from.")
            return
            
        spec_window = tk.Toplevel(self)
        spec_window.title("Full Specification")
        spec_window.geometry("600x600")
        spec_window.transient(self)
        spec_window.grab_set()

        full_properties = self.debugger.get_element_details(self.selected_element)
        
        spec_name = f"{self.selected_element_type}_spec"
        spec_str = ui_shared_logic.format_spec_to_string(full_properties, spec_name)
        
        text_area = scrolledtext.ScrolledText(spec_window, wrap="word", font=("Courier New", 10))
        text_area.pack(fill="both", expand=True, padx=10, pady=5)
        text_area.insert("1.0", spec_str)
        text_area.config(state="disabled")
        
        button_frame = ttk.Frame(spec_window)
        button_frame.pack(pady=10)
        
        def copy_and_close():
            self.clipboard_clear()
            self.clipboard_append(spec_str)
            spec_window.destroy()

        copy_button = ttk.Button(button_frame, text="📋 Copy and Close", command=copy_and_close)
        copy_button.pack()

# ======================================================================
#                      DEBUGGER LOGIC CLASS
# ======================================================================
class SelectorDebugger:
    def __init__(self, log_callback):
        self.log = log_callback
        self.desktop = Desktop(backend='uia')
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.log('ERROR', f"Fatal error initializing COM: {e}")
            raise
        self.finder = ui_shared_logic.ElementFinder(
            uia_instance=self.uia, tree_walker=self.tree_walker, log_callback=self.log
        )

    def run_debug_session(self, window_spec, element_spec, on_complete_callback):
        """Runs a full debug session and calls back with a result bundle."""
        self.log('HEADER', "--- STARTING DEBUG SESSION ---")
        result_bundle = {"results": [], "level": "element"}
        try:
            self.log('INFO', "--- Step 1: Searching for WINDOW ---")
            windows = self.finder.find(lambda: self.desktop.windows(), window_spec)
            
            if len(windows) == 1:
                target_window = windows[0]
                self.log('SUCCESS', f"Found 1 unique window: '{target_window.window_text()}'")
                if element_spec:
                    self.log('INFO', "--- Step 2: Searching for ELEMENT inside window ---")
                    elements = self.finder.find(lambda: target_window.descendants(), element_spec)
                    result_bundle["results"] = elements
                    result_bundle["level"] = "element"
                else:
                    result_bundle["results"] = [target_window]
                    result_bundle["level"] = "window"
            elif len(windows) > 1:
                self.log('ERROR', f"Found {len(windows)} ambiguous windows. Please refine window_spec.")
                result_bundle["results"] = windows
                result_bundle["level"] = "window"
            else:
                self.log('ERROR', "No window found matching the specified criteria.")
        except Exception as e:
            self.log('ERROR', f"An unexpected error occurred: {e}")
            logging.exception("Full traceback in console:")
            
        self.log('HEADER', "--- DEBUG SESSION FINISHED ---")
        on_complete_callback(result_bundle)
            
    def get_element_details(self, element):
        """Gets all properties of a given element."""
        self.log('DEBUG', "--- Getting full properties for selected element ---")
        return ui_shared_logic.get_all_properties(element, self.uia, self.tree_walker)

# ======================================================================
#                           ENTRY POINT
# ======================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = SpecTesterApp()
    app.mainloop()
