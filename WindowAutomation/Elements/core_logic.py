# core_logic.py
# Contains the core, shared logic and ALL definitions for the suite.
# --- VERSION 7.0: Added 'sort_by_scan_order' as the primary, most stable sorting key.
# The ElementFinder is now optimized to handle this key efficiently.

import logging
import re
from datetime import datetime

# --- Required Libraries ---
try:
    import psutil
    import win32gui
    import win32process
    import win32con
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
    from pywinauto import uia_defines
    from pywinauto.findwindows import ElementNotFoundError
except ImportError as e:
    print(f"Error importing libraries: {e}")
    print("Suggestion: pip install psutil pywin32 comtypes pywinauto")
    exit()

# Initialize logger for this module
logger = logging.getLogger(__name__)

# ======================================================================
#                      CENTRAL DEFINITIONS
# ======================================================================

# --- Property Definitions (Parameters for filtering) ---
PARAMETER_DEFINITIONS = {
    "pwa_title": "The visible text/name of the element (most important).",
    "pwa_auto_id": "Automation ID, a unique identifier for the element within the application.",
    "pwa_control_type": "The control type of the element (e.g., Button, Edit, Tree).",
    "pwa_class_name": "The Win32 class name of the element (useful for legacy apps).",
    "pwa_framework_id": "The framework that created the element (e.g., UIA, Win32, WPF).",
    "win32_handle": "The handle (unique ID) of the window managed by Windows.",
    "win32_styles": "The style flags of the window (in hex).",
    "win32_extended_styles": "The extended style flags of the window (in hex).",
    "state_is_visible": "Visibility state (True if visible).",
    "state_is_enabled": "Interaction state (True if enabled).",
    "state_is_active": "Active state (True if it is the focused window/element).",
    "state_is_minimized": "Minimized state (True if the window is minimized).",
    "state_is_maximized": "Maximized state (True if the window is maximized).",
    "state_is_focusable": "Focusable state (True if it can receive keyboard focus).",
    "state_is_password": "Password field state (True if it is a password input).",
    "state_is_offscreen": "Off-screen state (True if it is outside the visible screen area).",
    "state_is_content_element": "Is a content element, not just a decorative control.",
    "state_is_control_element": "Is an interactable control element (opposite of content).",
    "geo_bounding_rect_tuple": "The coordinate tuple (Left, Top, Right, Bottom) of the element.",
    "geo_center_point": "The center point coordinates of the element.",
    "proc_pid": "Process ID (ID of the process that owns the window).",
    "proc_thread_id": "Thread ID (ID of the thread that owns the window).",
    "proc_name": "The name of the process (e.g., 'notepad.exe').",
    "proc_path": "The full path to the process's executable file.",
    "proc_cmdline": "The command line used to launch the process.",
    "proc_create_time": "The creation time of the process (as a timestamp or string).",
    "proc_username": "The username that launched the process.",
    "rel_level": "The depth level of the element in the UI tree (0 is the root).",
    "rel_parent_handle": "The handle of the parent window (if any, 0 is the Desktop).",
    "rel_parent_title": "The name/title of the parent element.",
    "rel_labeled_by": "The name of the label element associated with this element.",
    "rel_child_count": "The number of direct child elements.",
    "uia_value": "The value of the element if it supports ValuePattern.",
    "uia_toggle_state": "The state of the element if it supports TogglePattern (On, Off, Indeterminate).",
    "uia_expand_state": "The state if it supports ExpandCollapsePattern (Collapsed, Expanded, LeafNode).",
    "uia_selection_items": "The currently selected items if it supports SelectionPattern.",
    "uia_range_value_info": "Information (Min, Max, Value) if it supports RangeValuePattern.",
    "uia_grid_cell_info": "Information (Row, Col, RowSpan, ColSpan) if it supports GridItemPattern.",
    "uia_table_row_headers": "The headers of the row if it supports TableItemPattern.",
}

# --- Operator Definitions ---
STRING_OPERATORS = {'equals', 'iequals', 'contains', 'icontains', 'in', 'regex',
                    'not_equals', 'not_iequals', 'not_contains', 'not_icontains'}
NUMERIC_OPERATORS = {'>', '>=', '<', '<='}
OPERATOR_DEFINITIONS = [
    {'category': 'String', 'name': 'equals', 'example': "'pwa_title': ('equals', 'File Explorer')", 'desc': "Matches the exact string (case-sensitive)."},
    {'category': 'String', 'name': 'iequals', 'example': "'pwa_title': ('iequals', 'file explorer')", 'desc': "Matches the exact string (case-insensitive)."},
    {'category': 'String', 'name': 'contains', 'example': "'pwa_title': ('contains', 'Explorer')", 'desc': "Checks if the string contains the substring (case-sensitive)."},
    {'category': 'String', 'name': 'icontains', 'example': "'pwa_title': ('icontains', 'explorer')", 'desc': "Checks if the string contains the substring (case-insensitive)."},
    {'category': 'String', 'name': 'in', 'example': "'proc_name': ('in', ['explorer.exe', 'notepad.exe'])", 'desc': "Checks if the value is in a list of strings."},
    {'category': 'String', 'name': 'regex', 'example': "'pwa_title': ('regex', r'File.*')", 'desc': "Matches using a regular expression."},
    {'category': 'String', 'name': 'not_equals', 'example': "'pwa_title': ('not_equals', 'Calculator')", 'desc': "Value is not exactly equal."},
    {'category': 'String', 'name': 'not_icontains', 'example': "'pwa_class_name': ('not_icontains', 'Chrome')", 'desc': "Value does not contain the substring (case-insensitive)."},
    {'category': 'Numeric', 'name': '>', 'example': "'rel_child_count': ('>', 5)", 'desc': "Greater than."},
    {'category': 'Numeric', 'name': '>=', 'example': "'rel_child_count': ('>=', 5)", 'desc': "Greater than or equal to."},
    {'category': 'Numeric', 'name': '<', 'example': "'win32_handle': ('<', 100000)", 'desc': "Less than."},
    {'category': 'Numeric', 'name': '<=', 'example': "'rel_level': ('<=', 3)", 'desc': "Less than or equal to."},
]

# --- Action Definitions ---
ACTION_DEFINITIONS = [
    {'category': 'Mouse', 'name': 'click', 'example': "action='click'", 'desc': "Performs a standard left-click."},
    {'category': 'Mouse', 'name': 'double_click', 'example': "action='double_click'", 'desc': "Performs a double left-click."},
    {'category': 'Mouse', 'name': 'right_click', 'example': "action='right_click'", 'desc': "Performs a right-click."},
    {'category': 'Keyboard', 'name': 'type_keys', 'example': "action='type_keys:Hello World!{ENTER}'", 'desc': "Types a string of text. Supports special keys like {ENTER}, {TAB}, etc."},
    {'category': 'Keyboard', 'name': 'set_text', 'example': "action='set_text:New text value'", 'desc': "Sets the text of an edit control directly. Faster than typing."},
    {'category': 'Keyboard', 'name': 'paste_text', 'example': "action='paste_text:Text from clipboard'", 'desc': "Pastes text from the clipboard (Ctrl+V)."},
    {'category': 'Keyboard', 'name': 'send_message_text', 'example': "action='send_message_text:Background text'", 'desc': "Sets text using Windows messages. Works even if window is not active."},
    {'category': 'State', 'name': 'focus', 'example': "action='focus'", 'desc': "Sets the keyboard focus to the element."},
    {'category': 'State', 'name': 'invoke', 'example': "action='invoke'", 'desc': "Invokes the default action of an element (like pressing a button)."},
    {'category': 'State', 'name': 'toggle', 'example': "action='toggle'", 'desc': "Toggles the state of a checkbox or toggle button."},
    {'category': 'State', 'name': 'select', 'example': "action='select:Item Name'", 'desc': "Selects an item in a list box, combo box, or tab control by its name."},
]

# --- Selector Definitions (for sorting and picking) ---
# Reordered to place the recommended key at the top.
SELECTOR_DEFINITIONS = [
    {'name': 'sort_by_scan_order', 'example': "'sort_by_scan_order': 2", 'desc': "RECOMMENDED. Selects the Nth element found during the scan. Most stable and predictable."},
    {'name': 'sort_by_y_pos', 'example': "'sort_by_y_pos': 1", 'desc': "Sorts elements by their Y coordinate (top to bottom). Use 1 for the topmost element."},
    {'name': 'sort_by_x_pos', 'example': "'sort_by_x_pos': -1", 'desc': "Sorts elements by their X coordinate (left to right). Use -1 for the rightmost element."},
    {'name': 'sort_by_creation_time', 'example': "'sort_by_creation_time': -1", 'desc': "Sorts windows by their creation time. Use -1 for newest, 1 for oldest."},
    {'name': 'sort_by_height', 'example': "'sort_by_height': -1", 'desc': "Sorts elements by their height. Use -1 for the tallest element."},
    {'name': 'sort_by_width', 'example': "'sort_by_width': -1", 'desc': "Sorts elements by their width. Use -1 for the widest element."},
    {'name': 'sort_by_title_length', 'example': "'sort_by_title_length': 1", 'desc': "Sorts elements by the length of their title text. Use 1 for the shortest title."},
    {'name': 'sort_by_child_count', 'example': "'sort_by_child_count': -1", 'desc': "Sorts elements by the number of direct children they have. Use -1 for the one with the most children."},
    {'name': 'z_order_index', 'example': "'z_order_index': 1", 'desc': "Selects an element based on its Z-order (drawing order). Rarely needed."},
]

# --- Property Sets ---
PWA_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('pwa_')}
WIN32_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('win32_')}
STATE_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('state_')}
GEO_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('geo_')}
PROC_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('proc_')}
REL_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('rel_')}
UIA_PROPS = {k for k in PARAMETER_DEFINITIONS if k.startswith('uia_')}

# --- Selectors and Operators ---
SORTING_KEYS = {item['name'] for item in SELECTOR_DEFINITIONS}
VALID_OPERATORS = STRING_OPERATORS.union(NUMERIC_OPERATORS)
SUPPORTED_FILTER_KEYS = PWA_PROPS | WIN32_PROPS | STATE_PROPS | GEO_PROPS | PROC_PROPS | REL_PROPS | UIA_PROPS
_CONTROL_TYPE_ID_TO_NAME = {v: k for k, v in uia_defines.IUIA().known_control_types.items()}
PROC_INFO_CACHE = {}

# ======================================================================
#                      PUBLIC UTILITY FUNCTIONS
# ======================================================================

def format_spec_to_string(spec_dict, spec_name="spec"):
    """
    Public function to format a spec dictionary into a copyable string.
    """
    if not spec_dict:
        return f"{spec_name} = {{}}"
    
    dict_to_format = {k: v for k, v in spec_dict.items() if not k.startswith('sys_') and (v or v is False or v == 0)}
    if not dict_to_format:
        return f"{spec_name} = {{}}"
        
    items_str = [f"    '{k}': {repr(v)}," for k, v in sorted(dict_to_format.items())]
    content = "\n".join(items_str)
    return f"{spec_name} = {{\n{content}\n}}"

def clean_element_spec(window_info, element_info):
    """Removes duplicate properties from the element_spec."""
    if not window_info or not element_info: return element_info
    cleaned_spec = element_info.copy()
    for key, value in list(element_info.items()):
        if key in window_info and window_info[key] == value:
            del cleaned_spec[key]
    return cleaned_spec

# ======================================================================
#                      CORE INFORMATION GETTERS
# ======================================================================

def get_process_info(pid):
    """Gets process information and caches it for performance."""
    if pid in PROC_INFO_CACHE:
        return PROC_INFO_CACHE[pid]
    if pid > 0:
        try:
            p = psutil.Process(pid)
            info = {
                'proc_name': p.name(),
                'proc_path': p.exe(),
                'proc_cmdline': ' '.join(p.cmdline()),
                'proc_create_time': datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S'),
                'proc_username': p.username()
            }
            PROC_INFO_CACHE[pid] = info
            return info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {}

def get_property_value(pwa_element, key, uia_instance=None, tree_walker=None):
    """
    Central function to get the value of a property from a pywinauto element.
    """
    prop = key.lower()
    
    if hasattr(pwa_element, 'element_info'):
        com_element = getattr(pwa_element.element_info, 'element', None)
    else:
        com_element = getattr(pwa_element, 'element', pwa_element)

    try:
        # --- PWA Properties ---
        if prop in PWA_PROPS:
            if prop == 'pwa_title': return pwa_element.window_text()
            if prop == 'pwa_class_name': return pwa_element.class_name()
            if prop == 'pwa_auto_id': return pwa_element.automation_id()
            if prop == 'pwa_control_type': return pwa_element.control_type()
            if prop == 'pwa_framework_id': return pwa_element.framework_id()

        # --- WIN32 Properties ---
        handle = pwa_element.handle
        if handle:
            if prop in WIN32_PROPS:
                if prop == 'win32_handle': return handle
                if prop == 'win32_styles': return win32gui.GetWindowLong(handle, win32con.GWL_STYLE)
                if prop == 'win32_extended_styles': return win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)
            if prop == 'proc_thread_id': return win32process.GetWindowThreadProcessId(handle)[0]
            if prop == 'rel_parent_handle': return win32gui.GetParent(handle)

        # --- State Properties ---
        if prop in STATE_PROPS:
            if prop == 'state_is_visible': return pwa_element.is_visible()
            if prop == 'state_is_enabled': return pwa_element.is_enabled()
            if prop == 'state_is_active': return pwa_element.is_active()
            if prop == 'state_is_minimized': return pwa_element.is_minimized()
            if prop == 'state_is_maximized': return pwa_element.is_maximized()
            if prop == 'state_is_focusable': return pwa_element.is_focusable()
            if prop == 'state_is_password': return pwa_element.is_password()
            if prop == 'state_is_offscreen': return pwa_element.is_offscreen()
            if prop == 'state_is_content_element': return pwa_element.is_content_element()
            if prop == 'state_is_control_element': return pwa_element.is_control_element()

        # --- Geometry Properties ---
        if prop in GEO_PROPS:
            try:
                rect = pwa_element.rectangle()
                if prop == 'geo_bounding_rect_tuple': return (rect.left, rect.top, rect.right, rect.bottom)
                if prop == 'geo_center_point':
                    mid_point = rect.mid_point()
                    return (mid_point.x, mid_point.y)
            except Exception:
                logger.debug(f"pwa_element.rectangle() failed. Trying direct COM access.")
                if com_element:
                    try:
                        com_rect = com_element.CurrentBoundingRectangle
                        if prop == 'geo_bounding_rect_tuple':
                            return (com_rect.left, com_rect.top, com_rect.right, com_rect.bottom)
                        if prop == 'geo_center_point':
                            return ((com_rect.left + com_rect.right) // 2, (com_rect.top + com_rect.bottom) // 2)
                    except (comtypes.COMError, AttributeError):
                        logger.debug(f"Direct COM access for BoundingRectangle also failed.")
                        return None
        
        # --- Process Properties ---
        if prop in PROC_PROPS:
            pid = pwa_element.process_id()
            if prop == 'proc_pid': return pid
            proc_info = get_process_info(pid)
            return proc_info.get(prop)

        # --- Relational Properties ---
        if prop in REL_PROPS:
            if prop == 'rel_child_count': return len(pwa_element.children())
            parent = pwa_element.parent()
            if prop == 'rel_parent_title': return parent.window_text() if parent else ''
            if prop == 'rel_labeled_by': return pwa_element.labeled_by() if hasattr(pwa_element, 'labeled_by') else ''
            
            if prop == 'rel_level' and com_element and tree_walker and uia_instance:
                level = 0
                root = uia_instance.GetRootElement()
                if comtypes.client.GetBestInterface(com_element) == comtypes.client.GetBestInterface(root):
                    return 0

                current = com_element
                while True:
                    parent = tree_walker.GetParentElement(current)
                    if not parent: break
                    level += 1
                    if comtypes.client.GetBestInterface(parent) == comtypes.client.GetBestInterface(root):
                        break
                    current = parent
                    if level > 50:
                        logger.warning("Reached max depth (50) when calculating rel_level.")
                        break
                return level

        # --- UIA Properties ---
        if prop in UIA_PROPS and com_element and uia_instance:
            if prop == 'uia_value':
                pattern = com_element.GetCurrentPattern(UIA.UIA_ValuePatternId)
                if pattern: return pattern.QueryInterface(UIA.IUIAutomationValuePattern).CurrentValue
            if prop == 'uia_toggle_state':
                pattern = com_element.GetCurrentPattern(UIA.UIA_TogglePatternId)
                if pattern: return pattern.QueryInterface(UIA.IUIAutomationTogglePattern).CurrentToggleState.name
            if prop == 'uia_expand_state':
                pattern = com_element.GetCurrentPattern(UIA.UIA_ExpandCollapsePatternId)
                if pattern: return pattern.QueryInterface(UIA.IUIAutomationExpandCollapsePattern).CurrentExpandCollapseState.name
            
        return None
    except (comtypes.COMError, AttributeError, Exception) as e:
        logger.debug(f"Error getting property '{prop}': {type(e).__name__} - {e}")
        return None

def get_all_properties(pwa_element, uia_instance=None, tree_walker=None):
    all_props = {}
    for key in SUPPORTED_FILTER_KEYS:
        value = get_property_value(pwa_element, key, uia_instance, tree_walker)
        if value or value is False or value == 0:
            all_props[key] = value
    if 'pwa_title' not in all_props:
        try: all_props['pwa_title'] = pwa_element.window_text()
        except Exception: pass
    if 'pwa_class_name' not in all_props:
        try: all_props['pwa_class_name'] = pwa_element.class_name()
        except Exception: pass
    return all_props

def get_top_level_window(pwa_element):
    try:
        return pwa_element.top_level_parent()
    except (AttributeError, RuntimeError):
        return None

# ======================================================================
#                      CENTRAL ELEMENT FINDER CLASS
# ======================================================================

class ElementFinder:
    def __init__(self, uia_instance, tree_walker, log_callback=None):
        def dummy_log(level, message): pass
        self.log = log_callback if callable(log_callback) else dummy_log
        self.uia = uia_instance
        self.tree_walker = tree_walker

    def find(self, search_pool, spec):
        self.log('DEBUG', f"Starting search with spec: {spec}")
        try:
            candidates = search_pool()
        except Exception as e:
            self.log('ERROR', f"Error getting initial list of candidates: {e}")
            return []
        self.log('DEBUG', f"Found {len(candidates)} initial candidates.")
        if not candidates: return []
        filter_spec, selector_spec = self._split_spec(spec)
        if filter_spec:
            self.log('INFO', f"Applying filters to {len(candidates)} candidates...")
            candidates = self._apply_filters(candidates, filter_spec)
            if not candidates:
                self.log('INFO', "No candidates left after filtering.")
                return []
            self.log('SUCCESS', f"Remaining {len(candidates)} candidates after filtering.")
        if selector_spec:
            self.log('INFO', f"Applying selectors to {len(candidates)} candidates...")
            candidates = self._apply_selectors(candidates, selector_spec)
            if not candidates:
                self.log('INFO', "No candidates left after selecting.")
                return []
        return candidates

    def _split_spec(self, spec):
        filter_spec = {k: v for k, v in spec.items() if k not in SORTING_KEYS}
        selector_spec = {k: v for k, v in spec.items() if k in SORTING_KEYS}
        return filter_spec, selector_spec

    def _apply_filters(self, elements, spec):
        if not spec: return elements
        current_elements = list(elements)
        for key, criteria in spec.items():
            self.log('FILTER', f"Filtering by: {{'{key}': {repr(criteria)}}}")
            initial_count = len(current_elements)
            kept_elements = []
            for elem in current_elements:
                actual_value = get_property_value(elem, key, self.uia, self.tree_walker)
                matches = self._check_condition(actual_value, criteria)
                log_msg_parts = []
                if matches:
                    log_msg_parts.append(("[KEEP] ", 'KEEP'))
                    log_msg_parts.append((f"'{elem.window_text()}' because '{key}' with value '{actual_value}' matches.", 'DEBUG'))
                else:
                    log_msg_parts.append(("[DISCARD] ", 'DISCARD'))
                    log_msg_parts.append((f"'{elem.window_text()}' because '{key}' with value '{actual_value}' does not match.", 'DEBUG'))
                self.log('DEBUG', log_msg_parts)
                if matches: kept_elements.append(elem)
            self.log('INFO', f"  -> Result: Kept {len(kept_elements)}/{initial_count} candidates.")
            if not kept_elements: return []
            current_elements = kept_elements
        return current_elements

    def _check_condition(self, actual_value, criteria):
        is_operator_syntax = (isinstance(criteria, tuple) and 
                              len(criteria) == 2 and 
                              str(criteria[0]).lower() in VALID_OPERATORS)
        if is_operator_syntax:
            operator, target_value = criteria
            op = str(operator).lower()
            if actual_value is None: return False
            if op in STRING_OPERATORS:
                str_actual, str_target = str(actual_value), str(target_value)
                if op == 'equals': return str_actual == str_target
                if op == 'iequals': return str_actual.lower() == str_target.lower()
                if op == 'contains': return str_target in str_actual
                if op == 'icontains': return str_target.lower() in str_actual.lower()
                if op == 'in': return str_actual in target_value
                if op == 'regex': return re.search(str_target, str_actual) is not None
                if op == 'not_equals': return str_actual != str_target
                if op == 'not_iequals': return str_actual.lower() != str_target.lower()
                if op == 'not_contains': return str_target not in str_actual
                if op == 'not_icontains': return str_target.lower() not in str_actual.lower()
            if op in NUMERIC_OPERATORS:
                try:
                    num_actual, num_target = float(actual_value), float(target_value)
                    if op == '>': return num_actual > num_target
                    if op == '>=': return num_actual >= num_target
                    if op == '<': return num_actual < num_target
                    if op == '<=': return num_actual <= num_target
                except (ValueError, TypeError): return False
        else:
            return actual_value == criteria
        return False

    def _apply_selectors(self, candidates, selectors):
        if not candidates: return []
        
        # The 'sort_by_scan_order' is the most direct and efficient selector.
        # It uses the natural order of the filtered list.
        if 'sort_by_scan_order' in selectors:
            index = selectors['sort_by_scan_order']
            self.log('FILTER', f"Selecting by scan order index: {index}")
            final_index = index - 1 if index > 0 else index
            try:
                selected = candidates[final_index]
                self.log('SUCCESS', f"Selected candidate by scan order: '{selected.window_text()}'")
                return [selected]
            except IndexError:
                self.log('ERROR', f"Index selection={final_index} is out of range for {len(candidates)} candidates.")
                return []

        # For other sorting keys, sort the list before selecting.
        sorted_candidates = list(candidates)
        for key in [k for k in selectors if k != 'z_order_index']:
            index = selectors[key]
            self.log('FILTER', f"Sorting by: '{key}' (Order: {'Descending' if index < 0 else 'Ascending'})")
            sort_key_func = self._get_sort_key_function(key)
            if sort_key_func:
                sorted_candidates.sort(key=lambda e: (sort_key_func(e) is None, sort_key_func(e)), reverse=(index < 0))
        
        final_index = 0
        if 'z_order_index' in selectors:
            final_index = selectors['z_order_index']
        elif selectors:
            last_selector_key = list(selectors.keys())[-1]
            final_index = selectors[last_selector_key]
            final_index = final_index - 1 if final_index > 0 else final_index
        
        self.log('FILTER', f"Selecting item at final index: {final_index}")
        try:
            selected = sorted_candidates[final_index]
            self.log('SUCCESS', f"Selected candidate after sorting: '{selected.window_text()}'")
            return [selected]
        except IndexError:
            self.log('ERROR', f"Index selection={final_index} is out of range for {len(sorted_candidates)} candidates.")
            return []

    def _get_sort_key_function(self, key):
        if key == 'sort_by_creation_time':
            return lambda e: get_property_value(e, 'proc_create_time') or datetime.min.strftime('%Y-%m-%d %H:%M:%S')
        if key == 'sort_by_title_length':
            return lambda e: len(get_property_value(e, 'pwa_title') or '')
        if key == 'sort_by_child_count':
            return lambda e: get_property_value(e, 'rel_child_count') or 0
        if key in ['sort_by_y_pos', 'sort_by_x_pos', 'sort_by_width', 'sort_by_height']:
            def get_rect_prop(elem, prop_key):
                rect = get_property_value(elem, 'geo_bounding_rect_tuple')
                if not rect: return 0
                if prop_key == 'sort_by_y_pos': return rect[1]
                if prop_key == 'sort_by_x_pos': return rect[0]
                if prop_key == 'sort_by_width': return rect[2] - rect[0]
                if prop_key == 'sort_by_height': return rect[3] - rect[1]
            return lambda e: get_rect_prop(e, key)
        return None
