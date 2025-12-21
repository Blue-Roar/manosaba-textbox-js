"""文件加载工具"""
import os
import threading
import queue
from PIL import ImageFont, Image
from typing import Callable, Dict, Any, Optional

from path_utils import get_resource_path, get_font_path
from config import CONFIGS

# 资源缓存
_font_cache = {}
_background_cache = {}  # 背景图片缓存（长期缓存）
_character_cache = {}   # 角色图片缓存（可释放）
_general_image_cache = {}  # 通用图片缓存


def get_image_path(base_name: str, sub_dir: str = "", with_ext: bool = True) -> str:
    """获取图片路径，支持多种格式"""
    supported_formats = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']
    
    for ext in supported_formats:
        if sub_dir:
            path = get_resource_path(os.path.join("assets", sub_dir, f"{base_name}{ext}"))
        else:
            path = get_resource_path(f"{base_name}{ext}")
        
        if os.path.exists(path):
            return path if with_ext else path[:-len(ext)]
    
    # 如果所有格式都不存在，返回默认png格式的路径
    if sub_dir:
        return get_resource_path(os.path.join("assets", sub_dir, f"{base_name}.png"))
    else:
        return get_resource_path(f"{base_name}.png")


def get_background_path(background_name: str) -> str:
    """获取背景图片路径"""
    return get_image_path(background_name, "background")


def get_character_path(character_name: str, emotion_index: int) -> str:
    """获取角色图片路径"""
    base_name = f"{character_name} ({emotion_index})"
    return get_image_path(base_name, os.path.join("chara", character_name))


# 预加载状态管理类
class PreloadManager:
    """预加载管理器"""
    def __init__(self):
        self._preload_status = {
            'total_items': 0,
            'loaded_items': 0,
            'is_complete': False
        }
        self._update_callback = None
        self._lock = threading.Lock()
        self._current_character = None       # 当前预加载的角色
        self._should_stop = threading.Event()  # 停止信号
        self._has_work = threading.Event()    # 有工作需要处理的信号
        self._task_queue = queue.Queue(maxsize=1)  # 任务队列，最多存储1个任务
        
        # 启动工作线程
        self._worker_thread = threading.Thread(
            target=self._preload_worker, 
            daemon=True,
            name="PreloadWorker"
        )
        self._worker_thread.start()
    
    def set_update_callback(self, callback: Callable[[str], None]):
        """设置状态更新回调"""
        self._update_callback = callback
    
    def update_status(self, message: str):
        """更新状态"""
        if self._update_callback:
            self._update_callback(message)

    def _preload_worker(self):
        """工作线程，持续处理预加载任务"""
        while not self._should_stop.is_set():
            try:
                # 等待有任务需要处理
                character_name = self._task_queue.get(timeout=0.1)
                
                # 检查预加载设置是否启用
                preloading_settings = CONFIGS.gui_settings.get("preloading", {})
                preload_character = preloading_settings.get("preload_character", True)
                
                if not preload_character:
                    self.update_status(f"角色预加载已禁用，跳过 {character_name} 的预加载")
                    # 标记任务完成
                    self._task_queue.task_done()
                    continue
                
                # 处理任务
                self._preload_character_task(character_name)
                
                # 标记任务完成
                self._task_queue.task_done()
                
            except queue.Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                self.update_status(f"预加载工作线程异常: {str(e)}")
        
    def _preload_character_task(self, character_name: str):
        """实际的预加载任务"""
        try:
            with self._lock:
                self._current_character = character_name
                self._preload_status['is_complete'] = False
            
            if character_name not in CONFIGS.mahoshojo:
                self.update_status(f"角色 {character_name} 配置不存在")
                return
            
            emotion_count = CONFIGS.mahoshojo[character_name]["emotion_count"]
            
            # 更新总项目数
            with self._lock:
                self._preload_status['total_items'] = emotion_count
                self._preload_status['loaded_items'] = 0
            
            self.update_status(f"开始预加载角色 {character_name}")
            
            # 预加载所有表情图片
            for emotion_index in range(1, emotion_count + 1):
                # 检查是否需要停止（有新的任务到来）
                if not self._task_queue.empty():
                    self.update_status(f"角色 {character_name} 预加载被新任务中断")
                    return
                
                load_character_safe(character_name, emotion_index)
                
                # 更新已加载项目数
                with self._lock:
                    self._preload_status['loaded_items'] = emotion_index
                
                # 实时更新进度
                progress = emotion_index / emotion_count
                if self._update_callback:
                    self.update_status(f"预加载角色 {character_name}: {emotion_index}/{emotion_count} ({progress:.0%})")
            
            with self._lock:
                self._preload_status['is_complete'] = True
            
            self.update_status(f"角色 {character_name} 预加载完成")
            
        except Exception as e:
            self.update_status(f"角色 {character_name} 预加载失败: {str(e)}")
            with self._lock:
                self._preload_status['is_complete'] = True
    
    def preload_character_images_async(self, character_name: str) -> bool:
        """异步预加载指定角色的所有表情图片"""
        try:
            # 清空队列中的旧任务（如果有）
            while not self._task_queue.empty():
                try:
                    self._task_queue.get_nowait()
                    self._task_queue.task_done()
                except queue.Empty:
                    break
            
            # 放入新任务
            self._task_queue.put_nowait(character_name)
            self.update_status(f"已提交角色 {character_name} 预加载任务")
            return True
            
        except queue.Full:
            self.update_status(f"预加载任务队列已满，无法提交 {character_name}")
            return False

    def preload_backgrounds_async(self):
        """异步预加载所有背景图片"""
        def preload_task():
            try:
                self.update_status("正在预加载背景图片...")
                background_count = CONFIGS.background_count
                
                for background_index in range(1, background_count + 1):
                    # 预加载背景图片
                    load_background_safe(f"c{background_index}")
                    
                    # 实时更新进度
                    progress = background_index / background_count
                    if background_index % 5 == 0 or background_index == background_count:
                        self.update_status(f"预加载背景: {background_index}/{background_count} ({progress:.0%})")
                
                self.update_status("背景图片预加载完成")
            except Exception as e:
                self.update_status(f"背景图片预加载失败: {str(e)}")
        
        # 在后台线程中执行预加载
        preload_thread = threading.Thread(target=preload_task, daemon=True, name="PreloadBG")
        preload_thread.start()
    
    def get_preload_progress(self) -> float:
        """获取预加载进度"""
        with self._lock:
            if self._preload_status['total_items'] == 0:
                return 0.0
            
            progress = self._preload_status['loaded_items'] / self._preload_status['total_items']
            return min(progress, 1.0)
    
    def get_preload_status(self) -> Dict[str, Any]:
        """获取预加载状态"""
        with self._lock:
            return {
                'loaded_items': self._preload_status['loaded_items'],
                'total_items': self._preload_status['total_items'],
                'is_complete': self._preload_status['is_complete'],
                'current_character': self._current_character
            }
    
#缓存字体
def load_font_cached(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """使用字体名称加载字体，支持多种格式（TTF、OTF等）"""
    cache_key = f"{font_name}_{size}"
    if cache_key not in _font_cache:
        # 获取字体路径（支持多种格式）
        font_path = get_font_path(font_name)
        
        if os.path.exists(font_path):
            try:
                _font_cache[cache_key] = ImageFont.truetype(font_path, size=size)
            except Exception as e:
                print(f"字体加载失败: {font_path}, 错误: {e}")
                return ImageFont.truetype(font_path, size=size)
        else:
            print(f"字体文件不存在: {font_path}")
            return ImageFont.truetype(font_path, size=size)
    
    return _font_cache[cache_key]

def load_image_cached(image_path: str) -> Image.Image:
    """通用图片缓存加载，支持透明通道"""
    cache_key = image_path
    if cache_key not in _general_image_cache:
        if image_path and os.path.exists(image_path):
            _general_image_cache[cache_key] = Image.open(image_path).convert("RGBA")
        else:
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
    return _general_image_cache[cache_key].copy()


# 安全加载背景图片（文件不存在时返回默认值）
def load_background_safe(background_name: str, default_size: tuple = (800, 600), default_color: tuple = (100, 100, 200)) -> Image.Image:
    """安全加载背景图片，文件不存在时返回默认图片，加载后等比缩放到宽度2560"""
    # 获取背景图片路径
    background_path = get_background_path(background_name)
    
    try:
        cache_key = background_path
        if cache_key not in _background_cache:
            if os.path.exists(background_path):
                img = Image.open(background_path).convert("RGBA")
                
                # 等比缩放到宽度2560
                target_width = 2560
                if img.width != target_width:
                    width_ratio = target_width / img.width
                    new_height = int(img.height * width_ratio)
                    img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
                
                _background_cache[cache_key] = img
            else:
                raise FileNotFoundError(f"背景图片文件不存在: {background_path}")
        return _background_cache[cache_key].copy()
    except FileNotFoundError:
        # 创建默认图片，并缩放到宽度2560
        default_img = Image.new("RGBA", default_size, default_color)
        
        # 等比缩放到宽度2560
        target_width = 2560
        if default_img.width != target_width:
            width_ratio = target_width / default_img.width
            new_height = int(default_img.height * width_ratio)
            default_img = default_img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
        return default_img

# 安全加载角色图片（文件不存在时返回默认值）
def load_character_safe(character_name: str, emotion_index: int, default_size: tuple = (800, 600), default_color: tuple = (0, 0, 0, 0)) -> Image.Image:
    """安全加载角色图片，文件不存在时返回默认图片"""
    # 获取角色图片路径
    character_path = get_character_path(character_name, emotion_index)
    
    try:
        # 生成不区分格式的缓存键（移除文件扩展名）
        cache_key = character_path.rsplit('.', 1)[0]  # 移除扩展名
        if cache_key not in _character_cache:
            if os.path.exists(character_path):
                img = Image.open(character_path).convert("RGBA")
                
                # 应用缩放
                scale = CONFIGS.current_character.get("scale", 1.0)
                
                if scale != 1.0:
                    original_width, original_height = img.size
                    new_width = int(original_width * scale)
                    new_height = int(original_height * scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                result =img
                    
                _character_cache[cache_key] = result
            else:
                raise FileNotFoundError(f"角色图片文件不存在: {character_path}")
        return _character_cache[cache_key].copy()
    except FileNotFoundError:
        # 创建默认透明图片
        return Image.new("RGBA", default_size, default_color)

def clear_cache(cache_type: str = "all"):
    """清理特定类型的缓存"""
    global _font_cache, _background_cache, _character_cache, _general_image_cache
    
    if cache_type in ("font", "all"):
        _font_cache.clear()
    if cache_type in ("background", "all"):
        _background_cache.clear()
    if cache_type in ("character", "all"):
        _character_cache.clear()
    if cache_type in ("image", "all"):
        _general_image_cache.clear()

# 创建全局预加载管理器实例
_preload_manager = PreloadManager()

def get_preload_manager() -> PreloadManager:
    """获取预加载管理器实例"""
    return _preload_manager