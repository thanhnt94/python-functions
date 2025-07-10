# screen_tool.py
# Một bộ công cụ màn hình đa năng, được viết lại để đảm bảo độ ổn định và
# cải thiện giao diện người dùng.
#
# Version 2.4:
# - Thêm khu vực "Lịch sử kết quả" vào giao diện chính để xem lại các thông số đã lấy.
# - Thêm nút "Xóa lịch sử" để dọn dẹp danh sách kết quả.
# - Cải tiến bố cục chung của ứng dụng.
#
# Dependencies:
# - Pillow: Để chụp ảnh màn hình. (pip install Pillow)

import tkinter as tk
from tkinter import ttk, font
import math

try:
    from PIL import ImageGrab, ImageTk
except ImportError:
    print("Lỗi: Thư viện Pillow chưa được cài đặt.")
    print("Vui lòng cài đặt bằng lệnh: pip install Pillow")
    exit()

class ScreenToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Công cụ Màn hình")
        self.root.geometry("480x350") # Tăng chiều cao cho khu vực lịch sử
        self.root.resizable(False, False)
        self.root.eval('tk::PlaceWindow . center')
        
        # Style
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Tool.TFrame", background="#F0F0F0")
        self.root.configure(bg="#F0F0F0")

        # --- Giao diện chính ---
        # Khung chứa các nút chức năng
        button_container = ttk.Frame(self.root, padding=(15, 15, 15, 10), style="Tool.TFrame")
        button_container.pack(expand=True, fill='x')
        button_container.columnconfigure((0, 1, 2), weight=1)

        # Nút Đo khoảng cách
        ruler_button = self.create_custom_button(
            button_container, text=" Đo khoảng cách", command=lambda: self.start_capture_mode('ruler'), icon_drawer=self.draw_ruler_icon)
        ruler_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # Nút Lấy tọa độ vùng
        region_button = self.create_custom_button(
            button_container, text=" Lấy tọa độ vùng", command=lambda: self.start_capture_mode('rect'), icon_drawer=self.draw_region_icon)
        region_button.grid(row=0, column=1, sticky="ew", padx=5)

        # Nút Lấy tọa độ điểm
        point_button = self.create_custom_button(
            button_container, text=" Lấy tọa độ điểm", command=lambda: self.start_capture_mode('point'), icon_drawer=self.draw_point_icon)
        point_button.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        # --- Khu vực lịch sử kết quả ---
        history_frame = ttk.LabelFrame(self.root, text=" Lịch sử kết quả ", padding=10)
        history_frame.pack(expand=True, fill='both', padx=15, pady=(0, 15))
        
        # Nút xóa lịch sử
        clear_button = ttk.Button(history_frame, text="Xóa", command=self.clear_history)
        clear_button.place(relx=1.0, rely=0, x=-5, y=-8, anchor="ne")

        # Text widget để hiển thị lịch sử
        self.history_text = tk.Text(history_frame, height=8, font=("Segoe UI", 9), relief="solid", bd=1, state="disabled")
        self.history_text.pack(expand=True, fill='both')

        # Biến trạng thái
        self.capture_window = None
        self.canvas = None
        self.screenshot = None
        self.tk_screenshot = None
        self.mode = 'ruler'
        self.start_x, self.start_y = 0, 0
        self.current_x, self.current_y = 0, 0
        self.is_drawing = False

    def create_custom_button(self, parent, text, command, icon_drawer):
        button_frame = tk.Frame(parent, bd=1, relief="raised", bg="#FFFFFF", cursor="hand2")
        icon_canvas = tk.Canvas(button_frame, width=24, height=24, bg="#FFFFFF", highlightthickness=0)
        icon_canvas.pack(side="left", padx=(10, 5), pady=10)
        icon_drawer(icon_canvas)
        label = tk.Label(button_frame, text=text, font=("Segoe UI", 10, "bold"), bg="#FFFFFF")
        label.pack(side="left", padx=(0, 10), pady=10)
        for widget in [button_frame, icon_canvas, label]:
            widget.bind("<Button-1>", lambda e: self._on_button_press(button_frame, command))
            widget.bind("<ButtonRelease-1>", lambda e: self._on_button_release(button_frame))
        return button_frame

    def _on_button_press(self, frame, command):
        frame.config(relief="sunken")
        command()

    def _on_button_release(self, frame):
        frame.config(relief="raised")

    def draw_ruler_icon(self, canvas):
        canvas.create_line(5, 19, 19, 5, fill="#333333", width=2)
        for i in range(3):
            canvas.create_line(8+i*4, 16-i*4, 6+i*4, 18-i*4, fill="#333333", width=1)

    def draw_region_icon(self, canvas):
        canvas.create_rectangle(5, 5, 19, 19, outline="#333333", width=2, dash=(2, 2))

    def draw_point_icon(self, canvas):
        canvas.create_line(12, 5, 12, 19, fill="#333333", width=1)
        canvas.create_line(5, 12, 19, 12, fill="#333333", width=1)
        canvas.create_oval(9, 9, 15, 15, outline="#FF3B30", width=2)

    def start_capture_mode(self, mode):
        self.mode = mode
        self.root.iconify()
        self.root.after(150, self.create_capture_window)

    def create_capture_window(self):
        try:
            self.screenshot = ImageGrab.grab()
        except Exception as e:
            print(f"Lỗi khi chụp màn hình: {e}")
            self.root.deiconify()
            return
        
        self.capture_window = tk.Toplevel(self.root)
        self.capture_window.attributes("-fullscreen", True)
        self.capture_window.attributes("-topmost", True)
        self.capture_window.config(cursor="crosshair")

        self.canvas = tk.Canvas(self.capture_window, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.tk_screenshot = ImageTk.PhotoImage(self.screenshot)
        self.canvas.create_image(0, 0, image=self.tk_screenshot, anchor='nw')

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.capture_window.bind("<Escape>", self.cleanup_and_restore)
        self.capture_window.bind("<Button-3>", self.cleanup_and_restore)

    def log_result(self, text):
        """Sao chép vào clipboard và ghi vào lịch sử."""
        # Sao chép
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        
        # Ghi vào lịch sử
        self.history_text.config(state="normal")
        self.history_text.insert("1.0", text + "\n")
        self.history_text.config(state="disabled")

        # Hiển thị thông báo
        self.show_confirmation(f"Đã sao chép: {text}")

    def clear_history(self):
        """Xóa nội dung trong ô lịch sử."""
        self.history_text.config(state="normal")
        self.history_text.delete("1.0", tk.END)
        self.history_text.config(state="disabled")

    def on_mouse_press(self, event):
        if self.mode == 'point':
            info_to_copy = f"({event.x}, {event.y})"
            self.log_result(info_to_copy)
        else:
            self.is_drawing = True
            self.start_x, self.start_y = event.x, event.y

    def on_mouse_drag(self, event):
        if not self.is_drawing or self.mode == 'point': return
        self.current_x, self.current_y = event.x, event.y
        self.draw_visuals()

    def on_mouse_release(self, event):
        if not self.is_drawing or self.mode == 'point': return
        self.is_drawing = False
        
        left, top = min(self.start_x, self.current_x), min(self.start_y, self.current_y)
        right, bottom = max(self.start_x, self.current_x), max(self.start_y, self.current_y)
        width, height = right - left, bottom - top
        
        if self.mode == 'ruler':
            distance = math.sqrt(width**2 + height**2)
            info_to_copy = f"W: {width}px, H: {height}px, D: {distance:.2f}px"
        else: # 'rect'
            info_to_copy = f"({left}, {top}, {right}, {bottom})"
        
        self.log_result(info_to_copy)

    def on_mouse_move(self, event):
        if self.mode != 'point' or self.is_drawing: return
        self.current_x, self.current_y = event.x, event.y
        self.draw_visuals()

    def draw_visuals(self):
        self.canvas.delete("drawing")
        self.canvas.create_image(0, 0, image=self.tk_screenshot, anchor='nw', tags="drawing")
        
        if self.is_drawing:
            if self.mode == 'ruler':
                self.canvas.create_line(self.start_x, self.start_y, self.current_x, self.current_y, fill="#FF3B30", width=2, tags="drawing")
            elif self.mode == 'rect':
                self.canvas.create_rectangle(self.start_x, self.start_y, self.current_x, self.current_y, outline="#FF3B30", width=2, tags="drawing")
        self.draw_info_box()

    def draw_info_box(self):
        left, top = min(self.start_x, self.current_x), min(self.start_y, self.current_y)
        right, bottom = max(self.start_x, self.current_x), max(self.start_y, self.current_y)
        width, height = right - left, bottom - top

        box_height = 50
        if self.mode == 'ruler':
            distance = math.sqrt(width**2 + height**2) if self.is_drawing else 0
            info_text = f"W: {width} px\nH: {height} px\nD: {distance:.1f} px"
            box_height = 65
        elif self.mode == 'rect':
            rect_tuple_str = f"({left}, {top}, {right}, {bottom})"
            info_text = f"Size: {width}x{height}\nRect: {rect_tuple_str}"
        else: # 'point'
            x, y = self.current_x, self.current_y
            if 0 <= x < self.screenshot.width and 0 <= y < self.screenshot.height:
                rgb = self.screenshot.getpixel((x, y))
                info_text = f"XY: ({x}, {y})\nRGB: {rgb}"
            else:
                info_text = f"XY: ({x}, {y})\nNgoài màn hình"

        text_x, text_y = self.current_x + 20, self.current_y + 20
        self.canvas.create_rectangle(text_x - 5, text_y - 5, text_x + 180, text_y + box_height, fill="black", outline="#FF3B30", tags="drawing")
        self.canvas.create_text(text_x + 5, text_y, text=info_text, anchor="nw", fill="white", font=("Segoe UI", 10, "bold"), tags="drawing")

    def show_confirmation(self, text):
        self.canvas.delete("drawing")
        self.canvas.create_image(0, 0, image=self.tk_screenshot, anchor='nw')
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.canvas.create_text(screen_w / 2, screen_h / 2, text=text, fill="#FF3B30", font=("Segoe UI", 20, "bold"), justify='center')
        self.root.after(1200, lambda: self.cleanup_and_restore(None))

    def cleanup_and_restore(self, event):
        if self.capture_window:
            self.capture_window.destroy()
            self.capture_window = None
        self.root.deiconify()

if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenToolApp(root)
    root.mainloop()
