import customtkinter as ctk
from tkinter import filedialog

# --- CÁC LOẠI CỬA SỔ POPUP ---

class InfoPopup(ctk.CTkToplevel):
    # (Giữ nguyên, không thay đổi)
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.title(title)
        self.geometry("350x150")
        self.transient(parent)
        self.grab_set()
        label = ctk.CTkLabel(self, text=message, font=ctk.CTkFont(size=16), wraplength=300)
        label.pack(padx=20, pady=20, expand=True)
        ctk.CTkButton(self, text="OK", command=self.destroy, width=100).pack(pady=(0, 20))

class LoginPopup(ctk.CTkToplevel):
    """Một cửa sổ đăng nhập hoàn chỉnh."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Đăng Nhập")
        self.geometry("400x250")
        self.transient(parent)
        self.grab_set()
        self.after(250, lambda: self.iconbitmap('')) # Bỏ icon mặc định của Toplevel

        ctk.CTkLabel(self, text="Đăng Nhập Tài Khoản", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        
        self.username_entry = ctk.CTkEntry(self, placeholder_text="Tên đăng nhập", width=250)
        self.username_entry.pack(pady=5)
        
        self.password_entry = ctk.CTkEntry(self, placeholder_text="Mật khẩu", show="*", width=250)
        self.password_entry.pack(pady=5)
        
        ctk.CTkButton(self, text="Đăng Nhập", command=self.login).pack(pady=20)
    
    def login(self):
        # Đây là nơi xử lý logic đăng nhập
        # Ví dụ: kiểm tra username/password và cập nhật lại cửa sổ chính
        print(f"Username: {self.username_entry.get()}, Password: {self.password_entry.get()}")
        self.master.status_label.configure(text=f"Đã đăng nhập với user: {self.username_entry.get()}")
        self.destroy()

class InputPopup(ctk.CTkToplevel):
    """Một popup cho phép nhập text và trả kết quả về cửa sổ chính."""
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title("Nhập Dữ Liệu")
        self.geometry("400x180")
        self.transient(parent)
        self.grab_set()
        self.callback = callback # Lưu hàm callback

        ctk.CTkLabel(self, text="Nhập nội dung mới:", font=ctk.CTkFont(size=16)).pack(pady=10)
        
        self.input_entry = ctk.CTkEntry(self, width=300)
        self.input_entry.pack(pady=5, padx=20, fill="x")
        self.input_entry.focus()

        ctk.CTkButton(self, text="Xác Nhận", command=self.confirm).pack(pady=20)

    def confirm(self):
        new_text = self.input_entry.get()
        if new_text:
            self.callback(new_text) # Gọi hàm callback với dữ liệu đã nhập
        self.destroy()


# --- ỨNG DỤNG CHÍNH ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # --- CẤU HÌNH CỬA SỔ CHÍNH ---
        self.title("Template CustomTkinter Siêu Cấp")
        self.geometry("950x650")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- TẠO CÁC THÀNH PHẦN GIAO DIỆN ---
        self.create_sidebar()
        self.create_all_content_frames()
        self.create_statusbar()

        # --- CHỌN FRAME MẶC ĐỊNH ---
        self.select_frame_by_name("input")

    def create_sidebar(self):
        self.navigation_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(5, weight=1) # Đẩy mục theme xuống

        # Tiêu đề sidebar
        ctk.CTkLabel(self.navigation_frame, text="UI TEMPLATE", 
                     font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=20, pady=(20, 10))

        # Các nút điều hướng
        self.input_button = self.create_nav_button("Input Widgets", "input", 1)
        self.scroll_button = self.create_nav_button("Scroll & Check", "scroll", 2)
        self.browser_button = self.create_nav_button("File Browser", "browser", 3)
        self.popup_button = self.create_nav_button("Popups", "popup", 4)
        
        # Menu Theme
        ctk.CTkOptionMenu(self.navigation_frame, values=["System", "Light", "Dark"],
                          command=self.change_appearance_mode_event).grid(row=6, column=0, padx=20, pady=20, sticky="s")
    
    def create_nav_button(self, text, name, row):
        """Hàm trợ giúp tạo nút điều hướng để tránh lặp code"""
        button = ctk.CTkButton(self.navigation_frame, corner_radius=0, height=40, border_spacing=10, 
                               text=text, fg_color="transparent", text_color=("gray10", "gray90"), 
                               hover_color=("gray70", "gray30"), anchor="w", 
                               command=lambda: self.select_frame_by_name(name))
        button.grid(row=row, column=0, sticky="ew")
        return button

    def create_all_content_frames(self):
        """Tạo và điền nội dung cho tất cả các frame."""
        self.content_frames = {
            "input": self.create_content_frame(),
            "scroll": self.create_content_frame(),
            "browser": self.create_content_frame(),
            "popup": self.create_content_frame()
        }
        self.populate_input_frame()
        self.populate_scroll_frame()
        self.populate_browser_frame()
        self.populate_popup_frame()

    def create_content_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=10)
        return frame

    def populate_input_frame(self):
        frame = self.content_frames["input"]
        ctk.CTkLabel(frame, text="Trang Widget Nhập Liệu", font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", padx=20, pady=(10, 20))
        ctk.CTkLabel(frame, text="CTkEntry & CTkTextbox").pack(anchor="w", padx=20)
        ctk.CTkEntry(frame, placeholder_text="Nhập văn bản...").pack(fill="x", padx=20, pady=(0, 10))
        textbox = ctk.CTkTextbox(frame, height=150)
        textbox.pack(fill="x", expand=True, padx=20, pady=(0, 20))
        textbox.insert("0.0", "Đây là một Textbox cho phép nhập nhiều dòng văn bản.")

    def populate_scroll_frame(self):
        frame = self.content_frames["scroll"]
        ctk.CTkLabel(frame, text="Trang Scroll & Checkbox", font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", padx=20, pady=(10, 20))
        
        # Scrollable Frame
        scroll_frame = ctk.CTkScrollableFrame(frame, label_text="Danh sách Checkbox")
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Thêm nhiều checkbox vào để có thể cuộn
        for i in range(20):
            ctk.CTkCheckBox(scroll_frame, text=f"Lựa chọn số {i+1}").pack(anchor="w", padx=10, pady=5)

    def populate_browser_frame(self):
        frame = self.content_frames["browser"]
        ctk.CTkLabel(frame, text="Trang Duyệt File & Thư Mục", font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", padx=20, pady=(10, 20))
        file_frame = ctk.CTkFrame(frame)
        file_frame.pack(fill="x", padx=20, pady=10)
        self.file_path_entry = ctk.CTkEntry(file_frame, placeholder_text="Đường dẫn file...")
        self.file_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(file_frame, text="Chọn File", width=120, command=self.browse_file).pack(side="left")

    def populate_popup_frame(self):
        frame = self.content_frames["popup"]
        ctk.CTkLabel(frame, text="Trang Quản Lý Popup", font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", padx=20, pady=(10, 20))
        
        ctk.CTkButton(frame, text="Mở Popup Đăng Nhập", command=lambda: LoginPopup(self).mainloop()).pack(fill="x", padx=20, pady=5)
        ctk.CTkButton(frame, text="Mở Popup Nhập Dữ Liệu", command=lambda: InputPopup(self, self.update_dynamic_label).mainloop()).pack(fill="x", padx=20, pady=5)
        
        # Label để hiển thị nội dung từ InputPopup
        ctk.CTkLabel(frame, text="Nội dung từ popup sẽ hiện ở đây:", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=(20, 5))
        self.dynamic_label = ctk.CTkLabel(frame, text="...", font=ctk.CTkFont(size=18, weight="bold"), fg_color="gray20", corner_radius=6)
        self.dynamic_label.pack(anchor="w", padx=20, ipady=10, ipadx=10)

    def create_statusbar(self):
        self.statusbar_frame = ctk.CTkFrame(self, height=25, corner_radius=0)
        self.statusbar_frame.grid(row=1, column=1, sticky="nsew", padx=20, pady=(0, 10))
        ctk.CTkLabel(self.statusbar_frame, text="© 2025 Your Company", anchor="w").pack(side="left", padx=10)
        self.status_label = ctk.CTkLabel(self.statusbar_frame, text="Trạng thái: Sẵn sàng", anchor="e")
        self.status_label.pack(side="right", padx=10)

    def select_frame_by_name(self, name):
        active_color = ("gray75", "gray25")
        self.input_button.configure(fg_color=active_color if name == "input" else "transparent")
        self.scroll_button.configure(fg_color=active_color if name == "scroll" else "transparent")
        self.browser_button.configure(fg_color=active_color if name == "browser" else "transparent")
        self.popup_button.configure(fg_color=active_color if name == "popup" else "transparent")
        
        # Dùng tkraise để đưa frame được chọn lên trên
        self.content_frames[name].tkraise()
    
    def browse_file(self):
        # (Giữ nguyên, không thay đổi)
        file_path = filedialog.askopenfilename(title="Chọn một file")
        if file_path:
            self.file_path_entry.delete(0, "end")
            self.file_path_entry.insert(0, file_path)
            self.status_label.configure(text=f"Đã chọn file: {file_path.split('/')[-1]}")

    def update_dynamic_label(self, new_text):
        """Callback function được gọi bởi InputPopup."""
        self.dynamic_label.configure(text=f"Nội dung mới: '{new_text}'")
        self.status_label.configure(text="Đã cập nhật nội dung từ popup!")

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

if __name__ == "__main__":
    app = App()
    app.mainloop()

