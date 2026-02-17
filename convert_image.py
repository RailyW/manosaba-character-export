from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import UnityPy
from PIL import Image


TOKEN_SPLIT_RE = re.compile(r"\s*,\s*")
OP_RE = re.compile(r"^(?P<layer>.+?)(?P<op>[>+\-])(?P<value>[A-Za-z0-9_]+)?$")
MAT_MASK_RE = re.compile(r"#Mask_Ref(?P<ref>\d+)", re.IGNORECASE)
MAT_MASKED_RE = re.compile(r"#Masked_Ref(?P<ref>\d+)", re.IGNORECASE)


@dataclass
class TransformNode:
    father_transform_id: int
    local_x: float
    local_y: float


@dataclass
class RendererEntry:
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
    write_mask_ref: int
    read_mask_ref: int
    blend_mode: str  # normal | multiply | overlay | softlight
    write_color: bool
    reason: str


def parse_tokens(expr: str) -> List[str]:
    return [t.strip() for t in TOKEN_SPLIT_RE.split(expr.strip()) if t.strip()]


def build_comp_map(tt: dict) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in tt.get("compositionMap", []) or []:
        if isinstance(item, dict):
            k = item.get("Key")
            v = item.get("Composition")
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    return out


def evaluate_expression(expr: str, comp_map: Dict[str, str]) -> Tuple[Dict[str, List[str]], List[str], Set[str]]:
    selections: Dict[str, List[str]] = {}
    unknown: List[str] = []
    disabled_layers: Set[str] = set()

    def eval_tokens(tokens: List[str], visiting: Set[str]) -> None:
        for token in tokens:
            m = OP_RE.match(token)
            if m:
                layer = m.group("layer")
                op = m.group("op")
                value = m.group("value")
                if op == "-":
                    disabled_layers.add(layer)
                    selections.pop(layer, None)
                    continue
                if not value:
                    continue
                if op == ">":
                    selections[layer] = [value]
                elif op == "+":
                    cur = selections.setdefault(layer, [])
                    if value not in cur:
                        cur.append(value)
                continue

            if token in comp_map:
                if token in visiting:
                    continue
                visiting.add(token)
                eval_tokens(parse_tokens(comp_map[token]), visiting)
                visiting.remove(token)
            else:
                unknown.append(token)

    eval_tokens(parse_tokens(expr), set())
    return selections, unknown, disabled_layers


def world_pos(transform_id: int, trans_map: Dict[int, TransformNode], cache: Dict[int, Tuple[float, float]]) -> Tuple[float, float]:
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
    return x * ppu, -y * ppu


def resolve_go_path(path_token: str, all_go_paths: Set[str]) -> Optional[str]:
    if path_token in all_go_paths:
        return path_token
    suffix = "/" + path_token
    hits = [p for p in all_go_paths if p.endswith(suffix)]
    return hits[0] if len(hits) == 1 else None


def get_whitelist_roots(character_name: str, combo_name: str) -> List[str]:
    """返回需要强制激活的 GO 路径（白名单）。"""
    _ = combo_name  # 预留：后续可按表情/组合名做条件白名单
    rules: Dict[str, List[str]] = {
        "anan": ["AnAn/Angle01/Head/HeadBase"],
        "nanoka": [
            "Nanoka/Angle01/Body/Body01",
            "Nanoka/Angle01/Head/Head01/HeadBase01",
        ],
    }
    return rules.get(character_name.lower(), [])


def classify_by_material(materials: List[str]) -> LayerDecision:
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
        # 关键修正：Mask_Ref 不等于仅遮罩。它通常仍然需要输出颜色。
        return LayerDecision(ref, 0, blend, True, f"{primary} => write_mask ref{ref} + color {blend}")

    m = MAT_MASKED_RE.search(primary)
    if m:
        ref = int(m.group("ref"))
        return LayerDecision(0, ref, blend, True, f"{primary} => read_mask ref{ref} + color {blend}")

    return LayerDecision(0, 0, blend, True, f"{primary} => color {blend}")


def apply_color_tint(img: Image.Image, color: Tuple[float, float, float, float]) -> Image.Image:
    r, g, b, a = color
    if abs(r - 1) < 1e-6 and abs(g - 1) < 1e-6 and abs(b - 1) < 1e-6 and abs(a - 1) < 1e-6:
        return img
    arr = np.asarray(img).astype(np.float32)
    arr[:, :, 0] *= r
    arr[:, :, 1] *= g
    arr[:, :, 2] *= b
    arr[:, :, 3] *= a
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _blend_rgb(base_rgb: np.ndarray, fg_rgb: np.ndarray, mode: str) -> np.ndarray:
    if mode == "multiply":
        return base_rgb * fg_rgb
    if mode == "overlay":
        return np.where(base_rgb <= 0.5, 2 * base_rgb * fg_rgb, 1 - 2 * (1 - base_rgb) * (1 - fg_rgb))
    if mode == "softlight":
        return (1 - 2 * fg_rgb) * (base_rgb**2) + 2 * fg_rgb * base_rgb
    return fg_rgb


def blend_patch(canvas: Image.Image, patch: Image.Image, x: int, y: int, mode: str) -> None:
    cw, ch = canvas.size
    pw, ph = patch.size
    left, top = max(0, x), max(0, y)
    right, bottom = min(cw, x + pw), min(ch, y + ph)
    if left >= right or top >= bottom:
        return

    src = patch.crop((left - x, top - y, right - x, bottom - y)).convert("RGBA")
    dst = canvas.crop((left, top, right, bottom)).convert("RGBA")
    s = np.asarray(src).astype(np.float32) / 255.0
    d = np.asarray(dst).astype(np.float32) / 255.0
    sa = s[:, :, 3:4]
    da = d[:, :, 3:4]
    brgb = _blend_rgb(d[:, :, :3], s[:, :, :3], mode)
    out_rgb = d[:, :, :3] * (1 - sa) + brgb * sa
    out_a = da + sa * (1 - da)
    out = np.concatenate([np.clip(out_rgb, 0, 1), np.clip(out_a, 0, 1)], axis=2)
    canvas.paste(Image.fromarray((out * 255).astype(np.uint8), "RGBA"), (left, top))


def write_to_mask(mask_canvas: np.ndarray, patch: Image.Image, x: int, y: int) -> None:
    alpha = np.asarray(patch.getchannel("A")).astype(np.float32) / 255.0
    pw, ph = patch.size
    mh, mw = mask_canvas.shape
    left, top = max(0, x), max(0, y)
    right, bottom = min(mw, x + pw), min(mh, y + ph)
    if left >= right or top >= bottom:
        return
    sl, st = left - x, top - y
    sr, sb = sl + (right - left), st + (bottom - top)
    mask_canvas[top:bottom, left:right] = np.maximum(mask_canvas[top:bottom, left:right], alpha[st:sb, sl:sr])


def apply_mask_to_patch(patch: Image.Image, mask_canvas: np.ndarray, x: int, y: int) -> Image.Image:
    alpha = np.asarray(patch.getchannel("A")).astype(np.float32) / 255.0
    out_alpha = np.zeros_like(alpha)
    pw, ph = patch.size
    mh, mw = mask_canvas.shape
    left, top = max(0, x), max(0, y)
    right, bottom = min(mw, x + pw), min(mh, y + ph)
    if left < right and top < bottom:
        sl, st = left - x, top - y
        sr, sb = sl + (right - left), st + (bottom - top)
        out_alpha[st:sb, sl:sr] = alpha[st:sb, sl:sr] * mask_canvas[top:bottom, left:right]
    arr = np.asarray(patch.convert("RGBA")).copy()
    arr[:, :, 3] = np.clip(out_alpha * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def load_bundle_character(bundle_path: Path):
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


def pick_body_renderer(renderers: List[RendererEntry]) -> Optional[RendererEntry]:
    for r in renderers:
        if r.go_name == "Body" or r.go_path.endswith("/Body"):
            return r
    return renderers[0] if renderers else None


def compose_active_renderers(active_renderers: List[RendererEntry], whitelisted_paths: Optional[Set[str]] = None):
    if not active_renderers:
        return None, "没有可渲染图层", {}, []

    whitelisted_paths = whitelisted_paths or set()

    body = pick_body_renderer(active_renderers)
    if not body:
        return None, "找不到 Body 参考层", {}, []

    bx, by = world_to_pixel(body.world_x, body.world_y, body.ppu)
    body_tl_x = bx - body.pivot_x * body.width
    body_tl_y = by - body.pivot_y * body.height

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
    mask_buffers: Dict[int, np.ndarray] = {}
    trace: List[dict] = []

    queue = sorted(active_renderers, key=lambda r: (r.sorting_layer_id, r.sorting_order, r.go_path))
    for r in queue:
        dec = classify_by_material(r.materials)
        x, y = placements[r.go_path]
        px, py = x + shift_x, y + shift_y
        img = apply_color_tint(r.image, r.color)

        if dec.write_mask_ref > 0:
            buf = mask_buffers.setdefault(dec.write_mask_ref, np.zeros((ch, cw), dtype=np.float32))
            write_to_mask(buf, img, px, py)

        if dec.read_mask_ref > 0:
            buf = mask_buffers.get(dec.read_mask_ref)
            if buf is None:
                img = Image.new("RGBA", img.size, (0, 0, 0, 0))
            else:
                img = apply_mask_to_patch(img, buf, px, py)

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


def sanitize_filename(name: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    return s or "unnamed"


def main() -> None:
    parser = argparse.ArgumentParser(description="严格按 bundle 材质语义渲染角色立绘")
    parser.add_argument("--characters-dir", default="resources/characters", help="角色 bundle 目录")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--test", action="store_true", help="测试模式：每角色仅导出 3 张")
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    args = parser.parse_args()

    def log(msg: str) -> None:
        print(msg)

    def vlog(msg: str) -> None:
        if args.verbose:
            print(msg)

    root = Path(args.characters_dir)
    out_root = Path(args.output_dir)
    trace_root = out_root / "render_trace"

    if out_root.exists():
        shutil.rmtree(out_root)
        log(f"[清理] 已清空输出目录：{out_root}")
    out_root.mkdir(parents=True, exist_ok=True)
    trace_root.mkdir(parents=True, exist_ok=True)

    report = {"characters_root": str(root), "output_root": str(out_root), "characters": {}}

    for bundle in sorted(root.glob("*.bundle")):
        cname = bundle.stem
        log(f"[角色] 开始处理：{cname}")

        data, err = load_bundle_character(bundle)
        if err:
            report["characters"][cname] = {"status": "skipped", "reason": err}
            log(f"  [跳过] {err}")
            continue

        comp_map: Dict[str, str] = data["comp_map"]
        default_expr: str = data["default_expr"]
        renderers: List[RendererEntry] = data["renderers"]
        all_go_paths: Set[str] = data["all_go_paths"]

        combos: Dict[str, str] = {"default": default_expr}
        for k in sorted(comp_map.keys()):
            combos[f"default__{k}"] = f"{default_expr},{k}"
        if args.test:
            keep = list(combos.keys())[:3]
            combos = {k: combos[k] for k in keep}
            vlog(f"  [测试] 仅导出：{keep}")

        body_paths = [p for p in all_go_paths if p.endswith("/Body") or p == "Body"]
        body_parent_val = None
        if body_paths:
            bp = sorted(body_paths)[0]
            if "/" in bp:
                body_parent_val = bp.rsplit("/", 1)

        c_report = {
            "status": "ok",
            "bundle": bundle.name,
            "exported": 0,
            "skipped": 0,
            "unknown_tokens": {},
            "missing_paths": {},
            "missing_whitelist_paths": {},
            "errors": {},
            "offset_source": "bundle Transform + SpriteRenderer + Material",
        }

        for combo_name, expr in combos.items():
            selections, unknown, disabled = evaluate_expression(expr, comp_map)

            if body_parent_val:
                parent, val = body_parent_val
                if parent not in disabled:
                    cur = selections.setdefault(parent, [])
                    if val not in cur:
                        cur.insert(0, val)

            selected_roots: List[str] = []
            missing: List[str] = []
            for layer, vals in selections.items():
                for v in vals:
                    rp = f"{layer}/{v}" if layer else v
                    mp = resolve_go_path(rp, all_go_paths)
                    if mp:
                        selected_roots.append(mp)
                    else:
                        missing.append(rp)

            whitelisted_roots: List[str] = []
            missing_whitelisted_roots: List[str] = []
            for wp in get_whitelist_roots(cname, combo_name):
                mp = resolve_go_path(wp, all_go_paths)
                if mp:
                    whitelisted_roots.append(mp)
                    selected_roots.append(mp)
                else:
                    missing_whitelisted_roots.append(wp)

            # 去重但保留顺序
            selected_roots = list(dict.fromkeys(selected_roots))

            if unknown:
                c_report["skipped"] += 1
                c_report["unknown_tokens"][combo_name] = unknown
                continue
            if missing:
                c_report["skipped"] += 1
                c_report["missing_paths"][combo_name] = sorted(set(missing))
                continue

            if missing_whitelisted_roots:
                c_report["missing_whitelist_paths"][combo_name] = sorted(set(missing_whitelisted_roots))

            active = [r for r in renderers if any(r.go_path == rootp or r.go_path.startswith(rootp + "/") for rootp in selected_roots)]
            canvas, cerr, _placements, trace = compose_active_renderers(active, set(whitelisted_roots))
            if canvas is None:
                c_report["skipped"] += 1
                c_report["errors"][combo_name] = cerr
                continue

            out_path = out_root / cname / (sanitize_filename(combo_name) + ".png")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(out_path)

            trace_path = trace_root / cname
            trace_path.mkdir(parents=True, exist_ok=True)
            (trace_path / f"{sanitize_filename(combo_name)}.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            c_report["exported"] += 1
            vlog(f"  [成功] {combo_name} -> {out_path}")

        report["characters"][cname] = c_report
        log(f"  [完成] 导出 {c_report['exported']} 张，跳过 {c_report['skipped']} 张")

    (out_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    total_exported = sum(v.get("exported", 0) for v in report["characters"].values() if isinstance(v, dict))
    total_skipped = sum(v.get("skipped", 0) for v in report["characters"].values() if isinstance(v, dict))
    log(f"[汇总] 总导出 {total_exported} 张，总跳过 {total_skipped} 张")
    log(f"[完成] 报告：{out_root / 'report.json'}")
    log(f"[完成] 渲染追踪：{trace_root}")


if __name__ == "__main__":
    main()
