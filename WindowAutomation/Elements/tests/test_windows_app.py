# tests/test_windows_apps.py
# Chứa các kịch bản test cho những ứng dụng mặc định của Windows
# như Máy tính và File Explorer.

import os
import time
import logging
import sys
import pytest
import subprocess # Sử dụng để quản lý tiến trình tốt hơn

# Thêm đường dẫn thư mục cha để có thể import các module khác
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_controller import UIController

# =================================================================
#                     TEST CASE CHO MÁY TÍNH (CALCULATOR)
# =================================================================

@pytest.fixture
def calculator_app():
    """
    Fixture để quản lý ứng dụng Máy tính (Calculator).
    - Setup: Khởi chạy Calculator.
    - Teardown: Đóng ứng dụng.
    """
    logging.info("--- SETUP: Mở ứng dụng Máy tính ---")
    # Sử dụng subprocess để có thể kiểm soát tiến trình tốt hơn
    app_process = subprocess.Popen("calc.exe", shell=True)
    time.sleep(2)  # Chờ ứng dụng khởi động

    yield # Điểm chạy của test case

    logging.info("--- TEARDOWN: Đóng ứng dụng Máy tính ---")
    app_process.terminate() # Gửi tín hiệu đóng tiến trình

def test_calculator_simple_addition():
    """
    Test kịch bản cộng đơn giản: 1 + 7 = 8.
    Kiểm tra các hành động 'click' và 'get_property'.
    """
    logging.info("===== BẮT ĐẦU TEST: Phép cộng trên Máy tính =====")
    controller = UIController()

    # Spec cho cửa sổ Calculator trên Windows 11
    # Tiêu đề có thể thay đổi theo ngôn ngữ, nhưng pwa_class_name thường ổn định
    window_spec = {"pwa_class_name": "ApplicationFrameWindow", "pwa_title": "Calculator"}

    # Các Automation ID cho các nút của máy tính (chuẩn trên Win11)
    # Bạn có thể dùng interactive_scanner.py để tự kiểm tra các ID này
    spec_button_1 = {"pwa_auto_id": "num1Button"}
    spec_button_7 = {"pwa_auto_id": "num7Button"}
    spec_button_plus = {"pwa_auto_id": "plusButton"}
    spec_button_equal = {"pwa_auto_id": "equalButton"}
    spec_results = {"pwa_auto_id": "CalculatorResults"}

    # Thực hiện phép tính 1 + 7 =
    actions = [
        ("click", spec_button_1),
        ("click", spec_button_plus),
        ("click", spec_button_7),
        ("click", spec_button_equal),
    ]

    for action, element_spec in actions:
        logging.info(f"Thực hiện hành động '{action}' trên element: {element_spec['pwa_auto_id']}")
        success = controller.run_action(
            window_spec=window_spec,
            element_spec=element_spec,
            action=action,
            timeout=5
        )
        assert success is True, f"Thất bại khi thực hiện '{action}' trên {element_spec['pwa_auto_id']}"
        time.sleep(0.5) # Thêm độ trễ nhỏ giữa các lần click

    # Lấy kết quả và kiểm tra
    result_text = controller.get_property(
        window_spec=window_spec,
        element_spec=spec_results,
        property_name="pwa_title" # Thuộc tính Name (pwa_title) chứa kết quả hiển thị
    )
    
    logging.info(f"Giá trị kết quả đọc được: '{result_text}'")
    
    # Kết quả trên máy tính thường có dạng "Display is 8"
    # Chúng ta chỉ cần kiểm tra xem số '8' có trong chuỗi đó không
    assert result_text is not None, "Không thể lấy được kết quả"
    assert "8" in result_text, f"Kết quả mong đợi là '8' nhưng nhận được '{result_text}'"

    logging.info("\n===== TEST HOÀN TẤT: Phép cộng trên Máy tính =====")


# =================================================================
#                     TEST CASE CHO FILE EXPLORER
# =================================================================

@pytest.fixture
def explorer_window():
    """
    Fixture để quản lý cửa sổ File Explorer.
    - Setup: Mở một cửa sổ Explorer mới.
    - Teardown: Đóng cửa sổ đó.
    """
    logging.info("--- SETUP: Mở cửa sổ File Explorer mới ---")
    # Mở thư mục người dùng
    app_process = subprocess.Popen("explorer.exe")
    time.sleep(3) # Chờ cửa sổ xuất hiện và tải xong

    yield # Điểm chạy của test case

    logging.info("--- TEARDOWN: Đóng cửa sổ File Explorer ---")
    # Vì explorer.exe quản lý cả desktop, chúng ta không nên kill nó.
    # Thay vào đó, ta sẽ tìm và đóng cửa sổ đã mở.
    # Cách đơn giản nhất trong môi trường test là kill tiến trình đã tạo.
    app_process.terminate()

def test_explorer_navigate_and_find_file(explorer_window):
    """
    Test kịch bản:
    1. Điều hướng đến thư mục C:\Windows.
    2. Tìm file 'explorer.exe' trong danh sách.
    Kiểm tra 'type_keys' và 'select_element'.
    """
    logging.info("===== BẮT ĐẦU TEST: Điều hướng và tìm file trong Explorer =====")
    controller = UIController()

    # Spec cho cửa sổ File Explorer
    window_spec = {"pwa_class_name": "CabinetWClass"}
    
    # Tìm thanh địa chỉ và gõ đường dẫn
    # Thanh địa chỉ là một phần của Toolbar
    address_bar_spec = {"pwa_control_type": "Edit", "pwa_title": "Address"}
    path_to_type = r"C:\Windows"
    
    logging.info(f"Điều hướng đến: {path_to_type}")
    
    # Sử dụng type_keys để nhập đường dẫn và nhấn Enter
    # {ENTER} là mã phím đặc biệt mà type_keys hiểu được
    success_nav = controller.run_action(
        window_spec=window_spec,
        element_spec=address_bar_spec,
        action=f"type_keys:{path_to_type}{{ENTER}}",
        timeout=10,
        auto_activate=True
    )
    assert success_nav, "Thất bại khi điều hướng đến thư mục Windows"
    
    time.sleep(3) # Chờ cho các file trong thư mục được tải

    # Tìm một file cụ thể trong danh sách
    logging.info("Tìm kiếm file 'explorer.exe' trong danh sách")
    file_spec = {"pwa_control_type": "DataItem", "pwa_title": "explorer.exe"}

    # Sử dụng select_element để kiểm tra xem file có tồn tại không
    found_element = controller.select_element(
        window_spec=window_spec,
        element_spec=file_spec,
        timeout=15 # Tăng timeout vì thư mục Windows có rất nhiều file
    )

    assert found_element is not None, "Không tìm thấy file 'explorer.exe' trong C:\\Windows"
    logging.info(f"Đã tìm thấy element: {found_element.window_text()}")
    
    logging.info("\n===== TEST HOÀN TẤT: Điều hướng và tìm file trong Explorer =====")