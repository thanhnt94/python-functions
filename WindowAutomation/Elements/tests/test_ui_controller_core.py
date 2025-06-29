# tests/test_ui_controller_core.py
# Test các chức năng cốt lõi của UIController.

import os
import sys
import time
import pytest
from pywinauto.application import Application

# Thêm đường dẫn thư mục cha
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_controller import UIController, WindowNotFoundError, AmbiguousElementError

# ===== FIXTURE ĐÃ ĐƯỢC SỬA LẠI HOÀN TOÀN ĐỂ CHẠY ỔN ĐỊNH =====

@pytest.fixture
def single_notepad_app():
    """
    SỬA LỖI CUỐI CÙNG: Dùng phương pháp ổn định nhất của pywinauto
    để khởi động và chờ Notepad, giải quyết các vấn đề về timing.
    """
    app = None
    try:
        # Dùng start() và lấy object app, tăng timeout để đảm bảo tiến trình khởi động
        app = Application(backend='uia').start("notepad.exe", timeout=20)

        # Chờ cho đến khi cửa sổ chính của app thực sự tồn tại và sẵn sàng.
        # Sử dụng `class_name="Notepad"` để tìm kiếm chính xác hơn là `top_window()`
        # Đây là bước quan trọng nhất để giải quyết lỗi
        main_window = app.window(class_name="Notepad")
        main_window.wait('ready', timeout=20)
        
        # Trả về cả object app, chứa cả thông tin process và cửa sổ
        yield app
    finally:
        # Đảm bảo app được đóng ngay cả khi test thất bại
        if app and app.is_process_running():
            app.kill()

@pytest.fixture
def multiple_notepad_apps():
    """Fixture mở hai cửa sổ Notepad và chờ cả hai sẵn sàng."""
    apps = []
    try:
        for _ in range(2):
            # Khởi động từng app riêng biệt và chờ nó sẵn sàng
            app = Application(backend='uia').start("notepad.exe", timeout=20)
            main_window = app.window(class_name="Notepad")
            main_window.wait('ready', timeout=20)
            apps.append(app)
        # Trả về list các object app
        yield apps
    finally:
        for app in apps:
            if app and app.is_process_running():
                app.kill()

# ===== CÁC BÀI TEST ĐÃ ĐƯỢC CẬP NHẬT ĐỂ TƯƠNG THÍCH VỚI FIXTURE MỚI =====

def test_select_element_by_pid_success(single_notepad_app):
    """
    Kiểm tra tìm kiếm thành công bằng PID.
    """
    controller = UIController()
    # single_notepad_app giờ là một object Application, lấy pid từ single_notepad_app.process
    spec = {'proc_pid': single_notepad_app.process}
    element = controller.select_element(window_spec=spec)
    
    assert element is not None
    assert element.element_info.class_name == 'Notepad'

def test_select_element_raises_error_for_nonexistent_window():
    """Kiểm tra WindowNotFoundError được ném ra khi không tìm thấy cửa sổ."""
    controller = UIController()
    spec = {'pwa_title': 'CuaSoNayChacChanKhongCoTonTaiTrenDoi'}
    
    with pytest.raises(WindowNotFoundError):
        controller.select_element(window_spec=spec, timeout=1)

def test_select_element_raises_error_for_ambiguous_spec(multiple_notepad_apps):
    """Kiểm tra AmbiguousElementError được ném ra khi có nhiều kết quả."""
    controller = UIController()
    # Spec này sẽ khớp với TẤT CẢ các cửa sổ Notepad đang mở
    spec = {'pwa_class_name': 'Notepad'}

    with pytest.raises(AmbiguousElementError):
        controller.select_element(window_spec=spec, timeout=2)

def test_get_properties_from_notepad(single_notepad_app):
    """
    Kiểm tra lấy thuộc tính từ đúng cửa sổ bằng PID.
    """
    controller = UIController()
    spec = {'proc_pid': single_notepad_app.process}
    
    # Lấy tiêu đề
    title = controller.get_property(window_spec=spec, property_name='pwa_title')
    assert title is not None
    assert "Untitled - Notepad" in title or "Không tên - Notepad" in title

    # Lấy trạng thái
    is_enabled = controller.get_property(window_spec=spec, property_name='state_is_enabled')
    assert is_enabled is True
