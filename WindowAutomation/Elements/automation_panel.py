# functions/automation_panel.py
# Module độc lập để tạo và quản lý bảng điều khiển tự động hóa.

import tkinter as tk
import threading
import logging

class AutomationState:
    """
    Một lớp an toàn để quản lý và chia sẻ trạng thái của tiến trình tự động hóa.
    Sử dụng lock để đảm bảo an toàn khi truy cập từ nhiều luồng.
    """
    def __init__(self):
        self._status = "running"  # Trạng thái ban đầu
        self._lock = threading.Lock()

    @property
    def status(self):
        with self._lock:
            return self._status

    def pause(self):
        with self._lock:
            if self._status == "running":
                self._status = "paused"
                logging.info("Trạng thái tự động hóa đã chuyển thành PAUSED.")
                return True
        return False

    def resume(self):
        with self._lock:
            if self._status == "paused":
                self._status = "running"
                logging.info("Trạng thái tự động hóa đã chuyển thành RUNNING.")
                return True
        return False

    def stop(self):
        with self._lock:
            self._status = "stopped"
            logging.info("Trạng thái tự động hóa đã chuyển thành STOPPED.")

    def is_stopped(self):
        with self._lock:
            return self._status == "stopped"

    def is_paused(self):
        with self._lock:
            return self._status == "paused"


class AutomationControlPanel:
    """
    Tạo một cửa sổ nhỏ, cố định trên màn hình với các nút Pause, Resume, Stop.
    """
    def __init__(self, automation_state, notifier_instance=None):
        """
        Args:
            automation_state (AutomationState): Đối tượng để chia sẻ trạng thái.
            notifier_instance: (Tùy chọn) Đối tượng StatusNotifier để hiển thị thông báo.
        """
        if not isinstance(automation_state, AutomationState):
            raise TypeError("automation_state phải là một đối tượng của lớp AutomationState.")
            
        self.state = automation_state
        self.notifier = notifier_instance
        self.root = None
        
        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.title("Ctrl")
        self.root.geometry("160x55+10+10") # Vị trí góc trên bên trái
        self.root.wm_attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._stop_automation) # Dừng nếu đóng cửa sổ

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10, padx=10, fill='x', expand=True)

        self.pause_button = tk.Button(button_frame, text="⏸️ Pause", command=self._toggle_pause, width=9)
        self.pause_button.pack(side='left', padx=2)

        stop_button = tk.Button(button_frame, text="⏹️ Stop", command=self._stop_automation, width=9)
        stop_button.pack(side='left', padx=2)
        
        self.root.mainloop()

    def _toggle_pause(self):
        if self.state.status == 'running':
            if self.state.pause():
                self.pause_button.config(text="▶️ Resume")
                if self.notifier:
                    self.notifier.update_status("Đã tạm dừng bởi người dùng.", style='warning', duration=0)
        elif self.state.status == 'paused':
            if self.state.resume():
                self.pause_button.config(text="⏸️ Pause")
                if self.notifier:
                    self.notifier.update_status("Tiếp tục thực thi...", style='success', duration=3)

    def _stop_automation(self):
        self.state.stop()
        if self.notifier:
            self.notifier.update_status("Tác vụ đã bị dừng hẳn!", style='error', duration=0)
        try:
            self.pause_button.config(state='disabled')
            for widget in self.pause_button.master.winfo_children():
                if 'Stop' in widget.cget('text'):
                    widget.config(state='disabled')
            self.root.after(2000, self.root.destroy)
        except tk.TclError:
            pass

    def close(self):
        """Đóng cửa sổ điều khiển từ bên ngoài."""
        if self.root and self.root.winfo_exists():
            self.root.destroy()

