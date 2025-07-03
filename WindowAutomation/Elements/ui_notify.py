
# Elements/status_notifier.py
# Module độc lập để quản lý cửa sổ thông báo trạng thái.

import tkinter as tk
import queue
import threading

class StatusNotifier:
    """Quản lý một cửa sổ nhỏ để hiển thị trạng thái hiện tại của Controller."""
    def __init__(self, style_config=None):
        self.queue = queue.Queue()
        # Sử dụng style mặc định nếu không được cung cấp
        self.style_config = style_config or {}
        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()

    def _run_gui(self):
        """Hàm này chạy trong một luồng riêng để không làm treo chương trình chính."""
        self.root = tk.Tk()
        self.root.overrideredirect(True) # Bỏ viền và thanh tiêu đề
        self.root.wm_attributes("-topmost", True) # Luôn nổi trên cùng
        self.root.wm_attributes("-alpha", 0.8) # Hơi trong suốt
        
        # Áp dụng style từ config
        font_style = (
            self.style_config.get('font_family', 'Segoe UI'), 
            self.style_config.get('font_size', 10)
        )
        
        self.label = tk.Label(self.root, text="Khởi tạo...", 
                              fg=self.style_config.get('fg_color', 'white'), 
                              bg=self.style_config.get('bg_color', 'black'),
                              font=font_style, padx=10, pady=5,
                              wraplength=350, justify="left") # Tự động xuống dòng
        self.label.pack()
        
        # Đặt vị trí ở góc dưới bên phải màn hình
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"+{screen_width - 360}+{screen_height - 100}")

        self._check_queue()
        self.root.mainloop()

    def _check_queue(self):
        """Kiểm tra hàng đợi để cập nhật thông báo từ luồng khác."""
        try:
            message = self.queue.get_nowait()
            if message == "STOP":
                self.root.destroy()
                return
            self.label.config(text=message)
        except queue.Empty:
            pass
        self.root.after(100, self._check_queue)

    def update_status(self, message):
        """Gửi một thông điệp mới để hiển thị trên cửa sổ trạng thái."""
        self.queue.put(message)

    def stop(self):
        """Gửi tín hiệu để đóng cửa sổ trạng thái."""
        self.queue.put("STOP")

