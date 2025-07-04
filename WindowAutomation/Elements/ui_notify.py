# functions/ui_notify.py
# Module độc lập để hiển thị các thông báo tạm thời trên màn hình.

import tkinter as tk
from tkinter import font
import queue
import threading
import time

# ======================================================================
#                      CẤU HÌNH MẶC ĐỊNH
# ======================================================================
DEFAULT_NOTIFIER_CONFIG = {
    'theme': 'dark',
    'font_family': 'Segoe UI',
    'font_size': 10,
    'alpha': 0.9,
    'wraplength': 350,
    'padding_x': 15,
    'padding_y': 10,
    'icon_text_spacing': 10,
    'styles': {
        'plain':   {'icon': '',       'fg': '#FFFFFF', 'bg': '#34495E'},
        'info':    {'icon': 'ℹ️', 'fg': '#FFFFFF', 'bg': '#2E86C1'},
        'success': {'icon': '✅', 'fg': '#FFFFFF', 'bg': '#2ECC71'},
        'warning': {'icon': '⚠️', 'fg': '#000000', 'bg': '#F1C40F'},
        'error':   {'icon': '❌', 'fg': '#FFFFFF', 'bg': '#E74C3C'},
        'process': {'icon': '⚙️', 'fg': '#FFFFFF', 'bg': '#5D6D7E'},
        'question':{'icon': '❓', 'fg': '#FFFFFF', 'bg': '#8E44AD'},
        'debug':   {'icon': '🐞', 'fg': '#AAB7B8', 'bg': '#17202A'},
    },
    'position': 'bottom_right',
    'margin_x': 20,
    'margin_y': 20,
    'default_duration': 5,
    'fade_speed': 0.05,
}

class StatusNotifier:
    """
    Quản lý một cửa sổ thông báo đa năng, có thể tùy chỉnh cao.
    """
    def __init__(self, config=None):
        self.queue = queue.Queue()
        self.config = {**DEFAULT_NOTIFIER_CONFIG, **(config or {})}
        
        if self.config['theme'] == 'light':
            light_styles = {
                'plain':   {'icon': '',       'fg': '#000000', 'bg': '#D5D8DC'},
                'info':    {'icon': 'ℹ️', 'fg': '#000000', 'bg': '#AED6F1'},
                'success': {'icon': '✅', 'fg': '#000000', 'bg': '#A9DFBF'},
                'warning': {'icon': '⚠️', 'fg': '#000000', 'bg': '#F9E79F'},
                'error':   {'icon': '❌', 'fg': '#FFFFFF', 'bg': '#F1948A'},
                'process': {'icon': '⚙️', 'fg': '#000000', 'bg': '#AEB6BF'},
                'question':{'icon': '❓', 'fg': '#FFFFFF', 'bg': '#9B59B6'},
                'debug':   {'icon': '🐞', 'fg': '#FFFFFF', 'bg': '#2C3E50'},
            }
            self.config['styles'].update(light_styles)

        self.root = None
        self._current_job = None
        self._is_fading = False

        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.0)
        
        self.icon_font = font.Font(family=self.config['font_family'], size=self.config['font_size'] + 4)
        self.text_font = font.Font(family=self.config['font_family'], size=self.config['font_size'])

        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(expand=True, fill='both')

        self.icon_label = tk.Label(self.main_frame, font=self.icon_font)
        self.text_label = tk.Label(self.main_frame, font=self.text_font, 
                                   wraplength=self.config['wraplength'], justify='left')
        
        self._check_queue()
        self.root.mainloop()
        
    def _check_queue(self):
        try:
            task = self.queue.get_nowait()
            if task['command'] == "STOP":
                self._fade_out_and_destroy()
                return
            elif task['command'] == "UPDATE":
                self._process_update(task['data'])
        except queue.Empty:
            pass
        self.root.after(50, self._check_queue)

    def _process_update(self, data):
        if self._current_job:
            self.root.after_cancel(self._current_job)
            self._current_job = None
        
        style_config = self.config['styles'].get(data['style'], self.config['styles']['info'])
        icon_text = style_config.get('icon', '')
        
        self.main_frame.config(bg=style_config['bg'])
        self.text_label.config(text=data['text'], bg=style_config['bg'], fg=style_config['fg'])
        
        self.icon_label.pack_forget()
        self.text_label.pack_forget()

        if icon_text:
            self.icon_label.config(text=icon_text, bg=style_config['bg'], fg=style_config['fg'])
            self.icon_label.pack(side='left', fill='y', 
                                 padx=(self.config['padding_x'], self.config['icon_text_spacing']), 
                                 pady=self.config['padding_y'])
            self.text_label.pack(side='left', expand=True, fill='both', 
                                 padx=(0, self.config['padding_x']), 
                                 pady=self.config['padding_y'])
        else:
            self.text_label.pack(side='left', expand=True, fill='both', 
                                 padx=self.config['padding_x'], 
                                 pady=self.config['padding_y'])
        
        self._set_window_position()
        self._fade_in()

        duration = data['duration']
        if duration > 0:
            self._current_job = self.root.after(int(duration * 1000), self._fade_out)

    def _set_window_position(self):
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()

        pos = self.config['position']
        margin_x = self.config['margin_x']
        margin_y = self.config['margin_y']
        x, y = 0, 0

        if isinstance(pos, tuple) and len(pos) == 2:
            x, y = pos
        else:
            if 'right' in pos: x = screen_width - window_width - margin_x
            elif 'left' in pos: x = margin_x
            else: x = (screen_width // 2) - (window_width // 2)
            
            if 'bottom' in pos: y = screen_height - window_height - margin_y
            elif 'top' in pos: y = margin_y
            else: y = (screen_height // 2) - (window_height // 2)

        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _fade_in(self):
        self._is_fading = True
        try:
            alpha = self.root.attributes("-alpha")
            if alpha < self.config['alpha']:
                self.root.attributes("-alpha", alpha + self.config['fade_speed'])
                self.root.after(10, self._fade_in)
            else:
                self._is_fading = False
        except tk.TclError:
            self._is_fading = False

    def _fade_out(self):
        if self._is_fading: return
        self._is_fading = True
        try:
            alpha = self.root.attributes("-alpha")
            if alpha > 0:
                self.root.attributes("-alpha", alpha - self.config['fade_speed'])
                self.root.after(10, self._fade_out)
            else:
                self.root.withdraw()
                self._is_fading = False
        except tk.TclError:
            self._is_fading = False

    def _fade_out_and_destroy(self):
        self._fade_out()
        self.root.after(500, self.root.destroy)

    def update_status(self, text, style='info', duration=None):
        if duration is None:
            duration = self.config.get('default_duration', 5)
        
        task_data = {'text': text, 'style': style, 'duration': duration}
        self.queue.put({'command': 'UPDATE', 'data': task_data})

    def stop(self):
        self.queue.put({'command': 'STOP'})
