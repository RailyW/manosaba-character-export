"""常量与正则表达式定义模块。

本模块集中维护原脚本中的正则对象，避免散落在多个文件里，
并为表达式解析、材质分类等逻辑提供统一依赖。
"""

import re

# 用于按逗号切分组合表达式（允许逗号前后有任意空白字符）。
TOKEN_SPLIT_RE = re.compile(r"\s*,\s*")

# 用于匹配形如：Layer>Value、Layer+Value、Layer- 的运算 token。
# - layer: 图层路径（左侧）
# - op: 运算符（> 覆盖、+ 追加、- 禁用）
# - value: 值（右侧，可空，主要用于 '-'）
OP_RE = re.compile(r"^(?P<layer>.+?)(?P<op>[>+\-])(?P<value>[A-Za-z0-9_]+)?$")

# 匹配材质名中的写遮罩引用，例如：Naninovel_Default#Mask_Ref1_CutoffLow
MAT_MASK_RE = re.compile(r"#Mask_Ref(?P<ref>\d+)", re.IGNORECASE)

# 匹配材质名中的读遮罩引用，例如：Naninovel_Default#Masked_Ref2
MAT_MASKED_RE = re.compile(r"#Masked_Ref(?P<ref>\d+)", re.IGNORECASE)
