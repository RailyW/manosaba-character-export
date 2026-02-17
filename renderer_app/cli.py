"""命令行参数解析模块。"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    参数定义与原 `convert_image.py` 保持一致，确保外部使用方式不变。
    """

    parser = argparse.ArgumentParser(description="严格按 bundle 材质语义渲染角色立绘")
    parser.add_argument("--characters-dir", default="resources/characters", help="角色 bundle 目录")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--test", action="store_true", help="测试模式：每角色仅导出 3 张")
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    return parser


def parse_args() -> argparse.Namespace:
    """解析命令行参数并返回命名空间对象。"""

    return build_parser().parse_args()
