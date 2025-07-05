# core_app_manager.py
# Contains utility functions for process management: launching and closing applications.
# Renamed from app_manager.py.

import logging
import subprocess
import shlex
import os
import time
import psutil # Required library for working with processes
from pywinauto import Desktop # Added import to find windows

# Configure logging for this module
logger = logging.getLogger(__name__)

def launch_app(command_line, close_existing=False):
    """
    Launches an application using a command line.

    Args:
        command_line (str): The command line to execute.
        close_existing (bool): If True, closes all old processes
                               of this application before running a new one.
    """
    logger.info(f"Preparing to execute command: {command_line}")
    try:
        # Use shlex.split to safely handle commands with spaces and parameters
        args = shlex.split(command_line)
        
        # UPGRADE: Re-add logic to close existing processes
        if close_existing:
            # Get the executable name from the command line (e.g., 'notepad.exe')
            executable_name = os.path.basename(args[0])
            logger.info(f"Requesting to close old '{executable_name}' processes...")
            
            # Call the kill_app function to perform the closing
            kill_app(process_name=executable_name)
            
            # Wait a moment for the OS to handle the process termination
            time.sleep(1)
            logger.info("Sent command to close old processes.")

        # Start the new process and do not wait for it to complete
        subprocess.Popen(args)
        
        logger.info("Launch command sent successfully.")
        
    except FileNotFoundError:
        logger.error(f"Error: Executable file not found in command: '{command_line}'")
    except Exception as e:
        logger.error(f"Could not launch application: {e}", exc_info=True)

def kill_app(process_name=None, pid=None, pwa_title=None):
    """
    Forcefully closes one or more processes of an application.

    Args:
        process_name (str, optional): The name of the process to close (e.g., "notepad.exe").
        pid (int, optional): The ID of a specific process to close.
        pwa_title (str, optional): A part or the whole window title.
                                   Will close all processes with a window matching the title.
    """
    if not process_name and not pid and not pwa_title:
        logger.warning("kill_app: Must provide process_name, pid, or pwa_title to close an application.")
        return

    try:
        # Prioritize closing by window title
        if pwa_title:
            logger.info(f"Finding and closing windows with title containing: '{pwa_title}'...")
            pids_to_kill = set()
            desktop = Desktop(backend='uia')
            for window in desktop.windows():
                try:
                    # Case-insensitive comparison and substring check
                    if pwa_title.lower() in window.window_text().lower():
                        pids_to_kill.add(window.process_id())
                except Exception:
                    continue
            
            if not pids_to_kill:
                logger.info(f"No window found with a title matching '{pwa_title}'.")
                return

            logger.info(f"Found {len(pids_to_kill)} processes to close based on title: {pids_to_kill}")
            for p_id in pids_to_kill:
                try:
                    p = psutil.Process(p_id)
                    p.terminate()
                except psutil.NoSuchProcess:
                    continue
            
            gone, alive = psutil.wait_procs([psutil.Process(p_id) for p_id in pids_to_kill if psutil.pid_exists(p_id)], timeout=3)
            for p in alive:
                logger.warning(f"Could not terminate PID {p.pid} gracefully, attempting to kill...")
                p.kill()

        # Close by process name
        elif process_name:
            logger.info(f"Sending command to close all processes named: '{process_name}'...")
            # Using taskkill is often more robust for closing by name
            kill_command = f"taskkill /f /im {process_name} > nul 2>&1"
            result = os.system(kill_command)
            
            if result == 0:
                 logger.info(f"Successfully sent command to close '{process_name}' processes.")
            else:
                 logger.info(f"No running process found with the name '{process_name}'.")

        # Close by specific PID
        elif pid:
            logger.info(f"Attempting to close process with PID: {pid}...")
            p = psutil.Process(pid)
            p.terminate()
            gone, alive = psutil.wait_procs([p], timeout=3)
            
            if gone:
                logger.info(f"Successfully terminated process PID {pid}.")
            elif alive:
                logger.warning(f"Could not terminate PID {pid} gracefully, attempting to kill...")
                p.kill()
                logger.info(f"Forcefully killed process PID {pid}.")

    except psutil.NoSuchProcess:
        logger.error(f"Error: No process found with the provided PID.")
    except Exception as e:
        logger.error(f"Error while closing application: {e}", exc_info=True)
