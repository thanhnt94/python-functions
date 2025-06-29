# tests/test_select_notepad.py
# Một kịch bản test đơn giản, có thể chạy trực tiếp để kiểm tra việc
# lựa chọn cửa sổ Notepad mới nhất.

import os
import sys
import time
import logging

# Thêm đường dẫn thư mục cha để có thể import UIController
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_controller import UIController

def setup_logging():
    """Cấu hình logging cơ bản cho file test."""
    # Đảm bảo chỉ cấu hình logging một lần
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def run_notepad_selection_test():
    """
    Hàm chính để chạy kịch bản test.
    """
    setup_logging()
    logging.info("===== BẮT ĐẦU KỊCH BẢN: CHỌN CỬA SỔ NOTEPAD MỚI NHẤT =====")
    
    # --- Bước 1: Chuẩn bị môi trường ---
    num_windows_to_open = 3
    logging.info(f"Đang mở {num_windows_to_open} cửa sổ Notepad...")
    for i in range(num_windows_to_open):
        os.startfile("notepad.exe")
        logging.info(f"Đã mở cửa sổ thứ {i+1}")
        time.sleep(1) # Chờ 1 giây để đảm bảo thứ tự tạo ra là rõ ràng

    time.sleep(2) # Chờ tất cả các cửa sổ ổn định
    
    # --- Bước 2: Khởi tạo Controller và định nghĩa Spec ---
    controller = UIController()
    
    logging.info("Đang định nghĩa spec để chọn cửa sổ mới nhất...")
    # Spec để tìm tất cả các cửa sổ Notepad và sắp xếp chúng theo thời gian tạo
    # 'sort_by_creation_time': -1  <-- Đây là chìa khóa.
    #  -1 có nghĩa là lấy phần tử cuối cùng trong danh sách đã sắp xếp,
    #     tức là cửa sổ được tạo ra gần đây nhất (mới nhất).
    #  -2 sẽ là cửa sổ mới thứ nhì.
    #   1 sẽ là cửa sổ cũ nhất (mở đầu tiên).
    window_spec = {
        'pwa_class_name': 'Notepad',
        'sort_by_creation_time': -1 
    }

    # Spec cho vùng soạn thảo bên trong Notepad
    editor_spec = {'pwa_control_type': 'Document'}
    
    # --- Bước 3: Thực thi hành động ---
    logging.info(f"Đang thực thi hành động trên cửa sổ khớp với spec: {window_spec}")
    
    success = controller.run_action(
        window_spec=window_spec,
        element_spec=editor_spec,
        action="paste_text:THIS IS THE NEWEST WINDOW",
        timeout=15,
        auto_activate=True # Tự động focus vào cửa sổ mới nhất
    )

    if success:
        logging.info("-> THÀNH CÔNG: Đã tìm và tương tác với cửa sổ mới nhất.")
    else:
        logging.error("-> THẤT BẠI: Không thể tìm hoặc tương tác với cửa sổ được chỉ định.")

    # --- Bước 4: Dọn dẹp ---
    logging.info("Đợi 5 giây trước khi đóng tất cả các cửa sổ Notepad...")
    time.sleep(5)
    
    logging.info("Đang đóng tất cả các cửa sổ Notepad...")
    # Lệnh taskkill sẽ đóng tất cả các tiến trình có tên notepad.exe
    # > nul 2>&1 để ẩn output của lệnh
    os.system("taskkill /f /im notepad.exe > nul 2>&1")
    
    logging.info("===== KỊCH BẢN HOÀN TẤT =====")


if __name__ == '__main__':
    run_notepad_selection_test()

