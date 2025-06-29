# Elements/ui_core.py
# Chứa các hàm lõi, tiện ích được chia sẻ giữa các module quét và điều khiển.

import logging
import time
from datetime import datetime

# --- Thư viện bên thứ ba ---
try:
    import psutil
    import win32gui
    import win32process
    import win32con
    import comtypes
    from pywinauto import Desktop
except ImportError as e:
    print(f"Lỗi import thư viện, vui lòng cài đặt: {e}")
    exit()

# Khởi tạo logger chung cho core
logger = logging.getLogger(__name__)

# --- BỘ NHỚ ĐỆM (CACHE) ---
PROC_INFO_CACHE = {}

# --- CÁC HÀM LẤY THÔNG TIN TIẾN TRÌNH (PROCESS) ---

def get_process_info(pid):
    """
    Lấy thông tin tiến trình từ cache hoặc psutil.
    Cải tiến: Trả về một dictionary trống nếu có lỗi và log chi tiết.
    """
    if pid in PROC_INFO_CACHE:
        return PROC_INFO_CACHE[pid]
    if pid > 0:
        try:
            p = psutil.Process(pid)
            info = {
                'proc_name': p.name(),
                'proc_path': p.exe(),
                'proc_cmdline': ' '.join(p.cmdline()),
                'proc_create_time': datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S'),
                'proc_username': p.username()
            }
            PROC_INFO_CACHE[pid] = info
            return info
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Không thể truy cập tiến trình PID={pid}: {e}")
        except Exception as e:
            logger.error(f"Lỗi không xác định khi lấy thông tin tiến trình PID={pid}", exc_info=True)
    return {}

# --- CÁC HÀM LẤY THÔNG TIN CHI TIẾT (WINDOW & ELEMENT) ---

def get_window_details(hwnd):
    """
    Thu thập thông tin chi tiết đầy đủ của một cửa sổ (window).
    """
    data = {}
    if not win32gui.IsWindow(hwnd):
        logger.warning(f"Cửa sổ với handle {hwnd} không còn tồn tại.")
        return data

    try:
        data['win32_handle'] = hwnd
        data['pwa_title'] = win32gui.GetWindowText(hwnd)
        data['pwa_class_name'] = win32gui.GetClassName(hwnd)
        
        thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        data['proc_pid'] = pid
        data['proc_thread_id'] = thread_id
        data.update(get_process_info(pid))

        desktop = Desktop(backend='uia')
        # Lấy đối tượng cửa sổ đầy đủ để truy cập rectangle
        win_wrapper = desktop.window(handle=hwnd)
        win_element = win_wrapper.element_info
        
        # ===== SỬA LỖI: Bổ sung thông tin tọa độ cho cửa sổ =====
        rect = win_wrapper.rectangle()
        data['geo_rectangle_tuple'] = (rect.left, rect.top, rect.right, rect.bottom)
        # ========================================================
        
        data['pwa_auto_id'] = win_element.automation_id
        if win_element.control_type:
            data['pwa_control_type'] = win_element.control_type.capitalize()
        data['pwa_framework_id'] = win_element.framework_id

    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin chi tiết cửa sổ handle={hwnd}", exc_info=True)
    return data


def get_element_details_comprehensive(element):
    """
    Thu thập thông tin chi tiết nhất có thể của một element.
    Cải thiện logging lỗi.
    """
    if not element:
        return {}
    
    data = {}
    try:
        pid = element.CurrentProcessId
        data['proc_pid'] = pid
        data.update(get_process_info(pid))

        data['pwa_title'] = element.CurrentName
        data['pwa_auto_id'] = element.CurrentAutomationId
        data['pwa_class_name'] = element.CurrentClassName
        data['pwa_framework_id'] = element.CurrentFrameworkId
        data['win32_handle'] = element.CurrentNativeWindowHandle
        
        control_type_str = element.CurrentLocalizedControlType or element.CurrentControlType.name.replace('Control', '')
        if control_type_str:
            data['pwa_control_type'] = control_type_str.capitalize()
            
        rect = element.CurrentBoundingRectangle
        if rect:
            data['geo_bounding_rect_tuple'] = (rect.left, rect.top, rect.right, rect.bottom)
            
        data['state_is_enabled'] = bool(element.CurrentIsEnabled)
        
    except comtypes.COMError as e:
        logger.warning(f"Lỗi COM khi truy cập element (có thể đã bị hủy). Lỗi: {e}")
    except Exception as e:
        logger.error(f"Lỗi không xác định khi lấy thông tin element", exc_info=True)
        
    return data

# --- HÀM TIỆN ÍCH ---

def format_dict_as_pep8_string(spec_dict):
    """
    Định dạng dictionary thành chuỗi PEP8 để dễ copy-paste.
    Cải tiến: Tự động loại bỏ các key có giá trị rỗng hoặc không hợp lệ.
    """
    if not spec_dict:
        return "{}"

    # Cải tiến: Chỉ giữ lại các giá trị có ý nghĩa.
    # Giữ lại boolean False, nhưng loại bỏ None, 0, chuỗi rỗng, list rỗng...
    dict_to_format = {
        k: v for k, v in spec_dict.items()
        if not k.startswith('sys_') and (v is False or v)
    }

    if not dict_to_format:
        return "{}"

    items_str = [f"    {repr(k)}: {repr(value)}," for k, value in sorted(dict_to_format.items())]
    return f"{{\n" + "\n".join(items_str) + "\n}"
