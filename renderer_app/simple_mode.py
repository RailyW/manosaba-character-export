"""simple_mode 渲染逻辑（独立文件）。

用于处理不含 GameObject/SpriteRenderer/compositionMap 的特殊 bundle，
例如仅在 MonoBehaviour 中通过 sprites 列表给出资源引用的结构。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PIL import Image


def detect_simple_mode_typetree(tt: dict) -> bool:
    """判断 MonoBehaviour typetree 是否符合 simple_mode 结构。"""

    if not isinstance(tt, dict):
        return False
    sprites = tt.get("sprites")
    return isinstance(sprites, list) and len(sprites) > 0


def extract_simple_mode_sprites(env) -> Tuple[Optional[List[dict]], Optional[str], Optional[str]]:
    """从 bundle 中提取 simple_mode 的 sprite 列表。

    返回：
    - records: [{'name': str, 'image': PIL.Image}] 或 None
    - actor_name: 角色名（用于输出目录）
    - err: 错误信息（成功时为 None）
    """

    obj_by_id = {o.path_id: o for o in env.objects}

    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            tt = o.read_typetree()
        except Exception:
            continue
        if not detect_simple_mode_typetree(tt):
            continue

        actor_name = str(tt.get("m_Name", "simple_mode")).strip() or "simple_mode"
        records: List[dict] = []
        for ref in tt.get("sprites", []) or []:
            spid = ref.get("m_PathID", 0) if isinstance(ref, dict) else 0
            so = obj_by_id.get(spid)
            if not so:
                continue
            try:
                st = so.read_typetree()
                sread = so.read()
                name = st.get("m_Name") or f"Sprite_{spid}"
                image: Image.Image = sread.image.convert("RGBA")
                records.append({"name": name, "image": image})
            except Exception:
                continue

        if not records:
            return None, actor_name, "simple_mode: sprites 列表为空或无法读取"
        return records, actor_name, None

    return None, None, "未命中 simple_mode 结构"
