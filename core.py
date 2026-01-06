"""魔裁文本框核心逻辑"""
from config import CONFIGS
from clipboard_utils import ClipboardManager
from sentiment_analyzer import SentimentAnalyzer
from image_processor import get_enhanced_loader, generate_image_with_dll, set_dll_global_config, clear_cache, update_dll_gui_settings, draw_content_auto

import time
import random
import psutil
import threading
from pynput.keyboard import Key, Controller
from sys import platform
from PIL import Image
from typing import Dict, Any

if platform.startswith("win"):
    try:
        import win32gui
        import win32process
    except ImportError:
        print("[red]请先安装 Windows 运行库: pip install pywin32[/red]")
        raise

def _calculate_canvas_size():
    """根据样式配置计算画布大小"""
    ratio = CONFIGS.style.aspect_ratio

    # 固定宽度为2560，根据比例计算高度
    if ratio == "5:4":
        height = 2048
    elif ratio == "16:9":
        height = 1440
    else:  # "3:1" 或默认
        height = 854
    
    return (2560, height)

class ManosabaCore:
    """魔裁文本框核心类"""

    def __init__(self):
        # 初始化配置
        self.kbd_controller = Controller()
        self.clipboard_manager = ClipboardManager()
        
        # 状态更新回调
        self.status_callback = None
        self.gui_callback = None

        # 初始化情感分析器 - 不在这里初始化，等待特定时机
        self.sentiment_analyzer = SentimentAnalyzer()
        self.sentiment_analyzer_status = {
            'initialized': False,
            'initializing': False,
            'current_config': {}
        }
        
        # 初始化DLL加载器
        self._assets_path = CONFIGS.config.ASSETS_PATH
        set_dll_global_config(self._assets_path, min_image_ratio=0.2)
        update_dll_gui_settings(CONFIGS.gui_settings)
    
    def set_gui_callback(self, callback):
        """设置GUI回调函数，用于通知状态变化"""
        self.gui_callback = callback

    def _notify_gui_status_change(self, initialized: bool, enabled: bool = None, initializing: bool = False):
        """通知GUI状态变化"""
        if self.gui_callback:
            if enabled is None:
                # 如果没有指定enabled，则使用当前设置
                sentiment_settings = CONFIGS.gui_settings.get("sentiment_matching", {})
                enabled = sentiment_settings.get("enabled", False) and initialized
            self.gui_callback(initialized, enabled, initializing)

    def _initialize_sentiment_analyzer_async(self):
        """异步初始化情感分析器"""
        def init_task():
            try:
                self.sentiment_analyzer_status['initializing'] = True
                self._notify_gui_status_change(False, False, True)
                
                sentiment_settings = CONFIGS.gui_settings.get("sentiment_matching", {})
                if sentiment_settings.get("enabled", False):
                    client_type = sentiment_settings.get("ai_model", "ollama")
                    model_configs = sentiment_settings.get("model_configs", {})
                    config = model_configs.get(client_type, {})
                    
                    # 记录当前配置
                    self.sentiment_analyzer_status['current_config'] = {
                        'client_type': client_type,
                        'config': config.copy()
                    }
                    
                    success = self.sentiment_analyzer.initialize(client_type, config)
                    
                    if success:
                        self.update_status("情感分析器初始化完成，功能已启用")
                        self.sentiment_analyzer_status['initialized'] = True
                        # 通知GUI初始化成功
                        self._notify_gui_status_change(True, True, False)
                    else:
                        self.update_status("情感分析器初始化失败，功能已禁用")
                        self.sentiment_analyzer_status['initialized'] = False
                        # 通知GUI初始化失败，需要禁用情感匹配
                        self._notify_gui_status_change(False, False, False)
                        # 更新设置，禁用情感匹配
                        self._disable_sentiment_matching()
                else:
                    self.update_status("情感匹配功能未启用，跳过初始化")
                    self.sentiment_analyzer_status['initialized'] = False
                    self._notify_gui_status_change(False, False, False)
                    
            except Exception as e:
                self.update_status(f"情感分析器初始化失败: {e}，功能已禁用")
                self.sentiment_analyzer_status['initialized'] = False
                # 通知GUI初始化失败，需要禁用情感匹配
                self._notify_gui_status_change(False, False, False)
                # 更新设置，禁用情感匹配
                self._disable_sentiment_matching()
            finally:
                self.sentiment_analyzer_status['initializing'] = False
        
        # 在后台线程中初始化
        init_thread = threading.Thread(target=init_task, daemon=True)
        init_thread.start()    
    
    def toggle_sentiment_matching(self):
        """切换情感匹配状态"""
        # 如果正在初始化，不处理点击
        if self.sentiment_analyzer_status['initializing']:
            return
            
        sentiment_settings = CONFIGS.gui_settings.get("sentiment_matching", {})
        current_enabled = sentiment_settings.get("enabled", False)
        
        if not current_enabled:
            # 如果当前未启用，则启用并初始化
            CONFIGS.gui_settings["sentiment_matching"]["enabled"] = True
            CONFIGS.save_gui_settings()
            if not self.sentiment_analyzer_status['initialized']:
                # 如果未初始化，则开始初始化
                self.update_status("正在初始化情感分析器...")
                self._initialize_sentiment_analyzer_async()
            else:
                # 如果已初始化，直接启用
                self.update_status("已启用情感匹配功能")
                self._notify_gui_status_change(True, True, False)
        else:
            # 如果当前已启用，则禁用
            self.update_status("已禁用情感匹配功能")
            CONFIGS.gui_settings["sentiment_matching"]["enabled"] = False
            CONFIGS.save_gui_settings()
            self._notify_gui_status_change(self.sentiment_analyzer_status['initialized'], False, False)

    def _disable_sentiment_matching(self):
        """禁用情感匹配设置"""
        if "sentiment_matching" in CONFIGS.gui_settings:
            CONFIGS.gui_settings["sentiment_matching"]["enabled"] = False
        # 保存设置
        CONFIGS.save_gui_settings()
        self.update_status("情感匹配功能已禁用")

    def _reinitialize_sentiment_analyzer_if_needed(self):
        """检查配置是否有变化，如果有变化则重新初始化"""
        sentiment_settings = CONFIGS.gui_settings.get("sentiment_matching", {})
        if not sentiment_settings.get("enabled", False):
            # 如果功能被禁用，重置状态
            if self.sentiment_analyzer_status['initialized']:
                self.sentiment_analyzer_status['initialized'] = False
                self.update_status("情感匹配已禁用，重置分析器状态")
                self._notify_gui_status_change(False, False, False)
            return
        
        client_type = sentiment_settings.get("ai_model", "ollama")
        model_configs = sentiment_settings.get("model_configs", {})
        config = model_configs.get(client_type, {})
        
        new_config = {
            'client_type': client_type,
            'config': config.copy()
        }
        
        # 检查配置是否有变化
        if new_config != self.sentiment_analyzer_status['current_config']:
            self.update_status("AI配置已更改，重新初始化情感分析器")
            self.sentiment_analyzer_status['initialized'] = False
            self.sentiment_analyzer_status['current_config'] = new_config
            # 通知GUI开始重新初始化
            self._notify_gui_status_change(False, False, False)
            self._initialize_sentiment_analyzer_async()

    def test_ai_connection(self, client_type: str, config: Dict[str, Any]) -> bool:
        """测试AI连接 - 这会进行模型初始化"""
        try:
            # 使用临时分析器进行测试，不影响主分析器状态
            temp_analyzer = SentimentAnalyzer()
            success = temp_analyzer.initialize(client_type, config)
            if success:
                self.update_status(f"AI连接测试成功: {client_type}")
                # 如果测试成功，可以更新主分析器
                self.sentiment_analyzer.initialize(client_type, config)
                self.sentiment_analyzer_status['initialized'] = True
                # 通知GUI测试成功
                self._notify_gui_status_change(True, True)
            else:
                self.update_status(f"AI连接测试失败: {client_type}")
                self.sentiment_analyzer_status['initialized'] = False
                # 通知GUI测试失败
                self._notify_gui_status_change(False, False)
            return success
        except Exception as e:
            self.update_status(f"连接测试失败: {e}")
            self.sentiment_analyzer_status['initialized'] = False
            # 通知GUI测试失败
            self._notify_gui_status_change(False, False)
            return False

    def _update_emotion_by_sentiment(self, text: str) -> bool:
        """根据文本情感更新表情，返回是否成功更新了至少一个角色图层"""
        if not self.sentiment_analyzer_status['initialized']:
            self.update_status("情感分析器未初始化，跳过情感分析")
            return False
        
        # 分析情感（只分析一次）
        sentiment = self.sentiment_analyzer.analyze_sentiment(text)
        if not sentiment:
            return False
        
        updated = False
        current_character = CONFIGS.get_character()
        
        # 获取所有角色图层
        preview_components = CONFIGS.get_sorted_preview_components()
        
        for component in preview_components:
            if not component.get("enabled", True):
                continue
            
            if component.get("type") == "character":
                character_name = component.get("character_name", current_character)
                
                # 获取当前角色的表情筛选设置
                filter_name = component.get("emotion_filter", "全部")
                
                # 获取筛选后的表情列表
                filtered_emotions = CONFIGS.get_filtered_emotions(character_name, filter_name)
                
                if not filtered_emotions:
                    return False
                
                # 从角色配置中获取该情感对应的表情索引
                emotion_indices = CONFIGS.mahoshojo.get(character_name, {}).get(sentiment, [])
                
                # 筛选出在过滤范围内的情感表情
                available_emotions = [idx for idx in emotion_indices if idx in filtered_emotions]
                
                if available_emotions:
                    # 随机选择一个在筛选范围内的表情
                    emotion_index = random.choice(available_emotions)
                    
                    # 更新组件的表情索引
                    component["emotion_index"] = emotion_index
                    component["force_use"] = True
                    updated = True
                    
                    # 获取角色全名用于显示
                    char_full_name = CONFIGS.mahoshojo.get(character_name, {}).get("full_name", character_name)
                    info = f"角色 {char_full_name} 表情({sentiment}): {emotion_index} |"
                    self.base_msg += info
                    print(info)
        if updated:
            clear_cache()
        return updated

    def _active_process_allowed(self) -> bool:
        """校验当前前台进程是否在白名单"""
        if not CONFIGS.process_whitelist:
            return True
        
        wl = {name.lower() for name in CONFIGS.process_whitelist}

        if platform.startswith("win"):
            try:
                hwnd = win32gui.GetForegroundWindow()
                if not hwnd:
                    return False
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                name = psutil.Process(pid).name().lower()
                return name in wl
            except (psutil.Error, OSError):
                return False

        elif platform == "darwin":
            try:
                import subprocess

                result = subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to get name of first process whose frontmost is true',
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                name = result.stdout.strip().lower()
                return name in wl
            except subprocess.SubprocessError:
                return False

        else:
            # Linux 支持
            return True
    
    def set_status_callback(self, callback):
        """设置状态更新回调函数"""
        self.status_callback = callback

    def update_status(self, message: str):
        """更新状态（供外部调用）"""
        if self.status_callback:
            self.status_callback(message)

    def generate_preview(self) -> tuple:
        """生成预览图片和相关信息"""
        st = time.time()
        use_cache = get_enhanced_loader().layer_cache
        try:
            compress_layer = False

            # 使用预览样式的组件数据
            components = CONFIGS.get_sorted_preview_components()
            
            if not components:
                print("警告：没有找到预览组件")
                return self._create_empty_preview()
            
            cp_components = []
            
            # 从图层获取当前角色（用于namebox）
            current_character_name = CONFIGS._get_current_character_from_layers()
            
            # 用于收集信息的变量
            character_info = ""
            background_info = ""

            # 确定每个组件的具体参数
            for component in components:
                if not component.get("enabled", True):
                    continue
                
                ufc = component.get("use_fixed_character", False)
                ufb = component.get("use_fixed_background", False)
                comp_type = component.get("type")
                if use_cache and ((comp_type in ["background", "character"] and (ufc or ufb)) or comp_type not in ["background", "character"]):
                    if not compress_layer:
                        cp_components.append({"use_cache": True})
                        compress_layer = True
                    continue

                if comp_type == "namebox":
                    # 添加角色文本配置
                    if current_character_name in CONFIGS.mahoshojo:
                        component["textcfg"] = CONFIGS.mahoshojo[current_character_name]["text"]
                        component["font_name"] = "font3"  # 使用默认字体
                elif comp_type == "character":
                    character_name = component.get("character_name", current_character_name)
                    emotion_index = component.get("emotion_index")
                    
                    # 检查是否有强制使用标记
                    force_use = component.get("force_use", False)
                    if force_use and emotion_index is not None:
                        emotion_index = int(emotion_index)
                        component.pop("force_use", None)
                        
                        # 收集角色信息
                        char_full_name = CONFIGS.mahoshojo.get(character_name, {}).get("full_name", character_name)
                        character_info = f"角色: {char_full_name}, 表情: {emotion_index}(强制)"
                        
                        # 更新组件的emotion_index
                        component["emotion_index"] = emotion_index
                    elif component.get("use_fixed_character", False):
                        # 使用固定表情
                        
                        if emotion_index is None:
                            # 在过滤范围内随机选择表情
                            filter_name = component.get("emotion_filter", "全部")
                            filtered_emotions = CONFIGS.get_filtered_emotions(character_name, filter_name)
                            if filtered_emotions:
                                emotion_index = random.choice(filtered_emotions)
                            else:
                                # 如果没有过滤表情，使用所有表情
                                emotion_count = CONFIGS.mahoshojo.get(character_name, {}).get("emotion_count", 1)
                                emotion_index = random.randint(1, emotion_count)
                        else:
                            # 确保表情索引是整数
                            emotion_index = int(emotion_index)
                        
                        # 收集角色信息
                        char_full_name = CONFIGS.mahoshojo.get(character_name, {}).get("full_name", character_name)
                        character_info = f"角色: {char_full_name}, 表情: {emotion_index}"
                        
                        # 更新组件的emotion_index
                        component["emotion_index"] = emotion_index
                    else:
                        
                        # 在过滤范围内随机选择表情
                        filter_name = component.get("emotion_filter", "全部")
                        filtered_emotions = CONFIGS.get_filtered_emotions(character_name, filter_name)
                        if filtered_emotions:
                            emotion_index = random.choice(filtered_emotions)
                        else:
                            # 如果没有过滤表情，使用所有表情
                            emotion_count = CONFIGS.mahoshojo.get(character_name, {}).get("emotion_count", 1)
                            emotion_index = random.randint(1, emotion_count)
                        
                        component["character_name"] = character_name
                        component["emotion_index"] = emotion_index
                        
                        # 收集角色信息
                        char_full_name = CONFIGS.mahoshojo.get(character_name, {}).get("full_name", character_name)
                        compress_layer = False
                        character_info = f"角色: {char_full_name}, 表情: 随机({emotion_index})"
                    
                    # 获取角色配置
                    character_config = CONFIGS.mahoshojo.get(character_name, {})
                    
                    # 设置缩放
                    component["scale1"] = float(character_config.get("scale", 1.0))
                    
                    # 设置偏移
                    offset = character_config.get("offset", (0, 0))
                    offset_x = 0
                    offset_y = 0
                    
                    # 获取表情偏移
                    emotion_offsets_X = character_config.get("offsetX", {})
                    emotion_offsets_Y = character_config.get("offsetY", {})
                    
                    if emotion_offsets_X and str(emotion_index) in emotion_offsets_X:
                        offset_x = float(emotion_offsets_X[str(emotion_index)])
                    if emotion_offsets_Y and str(emotion_index) in emotion_offsets_Y:
                        offset_y = float(emotion_offsets_Y[str(emotion_index)])
                    
                    # 加上基础偏移
                    if isinstance(offset, (tuple, list)) and len(offset) >= 2:
                        offset_x += float(offset[0])
                        offset_y += float(offset[1])
                    
                    component["offset_x1"] = offset_x
                    component["offset_y1"] = offset_y
                    
                elif comp_type == "background":
                    overlay = component.get("overlay", "")
                    if component.get("use_fixed_background", False) and overlay:
                        # 使用固定背景 - 颜色或图片
                        print(f"背景组件 - 固定背景overlay: {overlay}")
                        if overlay.startswith("#"):
                            # 颜色背景
                            background_info = f"背景: 纯色({overlay})"
                            # 确保组件包含颜色信息
                            component["color"] = overlay
                        else:
                            # 图片背景
                            background_info = f"背景: 图片({overlay})"
                        compress_layer = False
                    else:
                        # 随机背景
                        background_count = CONFIGS.background_count
                        if background_count > 0:
                            overlay = random.choice(CONFIGS.background_list)
                            component["overlay"] = overlay
                            compress_layer = False
                            background_info = f"背景: 随机({overlay})"
                        else:
                            # 没有背景图片
                            component["overlay"] = ""
                cp_components.append(component)

            # 如果没有收集到背景信息，说明没有背景组件
            if not background_info:
                background_info = "背景: 无"
            
            # 如果没有收集到角色信息，说明没有角色组件
            if not character_info:
                character_info = "角色: 无"
            
            # 使用DLL生成图像
            preview_image = generate_image_with_dll(_calculate_canvas_size(), cp_components,)
            
            get_enhanced_loader().layer_cache = True

            if preview_image:
                print(f"预览生成用时: {int((time.time()-st)*1000)}ms")
                info = f"{character_info} | {background_info} | 生成成功"
            else:
                print("预览图生成失败，使用默认图片")
                preview_image = Image.new("RGBA", _calculate_canvas_size(), (0, 0, 0, 0))
                info = f"{character_info} | {background_info} | 生成失败"
                
        except Exception as e:
            print(f"预览图生成出错: {e}")
            import traceback
            traceback.print_exc()
            preview_image, info = self._create_empty_preview()
            info = f"错误: {str(e)}"
        
        return preview_image, info
    
    def _create_empty_preview(self):
        """创建空的预览图像"""
        canvas_size = _calculate_canvas_size()
        preview_image = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        info = "没有找到组件配置"
        return preview_image, info

    def generate_image(self) -> str:
        """生成并发送图片"""
        if not self._active_process_allowed():
            return "前台应用不在白名单内"

        self.base_msg=""

        # 开始计时
        start_time = time.time()
        print(f"[{int((time.time()-start_time)*1000)}] 开始生成图片")

        # 清空剪贴板
        self.clipboard_manager.clear_clipboard()

        time.sleep(0.005)

        # 获取剪切模式设置
        cut_settings = CONFIGS.gui_settings.get("cut_settings", {})
        cut_mode = cut_settings.get("cut_mode", "full")
        
        # 根据剪切模式执行不同的剪切操作
        if cut_mode == "direct":
            # 手动剪切模式：不执行任何剪切操作，等待用户自行剪切
            self.kbd_controller.press(Key.ctrl)
            self.kbd_controller.press('x')
            self.kbd_controller.release('x')
            self.kbd_controller.release(Key.ctrl)
        else:
            # 执行剪切操作
            if cut_mode == "single_line":
                # 单行剪切模式：模拟 Shift+Home 选择当前行
                if platform.startswith("win"):
                    self.kbd_controller.press(Key.end)
                    self.kbd_controller.release(Key.end)
                    self.kbd_controller.press(Key.shift)
                    self.kbd_controller.press(Key.home)
                    self.kbd_controller.release(Key.home)
                    self.kbd_controller.release(Key.shift)
                    time.sleep(0.01)
                    self.kbd_controller.press(Key.ctrl)
                    self.kbd_controller.press('x')
                    self.kbd_controller.release('x')
                    self.kbd_controller.release(Key.ctrl)
                else:
                    self.kbd_controller.press(Key.shift)
                    self.kbd_controller.press(Key.home)
                    self.kbd_controller.release(Key.home)
                    self.kbd_controller.release(Key.shift)
                    time.sleep(0.01)
                    self.kbd_controller.press(Key.cmd)
                    self.kbd_controller.press('x')
                    self.kbd_controller.release('x')
                    self.kbd_controller.release(Key.cmd)
            else:
                # 全选剪切模式（默认）
                if platform.startswith("win"):
                    self.kbd_controller.press(Key.ctrl)
                    self.kbd_controller.press('a')
                    self.kbd_controller.release('a')
                    self.kbd_controller.press('x')
                    self.kbd_controller.release('x')
                    self.kbd_controller.release(Key.ctrl)
                else:
                    self.kbd_controller.press(Key.cmd)
                    self.kbd_controller.press('a')
                    self.kbd_controller.release('a')
                    self.kbd_controller.press('x')
                    self.kbd_controller.release('x')
                    self.kbd_controller.release(Key.cmd)

        print(f"[{int((time.time()-start_time)*1000)}] 开始读取剪切板")
        deadline = time.time() + 2.5
        while time.time() < deadline:
            text, image = self.clipboard_manager.get_clipboard_all()
            if (text and text.strip()) or image is not None:
                print(f"[{int((time.time()-start_time)*1000)}] 剪切板内容获取完成")
                break
            time.sleep(0.005)
        
        # 情感匹配处理
        sentiment_settings = CONFIGS.gui_settings.get("sentiment_matching", {})

        if (sentiment_settings.get("enabled", False) and 
            self.sentiment_analyzer_status['initialized'] and
            text.strip()):
            
            emotion_updated = self._update_emotion_by_sentiment(text)
            
            if emotion_updated:
                print(f"[{int((time.time()-start_time)*1000)}] 情感分析完成")
                # 刷新预览以显示新的表情
                self.generate_preview()
            else:
                print(f"[{int((time.time()-start_time)*1000)}] 情感分析失败")

        if text == "" and image is None:
            return "错误: 没有文本或图像"

        try:
            print(f"[{int((time.time()-start_time)*1000)}] 开始图像合成")
            
            bmp_bytes = draw_content_auto(text=text,content_image=image,)

            print(f"[{int((time.time()-start_time)*1000)}] 图片合成完成")

        except Exception as e:
            return f"生成图像失败: {e}"

        # 复制到剪贴板
        if not self.clipboard_manager.copy_image_to_clipboard(bmp_bytes):
            return "复制到剪贴板失败"
        
        print(f"[{int((time.time()-start_time)*1000)}] 图片复制到剪切板完成")

        # 等待剪贴板确认（最多等待2.5秒）
        wait = 0.01
        total = 0
        while total < 0.5:
            if self.clipboard_manager.has_image_in_clipboard():
                break
            time.sleep(wait)
            total += wait
            wait = min(wait * 1.5, 0.08)
        print(f"[{int((time.time()-start_time)*1000)}] 剪切板确认完成")

        # 自动粘贴和发送
        if CONFIGS.config.AUTO_PASTE_IMAGE:
            self.kbd_controller.press(Key.ctrl if platform != "darwin" else Key.cmd)
            self.kbd_controller.press("v")
            self.kbd_controller.release("v")
            self.kbd_controller.release(Key.ctrl if platform != "darwin" else Key.cmd)

            if not self._active_process_allowed():
                return "前台应用不在白名单内"
            if CONFIGS.config.AUTO_SEND_IMAGE:
                time.sleep(0.4)
                self.kbd_controller.press(Key.enter)
                self.kbd_controller.release(Key.enter)

                print(f"[{int((time.time()-start_time)*1000)}] 自动发送完成")
        
        # 构建状态消息
        self.base_msg += f"角色: {CONFIGS.get_character()}, 用时: {int((time.time() - start_time) * 1000)}ms"
        
        return self.base_msg