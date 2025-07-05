# build_script.py
# Kịch bản để đóng gói ui_inspector.py thành một file .exe duy nhất.
# Phiên bản này là "chế độ an toàn", không loại trừ thư viện để đảm bảo chạy được.
# Chạy file này bằng Python: python build_script.py

import PyInstaller.__main__
import os
from pathlib import Path

# --- CẤU HÌNH BUILD (Vui lòng chỉnh sửa các đường dẫn nếu cần) ---

# 1. Đường dẫn đến file ui_inspector.py của bạn
#    Script này giả định nó nằm cùng thư mục với ui_inspector.py
script_path = r'C:\Users\thanh\OneDrive\CodeHub\MyPythonFunctions\WindowAutomation\Elements\ui_inspector.py'

# 2. Tên file thực thi bạn muốn tạo
exe_name = r'UI_Inspector_v2.7_safe_build'

# 3. Đường dẫn đến thư mục chứa UPX (Vẫn rất quan trọng để giảm dung lượng)
#    - Tải UPX tại: https://github.com/upx/upx/releases/
#    - Giải nén và đặt đường dẫn đến thư mục chứa upx.exe ở đây.
#    - Ví dụ: r'C:\upx-4.2.4-win64'
upx_dir = r'C:\upx-4.2.4-win64' # <-- THAY ĐỔI ĐƯỜNG DẪN NÀY

# 4. Thư mục đầu ra cho file .exe và các file tạm
output_folder = Path('build_output')
dist_path = output_folder / 'dist'
work_path = output_folder / 'build'


# --- XÂY DỰNG KỊCH BẢN ---

# Kiểm tra xem file script có tồn tại không
if not Path(script_path).exists():
    print(f"LỖI: Không tìm thấy file '{script_path}'.")
    print("Vui lòng đảm bảo file build_script.py này nằm cùng thư mục với ui_inspector.py.")
    exit()

# Tạo danh sách các tham số cho PyInstaller
pyinstaller_args = [
    script_path,
    '--onefile',            # Đóng gói thành một file duy nhất
    '--windowed',           # Ẩn cửa sổ dòng lệnh màu đen khi chạy
    '--clean',              # Xóa các file tạm thời trước khi build
    f'--name={exe_name}',
    f'--distpath={dist_path}',
    f'--workpath={work_path}',
    # Thêm các file phụ vào (quan trọng cho các package)
    '--collect-all=pywinauto',
    '--collect-all=comtypes',
    '--collect-all=pandas', # Thêm pandas để đảm bảo
]

# Thêm tùy chọn UPX nếu thư mục tồn tại
if Path(upx_dir).exists():
    pyinstaller_args.append(f'--upx-dir={upx_dir}')
    print(f"[INFO] Tìm thấy UPX. File .exe sẽ được nén.")
else:
    print(f"[CẢNH BÁO] Không tìm thấy thư mục UPX tại: {upx_dir}")
    print(f"[CẢNH BÁO] File .exe sẽ không được nén và có dung lượng lớn hơn đáng kể.")
    print(f"[CẢNH BÁO] Tải UPX tại: https://github.com/upx/upx/releases/")


print("\n--- Bắt đầu quá trình đóng gói với các tham số sau: ---")
# In ra các tham số để dễ gỡ lỗi
for arg in pyinstaller_args:
    print(arg)
print("---------------------------------------------------------")
print("Quá trình này có thể mất vài phút...")

# Chạy PyInstaller
PyInstaller.__main__.run(pyinstaller_args)

print("\n" + "="*50)
print("===== QUÁ TRÌNH ĐÓNG GÓI HOÀN TẤT! =====")
print(f"File thực thi đã được tạo tại: {dist_path.resolve()}")
print("="*50 + "\n")
