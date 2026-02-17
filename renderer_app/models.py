"""数据模型定义模块。

本模块只负责声明跨模块共享的数据结构，不承载业务流程。
这样做可以让类型依赖关系清晰，避免循环引用，并提升可读性。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from PIL import Image


@dataclass
class TransformNode:
    """Transform 节点的最小信息。

    字段说明：
    - father_transform_id: 父 Transform 的 path_id，用于递归求世界坐标。
    - local_x/local_y: 本地坐标（Unity 空间）。
    """

    father_transform_id: int
    local_x: float
    local_y: float


@dataclass
class RendererEntry:
    """一个可渲染 SpriteRenderer 条目。

    该结构聚合了渲染所需的全部元数据：路径、排序、坐标、贴图、材质、颜色。
    """

    go_path: str
    go_name: str
    sorting_layer_id: int
    sorting_order: int
    world_x: float
    world_y: float
    sprite_name: str
    image: Image.Image
    width: int
    height: int
    pivot_x: float
    pivot_y: float
    ppu: float
    materials: List[str]
    color: Tuple[float, float, float, float]


@dataclass
class LayerDecision:
    """材质分类后的渲染决策。

    - write_mask_ref: 写入哪个遮罩槽（0 表示不写）
    - read_mask_ref: 从哪个遮罩槽读取（0 表示不读）
    - blend_mode: 混合模式（normal/multiply/overlay/softlight）
    - write_color: 是否写入颜色到画布
    - reason: 追踪日志文本，写入 render_trace 便于排障
    """

    write_mask_ref: int
    read_mask_ref: int
    blend_mode: str
    write_color: bool
    reason: str
