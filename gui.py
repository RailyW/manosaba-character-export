"""基础 GUI 入口。

功能：
1. 选择游戏根目录（文件夹选择器）；
2. 自动读取并展示角色 bundle 列表；
3. 支持多选 / 全选 / 取消全选；
4. 支持测试模式；
5. 支持选择输出目录；
6. 调用现有 pipeline 执行导出。
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from renderer_app.pipeline import resolve_characters_dir_from_game_root, run_pipeline


class ExporterGUI:
    """导出工具图形界面。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("manosaba 立绘导出工具")
        self.root.geometry("860x620")

        self.game_root_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(Path("output").resolve()))
        self.test_mode_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择游戏根目录。")

        self.bundle_names: list[str] = []
        self.bundle_vars: dict[str, tk.BooleanVar] = {}
        self.export_thread: threading.Thread | None = None
        self.progress_queue: queue.Queue = queue.Queue()

        self._build_ui()

    def _build_ui(self) -> None:
        frm = tk.Frame(self.root, padx=12, pady=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # 游戏根目录
        tk.Label(frm, text="游戏根目录：").grid(row=0, column=0, sticky="w")
        tk.Entry(frm, textvariable=self.game_root_var, width=90).grid(row=1, column=0, columnspan=4, sticky="we", pady=(0, 6))
        tk.Button(frm, text="浏览...", command=self.choose_game_root).grid(row=1, column=4, padx=(8, 0), sticky="e")
        tk.Button(frm, text="读取角色", command=self.reload_bundles).grid(row=1, column=5, padx=(8, 0), sticky="e")

        tk.Label(
            frm,
            text="示例：E:\\game\\steam\\steamapps\\common\\manosaba_game",
            fg="#666",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(0, 8))

        # bundle 列表
        tk.Label(frm, text="角色 bundle（可多选）：").grid(row=3, column=0, sticky="w")

        list_frame = tk.Frame(frm)
        # 列表区域左右留白，避免与其他内容硬对齐。
        list_frame.grid(row=4, column=0, columnspan=6, sticky="nsew", padx=(10, 10))
        frm.rowconfigure(4, weight=1)
        frm.columnconfigure(0, weight=1)

        # 用 Canvas + Frame 实现可滚动 checkbox 列表。
        self.bundle_canvas = tk.Canvas(list_frame, highlightthickness=0, bg="white")
        self.bundle_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.bundle_canvas.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.bundle_canvas.configure(yscrollcommand=sb.set)

        self.bundle_inner = tk.Frame(self.bundle_canvas, bg="white")
        # 在可滚动容器内部再留一点左右边距。
        self.bundle_window = self.bundle_canvas.create_window((10, 0), window=self.bundle_inner, anchor="nw")

        def _on_inner_configure(_event) -> None:
            self.bundle_canvas.configure(scrollregion=self.bundle_canvas.bbox("all"))

        def _on_canvas_configure(event) -> None:
            self.bundle_canvas.itemconfigure(self.bundle_window, width=max(event.width - 20, 0))

        def _on_mousewheel(event) -> None:
            # Windows: event.delta 通常为 120 的倍数。
            self.bundle_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event) -> None:
            self.bundle_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event) -> None:
            self.bundle_canvas.unbind_all("<MouseWheel>")

        self.bundle_inner.bind("<Configure>", _on_inner_configure)
        self.bundle_canvas.bind("<Configure>", _on_canvas_configure)
        self.bundle_canvas.bind("<Enter>", _bind_mousewheel)
        self.bundle_canvas.bind("<Leave>", _unbind_mousewheel)

        btn_frame = tk.Frame(frm)
        btn_frame.grid(row=5, column=0, columnspan=6, sticky="w", pady=(8, 8))
        tk.Button(btn_frame, text="全选", command=self.select_all).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="取消全选", command=self.clear_selection).pack(side=tk.LEFT, padx=(8, 0))

        # 选项
        options_frame = tk.Frame(frm)
        options_frame.grid(row=6, column=0, columnspan=6, sticky="we", pady=(6, 0))
        options_frame.columnconfigure(1, weight=1)

        tk.Checkbutton(options_frame, text="测试模式（每个角色导出前3张）", variable=self.test_mode_var).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )

        tk.Label(options_frame, text="输出目录：").grid(row=1, column=0, sticky="w")
        tk.Entry(options_frame, textvariable=self.output_dir_var).grid(row=1, column=1, columnspan=2, sticky="we")
        tk.Button(options_frame, text="浏览...", command=self.choose_output_dir).grid(row=1, column=3, padx=(8, 0))

        # 操作
        self.export_btn = tk.Button(frm, text="开始导出", command=self.start_export, height=2)
        self.export_btn.grid(row=7, column=0, sticky="w", pady=(12, 6))
        tk.Label(frm, textvariable=self.status_var, fg="#005a9c", anchor="w", justify="left").grid(
            row=8, column=0, columnspan=6, sticky="we"
        )

    def choose_game_root(self) -> None:
        path = filedialog.askdirectory(title="选择游戏根目录")
        if not path:
            return
        self.game_root_var.set(path)
        self.reload_bundles()

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_var.set(path)

    def reload_bundles(self) -> None:
        game_root = self.game_root_var.get().strip().strip('"')
        characters_dir, err = resolve_characters_dir_from_game_root(game_root)
        for child in self.bundle_inner.winfo_children():
            child.destroy()
        self.bundle_names = []
        self.bundle_vars = {}

        if err:
            self.status_var.set(f"路径无效：{err}")
            messagebox.showerror("路径错误", f"{err}\n\n示例：E:\\game\\steam\\steamapps\\common\\manosaba_game")
            return

        bundles = sorted(p.stem for p in characters_dir.glob("*.bundle"))
        self.bundle_names = bundles
        for name in bundles:
            var = tk.BooleanVar(value=False)
            self.bundle_vars[name] = var
            cb = tk.Checkbutton(
                self.bundle_inner,
                text=name,
                variable=var,
                anchor="w",
                bg="white",
                activebackground="white",
                highlightthickness=0,
                bd=0,
            )
            cb.pack(fill=tk.X, anchor="w", padx=(6, 6), pady=1)

        self.status_var.set(f"已读取 {len(bundles)} 个角色：{characters_dir}")

    def select_all(self) -> None:
        for var in self.bundle_vars.values():
            var.set(True)

    def clear_selection(self) -> None:
        for var in self.bundle_vars.values():
            var.set(False)

    def start_export(self) -> None:
        if self.export_thread and self.export_thread.is_alive():
            messagebox.showinfo("导出中", "当前已有导出任务在运行，请等待完成。")
            return

        game_root = self.game_root_var.get().strip().strip('"')
        output_dir = self.output_dir_var.get().strip().strip('"')

        if not game_root:
            messagebox.showwarning("缺少路径", "请先输入或选择游戏根目录。")
            return
        if not output_dir:
            messagebox.showwarning("缺少路径", "请先输入或选择输出目录。")
            return

        selected_chars = [name for name, var in self.bundle_vars.items() if var.get()]
        if not selected_chars:
            messagebox.showwarning("未选择角色", "请至少选择一个角色 bundle。")
            return

        args = Namespace(
            game_root=game_root,
            output_dir=output_dir,
            test="__ALL__" if self.test_mode_var.get() else None,
            character=None,
            characters=selected_chars,
            verbose=False,
            progress_callback=self._on_progress_event,
        )

        self.status_var.set(f"开始导出：{', '.join(selected_chars)}")
        self.export_btn.configure(state=tk.DISABLED)
        self.export_thread = threading.Thread(target=self._run_export_worker, args=(args,), daemon=True)
        self.export_thread.start()
        self.root.after(100, self._poll_progress)

    def _run_export_worker(self, args: Namespace) -> None:
        try:
            run_pipeline(args)
        except Exception as exc:
            self.progress_queue.put({"event": "error", "message": str(exc)})

    def _on_progress_event(self, event: dict) -> None:
        self.progress_queue.put(event)

    def _poll_progress(self) -> None:
        while True:
            try:
                event = self.progress_queue.get_nowait()
            except queue.Empty:
                break

            et = event.get("event")
            if et == "combo_exported":
                total = event.get("exported_total", 0)
                ch = event.get("character", "")
                combo = event.get("combo", "")
                self.status_var.set(f"已导出 {total} 张（{ch}/{combo}）")
            elif et == "character_start":
                ch = event.get("character", "")
                self.status_var.set(f"正在处理角色：{ch}")
            elif et == "done":
                exported = event.get("exported", 0)
                skipped = event.get("skipped", 0)
                self.status_var.set(f"导出完成：导出 {exported} 张，跳过 {skipped} 张。")
                self.export_btn.configure(state=tk.NORMAL)
                messagebox.showinfo("完成", f"导出已完成。\n导出 {exported} 张，跳过 {skipped} 张。")
            elif et == "error":
                msg = event.get("message", "未知错误")
                self.status_var.set(f"导出失败：{msg}")
                self.export_btn.configure(state=tk.NORMAL)
                messagebox.showerror("导出失败", msg)

        if self.export_thread and self.export_thread.is_alive():
            self.root.after(100, self._poll_progress)
        else:
            # 兜底恢复按钮，避免异常情况下按钮长时间不可用。
            self.export_btn.configure(state=tk.NORMAL)


def main() -> None:
    root = tk.Tk()
    ExporterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
