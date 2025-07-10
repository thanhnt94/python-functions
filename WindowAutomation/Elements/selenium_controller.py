# -*- coding: utf-8 -*-
import time
import datetime
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, InvalidArgumentException
from selenium.webdriver.common.by import By

# Import các Options và Service cần thiết cho các trình duyệt
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.ie.service import Service as IeService
from selenium.webdriver.ie.options import Options as IeOptions

# --- TỰ ĐỘNG IMPORT UI NOTIFIER MỘT CÁCH AN TOÀN ---
try:
    # Thử import class StatusNotifier thật
    from ui_notifier import StatusNotifier
except ImportError:
    # Nếu file không tồn tại, tạo một class giả để chương trình không bị lỗi
    print("⚠️ CẢNH BÁO: file 'ui_notifier.py' không được tìm thấy. Các thông báo UI sẽ bị vô hiệu hóa.")
    class StatusNotifier:
        def __init__(self, *args, **kwargs): pass
        def update_status(self, *args, **kwargs): pass
        def stop(self, *args, **kwargs): pass


class SeleniumController:
    """
    Một class Framework 'tất cả trong một' để điều khiển Selenium một cách mạnh mẽ và toàn diện.
    """
    DEFAULT_PATHS = {
        'chrome_driver': None,
        'edge_driver': None,
        'ie_driver': None,
        'edge_exe': r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    }

    def __init__(self,
                 browser_mode: str = 'chrome',
                 url: str = None,
                 headless: bool = False,
                 timeout: int = 15,
                 ui_notifier: object = None,
                 paths: dict = None):
        self.timeout = timeout
        self.driver: WebDriver = None
        self.ui_notifier = ui_notifier
        self.config_paths = self.DEFAULT_PATHS.copy()
        if paths:
            self.config_paths.update(paths)

        browser_mode = browser_mode.lower()
        self._show_notification(f"Đang khởi tạo trình duyệt: {browser_mode.upper()}", style='process')
        
        try:
            if browser_mode == 'chrome':
                options = ChromeOptions()
                if headless:
                    options.add_argument("--headless")
                    options.add_argument("--window-size=1920,1080")
                driver_path = self.config_paths.get('chrome_driver')
                service = ChromeService(executable_path=driver_path) if driver_path else None
                self.driver = webdriver.Chrome(service=service, options=options)
            elif browser_mode == 'edge':
                options = EdgeOptions()
                if headless:
                    options.add_argument("--headless")
                    options.add_argument("--window-size=1920,1080")
                driver_path = self.config_paths.get('edge_driver')
                service = EdgeService(executable_path=driver_path) if driver_path else None
                self.driver = webdriver.Edge(service=service, options=options)
            elif browser_mode == 'iemode':
                driver_path = self.config_paths.get('ie_driver')
                edge_exe_path = self.config_paths.get('edge_exe')
                if not driver_path:
                    raise ValueError("Cần chỉ định 'ie_driver' trong 'paths' khi chạy IE Mode.")
                ie_options = IeOptions()
                ie_options.attach_to_edge_chrome = True
                ie_options.edge_executable_path = edge_exe_path
                ie_options.ignore_protected_mode_settings = True
                ie_options.ignore_zoom_level = True
                service = IeService(executable_path=driver_path)
                self.driver = webdriver.Ie(service=service, options=ie_options)
            else:
                raise ValueError(f"Chế độ trình duyệt '{browser_mode}' không được hỗ trợ.")

            self.wait = WebDriverWait(self.driver, self.timeout)
            self._show_notification("Trình duyệt đã khởi tạo thành công.", style='success')
            if url:
                self.go_to_url(url, description=f"Mở trang web ban đầu")
        except Exception as e:
            self._show_notification(f"LỖI KHỞI TẠO: {e}", style='error', duration=0)
            print(f"❌ LỖI NGHIÊM TRỌNG khi khởi tạo trình duyệt: {e}")
            raise

    def _show_notification(self, message: str, style: str = 'info', duration: int = 3, buttons: list = None):
        if self.ui_notifier:
            try:
                self.ui_notifier.update_status(message, style=style, duration=duration, buttons=buttons)
            except Exception as e:
                print(f"⚠️ CẢNH BÁO: Không thể hiển thị thông báo UI. Lỗi: {e}")

    def go_to_url(self, url: str, description: str = None):
        log_msg = description or f"Điều hướng đến URL: {url}"
        self._show_notification(log_msg, style='process')
        print(log_msg)
        self.driver.get(url)

    def _find_element(self, by_locator: tuple) -> WebElement:
        try:
            return self.wait.until(EC.visibility_of_element_located(by_locator))
        except TimeoutException:
            error_msg = f"Hết thời gian chờ. Không tìm thấy element: {by_locator}"
            print(f"❌ LỖI: {error_msg}")
            self._show_notification(error_msg, style='error', duration=5)
            self.take_screenshot("ERROR_FIND_ELEMENT")
            raise

    def click(self, by_locator: tuple, description: str = None):
        log_msg = description or f"Click vào element: {by_locator}"
        self._show_notification(log_msg, style='process')
        print(log_msg)
        try:
            element = self.wait.until(EC.element_to_be_clickable(by_locator))
            element.click()
        except Exception as e:
            error_msg = f"Lỗi khi click vào {by_locator}"
            print(f"❌ {error_msg}")
            self._show_notification(error_msg, style='error', duration=5)
            self.take_screenshot("ERROR_CLICK")
            raise e

    def enter_text(self, by_locator: tuple, text: str, description: str = None):
        log_msg = description or f"Nhập text vào element: {by_locator}"
        self._show_notification(log_msg, style='process')
        print(log_msg)
        try:
            element = self._find_element(by_locator)
            element.clear()
            element.send_keys(text)
        except Exception as e:
            error_msg = f"Lỗi khi nhập text vào {by_locator}"
            print(f"❌ {error_msg}")
            self._show_notification(error_msg, style='error', duration=5)
            self.take_screenshot("ERROR_ENTER_TEXT")
            raise e

    def get_text(self, by_locator: tuple, description: str = None) -> str:
        log_msg = description or f"Lấy text từ element: {by_locator}"
        self._show_notification(log_msg, style='process', duration=2)
        print(log_msg)
        try:
            return self._find_element(by_locator).text
        except Exception as e:
            error_msg = f"Lỗi khi lấy text từ {by_locator}"
            print(f"❌ {error_msg}")
            self._show_notification(error_msg, style='error', duration=5)
            self.take_screenshot("ERROR_GET_TEXT")
            raise e

    def get_attribute(self, by_locator: tuple, attribute_name: str) -> str:
        try:
            return self._find_element(by_locator).get_attribute(attribute_name)
        except Exception as e:
            print(f"❌ LỖI khi lấy thuộc tính '{attribute_name}' từ {by_locator}.")
            self.take_screenshot("ERROR_GET_ATTRIBUTE")
            raise e
            
    # --- HÀM BỊ THIẾU ĐÃ ĐƯỢC THÊM VÀO ---
    def get_title(self) -> str:
        """Lấy tiêu đề của trang hiện tại."""
        return self.driver.title

    def execute_script(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    def scroll_to_element(self, by_locator: tuple):
        print(f"Cuộn trang đến element: {by_locator}")
        try:
            element = self._find_element(by_locator)
            self.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        except Exception as e:
            print(f"❌ LỖI khi cuộn trang đến {by_locator}.")
            self.take_screenshot("ERROR_SCROLL")
            raise e
            
    def take_screenshot(self, file_name_prefix: str) -> str:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        full_path = f"{file_name_prefix}_{timestamp}.png"
        try:
            self.driver.save_screenshot(full_path)
            print(f"📸 Đã chụp màn hình và lưu tại: {full_path}")
            self._show_notification(f"Đã lưu ảnh lỗi: {full_path}", style='warning')
            return full_path
        except Exception as e:
            print(f"❌ Không thể chụp màn hình: {e}")
            return ""

    # --- HÀM BỊ THIẾU ĐÃ ĐƯỢC THÊM VÀO ---
    def wait_for_page_load_complete(self, timeout: int = None):
        """
        Chờ cho trang tải hoàn toàn (document.readyState === 'complete').
        """
        wait = self.wait if timeout is None else WebDriverWait(self.driver, timeout)
        print("Đang chờ trang tải hoàn tất...")
        try:
            wait.until(lambda driver: driver.execute_script('return document.readyState') == 'complete')
        except Exception as e:
            print(f"❌ LỖI khi chờ trang tải: {e}")
            self.take_screenshot("ERROR_PAGE_LOAD")
            raise e

    def quit(self):
        if self.driver:
            self._show_notification("Đóng trình duyệt...", style='info', duration=2)
            print("--- Đóng trình duyệt ---")
            self.driver.quit()
            self.driver = None
