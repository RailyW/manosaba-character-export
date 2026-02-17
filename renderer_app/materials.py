"""材质分类模块。

用于将 SpriteRenderer 材质名映射为统一的渲染决策（遮罩读写/混合模式/是否写色）。
"""

from __future__ import annotations

from typing import List

from .constants import MAT_MASK_RE, MAT_MASKED_RE
from .models import LayerDecision


def classify_by_material(materials: List[str]) -> LayerDecision:
    """根据材质名生成层渲染决策。

    规则保持与原脚本一致：
    - 通过材质名关键字判断 blend_mode；
    - 通过 #Mask_RefX 判断“写遮罩”；
    - 通过 #Masked_RefX 判断“读遮罩”；
    - 默认写颜色。
    """

    primary = materials[0] if materials else "Naninovel_Default"
    low = primary.lower()

    if "multiply" in low:
        blend = "multiply"
    elif "overlay" in low:
        blend = "overlay"
    elif "softlight" in low:
        blend = "softlight"
    else:
        blend = "normal"

    m = MAT_MASK_RE.search(primary)
    if m:
        ref = int(m.group("ref"))
        # 保持原逻辑：Mask_Ref 层既写 mask 也写颜色。
        return LayerDecision(ref, 0, blend, True, f"{primary} => write_mask ref{ref} + color {blend}")

    m = MAT_MASKED_RE.search(primary)
    if m:
        ref = int(m.group("ref"))
        return LayerDecision(0, ref, blend, True, f"{primary} => read_mask ref{ref} + color {blend}")

    return LayerDecision(0, 0, blend, True, f"{primary} => color {blend}")
