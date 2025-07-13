#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, font
import os
import platform
import sys
import locale
from pathlib import Path

# UTF-8ロケール設定
try:
    locale.setlocale(locale.LC_ALL, 'ja_JP.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except locale.Error:
        pass


class FileManager:
    def __init__(self, root):
        self.root = root
        self.root.title("File Manager")
        self.root.geometry("1000x700")
        
        # 日本語フォント設定
        self.setup_fonts()
        
        self.setup_ui()
        self.setup_initial_data()
    
    def setup_fonts(self):
        """プラットフォームに応じた日本語フォントを設定"""
        system = platform.system()
        
        # フォント候補リスト
        font_candidates = []
        
        if system == "Windows":
            font_candidates = [
                ("Yu Gothic UI", 9),
                ("Meiryo UI", 9),
                ("MS Gothic", 9),
                ("Arial Unicode MS", 9)
            ]
        elif system == "Darwin":  # macOS
            font_candidates = [
                ("Hiragino Kaku Gothic ProN", 10),
                ("Hiragino Sans", 10),
                ("Arial Unicode MS", 10)
            ]
        else:  # Linux
            font_candidates = [
                ("Noto Sans CJK JP", 9),
                ("Noto Sans", 9),
                ("DejaVu Sans", 9),
                ("Liberation Sans", 9),
                ("TkDefaultFont", 9)
            ]
        
        # 利用可能なフォントを検索
        available_fonts = font.families()
        self.default_font = None
        
        for font_family, size in font_candidates:
            if font_family in available_fonts or font_family == "TkDefaultFont":
                try:
                    test_font = font.Font(family=font_family, size=size)
                    self.default_font = (font_family, size)
                    self.header_font = (font_family, size + 2, "bold")
                    break
                except Exception:
                    continue
        
        # 最終フォールバック
        if self.default_font is None:
            self.default_font = ("TkDefaultFont", 9)
            self.header_font = ("TkDefaultFont", 11, "bold")
        
        # デフォルトフォントを設定
        self.root.option_add("*Font", self.default_font)
        
        # tkinter全体の文字エンコーディング設定
        self.root.tk.call('encoding', 'system', 'utf-8')

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        self.setup_left_pane(paned_window)
        self.setup_right_pane(paned_window)

    def setup_left_pane(self, parent):
        left_frame = ttk.Frame(parent)
        parent.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="フォルダーツリー", font=self.header_font).pack(pady=(0, 5))
        
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeviewのスタイル設定
        style = ttk.Style()
        style.configure("Custom.Treeview", font=self.default_font)
        style.configure("Custom.Treeview.Heading", font=self.header_font)
        
        self.folder_tree = ttk.Treeview(tree_frame, style="Custom.Treeview")
        self.folder_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.folder_tree.yview)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.folder_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        self.folder_tree.bind("<<TreeviewSelect>>", self.on_folder_select)
        self.folder_tree.bind("<<TreeviewOpen>>", self.on_folder_expand)

    def setup_right_pane(self, parent):
        right_frame = ttk.Frame(parent)
        parent.add(right_frame, weight=2)
        
        ttk.Label(right_frame, text="ファイル一覧", font=self.header_font).pack(pady=(0, 5))
        
        file_frame = ttk.Frame(right_frame)
        file_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("名前", "タイプ", "サイズ", "更新日時")
        self.file_list = ttk.Treeview(file_frame, columns=columns, show="tree headings", style="Custom.Treeview")
        
        for col in columns:
            self.file_list.heading(col, text=col)
            self.file_list.column(col, width=120)
        
        self.file_list.column("#0", width=50)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        file_scrollbar = ttk.Scrollbar(file_frame, orient=tk.VERTICAL, command=self.file_list.yview)
        file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_list.configure(yscrollcommand=file_scrollbar.set)

    def setup_initial_data(self):
        if platform.system() == "Windows":
            drives = self.get_windows_drives()
            for drive in drives:
                self.folder_tree.insert("", tk.END, iid=drive, text=drive, values=[drive])
                self.folder_tree.insert(drive, tk.END, text="読み込み中...")
        else:
            home_path = str(Path.home())
            root_path = "/"
            
            self.folder_tree.insert("", tk.END, iid=root_path, text="Root (/)", values=[root_path])
            self.folder_tree.insert(root_path, tk.END, text="読み込み中...")
            
            self.folder_tree.insert("", tk.END, iid=home_path, text=f"Home ({home_path})", values=[home_path])
            self.folder_tree.insert(home_path, tk.END, text="読み込み中...")

    def get_windows_drives(self):
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
        return drives

    def on_folder_expand(self, event):
        selected_item = self.folder_tree.focus()
        if selected_item:
            self.load_folder_children(selected_item)

    def on_folder_select(self, event):
        selected_item = self.folder_tree.focus()
        if selected_item:
            folder_path = self.folder_tree.item(selected_item)["values"][0] if self.folder_tree.item(selected_item)["values"] else selected_item
            self.load_file_list(folder_path)

    def load_folder_children(self, parent_item):
        children = self.folder_tree.get_children(parent_item)
        if len(children) == 1 and self.folder_tree.item(children[0])["text"] == "読み込み中...":
            self.folder_tree.delete(children[0])
            
            folder_path = self.folder_tree.item(parent_item)["values"][0] if self.folder_tree.item(parent_item)["values"] else parent_item
            
            try:
                for item in sorted(os.listdir(folder_path)):
                    item_path = os.path.join(folder_path, item)
                    if os.path.isdir(item_path):
                        # フォルダー名の文字エンコーディング処理
                        try:
                            display_name = item
                            if isinstance(item, bytes):
                                display_name = item.decode('utf-8', errors='replace')
                            elif not isinstance(item, str):
                                display_name = str(item)
                        except Exception:
                            display_name = repr(item)
                        
                        item_id = self.folder_tree.insert(parent_item, tk.END, text=display_name, values=[item_path])
                        self.folder_tree.insert(item_id, tk.END, text="読み込み中...")
            except PermissionError:
                self.folder_tree.insert(parent_item, tk.END, text="アクセス権限がありません")
            except Exception as e:
                self.folder_tree.insert(parent_item, tk.END, text=f"エラー: {str(e)}")

    def load_file_list(self, folder_path):
        for item in self.file_list.get_children():
            self.file_list.delete(item)
        
        try:
            items = sorted(os.listdir(folder_path))
            
            for item in items:
                item_path = os.path.join(folder_path, item)
                
                if os.path.isdir(item_path):
                    item_type = "フォルダー"
                    size = "-"
                    icon = "📁"
                else:
                    item_type = "ファイル"
                    try:
                        size = self.format_file_size(os.path.getsize(item_path))
                    except:
                        size = "-"
                    icon = "📄"
                
                try:
                    mtime = os.path.getmtime(item_path)
                    import datetime
                    mod_time = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    mod_time = "-"
                
                # ファイル名の文字エンコーディング処理
                try:
                    display_name = item
                    if isinstance(item, bytes):
                        display_name = item.decode('utf-8', errors='replace')
                    elif not isinstance(item, str):
                        display_name = str(item)
                except Exception:
                    display_name = repr(item)
                
                self.file_list.insert("", tk.END, text=icon, values=(display_name, item_type, size, mod_time))
                
        except PermissionError:
            self.file_list.insert("", tk.END, text="❌", values=("アクセス権限がありません", "", "", ""))
        except Exception as e:
            self.file_list.insert("", tk.END, text="❌", values=(f"エラー: {str(e)}", "", "", ""))

    def format_file_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"


def main():
    root = tk.Tk()
    app = FileManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()