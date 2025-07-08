# color_picker_tool.py
# A feature-rich color picker tool built with Python's Tkinter and Pillow.
#
# Version 1.6: Replaced the hotkey-based screen picker with a more reliable
# click-based method using a temporary, transparent overlay window. This
# removes the 'keyboard' dependency and avoids permission issues.
#
# Features:
# 1. Interactive color palette with a brightness slider.
# 2. Screen-wide color picker using a simple mouse click.
# 3. Displays color in HEX and RGB formats.
# 4. "Copy to Clipboard" functionality for the HEX code.
#
# Dependencies:
# - Pillow: For image operations. (pip install Pillow)

import tkinter as tk
from tkinter import ttk
import colorsys

try:
    from PIL import ImageGrab, ImageTk, Image
except ImportError:
    print("Lỗi: Thư viện Pillow chưa được cài đặt.")
    print("Vui lòng cài đặt bằng lệnh: pip install Pillow")
    exit()

class ColorPickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Công cụ Chọn Màu")
        self.root.geometry("550x350")
        self.root.resizable(False, False)

        # --- Biến trạng thái ---
        self.hue = 0.0
        self.saturation = 1.0
        self.value = 1.0
        self.ui_ready = False

        # --- Giao diện chính ---
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(expand=True, fill='both')

        # --- Phần bảng màu (Trái) ---
        palette_frame = ttk.Frame(main_frame)
        palette_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))
        
        ttk.Label(palette_frame, text="Bảng màu (Hue/Saturation)").pack(anchor='w')
        self.color_canvas = tk.Canvas(palette_frame, width=256, height=256, borderwidth=0, highlightthickness=0)
        self.color_canvas.pack()
        self.color_canvas.bind("<B1-Motion>", self.on_palette_drag)
        self.color_canvas.bind("<Button-1>", self.on_palette_drag)

        # --- Phần thanh trượt độ sáng (Giữa) ---
        slider_frame = ttk.Frame(main_frame)
        slider_frame.pack(side='left', fill='y', padx=(0, 10))
        
        ttk.Label(slider_frame, text="Sáng/Tối").pack(anchor='w')
        self.brightness_slider = ttk.Scale(slider_frame, from_=1.0, to=0.0, orient='vertical', command=self.on_brightness_change)
        self.brightness_slider.pack(expand=True, fill='y')

        # --- Phần thông tin và điều khiển (Phải) ---
        info_frame = ttk.Frame(main_frame, width=180)
        info_frame.pack(side='left', fill='y')
        info_frame.pack_propagate(False)

        ttk.Label(info_frame, text="Màu đã chọn:", padding=(0,0,0,5)).pack(anchor='w')
        self.color_preview = tk.Label(info_frame, text="", background="#FFFFFF", relief='solid', borderwidth=1)
        self.color_preview.pack(fill='x', expand=True, pady=(0, 10))

        # Mã HEX và RGB
        hex_frame = ttk.Frame(info_frame)
        hex_frame.pack(fill='x', pady=5)
        ttk.Label(hex_frame, text="HEX:").pack(side='left')
        self.hex_entry = ttk.Entry(hex_frame, justify='center')
        self.hex_entry.pack(side='left', expand=True, fill='x', padx=(5, 0))
        
        rgb_frame = ttk.Frame(info_frame)
        rgb_frame.pack(fill='x', pady=5)
        ttk.Label(rgb_frame, text="RGB:").pack(side='left')
        self.rgb_entry = ttk.Entry(rgb_frame, justify='center')
        self.rgb_entry.pack(side='left', expand=True, fill='x', padx=(5, 0))

        # Các nút điều khiển
        self.copy_button = ttk.Button(info_frame, text="Sao chép mã HEX", command=self.copy_to_clipboard)
        self.copy_button.pack(fill='x', pady=10)
        
        self.pick_button = ttk.Button(info_frame, text="Lấy màu từ màn hình", command=self.start_screen_picker)
        self.pick_button.pack(fill='x', pady=5)

        # --- Hoàn tất khởi tạo UI ---
        self.ui_ready = True
        self.brightness_slider.set(1.0)

    def create_palette_image(self):
        width, height = 256, 256
        self.palette_image = Image.new("RGB", (width, height))
        v = self.value 
        for y in range(height):
            for x in range(width):
                h = x / width
                s = 1 - (y / height)
                r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)]
                self.palette_image.putpixel((x, y), (r, g, b))
        self.palette_photo = ImageTk.PhotoImage(self.palette_image)
        self.color_canvas.create_image(0, 0, anchor='nw', image=self.palette_photo)

    def on_palette_drag(self, event):
        if not self.ui_ready: return
        x, y = max(0, min(event.x, 255)), max(0, min(event.y, 255))
        self.hue = x / 256.0
        self.saturation = 1 - (y / 256.0)
        self.update_color()

    def on_brightness_change(self, value):
        if not self.ui_ready: return
        self.value = float(value)
        self.create_palette_image()
        self.update_color()

    def update_color(self, h=None, s=None, v=None):
        if not self.ui_ready: return
        if h is not None: self.hue = h
        if s is not None: self.saturation = s
        if v is not None: self.value = v
        rgb_float = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        rgb_int = tuple(int(c * 255) for c in rgb_float)
        hex_code = f"#{rgb_int[0]:02x}{rgb_int[1]:02x}{rgb_int[2]:02x}".upper()
        self.color_preview.config(background=hex_code)
        self.hex_entry.delete(0, tk.END); self.hex_entry.insert(0, hex_code)
        self.rgb_entry.delete(0, tk.END); self.rgb_entry.insert(0, f"{rgb_int[0]}, {rgb_int[1]}, {rgb_int[2]}")

    def copy_to_clipboard(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.hex_entry.get())
        original_text = self.copy_button.cget("text")
        self.copy_button.config(text="Đã sao chép!")
        self.root.after(1500, lambda: self.copy_button.config(text=original_text))

    def start_screen_picker(self):
        """Bắt đầu quá trình lấy màu bằng cách tạo một cửa sổ overlay."""
        self.root.iconify() # Thu nhỏ cửa sổ chính
        
        # Tạo một cửa sổ Toplevel để làm overlay
        picker_window = tk.Toplevel(self.root)
        picker_window.attributes("-fullscreen", True)
        picker_window.attributes("-alpha", 0.05) # Gần như trong suốt
        picker_window.attributes("-topmost", True)
        picker_window.config(cursor="crosshair")

        def on_pick(event):
            # Lấy màu tại vị trí click
            x, y = event.x_root, event.y_root
            picked_rgb = ImageGrab.grab(bbox=(x, y, x + 1, y + 1)).getpixel((0, 0))
            
            # Cập nhật màu
            rgb_float = [c / 255.0 for c in picked_rgb]
            h, s, v = colorsys.rgb_to_hsv(*rgb_float)
            self.brightness_slider.set(v)
            self.update_color(h, s, v)
            
            # Dọn dẹp và phục hồi cửa sổ chính
            cleanup_and_restore()

        def on_cancel(event):
            cleanup_and_restore()

        def cleanup_and_restore():
            picker_window.destroy()
            self.root.deiconify() # Phục hồi cửa sổ chính

        picker_window.bind("<Button-1>", on_pick)
        picker_window.bind("<Button-3>", on_cancel) # Chuột phải để hủy
        picker_window.bind("<Escape>", on_cancel)   # Phím Esc để hủy

if __name__ == "__main__":
    root = tk.Tk()
    app = ColorPickerApp(root)
    root.mainloop()
