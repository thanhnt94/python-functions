# test_wait_for_activation.py
# Kịch bản test để kiểm tra tính năng "chờ người dùng kích hoạt cửa sổ".

import os
import time
import logging
from ui_controller import UIController

def setup_logging():
    """Cấu hình logging cơ bản cho file test."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def run_test_with_manual_activation():
    """
    Test kịch bản: Tìm một cửa sổ Notepad, nếu nó không active,
    chương trình sẽ chờ người dùng kích hoạt nó trước khi hành động.
    """
    logging.info("===== BẮT ĐẦU TEST TÍNH NĂNG CHỜ KÍCH HOẠT =====")
    
    # --- Bước 1: Yêu cầu người dùng chuẩn bị ---
    # Bạn có thể mở sẵn 1 hoặc nhiều cửa sổ Notepad.
    # Script sẽ hành động trên cửa sổ Notepad mà bạn không click vào.
    logging.info("\n>>> VUI LÒNG MỞ SẴN MỘT CỬA SỔ NOTEPAD <<<")
    logging.info(">>> SAU KHI SCRIPT TÌM THẤY CỬA SỔ, HÃY CLICK VÀO NÓ ĐỂ TEST <<<")
    time.sleep(3)

    # Khởi tạo controller ở chế độ chờ (mặc định)
    # auto_activate=False có nghĩa là nó sẽ chờ bạn, không tự ý kích hoạt.
    controller = UIController(auto_activate=False)

    # --- Bước 2: Định nghĩa mục tiêu và hành động ---
    # Chúng ta chỉ cần tìm một cửa sổ Notepad bất kỳ, không cần nó phải active lúc đầu.
    notepad_spec = {
        'pwa_class_name': 'Notepad',
        'proc_create_time': 'latest' # Tìm cái mới nhất cho dễ test
    }
    
    editor_spec = {
        'pwa_control_type': 'Document'
    }

    # 'paste_text' là một hành động yêu cầu cửa sổ phải active
    action_to_run = "paste_text:Văn bản này chỉ được dán khi bạn kích hoạt cửa sổ!"

    # --- Bước 3: Thực thi ---
    # UIController sẽ tìm cửa sổ. Nếu nó không active, nó sẽ vào chế độ chờ.
    success = controller.run_action(
        window_spec=notepad_spec,
        element_spec=editor_spec,
        action=action_to_run,
        timeout=30  # Chờ tối đa 30 giây để bạn có thời gian kích hoạt
    )

    # --- Bước 4: Thông báo kết quả ---
    if success:
        logging.info("-> Kịch bản THÀNH CÔNG! Đã chờ, phát hiện kích hoạt và thực hiện hành động.")
    else:
        logging.error("-> Kịch bản THẤT BẠI. Có thể bạn đã không kích hoạt cửa sổ trong thời gian cho phép.")
    
    logging.info("\n===== KẾT THÚC TEST =====")

if __name__ == '__main__':
    setup_logging()
    run_test_with_manual_activation()
