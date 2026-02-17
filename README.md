# 魔法少女的魔女审判 立绘导出工具

本工具仅在Windows下进行开发和测试，没有针对Mac OS进行过兼容性测试，请自行测试。

如果有问题或希望改进的功能，欢迎issue互动。

## 安装

克隆仓库

```
git clone git@github.com:RailyW/manosaba-character-export.git
```

安装依赖

```
pip install -r requirement.txt
```


## 使用

### GUI 模式（推荐）

```bash
python gui.py
```

GUI 提供以下能力：
- 输入或浏览选择游戏根目录
- 自动读取并列出角色 bundle
- 多选 / 全选 / 取消全选
- 勾选测试模式（每角色前 3 张）
- 选择输出目录（默认项目目录下 `output`）

### 0) 启动后输入游戏根目录

运行程序后，会提示你输入《魔法少女的魔女审判》游戏根目录。

示例：

```
E:\game\steam\steamapps\common\manosaba_game
```

程序会自动拼接为以下目录来查找 `.bundle` 文件：

```
<游戏根目录>\manosaba_Data\StreamingAssets\aa\StandaloneWindows64\naninovel-characters_assets_naninovel\characters
```

### 1) 测试

每个角色导出 3 个立绘：

```bash
python main.py --test
```

仅导出指定角色的 3 个立绘，例如仅测试 `yuki.bundle`：


```bash
python main.py --test yuki
```

### 2) 导出

导出全部角色：

```bash
python main.py
```

导出指定角色，例如仅导出 `yuki.bundle` 的全部图像：

```bash
python main.py --character yuki
```

### 3) 指定输出目录

```bash
python main.py --output-dir output
```

### 4) 打印详细日志

```bash
python main.py --verbose
```


## 命令行参数

- `--output-dir`：输出目录，默认 `output`
- `--test`：测试模式。
  - 不带值：每个角色仅导出前 3 张
  - 带角色名：仅测试指定角色（如 `--test yuki`）
- `--character`：仅导出指定角色的全部图像（如 `--character yuki`）
- `--verbose`：输出详细日志


## 输出内容结构

运行后会写入输出目录（默认 `output`）。若同名文件已存在，会直接覆盖，结构如下：

```text
output/
  report.json
  <character>/
    <combo>.png
  render_trace/
    <character>/
      <combo>.json
```

- `report.json`：本次运行汇总报告（导出数、跳过数、错误信息等）
- `output/<character>/*.png`：最终导出的角色图像
- `output/render_trace/<character>/*.json`：每张图的渲染轨迹记录（DEBUG用）