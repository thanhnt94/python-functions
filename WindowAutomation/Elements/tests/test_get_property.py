# tests/test_get_property.py
# Kịch bản test trực tiếp để kiểm tra hàm get_property của UIController.
# Kịch bản: Mở Notepad, gõ văn bản, sau đó dùng get_property để đọc lại và xác thực.

import os
import sys
import time
import logging

# Thêm đường dẫn thư mục cha để import các module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_controller import UIController, WindowNotFoundError

def setup_logging():
    """Cấu hình logging cơ bản."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def run_get_property_test():
    """Hàm chính để chạy kịch bản test."""
    setup_logging()
    logging.info("===== BẮT ĐẦU KỊCH BẢN: TEST GET_PROPERTY (TÌM CỬA SỔ MỚI NHẤT) =====")
    
    try:
        # --- Bước 1: Chuẩn bị môi trường ---
        logging.info("Khởi động cửa sổ Notepad mục tiêu...")
        os.startfile("notepad.exe")
        time.sleep(2) 
        logging.info("Notepad đã sẵn sàng.")

        # --- Bước 2: Tìm cửa sổ mới nhất và lấy handle của nó ---
        controller = UIController()
        text_to_type = "Hello, this is the correct window!"

        # Spec để tìm cửa sổ mới nhất
        find_newest_spec = {
            'pwa_class_name': 'Notepad',
            'sort_by_creation_time': -1 
        }
        
        logging.info("Đang tìm cửa sổ mới nhất để lấy handle...")
        newest_window = controller.select_element(window_spec=find_newest_spec)

        if not newest_window:
            logging.error("Không tìm thấy cửa sổ Notepad nào. Dừng test.")
            return

        # Lấy handle - đây là định danh duy nhất và không đổi của cửa sổ
        target_handle = newest_window.handle
        logging.info(f"Đã tìm thấy cửa sổ mục tiêu với handle: {target_handle}")

        # --- Bước 3: Dùng handle để tương tác chính xác ---
        
        # SỬA LỖI: Tạo spec mới để nhắm chính xác vào handle đã tìm thấy
        target_window_spec = {'win32_handle': target_handle}
        editor_spec = {'pwa_control_type': 'Document'}

        logging.info(f"Đang gõ nội dung vào cửa sổ với handle {target_handle}...")
        type_success = controller.run_action(
            window_spec=target_window_spec,
            element_spec=editor_spec,
            action=f"paste_text:{text_to_type}",
            auto_activate=True
        )

        if not type_success:
            logging.error("Có lỗi xảy ra khi gõ văn bản. Dừng test.")
            return

        time.sleep(1)

        # --- Bước 4: Dùng handle để đọc lại nội dung ---
        logging.info(f"Đang đọc lại nội dung từ cửa sổ với handle {target_handle}...")
        retrieved_text = controller.get_property(
            window_spec=target_window_spec,
            element_spec=editor_spec,
            property_name='text'
        )

        logging.info(f"Nội dung lấy được: '{retrieved_text}'")

        # --- Bước 5: So sánh và xác thực ---
        if retrieved_text == text_to_type:
            logging.info("-> THÀNH CÔNG: Nội dung lấy lại khớp với nội dung đã gõ.")
        else:
            logging.error("-> THẤT BẠI: Nội dung không khớp!")
            logging.error(f"  - Mong đợi: '{text_to_type}'")
            logging.error(f"  - Thực tế: '{retrieved_text}'")

    except Exception as e:
        logging.error(f"Đã xảy ra lỗi không mong muốn trong quá trình test: {e}", exc_info=True)
    finally:
        # --- Bước 6: Dọn dẹp ---
        logging.info("Đang đóng TẤT CẢ các cửa sổ Notepad...")
        os.system("taskkill /f /im notepad.exe > nul 2>&1")
        
    logging.info("===== KỊCH BẢN HOÀN TẤT =====")


if __name__ == '__main__':
    run_get_property_test()

