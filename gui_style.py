"""样式编辑窗口模块"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageDraw
import os
import re
import copy

from path_utils import get_resource_path, get_available_fonts
from config import CONFIGS

# 对齐方式的中英文映射
ALIGN_MAPPING = {
    "top-left": "左上",
    "top-center": "上中", 
    "top-right": "右上",
    "middle-left": "左中",
    "middle-center": "中心",
    "middle-right": "右中",
    "bottom-left": "左下",
    "bottom-center": "下中",
    "bottom-right": "右下",
    "custom": "自定义"
}

REVERSE_ALIGN_MAPPING = {v: k for k, v in ALIGN_MAPPING.items()}

# 组件的图层类型映射
COMPONENT_LAYER_TYPES = {
    "character": "角色",
    "textbox": "文本框",
    "namebox": "名称框",
    "extra": "额外组件"
}

def validate_and_update_color_preview(color_var, preview_label, color_value=None):
    """通用的颜色验证和预览更新函数"""
    if color_value is None:
        color_value = color_var.get()
    
    # 验证颜色格式
    if _validate_color_format(color_value):
        if preview_label and preview_label.winfo_exists():
            preview_label.configure(background=color_value)
        return True
    return False

def _validate_color_format(color_value):
    """验证颜色格式 - 通用版本"""
    pattern = r'^#([A-Fa-f0-9]{6})$'
    return re.match(pattern, color_value) is not None

class StyleWindow:
    """样式编辑窗口"""
    
    def __init__(self, parent, core, gui):
        self.parent = parent
        self.core = core
        self.gui = gui
        
        # 保存原始配置的副本用于比较
        self.original_style_config = copy.deepcopy(CONFIGS.style_configs.get(CONFIGS.current_style, {}))
        self.original_components = copy.deepcopy(CONFIGS.style.image_components)
        
        # 标记配置是否已修改
        self.style_changed = False
        self.components_changed = False
        
        # 创建窗口
        self.window = tk.Toplevel(parent)
        self.window.title("样式编辑")
        self.window.geometry("500x700")
        self.window.resizable(True, True)
        self.window.transient(parent)
        self.window.grab_set()
        
        # 添加窗口关闭事件处理
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 组件UI控件存储
        self.component_widgets = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI界面"""
        # 创建滚动容器
        self.main_canvas = tk.Canvas(self.window, highlightthickness=0)  # 改为实例变量
        v_scrollbar = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=self.main_canvas.yview)
        h_scrollbar = ttk.Scrollbar(self.window, orient=tk.HORIZONTAL, command=self.main_canvas.xview)
        
        # 创建可滚动框架
        scrollable_frame = ttk.Frame(self.main_canvas)
        
        # 配置canvas
        self.main_canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # 创建窗口并设置合适的宽度
        canvas_frame = self.main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        # 更新函数确保框架宽度正确
        def update_scrollable_frame_width(event=None):
            # 获取canvas当前宽度
            canvas_width = self.main_canvas.winfo_width()
            if canvas_width > 10:  # 确保有有效宽度
                # 减少右侧边距，使内容更靠近窗口边缘
                self.main_canvas.itemconfig(canvas_frame, width=canvas_width)
        
        scrollable_frame.bind("<Configure>", lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all")))
        self.main_canvas.bind("<Configure>", update_scrollable_frame_width)
        
        # 布局滚动组件
        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 初始更新一次宽度
        self.window.after(100, update_scrollable_frame_width)
        
        # 添加内部边距，使用更小的边距
        content_frame = ttk.Frame(scrollable_frame, padding="15")
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置文件管理部分
        self._setup_style_management(content_frame)
        
        # 图片比例设置
        self._setup_aspect_ratio(content_frame)
        
        # 字体设置
        self._setup_font_settings(content_frame)
        
        # 文本位置设置
        self._setup_text_settings(content_frame)
        
        # 图片组件设置
        self._setup_image_components(content_frame)
        
        # 按钮框架
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X, pady=20)
        
        ttk.Button(button_frame, text="保存", command=self._on_save_apply).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="应用", command=self._on_apply).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="取消", command=self._on_close).pack(
            side=tk.RIGHT, padx=5
        )
    
    def _setup_style_management(self, parent):
        """设置配置文件管理部分"""
        style_frame = ttk.LabelFrame(parent, text="样式配置文件", padding="10")
        style_frame.pack(fill=tk.X, pady=10)
        
        # 样式选择
        ttk.Label(style_frame, text="当前样式:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        # 创建选择框架
        selection_frame = ttk.Frame(style_frame)
        selection_frame.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        
        # 获取可用样式列表
        available_styles = list(CONFIGS.style_configs.keys())
        self.style_var = tk.StringVar(value=CONFIGS.current_style)
        
        self.style_combo = ttk.Combobox(
            selection_frame,
            textvariable=self.style_var,
            values=available_styles,
            state="readonly"
        )
        self.style_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.style_combo.bind("<<ComboboxSelected>>", self._on_style_selected)
        
        # 配置列权重
        style_frame.columnconfigure(1, weight=1)
    
    def _setup_aspect_ratio(self, parent):
        """设置图片比例部分"""
        ratio_frame = ttk.LabelFrame(parent, text="图片比例设置", padding="10")
        ratio_frame.pack(fill=tk.X, pady=10)
        
        # 比例选择
        self.aspect_ratio_var = tk.StringVar(value=CONFIGS.style.aspect_ratio)
        
        # 使用Frame将三个选项放在一行
        ratio_options_frame = ttk.Frame(ratio_frame)
        ratio_options_frame.pack(fill=tk.X, pady=5)
        
        ttk.Radiobutton(
            ratio_options_frame,
            text="3:1 (默认)",
            variable=self.aspect_ratio_var,
            value="3:1",
            command=lambda: setattr(self, 'style_changed', True)
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(
            ratio_options_frame,
            text="5:4",
            variable=self.aspect_ratio_var,
            value="5:4",
            command=lambda: setattr(self, 'style_changed', True)
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(
            ratio_options_frame,
            text="16:9",
            variable=self.aspect_ratio_var,
            value="16:9",
            command=lambda: setattr(self, 'style_changed', True)
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Label(
            ratio_frame,
            text="注：修改比例仅改变图片高度，宽度固定为2560像素",
            font=("", 8),
            foreground="gray"
        ).pack(anchor=tk.W, pady=5)
    
    def _setup_font_settings(self, parent):
        """设置字体相关设置"""
        font_frame = ttk.LabelFrame(parent, text="字体设置", padding="10")
        font_frame.pack(fill=tk.X, pady=10)
        
        # 对话框字体和字号放在同一行
        font_row_frame = ttk.Frame(font_frame)
        font_row_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(font_row_frame, text="文本字体:").pack(side=tk.LEFT, padx=(0, 5))
        
        # 获取可用字体列表
        available_fonts = get_available_fonts()
        self.font_family_var = tk.StringVar(value=CONFIGS.style.font_family)
        
        font_combo = ttk.Combobox(
            font_row_frame,
            textvariable=self.font_family_var,
            values=available_fonts,
            state="readonly",
            width=15
        )
        font_combo.pack(side=tk.LEFT, padx=(0, 20))
        font_combo.bind("<<ComboboxSelected>>", lambda e: setattr(self, 'style_changed', True))
        
        ttk.Label(font_row_frame, text="字号:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.font_size_var = tk.StringVar(value=str(CONFIGS.style.font_size))
        font_size_entry = ttk.Entry(
            font_row_frame,
            textvariable=self.font_size_var,
            width=8
        )
        font_size_entry.pack(side=tk.LEFT)
        font_size_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 文字颜色和阴影颜色在同一行
        color_frame = ttk.Frame(font_frame)
        color_frame.pack(fill=tk.X, pady=5)
        
        # 文字颜色
        ttk.Label(color_frame, text="文字颜色:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.text_color_var = tk.StringVar(value=CONFIGS.style.text_color)
        text_color_entry = ttk.Entry(
            color_frame,
            textvariable=self.text_color_var,
            width=12
        )
        text_color_entry.pack(side=tk.LEFT, padx=(0, 5))
        text_color_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 文字颜色预览
        self.text_color_preview = ttk.Label(
            color_frame,
            text="   ",
            background=self.text_color_var.get(),
            relief="solid",
            width=3
        )
        self.text_color_preview.pack(side=tk.LEFT, padx=(0, 20))
        
        # 阴影颜色
        ttk.Label(color_frame, text="阴影颜色:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.shadow_color_var = tk.StringVar(value=CONFIGS.style.shadow_color)
        shadow_color_entry = ttk.Entry(
            color_frame,
            textvariable=self.shadow_color_var,
            width=12
        )
        shadow_color_entry.pack(side=tk.LEFT, padx=(0, 5))
        shadow_color_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 阴影颜色预览
        self.shadow_color_preview = ttk.Label(
            color_frame,
            text="   ",
            background=self.shadow_color_var.get(),
            relief="solid",
            width=3
        )
        self.shadow_color_preview.pack(side=tk.LEFT)
        
        # 阴影偏移设置
        shadow_offset_frame = ttk.Frame(font_frame)
        shadow_offset_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(shadow_offset_frame, text="阴影偏移:", width=8).pack(side=tk.LEFT, padx=(0, 5))
        
        # 阴影X偏移
        ttk.Label(shadow_offset_frame, text="X:", width=2).pack(side=tk.LEFT, padx=(0, 2))
        self.shadow_offset_x_var = tk.StringVar(value=str(CONFIGS.style.shadow_offset_x))
        shadow_x_entry = ttk.Entry(shadow_offset_frame, textvariable=self.shadow_offset_x_var, width=6)
        shadow_x_entry.pack(side=tk.LEFT, padx=(0, 15))
        shadow_x_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 阴影Y偏移
        ttk.Label(shadow_offset_frame, text="Y:", width=2).pack(side=tk.LEFT, padx=(0, 2))
        self.shadow_offset_y_var = tk.StringVar(value=str(CONFIGS.style.shadow_offset_y))
        shadow_y_entry = ttk.Entry(shadow_offset_frame, textvariable=self.shadow_offset_y_var, width=6)
        shadow_y_entry.pack(side=tk.LEFT)
        shadow_y_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 绑定颜色变化
        self.text_color_var.trace_add("write", self._update_text_color_preview)
        self.shadow_color_var.trace_add("write", self._update_shadow_color_preview)
        
        # 使用角色颜色作为强调色
        self.use_character_color_var = tk.BooleanVar(value=CONFIGS.style.use_character_color)
        use_char_color_cb = ttk.Checkbutton(
            font_frame,
            text="使用角色颜色作为强调色",
            variable=self.use_character_color_var,
            command=lambda: [self._on_use_character_color_changed(), setattr(self, 'style_changed', True)]
        )
        use_char_color_cb.pack(anchor=tk.W, pady=5)
        
        # 强调颜色
        bracket_color_frame = ttk.Frame(font_frame)
        bracket_color_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(bracket_color_frame, text="强调颜色:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.bracket_color_var = tk.StringVar(value=CONFIGS.style.bracket_color)
        bracket_color_entry = ttk.Entry(
            bracket_color_frame,
            textvariable=self.bracket_color_var,
            width=12
        )
        bracket_color_entry.pack(side=tk.LEFT, padx=(0, 5))
        bracket_color_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 强调颜色预览
        self.bracket_color_preview = ttk.Label(
            bracket_color_frame,
            text="   ",
            background=self.bracket_color_var.get(),
            relief="solid",
            width=3
        )
        self.bracket_color_preview.pack(side=tk.LEFT)
        
        # 绑定强调颜色变化
        self.bracket_color_var.trace_add("write", self._update_bracket_color_preview)
        
        # 更新强调颜色输入框状态
        self._update_bracket_color_entry_state()
    
    def _setup_text_settings(self, parent):
        """设置文本设置"""
        text_frame = ttk.LabelFrame(parent, text="文本设置", padding="10")
        text_frame.pack(fill=tk.X, pady=10)
        
        # 第一行：文本框区域设置
        region_frame = ttk.Frame(text_frame)
        region_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(region_frame, text="文本区域:", width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        # X坐标
        ttk.Label(region_frame, text="X:", width=2).pack(side=tk.LEFT, padx=(0, 2))
        self.textbox_x_var = tk.StringVar(value=str(CONFIGS.style.textbox_x))
        x_entry = ttk.Entry(region_frame, textvariable=self.textbox_x_var, width=6)
        x_entry.pack(side=tk.LEFT, padx=(0, 5))
        x_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # Y坐标
        ttk.Label(region_frame, text="Y:", width=2).pack(side=tk.LEFT, padx=(0, 2))
        self.textbox_y_var = tk.StringVar(value=str(CONFIGS.style.textbox_y))
        y_entry = ttk.Entry(region_frame, textvariable=self.textbox_y_var, width=6)
        y_entry.pack(side=tk.LEFT, padx=(0, 5))
        y_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 宽度
        ttk.Label(region_frame, text="宽:", width=2).pack(side=tk.LEFT, padx=(0, 2))
        self.textbox_width_var = tk.StringVar(value=str(CONFIGS.style.textbox_width))
        width_entry = ttk.Entry(region_frame, textvariable=self.textbox_width_var, width=6)
        width_entry.pack(side=tk.LEFT, padx=(0, 5))
        width_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 高度
        ttk.Label(region_frame, text="高:", width=2).pack(side=tk.LEFT, padx=(0, 2))
        self.textbox_height_var = tk.StringVar(value=str(CONFIGS.style.textbox_height))
        height_entry = ttk.Entry(region_frame, textvariable=self.textbox_height_var, width=6)
        height_entry.pack(side=tk.LEFT, padx=(0, 5))
        height_entry.bind("<KeyRelease>", lambda e: setattr(self, 'style_changed', True))
        
        # 预览按钮（放在第一行最右边）
        preview_btn = ttk.Button(
            region_frame,
            text="预览区域",
            command=self._show_textbox_preview,
            width=8
        )
        preview_btn.pack(side=tk.RIGHT, padx=(10, 0))
        
        # 第二行：对齐设置
        align_frame = ttk.Frame(text_frame)
        align_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(align_frame, text="文本对齐:", width=10).pack(side=tk.LEFT, padx=(0, 5))
        
        # 水平对齐
        ttk.Label(align_frame, text="水平:", width=4).pack(side=tk.LEFT, padx=(0, 2))
        
        self.text_align_var = tk.StringVar(value=CONFIGS.style.text_align)
        align_mapping = {"left": "左", "center": "中", "right": "右"}
        align_display = align_mapping.get(CONFIGS.style.text_align, "左")
        align_combo = ttk.Combobox(
            align_frame,
            textvariable=self.text_align_var,
            values=["左", "中", "右"],
            state="readonly",
            width=5
        )
        align_combo.set(align_display)
        align_combo.pack(side=tk.LEFT, padx=(0, 15))
        align_combo.bind("<<ComboboxSelected>>", lambda e: setattr(self, 'style_changed', True))
        
        # 垂直对齐
        ttk.Label(align_frame, text="垂直:", width=4).pack(side=tk.LEFT, padx=(0, 2))
        
        self.text_valign_var = tk.StringVar(value=CONFIGS.style.text_valign)
        valign_mapping = {"top": "上", "middle": "中", "bottom": "下"}
        valign_display = valign_mapping.get(CONFIGS.style.text_valign, "上")
        valign_combo = ttk.Combobox(
            align_frame,
            textvariable=self.text_valign_var,
            values=["上", "中", "下"],
            state="readonly",
            width=5
        )
        valign_combo.set(valign_display)
        valign_combo.pack(side=tk.LEFT)
        valign_combo.bind("<<ComboboxSelected>>", lambda e: setattr(self, 'style_changed', True))
        
        # 说明
        ttk.Label(
            text_frame,
            text="注：文本框区域定义文字和图片的绘制范围",
            font=("", 8),
            foreground="gray"
        ).pack(anchor=tk.W, pady=(5, 0))

    def _show_textbox_preview(self):
        """显示文本框区域预览"""
        if not self.gui:
            return
        
        if (hasattr(self, '_is_previewing') and self._is_previewing):
            self._clear_textbox_preview()

        # 获取预览管理器
        preview_manager = self.gui.preview_manager
        
        # 确保有显示图片
        if not preview_manager.displayed_image:
            messagebox.showinfo("提示", "请先生成预览图")
            return
        
        # 获取当前缩放比例
        zoom_level = preview_manager.zoom_level
        
        # 创建显示图的副本
        display_copy = preview_manager.displayed_image.copy()
        draw = ImageDraw.Draw(display_copy, 'RGBA')
        
        # 计算文本框区域
        try:
            textbox_x = int(self.textbox_x_var.get() or 0)
            textbox_y = int(self.textbox_y_var.get() or 0)
            textbox_width = int(self.textbox_width_var.get() or 0)
            textbox_height = int(self.textbox_height_var.get() or 0)
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
            return
        
        # 将实际区域坐标缩放到当前显示图的大小
        scaled_x1 = int(textbox_x * zoom_level)
        scaled_y1 = int(textbox_y * zoom_level)
        scaled_x2 = int((textbox_x + textbox_width) * zoom_level)
        scaled_y2 = int((textbox_y + textbox_height) * zoom_level)
        
        # 确保坐标在显示图范围内
        img_width, img_height = display_copy.size
        if scaled_x1 < 0:
            scaled_x1 = 0
        if scaled_y1 < 0:
            scaled_y1 = 0
        if scaled_x2 > img_width:
            scaled_x2 = img_width
        if scaled_y2 > img_height:
            scaled_y2 = img_height
        
        # 绘制矩形边框（红色，宽度3）
        draw.rectangle([scaled_x1, scaled_y1, scaled_x2, scaled_y2], 
                    outline=(255, 0, 0, 255), width=3)
        
        # 绘制半透明填充
        draw.rectangle([scaled_x1, scaled_y1, scaled_x2, scaled_y2], 
                    fill=(255, 0, 0, 50))
        
        # 保存当前显示状态
        self._original_display = preview_manager.displayed_image
        self._display_with_box = display_copy
        
        # 更新显示图
        preview_manager.displayed_image = display_copy
        preview_manager._update_displayed_image()
        
        # 标记正在预览
        self._is_previewing = True

    def _clear_textbox_preview(self):
        """清除文本框区域预览"""
        if not hasattr(self, '_is_previewing') or not self._is_previewing:
            return
        
        # 获取预览管理器
        preview_manager = self.gui.preview_manager
        
        # 恢复原始预览图
        if hasattr(self, '_original_display') and self._original_display:
            preview_manager.displayed_image = self._original_display
            preview_manager._update_displayed_image()
        
        # 清除标记
        self._is_previewing = False
        if hasattr(self, '_original_display'):
            delattr(self, '_original_display')
        if hasattr(self, '_preview_with_box'):
            delattr(self, '_preview_with_box')
            
    def _setup_image_components(self, parent):
        """设置图片组件设置"""
        components_frame = ttk.LabelFrame(parent, text="图片组件设置", padding="10")
        components_frame.pack(fill=tk.X, pady=10)
        
        # 组件容器框架
        self.components_container = ttk.Frame(components_frame)
        self.components_container.pack(fill=tk.X, pady=5)
        
        # 添加新组件按钮
        add_button_frame = ttk.Frame(components_frame)
        add_button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            add_button_frame,
            text="添加图片组件",
            command=self._add_image_component,
            width=15
        ).pack(side=tk.LEFT)
        
        # 获取shader文件夹中的图片
        self.shader_files = self._get_shader_files()
        
        # 加载现有组件
        self._load_image_components()
    
    def _create_component_ui(self, component, index=None):
        """创建组件UI - 使用pack布局"""
        component_type = component.get("type", "extra")
        
        # 为内置组件设置固定ID
        if component_type == "character":
            component_id = "character"
        elif component_type == "textbox":
            component_id = "textbox"
        elif component_type == "namebox":
            component_id = "namebox"
        else:
            component_id = component.get("id", f"extra_{len(self.component_widgets)}")
        
        # 获取图层值
        layer_value = component.get("layer", 0)
        
        # 创建组件框架
        comp_frame = ttk.Frame(self.components_container, relief="solid", padding=8)
        comp_frame.pack(fill=tk.X, pady=3, padx=2)
        
        # 在框架右上角显示图层顺序
        layer_label = ttk.Label(
            comp_frame, 
            text=f"图层 {layer_value}", 
            font=("", 9, "bold"),
            foreground="blue"
        )
        layer_label.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)
        
        row = 0
        
        # 第一行：类型、启用/禁用、缩放、图层控制
        row_frame1 = ttk.Frame(comp_frame)
        row_frame1.pack(fill=tk.X, pady=(0, 5))
        
        type_display = COMPONENT_LAYER_TYPES.get(component_type, component_type)
        ttk.Label(row_frame1, text=f"{type_display}", width=7).pack(side=tk.LEFT, padx=(0, 10))
        
        # 启用/禁用复选框
        enabled_var = tk.BooleanVar(value=component.get("enabled", True))
        enabled_cb = ttk.Checkbutton(
            row_frame1,
            text="启用",
            variable=enabled_var,
            command=lambda: self._on_component_changed(component_id)
        )
        enabled_cb.pack(side=tk.LEFT, padx=(0, 10))
        
        # 缩放控件（放在启用按钮右边）
        ttk.Label(row_frame1, text="缩放:", width=6).pack(side=tk.LEFT, padx=(0, 2))
        
        scale_var = tk.StringVar(value=str(component.get("scale", 1.0)))
        scale_entry = ttk.Entry(
            row_frame1,
            textvariable=scale_var,
            width=8
        )
        scale_entry.pack(side=tk.LEFT, padx=(0, 10))
        scale_entry.bind("<KeyRelease>", lambda e: self._on_component_changed(component_id))
        
        # 图层控制按钮（靠右对齐）
        controls_frame = ttk.Frame(row_frame1)
        controls_frame.pack(side=tk.RIGHT)
        
        # 上移按钮
        move_up_btn = ttk.Button(
            controls_frame,
            text="↑",
            width=3,
            command=lambda: self._move_component_up(component_id)
        )
        move_up_btn.pack(side=tk.LEFT, padx=(0, 2))
        
        # 下移按钮
        move_down_btn = ttk.Button(
            controls_frame,
            text="↓",
            width=3,
            command=lambda: self._move_component_down(component_id)
        )
        move_down_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 删除按钮（如果是额外组件）
        if component_type == "extra":
            delete_btn = ttk.Button(
                controls_frame,
                text="删除",
                width=6,
                command=lambda: self._remove_component(component_id)
            )
            delete_btn.pack(side=tk.LEFT)
        
        # 第二行：图片选择（如果适用）
        overlay_var = None
        align_var = None
        
        if component_type in ["textbox", "namebox", "extra"]:
            row_frame2 = ttk.Frame(comp_frame)
            row_frame2.pack(fill=tk.X, pady=(0, 5))
            
            ttk.Label(row_frame2, text="图片:", width=7).pack(side=tk.LEFT, padx=(0, 5))
            
            overlay_var = tk.StringVar(value=component.get("overlay", ""))
            overlay_combo = ttk.Combobox(
                row_frame2,
                textvariable=overlay_var,
                values=[""] + self.shader_files,
                state="readonly",
                width=20
            )
            overlay_combo.pack(side=tk.LEFT, padx=(0, 20))
            overlay_combo.bind("<<ComboboxSelected>>", lambda e: self._on_component_changed(component_id))
            
            # 对齐方式（如果是额外组件或名称框）
            if component_type in ["namebox", "extra"]:
                ttk.Label(row_frame2, text="对齐:", width=5).pack(side=tk.LEFT, padx=(0, 5))
                
                # 使用中文对齐选项
                align_options = list(ALIGN_MAPPING.values())
                current_align = component.get("align", "top-left")
                align_display = ALIGN_MAPPING.get(current_align, "左上")
                
                align_var = tk.StringVar(value=align_display)
                align_combo = ttk.Combobox(
                    row_frame2,
                    textvariable=align_var,
                    values=align_options,
                    state="readonly",
                    width=12
                )
                align_combo.pack(side=tk.LEFT)
                align_combo.bind("<<ComboboxSelected>>", lambda e: self._on_component_changed(component_id))
        
        # 第三行：偏移设置（X和Y偏移）
        row_frame3 = ttk.Frame(comp_frame)
        row_frame3.pack(fill=tk.X)
        
        ttk.Label(row_frame3, text="X偏移:", width=7).pack(side=tk.LEFT, padx=(0, 5))
        
        offset_x_var = tk.StringVar(value=str(component.get("offset_x", 0)))
        offset_x_entry = ttk.Entry(
            row_frame3,
            textvariable=offset_x_var,
            width=6
        )
        offset_x_entry.pack(side=tk.LEFT, padx=(0, 15))
        offset_x_entry.bind("<KeyRelease>", lambda e: self._on_component_changed(component_id))
        
        ttk.Label(row_frame3, text="Y偏移:", width=7).pack(side=tk.LEFT, padx=(0, 5))
        
        offset_y_var = tk.StringVar(value=str(component.get("offset_y", 0)))
        offset_y_entry = ttk.Entry(
            row_frame3,
            textvariable=offset_y_var,
            width=6
        )
        offset_y_entry.pack(side=tk.LEFT)
        offset_y_entry.bind("<KeyRelease>", lambda e: self._on_component_changed(component_id))
        
        # 存储UI控件
        self.component_widgets[component_id] = {
            "frame": comp_frame,
            "type": component_type,
            "layer_label": layer_label,  # 右上角的图层标签
            "widgets": {
                "enabled_var": enabled_var,
                "layer_var": tk.IntVar(value=layer_value),  # 保留layer_var用于内部跟踪
                "overlay_var": overlay_var,
                "align_var": align_var,
                "offset_x_var": offset_x_var,
                "offset_y_var": offset_y_var,
                "scale_var": scale_var
            }
        }
        
        return component_id
    
    def _add_image_component(self):
        """添加新的图片组件"""
        # 获取所有组件的图层值
        layers = []
        for component in CONFIGS.style.image_components:
            layers.append(component.get("layer", 0))
        
        # 找到可用的最小图层序号
        new_layer = 0
        while new_layer in layers:
            new_layer += 1
        
        # 创建默认的额外组件配置
        component_config = {
            "type": "extra",
            "enabled": True,
            "overlay": "",
            "align": "top-left",
            "offset_x": 0,
            "offset_y": 0,
            "scale": 1.0,
            "layer": new_layer,
            "id": f"extra_{len([c for c in CONFIGS.style.image_components if c.get('type') == 'extra']) + 1}"
        }
        
        # 添加到临时组件列表（不直接修改CONFIGS）
        self._temp_components = copy.deepcopy(CONFIGS.style.image_components)
        self._temp_components.append(component_config)
        
        # 重新加载所有组件以确保正确显示
        self._load_image_components()
        self.components_changed = True
    
    def _remove_component(self, component_id):
        """删除组件"""
        # 从临时组件列表中移除
        self._temp_components = [c for c in self._temp_components 
                               if not (c.get("type") == "extra" and c.get("id") == component_id)]
        
        # 重新加载所有组件以确保UI正确显示
        self._load_image_components()
        self.components_changed = True
    
    def _move_component_up(self, component_id):
        """上移组件（增加图层值）并调整UI位置 - 优化版"""
        if component_id not in self.component_widgets:
            return
        
        # 获取当前组件图层值
        current_layer = self.component_widgets[component_id]["widgets"]["layer_var"].get()
        all_layers = [ui["widgets"]["layer_var"].get() for ui in self.component_widgets.values()]
        max_layer = max(all_layers)
        
        # 如果已经是最高层，不执行操作
        if current_layer >= max_layer:
            return
        
        # 找到当前组件之上的组件（图层值比当前大的组件）
        higher_layers = [layer for layer in all_layers if layer > current_layer]
        if not higher_layers:
            return
        
        next_layer = min(higher_layers)
        
        # 找到具有next_layer的组件
        for other_id, other_ui in self.component_widgets.items():
            if other_id != component_id and other_ui["widgets"]["layer_var"].get() == next_layer:
                # 交换图层值
                other_ui["widgets"]["layer_var"].set(current_layer)
                self.component_widgets[component_id]["widgets"]["layer_var"].set(next_layer)
                
                # 更新图层显示
                self._update_layer_display()
                
                # 交换两个组件在UI中的位置（不重新创建整个UI）
                self._swap_component_positions(component_id, other_id)
                
                # 标记组件已修改
                self.components_changed = True
                return
        
        # 如果没有找到交换的组件，直接增加图层值
        self.component_widgets[component_id]["widgets"]["layer_var"].set(next_layer)
        
        # 更新图层显示
        self._update_layer_display()
        
        # 重新排序UI但不重新创建
        self._reorder_component_uis_no_recreate()
        
        # 标记组件已修改
        self.components_changed = True

    def _move_component_down(self, component_id):
        """下移组件（减少图层值）并调整UI位置 - 优化版"""
        if component_id not in self.component_widgets:
            return
        
        # 获取当前组件图层值
        current_layer = self.component_widgets[component_id]["widgets"]["layer_var"].get()
        all_layers = [ui["widgets"]["layer_var"].get() for ui in self.component_widgets.values()]
        min_layer = min(all_layers)
        
        # 如果已经是最底层，不执行操作
        if current_layer <= min_layer:
            return
        
        # 找到当前组件之下的组件（图层值比当前小的组件）
        lower_layers = [layer for layer in all_layers if layer < current_layer]
        if not lower_layers:
            return
        
        prev_layer = max(lower_layers)
        
        # 找到具有prev_layer的组件
        for other_id, other_ui in self.component_widgets.items():
            if other_id != component_id and other_ui["widgets"]["layer_var"].get() == prev_layer:
                # 交换图层值
                other_ui["widgets"]["layer_var"].set(current_layer)
                self.component_widgets[component_id]["widgets"]["layer_var"].set(prev_layer)
                
                # 更新图层显示
                self._update_layer_display()
                
                # 交换两个组件在UI中的位置（不重新创建整个UI）
                self._swap_component_positions(other_id, component_id)
                
                # 标记组件已修改
                self.components_changed = True
                return
        
        # 如果没有找到交换的组件，直接减少图层值
        self.component_widgets[component_id]["widgets"]["layer_var"].set(prev_layer)
        
        # 更新图层显示
        self._update_layer_display()
        
        # 重新排序UI但不重新创建
        self._reorder_component_uis_no_recreate()
        
        # 标记组件已修改
        self.components_changed = True

    def _swap_component_positions(self, component_id1, component_id2):
        """交换两个组件在UI中的位置"""
        if component_id1 not in self.component_widgets or component_id2 not in self.component_widgets:
            return
        
        # 获取两个组件的框架
        frame1 = self.component_widgets[component_id1]["frame"]
        frame2 = self.component_widgets[component_id2]["frame"]
        
        # 从容器中暂时移除两个框架
        frame1.pack_forget()
        frame2.pack_forget()
        
        # 记录当前滚动位置
        if hasattr(self, 'main_canvas'):
            original_yview = self.main_canvas.yview()
        
        # 获取所有组件按图层排序
        components_by_layer = []
        for comp_id, component_ui in self.component_widgets.items():
            layer = component_ui["widgets"]["layer_var"].get()
            components_by_layer.append((layer, comp_id, component_ui["frame"]))
        
        # 按图层降序排序（图层值大的在上，图层值小的在下）
        components_by_layer.sort(key=lambda x: x[0], reverse=True)
        
        # 从容器中移除所有组件
        for frame in self.components_container.winfo_children():
            frame.pack_forget()
        
        # 按新的图层顺序重新pack（图层值大的在上）
        for layer, component_id, frame in components_by_layer:
            frame.pack(fill=tk.X, pady=3, padx=2)
        
        # 恢复滚动位置
        if hasattr(self, 'main_canvas') and original_yview:
            self.window.update_idletasks()  # 等待UI更新
            self.main_canvas.yview_moveto(original_yview[0])

    def _reorder_component_uis_no_recreate(self):
        """重新排序组件UI但不重新创建 - 优化版"""
        # 记录当前滚动位置
        if hasattr(self, 'main_canvas'):
            original_yview = self.main_canvas.yview()
        
        # 获取所有组件按图层排序
        components_by_layer = []
        for component_id, component_ui in self.component_widgets.items():
            layer = component_ui["widgets"]["layer_var"].get()
            components_by_layer.append((layer, component_id, component_ui["frame"]))
        
        # 按图层降序排序（图层值大的在上，图层值小的在下）
        components_by_layer.sort(key=lambda x: x[0], reverse=True)
        
        # 从容器中移除所有组件
        for frame in self.components_container.winfo_children():
            frame.pack_forget()
        
        # 按新的图层顺序重新pack（图层值大的在上）
        for layer, component_id, frame in components_by_layer:
            frame.pack(fill=tk.X, pady=3, padx=2)
        
        # 恢复滚动位置
        if hasattr(self, 'main_canvas') and original_yview:
            self.window.update_idletasks()  # 等待UI更新
            self.main_canvas.yview_moveto(original_yview[0])

    def _update_layer_display(self):
        """更新所有组件的图层显示"""
        for component_id, component_ui in self.component_widgets.items():
            layer = component_ui["widgets"]["layer_var"].get()
            component_ui["layer_label"].config(text=f"图层 {layer}")
        
    def _on_component_changed(self, component_id):
        """组件设置改变"""
        # 标记组件已修改
        self.components_changed = True
    
    def _load_image_components(self):
        """加载图片组件 - 重新创建所有UI"""
        # 清空现有组件UI
        for widget in self.components_container.winfo_children():
            widget.destroy()
        self.component_widgets.clear()
        
        # 初始化临时组件列表
        if not hasattr(self, '_temp_components'):
            self._temp_components = copy.deepcopy(CONFIGS.style.image_components)
        
        # 按图层值降序加载组件（图层值大的先加载，显示在上方）
        sorted_components = sorted(self._temp_components, 
                                  key=lambda x: x.get("layer", 0), reverse=True)
        
        # 加载所有组件
        for component in sorted_components:
            self._create_component_ui(component)
    
    def _get_shader_files(self):
        """获取shader文件夹中的图片文件列表"""
        shader_dir = get_resource_path(os.path.join("assets", "shader"))
        shader_files = []
        
        if os.path.exists(shader_dir):
            for file in os.listdir(shader_dir):
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')):
                    shader_files.append(file)
        
        return sorted(shader_files)
    
    def _on_style_selected(self, event=None):
        """样式选择改变事件 - 修复：完全重新构建UI"""
        style_name = self.style_var.get()
        
        # 加载新样式配置
        CONFIGS.apply_style(style_name)
        
        # 更新原始配置副本
        self.original_style_config = copy.deepcopy(CONFIGS.style_configs.get(style_name, {}))
        self.original_components = copy.deepcopy(CONFIGS.style.image_components)
        
        # 重置临时组件列表
        if hasattr(self, '_temp_components'):
            delattr(self, '_temp_components')
        
        # 重置修改标记
        self.style_changed = False
        self.components_changed = False
        
        # 完全重新构建UI显示
        self._rebuild_ui_from_style()

        # 通知主界面刷新预览
        if self.gui:
            self.gui.update_preview()

        # 如果预览了文本区，清除标志
        if(hasattr(self, '_is_previewing')):
            self._is_previewing = False
    
    def _rebuild_ui_from_style(self):
        """完全重新构建UI从当前样式"""
        # 图片比例
        self.aspect_ratio_var.set(CONFIGS.style.aspect_ratio)
        
        # 字体设置
        self.font_family_var.set(CONFIGS.style.font_family)
        self.font_size_var.set(str(CONFIGS.style.font_size))
        self.text_color_var.set(CONFIGS.style.text_color)
        self.use_character_color_var.set(CONFIGS.style.use_character_color)
        self.bracket_color_var.set(CONFIGS.style.bracket_color)
        
        # 更新预览
        self._update_text_color_preview()
        self._update_bracket_color_preview()
        self._update_bracket_color_entry_state()
        
        # 文本设置 - 更新文本框区域和对齐方式
        self.textbox_x_var.set(str(CONFIGS.style.textbox_x))
        self.textbox_y_var.set(str(CONFIGS.style.textbox_y))
        self.textbox_width_var.set(str(CONFIGS.style.textbox_width))
        self.textbox_height_var.set(str(CONFIGS.style.textbox_height))
        
        # 将对齐方式从英文转换为中文显示
        align_mapping = {"left": "左", "center": "中", "right": "右"}
        valign_mapping = {"top": "上", "middle": "中", "bottom": "下"}
        
        align_display = align_mapping.get(CONFIGS.style.text_align, "左")
        valign_display = valign_mapping.get(CONFIGS.style.text_valign, "上")
        
        # 直接设置Combobox的值
        if hasattr(self, 'text_align_var'):
            self.text_align_var.set(align_display)
        
        if hasattr(self, 'text_valign_var'):
            self.text_valign_var.set(valign_display)
        
        # 完全重新加载图片组件
        self._load_image_components()
    
    def _on_use_character_color_changed(self):
        """使用角色颜色作为强调色选项改变"""
        self._update_bracket_color_entry_state()
        
        # 如果启用使用角色颜色，更新强调色
        if self.use_character_color_var.get():
            self._update_bracket_color_from_character()
    
    def _update_bracket_color_from_character(self):
        """从当前角色颜色更新强调色"""
        character_name = CONFIGS.get_character()
        if character_name in CONFIGS.text_configs_dict and CONFIGS.text_configs_dict[character_name]:
            first_config = CONFIGS.text_configs_dict[character_name][0]
            font_color = first_config.get("font_color", (255, 255, 255))
            hex_color = f"#{font_color[0]:02x}{font_color[1]:02x}{font_color[2]:02x}"
            self.bracket_color_var.set(hex_color)
    
    def _update_bracket_color_entry_state(self):
        """更新强调颜色输入框状态"""
        if not hasattr(self, 'bracket_color_preview'):
            return
            
        if self.use_character_color_var.get():
            # 禁用强调颜色输入框
            for widget in self.bracket_color_preview.master.winfo_children():
                if isinstance(widget, ttk.Entry):
                    widget.config(state="disabled")
            if hasattr(self, 'bracket_color_preview'):
                self.bracket_color_preview.config(state="disabled")
        else:
            # 启用强调颜色输入框
            for widget in self.bracket_color_preview.master.winfo_children():
                if isinstance(widget, ttk.Entry):
                    widget.config(state="normal")
            if hasattr(self, 'bracket_color_preview'):
                self.bracket_color_preview.config(state="normal")
    
    def _update_text_color_preview(self, *args):
        """更新文字颜色预览 - 使用通用函数"""
        if not hasattr(self, 'text_color_preview'):
            return
            
        color_value = self.text_color_var.get()
        if validate_and_update_color_preview(self.text_color_var, self.text_color_preview, color_value):
            pass  # 颜色有效
        else:
            self.text_color_preview.configure(background="#FFFFFF")

    def _update_bracket_color_preview(self, *args):
        """更新强调颜色预览 - 使用通用函数"""
        if not hasattr(self, 'bracket_color_preview'):
            return
            
        color_value = self.bracket_color_var.get()
        if validate_and_update_color_preview(self.bracket_color_var, self.bracket_color_preview, color_value):
            pass  # 颜色有效
        else:
            self.bracket_color_preview.configure(background="#EF4F54")

    def _update_shadow_color_preview(self, *args):
        """更新阴影颜色预览 - 使用通用函数"""
        if not hasattr(self, 'shadow_color_preview'):
            return
            
        color_value = self.shadow_color_var.get()
        if validate_and_update_color_preview(self.shadow_color_var, self.shadow_color_preview, color_value):
            pass  # 颜色有效
        else:
            self.shadow_color_preview.configure(background="#000000")

    def _collect_style_data(self):
        """收集所有样式设置数据"""
        # 收集组件数据
        image_components = []
        
        # 使用临时组件列表或原始组件列表
        components_source = self._temp_components if hasattr(self, '_temp_components') else CONFIGS.style.image_components
        
        # 首先收集内置组件（character, textbox, namebox）
        for component_type in ["character", "textbox", "namebox"]:
            component = None
            for comp in components_source:
                if comp.get("type") == component_type:
                    component = comp
                    break
            
            if component:
                # 查找对应的UI控件
                component_id = component_type  # 使用组件类型作为ID
                if component_id in self.component_widgets:
                    widgets = self.component_widgets[component_id]["widgets"]
                    updated_component = component.copy()
                    
                    # 只更新基本的配置字段
                    updated_component.update({
                        "enabled": widgets["enabled_var"].get(),
                        "layer": int(widgets["layer_var"].get() or component.get("layer", 0)),
                        "offset_x": int(widgets["offset_x_var"].get() or component.get("offset_x", 0)),
                        "offset_y": int(widgets["offset_y_var"].get() or component.get("offset_y", 0)),
                        "scale": float(widgets["scale_var"].get() or component.get("scale", 1.0))
                    })
                    
                    # 对于textbox和namebox，更新overlay
                    if component_type in ["textbox", "namebox"] and widgets["overlay_var"]:
                        updated_component["overlay"] = widgets["overlay_var"].get()
                    
                    # 对于namebox，更新align（需要将中文转换回英文）
                    if component_type == "namebox" and widgets["align_var"]:
                        align_display = widgets["align_var"].get()
                        align_value = REVERSE_ALIGN_MAPPING.get(align_display, "top-left")
                        updated_component["align"] = align_value
                    
                    image_components.append(updated_component)
                else:
                    # 如果没有UI控件，使用原始配置
                    image_components.append(component.copy())
        
        # 收集额外组件
        for component_id, component_ui in self.component_widgets.items():
            if component_ui["type"] == "extra":
                widgets = component_ui["widgets"]
                
                # 将对齐方式从中文转换回英文
                align_display = widgets["align_var"].get() if widgets["align_var"] else "左上"
                align_value = REVERSE_ALIGN_MAPPING.get(align_display, "top-left")
                
                image_components.append({
                    "type": "extra",
                    "id": component_id,
                    "enabled": widgets["enabled_var"].get(),
                    "overlay": widgets["overlay_var"].get() if widgets["overlay_var"] else "",
                    "align": align_value,
                    "offset_x": int(widgets["offset_x_var"].get() or 0),
                    "offset_y": int(widgets["offset_y_var"].get() or 0),
                    "scale": float(widgets["scale_var"].get() or 1.0),
                    "layer": int(widgets["layer_var"].get() or 0)
                })
        
        # 按图层排序（图层值小的在下，图层值大的在上）
        image_components.sort(key=lambda x: x.get("layer", 0))
        
        # 将对齐方式从中文转换回英文
        text_align_display = self.text_align_var.get() if hasattr(self, 'text_align_var') else "左"
        text_valign_display = self.text_valign_var.get() if hasattr(self, 'text_valign_var') else "上"
        
        text_align_mapping = {"左": "left", "中": "center", "右": "right"}
        text_valign_mapping = {"上": "top", "中": "middle", "下": "bottom"}
        
        # 收集其他样式设置
        style_data = {
            "aspect_ratio": self.aspect_ratio_var.get() if hasattr(self, 'aspect_ratio_var') else "3:1",
            "font_family": self.font_family_var.get() if hasattr(self, 'font_family_var') else "font3",
            "font_size": int(self.font_size_var.get() or 90) if hasattr(self, 'font_size_var') else 90,
            "text_color": self.text_color_var.get() if hasattr(self, 'text_color_var') else "#FFFFFF",
            "bracket_color": self.bracket_color_var.get() if hasattr(self, 'bracket_color_var') else "#EF4F54",
            "use_character_color": self.use_character_color_var.get() if hasattr(self, 'use_character_color_var') else False,
            "shadow_color": self.shadow_color_var.get() if hasattr(self, 'shadow_color_var') else "#000000",
            "shadow_offset_x": int(self.shadow_offset_x_var.get() or 4) if hasattr(self, 'shadow_offset_x_var') else 4,
            "shadow_offset_y": int(self.shadow_offset_y_var.get() or 4) if hasattr(self, 'shadow_offset_y_var') else 4,
            "textbox_x": int(self.textbox_x_var.get() or 760) if hasattr(self, 'textbox_x_var') else 760,
            "textbox_y": int(self.textbox_y_var.get() or 355) if hasattr(self, 'textbox_y_var') else 355,
            "textbox_width": int(self.textbox_width_var.get() or 1579) if hasattr(self, 'textbox_width_var') else 1579,
            "textbox_height": int(self.textbox_height_var.get() or 445) if hasattr(self, 'textbox_height_var') else 445,
            "text_align": text_align_mapping.get(text_align_display, "left"),
            "text_valign": text_valign_mapping.get(text_valign_display, "top"),
            "image_components": image_components
        }
        
        return style_data
    
    def _on_apply(self):
        """应用样式设置"""
        style_name = self.style_var.get()
        style_data = self._collect_style_data()
        
        # 验证颜色格式
        color_errors = []
        
        # 验证文字颜色
        if not validate_and_update_color_preview(self.text_color_var, None, style_data["text_color"]):
            color_errors.append("文字颜色")
        
        # 验证强调颜色
        if not validate_and_update_color_preview(self.bracket_color_var, None, style_data["bracket_color"]):
            color_errors.append("强调颜色")
        
        # 验证阴影颜色
        if not validate_and_update_color_preview(self.shadow_color_var, None, style_data["shadow_color"]):
            color_errors.append("阴影颜色")
        
        if color_errors:
            error_msg = f"以下颜色格式无效，请输入有效的十六进制颜色值（例如：#FFFFFF）：\n{', '.join(color_errors)}"
            messagebox.showerror("错误", error_msg)
            return False
        
        # 验证数值输入
        try:
            # 验证字体大小
            if not 8 <= style_data["font_size"] <= 250:
                messagebox.showerror("错误", "字体大小必须在8到250之间")
                return False
                                
        except ValueError as e:
            messagebox.showerror("错误", f"数值格式错误: {str(e)}")
            return False
        
        # 检查样式是否有变化
        if not self.style_changed and not self.components_changed:
            # 没有变化，直接返回成功
            return True
        
        # 更新样式配置
        success = CONFIGS.update_style(style_name, style_data)
        
        if success:
            # 立即应用样式到当前配置
            CONFIGS.apply_style(style_name)
            
            # 更新原始配置副本
            self.original_style_config = copy.deepcopy(CONFIGS.style_configs.get(style_name, {}))
            self.original_components = copy.deepcopy(CONFIGS.style.image_components)
            
            # 清除临时组件列表
            if hasattr(self, '_temp_components'):
                delattr(self, '_temp_components')
            
            # 重置修改标记
            self.style_changed = False
            self.components_changed = False
            
            # 刷新GUI预览
            if self.gui:
                self.gui.update_preview()
                # 更新状态显示
                self.gui.update_status(f"样式已应用: {self.style_var.get()}")
            return True
        else:
            messagebox.showerror("错误", "应用样式失败")
            return False
    
    def _on_save_apply(self):
        """保存并应用样式设置"""
        if(self._on_apply()):
            self.window.destroy()

    def _on_close(self):
        """处理窗口关闭事件"""
        self.window.destroy()