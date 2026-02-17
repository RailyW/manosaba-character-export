"""程序主入口。

该文件只负责：
1. 解析命令行参数；
2. 调用渲染流水线。

业务细节全部放在 renderer_app 包内，保持入口轻量。
"""

from __future__ import annotations

from renderer_app.cli import parse_args
from renderer_app.pipeline import run_pipeline


def main() -> None:
    """应用启动函数。"""

    args = parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
