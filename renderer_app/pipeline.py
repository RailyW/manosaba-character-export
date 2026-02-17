"""渲染主流程模块。

该模块是拆分后的“业务编排层”：
- 读取 bundle
- 解析组合表达式
- 合并白名单
- 执行渲染合成
- 输出图片、trace、report

注意：本文件逻辑保持与原 `convert_image.py` 一致，仅做结构化拆分。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Set

import UnityPy

from .bundle_loader import load_bundle_character
from .compositor import compose_active_renderers
from .expression import evaluate_expression, resolve_go_path
from .models import RendererEntry
from .simple_mode import extract_simple_mode_sprites
from .utils import sanitize_filename
from .whitelist import get_whitelist_roots


def resolve_characters_dir_from_game_root(game_root: str) -> tuple[Path | None, str | None]:
    """从游戏根目录解析 characters 目录，并做基础校验。

    校验规则：
    1. 游戏根目录必须存在；
    2. 拼接后的 characters 目录必须存在；
    3. characters 目录下至少包含一个 .bundle 文件。
    """

    if not game_root:
        return None, "未输入游戏根目录。"

    root_path = Path(game_root)
    if not root_path.exists() or not root_path.is_dir():
        return None, f"游戏根目录不存在或不是文件夹：{root_path}"

    characters_path = (
        root_path
        / "manosaba_Data"
        / "StreamingAssets"
        / "aa"
        / "StandaloneWindows64"
        / "naninovel-characters_assets_naninovel"
        / "characters"
    )
    if not characters_path.exists() or not characters_path.is_dir():
        return None, f"characters 目录不存在：{characters_path}"

    if not any(characters_path.glob("*.bundle")):
        return None, f"characters 目录下未找到 .bundle 文件：{characters_path}"

    return characters_path, None


def run_pipeline(args) -> None:
    """执行完整渲染流水线。"""

    def log(msg: str) -> None:
        print(msg)

    def vlog(msg: str) -> None:
        if args.verbose:
            print(msg)

    resolved_root, root_err = resolve_characters_dir_from_game_root(getattr(args, "game_root", ""))
    if root_err:
        print(f"[错误] {root_err}")
        print("[示例] 请输入类似路径：E:\\game\\steam\\steamapps\\common\\manosaba_game")
        return

    root = resolved_root
    out_root = Path(args.output_dir)
    trace_root = out_root / "render_trace"

    # 与原脚本一致：每次运行前清空 output 目录。
    if out_root.exists():
        shutil.rmtree(out_root)
        log(f"[清理] 已清空输出目录：{out_root}")
    out_root.mkdir(parents=True, exist_ok=True)
    trace_root.mkdir(parents=True, exist_ok=True)

    report = {"characters_root": str(root), "output_root": str(out_root), "characters": {}}

    all_bundles = sorted(root.glob("*.bundle"))
    if args.character:
        target = str(args.character).strip().lower()
        all_bundles = [b for b in all_bundles if b.stem.lower() == target]
        if not all_bundles:
            log(f"[提示] 未找到指定角色：{target}")
    elif args.test and args.test != "__ALL__":
        target = str(args.test).strip().lower()
        all_bundles = [b for b in all_bundles if b.stem.lower() == target]
        if not all_bundles:
            log(f"[提示] 未找到指定测试角色：{target}")

    for bundle in all_bundles:
        cname = bundle.stem
        log(f"[角色] 开始处理：{cname}")

        data, err = load_bundle_character(bundle)
        if err:
            # 常规结构失败后，尝试 simple_mode 分支。
            env = UnityPy.load(str(bundle))
            simple_records, actor_name, simple_err = extract_simple_mode_sprites(env)
            if simple_records:
                c_report = {
                    "status": "ok",
                    "bundle": bundle.name,
                    "mode": "simple_mode",
                    "exported": 0,
                    "skipped": 0,
                    "unknown_tokens": {},
                    "missing_paths": {},
                    "missing_whitelist_paths": {},
                    "errors": {},
                    "offset_source": "simple_mode: MonoBehaviour.sprites",
                }

                export_records = simple_records
                # 在测试模式下，simple_mode 也遵循“仅前 3 项”的节流规则。
                if args.test:
                    export_records = export_records[:3]

                for rec in export_records:
                    combo_name = rec["name"]
                    out_path = out_root / cname / (sanitize_filename(combo_name) + ".png")
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    rec["image"].save(out_path)

                    trace = [
                        {
                            "path": f"{actor_name}/{rec['name']}",
                            "sprite": rec["name"],
                            "write_mask_ref": 0,
                            "read_mask_ref": 0,
                            "blend_mode": "normal",
                            "write_color": True,
                            "reason": "simple_mode: direct sprite export",
                        }
                    ]
                    trace_path = trace_root / cname
                    trace_path.mkdir(parents=True, exist_ok=True)
                    (trace_path / f"{sanitize_filename(combo_name)}.json").write_text(
                        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    c_report["exported"] += 1

                report["characters"][cname] = c_report
                log(f"  [完成/simple_mode] 导出 {c_report['exported']} 张，跳过 {c_report['skipped']} 张")
                continue

            report["characters"][cname] = {"status": "skipped", "reason": f"{err}; simple_mode: {simple_err}"}
            log(f"  [跳过] {err}; simple_mode: {simple_err}")
            continue

        comp_map: Dict[str, str] = data["comp_map"]
        default_expr: str = data["default_expr"]
        renderers: List[RendererEntry] = data["renderers"]
        all_go_paths: Set[str] = data["all_go_paths"]

        # 组合生成规则：default + 每个 composition key 的 default__key。
        combos: Dict[str, str] = {"default": default_expr}
        for k in sorted(comp_map.keys()):
            combos[f"default__{k}"] = f"{default_expr},{k}"
        if args.test:
            keep = list(combos.keys())[:3]
            combos = {k: combos[k] for k in keep}
            vlog(f"  [测试] 仅导出：{keep}")

        # 保留原有“自动补 Body”逻辑（若存在 /Body 或 Body 根节点）。
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

            # 自动补 Body：当 body_parent 不在禁用列表里，强插默认 Body 值。
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

            # 合并白名单路径。
            whitelisted_roots: List[str] = []
            missing_whitelisted_roots: List[str] = []
            for wp in get_whitelist_roots(cname, combo_name):
                mp = resolve_go_path(wp, all_go_paths)
                if mp:
                    whitelisted_roots.append(mp)
                    selected_roots.append(mp)
                else:
                    missing_whitelisted_roots.append(wp)

            # 去重但保留顺序，避免重复渲染同一路径。
            selected_roots = list(dict.fromkeys(selected_roots))

            # 行为保持：unknown/missing 都会导致该组合跳过。
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

            # 激活规则：只要渲染路径等于 root，或位于 root 的子树下，即视为激活。
            active = [
                r
                for r in renderers
                if any(r.go_path == rootp or r.go_path.startswith(rootp + "/") for rootp in selected_roots)
            ]

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
