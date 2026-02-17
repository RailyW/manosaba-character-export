"""图像处理与混合模块。

本模块封装所有与像素运算相关的函数：
- 颜色着色（tint）
- 局部混合（multiply/overlay/softlight）
- 遮罩写入与读取
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from PIL import Image


def apply_color_tint(img: Image.Image, color: Tuple[float, float, float, float]) -> Image.Image:
    """按 RGBA 系数对图片进行乘法着色。

    参数 color 的每一项通常位于 [0,1]，与 Unity 的 m_Color 语义一致。
    """

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
    """对 RGB 做 blend 运算（不处理 alpha）。"""

    if mode == "multiply":
        return base_rgb * fg_rgb
    if mode == "overlay":
        return np.where(base_rgb <= 0.5, 2 * base_rgb * fg_rgb, 1 - 2 * (1 - base_rgb) * (1 - fg_rgb))
    if mode == "softlight":
        return (1 - 2 * fg_rgb) * (base_rgb**2) + 2 * fg_rgb * base_rgb
    return fg_rgb


def blend_patch(canvas: Image.Image, patch: Image.Image, x: int, y: int, mode: str) -> None:
    """将 patch 以指定 blend 模式混合到 canvas。

    注意：
    - 仅处理与画布交叠区域，避免越界；
    - 先取出 dst/src 子区域，再用 numpy 计算输出。
    """

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
    """将 patch 的 alpha 写入 mask 缓冲区（取 max）。"""

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
    """使用 mask 缓冲区裁剪 patch 的 alpha。"""

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
