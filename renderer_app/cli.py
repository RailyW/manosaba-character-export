"""命令行参数解析模块。"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    参数定义与原 `convert_image.py` 保持一致，确保外部使用方式不变。
    """

    parser = argparse.ArgumentParser(description="严格按 bundle 材质语义渲染角色立绘")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument(
        "--test",
        nargs="?",
        const="__ALL__",
        default=None,
        metavar="CHARACTER",
        help="测试模式。可选指定角色名：--test 或 --test yuki",
    )
    parser.add_argument(
        "--character",
        default=None,
        metavar="CHARACTER",
        help="仅导出指定角色的全部图像（非测试模式）。例如：--character yuki",
    )
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    return parser


def parse_args() -> argparse.Namespace:
    """解析命令行参数并返回命名空间对象。"""

    return build_parser().parse_args()
