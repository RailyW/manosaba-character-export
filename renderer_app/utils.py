"""通用工具函数模块。"""

from __future__ import annotations

import re


def sanitize_filename(name: str) -> str:
    """将任意字符串转换为安全文件名。

    Windows 文件名不允许出现 `\\ / : * ? " < > |`，
    这里统一替换为下划线，保证跨平台写文件稳定。
    """

    s = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return s or "unnamed"
