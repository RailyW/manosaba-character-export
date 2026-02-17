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

支持解析的人物：

- alisa.bundle
- anan.bundle
- coco.bundle
- ema.bundle
- hanna.bundle
- hiro.bundle
- leia.bundle
- margo.bundle
- meruru.bundle
- miria.bundle
- nanoka.bundle
- noah.bundle
- sherry.bundle

其他角色，如狱卒，典狱长，小雪，因为文件结构不同，暂不支持，之后可能会支持，也可能不会支持。

### 1) 测试模式（每个角色导出前 3 个组合）

```bash
python main.py --test
```

### 2) 全量模式（导出全部组合）

```bash
python main.py
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
- `--test`：测试模式，每个角色仅导出 3 张
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


## 常用命令示例

```bash
# 快速检查（推荐）
python main.py --test

# 全量导出
python main.py
```
