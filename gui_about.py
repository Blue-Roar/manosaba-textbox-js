# gui_about.py
"""关于窗口"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from update_checker import update_checker
from config import CONFIGS
from path_utils import set_window_icon

class AboutWindow:
    """关于窗口"""

    def __init__(self, parent):
        self.parent = parent
        self.window = None
        self.update_result = None
        
    def open(self):
        """打开关于窗口"""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        self.window = tk.Toplevel(self.parent)
        self.window.withdraw()  # 先隐藏窗口
        
        # 设置窗口属性
        self.window.title("关于 - 魔裁文本框生成器")
        self.window.geometry("500x650")
        self.window.minsize(450, 550)
        self.window.resizable(True, True)
        self.window.transient(self.parent)
        self.window.grab_set()

        # 添加图标
        set_window_icon(self.window)

        self.setup_ui()
        
        # 计算并设置窗口位置
        self.window.update_idletasks()  # 更新窗口大小信息
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.window.winfo_screenheight() // 2) - (height // 2)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        
        self.window.deiconify()  # 显示窗口

        # 窗口关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def center_window(self):
        """窗口居中显示"""
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.window.winfo_screenheight() // 2) - (height // 2)
        self.window.geometry(f"+{x}+{y}")

    def setup_ui(self):
        """设置UI界面 - 使用ttk控件统一风格"""
        # 获取程序信息
        program_info = CONFIGS.get_program_info()
        contact_info = CONFIGS.get_contact_info()

        # 创建主容器框架
        main_container = ttk.Frame(self.window, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建滚动容器
        canvas = tk.Canvas(main_container, highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(main_container, orient=tk.VERTICAL, command=canvas.yview)
        
        # 配置canvas
        canvas.configure(yscrollcommand=v_scrollbar.set)
        
        # 创建可滚动框架
        scrollable_frame = ttk.Frame(canvas)
        
        # 创建窗口并设置合适的宽度
        canvas_frame = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def on_canvas_configure(event):
            # 更新Canvas的滚动区域
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
            
            # 设置框架宽度为Canvas宽度（减去滚动条宽度）
            canvas_width = event.width
            if canvas_width > 10:
                canvas.itemconfig(canvas_frame, width=canvas_width - 20)
        
        def on_frame_configure(event):
            # 更新滚动区域
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        # 绑定事件
        canvas.bind("<Configure>", on_canvas_configure)
        scrollable_frame.bind("<Configure>", on_frame_configure)
        
        # 绑定鼠标滚轮事件
        def on_mouse_wheel(event):
            delta = -1 if event.delta > 0 else 1
            canvas.yview_scroll(delta, "units")
            return "break"
        
        canvas.bind_all("<MouseWheel>", on_mouse_wheel)
        
        # 布局滚动组件
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 添加内部边距
        content_frame = ttk.Frame(scrollable_frame, padding="10")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 版本信息框架
        version_frame = ttk.LabelFrame(content_frame, text="版本信息", padding="10")
        version_frame.pack(fill=tk.X, pady=(0, 10))

        # 当前版本和按钮在同一行
        version_row = ttk.Frame(version_frame)
        version_row.pack(fill=tk.X, pady=(0, 5))

        version_text = f"当前版本: v{program_info['version']}"
        ttk.Label(version_row, text=version_text).pack(side=tk.LEFT, padx=(0, 10))

        # 按钮框架（右对齐）
        button_frame = ttk.Frame(version_row)
        button_frame.pack(side=tk.RIGHT)

        # 版本历史按钮
        history_button = ttk.Button(
            button_frame,
            text="版本历史",
            command=self.show_version_history,
            width=10
        )
        history_button.pack(side=tk.LEFT, padx=(0, 5))

        # 检查更新按钮
        update_button = ttk.Button(
            button_frame,
            text="检查更新",
            command=self.check_update,
            width=10
        )
        update_button.pack(side=tk.LEFT)

        # 更新结果显示区域
        self.update_result_frame = ttk.Frame(version_frame)
        self.update_result_frame.pack(fill=tk.X, pady=(5, 0))

        # 程序描述框架
        desc_frame = ttk.LabelFrame(content_frame, text="程序描述", padding="10")
        desc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        desc_text = (
            program_info.get("description", "")
            + "\n\n情感匹配使用说明：\n"
            "1. 下载ollama\n"
            "2. 在ollama中运行 OmniDimen 模型\n"
            "3. 启用程序内的情感匹配功能\n"
            "   （在setting.yml中启用sentiment_matching的display）\n"
            "4. 勾选主界面的情感匹配即可\n\n"
            "注意事项：\n"
            "• 有bug请及时反馈\n"
            "• 检查更新按钮可能对网络有要求"
        )

        # 创建Text控件
        desc_text_widget = tk.Text(
            desc_frame,
            wrap=tk.WORD,
            font=("TkDefaultFont", 10),
            relief=tk.FLAT,
            borderwidth=0,
            height=22
        )
        desc_text_widget.insert(1.0, desc_text)
        desc_text_widget.config(state=tk.DISABLED)

        # 添加滚动条
        desc_scrollbar = ttk.Scrollbar(desc_frame)
        desc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        desc_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_text_widget.config(yscrollcommand=desc_scrollbar.set)
        desc_scrollbar.config(command=desc_text_widget.yview)

        # 联系信息框架
        contact_frame = ttk.LabelFrame(content_frame, text="联系信息", padding="10")
        contact_frame.pack(fill=tk.X, pady=(0, 10))

        # 作者信息
        author_frame = ttk.Frame(contact_frame)
        author_frame.pack(fill=tk.X, pady=2)

        ttk.Label(author_frame, text="贡献者:", width=8).pack(side=tk.LEFT, padx=(0, 5))

        authors = program_info.get("author", [])
        if isinstance(authors, list):
            authors_text = ", ".join(authors)
        else:
            authors_text = str(authors)
        
        # 使用tk.Label，支持换行
        author_label = tk.Label(
            author_frame,
            text=authors_text,
            wraplength=340,
            justify=tk.LEFT,
            anchor='w',
        )
        author_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # GitHub链接
        origin_project_url = program_info.get("origin_project", "")

        if origin_project_url and origin_project_url.strip():
            github_frame = ttk.Frame(contact_frame)
            github_frame.pack(fill=tk.X, pady=2)

            ttk.Label(github_frame, text="项目地址:", width=8).pack(side=tk.LEFT, padx=(0, 5))

            # 创建可点击的链接
            github_link = ttk.Label(
                github_frame,
                text=origin_project_url.strip(),
                foreground="blue",
                cursor="hand2",
            )
            github_link.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            def on_github_click(event):
                self.open_url(origin_project_url.strip())
                
            github_link.bind("<Button-1>", on_github_click)

        # QQ交流群
        qq_groups = contact_info.get("qq_group", [])
        if qq_groups:
            if not isinstance(qq_groups, list):
                qq_groups = [qq_groups]

            qq_frame = ttk.Frame(contact_frame)
            qq_frame.pack(fill=tk.X, pady=2)

            ttk.Label(qq_frame, text="QQ交流群:", width=8).pack(side=tk.LEFT, padx=(0, 5))

            qq_groups_text = ", ".join(qq_groups)
            qq_label = ttk.Label(qq_frame, text=qq_groups_text)
            qq_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 初始更新一次滚动区域
        canvas.after(100, lambda: canvas.configure(scrollregion=canvas.bbox("all")))

    def show_version_history(self):
        """显示版本历史"""
        version_history = CONFIGS.get_version_history()

        if not version_history:
            messagebox.showinfo("版本历史", "暂无版本历史信息")
            return

        # 创建版本历史窗口
        history_window = tk.Toplevel(self.window)
        history_window.withdraw()
        history_window.title("版本历史")
        history_window.resizable(True, True)
        history_window.transient(self.window)

        set_window_icon(history_window)
        
        # 创建主框架
        main_frame = ttk.Frame(history_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 创建带滚动条的Text控件
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("TkDefaultFont", 10),
        )
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 添加滚动条
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=text_widget.yview)

        # 添加版本历史内容
        for i, version in enumerate(version_history, 1):
            text_widget.insert(tk.END, f"版本 {version.get('version', '未知')}\n")
            text_widget.insert(tk.END, f"发布时间: {version.get('date', '未知')}\n")
            text_widget.insert(tk.END, "更新说明:\n")

            descriptions = version.get("description", [])
            if isinstance(descriptions, list):
                for desc in descriptions:
                    text_widget.insert(tk.END, f"• {desc}\n")
            else:
                text_widget.insert(tk.END, f"• {descriptions}\n")

            if i < len(version_history):
                text_widget.insert(tk.END, "\n" + "-" * 50 + "\n\n")

        text_widget.config(state=tk.DISABLED)

        # 关闭按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        close_button = ttk.Button(
            button_frame, text="关闭", command=history_window.destroy, width=10
        )
        close_button.pack(anchor=tk.CENTER)
        
        # 计算窗口大小和位置
        history_window.update_idletasks()
        
        # 设置合适的大小（基于内容）
        text_widget_width = 500
        text_widget_height = 400
        
        # 获取屏幕尺寸
        screen_width = history_window.winfo_screenwidth()
        screen_height = history_window.winfo_screenheight()
        
        # 计算居中位置
        x = (screen_width // 2) - (text_widget_width // 2)
        y = (screen_height // 2) - (text_widget_height // 2)
        
        # 设置窗口大小和位置
        history_window.geometry(f"{text_widget_width}x{text_widget_height}+{x}+{y}")
        history_window.minsize(400, 300)
        
        # 显示窗口
        history_window.deiconify()

    def check_update(self):
        """检查更新"""
        # 清空之前的结果
        for widget in self.update_result_frame.winfo_children():
            widget.destroy()

        # 显示检查中
        checking_label = ttk.Label(
            self.update_result_frame,
            text="正在检查更新...",
            foreground="blue"
        )
        checking_label.pack()

        # 异步检查更新
        self.window.after(100, self._do_check_update)

    def _do_check_update(self):
        """执行检查更新"""
        try:
            # 调用更新检查器
            result = update_checker.check_update(CONFIGS.version)

            # 清除检查中标签
            for widget in self.update_result_frame.winfo_children():
                widget.destroy()

            if isinstance(result, dict) and "error" in result:
                # 检查出错
                error_label = ttk.Label(
                    self.update_result_frame,
                    text=f"检查更新失败: {result['error']}",
                    foreground="red"
                )
                error_label.pack(pady=5)
                return

            if result.get("has_update", False):
                # 有更新可用
                latest = result["latest_release"]

                # 更新提示
                update_label = ttk.Label(
                    self.update_result_frame,
                    text=f"有新版本可用: {latest['version']}",
                    foreground="green",
                    font=("TkDefaultFont", 10, "bold")
                )
                update_label.pack(pady=(0, 5))

                # 版本信息
                info_text = f"版本: {latest['version']}\n"
                info_text += f"名称: {latest['version_name']}\n"
                info_text += f"发布时间: {latest.get('published_at', '未知')}\n"
                info_text += f"预发布: {'是' if latest.get('is_prerelease', False) else '否'}"

                info_label = ttk.Label(
                    self.update_result_frame,
                    text=info_text,
                    justify=tk.LEFT
                )
                info_label.pack(anchor=tk.W, pady=(0, 5))

                # 发布说明框架
                notes_frame = ttk.LabelFrame(
                    self.update_result_frame,
                    text="发布说明",
                    padding="5"
                )
                notes_frame.pack(fill=tk.X, pady=(0, 5))

                notes = latest.get("release_notes", "无更新说明")
                if len(notes) > 500:
                    notes = notes[:500] + "..."

                notes_text = tk.Text(
                    notes_frame,
                    wrap=tk.WORD,
                    height=4,
                    font=("TkFixedFont", 9),
                    relief=tk.FLAT,
                    borderwidth=0,
                    spacing1=3,
                    spacing2=3
                )
                notes_text.insert(1.0, notes)
                notes_text.config(state=tk.DISABLED)
                notes_text.pack(fill=tk.BOTH, expand=True)

                # 下载链接
                assets = latest.get("assets", [])
                if assets:
                    download_frame = ttk.Frame(self.update_result_frame)
                    download_frame.pack(fill=tk.X, pady=(0, 5))

                    ttk.Label(download_frame, text="下载链接:").pack(side=tk.LEFT, anchor=tk.N)

                    links_frame = ttk.Frame(download_frame)
                    links_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

                    for i, asset in enumerate(assets):
                        if i >= 3:
                            if len(assets) > 3:
                                more_label = ttk.Label(
                                    links_frame,
                                    text=f"... 等 {len(assets)} 个文件",
                                    foreground="gray",
                                    font=("TkDefaultFont", 9)
                                )
                                more_label.pack(anchor=tk.W)
                            break

                        link_frame = ttk.Frame(links_frame)
                        link_frame.pack(fill=tk.X, pady=1)

                        link_label = ttk.Label(
                            link_frame,
                            text=f"{asset.get('name', '未知文件')} ({self._format_size(asset.get('size', 0))})",
                            foreground="blue",
                            cursor="hand2"
                        )
                        link_label.pack(anchor=tk.W)
                        
                        def open_link(url):
                            return lambda e: self.open_url(url)
                            
                        link_label.bind("<Button-1>", open_link(asset.get("download_url", "")))

                # GitHub页面链接
                github_link = ttk.Label(
                    self.update_result_frame,
                    text="前往GitHub发布页面",
                    foreground="blue",
                    cursor="hand2",
                    font=("TkDefaultFont", 9, "underline")
                )
                github_link.pack(pady=(5, 0))
                
                github_link.bind(
                    "<Button-1>",
                    lambda e: self.open_url(f"{update_checker.repo_url}releases/latest")
                )

            else:
                # 已是最新版本
                up_to_date_label = ttk.Label(
                    self.update_result_frame,
                    text="当前已是最新版本！",
                    foreground="green",
                    font=("TkDefaultFont", 10, "bold")
                )
                up_to_date_label.pack(pady=5)

        except Exception as e:
            # 清除检查中标签
            for widget in self.update_result_frame.winfo_children():
                widget.destroy()

            error_label = ttk.Label(
                self.update_result_frame,
                text=f"检查更新时出错: {str(e)}",
                foreground="red"
            )
            error_label.pack(pady=5)

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def open_url(self, url: str):
        """打开URL"""
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开链接: {str(e)}")

    def close(self):
        """关闭窗口"""
        if self.window:
            # 解绑鼠标滚轮事件
            self.window.unbind_all("<MouseWheel>")
            self.window.grab_release()
            self.window.destroy()
            self.window = None