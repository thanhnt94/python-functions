# build_exe.py
# Kịch bản nâng cao để đóng gói ứng dụng, với danh sách loại trừ thư viện.
# Yêu cầu: pip install pyinstaller
# Tùy chọn: Tải và giải nén UPX tại một đường dẫn để giảm dung lượng file EXE.

import PyInstaller.__main__
import os
import shutil

# --- CẤU HÌNH ---
main_script = 'WindowAutomation/Elements/automation_suite.py'
exe_name = 'AutomationSuite'
icon_path = 'assets/app_icon.ico' 

# --- CẤU HÌNH ĐƯỜNG DẪN NÂNG CAO ---
upx_dir_path = 'C:/upx' 
output_dir = 'tool'
build_temp_dir = 'D:/build_temp/automation_suite'

# --- DANH SÁCH CÁC THƯ VIỆN CẦN LOẠI BỎ ---
# Thêm tên các module bạn muốn loại bỏ vào danh sách này.
modules_to_exclude = [
    # Web Frameworks & Scraping
    'Django', 'Flask', 'fastapi', 'uvicorn', 'asgiref', 'starlette', 'h11',
    'Scrapy', 'beautifulsoup4', 'bs4', 'requests_html', 'lxml', 'parsel', 
    'pyquery', 'w3lib', 'tldextract', 'url_normalize', 'Protego', 
    'itemadapter', 'itemloaders', 'queuelib', 'cssselect', 'soupsieve',
    'Twisted', 'zope.interface', 'Automat', 'constantly', 'hyperlink', 
    'incremental', 'PyDispatcher', 'service_identity',
    
    # Data Science, Plotting, and Heavy Math
    'matplotlib', 'scipy', 'scikit-image', 'kiwisolver', 'contourpy', 
    'cycler', 'fonttools', 'nltk', 'sympy', 'mpmath', 'networkx', 'joblib',

    # OCR and Deep Learning
    'easyocr', 'torch', 'torchvision', 'opencv-python', 'opencv-python-headless', 'ninja',

    # PDF and Presentation Libraries
    'pdfminer.six', 'pdfplumber', 'PyPDF2', 'pypdfium2', 'python-pptx',

    # Alternative GUI / Automation Libraries
    'customtkinter', 'PyAutoGUI', 'PyGetWindow', 'PyMsgBox', 'PyRect', 'PyScreeze', 
    'MouseInfo', 'pytweening',

    # Browser Automation
    'playwright', 'pyppeteer', 'pyee', 'websockets',

    # Testing Frameworks
    'pytest', 'pluggy', 'iniconfig',

    # Other misc libraries not used in this project
    'pydantic', 'cattrs', 'defusedxml', 'imageio', 'jmespath', 'pyOpenSSL',
    'python-bidi', 'python-dotenv', 'xlrd', 'xlsxwriter', 'xlwings', 'PyYAML'
]

# --- Dọn dẹp các bản build cũ ---
print("--- Dọn dẹp các thư mục build cũ... ---")
if os.path.isdir(build_temp_dir):
    shutil.rmtree(build_temp_dir)
if os.path.isdir(output_dir):
    if os.path.isfile(os.path.join(output_dir, f'{exe_name}.exe')):
        os.remove(os.path.join(output_dir, f'{exe_name}.exe'))
if os.path.isfile(f'{exe_name}.spec'):
    os.remove(f'{exe_name}.spec')
print("Dọn dẹp hoàn tất.")


# --- Các tùy chọn cho PyInstaller ---
pyinstaller_options = [
    f'--name={exe_name}',
    '--onefile',
    '--windowed',
    f'--icon={icon_path}',
    f'--distpath={output_dir}',
    f'--workpath={build_temp_dir}',
    # --- Các thư viện ẩn cần thiết ---
    '--hidden-import=pywinauto.backend.uia',
    '--hidden-import=pywinauto.backend.win32',
    '--hidden-import=keyboard._winkeyboard',
    '--hidden-import=pynput.keyboard._win32',
    '--hidden-import=pynput.mouse._win32',
    '--hidden-import=psutil',
]

# Thêm các module cần loại bỏ vào câu lệnh
for module in modules_to_exclude:
    pyinstaller_options.append(f'--exclude-module={module}')

# Kết hợp các tùy chọn với file kịch bản chính
full_command = pyinstaller_options + [main_script]

# --- CHẠY ĐÓNG GÓI ---
if __name__ == '__main__':
    print("\n--- Bắt đầu quá trình đóng gói với PyInstaller ---")
    
    if os.path.isdir(upx_dir_path):
        print(f"Tìm thấy UPX tại: '{upx_dir_path}'. Sẽ sử dụng để nén file.")
        full_command.append(f'--upx-dir={upx_dir_path}')
    else:
        print(f"\n!!! CẢNH BÁO: Không tìm thấy thư mục UPX tại '{upx_dir_path}'.")
        print("Bỏ qua bước nén file. File EXE sẽ có dung lượng lớn hơn.")

    if not os.path.exists(icon_path):
        print(f"\n!!! CẢNH BÁO: Không tìm thấy file icon tại '{icon_path}'.")
        print("Bỏ qua tùy chọn icon. EXE sẽ sử dụng icon mặc định.")
        full_command = [opt for opt in full_command if not opt.startswith('--icon')]

    print(f"\nLệnh thực thi: pyinstaller {' '.join(full_command)}")
    
    try:
        os.makedirs(build_temp_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        
        PyInstaller.__main__.run(full_command)
        print("\n--- QUÁ TRÌNH ĐÓNG GÓI HOÀN TẤT! ---")
        print(f"=> File thực thi của bạn nằm trong thư mục: {os.path.abspath(output_dir)}")
    except Exception as e:
        print("\n--- !!! CÓ LỖI XẢY RA TRONG QUÁ TRÌNH ĐÓNG GÓI !!! ---")
        print(f"Lỗi: {e}")

