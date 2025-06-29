# Elements/app_launcher.py
# Chứa hàm tiện ích để khởi động ứng dụng và lấy handle duy nhất của nó.

import os
import sys
import time
import logging

try:
    from pywinauto import Desktop
    import psutil
except ImportError:
    print("Lỗi: Vui lòng cài đặt thư viện pywinauto và psutil")
    print("pip install pywinauto psutil")
    exit()

# Cấu hình logging cho module này
logger = logging.getLogger(__name__)

def launch_and_get_handle(executable_path, timeout=15):
    """
    Khởi động một ứng dụng và trả về handle duy nhất của cửa sổ mới nhất
    thuộc về chính ứng dụng đó.

    Args:
        executable_path (str): Đường dẫn hoặc tên của file .exe.
        timeout (int): Thời gian tối đa để tìm kiếm cửa sổ mới.

    Returns:
        int: Handle (HWND) của cửa sổ mới tìm thấy, hoặc None nếu thất bại.
    """
    logger.info(f"Chuẩn bị khởi động: {executable_path}")
    
    # Chuẩn hóa đường dẫn để so sánh
    # os.path.normcase rất quan trọng để so sánh đường dẫn trên Windows (không phân biệt hoa/thường)
    normalized_path = os.path.normcase(os.path.abspath(executable_path))
    is_absolute_path = os.path.isabs(executable_path)
    expected_proc_name = os.path.basename(executable_path).lower()

    start_time = time.time()
    
    try:
        os.startfile(executable_path)
        logger.info(f"Đã gửi lệnh khởi động. Đang chờ cửa sổ của '{expected_proc_name}' xuất hiện...")

        end_time = time.time() + timeout
        while time.time() < end_time:
            newly_created_windows = []
            
            all_windows = Desktop(backend='uia').windows()

            for window in all_windows:
                try:
                    pid = window.process_id()
                    proc = psutil.Process(pid)
                    
                    # Điều kiện 1: Thời gian tạo phải sau thời điểm bắt đầu
                    if not proc.create_time() > start_time:
                        continue
                        
                    # ===== BỘ LỌC NÂNG CẤP =====
                    # Điều kiện 2: Tiến trình phải khớp
                    path_matches = False
                    if is_absolute_path:
                        # Nếu người dùng cung cấp đường dẫn đầy đủ, ta so sánh đường dẫn đầy đủ
                        path_matches = (os.path.normcase(proc.exe()) == normalized_path)
                    else:
                        # Nếu chỉ có tên file, ta so sánh tên file
                        path_matches = (proc.name().lower() == expected_proc_name)

                    if path_matches:
                        newly_created_windows.append((window, proc.create_time()))
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if newly_created_windows:
                newly_created_windows.sort(key=lambda x: x[1], reverse=True)
                
                newest_window = newly_created_windows[0][0]
                newest_handle = newest_window.handle
                
                logger.info(f"Đã xác định cửa sổ mới nhất: '{newest_window.window_text()}' với handle {newest_handle}")
                
                return newest_handle

            time.sleep(0.5)

        logger.error(f"Lỗi Timeout: Không tìm thấy cửa sổ nào của '{expected_proc_name}' xuất hiện trong {timeout} giây.")
        return None

    except Exception as e:
        logger.error(f"Lỗi không mong muốn trong quá trình khởi động hoặc tìm kiếm: {e}", exc_info=True)
        return None
