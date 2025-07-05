# core_controller.py
# Provides the main class for executing UI actions like clicks, text input, etc.
# Renamed from ui_controller.py and imports cleaned up.

import logging
import time
import threading
import sys

# --- Required Libraries ---
try:
    import win32api
    import win32con
    import pyperclip
    from pynput import mouse, keyboard
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto import Desktop
    import comtypes
    from comtypes.gen import UIAutomationClient as UIA
except ImportError as e:
    print(f"Error importing libraries, please install: {e}")
    print("Suggestion: pip install pynput pywinauto pyperclip comtypes")
    sys.exit(1)

# --- Configure logging ---
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# --- Import refactored components ---
try:
    # Standard import path when used within a package
    from . import core_logic
    from .ui_notifier import StatusNotifier
except ImportError:
    # Fallback for standalone execution
    try:
        import core_logic
        from ui_notifier import StatusNotifier
    except ImportError:
        print("CRITICAL ERROR: 'core_logic.py' and 'ui_notifier.py' must be in the same directory.")
        sys.exit(1)


# --- Custom Exception Definitions ---
class UIActionError(Exception): pass
class WindowNotFoundError(UIActionError): pass
class ElementNotFoundFromWindowError(UIActionError): pass
class AmbiguousElementError(UIActionError): pass

def create_notifier_callback(notifier_instance):
    """Creates a callback function from a StatusNotifier instance."""
    if not notifier_instance or not isinstance(notifier_instance, StatusNotifier):
        return None
    def event_handler(event_type, message, **kwargs):
        notifier_instance.update_status(
            text=message, style=event_type, duration=kwargs.get('duration')
        )
    return event_handler

# ======================================================================
#                      DEFAULT CONFIGURATION
# ======================================================================
DEFAULT_CONTROLLER_CONFIG = {
    'backend': 'uia',
    'human_interruption_detection': False,
    'human_cooldown_period': 5,
    'secure_mode': False,
    'default_timeout': 10,
    'default_retry_interval': 0.5
}

class UIController:
    GETTABLE_PROPERTIES = {'text', 'texts', 'value', 'is_toggled'}.union(core_logic.SUPPORTED_FILTER_KEYS)
    BACKGROUND_SAFE_ACTIONS = {'set_text', 'send_message_text'}
    SENSITIVE_ACTIONS = {'paste_text', 'type_keys', 'set_text'}
    VALID_ACTIONS = {'click', 'double_click', 'right_click', 'focus', 'invoke', 'toggle',
                     'select', 'set_text', 'paste_text', 'type_keys', 'send_message_text'}

    def __init__(self, notifier=None, event_callback=None, **kwargs):
        self.logger = logging.getLogger(self.__class__.__name__)
        if event_callback:
            self.event_callback = event_callback
        elif notifier and StatusNotifier:
            self.event_callback = create_notifier_callback(notifier)
        else:
            self.event_callback = None
        
        self.config = {**DEFAULT_CONTROLLER_CONFIG, **kwargs}
        self.desktop = Desktop(backend=self.config['backend'])
        self._last_human_activity_time = time.time() - self.config['human_cooldown_period']
        self._is_bot_acting = False
        self._bot_acting_lock = threading.Lock()
        
        try:
            self.uia = comtypes.client.CreateObject(UIA.CUIAutomation)
            self.tree_walker = self.uia.ControlViewWalker
        except (OSError, comtypes.COMError) as e:
            self.logger.critical(f"Fatal error initializing COM: {e}", exc_info=True)
            raise
        
        self.finder = core_logic.ElementFinder(
            uia_instance=self.uia,
            tree_walker=self.tree_walker,
            log_callback=self._internal_log
        )
        
        if self.config['human_interruption_detection']:
            self._start_input_listener()

    def _internal_log(self, level, message):
        """Internal log handler for ElementFinder messages."""
        self.logger.debug(f"[ElementFinder] {message}")

    def _emit_event(self, event_type, message, **kwargs):
        """Logs events and calls the external callback if available."""
        log_levels = {"info": logging.INFO, "success": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR, "process": logging.DEBUG, "debug": logging.DEBUG}
        self.logger.log(log_levels.get(event_type, logging.INFO), message)
        if self.event_callback and callable(self.event_callback):
            try:
                self.event_callback(event_type, message, **kwargs)
            except Exception as e:
                self.logger.error(f"Error executing event_callback: {e}")

    def close(self):
        """Shuts down the UIController."""
        self.logger.info("Closing UIController...")
        # In the future, this could stop the listener threads if they are not daemons.
            
    def get_next_state(self, cases, timeout=None, retry_interval=None, description=None, notify_style='info'):
        """
        Waits for one of several UI states to be true.

        Args:
            cases (dict): A dictionary where keys are state names and values are spec dicts.
            timeout (int): How long to wait in seconds.
            description (str): A custom message to log for this action.

        Returns:
            str: The name of the case that was matched, or None if timed out.
        """
        timeout = timeout if timeout is not None else self.config['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else self.config['default_retry_interval']
        display_message = description or f"Waiting for one of {len(cases)} states"
        self._emit_event(notify_style if description else 'info', display_message)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            self._wait_for_user_idle()
            for case_name, specs in cases.items():
                self.logger.debug(f"--- Checking case: '{case_name}' ---")
                try:
                    self._find_target(specs.get('window_spec'), specs.get('element_spec'), timeout=0)
                    self._emit_event('success', f"Success: '{display_message}' -> State '{case_name}' found")
                    return case_name
                except (WindowNotFoundError, ElementNotFoundFromWindowError, AmbiguousElementError) as e:
                    self.logger.debug(f"Case '{case_name}' does not match. Reason: {e}")
                    continue
            time.sleep(retry_interval)
            
        self._emit_event('warning', f"Timeout waiting for: '{display_message}'")
        return None

    def run_action(self, window_spec, element_spec=None, action=None, timeout=None, auto_activate=False, retry_interval=None, description=None, notify_style='info'):
        """
        Finds a UI element and performs an action on it.
        """
        timeout = timeout if timeout is not None else self.config['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else self.config['default_retry_interval']
        
        log_action = action
        if self.config['secure_mode'] and action and ':' in action:
            command, _ = action.split(':', 1)
            if command.lower().strip() in self.SENSITIVE_ACTIONS:
                log_action = f"{command}:********"
        
        display_message = description or f"Executing task: {log_action or 'Find Only'}"
        verbose = description is None
        self._emit_event(notify_style if description else 'info', display_message)

        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
            
            if action:
                command = action.split(':', 1)[0].lower().strip()
                if command not in self.BACKGROUND_SAFE_ACTIONS:
                    self._handle_activation(target_element, command, auto_activate)
                
                if verbose: self._emit_event('process', f"Executing action '{log_action}'...")
                self._execute_action_safely(target_element, action)
            
            self._emit_event('success', f"Success: {display_message}")
            return True
        except (UIActionError, WindowNotFoundError, ElementNotFoundFromWindowError, AmbiguousElementError) as e:
            self.logger.error(f"Error performing '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Failed: {display_message}")
            return False
        except Exception as e:
            self.logger.critical(f"Unexpected error performing '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Failed: {display_message}")
            return False

    def get_property(self, window_spec, element_spec=None, property_name=None, timeout=None, retry_interval=None, description=None, notify_style='info'):
        """
        Finds a UI element and retrieves a specified property from it.
        """
        timeout = timeout if timeout is not None else self.config['default_timeout']
        retry_interval = retry_interval if retry_interval is not None else self.config['default_retry_interval']
        display_message = description or f"Getting property '{property_name}'"
        self._emit_event(notify_style if description else 'info', display_message)

        if property_name not in self.GETTABLE_PROPERTIES:
            raise ValueError(f"Property '{property_name}' is not supported for getting.")

        try:
            self._wait_for_user_idle()
            target_element = self._find_target(window_spec, element_spec, timeout, retry_interval)
            value = core_logic.get_property_value(target_element, property_name, self.uia, self.tree_walker)
            self._emit_event('success', f"Successfully got property '{property_name}'.")
            return value
        except (UIActionError, WindowNotFoundError, ElementNotFoundFromWindowError, AmbiguousElementError) as e:
            self.logger.error(f"Error performing '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Failed: {display_message}")
            return None
        except Exception as e:
            self.logger.critical(f"Unexpected error performing '{display_message}': {e}", exc_info=True)
            self._emit_event('error', f"Failed: {display_message}")
            return None

    def _find_target(self, window_spec, element_spec=None, timeout=10, retry_interval=0.5):
        """Internal method to find a window and optionally an element within it."""
        start_time = time.time()
        last_error = ""
        while True:
            windows = self.finder.find(lambda: self.desktop.windows(), window_spec)
            
            if len(windows) == 1:
                window = windows[0]
                self.logger.debug(f"Found matching window: '{window.window_text()}' (Handle: {window.handle})")
                if not element_spec:
                    return window
                
                elements = self.finder.find(lambda: window.descendants(), element_spec)
                if len(elements) == 1:
                    element = elements[0]
                    self.logger.debug(f"Found matching element: '{element.window_text()}'")
                    return element
                elif len(elements) > 1:
                    details = [f"'{c.window_text()}'" for c in elements[:5]]
                    raise AmbiguousElementError(f"Found {len(elements)} ambiguous elements inside the window. Details: {details}")
                else:
                    last_error = f"No element matching spec found inside window '{window.window_text()}'."
            elif len(windows) > 1:
                details = [f"'{c.window_text()}'" for c in windows[:5]]
                raise AmbiguousElementError(f"Found {len(windows)} ambiguous windows. Details: {details}")
            else:
                last_error = "No window matching spec found."

            if time.time() - start_time >= timeout:
                if not element_spec and not windows:
                    raise WindowNotFoundError(f"Timeout. {last_error}")
                if element_spec and 'elements' not in locals(): # elements list was never created
                     raise WindowNotFoundError(f"Timeout. {last_error}")
                if element_spec and not elements:
                    raise ElementNotFoundFromWindowError(f"Timeout. {last_error}")
                break
            
            time.sleep(retry_interval)
        
        raise UIActionError(f"Could not find target after {timeout} seconds. Last error: {last_error}")

    def _execute_action(self, element, action_str):
        """Internal method to execute a parsed action string on an element."""
        self.logger.debug(f"Executing action '{action_str}' on element '{element.window_text()}'")
        parts = action_str.split(':', 1)
        command = parts[0].lower().strip()
        value = parts[1] if len(parts) > 1 else None
        
        try:
            if command not in self.VALID_ACTIONS:
                raise ValueError(f"Action '{command}' is not supported.")

            if command == 'click': element.click_input()
            elif command == 'double_click': element.double_click_input()
            elif command == 'right_click': element.right_click_input()
            elif command == 'focus': element.set_focus()
            elif command == 'invoke': element.invoke()
            elif command == 'toggle': element.toggle()
            elif command in ('select', 'set_text', 'paste_text', 'type_keys', 'send_message_text'):
                if value is None:
                    raise ValueError(f"Action '{command}' requires a value.")
                if command == 'select': element.select(value)
                elif command == 'set_text': element.set_edit_text(value)
                elif command == 'paste_text':
                    pyperclip.copy(value)
                    element.type_keys('^a^v', pause=0.1) 
                elif command == 'type_keys':
                    element.type_keys(value, with_spaces=True, with_newlines=True, pause=0.01)
                elif command == 'send_message_text':
                    if not element.handle:
                        raise UIActionError("Action 'send_message_text' requires the element to have a handle.")
                    win32api.SendMessage(element.handle, win32con.WM_SETTEXT, 0, value)
        except Exception as e:
            raise UIActionError(f"Execution of action '{action_str}' failed. Original error: {type(e).__name__} - {e}") from e
        
    def _wait_for_user_idle(self):
        """Pauses execution if human activity is detected."""
        if not self.config['human_interruption_detection']:
            return
        is_paused = False
        while time.time() - self._last_human_activity_time < self.config['human_cooldown_period']:
            if not is_paused:
                self._emit_event('warning', "User activity detected! Pausing automation...")
                is_paused = True
            time.sleep(1)
        if is_paused:
            self._emit_event('success', "User is idle. Resuming automation...", duration=3)

    def _handle_activation(self, target_element, command, auto_activate):
        """Ensures the target window is active before performing foreground actions."""
        top_window = core_logic.get_top_level_window(target_element)
        if top_window and not top_window.is_active():
            if auto_activate:
                self._emit_event('info', f"Auto-activating window '{top_window.window_text()}'...")
                if top_window.is_minimized():
                    top_window.restore()
                top_window.set_focus()
                time.sleep(0.5) # Give window time to respond
            else:
                raise UIActionError(f"Window '{top_window.window_text()}' is not active. Action '{command}' requires activation.")

    def _execute_action_safely(self, element, action_str):
        """Wrapper to set a flag indicating the bot is acting, for the input listener."""
        with self._bot_acting_lock:
            self._is_bot_acting = True
        try:
            self._execute_action(element, action_str)
        finally:
            with self._bot_acting_lock:
                self._is_bot_acting = False

    def _start_input_listener(self):
        """Starts the mouse and keyboard listeners in a daemon thread."""
        listener_thread = threading.Thread(target=self._run_listeners, daemon=True)
        listener_thread.start()

    def _update_last_activity(self, *args):
        """Callback for input listeners to update the activity timestamp."""
        with self._bot_acting_lock:
            if not self._is_bot_acting:
                self._last_human_activity_time = time.time()

    def _run_listeners(self):
        """The target function for the listener thread."""
        with mouse.Listener(on_move=self._update_last_activity, on_click=self._update_last_activity, on_scroll=self._update_last_activity) as m_listener:
            with keyboard.Listener(on_press=self._update_last_activity) as k_listener:
                m_listener.join()
                k_listener.join()
