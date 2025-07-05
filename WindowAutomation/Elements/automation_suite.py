# automation_suite.py
# Version 1.0: The All-in-One Toolkit for UI Automation.
# Integrates Explorer, Scanner, and Debugger into a single, tabbed application.

import tkinter as tk
from tkinter import ttk, font, messagebox
import logging
import sys

# --- Import refactored tool components ---
# These files must be in the same directory and refactored to be embeddable.
try:
    from tool_explorer import ExplorerTab
    from tool_debugger import DebuggerTab
    from tool_scanner import ScannerApp
    from core_logic import PARAMETER_DEFINITIONS
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import a required tool module: {e}")
    print("Please ensure tool_explorer.py, tool_debugger.py, tool_scanner.py, and core_logic.py are in the same folder.")
    sys.exit(1)

# ======================================================================
#                      SCANNER TAB (Special Handling)
# ======================================================================

class ScannerLauncherTab(ttk.Frame):
    """A simple tab with a button to launch the standalone interactive scanner."""
    def __init__(self, parent, app_root):
        super().__init__(parent)
        self.app_root = app_root

        # Center the button in the frame
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
            self.app_root.withdraw()
            # The scanner is a Toplevel window that can run on its own.
            scanner_app = ScannerApp()
            # This makes the main loop wait until the scanner window is closed.
            scanner_app.wait_window()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch scanner: {e}")
        finally:
            # This will run after the scanner window is closed, whether normally or by error.
            self.app_root.deiconify()
            self.app_root.focus_force()

# ======================================================================
#                      REFERENCE TAB
# ======================================================================

class ReferenceTab(ttk.Frame):
    """A tab to display all available parameters and their descriptions."""
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Create Treeview for parameters ---
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = ("Parameter", "Description")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.tree.heading("Parameter", text="Parameter Name")
        self.tree.heading("Description", text="Description")
        self.tree.column("Parameter", width=250, anchor='w')
        self.tree.column("Description", width=600, anchor='w')
        
        # --- Scrollbars ---
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        h_scrollbar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.tree.configure(xscrollcommand=h_scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")

        # --- Populate Data ---
        self.populate_data()

    def populate_data(self):
        """Fills the treeview with parameter definitions."""
        categories = {
            "PWA": "pwa_", "WIN32": "win32_", "State": "state_", "Geometry": "geo_",
            "Process": "proc_", "Relational": "rel_", "UIA Patterns": "uia_"
        }
        
        # Sort parameters alphabetically
        sorted_params = sorted(PARAMETER_DEFINITIONS.items())

        # Group by category
        for cat_name, cat_prefix in categories.items():
            category_id = self.tree.insert("", "end", values=(f"--- {cat_name} Properties ---", ""), tags=('category',))
            for param, desc in sorted_params:
                if param.startswith(cat_prefix):
                    self.tree.insert(category_id, "end", values=(param, desc))
        
        # Configure tag for styling category rows
        self.tree.tag_configure('category', background='#e0e0e0', font=('Segoe UI', 10, 'bold'))


# ======================================================================
#                      MAIN APPLICATION
# ======================================================================

class AutomationSuiteApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Automation Suite v1.0 (by KNT15083)")
        self.geometry("1200x800")

        # --- Style Configuration ---
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TNotebook.Tab", font=('Segoe UI', 10, 'bold'), padding=[10, 5])
        style.configure("TButton", padding=5)
        style.configure("TLabelframe.Label", font=('Segoe UI', 11, 'bold'))
        style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'))

        # --- Create Main Widgets ---
        self.create_widgets()

    def create_widgets(self):
        # --- Status Bar ---
        status_frame = ttk.Frame(self, relief='sunken', padding=2)
        status_frame.pack(side='bottom', fill='x')
        ttk.Label(status_frame, text="© KNT15083").pack(side='right', padx=5)
        self.status_label = ttk.Label(status_frame, text="Welcome to the Automation Suite!")
        self.status_label.pack(side='left', padx=5)

        # --- Notebook for Tabs ---
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Create and Add Tabs in the correct order ---
        explorer_tab = ExplorerTab(notebook, self.status_label)
        scanner_tab = ScannerLauncherTab(notebook, self)
        debugger_tab = DebuggerTab(notebook, self.status_label)
        reference_tab = ReferenceTab(notebook)

        notebook.add(explorer_tab, text=" Window Explorer ")
        notebook.add(scanner_tab, text=" Interactive Scan ")
        notebook.add(debugger_tab, text=" Selector Debugger ")
        notebook.add(reference_tab, text=" Parameter Reference ")

if __name__ == "__main__":
    # Setup basic logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    
    app = AutomationSuiteApp()
    app.mainloop()
