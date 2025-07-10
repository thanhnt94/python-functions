# automation_suite.py
# Version 2.2: Updated the ScannerConfigTab to use a 3-column grid layout
# for better visibility of all options, as requested.

import tkinter as tk
from tkinter import ttk, font, messagebox
import logging
import sys

# --- Import refactored tool components ---
try:
    from tool_explorer import ExplorerTab
    from tool_debugger import DebuggerTab
    # ScannerApp is the pop-up window
    from tool_scanner import ScannerApp, ALL_QUICK_SPEC_OPTIONS, DEFAULT_QUICK_SPEC_OPTIONS
    from core_logic import (
        PARAMETER_DEFINITIONS,
        OPERATOR_DEFINITIONS,
        ACTION_DEFINITIONS,
        SELECTOR_DEFINITIONS
    )
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import a required tool module: {e}")
    print("Please ensure tool_explorer.py, tool_debugger.py, tool_scanner.py, and core_logic.py are in the same folder.")
    sys.exit(1)

# ======================================================================
#                       SCANNER TAB (NEW IMPLEMENTATION)
# ======================================================================

class ScannerConfigTab(ttk.Frame):
    """A tab to configure and launch the interactive scanner."""
    def __init__(self, parent, suite_app):
        super().__init__(parent)
        self.suite_app = suite_app
        self.pack(fill="both", expand=True, padx=20, pady=20)
        self.config_vars = {}

        # --- Create the configuration UI directly in the tab ---
        style = ttk.Style(self)
        style.configure("TLabel", font=('Segoe UI', 10))
        style.configure("TButton", font=('Segoe UI', 10, 'bold'), padding=5)
        style.configure("TLabelframe.Label", font=('Segoe UI', 11, 'bold'))

        info_label = ttk.Label(self, text="Select properties for the 'Quick Spec', then launch the scanner.", wraplength=400, justify='center', font=('Segoe UI', 11))
        info_label.pack(pady=(0, 20), fill='x')

        options_container = ttk.LabelFrame(self, text="Element Properties for Quick Spec")
        options_container.pack(fill="both", expand=True, pady=5)

        # <<< GIAO DIỆN ĐÃ SỬA TẠI ĐÂY >>>
        # Sử dụng grid layout để chia thành 3 cột
        num_columns = 3
        for i, option in enumerate(ALL_QUICK_SPEC_OPTIONS):
            row = i // num_columns
            col = i % num_columns
            
            is_default = option in DEFAULT_QUICK_SPEC_OPTIONS
            var = tk.BooleanVar(value=is_default)
            self.config_vars[option] = var
            cb = ttk.Checkbutton(options_container, text=option, variable=var)
            # Dùng .grid() thay vì .pack()
            cb.grid(row=row, column=col, sticky="w", padx=10, pady=4)


        start_button = ttk.Button(
            self,
            text="Launch Interactive Scan",
            command=self.launch_scanner,
            style="TButton"
        )
        start_button.pack(pady=20, ipady=10, ipadx=20)


    def launch_scanner(self):
        """Hides the main suite window and launches the scanner app with selected config."""
        selected_keys = [key for key, var in self.config_vars.items() if var.get()]
        if not selected_keys:
            messagebox.showwarning("No Selection", "Please select at least one property for the Quick Spec.")
            return

        try:
            self.suite_app.withdraw()
            # Pass the selected keys to the ScannerApp
            scanner_app = ScannerApp(suite_app=self.suite_app, quick_spec_keys=selected_keys)
            scanner_app.wait_window()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch scanner: {e}")
        finally:
            self.suite_app.deiconify()
            self.suite_app.focus_force()

# ======================================================================
#                       REFERENCE TAB
# ======================================================================

class ReferenceTab(ttk.Frame):
    """A tab to display all available parameters, operators, actions, and selectors."""
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copy", command=self._copy_cell_value)
        self.clicked_tree = None
        self.clicked_item = None
        self.clicked_column_id = None

        main_pane = ttk.PanedWindow(self, orient='vertical')
        main_pane.pack(fill='both', expand=True)

        params_frame = ttk.LabelFrame(main_pane, text="Parameters Reference (for filtering)")
        main_pane.add(params_frame, weight=3)
        self.create_parameters_table(params_frame)
        self.populate_parameters_data()

        operators_frame = ttk.LabelFrame(main_pane, text="Filter Operators Reference")
        main_pane.add(operators_frame, weight=2)
        self.create_operators_table(operators_frame)
        self.populate_operators_data()
        
        actions_frame = ttk.LabelFrame(main_pane, text="Controller Actions Reference")
        main_pane.add(actions_frame, weight=2)
        self.create_actions_table(actions_frame)
        self.populate_actions_data()
        
        selectors_frame = ttk.LabelFrame(main_pane, text="Selector & Sorting Keys Reference")
        main_pane.add(selectors_frame, weight=2)
        self.create_selectors_table(selectors_frame)
        self.populate_selectors_data()

    def _show_context_menu(self, event, tree):
        item_id = tree.identify_row(event.y)
        if not item_id: return
        tree.selection_set(item_id)
        self.clicked_tree = tree
        self.clicked_item = item_id
        self.clicked_column_id = tree.identify_column(event.x)
        self.context_menu.post(event.x_root, event.y_root)

    def _copy_cell_value(self):
        if not all([self.clicked_tree, self.clicked_item, self.clicked_column_id]): return
        try:
            column_index = int(self.clicked_column_id.replace('#', '')) - 1
            if column_index < 0: return
            item_data = self.clicked_tree.item(self.clicked_item)
            value_to_copy = item_data.get('values')[column_index]
            if value_to_copy:
                self.clipboard_clear()
                self.clipboard_append(str(value_to_copy))
                self.update()
        except (ValueError, IndexError) as e:
            logging.error(f"Error copying from treeview: {e}")

    def create_parameters_table(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        cols = ("Parameter", "Description")
        self.params_tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.params_tree.heading("Parameter", text="Parameter Name")
        self.params_tree.heading("Description", text="Description")
        self.params_tree.column("Parameter", width=250, anchor='w')
        self.params_tree.column("Description", width=600, anchor='w')
        v_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.params_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.params_tree.configure(yscrollcommand=v_scrollbar.set)
        self.params_tree.grid(row=0, column=0, sticky="nsew")
        self.params_tree.bind("<Button-3>", lambda e: self._show_context_menu(e, self.params_tree))

    def populate_parameters_data(self):
        categories = {
            "PWA": "pwa_", "WIN32": "win32_", "State": "state_", "Geometry": "geo_",
            "Process": "proc_", "Relational": "rel_", "UIA Patterns": "uia_"
        }
        sorted_params = sorted(PARAMETER_DEFINITIONS.items())
        for cat_name, cat_prefix in categories.items():
            category_id = self.params_tree.insert("", "end", values=(f"--- {cat_name} Properties ---", ""), open=False, tags=('category',))
            for param, desc in sorted_params:
                if param.startswith(cat_prefix):
                    self.params_tree.insert(category_id, "end", values=(param, desc))
        self.params_tree.tag_configure('category', background='#d3d3d3', foreground='black', font=('Segoe UI', 10, 'bold'))

    def create_operators_table(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        cols = ("Operator", "Example", "Description")
        self.operators_tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.operators_tree.heading("Operator", text="Operator")
        self.operators_tree.heading("Example", text="Example Usage")
        self.operators_tree.heading("Description", text="Description")
        self.operators_tree.column("Operator", width=120, anchor='w')
        self.operators_tree.column("Example", width=350, anchor='w')
        self.operators_tree.column("Description", width=400, anchor='w')
        v_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.operators_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.operators_tree.configure(yscrollcommand=v_scrollbar.set)
        self.operators_tree.grid(row=0, column=0, sticky="nsew")
        self.operators_tree.bind("<Button-3>", lambda e: self._show_context_menu(e, self.operators_tree))

    def populate_operators_data(self):
        categories = {}
        for op in OPERATOR_DEFINITIONS:
            cat = op['category']
            if cat not in categories: categories[cat] = []
            categories[cat].append(op)
        for cat_name, op_list in categories.items():
            category_id = self.operators_tree.insert("", "end", values=(f"--- {cat_name} Operators ---", "", ""), open=False, tags=('category',))
            for op in op_list:
                self.operators_tree.insert(category_id, "end", values=(op['name'], op['example'], op['desc']))
        self.operators_tree.tag_configure('category', background='#d3d3d3', foreground='black', font=('Segoe UI', 10, 'bold'))
        
    def create_actions_table(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        cols = ("Action", "Example", "Description")
        self.actions_tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.actions_tree.heading("Action", text="Action Name")
        self.actions_tree.heading("Example", text="Example Usage")
        self.actions_tree.heading("Description", text="Description")
        self.actions_tree.column("Action", width=150, anchor='w')
        self.actions_tree.column("Example", width=350, anchor='w')
        self.actions_tree.column("Description", width=400, anchor='w')
        v_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.actions_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.actions_tree.configure(yscrollcommand=v_scrollbar.set)
        self.actions_tree.grid(row=0, column=0, sticky="nsew")
        self.actions_tree.bind("<Button-3>", lambda e: self._show_context_menu(e, self.actions_tree))

    def populate_actions_data(self):
        categories = {}
        for action in ACTION_DEFINITIONS:
            cat = action['category']
            if cat not in categories: categories[cat] = []
            categories[cat].append(action)
        for cat_name, action_list in categories.items():
            category_id = self.actions_tree.insert("", "end", values=(f"--- {cat_name} Actions ---", "", ""), open=False, tags=('category',))
            for action in action_list:
                self.actions_tree.insert(category_id, "end", values=(action['name'], action['example'], action['desc']))
        self.actions_tree.tag_configure('category', background='#d3d3d3', foreground='black', font=('Segoe UI', 10, 'bold'))

    def create_selectors_table(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        cols = ("Selector", "Example", "Description")
        self.selectors_tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.selectors_tree.heading("Selector", text="Selector Key")
        self.selectors_tree.heading("Example", text="Example Usage")
        self.selectors_tree.heading("Description", text="Description")
        self.selectors_tree.column("Selector", width=180, anchor='w')
        self.selectors_tree.column("Example", width=320, anchor='w')
        self.selectors_tree.column("Description", width=400, anchor='w')
        v_scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.selectors_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.selectors_tree.configure(yscrollcommand=v_scrollbar.set)
        self.selectors_tree.grid(row=0, column=0, sticky="nsew")
        self.selectors_tree.bind("<Button-3>", lambda e: self._show_context_menu(e, self.selectors_tree))

    def populate_selectors_data(self):
        self.selectors_tree.tag_configure('recommended', background='#d8e9d8', font=('Segoe UI', 9, 'bold'))
        for selector in SELECTOR_DEFINITIONS:
            tags = ('recommended',) if 'RECOMMENDED' in selector['desc'] else ()
            self.selectors_tree.insert("", "end", values=(selector['name'], selector['example'], selector['desc']), tags=tags)

# ======================================================================
#                       MAIN APPLICATION
# ======================================================================

class AutomationSuiteApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Automation Suite v2.0 (by KNT15083)")
        self.geometry("1200x800")

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TNotebook.Tab", font=('Segoe UI', 10, 'bold'), padding=[10, 5])
        style.configure("TButton", padding=5)
        style.configure("TLabelframe.Label", font=('Segoe UI', 11, 'bold'))
        style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'))

        self.create_widgets()

    def create_widgets(self):
        status_frame = ttk.Frame(self, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        self.status_label = ttk.Label(status_frame, text="Welcome to the Automation Suite!")
        self.status_label.pack(side='left', padx=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.explorer_tab = ExplorerTab(self.notebook, suite_app=self)
        # Sử dụng lớp tab cấu hình mới
        self.scanner_tab = ScannerConfigTab(self.notebook, suite_app=self)
        self.debugger_tab = DebuggerTab(self.notebook, suite_app=self)
        self.reference_tab = ReferenceTab(self.notebook)

        self.notebook.add(self.explorer_tab, text=" Window Explorer ")
        self.notebook.add(self.scanner_tab, text=" Interactive Scan ")
        self.notebook.add(self.debugger_tab, text=" Selector Debugger ")
        self.notebook.add(self.reference_tab, text=" All-in-One Reference ")

    def send_specs_to_debugger(self, window_spec, element_spec):
        """
        Receives specs from other tools and sends them to the Debugger tab.
        """
        if self.debugger_tab:
            self.debugger_tab.receive_specs(window_spec, element_spec)
            self.notebook.select(self.debugger_tab)
            self.status_label.config(text="Specifications received in Debugger.")
        else:
            messagebox.showerror("Error", "Debugger tab is not available.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    
    app = AutomationSuiteApp()
    app.mainloop()
