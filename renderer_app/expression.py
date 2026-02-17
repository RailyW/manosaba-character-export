"""组合表达式解析模块。

职责：
1. 将字符串表达式拆分为 token；
2. 展开 compositionMap 引用；
3. 计算每个 layer 的最终选择结果；
4. 提供 GO 路径解析（精确匹配 + 唯一后缀匹配）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .constants import OP_RE, TOKEN_SPLIT_RE


def parse_tokens(expr: str) -> List[str]:
    """按逗号切分表达式 token，并去掉空 token。"""
    return [t.strip() for t in TOKEN_SPLIT_RE.split(expr.strip()) if t.strip()]


def build_comp_map(tt: dict) -> Dict[str, str]:
    """从 typetree 中提取 compositionMap 为 {Key: Composition} 字典。"""
    out: Dict[str, str] = {}
    for item in tt.get("compositionMap", []) or []:
        if isinstance(item, dict):
            k = item.get("Key")
            v = item.get("Composition")
            if isinstance(k, str) and isinstance(v, str):
                out[k] = v
    return out


def evaluate_expression(expr: str, comp_map: Dict[str, str]) -> Tuple[Dict[str, List[str]], List[str], Set[str]]:
    """解析组合表达式。

    返回值：
    - selections: 每个 layer 最终选中的 value 列表
    - unknown: 无法在 comp_map 中解析的 token
    - disabled_layers: 被 '-' 运算禁用的 layer
    """

    selections: Dict[str, List[str]] = {}
    unknown: List[str] = []
    disabled_layers: Set[str] = set()

    def eval_tokens(tokens: List[str], visiting: Set[str]) -> None:
        """递归展开 token。

        visiting 用于防止循环引用：A 引 B、B 又引 A。
        """

        for token in tokens:
            m = OP_RE.match(token)
            if m:
                layer = m.group("layer")
                op = m.group("op")
                value = m.group("value")
                if op == "-":
                    # layer-：禁用该 layer，并移除此前选择。
                    disabled_layers.add(layer)
                    selections.pop(layer, None)
                    continue
                if not value:
                    continue
                if op == ">":
                    # 覆盖：只保留当前 value。
                    selections[layer] = [value]
                elif op == "+":
                    # 追加：保持已有结果并追加新 value。
                    cur = selections.setdefault(layer, [])
                    if value not in cur:
                        cur.append(value)
                continue

            # 非 OP token：可能是 compositionMap 的 key。
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


def resolve_go_path(path_token: str, all_go_paths: Set[str]) -> Optional[str]:
    """解析 GO 路径。

    解析策略：
    1) 精确匹配直接返回；
    2) 若精确失败，尝试唯一后缀匹配（`.../path_token`）；
    3) 匹配数不为 1 时返回 None，避免歧义。
    """

    if path_token in all_go_paths:
        return path_token
    suffix = "/" + path_token
    hits = [p for p in all_go_paths if p.endswith(suffix)]
    return hits[0] if len(hits) == 1 else None
