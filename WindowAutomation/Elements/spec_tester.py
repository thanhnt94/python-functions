# build_ui_inspector.py
# Kịch bản để đóng gói ui_inspector.py thành một file .exe duy nhất với dung lượng tối ưu.

import PyInstaller.__main__
import os

# --- CẤU HÌNH BUILD ---

# Đường dẫn đến tệp ui_inspector.py của bạn
script_path = r'C:\Users\KNT15083\OneDrive - Nissan Motor Corporation\Python\My Project\2D Drawing Download\1.0\functions\spec_tester.py'

# Đường dẫn đến thư mục chứa UPX (nếu có, để nén file)
upx_dir = r'C:\upx-4.2.4-win64'

# Đường dẫn thư mục đầu ra
dist_path = r'C:\exeBuild\UI'
work_path = r'C:\exeBuild\build'

# Tên file thực thi
exe_name = 'Spec Tester 1.0'

# --- DANH SÁCH CÁC THƯ VIỆN CẦN LOẠI TRỪ ---
# Đây là những thư viện lớn có trong môi trường của bạn nhưng không cần thiết
# cho ui_inspector.py. Việc loại trừ chúng sẽ giảm đáng kể dung lượng file.
excludes = [
    # Thư viện AI/ML/CV lớn
    'torch',
    'torchvision',
    'torchaudio',
    'easyocr',
    'cv2',          # Tên import của opencv-python
    'skimage',      # Tên import của scikit-image
    'scipy',
    
    # Thư viện Web/Network
    'playwright',
    'selenium',
    'msedge-selenium-tools',
    'webdriver-manager',
    'requests',
    'urllib3',
    'websocket',

    # Thư viện Testing
    'pytest',
    'pytest-base-url',
    'pytest-playwright',

    # Thư viện xử lý file/dữ liệu không cần thiết
    'pdfminer',
    'pdfplumber',
    'PyPDF2',
    'pypdfium2',
    'pytesseract',
    'python-pptx',
    'lxml',
    'xlrd',
    'xlwings',

    # Thư viện GUI khác
    'customtkinter',
    'PyQt5',
    'PySide2',
    
    # Thư viện khác
    'matplotlib',
    'cryptography',
    'thefuzz',
    'python-Levenshtein',
    'Jinja2',
    'sympy'
]

# --- XÂY DỰNG KỊCH BẢN ---

# Tạo danh sách các tham số cho PyInstaller
pyinstaller_args = [
    script_path,
    '--onefile',     # Đóng gói thành một file duy nhất
    '--windowed',    # Ẩn cửa sổ dòng lệnh màu đen khi chạy
    '--clean',       # Xóa các file tạm thời trước khi build
    f'--name={exe_name}',
    f'--distpath={dist_path}',
    f'--workpath={work_path}',
]

# Thêm tùy chọn UPX nếu thư mục tồn tại
if os.path.exists(upx_dir):
    pyinstaller_args.append(f'--upx-dir={upx_dir}')
else:
    print(f"[Cảnh báo] Không tìm thấy thư mục UPX tại: {upx_dir}. File exe sẽ không được nén.")

# Thêm các module cần loại trừ vào danh sách tham số
for module in excludes:
    pyinstaller_args.append(f'--exclude-module={module}')

print("--- Bắt đầu quá trình đóng gói với các tham số sau: ---")
print(pyinstaller_args)
print("---------------------------------------------------------")

# Chạy PyInstaller
PyInstaller.__main__.run(pyinstaller_args)

print("\n===== QUÁ TRÌNH ĐÓNG GÓI HOÀN TẤT! =====")
print(f"File thực thi đã được tạo tại: {dist_path}")
