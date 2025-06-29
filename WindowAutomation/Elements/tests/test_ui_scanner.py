# tests/test_ui_scanner.py
# Test chức năng của UIScanner.

import os
import sys
import time
import subprocess
import pytest
import pandas as pd # Cần pandas để đọc và kiểm tra file excel

# Thêm đường dẫn thư mục cha
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui_scanner import UIScanner
# Cần import win32gui để có thể mock
import win32gui

@pytest.fixture
def notepad_for_scanning():
    """Fixture mở một Notepad và trả về process và handle của nó."""
    p = subprocess.Popen("notepad.exe")
    time.sleep(2)
    
    hwnd = None
    # pygetwindow là một thư viện hữu ích để lấy handle từ PID một cách ổn định
    try:
        import pygetwindow as gw
        # Chờ cửa sổ xuất hiện và có tiêu đề
        for _ in range(5): # Thử trong 5 giây
            windows = gw.getWindowsWithTitle('Untitled - Notepad') or gw.getWindowsWithTitle('Không tên - Notepad')
            if windows:
                hwnd = windows[0]._hWnd
                break
            time.sleep(1)
        if not hwnd:
            raise RuntimeError("Không tìm thấy handle của cửa sổ Notepad.")
    except ImportError:
        pytest.skip("Bỏ qua test này vì thiếu thư viện pygetwindow. Vui lòng chạy: pip install pygetwindow")
    except Exception as e:
        pytest.fail(f"Lỗi khi tìm handle cửa sổ: {e}")
        
    yield p, hwnd
    p.terminate()

def test_scanner_creates_valid_excel_file(notepad_for_scanning, monkeypatch, tmp_path):
    """
    Test xem UIScanner có tạo ra file Excel hợp lệ không.
    - notepad_for_scanning: Fixture để mở Notepad.
    - monkeypatch: Fixture của pytest để thay thế hàm.
    - tmp_path: Fixture của pytest để tạo một thư mục tạm.
    """
    scanner = UIScanner()
    notepad_process, notepad_hwnd = notepad_for_scanning
    
    # Sử dụng monkeypatch để đảm bảo UIScanner luôn "thấy" cửa sổ Notepad của chúng ta
    # là cửa sổ đang hoạt động, tránh trường hợp người dùng click ra ngoài.
    monkeypatch.setattr(win32gui, 'GetForegroundWindow', lambda: notepad_hwnd)

    # Chạy scan và lưu vào thư mục tạm do tmp_path cung cấp
    output_path = scanner.scan_and_save_to_excel(wait_time=0, output_dir=tmp_path)

    # 1. Kiểm tra file có được tạo ra không
    assert output_path is not None, "Hàm scan không trả về đường dẫn file"
    assert os.path.exists(output_path), "File Excel không được tạo ra"

    # 2. Kiểm tra file không bị rỗng
    assert os.path.getsize(output_path) > 0, "File Excel được tạo ra nhưng bị rỗng"

    # 3. Kiểm tra nội dung file Excel
    try:
        xls = pd.ExcelFile(output_path)
        sheet_names = xls.sheet_names
        assert 'Windows Info' in sheet_names
        assert 'Elements Details' in sheet_names
        assert 'Tra cứu thông số' in sheet_names
        
        df_win = pd.read_excel(xls, 'Windows Info')
        assert len(df_win) > 0, "Sheet 'Windows Info' không có dữ liệu"
        # Kiểm tra xem có đúng là thông tin của Notepad không
        assert 'Notepad' in df_win.iloc[0]['pwa_class_name']

    except Exception as e:
        pytest.fail(f"Lỗi khi đọc và xác thực file Excel: {e}")
