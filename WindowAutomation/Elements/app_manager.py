# Elements/app_manager.py
# Chứa các hàm tiện ích để quản lý tiến trình: khởi động và đóng ứng dụng.

import logging
import subprocess
import shlex
import os
import time
import psutil # Thư viện cần thiết để làm việc với các tiến trình
from pywinauto import Desktop # Thêm import để tìm cửa sổ

# Cấu hình logging cho module này
logger = logging.getLogger(__name__)

def launch_app(command_line, close_existing=False):
    """
    Khởi động một ứng dụng bằng một dòng lệnh.

    Args:
        command_line (str): Dòng lệnh để thực thi.
        close_existing (bool): Nếu True, sẽ đóng tất cả các tiến trình cũ
                               của ứng dụng này trước khi chạy mới.
    """
    logger.info(f"Chuẩn bị thực thi lệnh: {command_line}")
    try:
        # Dùng shlex.split để xử lý các lệnh có khoảng trắng và tham số một cách an toàn
        args = shlex.split(command_line)
        
        # NÂNG CẤP: Thêm lại logic đóng các tiến trình cũ
        if close_existing:
            # Lấy tên file thực thi từ dòng lệnh (ví dụ: 'notepad.exe')
            executable_name = os.path.basename(args[0])
            logger.info(f"Yêu cầu đóng các tiến trình '{executable_name}' cũ...")
            
            # Gọi hàm kill_app để thực hiện việc đóng
            kill_app(process_name=executable_name)
            
            # Chờ một chút để hệ điều hành xử lý việc đóng tiến trình
            time.sleep(1)
            logger.info("Đã gửi lệnh đóng các tiến trình cũ.")

        # Khởi động tiến trình mới và không chờ nó kết thúc
        subprocess.Popen(args)
        
        logger.info("Đã gửi lệnh khởi động thành công.")
        
    except FileNotFoundError:
        logger.error(f"Lỗi: Không tìm thấy file thực thi trong lệnh: '{command_line}'")
    except Exception as e:
        logger.error(f"Không thể khởi động ứng dụng: {e}", exc_info=True)

def kill_app(process_name=None, pid=None, pwa_title=None):
    """
    Đóng một hoặc nhiều tiến trình của một ứng dụng một cách mạnh mẽ.

    Args:
        process_name (str, optional): Tên của tiến trình cần đóng (ví dụ: "notepad.exe").
        pid (int, optional): ID của một tiến trình cụ thể cần đóng.
        pwa_title (str, optional): Một phần hoặc toàn bộ tiêu đề cửa sổ.
                                   Sẽ đóng tất cả các tiến trình có cửa sổ khớp tiêu đề.
    """
    if not process_name and not pid and not pwa_title:
        logger.warning("kill_app: Cần cung cấp process_name, pid, hoặc pwa_title để đóng ứng dụng.")
        return

    try:
        # Ưu tiên đóng theo tiêu đề cửa sổ
        if pwa_title:
            logger.info(f"Đang tìm và đóng các cửa sổ có tiêu đề chứa: '{pwa_title}'...")
            pids_to_kill = set()
            desktop = Desktop(backend='uia')
            for window in desktop.windows():
                try:
                    # So sánh không phân biệt hoa thường và chứa chuỗi
                    if pwa_title.lower() in window.window_text().lower():
                        pids_to_kill.add(window.process_id())
                except Exception:
                    continue
            
            if not pids_to_kill:
                logger.info(f"Không tìm thấy cửa sổ nào có tiêu đề khớp với '{pwa_title}'.")
                return

            logger.info(f"Tìm thấy {len(pids_to_kill)} tiến trình để đóng dựa trên tiêu đề: {pids_to_kill}")
            for p_id in pids_to_kill:
                try:
                    p = psutil.Process(p_id)
                    p.terminate()
                except psutil.NoSuchProcess:
                    continue
            
            gone, alive = psutil.wait_procs([psutil.Process(p_id) for p_id in pids_to_kill if psutil.pid_exists(p_id)], timeout=3)
            for p in alive:
                logger.warning(f"Không thể đóng PID {p.pid} một cách an toàn, đang thử đóng mạnh (kill)...")
                p.kill()

        # Đóng theo tên tiến trình
        elif process_name:
            logger.info(f"Đang gửi lệnh đóng tất cả các tiến trình có tên: '{process_name}'...")
            kill_command = f"taskkill /f /im {process_name} > nul 2>&1"
            result = os.system(kill_command)
            
            if result == 0:
                 logger.info(f"Đã gửi lệnh đóng thành công các tiến trình '{process_name}'.")
            else:
                 logger.info(f"Không tìm thấy tiến trình nào đang chạy với tên '{process_name}'.")

        # Đóng theo PID cụ thể
        elif pid:
            logger.info(f"Đang cố gắng đóng tiến trình với PID: {pid}...")
            p = psutil.Process(pid)
            p.terminate()
            gone, alive = psutil.wait_procs([p], timeout=3)
            
            if gone:
                logger.info(f"Đã đóng thành công tiến trình PID {pid}.")
            elif alive:
                logger.warning(f"Không thể đóng PID {pid} một cách an toàn, đang thử đóng mạnh (kill)...")
                p.kill()
                logger.info(f"Đã đóng mạnh tiến trình PID {pid}.")

    except psutil.NoSuchProcess:
        logger.error(f"Lỗi: Không tìm thấy tiến trình nào với PID được cung cấp.")
    except Exception as e:
        logger.error(f"Lỗi khi đóng ứng dụng: {e}", exc_info=True)
