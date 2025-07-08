# functions/ui_notifier.py
# --- VERSION 12.0 (Action Buttons)
# This version adds the highly requested action buttons feature.
# 1. New `buttons` parameter in `update_status` to define action buttons.
# 2. Each button has a text label and a callback command.
# 3. Clicking a button executes the command and then dismisses the notification.
# 4. UI is restructured to accommodate a dedicated button area.

import tkinter as tk
from tkinter import font
import queue
import threading
import time
import logging

# ======================================================================
#                           DEFAULT CONFIGURATION
# ======================================================================
DEFAULT_NOTIFIER_CONFIG = {
    # General
    'alpha': 0.95,
    'position': 'bottom_right',
    'margin_x': 20,
    'margin_y': 20,
    
    # Sizing
    'width': 'auto',
    'height': 'auto',
    'min_width': 300,
    'max_width': 450,
    'min_height': 70,
    
    # Font & Text
    'font_family': 'Segoe UI',
    'font_size': 10,
    'font_style': 'normal',
    'font_color': 'auto', # 'auto' uses style color, or specify a hex code
    
    # Layout & Icons
    'padding_x': 20,
    'padding_y': 15,
    'icon_text_spacing': 10,
    'show_icons': True,
    
    # Border configuration
    'border_thickness': 1,
    'border_color': '#FFFFFF',
    
    # Behavior
    'default_duration': 5,
    'default_style': 'info',
    
    # Animation
    'animation': 'slide-up',
    'animation_speed': 10,
    
    # Style Definitions
    'styles': {
        'plain':   {'icon': '',     'fg': '#FFFFFF', 'bg': '#34495E'},
        'info':    {'icon': 'ℹ️', 'fg': '#E1F5FE', 'bg': '#0288D1'},
        'success': {'icon': '✅', 'fg': '#FFFFFF', 'bg': '#27AE60'},
        'warning': {'icon': '⚠️', 'fg': '#000000', 'bg': '#F39C12'},
        'error':   {'icon': '❌', 'fg': '#FFFFFF', 'bg': '#C0392B'},
        'process': {'icon': '⚙️', 'fg': '#FFFFFF', 'bg': '#7F8C8D'},
        'question':{'icon': '❓', 'fg': '#FFFFFF', 'bg': '#8E44AD'},
        'debug':   {'icon': '🐞', 'fg': '#AAB7B8', 'bg': '#17202A'},
        'download':{'icon': '📥', 'fg': '#FFFFFF', 'bg': '#16A085'},
        'upload':  {'icon': '📤', 'fg': '#FFFFFF', 'bg': '#16A085'},
        'auth':    {'icon': '🔑', 'fg': '#FFFFFF', 'bg': '#D35400'},
    },
}

class StatusNotifier:
    """
    Manages a feature-rich, non-blocking notification window with a modern UI.
    Now with Action Buttons.
    """
    def __init__(self, config=None):
        self.queue = queue.Queue()
        self.config = self._deep_merge_configs(DEFAULT_NOTIFIER_CONFIG, config or {})
        
        self.root = None
        self._hide_job = None
        self._animation_job = None
        
        self._is_paused = False
        self._start_time = 0
        self._current_duration = 0
        
        # NEW: To store button widgets
        self._buttons = []

        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()

    def _deep_merge_configs(self, default, user):
        # This method remains the same
        merged = default.copy()
        for key, value in user.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = self._deep_merge_configs(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _run_gui(self):
        try:
            self.root = tk.Tk()
            self.root.overrideredirect(True)
            self.root.wm_attributes("-topmost", True)
            self.root.withdraw()
            
            font_style_str = self.config['font_style'].lower()
            weight = 'bold' if 'bold' in font_style_str else 'normal'
            slant = 'italic' if 'italic' in font_style_str else 'roman'

            self.icon_font = font.Font(family=self.config['font_family'], size=self.config['font_size'] + 4, weight='bold')
            self.text_font = font.Font(family=self.config['font_family'], size=self.config['font_size'], weight=weight, slant=slant)
            self.button_font = font.Font(family=self.config['font_family'], size=self.config['font_size'] -1, weight='bold')

            border_thickness = self.config['border_thickness']
            self.border_frame = tk.Frame(self.root, bg=self.config['border_color'], bd=0)
            self.border_frame.pack(expand=True, fill='both')

            self.main_frame = tk.Frame(self.border_frame, bd=0)
            self.main_frame.pack(expand=True, fill='both', padx=border_thickness, pady=border_thickness)

            # NEW: Restructured UI with a content frame and a button frame
            self.content_frame = tk.Frame(self.main_frame)
            self.content_frame.pack(side='top', fill='x', expand=True)
            
            self.buttons_frame = tk.Frame(self.main_frame)
            self.buttons_frame.pack(side='bottom', fill='x', pady=(5,0))

            self.icon_label = tk.Label(self.content_frame, font=self.icon_font, justify='center')
            self.text_label = tk.Label(self.content_frame, font=self.text_font, justify='left')
            
            widgets_to_bind = [self.border_frame, self.main_frame, self.content_frame, self.icon_label, self.text_label]
            for widget in widgets_to_bind:
                widget.bind("<Button-1>", self._dismiss)
                widget.bind("<Enter>", self._on_mouse_enter)
                widget.bind("<Leave>", self._on_mouse_leave)

            self._check_queue()
            self.root.mainloop()
        except Exception as e:
            logging.error(f"Error in Tkinter thread: {e}", exc_info=True)
            
    def _check_queue(self):
        # This method remains the same
        try:
            task = self.queue.get_nowait()
            if self._hide_job: self.root.after_cancel(self._hide_job); self._hide_job = None
            if self._animation_job: self.root.after_cancel(self._animation_job); self._animation_job = None
            if task['command'] == "STOP": self._animate_out(self.config['animation'], destroy_after=True); return
            elif task['command'] == "UPDATE": self._process_update(task['data'])
        except queue.Empty:
            pass
        if self.root and self.root.winfo_exists(): self.root.after(50, self._check_queue)

    def _process_update(self, data):
        style_config = self.config['styles'].get(data['style'], self.config['styles']['info'])
        bg_color = style_config['bg']
        fg_color = self.config['font_color'] if self.config['font_color'] != 'auto' else style_config['fg']
        
        # Configure frames
        self.border_frame.config(bg=self.config['border_color'])
        self.main_frame.config(bg=bg_color)
        self.content_frame.config(bg=bg_color)
        self.buttons_frame.config(bg=bg_color)

        # Configure content
        self.text_label.config(text=data['text'], bg=bg_color, fg=fg_color)
        self.icon_label.pack_forget()
        self.text_label.pack_forget()

        icon_text = style_config.get('icon', '') if self.config.get('show_icons', True) else ''
        if icon_text:
            self.icon_label.config(text=icon_text, bg=bg_color, fg=fg_color)
            self.icon_label.pack(side='left', fill='y', padx=(self.config['padding_x'], self.config['icon_text_spacing']), pady=self.config['padding_y'])
        
        self.text_label.pack(side='left', fill='both', expand=True, padx=(0 if icon_text else self.config['padding_x'], self.config['padding_x']), pady=self.config['padding_y'])

        # NEW: Process and create buttons
        for button in self._buttons: button.destroy()
        self._buttons.clear()

        buttons_data = data.get('buttons')
        if buttons_data:
            self.buttons_frame.pack(side='bottom', fill='x', padx=self.config['padding_x'], pady=(0, self.config['padding_y']))
            for button_info in buttons_data:
                btn = tk.Button(
                    self.buttons_frame,
                    text=button_info['text'],
                    font=self.button_font,
                    bg=fg_color, # Swapped for contrast
                    fg=bg_color,
                    relief='flat',
                    overrelief='raised',
                    borderwidth=1,
                    command=lambda cmd=button_info['command']: self._on_button_click(cmd)
                )
                btn.pack(side='right', padx=(5, 0))
                self._buttons.append(btn)
        else:
            self.buttons_frame.pack_forget()

        self.root.update_idletasks()
        
        icon_width = self.icon_label.winfo_reqwidth() if icon_text else 0
        wraplength = self.config['max_width'] - (self.config['padding_x'] * 2) - self.config['icon_text_spacing'] - icon_width - (self.config['border_thickness'] * 2)
        self.text_label.config(wraplength=wraplength)
        self.root.update_idletasks()
        
        req_width = self.main_frame.winfo_reqwidth()
        req_height = self.main_frame.winfo_reqheight()

        final_width = int(max(self.config['min_width'], min(req_width, self.config['max_width'])))
        final_height = int(max(self.config['min_height'], min(req_height, self.root.winfo_screenheight())))
        
        animation = data.get('animation') or self.config['animation']
        self._animate_in(final_width, final_height, animation)

        duration = data['duration']
        if duration > 0:
            self._is_paused = False
            self._current_duration = duration
            self._start_time = time.time()
            self._hide_job = self.root.after(int(duration * 1000), lambda: self._animate_out(animation))

    # --- Event Handlers ---

    def _on_mouse_enter(self, event=None):
        if self._hide_job:
            self._is_paused = True
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
            elapsed_time = time.time() - self._start_time
            self._current_duration -= elapsed_time

    def _on_mouse_leave(self, event=None):
        if self._is_paused:
            self._is_paused = False
            if self._current_duration > 0:
                self._start_time = time.time()
                animation = self.config['animation']
                self._hide_job = self.root.after(int(self._current_duration * 1000), lambda: self._animate_out(animation))
    
    def _on_button_click(self, command):
        if command:
            try:
                command()
            except Exception as e:
                logging.error(f"Error executing button command: {e}", exc_info=True)
        self._dismiss()

    def _dismiss(self, event=None):
        # This method is now also called by button clicks
        if self._hide_job: self.root.after_cancel(self._hide_job); self._hide_job = None
        if self._animation_job: self.root.after_cancel(self._animation_job); self._animation_job = None
        self._animate_out(self.config['animation'])

    # --- Animation and position methods (unchanged) ---
    def _get_positions(self, width, height, animation_style):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        margin_x = self.config['margin_x']
        margin_y = self.config['margin_y']
        pos_map = {
            'top_right': (screen_width - width - margin_x, margin_y),
            'top_left': (margin_x, margin_y),
            'bottom_right': (screen_width - width - margin_x, screen_height - height - margin_y),
            'bottom_left': (margin_x, screen_height - height - margin_y),
            'center': ((screen_width // 2) - (width // 2), (screen_height // 2) - (height // 2))
        }
        end_x, end_y = pos_map.get(self.config['position'], pos_map['bottom_right'])
        start_x, start_y = end_x, end_y
        if 'slide' in animation_style:
            if 'up' in animation_style: start_y = screen_height
            elif 'down' in animation_style: start_y = -height
            elif 'left' in animation_style: start_x = screen_width
            elif 'right' in animation_style: start_x = -width
        return start_x, start_y, end_x, end_y

    def _animate_in(self, width, height, animation):
        start_x, start_y, end_x, end_y = self._get_positions(width, height, animation)
        self.root.geometry(f'{width}x{height}+{start_x}+{start_y}')
        if not self.root.winfo_viewable(): self.root.deiconify()
        if animation == 'none':
            self.root.attributes("-alpha", self.config['alpha'])
            self.root.geometry(f'{width}x{height}+{end_x}+{end_y}')
            return
        total_steps = 20
        def step(i):
            progress = i / total_steps
            new_x = int(start_x + (end_x - start_x) * progress)
            new_y = int(start_y + (end_y - start_y) * progress)
            if 'fade' in animation:
                self.root.attributes("-alpha", self.config['alpha'] * progress)
                self.root.geometry(f'+{new_x}+{new_y}')
            elif 'grow' in animation:
                scale = progress
                current_w, current_h = int(width * scale), int(height * scale)
                pos_x, pos_y = end_x + (width - current_w) // 2, end_y + (height - current_h) // 2
                self.root.geometry(f'{current_w}x{current_h}+{pos_x}+{pos_y}')
                self.root.attributes("-alpha", self.config['alpha'] * progress)
            else:
                self.root.geometry(f'+{new_x}+{new_y}')
                self.root.attributes("-alpha", self.config['alpha'])
            if i >= total_steps:
                self.root.geometry(f'{width}x{height}+{end_x}+{end_y}')
                self._animation_job = None
            else:
                self._animation_job = self.root.after(self.config['animation_speed'], lambda: step(i + 1))
        step(1)

    def _animate_out(self, animation, destroy_after=False):
        width, height = self.root.winfo_width(), self.root.winfo_height()
        target_x, target_y, current_x, current_y = self._get_positions(width, height, animation)
        if animation == 'none':
            self.root.withdraw()
            if destroy_after: self.root.destroy()
            return
        total_steps = 20
        def step(i):
            progress = i / total_steps
            new_x = int(current_x + (target_x - current_x) * progress)
            new_y = int(current_y + (target_y - current_y) * progress)
            if 'fade' in animation or 'grow' in animation:
                self.root.attributes("-alpha", self.config['alpha'] * (1 - progress))
            if 'grow' in animation:
                scale = 1 - progress
                current_w, current_h = int(width * scale), int(height * scale)
                pos_x, pos_y = current_x + (width - current_w) // 2, current_y + (height - current_h) // 2
                self.root.geometry(f'{current_w}x{current_h}+{pos_x}+{pos_y}')
            else:
                 self.root.geometry(f'+{new_x}+{new_y}')
            if i >= total_steps:
                self.root.withdraw()
                self._animation_job = None
                if destroy_after: self.root.destroy()
            else:
                self._animation_job = self.root.after(self.config['animation_speed'], lambda: step(i + 1))
        step(1)

    def update_status(self, text, style=None, duration=None, animation=None, buttons=None):
        if duration is None: duration = self.config.get('default_duration', 5)
        if style is None: style = self.config.get('default_style', 'info')
        task_data = {'text': text, 'style': style, 'duration': duration, 'animation': animation, 'buttons': buttons}
        self.queue.put({'command': 'UPDATE', 'data': task_data})

    def stop(self):
        self.queue.put({'command': 'STOP'})


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("--- Running Notifier Demonstration (v12) ---")

    # --- NEW: Demo function for button callback ---
    def retry_operation():
        print(">>> ACTION: 'Thử lại' button was clicked. Running retry logic...")
        # In a real app, you would put your retry code here.
        # For the demo, we'll just show another notification.
        notifier.update_status("Đang thử lại kết nối...", style='process', duration=3)

    def run_demo():
        # --- Demo 1: Interactive Features (Same as before) ---
        print("\n1. Testing Pause on Hover and Click to Dismiss...")
        interactive_notifier = StatusNotifier({'animation': 'fade'})
        interactive_notifier.update_status("Di chuột vào để tạm dừng. Nhấp chuột để đóng.", style='question', duration=8)
        time.sleep(9) 
        interactive_notifier.stop()

        # --- NEW Demo 2: Testing Action Buttons ---
        print("\n2. Testing Action Buttons...")
        print("   - Một thông báo lỗi với các nút hành động sẽ xuất hiện.")
        print("   - Hãy thử nhấn nút 'Thử lại' hoặc 'Hủy'.")
        
        # We need a global or nonlocal notifier instance for the callback to access
        global notifier
        notifier = StatusNotifier({'position': 'center', 'animation': 'grow'})
        
        action_buttons = [
            {'text': 'Thử lại', 'command': retry_operation},
            {'text': 'Hủy', 'command': None} # No command needed, it will just dismiss
        ]
        
        notifier.update_status(
            text="Không thể lưu tệp. Vui lòng kiểm tra lại quyền truy cập.",
            style='error',
            duration=0, # Keep it open until user interacts
            buttons=action_buttons
        )
        
        # Keep the script alive to test the buttons
        time.sleep(10)
        notifier.stop()


    run_demo()
    print("\n--- Demonstration Finished ---")
