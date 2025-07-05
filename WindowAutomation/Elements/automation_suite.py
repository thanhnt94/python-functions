# automation_suite.py
# Version 1.3: The All-in-One Toolkit for UI Automation.
# The Reference Tab is now a complete "all-in-one" document, data-driven from core_logic.py.

import tkinter as tk
from tkinter import ttk, font, messagebox
import logging
import sys

# --- Import refactored tool components ---
try:
    from tool_explorer import ExplorerTab
    from tool_debugger import DebuggerTab
    from tool_scanner import ScannerApp
    # Import all definitions from the single source of truth
    from core_logic import PARAMETER_DEFINITIONS, OPERATOR_DEFINITIONS, ACTION_DEFINITIONS
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import a required tool module: {e}")
    print("Please ensure tool_explorer.py, tool_debugger.py, tool_scanner.py, and core_logic.py are in the same folder.")
    sys.exit(1)

# ======================================================================
#                      SCANNER TAB (Special Handling)
# ======================================================================

class ScannerLauncherTab(ttk.Frame):
    """A simple tab with a button to launch the standalone interactive scanner."""
    def __init__(self, parent, suite_app):
        super().__init__(parent)
        self.suite_app = suite_app

        self.pack(fill="both", expand=True)
        container = ttk.Frame(self)
        container.place(relx=0.5, rely=0.5, anchor='center')

        label = ttk.Label(
            container,
            text="Launch the interactive scanner in a separate window.\n\nPress F8 to scan the element under your cursor.",
            justify='center',
            font=('Segoe UI', 11)
        )
        label.pack(pady=(0, 20))

        start_button = ttk.Button(
            container,
            text="Start Interactive Scan",
            command=self.launch_scanner,
            style="TButton"
        )
        start_button.pack(ipady=10, ipadx=20)

    def launch_scanner(self):
        """Hides the main suite window and launches the scanner app."""
        try:
            self.suite_app.withdraw()
            scanner_app = ScannerApp(suite_app=self.suite_app)
            scanner_app.wait_window()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch scanner: {e}")
        finally:
            self.suite_app.deiconify()
            self.suite_app.focus_force()

# ======================================================================
#                      REFERENCE TAB
# ======================================================================

class ReferenceTab(ttk.Frame):
    """A tab to display all available parameters and their descriptions."""
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=5, pady=5)

        # Use a PanedWindow to allow resizing between the tables
        main_pane = ttk.PanedWindow(self, orient='vertical')
        main_pane.pack(fill='both', expand=True)

        # --- Parameters Table ---
        params_frame = ttk.LabelFrame(main_pane, text="Parameters Reference")
        main_pane.add(params_frame, weight=2)
        self.create_parameters_table(params_frame)
        self.populate_parameters_data()

        # --- Operators Table ---
        operators_frame = ttk.LabelFrame(main_pane, text="Filter Operators Reference")
        main_pane.add(operators_frame, weight=1)
        self.create_operators_table(operators_frame)
        self.populate_operators_data()
        
        # --- Actions Table ---
        actions_frame = ttk.LabelFrame(main_pane, text="Controller Actions Reference")
        main_pane.add(actions_frame, weight=1)
        self.create_actions_table(actions_frame)
        self.populate_actions_data()

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

    def populate_parameters_data(self):
        categories = {
            "PWA": "pwa_", "WIN32": "win32_", "State": "state_", "Geometry": "geo_",
            "Process": "proc_", "Relational": "rel_", "UIA Patterns": "uia_"
        }
        sorted_params = sorted(PARAMETER_DEFINITIONS.items())
        for cat_name, cat_prefix in categories.items():
            category_id = self.params_tree.insert("", "end", values=(f"--- {cat_name} Properties ---", ""), tags=('category',))
            for param, desc in sorted_params:
                if param.startswith(cat_prefix):
                    self.params_tree.insert(category_id, "end", values=(param, desc))
        self.params_tree.tag_configure('category', background='#e0e0e0', font=('Segoe UI', 10, 'bold'))

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

    def populate_operators_data(self):
        # Group operators by category
        categories = {}
        for op in OPERATOR_DEFINITIONS:
            cat = op['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(op)

        for cat_name, op_list in categories.items():
            category_id = self.operators_tree.insert("", "end", values=(f"--- {cat_name} Operators ---", "", ""), tags=('category',))
            for op in op_list:
                self.operators_tree.insert(category_id, "end", values=(op['name'], op['example'], op['desc']))

        self.operators_tree.tag_configure('category', background='#e0e0e0', font=('Segoe UI', 10, 'bold'))
        
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

    def populate_actions_data(self):
        # Group actions by category
        categories = {}
        for action in ACTION_DEFINITIONS:
            cat = action['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(action)

        for cat_name, action_list in categories.items():
            category_id = self.actions_tree.insert("", "end", values=(f"--- {cat_name} Actions ---", "", ""), tags=('category',))
            for action in action_list:
                self.actions_tree.insert(category_id, "end", values=(action['name'], action['example'], action['desc']))

        self.actions_tree.tag_configure('category', background='#e0e0e0', font=('Segoe UI', 10, 'bold'))


# ======================================================================
#                      MAIN APPLICATION
# ======================================================================

class AutomationSuiteApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Automation Suite v1.3 (by KNT15083)")
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
        self.scanner_tab = ScannerLauncherTab(self.notebook, suite_app=self)
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
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    
    app = AutomationSuiteApp()
    app.mainloop()
