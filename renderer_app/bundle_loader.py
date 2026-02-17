"""Unity bundle 读取模块。

职责：
1. 从 bundle 中读取角色配置（compositionMap/defaultAppearance）；
2. 收集所有 SpriteRenderer 的渲染元数据；
3. 构建完整 GO 路径，供后续表达式解析与激活筛选使用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import UnityPy

from .expression import build_comp_map
from .models import RendererEntry, TransformNode


def world_pos(transform_id: int, trans_map: Dict[int, TransformNode], cache: Dict[int, Tuple[float, float]]) -> Tuple[float, float]:
    """递归计算 Transform 的世界坐标（仅平移）。

    说明：
    - 原脚本只处理二维位置累计，不处理旋转/缩放；
    - 与历史行为一致，保证输出不变。
    """

    if transform_id in cache:
        return cache[transform_id]
    node = trans_map.get(transform_id)
    if not node:
        cache[transform_id] = (0.0, 0.0)
        return (0.0, 0.0)
    px, py = world_pos(node.father_transform_id, trans_map, cache) if node.father_transform_id else (0.0, 0.0)
    cache[transform_id] = (px + node.local_x, py + node.local_y)
    return cache[transform_id]


def world_to_pixel(x: float, y: float, ppu: float) -> Tuple[float, float]:
    """将世界坐标转换为像素坐标。

    y 取反与原脚本一致（Unity 上向上，图像坐标向下）。
    """

    return x * ppu, -y * ppu


def load_bundle_character(bundle_path: Path):
    """加载单个角色 bundle。

    返回：
    - 成功: (data, None)
      data 包含 comp_map/default_expr/renderers/all_go_paths
    - 失败: (None, 错误字符串)
    """

    env = UnityPy.load(str(bundle_path))
    obj_by_id = {o.path_id: o for o in env.objects}

    config_tt = None
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            tt = o.read_typetree()
        except Exception:
            continue
        if isinstance(tt, dict) and "compositionMap" in tt and "defaultAppearance" in tt:
            config_tt = tt
            break
    if not config_tt:
        return None, "未找到 compositionMap/defaultAppearance"

    comp_map = build_comp_map(config_tt)
    default_expr = str(config_tt.get("defaultAppearance", "")).strip()
    if not default_expr:
        return None, "defaultAppearance 为空"

    go_name: Dict[int, str] = {}
    go_transform: Dict[int, int] = {}
    go_renderer: Dict[int, int] = {}
    trans_map: Dict[int, TransformNode] = {}
    trans_to_go: Dict[int, int] = {}

    # 第一次遍历：建立 GameObject 与组件索引。
    for o in env.objects:
        if o.type.name != "GameObject":
            continue
        tt = o.read_typetree()
        gpid = o.path_id
        go_name[gpid] = tt.get("m_Name", f"GO_{gpid}")
        for c in tt.get("m_Component", []) or []:
            cpid = c["component"]["m_PathID"]
            co = obj_by_id.get(cpid)
            if not co:
                continue
            if co.type.name == "Transform":
                go_transform[gpid] = cpid
                trans_to_go[cpid] = gpid
            elif co.type.name == "SpriteRenderer":
                go_renderer[gpid] = cpid

    # 第二次遍历：读取 Transform 层级与本地坐标。
    for o in env.objects:
        if o.type.name != "Transform":
            continue
        tt = o.read_typetree()
        trans_map[o.path_id] = TransformNode(
            father_transform_id=tt["m_Father"]["m_PathID"],
            local_x=float(tt["m_LocalPosition"]["x"]),
            local_y=float(tt["m_LocalPosition"]["y"]),
        )

    go_path_cache: Dict[int, str] = {}

    def go_full_path(gpid: int) -> str:
        """递归构建 GameObject 完整路径。"""

        if gpid in go_path_cache:
            return go_path_cache[gpid]
        name = go_name.get(gpid, f"GO_{gpid}")
        tid = go_transform.get(gpid, 0)
        father_tid = trans_map.get(tid).father_transform_id if tid and tid in trans_map else 0
        if father_tid and father_tid in trans_to_go:
            p = go_full_path(trans_to_go[father_tid]) + "/" + name
        else:
            p = name
        go_path_cache[gpid] = p
        return p

    sprite_cache: Dict[int, dict] = {}
    renderers: List[RendererEntry] = []
    world_cache: Dict[int, Tuple[float, float]] = {}

    # 第三次：收集所有 SpriteRenderer 条目。
    for gpid, srpid in go_renderer.items():
        sr_obj = obj_by_id.get(srpid)
        if not sr_obj:
            continue
        sr_tt = sr_obj.read_typetree()
        spid = sr_tt.get("m_Sprite", {}).get("m_PathID", 0)
        if not spid or spid not in obj_by_id:
            continue

        if spid not in sprite_cache:
            s_obj = obj_by_id[spid]
            st = s_obj.read_typetree()
            sread = s_obj.read()
            sprite_cache[spid] = {
                "name": st.get("m_Name") or f"Sprite_{spid}",
                "w": int(round(float(st["m_Rect"]["width"]))),
                "h": int(round(float(st["m_Rect"]["height"]))),
                "pivot_x": float(st["m_Pivot"]["x"]),
                "pivot_y": float(st["m_Pivot"]["y"]),
                "ppu": float(st.get("m_PixelsToUnits", 100.0) or 100.0),
                "img": sread.image.convert("RGBA"),
            }
        s = sprite_cache[spid]

        mats: List[str] = []
        for m in sr_tt.get("m_Materials", []) or []:
            mpid = m.get("m_PathID", 0)
            mo = obj_by_id.get(mpid)
            if mo and mo.type.name == "Material":
                try:
                    mats.append(mo.read_typetree().get("m_Name", f"Material_{mpid}"))
                except Exception:
                    mats.append(f"Material_{mpid}")

        color_tt = sr_tt.get("m_Color", {})
        color = (
            float(color_tt.get("r", 1.0)),
            float(color_tt.get("g", 1.0)),
            float(color_tt.get("b", 1.0)),
            float(color_tt.get("a", 1.0)),
        )

        tid = go_transform.get(gpid, 0)
        wx, wy = world_pos(tid, trans_map, world_cache) if tid else (0.0, 0.0)
        renderers.append(
            RendererEntry(
                go_path=go_full_path(gpid),
                go_name=go_name.get(gpid, ""),
                sorting_layer_id=int(sr_tt.get("m_SortingLayerID", 0)),
                sorting_order=int(sr_tt.get("m_SortingOrder", 0)),
                world_x=wx,
                world_y=wy,
                sprite_name=s["name"],
                image=s["img"],
                width=s["w"],
                height=s["h"],
                pivot_x=s["pivot_x"],
                pivot_y=s["pivot_y"],
                ppu=s["ppu"],
                materials=mats,
                color=color,
            )
        )

    all_go_paths = {r.go_path for r in renderers}
    return {"comp_map": comp_map, "default_expr": default_expr, "renderers": renderers, "all_go_paths": all_go_paths}, None
