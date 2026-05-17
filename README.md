# 说明书保管箱

一个本地浏览器中的「说明书 / 技术资料」管理小程序：拖入文件即自动识别设备/厂商/型号/类别，自动归类、打标签、全文搜索。支持设备说明书、软件用法、政策条文、生活规定等任何起说明作用的资料。

完全本地运行，资料不上传任何云服务（仅在自动识别时把首页文本片段发给 Claude API）。

## 快速开始（已经 clone / 已经有源码）

1. **装 Python**：Python 3.10 或更高版本，去 https://www.python.org/downloads/ 下载安装。

2. **安装依赖**：在项目目录打开命令行（按住 Shift + 右键 → "在此处打开 PowerShell 窗口"），执行：
   ```cmd
   pip install -r requirements.txt
   ```

3. **准备配置文件**：把 `config.example.json` 复制一份命名为 `config.json`，用记事本打开把 `anthropic_api_key` 填上自己的 Claude API key（去 https://console.anthropic.com/ 注册申请）。没有 key 也能跑，只是不会自动识别。

4. **启动**：双击 `start.bat`，浏览器会自动打开 `http://127.0.0.1:8765`。

5. **使用**：把 PDF / Word / 图片 / 文本拖到任意位置即可上传；几秒钟后会自动出现在分类树里。

## 从 GitHub 第一次安装

```cmd
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>
pip install -r requirements.txt
copy config.example.json config.json
notepad config.json
```

填好 API key 后双击 `start.bat`。

## 支持的文件类型

- PDF（推荐，预览体验最好）
- Word `.docx`（`.doc` 旧格式请先另存为 `.docx`）
- 图片 `.jpg / .png / .bmp / .tiff / .webp`（需要安装 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) 才能识别文字内容；不装也能上传，但识别结果会不准）
- 文本 `.txt / .md / .html / .csv / .log`

## 配置说明 (config.json)

| 字段 | 说明 |
|------|------|
| `anthropic_api_key` | Claude API key；为空则跳过自动识别 |
| `model` | 默认 `claude-haiku-4-5`，需要更准可改 `claude-sonnet-4-6` |
| `port` | 监听端口（默认 8765） |
| `storage_dir` | 文件存放根目录（默认 `./storage`） |
| `db_path` | SQLite 数据库路径（默认 `./data/app.db`） |
| `min_confidence` | 识别置信度低于此值时进"待确认"，默认 0.6 |
| `tesseract_cmd` | 如果 Tesseract 不在 PATH 中，可填绝对路径 |

## 目录结构

```
说明书保管箱/
  start.bat               ← 双击启动
  config.example.json     ← 配置模板（进仓库）
  config.json             ← 你的实际配置（不进仓库，含 API key）
  data/app.db             ← SQLite 数据库（不进仓库）
  storage/files/<大类>/<细类>/<厂商>/<型号>/<uuid>_<原名>.<ext>
  storage/files/_unclassified/...   ← 识别失败或低置信度
```

文件按"大类 / 细类 / 厂商 / 型号"四级目录自动归位；政策、规定、软件用法等若没有厂商/型号则降级保存。编辑分类后文件会自动迁移目录。

## 隐私说明

- 全部资料、数据库都只存在你自己电脑的 `storage/` 与 `data/` 目录里
- 自动识别功能会把文档的**首几页文本片段**发送给 Anthropic 的 Claude API 处理后返回分类
- 不调用任何其它云服务，没有遥测，不收集数据
- `config.json`、`storage/`、`data/` 已通过 `.gitignore` 排除，不会被 git 推送

## 故障排查

- **启动报端口被占用**：修改 `config.json` 里的 `port`。
- **PDF 显示乱码**：通常是扫描件 PDF 没有文字层；建议用 OCR 工具先转一遍。
- **图片识别为空**：装 Tesseract OCR，路径填到 `tesseract_cmd`。
- **想换模型**：把 `model` 改成 `claude-sonnet-4-6` 之类的更强模型。

## 端到端流程

1. 启动后浏览器自动打开
2. 拖入说明书 PDF → 进度条 → 几秒后列表新增一条"网络设备/路由器/TP-Link/Archer C7"
3. 顶部搜索框输入"WPS"→ 命中正文，返回该条
4. 右侧详情区点击「编辑」可手动修正分类与标签，保存后文件自动迁移目录
5. 顶部「待确认」红点：进入查看所有识别置信度低的文档

## 协议

MIT License — 见 [LICENSE](LICENSE)。可自由使用、修改、分发。
