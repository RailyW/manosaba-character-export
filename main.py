"""程序主入口。

该文件只负责：
1. 解析命令行参数；
2. 调用渲染流水线。

业务细节全部放在 renderer_app 包内，保持入口轻量。
"""

from __future__ import annotations

from renderer_app.cli import parse_args
from renderer_app.pipeline import run_pipeline


def main() -> None:
    """应用启动函数。"""

    args = parse_args()

    # 运行时交互获取游戏根目录。
    # 示例：E:\game\steam\steamapps\common\manosaba_game
    print("请输入《魔法少女的魔女审判》游戏根目录（示例：E:\\game\\steam\\steamapps\\common\\manosaba_game）")
    game_root = input("游戏根目录: ").strip().strip('"')
    # main 层只负责收集输入，不做路径校验；校验逻辑放到 renderer_app。
    args.game_root = game_root

    run_pipeline(args)


if __name__ == "__main__":
    main()
