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
import concurrent.futures
from functools import lru_cache
import time


class TokenCalculator:
    """Token计算器 - 支持精确计算和智能估算"""

    def __init__(self):
        self.encoder = None
        self.precise_mode = False
        self._init_encoder()

        # 缓存统计
        self.cache_hits = 0
        self.cache_misses = 0

    @lru_cache(maxsize=1024)
    def count_tokens_cached(self, text: str) -> int:
        """带缓存的token计算"""
        return self.count_tokens(text)

    def _init_encoder(self):
        """初始化token编码器"""
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("o200k_base")  # Claude使用的编码器
            self.precise_mode = True
            print("✅ 已加载tiktoken，使用精确token计算模式")
        except ImportError:
            self.encoder = None
            self.precise_mode = False
            print("⚠️  未安装tiktoken，使用智能估算模式")
        except Exception as e:
            self.encoder = None
            self.precise_mode = False
            print(f"⚠️  tiktoken初始化失败: {e}，使用智能估算模式")

    def count_tokens(self, text: str) -> int:
        """计算文本的token数量"""
        if not text or not text.strip():
            return 0

        text = text.strip()

        # 精确模式
        if self.precise_mode and self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception as e:
                print(f"Token计算错误，切换到估算模式: {e}")
                return self._estimate_tokens(text)

        # 估算模式
        return self._estimate_tokens(text)

    def _estimate_tokens(self, text: str) -> int:
        """智能token估算算法"""
        if not text:
            return 0

        # 中文字符统计
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))

        # 英文字符统计
        english_chars = len(re.findall(r"[a-zA-Z]", text))

        # 数字统计
        digit_chars = len(re.findall(r"[0-9]", text))

        # 标点符号和空格
        space_chars = len(re.findall(r"\s", text))
        punct_chars = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))

        # Token估算规则（基于Claude的tokenization特点）
        # 中文字符：通常1-2个字符=1token
        chinese_tokens = chinese_chars * 1.8

        # 英文单词：平均4个字符=1token
        english_tokens = english_chars / 4.0

        # 数字：通常1-3个数字=1token
        digit_tokens = digit_chars / 2.0

        # 空格和标点：通常多个=1token
        other_tokens = (space_chars + punct_chars) / 5.0

        total_tokens = chinese_tokens + english_tokens + digit_tokens + other_tokens

        return max(1, int(total_tokens))

    def count_message_tokens(self, message_data: Dict) -> int:
        """计算单个消息的token数量（带缓存）"""
        # 为消息创建缓存键（基于消息内容的hash）
        cache_key = self._create_message_cache_key(message_data)

        if hasattr(self, '_message_token_cache'):
            if cache_key in self._message_token_cache:
                self.cache_hits += 1
                return self._message_token_cache[cache_key]
        else:
            self._message_token_cache = {}

        self.cache_misses += 1
        total_tokens = self._calculate_message_tokens(message_data)

        # 缓存结果
        self._message_token_cache[cache_key] = total_tokens

        # 限制缓存大小
        if len(self._message_token_cache) > 500:
            # 删除一些旧缓存
            keys_to_remove = list(self._message_token_cache.keys())[:100]
            for key in keys_to_remove:
                del self._message_token_cache[key]

        return total_tokens

    def _create_message_cache_key(self, message_data: Dict) -> str:
        """为消息创建缓存键"""
        try:
            # 创建基于内容的hash
            import hashlib
            content_str = json.dumps(message_data, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(content_str.encode('utf-8')).hexdigest()[:16]
        except:
            # 如果序列化失败，使用类型和时间戳作为键
            msg_type = message_data.get('type', 'unknown')
            timestamp = message_data.get('timestamp', '')
            return f"{msg_type}_{timestamp}"

    def _calculate_message_tokens(self, message_data: Dict) -> int:
        """实际计算消息token数量"""
        total_tokens = 0

        msg_type = message_data.get('type', '')

        if msg_type == 'summary':
            # 摘要消息
            summary = message_data.get('summary', '')
            total_tokens += self.count_tokens_cached(summary)

        elif msg_type in ['user', 'assistant']:
            # 用户和助手消息
            message = message_data.get('message', {})
            content = message.get('content', '')

            if isinstance(content, str):
                total_tokens += self.count_tokens_cached(content)
            elif isinstance(content, list):
                for item in content:
                    if item.get('type') == 'text':
                        total_tokens += self.count_tokens_cached(item.get('text', ''))
                    elif item.get('type') == 'image':
                        # 图片消息通常有固定的token开销
                        total_tokens += 85  # Claude的图片token估算值

        # 消息结构开销（JSON结构、时间戳等）
        total_tokens += 10  # 基础结构开销

        return total_tokens

    def analyze_conversation_tokens(self, conversation_data: List[Dict]) -> Dict:
        """分析整个对话的token使用情况"""
        if not conversation_data:
            return {
                'total_tokens': 0,
                'user_tokens': 0,
                'assistant_tokens': 0,
                'summary_tokens': 0,
                'message_count': 0,
                'avg_tokens_per_message': 0
            }

        total_tokens = 0
        user_tokens = 0
        assistant_tokens = 0
        summary_tokens = 0
        message_count = 0

        for line_num, data in conversation_data:
            msg_type = data.get('type', '')
            msg_tokens = self.count_message_tokens(data)

            total_tokens += msg_tokens
            message_count += 1

            if msg_type == 'user':
                user_tokens += msg_tokens
            elif msg_type == 'assistant':
                assistant_tokens += msg_tokens
            elif msg_type == 'summary':
                summary_tokens += msg_tokens

        avg_tokens = total_tokens / message_count if message_count > 0 else 0

        return {
            'total_tokens': total_tokens,
            'user_tokens': user_tokens,
            'assistant_tokens': assistant_tokens,
            'summary_tokens': summary_tokens,
            'message_count': message_count,
            'avg_tokens_per_message': round(avg_tokens, 1)
        }

    def format_tokens(self, token_count: int) -> str:
        """格式化token数量显示"""
        if token_count < 1000:
            return f"{token_count:,}"
        elif token_count < 1000000:
            return f"{token_count/1000:.1f}K"
        else:
            return f"{token_count/1000000:.1f}M"

    def get_token_cost_estimate(self, token_count: int, model: str = "claude-3-5-sonnet") -> Dict:
        """估算token成本（基于Claude定价）"""
        # 定价数据（每1M tokens的美元价格）
        pricing = {
            "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
            "claude-3-5-haiku": {"input": 0.25, "output": 1.25},
            "claude-3-opus": {"input": 15.0, "output": 75.0},
        }

        if model not in pricing:
            model = "claude-3-5-sonnet"

        input_cost = (token_count / 1000000) * pricing[model]["input"]
        output_cost = (token_count / 1000000) * pricing[model]["output"]

        return {
            "model": model,
            "input_cost": round(input_cost, 4),
            "output_cost": round(output_cost, 4),
            "total_cost": round(input_cost + output_cost, 4)
        }


class ConversationViewer:
    """对话内容查看器 - 集成到主界面"""

    def __init__(self, parent):
        self.parent = parent
        self.current_data = []
        self.current_conversation_info = None

    def show_conversation(self, file_path: str, conversation_info: Dict):
        """显示对话内容到主界面（延迟加载）"""
        self.current_conversation_info = conversation_info
        self.current_data = []

        # 先显示加载状态
        self.parent.conversation_info_label.config(
            text=f"{conversation_info['file_name']} (正在加载...)"
        )
        self.parent.message_listbox.delete(0, tk.END)
        self.parent.message_listbox.insert(tk.END, "🔄 正在加载对话内容...")
        self.parent.content_text.delete(1.0, tk.END)
        self.parent.content_text.insert(tk.END, "正在加载对话内容，请稍候...")

        # 在后台线程中加载对话内容
        threading.Thread(
            target=self._load_conversation_content,
            args=(file_path, conversation_info),
            daemon=True
        ).start()

    def _load_conversation_content(self, file_path: str, conversation_info: Dict):
        """后台加载对话内容"""
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"对话文件不存在: {file_path}")

            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise ValueError(f"对话文件为空: {file_path}")

            # 延迟加载：先读取前几条消息快速显示
            quick_data = []
            full_data = []

            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)

                        # 添加到完整数据
                        full_data.append((line_num, data))

                        # 前10条消息用于快速显示
                        if len(quick_data) < 10:
                            quick_data.append((line_num, data))

                        # 每20条消息更新一次UI（对于大文件）
                        elif len(full_data) % 20 == 0:
                            self.parent.root.after(0, lambda d=full_data.copy(): self._update_loading_progress(d))

                    except json.JSONDecodeError as e:
                        print(f"警告: 跳过无效的JSON行 {line_num}: {e}")
                        continue
                    except Exception as e:
                        print(f"警告: 处理行 {line_num} 时出错: {e}")
                        continue

            # 设置完整数据
            self.current_data = full_data

            # 更新UI
            self.parent.root.after(0, lambda: self._finish_loading(conversation_info, full_data))

        except FileNotFoundError as e:
            self.parent.root.after(0, lambda: messagebox.showerror("错误", f"文件不存在: {e}"))
        except PermissionError as e:
            self.parent.root.after(0, lambda: messagebox.showerror("错误", f"没有文件读取权限: {e}"))
        except UnicodeDecodeError as e:
            self.parent.root.after(0, lambda: messagebox.showerror("错误", f"文件编码错误: {e}"))
        except ValueError as e:
            self.parent.root.after(0, lambda: messagebox.showerror("错误", f"文件格式错误: {e}"))
        except Exception as e:
            self.parent.root.after(0, lambda: messagebox.showerror("错误", f"读取对话文件失败: {e}"))
            # 记录详细错误用于调试
            print(f"读取对话文件时发生未知错误: {e}", file=sys.stderr)

    def _update_loading_progress(self, current_data):
        """更新加载进度"""
        count = len(current_data)
        self.parent.conversation_info_label.config(
            text=f"{self.current_conversation_info['file_name']} (已加载 {count} 条消息...)"
        )

    def _finish_loading(self, conversation_info: Dict, full_data: List[Tuple]):
        """完成加载并更新UI"""
        # 更新父界面的对话内容区域
        self.parent.update_conversation_content(conversation_info, full_data)

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
            # 计算token统计
            token_analysis = self.parent.token_calculator.analyze_conversation_tokens(self.current_data)
            cost_estimate = self.parent.token_calculator.get_token_cost_estimate(token_analysis['total_tokens'])

            with open(filename, 'w', encoding='utf-8') as f:
                f.write("# 对话导出\n\n")

                # 写入token统计信息
                f.write("## 📊 Token统计报告\n\n")
                f.write(f"- **总Token数**: {self.parent.token_calculator.format_tokens(token_analysis['total_tokens'])}\n")
                f.write(f"- **用户Token**: {self.parent.token_calculator.format_tokens(token_analysis['user_tokens'])}\n")
                f.write(f"- **助手Token**: {self.parent.token_calculator.format_tokens(token_analysis['assistant_tokens'])}\n")
                f.write(f"- **摘要Token**: {self.parent.token_calculator.format_tokens(token_analysis['summary_tokens'])}\n")
                f.write(f"- **消息数量**: {token_analysis['message_count']}\n")
                f.write(f"- **平均Token/消息**: {token_analysis['avg_tokens_per_message']}\n\n")

                f.write("### 💰 成本估算\n\n")
                f.write(f"- **模型**: {cost_estimate['model']}\n")
                f.write(f"- **输入成本**: ${cost_estimate['input_cost']:.4f}\n")
                f.write(f"- **输出成本**: ${cost_estimate['output_cost']:.4f}\n")
                f.write(f"- **总成本**: ${cost_estimate['total_cost']:.4f}\n\n")

                f.write("---\n\n")

                # 写入对话内容
                message_num = 1
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

                    # 计算当前消息的token数
                    msg_tokens = self.parent.token_calculator.count_message_tokens(data)

                    if msg_type == 'user':
                        f.write(f"## 👤 用户 {message_num}{time_str} ({self.parent.token_calculator.format_tokens(msg_tokens)} tokens)\n\n")
                        message_num += 1
                    elif msg_type == 'assistant':
                        f.write(f"## 🤖 助手 {message_num}{time_str} ({self.parent.token_calculator.format_tokens(msg_tokens)} tokens)\n\n")
                        message_num += 1
                    elif msg_type == 'summary':
                        f.write(f"## 📝 摘要{time_str} ({self.parent.token_calculator.format_tokens(msg_tokens)} tokens)\n\n")
                    else:
                        f.write(f"## 📄 {msg_type}{time_str} ({self.parent.token_calculator.format_tokens(msg_tokens)} tokens)\n\n")

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
            # 计算token统计
            token_analysis = self.parent.token_calculator.analyze_conversation_tokens(self.current_data)
            cost_estimate = self.parent.token_calculator.get_token_cost_estimate(token_analysis['total_tokens'])

            # 准备导出数据
            export_data = {
                "metadata": {
                    "file_name": self.current_conversation_info['file_name'],
                    "export_time": datetime.now().isoformat(),
                    "total_messages": len(self.current_data),
                    "token_analysis": token_analysis,
                    "cost_estimate": cost_estimate,
                    "calculator_mode": "精确模式" if self.parent.token_calculator.precise_mode else "估算模式"
                },
                "messages": []
            }

            # 为每个消息添加token信息
            for line_num, data in self.current_data:
                msg_data = data.copy()
                msg_data["line_number"] = line_num
                msg_data["token_count"] = self.parent.token_calculator.count_message_tokens(data)
                export_data["messages"].append(msg_data)

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

        # 创建Token计算器
        self.token_calculator = TokenCalculator()

        # 搜索缓存和索引
        self._search_cache = {}
        self._search_index = {}  # 简单的搜索索引
        self._search_cache_max_size = 50

        # 文件分析缓存
        self._file_analysis_cache = {}
        self._file_cache_max_size = 100

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

        columns = ("文件名", "修改时间", "消息数", "Token", "大小")
        self.conversation_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                           yscrollcommand=tree_scrollbar.set)
        self.conversation_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.config(command=self.conversation_tree.yview)

        # 设置列标题并绑定点击排序事件
        self.conversation_tree.heading("文件名", text="文件名", command=lambda: self._sort_conversations("文件名"))
        self.conversation_tree.heading("修改时间", text="修改时间", command=lambda: self._sort_conversations("修改时间"))
        self.conversation_tree.heading("消息数", text="消息数", command=lambda: self._sort_conversations("消息数"))
        self.conversation_tree.heading("Token", text="Token", command=lambda: self._sort_conversations("Token"))
        self.conversation_tree.heading("大小", text="大小", command=lambda: self._sort_conversations("大小"))

        # 设置列宽
        self.conversation_tree.column("文件名", width=220)
        self.conversation_tree.column("修改时间", width=140)
        self.conversation_tree.column("消息数", width=70)
        self.conversation_tree.column("Token", width=80)
        self.conversation_tree.column("大小", width=70)

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
            start_time = time.time()
            self.projects_data = {}

            # 获取所有项目目录
            project_dirs = [d for d in self.projects_path.iterdir() if d.is_dir()]

            if not project_dirs:
                self.root.after(0, lambda: self._update_projects_ui())
                return

            # 使用线程池并发处理项目
            max_workers = min(4, len(project_dirs))  # 限制最大并发数
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有项目分析任务
                future_to_project = {
                    executor.submit(self._analyze_project_concurrent, project_dir): project_dir
                    for project_dir in project_dirs
                }

                # 收集结果
                completed_count = 0
                for future in concurrent.futures.as_completed(future_to_project):
                    project_dir = future_to_project[future]
                    try:
                        project_name, conversations = future.result()
                        if conversations:
                            self.projects_data[project_name] = conversations
                        completed_count += 1

                        # 更新进度
                        progress = (completed_count / len(project_dirs)) * 100
                        self.root.after(0, lambda p=progress: self.status_bar.config(
                            text=f"正在加载项目... {completed_count}/{len(project_dirs)} ({p:.0f}%)"
                        ))

                    except Exception as e:
                        print(f"分析项目 {project_dir.name} 时出错: {e}")

            # 更新UI
            elapsed_time = time.time() - start_time
            self.root.after(0, lambda: self._update_projects_ui_with_stats(elapsed_time))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"加载项目失败: {e}"))
            self.root.after(0, lambda: self.status_bar.config(text="加载失败"))

    def _analyze_project_concurrent(self, project_dir: Path) -> Tuple[str, List[Dict]]:
        """并发分析单个项目"""
        project_name = project_dir.name
        conversations = []

        try:
            # 获取项目中的所有.jsonl文件
            jsonl_files = list(project_dir.glob("*.jsonl"))

            if not jsonl_files:
                return project_name, []

            # 使用线程池并发处理对话文件
            max_file_workers = min(2, len(jsonl_files))  # 每个项目最多2个并发文件处理
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_file_workers) as file_executor:
                # 提交所有文件分析任务
                future_to_file = {
                    file_executor.submit(self._analyze_conversation_file, jsonl_file): jsonl_file
                    for jsonl_file in jsonl_files
                }

                # 收集结果
                for future in concurrent.futures.as_completed(future_to_file):
                    jsonl_file = future_to_file[future]
                    try:
                        conv_info = future.result()
                        if conv_info:
                            conversations.append(conv_info)
                    except Exception as e:
                        print(f"分析文件 {jsonl_file.name} 时出错: {e}")

            # 按修改时间排序
            conversations.sort(key=lambda x: x['modified_time'], reverse=True)
            return project_name, conversations

        except Exception as e:
            print(f"分析项目 {project_name} 时出错: {e}")
            return project_name, []

    def _update_projects_ui_with_stats(self, elapsed_time: float):
        """更新项目UI并显示性能统计"""
        # 更新项目下拉框
        project_names = list(self.projects_data.keys())
        self.project_combo['values'] = project_names

        if project_names:
            self.project_combo.set(project_names[0])
            self._on_project_select(None)

        # 计算总对话数和token数
        total_conversations = sum(len(convs) for convs in self.projects_data.values())
        total_tokens = sum(
            sum(conv.get('total_tokens', 0) for conv in convs)
            for convs in self.projects_data.values()
        )

        # 显示加载统计
        status_text = f"已加载 {len(project_names)} 个项目, {total_conversations} 个对话"
        if total_tokens > 0:
            token_str = self.token_calculator.format_tokens(total_tokens)
            status_text += f", {token_str} tokens"
        status_text += f" (耗时: {elapsed_time:.2f}s)"

        self.status_bar.config(text=status_text)

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
        """分析单个对话文件（带缓存）"""
        try:
            # 检查文件修改时间
            stat = file_path.stat()
            mtime = stat.st_mtime

            # 创建缓存键
            cache_key = f"{file_path}:{mtime}"

            # 检查缓存
            if cache_key in self._file_analysis_cache:
                return self._file_analysis_cache[cache_key]

            # 分析文件
            result = self._perform_file_analysis(file_path, stat)

            # 缓存结果
            if result:
                self._cache_file_analysis(cache_key, result)

            return result

        except Exception as e:
            print(f"分析文件失败 {file_path}: {e}")
            return None

    def _perform_file_analysis(self, file_path: Path, stat) -> Optional[Dict]:
        """实际执行文件分析"""
        try:
            # 读取文件基本信息
            message_count = 0
            summary = None
            first_user_msg = None
            last_timestamp = None

            # Token计算相关
            conversation_data = []
            total_tokens = 0

            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        conversation_data.append((line_num, data))

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

            # 计算token使用情况
            token_analysis = self.token_calculator.analyze_conversation_tokens(conversation_data)
            total_tokens = token_analysis['total_tokens']

            return {
                'file_name': file_path.name,
                'file_path': str(file_path),
                'file_size': stat.st_size,
                'modified_time': datetime.fromtimestamp(stat.st_mtime),
                'created_time': datetime.fromtimestamp(stat.st_ctime),
                'message_count': message_count,
                'summary': summary,
                'first_user_msg': first_user_msg,
                'last_timestamp': last_timestamp,
                # 新增token相关字段
                'total_tokens': total_tokens,
                'token_analysis': token_analysis
            }

        except Exception as e:
            print(f"分析文件失败 {file_path}: {e}")
            return None

    def _cache_file_analysis(self, cache_key: str, result: Dict):
        """缓存文件分析结果"""
        # 限制缓存大小
        if len(self._file_analysis_cache) >= self._file_cache_max_size:
            # 删除一些旧缓存
            keys_to_remove = list(self._file_analysis_cache.keys())[:20]
            for key in keys_to_remove:
                del self._file_analysis_cache[key]

        self._file_analysis_cache[cache_key] = result

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

        # 计算项目总token数
        total_tokens = sum(conv.get('total_tokens', 0) for conv in self.current_conversations)
        total_tokens_str = self.token_calculator.format_tokens(total_tokens)

        self.status_bar.config(text=f"项目: {project_name} - {len(self.current_conversations)} 个对话, 总计 {total_tokens_str} tokens")

    def _update_conversation_list(self):
        """更新对话列表"""
        # 临时解绑选择事件，避免清空列表时触发
        self.conversation_tree.unbind('<<TreeviewSelect>>')

        # 清空列表
        for item in self.conversation_tree.get_children():
            self.conversation_tree.delete(item)

        # 添加对话
        for conv in self.current_conversations:
            token_count = conv.get('total_tokens', 0)
            token_str = self.token_calculator.format_tokens(token_count) if token_count > 0 else "未知"

            self.conversation_tree.insert("", tk.END,
                                       values=(
                                           conv['file_name'],
                                           conv['modified_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                           conv['message_count'],
                                           token_str,
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
            elif column == "Token":
                self.current_conversations.sort(key=lambda x: x.get('total_tokens', 0), reverse=self.sort_reverse)
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
            token_count = conv.get('total_tokens', 0)
            token_str = self.token_calculator.format_tokens(token_count) if token_count > 0 else "未知"

            self.conversation_tree.insert("", tk.END,
                                       values=(
                                           conv['file_name'],
                                           conv['modified_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                           conv['message_count'],
                                           token_str,
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
        """后台线程搜索对话（优化版）"""
        try:
            # 检查搜索缓存
            cache_key = f"{self.current_project}:{keyword}"
            if cache_key in self._search_cache:
                cached_results = self._search_cache[cache_key]
                self.root.after(0, lambda: self._show_search_results(cached_results, keyword))
                self.root.after(0, lambda: self.status_bar.config(text=f"搜索 '{keyword}' 找到 {len(cached_results)} 个对话 (缓存)"))
                return

            # 编译正则表达式
            start_time = time.time()
            pattern = re.compile(keyword, re.IGNORECASE)

            # 使用线程池并发搜索
            if len(self.current_conversations) > 5:
                results = self._search_conversations_parallel(pattern)
            else:
                results = self._search_conversations_sequential(pattern)

            # 缓存搜索结果
            self._cache_search_results(cache_key, results)

            search_time = time.time() - start_time

            # 更新UI
            self.root.after(0, lambda: self._show_search_results(results, keyword))
            self.root.after(0, lambda: self.status_bar.config(
                text=f"搜索 '{keyword}' 找到 {len(results)} 个对话 (耗时: {search_time:.2f}s)"
            ))

        except re.error as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"搜索表达式无效: {e}"))
            self.root.after(0, lambda: self.status_bar.config(text="搜索失败"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"搜索失败: {e}"))
            self.root.after(0, lambda: self.status_bar.config(text="搜索失败"))

    def _search_conversations_parallel(self, pattern: re.Pattern) -> List[Dict]:
        """并发搜索对话"""
        results = []
        max_workers = min(4, len(self.current_conversations))

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交搜索任务
            future_to_conv = {
                executor.submit(self._search_in_conversation, conv, pattern): conv
                for conv in self.current_conversations
            }

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_conv):
                conv = future_to_conv[future]
                try:
                    matches = future.result()
                    if matches:
                        result = conv.copy()
                        result['matches'] = matches
                        results.append(result)
                except Exception as e:
                    print(f"搜索对话 {conv['file_name']} 时出错: {e}")

        return results

    def _search_conversations_sequential(self, pattern: re.Pattern) -> List[Dict]:
        """顺序搜索对话（用于少量对话）"""
        results = []

        for conv in self.current_conversations:
            matches = self._search_in_conversation(conv, pattern)
            if matches:
                result = conv.copy()
                result['matches'] = matches
                results.append(result)

        return results

    def _cache_search_results(self, cache_key: str, results: List[Dict]):
        """缓存搜索结果"""
        # 限制缓存大小
        if len(self._search_cache) >= self._search_cache_max_size:
            # 删除最旧的缓存项
            oldest_key = next(iter(self._search_cache))
            del self._search_cache[oldest_key]

        self._search_cache[cache_key] = results

    def _search_in_conversation(self, conv: Dict, pattern: re.Pattern) -> List[Dict]:
        """在单个对话中搜索（优化版）"""
        matches = []

        try:
            # 先检查预览文本，如果预览文本匹配则直接返回
            first_user_msg = conv.get('first_user_msg', '')
            summary = conv.get('summary', '')

            # 快速检查预览和摘要
            quick_content = f"{first_user_msg} {summary}"
            if pattern.search(quick_content):
                # 如果预览匹配，返回一个快速匹配标记
                return [{
                    'line_number': 0,
                    'field_name': 'preview',
                    'message_type': 'quick_match',
                    'timestamp': conv.get('last_timestamp'),
                    'preview': True
                }]

            # 如果快速匹配失败，进行全文搜索
            with open(conv['file_path'], 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)

                        # 使用快速内容提取
                        content_text = self._extract_searchable_text(data)
                        if content_text and pattern.search(content_text):
                            matches.append({
                                'line_number': line_num,
                                'field_name': 'content',
                                'message_type': data.get('type'),
                                'timestamp': data.get('timestamp'),
                                'preview': False
                            })

                            # 限制匹配数量，避免返回过多结果
                            if len(matches) >= 10:
                                break

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"搜索对话失败 {conv['file_path']}: {e}")

        return matches

    def _extract_searchable_text(self, data: Dict) -> str:
        """快速提取可搜索的文本内容"""
        try:
            msg_type = data.get('type', '')

            if msg_type == 'summary':
                return data.get('summary', '')

            elif msg_type in ['user', 'assistant']:
                content = data.get('message', {}).get('content', '')
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # 只提取文本内容，跳过图片和其他类型
                    text_parts = []
                    for item in content:
                        if item.get('type') == 'text':
                            text_parts.append(item.get('text', ''))
                    return ' '.join(text_parts)

            return ''
        except Exception:
            return ''

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

            token_count = result.get('total_tokens', 0)
            token_str = self.token_calculator.format_tokens(token_count) if token_count > 0 else "未知"

            self.conversation_tree.insert("", tk.END,
                                       values=(
                                           display_name,
                                           result['modified_time'].strftime("%Y-%m-%d %H:%M:%S"),
                                           result['message_count'],
                                           token_str,
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
        token_count = conversation_info.get('total_tokens', 0)
        token_str = self.token_calculator.format_tokens(token_count) if token_count > 0 else "未知"

        self.conversation_info_label.config(text=f"{file_name} ({message_count} 条消息, {token_str} tokens)")

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
        token_count = conv.get('total_tokens', 0)
        token_str = self.token_calculator.format_tokens(token_count) if token_count > 0 else "未知"

        result = messagebox.askyesno(
            "确认删除",
            f"确定要删除对话 '{conv['file_name']}' 吗？\n\n"
            f"此操作不可恢复！\n\n"
            f"文件大小: {self._format_file_size(conv['file_size'])}\n"
            f"消息数量: {conv['message_count']}\n"
            f"Token数量: {token_str}"
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
        conversation_data = []

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                conversation_data.append((line_num, data))

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
                        'timestamp': timestamp,
                        'raw_data': data
                    })

            except json.JSONDecodeError:
                continue

        # 计算token统计
        token_analysis = self.token_calculator.analyze_conversation_tokens(conversation_data)
        cost_estimate = self.token_calculator.get_token_cost_estimate(token_analysis['total_tokens'])

        # 生成Markdown内容
        markdown_content = f"# {file_name}\n\n"

        # 添加token统计报告
        markdown_content += "## 📊 Token统计报告\n\n"
        markdown_content += f"- **总Token数**: {self.token_calculator.format_tokens(token_analysis['total_tokens'])}\n"
        markdown_content += f"- **用户Token**: {self.token_calculator.format_tokens(token_analysis['user_tokens'])}\n"
        markdown_content += f"- **助手Token**: {self.token_calculator.format_tokens(token_analysis['assistant_tokens'])}\n"
        markdown_content += f"- **摘要Token**: {self.token_calculator.format_tokens(token_analysis['summary_tokens'])}\n"
        markdown_content += f"- **消息数量**: {token_analysis['message_count']}\n"
        markdown_content += f"- **平均Token/消息**: {token_analysis['avg_tokens_per_message']}\n\n"

        markdown_content += "### 💰 成本估算\n\n"
        markdown_content += f"- **模型**: {cost_estimate['model']}\n"
        markdown_content += f"- **输入成本**: ${cost_estimate['input_cost']:.4f}\n"
        markdown_content += f"- **输出成本**: ${cost_estimate['output_cost']:.4f}\n"
        markdown_content += f"- **总成本**: ${cost_estimate['total_cost']:.4f}\n\n"

        markdown_content += "---\n\n"

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

            # 计算消息token数
            msg_tokens = self.token_calculator.count_message_tokens(msg['raw_data'])

            markdown_content += f"### {role_name} {i}{timestamp_str} ({self.token_calculator.format_tokens(msg_tokens)} tokens)\n\n"
            markdown_content += f"{msg['content']}\n\n"
            markdown_content += "---\n\n"

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

    def _export_to_json(self, file_path: str, output_path: str):
        """导出为JSON格式"""
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 读取并过滤数据，计算token
        conversation_data = []
        exported_data = []

        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                conversation_data.append((line_num, data))
                exported_data.append(data)
            except json.JSONDecodeError:
                continue

        # 计算token统计
        token_analysis = self.token_calculator.analyze_conversation_tokens(conversation_data)
        cost_estimate = self.token_calculator.get_token_cost_estimate(token_analysis['total_tokens'])

        # 构建完整的导出数据
        complete_export_data = {
            "metadata": {
                "file_name": Path(file_path).name,
                "export_time": datetime.now().isoformat(),
                "total_messages": len(exported_data),
                "token_analysis": token_analysis,
                "cost_estimate": cost_estimate,
                "calculator_mode": "精确模式" if self.token_calculator.precise_mode else "估算模式"
            },
            "messages": []
        }

        # 为每个消息添加token信息
        for line_num, data in conversation_data:
            msg_data = data.copy()
            msg_data["line_number"] = line_num
            msg_data["token_count"] = self.token_calculator.count_message_tokens(data)
            complete_export_data["messages"].append(msg_data)

        # 写入JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(complete_export_data, f, ensure_ascii=False, indent=2)

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
        # 获取缓存统计
        token_cache_stats = getattr(self.token_calculator, 'cache_hits', 0), getattr(self.token_calculator, 'cache_misses', 0)
        token_hits, token_misses = token_cache_stats
        token_total = token_hits + token_misses
        token_hit_rate = (token_hits / token_total * 100) if token_total > 0 else 0

        search_cache_size = len(self._search_cache)
        file_cache_size = len(getattr(self, '_file_analysis_cache', {}))

        about_text = f"""Claude Code 历史对话管理器 - GUI版本

版本: 1.2.0 - 性能优化版
作者: Claude

功能特性:
• 浏览和管理Claude Code历史对话
• 查看完整对话内容
• 搜索对话内容（并发搜索 + 缓存）
• 导出对话为Markdown/JSON格式
• 安全删除对话
• 备份所有对话
• Token计算和成本估算
• 性能优化（并发处理 + 缓存机制）

性能统计:
• Token缓存命中率: {token_hit_rate:.1f}% ({token_hits}/{token_total})
• 搜索缓存大小: {search_cache_size} 项
• 文件分析缓存: {file_cache_size} 项
• 计算器模式: {'精确模式' if self.token_calculator.precise_mode else '估算模式'}

技术栈:
• Python + tkinter
• concurrent.futures 并发处理
• LRU缓存优化
• 跨平台支持

性能优化特性:
• 多线程并发扫描
• 智能缓存机制
• 延迟加载
• 搜索结果缓存

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