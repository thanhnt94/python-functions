# functions/app_manager.py
# --- VERSION 2.0: Refactored with an object-oriented approach. ---
# Introduces the AppManager class for stateful application lifecycle management,
# while retaining the old functions for simple, stateless operations.

import logging
import subprocess
import time
import psutil
import os

# --- Import project modules ---
try:
    # Standard import path when used within the 'functions' package
    from .core_controller import UIController
except ImportError:
    # Fallback for standalone execution or testing
    try:
        from core_controller import UIController
    except ImportError:
        print("CRITICAL ERROR: 'core_controller.py' must be in the same directory or package.")
        # Create a dummy class to prevent crashing if core_controller is not found
        class UIController:
            def __init__(self, *args, **kwargs): pass
            def check_exists(self, *args, **kwargs): return False
        print("Warning: UIController not found. AppManager will have limited functionality.")


# ======================================================================
#                      RECOMMENDED: AppManager Class
# ======================================================================

class AppManager:
    """
    Manages the lifecycle of a single application in a stateful way.
    This is the recommended approach for complex automation scenarios.
    """
    def __init__(self, name, command_line, main_window_spec, controller=None):
        """
        Initializes an application manager.

        Args:
            name (str): A user-friendly name for the application (e.g., "Teamcenter").
            command_line (str): The full command line to execute to launch the app.
            main_window_spec (dict): The spec for the application's main window,
                                     used to verify if the app is ready.
            controller (UIController, optional): An existing UIController instance. 
                                                 If None, a new one will be created.
        """
        self.name = name
        self.command = command_line
        self.main_window_spec = main_window_spec
        self.process = None  # Will store the subprocess.Popen object
        self.pid = None      # Will store the process ID
        self.logger = logging.getLogger(f"AppManager({self.name})")
        
        # Use the provided controller or create a default one for internal use
        self.controller = controller if controller else UIController()
        self.logger.info(f"AppManager for '{self.name}' initialized.")

    def is_running(self):
        """
        Checks if the managed application process is currently running.
        
        Returns:
            bool: True if the process is running, False otherwise.
        """
        if self.pid and psutil.pid_exists(self.pid):
            # Verify that the running process has the same name, in case the PID was recycled
            try:
                p = psutil.Process(self.pid)
                # Check if the process name from the command matches the running process
                # This handles cases where the command is a path like "C:\...\app.exe"
                expected_exe = os.path.basename(self.command.strip('"').split()[0])
                if p.name().lower() == expected_exe.lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        return False

    def launch(self, wait_ready=True, timeout=60):
        """
        Launches the application.

        Args:
            wait_ready (bool, optional): If True, the method will wait until the main
                                         window of the application appears. Defaults to True.
            timeout (int, optional): The maximum time in seconds to wait for the main
                                     window to appear. Defaults to 60.

        Returns:
            bool: True if the launch was successful (and window appeared, if waited for),
                  False otherwise.
        """
        if self.is_running():
            self.logger.warning(f"Application '{self.name}' is already running with PID {self.pid}. Not launching again.")
            return True

        self.logger.info(f"Launching '{self.name}' with command: {self.command}")
        try:
            # Use Popen for non-blocking execution
            self.process = subprocess.Popen(self.command, shell=True)
            self.pid = self.process.pid
            self.logger.info(f"'{self.name}' process started with PID: {self.pid}")

            if wait_ready:
                self.logger.info(f"Waiting for main window to be ready (timeout: {timeout}s)...")
                if self.controller.check_exists(window_spec=self.main_window_spec, timeout=timeout):
                    self.logger.info(f"Main window for '{self.name}' found. Launch successful.")
                    return True
                else:
                    self.logger.error(f"Timeout: Main window for '{self.name}' did not appear within {timeout} seconds.")
                    self.kill() # Clean up the zombie process if the window never appeared
                    return False
            
            return True # Launch successful without waiting
        except Exception as e:
            self.logger.error(f"Failed to launch '{self.name}': {e}", exc_info=True)
            self.process = None
            self.pid = None
            return False

    def kill(self):
        """

        Terminates the managed application process forcefully.
        """
        if not self.is_running():
            self.logger.info(f"Application '{self.name}' is not running. No action needed.")
            return

        self.logger.warning(f"Attempting to terminate '{self.name}' (PID: {self.pid})...")
        try:
            parent = psutil.Process(self.pid)
            # Terminate all children first, then the parent
            for child in parent.children(recursive=True):
                self.logger.debug(f"Terminating child process {child.pid}")
                child.kill()
            parent.kill()
            self.logger.info(f"Successfully terminated '{self.name}' and its children.")
        except psutil.NoSuchProcess:
            self.logger.warning(f"Process with PID {self.pid} no longer exists.")
        except Exception as e:
            self.logger.error(f"An error occurred while trying to kill '{self.name}': {e}", exc_info=True)
        finally:
            self.process = None
            self.pid = None


# ======================================================================
#                      STATELESS UTILITY FUNCTIONS
# ======================================================================
# These are kept for simple, one-off tasks or for backward compatibility.

def launch_app(command_line):
    """
    Launches an application in a simple, non-blocking way.
    Note: This is a stateless function. For better control, use the AppManager class.
    """
    logging.info(f"Stateless launch: Executing command '{command_line}'")
    try:
        subprocess.Popen(command_line, shell=True)
        return True
    except Exception as e:
        logging.error(f"Stateless launch failed: {e}", exc_info=True)
        return False

def is_app_running(process_name):
    """
    Checks if any process with the given name is running.
    
    Args:
        process_name (str): The name of the process executable (e.g., "notepad.exe").

    Returns:
        bool: True if at least one process with that name is running.
    """
    return any(p.name().lower() == process_name.lower() for p in psutil.process_iter(['name']))

def kill_app(process_name=None, pwa_title=None, pwa_title_icontains=None):
    """
    Forcefully terminates all processes matching the given criteria.
    This is a broad and forceful method. Use with caution.

    Args:
        process_name (str, optional): The name of the process to kill (e.g., "chrome.exe").
        pwa_title (str, optional): Not used for killing processes, included for legacy reasons.
        pwa_title_icontains (str, optional): Not used, included for legacy reasons.
    """
    if not process_name:
        logging.warning("kill_app called without a process_name. No action taken.")
        return

    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == process_name.lower():
            try:
                logging.warning(f"Killing process '{proc.info['name']}' with PID {proc.info['pid']}")
                p = psutil.Process(proc.info['pid'])
                for child in p.children(recursive=True):
                    child.kill()
                p.kill()
                killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logging.error(f"Failed to kill process {proc.info['pid']}: {e}")
    
    if killed_count > 0:
        logging.info(f"Successfully killed {killed_count} process(es) named '{process_name}'.")
    else:
        logging.info(f"No running processes named '{process_name}' were found.")
