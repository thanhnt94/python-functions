# tests/test_human_interruption.py
# Kịch bản test để kiểm tra tính năng tự động tạm dừng khi người dùng can thiệp.

import os
import time
import logging
import sys

# Thêm đường dẫn thư mục cha để có thể import các module khác
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_controller import UIController

def setup_logging():
    """Cấu hình logging cơ bản cho file test."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def run_interruption_test():
    """
    Test kịch bản: Chạy một chuỗi hành động và kiểm tra xem chương trình
    có tự động tạm dừng khi người dùng di chuyển chuột/gõ phím không.
    """
    logging.info("===== BẮT ĐẦU TEST TÍNH NĂNG PHÁT HIỆN CAN THIỆP =====")
    
    num_windows_to_open = 3
    cooldown_period = 5 # Giữ nguyên 5 giây để dễ quan sát

    # --- Bước 1: Khởi tạo Controller với tính năng được bật ---
    # Đây là phần quan trọng nhất của bài test
    controller = UIController(
        human_interruption_detection=True, 
        human_cooldown_period=cooldown_period
    )

    # --- Bước 2: Chuẩn bị môi trường ---
    logging.info(f"Đang mở {num_windows_to_open} cửa sổ Notepad để mô phỏng công việc...")
    for _ in range(num_windows_to_open):
        os.startfile("notepad.exe")
        time.sleep(0.5)
    time.sleep(2)

    # --- Bước 3: Bắt đầu vòng lặp và yêu cầu người dùng can thiệp ---
    logging.info("\n>>> BÂY GIỜ, TRONG LÚC SCRIPT ĐANG CHẠY, HÃY THỬ DI CHUYỂN CHUỘT <<<")
    logging.info(">>> BẠN SẼ THẤY CHƯƠNG TRÌNH TẠM DỪNG VÀ CHẠY LẠI KHI BẠN NGỪNG <<<")
    
    base_notepad_spec = {'pwa_class_name': 'Notepad'}
    editor_spec = {'pwa_control_type': 'Document'}

    for i in range(num_windows_to_open):
        # Tạo spec để chọn cửa sổ Notepad cũ nhất chưa được ghi
        # Bằng cách này, nó sẽ không chọn lại cửa sổ đã ghi rồi
        spec_for_this_loop = base_notepad_spec.copy()
        spec_for_this_loop['sort_by_creation_time'] = i + 1 # 1 là cũ nhất, 2 là cũ nhì...

        action_to_run = f"paste_text:Đây là cửa sổ thứ {i + 1} được xử lý."
        
        logging.info(f"\n--- Chuẩn bị hành động trên cửa sổ thứ {i+1} (cũ nhất) ---")
    
        success = controller.run_action(
            window_spec=spec_for_this_loop,
            element_spec=editor_spec,
            action=action_to_run,
            timeout=20, # Tăng timeout để có thời gian test
            auto_activate=True
        )

        if not success:
            logging.error(f"-> Thất bại khi tương tác với cửa sổ tại index {i}. Dừng test.")
            break 
    
    logging.info("\n===== KỊCH BẢN TEST HOÀN TẤT =====")


if __name__ == '__main__':
    setup_logging()
    run_interruption_test()
