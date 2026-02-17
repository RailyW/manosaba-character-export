"""渲染合成模块。

本模块负责把“已激活的渲染条目”实际合成为一张 RGBA 图：
1. 选择基准层（Body）建立统一坐标系；
2. 按 sorting 规则排队；
3. 执行遮罩写入/读取；
4. 执行 normal/multiply/overlay/softlight 混合；
5. 记录 render_trace。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image

from .bundle_loader import world_to_pixel
from .image_ops import apply_color_tint, apply_mask_to_patch, blend_patch, write_to_mask
from .materials import classify_by_material
from .models import RendererEntry


def pick_body_renderer(renderers: List[RendererEntry]) -> Optional[RendererEntry]:
    """选择 Body 参考层。

    约定：
    - 优先 GO 名称为 Body 或路径以 /Body 结尾的节点；
    - 若未找到，回退到第一层（保持原脚本行为）。
    """

    for r in renderers:
        if r.go_name == "Body" or r.go_path.endswith("/Body"):
            return r
    return renderers[0] if renderers else None


def compose_active_renderers(active_renderers: List[RendererEntry], whitelisted_paths: Optional[Set[str]] = None):
    """把激活条目合成为画布图像并输出 trace。

    参数：
    - active_renderers: 当前组合中真正参与渲染的层列表
    - whitelisted_paths: 由白名单注入的路径集合，用于在 trace reason 里标记

    返回：
    - (canvas, None, placements, trace) 成功
    - (None, 错误信息, {}, []) 失败
    """

    if not active_renderers:
        return None, "没有可渲染图层", {}, []

    whitelisted_paths = whitelisted_paths or set()

    body = pick_body_renderer(active_renderers)
    if not body:
        return None, "找不到 Body 参考层", {}, []

    # 以 Body 的世界坐标与 pivot 计算“Body 左上角”的像素坐标，作为统一参考原点。
    bx, by = world_to_pixel(body.world_x, body.world_y, body.ppu)
    body_tl_x = bx - body.pivot_x * body.width
    body_tl_y = by - body.pivot_y * body.height

    # 先计算每层在参考坐标系中的放置位置，并统计包围盒范围。
    placements: Dict[str, Tuple[int, int]] = {}
    min_x = min_y = 0
    max_x = max_y = 0
    for r in active_renderers:
        rx, ry = world_to_pixel(r.world_x, r.world_y, r.ppu)
        tl_x = int(round(rx - r.pivot_x * r.width - body_tl_x))
        tl_y = int(round(ry - r.pivot_y * r.height - body_tl_y))
        placements[r.go_path] = (tl_x, tl_y)
        min_x = min(min_x, tl_x)
        min_y = min(min_y, tl_y)
        max_x = max(max_x, tl_x + r.width)
        max_y = max(max_y, tl_y + r.height)

    shift_x, shift_y = -min_x, -min_y
    cw, ch = max_x - min_x, max_y - min_y
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

    # 多个遮罩槽并存：key 为 ref 编号，value 为二维 alpha 浮点缓冲区。
    mask_buffers: Dict[int, np.ndarray] = {}
    trace: List[dict] = []

    # 排序规则保持与原脚本一致：sorting_layer_id -> sorting_order -> go_path。
    queue = sorted(active_renderers, key=lambda r: (r.sorting_layer_id, r.sorting_order, r.go_path))
    for r in queue:
        dec = classify_by_material(r.materials)
        x, y = placements[r.go_path]
        px, py = x + shift_x, y + shift_y
        img = apply_color_tint(r.image, r.color)

        # 1) 如需写遮罩，先把当前 alpha 写入对应槽位。
        if dec.write_mask_ref > 0:
            buf = mask_buffers.setdefault(dec.write_mask_ref, np.zeros((ch, cw), dtype=np.float32))
            write_to_mask(buf, img, px, py)

        # 2) 如需读遮罩，则用目标槽位裁剪当前图层 alpha。
        if dec.read_mask_ref > 0:
            buf = mask_buffers.get(dec.read_mask_ref)
            if buf is None:
                # 未找到目标遮罩时，行为保持为“整层透明”。
                img = Image.new("RGBA", img.size, (0, 0, 0, 0))
            else:
                img = apply_mask_to_patch(img, buf, px, py)

        # 3) 若该层不写颜色，则只写 trace，不上屏。
        if not dec.write_color:
            trace.append(
                {
                    "path": r.go_path,
                    "sprite": r.sprite_name,
                    "write_mask_ref": dec.write_mask_ref,
                    "read_mask_ref": dec.read_mask_ref,
                    "blend_mode": dec.blend_mode,
                    "write_color": dec.write_color,
                    "reason": dec.reason,
                }
            )
            continue

        # 4) 写颜色：normal 用 alpha_composite；其它模式走自定义 blend_patch。
        if dec.blend_mode == "normal":
            canvas.alpha_composite(img, (px, py))
        elif dec.blend_mode in ("multiply", "overlay", "softlight"):
            blend_patch(canvas, img, px, py, dec.blend_mode)
        else:
            canvas.alpha_composite(img, (px, py))

        reason = dec.reason
        if r.go_path in whitelisted_paths:
            reason = f"{reason} | whitelisted"

        trace.append(
            {
                "path": r.go_path,
                "sprite": r.sprite_name,
                "write_mask_ref": dec.write_mask_ref,
                "read_mask_ref": dec.read_mask_ref,
                "blend_mode": dec.blend_mode,
                "write_color": dec.write_color,
                "reason": reason,
            }
        )

    return canvas, None, placements, trace
