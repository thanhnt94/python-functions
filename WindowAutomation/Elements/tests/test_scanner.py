# tests/test_ui_scanner_with_spec.py
# Kịch bản test trực tiếp để kiểm tra việc UIScanner có thể
# quét một cửa sổ cụ thể bằng bộ lọc (spec).

import os
import sys
import time
import logging
from pathlib import Path

# Thêm đường dẫn thư mục cha
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_scanner import UIScanner

def setup_logging():
    """Cấu hình logging cơ bản."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def run_scanner_spec_test():
    """Hàm chính để chạy kịch bản test."""
    setup_logging()
    logging.info("===== BẮT ĐẦU KỊCH BẢN: TEST UISCANNER VỚI SPEC =====")
    
    try:
        # --- Bước 1: Chuẩn bị môi trường ---
        logging.info("Đang mở 3 cửa sổ Notepad...")
        for i in range(3):
            os.startfile("notepad.exe")
            time.sleep(0.5)
        time.sleep(2) # Chờ các cửa sổ ổn định

        # --- Bước 2: Khởi tạo Scanner và định nghĩa Spec ---
        scanner = UIScanner()
        
        # Spec này sẽ tìm cửa sổ Notepad cũ nhất (mở đầu tiên)
        spec_to_scan = {
            'pwa_class_name': 'Notepad',
            'sort_by_creation_time': 1 # 1 = cũ nhất
        }
        
        # Tạo thư mục đầu ra
        output_dir = Path.home() / "UiScannerTestResults"
        output_dir.mkdir(exist_ok=True)
        logging.info(f"Kết quả sẽ được lưu vào: {output_dir}")
        
        # --- Bước 3: Chạy quét với spec đã định nghĩa ---
        output_path = scanner.scan_and_save_to_excel(
            window_spec=spec_to_scan,
            output_dir=output_dir
        )

        # --- Bước 4: Kiểm tra kết quả ---
        if output_path and os.path.exists(output_path):
            logging.info(f"-> THÀNH CÔNG: File Excel đã được tạo tại '{output_path}'")
            logging.info("Hãy mở file để kiểm tra xem nó có đúng là thông tin của một cửa sổ Notepad không.")
        else:
            logging.error("-> THẤT BẠI: Không tạo được file Excel.")

    except Exception as e:
        logging.error(f"Đã xảy ra lỗi không mong muốn: {e}", exc_info=True)
    finally:
        # --- Bước 5: Dọn dẹp ---
        logging.info("Đang đóng tất cả cửa sổ Notepad...")
        os.system("taskkill /f /im notepad.exe > nul 2>&1")
        
    logging.info("===== KỊCH BẢN HOÀN TẤT =====")


if __name__ == '__main__':
    run_scanner_spec_test()
