"""白名单规则模块。

该模块用于维护“强制激活路径”规则：
即使表达式未选中某些关键层，也可通过白名单补入 selected_roots。
"""

from __future__ import annotations

from typing import Dict, List


def get_whitelist_roots(character_name: str, combo_name: str) -> List[str]:
    """返回需要强制激活的 GO 路径白名单。

    参数：
    - character_name: 角色名（通常是 bundle 文件名去扩展名）
    - combo_name: 当前组合名，预留给未来按表情做细粒度控制

    返回：
    - 需要追加到 selected_roots 的路径列表。
    """

    _ = combo_name  # 预留扩展：未来可按 combo_name 做条件白名单
    rules: Dict[str, List[str]] = {
        "anan": ["AnAn/Angle01/Head/HeadBase"],
        "nanoka": [
            "Nanoka/Angle01/Body/Body01",
            "Nanoka/Angle01/Head/Head01/HeadBase01",
        ],
    }
    return rules.get(character_name.lower(), [])
