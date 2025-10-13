#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code 历史对话管理工具 - GUI版本
用于管理和浏览 Claude Code projects 目录下的历史对话
"""

import os
import json
import sys
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import threading


class ConversationViewer:
    """对话内容查看器 - 集成到主界面"""

    def __init__(self, parent):
        self.parent = parent
        self.current_data = []
        self.current_conversation_info = None

    def show_conversation(self, file_path: str, conversation_info: Dict):
        """显示对话内容到主界面"""
        self.current_conversation_info = conversation_info
        self.current_data = []

        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"对话文件不存在: {file_path}")

            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise ValueError(f"对话文件为空: {file_path}")

            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        self.current_data.append((line_num, data))
                    except json.JSONDecodeError as e:
                        print(f"警告: 跳过无效的JSON行 {line_num}: {e}")
                        continue
                    except Exception as e:
                        print(f"警告: 处理行 {line_num} 时出错: {e}")
                        continue

            # 更新父界面的对话内容区域
            self.parent.update_conversation_content(conversation_info, self.current_data)

        except FileNotFoundError as e:
            messagebox.showerror("错误", f"文件不存在: {e}")
        except PermissionError as e:
            messagebox.showerror("错误", f"没有文件读取权限: {e}")
        except UnicodeDecodeError as e:
            messagebox.showerror("错误", f"文件编码错误: {e}")
        except ValueError as e:
            messagebox.showerror("错误", f"文件格式错误: {e}")
        except Exception as e:
            messagebox.showerror("错误", f"读取对话文件失败: {e}")
            # 记录详细错误用于调试
            print(f"读取对话文件时发生未知错误: {e}", file=sys.stderr)

    def populate_message_list(self, message_listbox):
        """填充消息列表到主界面"""
        message_listbox.delete(0, tk.END)

        # 性能优化：如果消息数量很大，显示警告并限制显示
        max_display_items = 1000
        data_to_display = self.current_data[:max_display_items]

        if len(self.current_data) > max_display_items:
            # 显示大量消息的提示
            message_listbox.insert(tk.END, f"📊 共 {len(self.current_data)} 条消息，显示前 {max_display_items} 条")

        for line_num, data in data_to_display:
            msg_type = data.get('type', 'unknown')
            timestamp = data.get('timestamp', '')

            # 格式化时间戳
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = timestamp[:8] if len(timestamp) >= 8 else timestamp
            else:
                time_str = ""

            # 获取消息预览
            preview = ""
            if msg_type == 'summary':
                preview = f"📝 摘要: {data.get('summary', '')[:50]}..."
            elif msg_type in ['user', 'assistant']:
                content = data.get('message', {}).get('content', '')
                if isinstance(content, str):
                    preview = content[:50].replace('\n', ' ') + "..."
                elif isinstance(content, list) and content:
                    text = content[0].get('text', '')
                    preview = text[:50].replace('\n', ' ') + "..."

            # 确定角色图标
            if msg_type == 'user':
                icon = "👤"
            elif msg_type == 'assistant':
                icon = "🤖"
            elif msg_type == 'summary':
                icon = "📝"
            else:
                icon = "📄"

            # 列表项格式
            list_item = f"{icon} [{time_str}] {preview}"
            message_listbox.insert(tk.END, list_item)

    def display_message_content(self, content_text, status_label, index):
        """显示选中消息的内容"""
        if index >= len(self.current_data):
            return

        line_num, data = self.current_data[index]

        # 清空并显示消息内容
        content_text.delete(1.0, tk.END)

        msg_type = data.get('type', 'unknown')
        timestamp = data.get('timestamp', '')

        # 消息头部
        header = f"类型: {msg_type}\n"
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                header += f"时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            except:
                header += f"时间: {timestamp}\n"

        header += f"行号: {line_num}\n"
        header += "-" * 50 + "\n\n"

        content_text.insert(tk.END, header)

        # 消息内容
        if msg_type == 'summary':
            content = data.get('summary', '')
            content_text.insert(tk.END, f"摘要内容:\n{content}")
        elif msg_type in ['user', 'assistant']:
            message_data = data.get('message', {})
            content = message_data.get('content', '')

            if isinstance(content, str):
                content_text.insert(tk.END, content)
            elif isinstance(content, list):
                for item in content:
                    if item.get('type') == 'text':
                        content_text.insert(tk.END, item.get('text', ''))
                    elif item.get('type') == 'image':
                        content_text.insert(tk.END, f"[图片: {item.get('source', '')}]\n")
                    else:
                        content_text.insert(tk.END, f"[{item.get('type', 'unknown')}: {item}]\n")
        else:
            content_text.insert(tk.END, f"其他数据:\n{json.dumps(data, ensure_ascii=False, indent=2)}")

        status_label.config(text=f"显示消息 {index + 1}/{len(self.current_data)}")

    def export_current_conversation(self, format_type: str = 'markdown'):
        """导出当前对话"""
        if not self.current_data:
            messagebox.showwarning("警告", "没有数据可导出")
            return

        if format_type == 'markdown':
            self._export_markdown()
        elif format_type == 'json':
            self._export_json()

    def _export_markdown(self):
        """导出为Markdown格式"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=f"{self.current_conversation_info['file_name'].replace('.jsonl', '.md')}",
            filetypes=[("Markdown文件", "*.md"), ("所有文件", "*.*")]
        )

        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("# 对话导出\n\n")

                for line_num, data in self.current_data:
                    msg_type = data.get('type', 'unknown')
                    timestamp = data.get('timestamp', '')

                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            time_str = f" ({dt.strftime('%Y-%m-%d %H:%M:%S')})"
                        except:
                            time_str = f" ({timestamp})"
                    else:
                        time_str = ""

                    if msg_type == 'user':
                        f.write(f"## 👤 用户{time_str}\n\n")
                    elif msg_type == 'assistant':
                        f.write(f"## 🤖 助手{time_str}\n\n")
                    elif msg_type == 'summary':
                        f.write(f"## 📝 摘要{time_str}\n\n")
                    else:
                        f.write(f"## 📄 {msg_type}{time_str}\n\n")

                    # 写入内容
                    if msg_type == 'summary':
                        f.write(f"{data.get('summary', '')}\n\n")
                    elif msg_type in ['user', 'assistant']:
                        content = data.get('message', {}).get('content', '')
                        if isinstance(content, str):
                            f.write(f"{content}\n\n")
                        elif isinstance(content, list):
                            for item in content:
                                if item.get('type') == 'text':
                                    f.write(f"{item.get('text', '')}")
                                elif item.get('type') == 'image':
                                    f.write(f"[图片: {item.get('source', '')}]\n")
                    else:
                        f.write(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n\n")

                    f.write("---\n\n")

            messagebox.showinfo("成功", f"已导出到: {filename}")

        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _export_json(self):
        """导出为JSON格式"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=f"{self.current_conversation_info['file_name'].replace('.jsonl', '.json')}",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )

        if not filename:
            return

        try:
            export_data = [data for line_num, data in self.current_data]

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("成功", f"已导出到: {filename}")

        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")


class ClaudeHistoryGUI:
    """Claude Code 历史对话管理器 - GUI版本"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude Code 历史对话管理器")
        self.root.geometry("1400x800")

        # 设置样式
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 初始化数据
        self.projects_path = Path(os.path.expanduser("~/.claude/projects"))
        if os.name == 'nt':
            self.projects_path = Path(os.path.normpath(str(self.projects_path)))

        self.projects_data = {}
        self.current_project = None
        self.current_conversations = []
        self.current_conversation = None
        self.current_messages = []

        # 排序相关
        self.sort_column = None
        self.sort_reverse = False  # False: 升序, True: 降序
        self._sorting_in_progress = False  # 防止重复触发排序
        self._sort_block_timer = None  # 排序阻塞定时器

        # 创建组件
        self.conversation_viewer = ConversationViewer(self)

        # 创建界面
        self._create_widgets()

        # 设置窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 加载数据
        self._load_projects()

    def _create_widgets(self):
        """创建界面组件"""
        # 创建菜单栏
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="刷新", command=self._load_projects)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        # 工具菜单
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="工具", menu=tools_menu)
        tools_menu.add_command(label="设置项目路径", command=self._set_projects_path)
        tools_menu.add_command(label="备份所有对话", command=self._backup_all)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self._show_about)

        # 创建主面板 - 使用三栏布局
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧面板 - 项目和对话列表
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        # 项目选择
        project_frame = ttk.LabelFrame(left_frame, text="项目", padding=8)
        project_frame.pack(fill=tk.X, padx=5, pady=5)

        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(project_frame, textvariable=self.project_var,
                                          state="readonly", width=30)
        self.project_combo.pack(fill=tk.X)
        self.project_combo.bind('<<ComboboxSelected>>', self._on_project_select)

        # 搜索框
        search_frame = ttk.LabelFrame(left_frame, text="搜索", padding=8)
        search_frame.pack(fill=tk.X, padx=5, pady=5)

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(fill=tk.X, pady=(0, 5))

        search_entry.bind('<Return>', self._search_conversations)
        ttk.Button(search_frame, text="搜索", command=self._search_conversations).pack()
        ttk.Button(search_frame, text="清除", command=self._clear_search).pack(pady=(5, 0))

        # 对话列表
        list_frame = ttk.LabelFrame(left_frame, text="对话列表", padding=8)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建Treeview
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree_scrollbar = ttk.Scrollbar(tree_frame)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        columns = ("文件名", "修改时间", "消息数", "大小")
        self.conversation_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                           yscrollcommand=tree_scrollbar.set)
        self.conversation_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.config(command=self.conversation_tree.yview)

        # 设置列标题并绑定点击排序事件
        self.conversation_tree.heading("文件名", text="文件名", command=lambda: self._sort_conversations("文件名"))
        self.conversation_tree.heading("修改时间", text="修改时间", command=lambda: self._sort_conversations("修改时间"))
        self.conversation_tree.heading("消息数", text="消息数", command=lambda: self._sort_conversations("消息数"))
        self.conversation_tree.heading("大小", text="大小", command=lambda: self._sort_conversations("大小"))

        # 设置列宽
        self.conversation_tree.column("文件名", width=250)
        self.conversation_tree.column("修改时间", width=150)
        self.conversation_tree.column("消息数", width=80)
        self.conversation_tree.column("大小", width=80)

        # 绑定选择事件 - 点击即刷新
        self.conversation_tree.bind('<<TreeviewSelect>>', self._on_conversation_select)
        self.conversation_tree.bind('<Double-1>', self._on_conversation_double_click)
        self.conversation_tree.bind('<Button-3>', self._show_context_menu)

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="删除对话", command=self._delete_conversation)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="导出为Markdown", command=self._export_conversation_markdown)
        self.context_menu.add_command(label="导出为JSON", command=self._export_conversation_json)

        # 中间面板 - 消息列表
        middle_frame = ttk.Frame(main_paned)
        main_paned.add(middle_frame, weight=1)

        # 消息列表面板
        message_frame = ttk.LabelFrame(middle_frame, text="消息列表", padding=8)
        message_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 消息列表
        msg_list_frame = ttk.Frame(message_frame)
        msg_list_frame.pack(fill=tk.BOTH, expand=True)

        msg_list_scrollbar = ttk.Scrollbar(msg_list_frame)
        msg_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.message_listbox = tk.Listbox(msg_list_frame, yscrollcommand=msg_list_scrollbar.set)
        self.message_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        msg_list_scrollbar.config(command=self.message_listbox.yview)

        # 绑定消息选择事件
        self.message_listbox.bind('<<ListboxSelect>>', self._on_message_select)

        # 右侧面板 - 对话内容和操作
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)

        # 对话信息工具栏
        info_frame = ttk.Frame(right_frame)
        info_frame.pack(fill=tk.X, padx=5, pady=3)

        self.conversation_info_label = ttk.Label(info_frame, text="未选择对话", font=("Arial", 10, "bold"))
        self.conversation_info_label.pack(side=tk.LEFT)

        # 导出按钮
        export_frame = ttk.Frame(info_frame)
        export_frame.pack(side=tk.RIGHT)

        ttk.Button(export_frame, text="导出MD", command=self._export_current_markdown, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(export_frame, text="导出JSON", command=self._export_current_json, width=8).pack(side=tk.LEFT, padx=2)

        # 对话内容显示
        content_frame = ttk.LabelFrame(right_frame, text="对话内容", padding=8)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        content_display_frame = ttk.Frame(content_frame)
        content_display_frame.pack(fill=tk.BOTH, expand=True)

        content_scrollbar = ttk.Scrollbar(content_display_frame)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.content_text = tk.Text(content_display_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scrollbar.config(command=self.content_text.yview)
        self.content_text.config(yscrollcommand=content_scrollbar.set)

        # 操作按钮
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=3)

        ttk.Button(button_frame, text="删除对话", command=self._delete_conversation).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="刷新项目", command=self._load_projects).pack(side=tk.RIGHT, padx=5)

        # 状态栏
        self.status_bar = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _load_projects(self):
        """加载项目数据"""
        if not self.projects_path.exists():
            messagebox.showerror("错误", f"Projects目录不存在: {self.projects_path}")
            return

        self.status_bar.config(text="正在加载项目数据...")
        self.root.update()

        # 在后台线程中加载数据
        threading.Thread(target=self._load_projects_thread, daemon=True).start()

    def _load_projects_thread(self):
        """后台线程加载项目数据"""
        try:
            self.projects_data = {}

            for project_dir in self.projects_path.iterdir():
                if not project_dir.is_dir():
                    continue

                project_name = project_dir.name
                conversations = []

                # 扫描.jsonl文件
                for jsonl_file in project_dir.glob("*.jsonl"):
                    conv_info = self._analyze_conversation_file(jsonl_file)
                    if conv_info:
                        conversations.append(conv_info)

                if conversations:
                    # 按修改时间排序
                    conversations.sort(key=lambda x: x['modified_time'], reverse=True)
                    self.projects_data[project_name] = conversations

            # 更新UI
            self.root.after(0, self._update_projects_ui)

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"加载项目失败: {e}"))
            self.root.after(0, lambda: self.status_bar.config(text="加载失败"))

    def _update_projects_ui(self):
        """更新项目UI"""
        # 更新项目下拉框
        project_names = list(self.projects_data.keys())
        self.project_combo['values'] = project_names

        if project_names:
            self.project_combo.set(project_names[0])
            self._on_project_select(None)

        self.status_bar.config(text=f"已加载 {len(project_names)} 个项目")

    def _analyze_conversation_file(self, file_path: Path) -> Optional[Dict]:
        """分析单个对话文件"""
        try:
            stat = file_path.stat()

            # 读取文件基本信息
            message_count = 0
            summary = None
            first_user_msg = None
            last_timestamp = None

            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)

                        # 统计消息数量
                        if data.get('type') in ['user', 'assistant']:
                            message_count += 1

                            # 记录第一条用户消息作为预览
                            if first_user_msg is None and data.get('type') == 'user':
                                content = data.get('message', {}).get('content', '')
                                if isinstance(content, str):
                                    first_user_msg = content[:100] + '...' if len(content) > 100 else content
                                elif isinstance(content, list) and content and content[0].get('type') == 'text':
                                    text = content[0].get('text', '')
                                    first_user_msg = text[:100] + '...' if len(text) > 100 else text

                        # 获取摘要
                        if data.get('type') == 'summary':
                            summary = data.get('summary', '').strip('"')

                        # 获取最后时间戳
                        timestamp = data.get('timestamp')
                        if timestamp:
                            try:
                                last_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                pass

                    except json.JSONDecodeError:
                        continue

            return {
                'file_name': file_path.name,
                'file_path': str(file_path),
                'file_size': stat.st_size,
                'modified_time': datetime.fromtimestamp(stat.st_mtime),
                'created_time': datetime.fromtimestamp(stat.st_ctime),
                'message_count': message_count,
                'summary': summary,
                'first_user_msg': first_user_msg,
                'last_timestamp': last_timestamp
            }

        except Exception as e:
            print(f"分析文件失败 {file_path}: {e}")
            return None

    def _on_project_select(self, event):
        """项目选择事件处理"""
        project_name = self.project_var.get()
        if not project_name or project_name not in self.projects_data:
            return

        self.current_project = project_name
        self.current_conversations = self.projects_data[project_name]

        # 重置排序状态并默认按修改时间降序排列
        self.sort_column = "修改时间"
        self.sort_reverse = True  # 降序，最新的在前

        # 更新对话列表
        self._update_conversation_list()

        self.status_bar.config(text=f"项目: {project_name} - {len(self.current_conversations)} 个对话")

    def _update_conversation_list(self):
        """更新对话列表"""
        # 临时解绑选择事件，避免清空列表时触发
        self.conversation_tree.unbind('<<TreeviewSelect>>')

        # 清空列表
        for item in self.conversation_tree.get_children():
            self.conversation_tree.delete(item)

        # 添加对话
        for conv in self.current_conversations:
            self.conversation_tree.insert("", tk.END,
                                       values=(
                                           conv['file_name'],
                                           conv['modified_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                           conv['message_count'],
                                           self._format_file_size(conv['file_size'])
                                       ))

        # 重新绑定选择事件
        self.conversation_tree.bind('<<TreeviewSelect>>', self._on_conversation_select)

    def _sort_conversations(self, column: str):
        """排序对话列表"""
        # 如果正在排序，直接返回
        if self._sorting_in_progress:
            return

        # 取消之前的阻塞定时器
        if self._sort_block_timer:
            self.root.after_cancel(self._sort_block_timer)
            self._sort_block_timer = None

        self._sorting_in_progress = True

        try:
            # 如果点击同一列，切换排序方向
            if self.sort_column == column:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_column = column
                self.sort_reverse = False

            # 根据列名进行排序
            if column == "文件名":
                self.current_conversations.sort(key=lambda x: x['file_name'].lower(), reverse=self.sort_reverse)
            elif column == "修改时间":
                self.current_conversations.sort(key=lambda x: x['modified_time'], reverse=self.sort_reverse)
            elif column == "消息数":
                self.current_conversations.sort(key=lambda x: x['message_count'], reverse=self.sort_reverse)
            elif column == "大小":
                self.current_conversations.sort(key=lambda x: x['file_size'], reverse=self.sort_reverse)

            # 保存当前选中的对话（如果有）
            selected_items = self.conversation_tree.selection()
            selected_file = None
            if selected_items:
                item = selected_items[0]
                item_values = self.conversation_tree.item(item, 'values')
                display_name = item_values[0]
                # 如果是搜索结果，提取实际文件名
                if display_name.startswith('🔍 '):
                    selected_file = display_name.split(' (')[0][2:]
                else:
                    selected_file = display_name

            # 完全禁用选择事件，包括移除所有绑定
            self.conversation_tree.unbind('<<TreeviewSelect>>')

            # 额外保护：临时修改选择事件处理函数
            original_handler = self._on_conversation_select
            self._on_conversation_select = lambda event: None

            # 更新显示
            self._update_conversation_list_silent()

            # 恢复之前选中的对话
            restored_item = None
            if selected_file:
                for item in self.conversation_tree.get_children():
                    item_values = self.conversation_tree.item(item, 'values')
                    display_name = item_values[0]
                    current_file = display_name.split(' (')[0][2:] if display_name.startswith('🔍 ') else display_name
                    if current_file == selected_file:
                        self.conversation_tree.selection_set(item)
                        restored_item = item
                        break
            # 如果没有恢复的选择（可能是之前没有选择任何对话），不触发选择事件

            # 更新状态栏显示排序信息
            direction = "降序" if self.sort_reverse else "升序"
            self.status_bar.config(text=f"项目: {self.current_project} - {len(self.current_conversations)} 个对话 (按{column}{direction}排列)")

            # 设置阻塞定时器，确保在足够长的时间内阻止新的排序
            def restore_handlers():
                self._on_conversation_select = original_handler
                self.conversation_tree.bind('<<TreeviewSelect>>', self._on_conversation_select)

                # 只有在真正恢复了选择时才触发选择事件
                if restored_item:
                    self.root.after(50, self._on_conversation_select_safe)
                # 如果没有恢复选择（即原本就没有选择任何对话），不触发任何事件

                self._sorting_in_progress = False
                self._sort_block_timer = None

            self._sort_block_timer = self.root.after(300, restore_handlers)

        except Exception as e:
            # 出错时确保状态恢复
            self._sorting_in_progress = False
            if self._sort_block_timer:
                self.root.after_cancel(self._sort_block_timer)
                self._sort_block_timer = None
            # 重新绑定选择事件
            self.conversation_tree.bind('<<TreeviewSelect>>', self._on_conversation_select)

    def _update_conversation_list_silent(self):
        """静默更新对话列表，不触发选择事件"""
        # 清空列表
        for item in self.conversation_tree.get_children():
            self.conversation_tree.delete(item)

        # 添加对话
        for conv in self.current_conversations:
            self.conversation_tree.insert("", tk.END,
                                       values=(
                                           conv['file_name'],
                                           conv['modified_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                           conv['message_count'],
                                           self._format_file_size(conv['file_size'])
                                       ))

    def _on_conversation_select_safe(self):
        """安全的选择事件处理，避免弹窗"""
        selection = self.conversation_tree.selection()
        if selection:
            # 只有在有选中项且有当前对话数据时才查看
            if self.current_conversation and self.current_messages:
                self._view_conversation(show_warning=False)
            # 如果有选中项但没有对话数据，尝试加载
            elif self.current_conversations:
                # 获取选中的对话信息并加载
                conv = self._get_selected_conversation(show_warning=False)
                if conv:
                    self._view_conversation(show_warning=False)

    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"

        units = ['B', 'KB', 'MB', 'GB', 'TB']
        size = float(size_bytes)

        for i, unit in enumerate(units):
            if size < 1024.0:
                if i == 0:  # B
                    return f"{int(size)} {unit}"
                else:  # KB, MB, GB, TB
                    return f"{size:.1f} {unit}"
            size /= 1024.0

        return f"{size:.1f} PB"  # PB for extremely large files

    def _search_conversations(self, event=None):
        """搜索对话"""
        keyword = self.search_var.get().strip()
        if not keyword:
            return

        if not self.current_project or not self.current_conversations:
            messagebox.showwarning("警告", "请先选择项目")
            return

        self.status_bar.config(text="正在搜索...")
        self.root.update()

        # 在后台线程中搜索
        threading.Thread(target=self._search_conversations_thread, args=(keyword,), daemon=True).start()

    def _search_conversations_thread(self, keyword: str):
        """后台线程搜索对话"""
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
            results = []

            for conv in self.current_conversations:
                matches = self._search_in_conversation(conv, pattern)
                if matches:
                    result = conv.copy()
                    result['matches'] = matches
                    results.append(result)

            # 更新UI
            self.root.after(0, lambda: self._show_search_results(results, keyword))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"搜索失败: {e}"))
            self.root.after(0, lambda: self.status_bar.config(text="搜索失败"))

    def _search_in_conversation(self, conv: Dict, pattern: re.Pattern) -> List[Dict]:
        """在单个对话中搜索"""
        matches = []

        try:
            with open(conv['file_path'], 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)

                        # 在不同字段中搜索
                        search_fields = []

                        if data.get('type') in ['user', 'assistant']:
                            content = data.get('message', {}).get('content', '')
                            if isinstance(content, str):
                                search_fields.append(('message', content))
                            elif isinstance(content, list):
                                for item in content:
                                    if item.get('type') == 'text':
                                        search_fields.append(('message', item.get('text', '')))

                        # 搜索摘要
                        if data.get('type') == 'summary':
                            summary = data.get('summary', '')
                            search_fields.append(('summary', summary))

                        # 执行搜索
                        for field_name, field_content in search_fields:
                            if pattern.search(field_content):
                                matches.append({
                                    'line_number': line_num,
                                    'field_name': field_name,
                                    'message_type': data.get('type'),
                                    'timestamp': data.get('timestamp')
                                })
                                break  # 每行只记录一次匹配

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"搜索对话失败 {conv['file_path']}: {e}")

        return matches

    def _show_search_results(self, results: List[Dict], keyword: str):
        """显示搜索结果"""
        # 临时解绑选择事件，避免清空列表时触发
        self.conversation_tree.unbind('<<TreeviewSelect>>')

        # 清空列表
        for item in self.conversation_tree.get_children():
            self.conversation_tree.delete(item)

        # 添加搜索结果
        for result in results:
            # 在文件名中添加匹配数量标识
            display_name = f"🔍 {result['file_name']} ({len(result['matches'])} 匹配)"
            self.conversation_tree.insert("", tk.END,
                                       values=(
                                           display_name,
                                           result['modified_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                           result['message_count'],
                                           self._format_file_size(result['file_size'])
                                       ))

        # 重新绑定选择事件
        self.conversation_tree.bind('<<TreeviewSelect>>', self._on_conversation_select)

        self.status_bar.config(text=f"搜索 '{keyword}' 找到 {len(results)} 个对话")

    def _clear_search(self):
        """清除搜索"""
        self.search_var.set("")
        if self.current_project:
            self._update_conversation_list()
            self.status_bar.config(text=f"项目: {self.current_project} - {len(self.current_conversations)} 个对话")

    def _on_conversation_select(self, event):
        """对话选择事件 - 点击即自动刷新"""
        # 如果正在排序，不处理选择事件
        if self._sorting_in_progress:
            return

        # 只有在有选中项时才查看对话，避免界面清空时的误触发
        selection = self.conversation_tree.selection()
        if selection:
            self._view_conversation()

    def _on_conversation_double_click(self, event):
        """对话双击事件"""
        self._view_conversation(show_warning=True)

    def _on_message_select(self, event):
        """消息选择事件"""
        selection = self.message_listbox.curselection()
        if selection:
            index = selection[0]
            self.conversation_viewer.display_message_content(self.content_text, self.status_bar, index)

    def _show_context_menu(self, event):
        """显示右键菜单"""
        # 选择点击的项目
        item = self.conversation_tree.identify('item', event.x, event.y)
        if item:
            self.conversation_tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _get_selected_conversation(self, show_warning: bool = True) -> Optional[Dict]:
        """获取选中的对话"""
        selection = self.conversation_tree.selection()
        if not selection:
            if show_warning:
                messagebox.showwarning("警告", "请先选择对话")
            return None

        item = selection[0]
        item_values = self.conversation_tree.item(item, 'values')
        display_name = item_values[0]  # 文件名列

        # 如果是搜索结果，提取实际文件名
        if display_name.startswith('🔍 '):
            # 提取真实文件名：去掉搜索标识和匹配数量
            file_name = display_name.split(' (')[0][2:]
        else:
            file_name = display_name

        # 查找对应的对话信息
        for conv in self.current_conversations:
            if conv['file_name'] == file_name:
                return conv

        return None

    def update_conversation_content(self, conversation_info, messages):
        """更新对话内容显示区域"""
        self.current_conversation = conversation_info
        self.current_messages = messages

        # 更新对话信息标签
        file_name = conversation_info['file_name']
        message_count = len(messages)
        self.conversation_info_label.config(text=f"{file_name} ({message_count} 条消息)")

        # 填充消息列表
        self.conversation_viewer.populate_message_list(self.message_listbox)

        # 如果有消息，默认选中第一条
        if messages:
            self.message_listbox.selection_set(0)
            self.conversation_viewer.display_message_content(self.content_text, self.status_bar, 0)
        else:
            self.content_text.delete(1.0, tk.END)
            self.content_text.insert(tk.END, "此对话暂无内容")

    def _view_conversation(self, show_warning: bool = False):
        """查看对话"""
        conv = self._get_selected_conversation(show_warning)
        if not conv:
            return

        # 显示对话内容
        self.conversation_viewer.show_conversation(conv['file_path'], conv)

    def _delete_conversation(self):
        """删除对话"""
        conv = self._get_selected_conversation()
        if not conv:
            return

        # 确认删除
        result = messagebox.askyesno(
            "确认删除",
            f"确定要删除对话 '{conv['file_name']}' 吗？\n\n"
            f"此操作不可恢复！\n\n"
            f"文件大小: {self._format_file_size(conv['file_size'])}\n"
            f"消息数量: {conv['message_count']}"
        )

        if not result:
            return

        try:
            # 删除文件
            os.remove(conv['file_path'])

            # 安全地从数据中移除 - 使用文件路径匹配而不是对象引用
            removed = False
            for i, conv_item in enumerate(self.current_conversations[:]):
                if conv_item['file_path'] == conv['file_path']:
                    self.current_conversations.pop(i)
                    removed = True
                    break

            # 同样从projects_data中移除
            if removed and self.current_project in self.projects_data:
                for i, conv_item in enumerate(self.projects_data[self.current_project][:]):
                    if conv_item['file_path'] == conv['file_path']:
                        self.projects_data[self.current_project].pop(i)
                        break

            # 更新UI
            self._update_conversation_list()
            # 清空对话内容显示区域
            self.conversation_info_label.config(text="未选择对话")
            self.message_listbox.delete(0, tk.END)
            self.content_text.delete(1.0, tk.END)

            messagebox.showinfo("成功", f"已删除对话: {conv['file_name']}")
            self.status_bar.config(text=f"已删除对话，剩余 {len(self.current_conversations)} 个")

        except ValueError as e:
            if "remove(x): x not in list" in str(e):
                messagebox.showinfo("提示", f"对话 '{conv['file_name']}' 已从列表中移除")
                # 强制刷新界面
                self._load_projects()
            else:
                messagebox.showerror("错误", f"删除失败: {e}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    def _export_conversation_markdown(self):
        """导出对话为Markdown"""
        conv = self._get_selected_conversation()
        if not conv:
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=conv['file_name'].replace('.jsonl', '.md'),
            filetypes=[("Markdown文件", "*.md"), ("所有文件", "*.*")]
        )

        if not filename:
            return

        try:
            self._export_to_markdown(conv['file_path'], filename)
            messagebox.showinfo("成功", f"已导出到: {filename}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _export_conversation_json(self):
        """导出对话为JSON"""
        conv = self._get_selected_conversation()
        if not conv:
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=conv['file_name'].replace('.jsonl', '.json'),
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )

        if not filename:
            return

        try:
            self._export_to_json(conv['file_path'], filename)
            messagebox.showinfo("成功", f"已导出到: {filename}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _export_current_markdown(self):
        """导出当前对话为Markdown"""
        if not self.current_conversation:
            messagebox.showwarning("警告", "请先选择对话")
            return

        try:
            self.conversation_viewer.export_current_conversation('markdown')
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _export_current_json(self):
        """导出当前对话为JSON"""
        if not self.current_conversation:
            messagebox.showwarning("警告", "请先选择对话")
            return

        try:
            self.conversation_viewer.export_current_conversation('json')
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _export_to_markdown(self, file_path: str, output_path: str):
        """导出为Markdown格式"""
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 获取对话基本信息
        file_name = Path(file_path).stem
        messages = []
        summary = ""

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)

                if data.get('type') == 'summary':
                    summary = data.get('summary', '').strip('"')

                elif data.get('type') in ['user', 'assistant']:
                    msg_type = data.get('type')
                    content = data.get('message', {}).get('content', '')
                    timestamp = data.get('timestamp', '')

                    # 处理内容格式
                    if isinstance(content, str):
                        formatted_content = content
                    elif isinstance(content, list):
                        formatted_content = ""
                        for item in content:
                            if item.get('type') == 'text':
                                formatted_content += item.get('text', '')

                    messages.append({
                        'type': msg_type,
                        'content': formatted_content,
                        'timestamp': timestamp
                    })

            except json.JSONDecodeError:
                continue

        # 生成Markdown内容
        markdown_content = f"# {file_name}\n\n"

        if summary:
            markdown_content += f"## 摘要\n{summary}\n\n"

        markdown_content += "## 对话内容\n\n"

        for i, msg in enumerate(messages, 1):
            role_name = "👤 用户" if msg['type'] == 'user' else "🤖 助手"
            timestamp_str = ""
            if msg['timestamp']:
                try:
                    dt = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
                    timestamp_str = f" ({dt.strftime('%Y-%m-%d %H:%M:%S')})"
                except:
                    pass

            markdown_content += f"### {role_name} {i}{timestamp_str}\n\n"
            markdown_content += f"{msg['content']}\n\n"
            markdown_content += "---\n\n"

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

    def _export_to_json(self, file_path: str, output_path: str):
        """导出为JSON格式"""
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 读取并过滤数据
        exported_data = []

        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                exported_data.append(data)
            except json.JSONDecodeError:
                continue

        # 写入JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(exported_data, f, ensure_ascii=False, indent=2)

    def _set_projects_path(self):
        """设置项目路径"""
        path = filedialog.askdirectory(
            title="选择Claude Projects目录",
            initialdir=str(self.projects_path)
        )

        if path:
            self.projects_path = Path(path)
            self._load_projects()

    def _backup_all(self):
        """备份所有对话"""
        if not self.projects_data:
            messagebox.showwarning("警告", "没有数据可备份")
            return

        backup_dir = filedialog.askdirectory(title="选择备份目录")
        if not backup_dir:
            return

        try:
            backup_path = Path(backup_dir) / f"claude_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path.mkdir(parents=True, exist_ok=True)

            backed_up_files = 0

            for project_name, conversations in self.projects_data.items():
                # 为每个项目创建子目录
                project_backup_dir = backup_path / project_name
                project_backup_dir.mkdir(exist_ok=True)

                for conv in conversations:
                    source_file = Path(conv['file_path'])
                    target_file = project_backup_dir / conv['file_name']

                    import shutil
                    shutil.copy2(source_file, target_file)
                    backed_up_files += 1

            messagebox.showinfo("成功", f"备份完成！\n已备份 {backed_up_files} 个文件到:\n{backup_path}")

        except Exception as e:
            messagebox.showerror("错误", f"备份失败: {e}")

    def _on_closing(self):
        """窗口关闭事件处理"""
        try:
            self.cleanup()
            self.root.destroy()
        except Exception as e:
            print(f"清理资源时出错: {e}")
            self.root.destroy()

    def _show_about(self):
        """显示关于信息"""
        about_text = """Claude Code 历史对话管理器 - GUI版本

版本: 1.0.0
作者: Claude

功能特性:
• 浏览和管理Claude Code历史对话
• 查看完整对话内容
• 搜索对话内容
• 导出对话为Markdown/JSON格式
• 安全删除对话
• 备份所有对话

技术栈:
• Python + tkinter
• 纯标准库实现
• 跨平台支持

© 2025 All rights reserved."""

        messagebox.showinfo("关于", about_text)

    def cleanup(self):
        """清理资源，防止内存泄漏"""
        if hasattr(self, '_sort_block_timer') and self._sort_block_timer:
            self.root.after_cancel(self._sort_block_timer)
            self._sort_block_timer = None

    def run(self):
        """运行应用"""
        try:
            self.root.mainloop()
        finally:
            self.cleanup()


def main():
    """主函数"""
    try:
        # 检查Python版本
        if sys.version_info < (3, 7):
            print("错误: 需要 Python 3.7 或更高版本")
            sys.exit(1)

        # 检查tkinter是否可用
        try:
            import tkinter as tk_test
        except ImportError:
            print("错误: tkinter 模块不可用，请安装 Python tkinter")
            sys.exit(1)

        # 创建并运行应用
        app = ClaudeHistoryGUI()
        app.run()

    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        error_msg = f"应用启动失败: {e}"
        try:
            # 如果GUI已经初始化，显示错误对话框
            messagebox.showerror("启动错误", error_msg)
        except:
            # GUI未初始化，打印到控制台
            print(error_msg)
        sys.exit(1)


if __name__ == '__main__':
    main()