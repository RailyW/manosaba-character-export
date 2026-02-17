# manosaba 渲染工具

## 运行环境

- Python 3.10+
- 已安装依赖：`UnityPy`、`Pillow`、`numpy`

## 安装方式

克隆仓库

```
git clone git@github.com:RailyW/manosaba-character-export.git
```

安装依赖

```
pip install -r requirement.txt
```


## 使用方式

### 0) 指定导入文件

将游戏的.bundle文件复制进入文件夹`resources/characters`。

bundle文件存放位置：

```
manosaba_game\manosaba_Data\StreamingAssets\aa\StandaloneWindows64\naninovel-characters_assets_naninovel\characters
```

### 1) 测试模式

每个角色导出前 3 个组合

```bash
python main.py --test
```

仅导出指定角色

例如仅测试 `yuki.bundle`：

```bash
python main.py --test yuki
```

### 2) 全量导出

导出全部角色

```bash
python main.py
```

导出指定角色，例如仅导出 `yuki.bundle` 的全部图像：

```bash
python main.py --character yuki
```

### 3) 指定输入/输出目录

```bash
python main.py --characters-dir resources/characters --output-dir output
```

### 4) 打印详细日志

```bash
python main.py --verbose
```


## 命令行参数

- `--characters-dir`：角色 bundle 目录，默认 `resources/characters`
- `--output-dir`：输出目录，默认 `output`
- `--test`：测试模式。
  - 不带值：每个角色仅导出前 3 张
  - 带角色名：仅测试指定角色（如 `--test yuki`）
- `--character`：仅导出指定角色的全部图像（如 `--character yuki`）
- `--verbose`：输出详细日志


## 输出内容结构

运行后会清空并重建输出目录（默认 `output`），结构如下：

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