"""热键管理模块"""

import threading
import time
import keyboard
from load_utils import clear_cache
from config import CONFIGS


class HotkeyManager:
    """热键管理器"""

    def __init__(self, gui):
        self.gui = gui
        self.core = gui.core
        
        self.hotkey_thread = None
        self._thread_lock = threading.Lock()  # 线程锁，防止重复创建线程

        self._hotkey_was_trigger = False
        self.hotkey_listener_active = True

    def setup_hotkeys(self):
        """设置热键监听（仅在初始化时调用）"""
        with self._thread_lock:
            if self.hotkey_thread and self.hotkey_thread.is_alive():
                return  # 如果线程已经在运行，则不重复启动
            
            self.hotkey_listener_active = True
            self.hotkey_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
            self.hotkey_thread.start()
            print("热键监听线程已启动")

    def hotkey_listener(self):
        """热键监听线程"""
        try:
            while True:
                time.sleep(0.1)

                # 重新加载设置以获取最新配置
                try:
                    hotkeys = CONFIGS.keymap
                    quick_chars = CONFIGS.gui_settings.get("quick_characters", {})
                except Exception as e:
                    print(f"加载热键设置失败: {e}")
                    time.sleep(1)
                    continue
                
                # 获取当前按下的热键组合
                current_hotkey = keyboard.get_hotkey_name()
                if current_hotkey not in hotkeys.values():
                    self._hotkey_was_trigger = False
                    continue
                elif self._hotkey_was_trigger:
                    # 等待按键释放
                    continue

                # 检查切换监听热键（始终监听）
                if current_hotkey == hotkeys.get("toggle_listener", "alt+ctrl+p"):
                    self.gui.root.after(0, self.toggle_hotkey_listener)
                    self._hotkey_was_trigger = True
                
                # 如果监听未激活，则等待
                if not self.hotkey_listener_active:
                    continue
                
                # 遍历所有热键（排除切换监听热键）
                for action, hotkey in hotkeys.items():
                    if action == "toggle_listener":
                        continue
                        
                    # 只监听GUI相关的热键
                    if action in [
                        "start_generate",
                        "next_character",
                        "prev_character",
                        "next_background",
                        "prev_background",
                        "next_emotion",
                        "prev_emotion",
                    ] or action.startswith("character_"):
                        if current_hotkey == hotkey:
                            self._hotkey_was_trigger = True
                            if action.startswith("character_"):
                                char_id = quick_chars.get(action, "")
                                self.gui.root.after(0,lambda a=action, c=char_id: self.handle_hotkey_action(a, c),)
                            else:
                                self.gui.root.after(0, lambda a=action: self.handle_hotkey_action(a))
                            break  # 找到匹配的热键就退出循环
        except Exception as e:
            print(f"热键监听错误: {e}")

    def toggle_hotkey_listener(self):
        """切换热键监听状态"""
        self.hotkey_listener_active = not self.hotkey_listener_active
        status = "启用" if self.hotkey_listener_active else "禁用"
        self.gui.update_status(f"热键监听已{status}")
        print(f"热键监听状态已切换为: {status}")

    def handle_hotkey_action(self, action, char_id=None):
        """处理热键动作"""
        try:
            if action == "start_generate":
                self.gui.generate_image()  # 生成图片
            elif action == "next_character":
                self.switch_character(1)  # 向后切换
            elif action == "prev_character":
                self.switch_character(-1)  # 向前切换
            elif action == "next_emotion":
                self.switch_emotion(1)
            elif action == "prev_emotion":
                self.switch_emotion(-1)
            elif action == "next_background":
                self.switch_background(1)  # 向后切换背景
            elif action == "prev_background":
                self.switch_background(-1)  # 向前切换背景
            elif action.startswith("character_") and char_id:
                self.switch_to_character_by_id(char_id)

        except Exception as e:
            print(f"处理热键动作失败: {e}")

    def switch_character(self, direction):
        """切换角色"""
        current_index = CONFIGS.current_character_index
        total_chars = len(CONFIGS.character_list)
    
        new_index = current_index + direction
        if new_index > total_chars:
            new_index = 1
        elif new_index < 1:
            new_index = total_chars
    
        if self.core.switch_character(new_index):
            self._handle_character_switch_success()
    
    def switch_to_character_by_id(self, char_id):
        """通过角色ID切换到指定角色"""
        if char_id and char_id in CONFIGS.character_list:
            if char_id == CONFIGS.character_list[CONFIGS.current_character_index - 1]:
                return
            char_index = CONFIGS.character_list.index(char_id) + 1
            if self.core.switch_character(char_index):
                self._handle_character_switch_success()
    
    def switch_emotion(self, direction):
        """切换表情"""
        # 取消情感匹配勾选
        self._cancel_sentiment_matching()
        
        if self.gui.emotion_random_var.get():
            # 如果当前是随机模式，切换到指定模式
            self.gui.emotion_random_var.set(False)
            self.gui.on_emotion_random_changed()
    
        emotion_count = CONFIGS.current_character["emotion_count"]
        current_emotion = CONFIGS.selected_emotion or 1
    
        new_emotion = current_emotion + direction
        if new_emotion > emotion_count:
            new_emotion = 1
        elif new_emotion < 1:
            new_emotion = emotion_count
    
        CONFIGS.selected_emotion = new_emotion
        self.gui.emotion_combo.set(f"表情 {new_emotion}")
        self.gui.update_preview()
        self.gui.update_status(f"已切换到表情: {new_emotion}")

    def _handle_character_switch_success(self):
        """处理角色切换成功后的通用操作"""
        # 切换角色后清理缓存
        clear_cache("character")
        # 更新GUI显示
        self.gui.character_var.set(
            f"{CONFIGS.get_character(full_name=True)} ({CONFIGS.get_character()})"
        )
        self.gui.update_emotion_options()
        
        # 重置表情索引为1，与手动切换保持一致
        self.gui.emotion_combo.set("表情 1")
        if self.gui.emotion_random_var.get():
            CONFIGS.selected_emotion = None
        else:
            CONFIGS.selected_emotion = 1
        
        self.gui.update_preview()
        self.gui.update_status(
            f"已切换到角色: {CONFIGS.get_character(full_name=True)}"
        )
    
    def _cancel_sentiment_matching(self):
        """取消情感匹配并更新状态"""
        if self.gui.sentiment_matching_var.get():
            self.gui.sentiment_matching_var.set(False)
            self.gui.on_sentiment_matching_changed()
            self.gui.update_status("已取消情感匹配（手动切换表情）")

    def switch_background(self, direction):
        """切换背景"""
        if self.gui.background_random_var.get():
            # 如果当前是随机模式，切换到指定模式
            self.gui.background_random_var.set(False)
            self.gui.on_background_random_changed()

        current_bg = CONFIGS.selected_background or 1
        total_bgs = CONFIGS.background_count

        new_bg = current_bg + direction
        if new_bg > total_bgs:
            new_bg = 1
        elif new_bg < 1:
            new_bg = total_bgs

        CONFIGS.selected_background = new_bg
        self.gui.background_combo.set(f"背景 {new_bg}")
        self.gui.update_preview()
        self.gui.update_status(f"已切换到背景: {new_bg}")