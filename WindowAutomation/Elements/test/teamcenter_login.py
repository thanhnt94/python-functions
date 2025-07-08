# tests/teamcenter_login.py
# --- VERSION 2.0: Upgraded to use the new AppManager class for robust lifecycle management.

import os
import sys
import time
import logging

# --- Cấu hình và Import ---

def setup_logging():
    """Cấu hình logging cơ bản."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

# Thêm đường dẫn thư mục cha để import các module đúng theo cấu trúc của bạn
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from functions.core_controller import UIController
    from functions.ui_notifier import StatusNotifier
    # Import lớp AppManager và hàm kill_app tiện ích
    from functions.app_manager import AppManager, kill_app
except ImportError:
    print("Lỗi: Không thể import các module cần thiết. Hãy đảm bảo cấu trúc thư mục của bạn là chính xác.")
    print("Cấu trúc gợi ý: \n- your_project/\n  |- functions/\n  |  |- app_manager.py\n  |  |- ...\n  |- tests/\n     |- test_teamcenter_login.py")
    sys.exit(1)


def run_teamcenter_login_test(username, password):
    """
    Chạy kịch bản đăng nhập Teamcenter sử dụng AppManager.
    """
    setup_logging()

    # --- Bước 1: Khởi tạo các công cụ ---
    notifier = StatusNotifier(config={'theme': 'dark', 'position': 'top_right'})
    controller = UIController(notifier=notifier, default_timeout=60, auto_activate=True)
    
    # --- Bước 2: Định nghĩa ứng dụng Teamcenter ---
    # Định nghĩa một lần duy nhất, bao gồm lệnh khởi chạy và spec của cửa sổ chờ.
    login_window_spec = {
        'proc_name': 'javaw.exe',
        'pwa_title': 'Teamcenter Login',
    }
    teamcenter_app = AppManager(
        name="Teamcenter",
        command_line=r'"C:\UGS\NAP\v2306\UGII\startup.exe" /l:english',
        main_window_spec=login_window_spec,
        controller=controller # Cung cấp controller để AppManager sử dụng
    )

    try:
        # --- Bước 3: Dọn dẹp và Khởi động ---
        notifier.update_status("Bắt đầu kịch bản đăng nhập Teamcenter...", style='info')
        
        notifier.update_status("Dọn dẹp môi trường...", style='process')
        # Sử dụng hàm kill_app tiện ích để đóng các tiến trình có thể còn sót lại
        kill_app(process_name='javaw.exe')
        kill_app(process_name='startup.exe')
        time.sleep(2)

        # Khởi chạy và chờ cho đến khi cửa sổ đăng nhập sẵn sàng
        if not teamcenter_app.launch(wait_ready=True, timeout=120):
            # Nếu sau 2 phút mà cửa sổ không xuất hiện, báo lỗi và thoát
            raise RuntimeError("Không thể khởi động Teamcenter hoặc cửa sổ đăng nhập không xuất hiện.")

        # --- Bước 4: Định nghĩa các spec cho phần tử ---
        username_spec = {'pwa_class_name': 'Edit', 'sort_by_scan_order': 1}
        password_spec = {'pwa_class_name': 'Edit', 'sort_by_scan_order': 2}
        login_button_spec = {'pwa_title': 'Login'}

        # --- Bước 5: Thực hiện các hành động ---
        controller.run_action(
            window_spec=login_window_spec,
            element_spec=username_spec,
            action=f"set_text:{username}",
            description=f"Điền Username: {username}"
        )
        controller.run_action(
            window_spec=login_window_spec,
            element_spec=password_spec,
            action=f"set_text:{password}",
            description="Điền Password"
        )
        controller.run_action(
            window_spec=login_window_spec,
            element_spec=login_button_spec,
            action="click",
            description="Nhấn nút Login"
        )
        
        # --- Bước 6: Kiểm tra kết quả đăng nhập ---
        notifier.update_status("Đang kiểm tra kết quả đăng nhập...", style='process')
        
        possible_outcomes = {
            "login_success": {
                "window_spec": {'pwa_title': ('icontains', 'Teamcenter RAC')}
            },
            "login_failed": {
                "window_spec": login_window_spec,
                "element_spec": {'pwa_title': 'The login attempt failed: either the user ID or the password is invalid.', 'sort_by_scan_order': 1}
            }
        }
        
        final_state = controller.get_next_state(
            cases=possible_outcomes,
            timeout=180, # Chờ tối đa 3 phút để Teamcenter khởi động hoàn tất
            description="Chờ kết quả đăng nhập"
        )

        if final_state == "login_success":
            notifier.update_status("Đăng nhập thành công!", style='success', duration=10)
        elif final_state == "login_failed":
            notifier.update_status("Đăng nhập thất bại! Sai User ID hoặc Password.", style='error', duration=10)
        else:
            notifier.update_status("Không xác định được trạng thái sau khi đăng nhập.", style='error', duration=0)

    except Exception as e:
        logging.error(f"Đã xảy ra lỗi không mong muốn: {e}", exc_info=True)
        notifier.update_status(f"Lỗi nghiêm trọng: {e}", style='error', duration=0)
        time.sleep(10)
    finally:
        logging.info("Kịch bản kết thúc.")
        time.sleep(5)
        if notifier:
            notifier.stop()
        logging.info("===== KỊCH BẢN HOÀN TẤT =====")


if __name__ == '__main__':
    TC_USERNAME = "KNT15083"
    # Chú ý: Đây chỉ là ví dụ. Trong thực tế, hãy dùng các phương pháp an toàn hơn
    # để quản lý mật khẩu, ví dụ như biến môi trường hoặc một dịch vụ quản lý bí mật.
    TC_PASSWORD = "your_password_here" 
    
    run_teamcenter_login_test(username=TC_USERNAME, password=TC_PASSWORD)
