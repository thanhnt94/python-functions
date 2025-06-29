# tests/example_launcher_usage.py
# Kịch bản ví dụ để minh họa cách sử dụng hàm launch_and_get_handle

import os
import sys
import time
import logging

# Thêm đường dẫn thư mục cha để import các module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app_launcher import launch_and_get_handle
from ui_controller import UIController

def setup_logging():
    """Cấu hình logging cơ bản."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def main():
    """Hàm chính để chạy kịch bản."""
    setup_logging()
    logging.info("===== BẮT ĐẦU VÍ DỤ: SỬ DỤNG APP_LAUNCHER (LOGIC MỚI) =====")
    
    app_handle = None
    try:
        # --- Bước 1: Gọi hàm mới để mở Notepad và lấy handle duy nhất ---
        app_handle = launch_and_get_handle("notepad.exe")

        if not app_handle:
            logging.error("Khởi động hoặc tìm Notepad thất bại. Dừng kịch bản.")
            return

        # --- Bước 2: Dùng handle đã lấy được để điều khiển ---
        controller = UIController()
        text_to_type = "This is the most reliable way!"
        
        # Tạo spec chính xác bằng handle
        notepad_spec = {'win32_handle': app_handle}
        editor_spec = {'pwa_control_type': 'Document'}

        logging.info(f"Sử dụng spec {notepad_spec} để tương tác...")
        success = controller.run_action(
            window_spec=notepad_spec,
            element_spec=editor_spec,
            action=f"paste_text:{text_to_type}",
            auto_activate=True
        )

        if success:
            logging.info("-> THÀNH CÔNG!")
        else:
            logging.error("-> THẤT BẠI!")

    finally:
        # --- Bước 3: Dọn dẹp ---
        # Vì chúng ta không có đối tượng 'app', ta sẽ đóng bằng lệnh hệ thống
        logging.info("Đợi 3 giây trước khi đóng Notepad...")
        time.sleep(3)
        os.system("taskkill /f /im notepad.exe > nul 2>&1")
        logging.info("Đã đóng Notepad.")
        
    logging.info("===== VÍ DỤ HOÀN TẤT =====")


if __name__ == '__main__':
    main()
