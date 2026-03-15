# Java 视频教程 → 结构化知识体系

> **一套基于 Claude Code Skill + MCP 的高自动化 Java 全栈学习提效工作流**
> 
> 将本地视频教程自动转化为：权威校验的知识文档（含图）+ Anki 卡包 + 练习题组
> 
> 覆盖：Java 基础 → Java Web → Spring Boot → Spring Cloud 全系列课程

---

## 目录

- [项目概述](#项目概述)
- [核心设计理念](#核心设计理念)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [完整工作流](#完整工作流)
- [长视频处理](#长视频处理)
- [输出产物规格](#输出产物规格)
- [配置参考](#配置参考)
- [API 兼容性](#api-兼容性)
- [FAQ](#faq)

---

## 项目概述

### 你在用这个方案解决什么问题？

| 痛点 | 本方案的解法 |
|------|------------|
| 倍速看视频容易遗漏难点 | 提取字幕 + AI 重建知识，不依赖视频语速 |
| 字幕有噪声，不能直接当学习材料 | 字幕仅作"话题线索"，知识从权威文档重建 |
| 教程版本老旧（Java 8 时代） | 强制版本差异对比，以 Java 21 LTS 为主线 |
| AI 生成内容可信度存疑 | 每条知识点必须有 JLS/官方文档/JEP 锚点 |
| 学完容易忘 | 自动生成 Anki 卡包，强制间隔重复 |
| 视频中的代码/板书难以截取 | 自动提取场景关键帧，嵌入知识文档 |
| 视频太长（2小时+）无从下手 | 自动按静音点分段，每段独立处理 |
| 基础差看不懂技术文档 | 生活类比 + 分步拆解 + 逐行代码解读 |
| 换 AI 平台就要重头来 | API 无关设计，换任何 LLM 都能用 |

### 覆盖的课程范围

```
Java 基础 ────→ Java Web ────→ Spring Boot ────→ Spring Cloud
  ├ 语法           ├ Servlet        ├ 自动配置         ├ Nacos/Eureka
  ├ 面向对象       ├ JSP            ├ Spring MVC       ├ Feign
  ├ 集合框架       ├ JDBC           ├ MyBatis           ├ Gateway
  ├ 异常/IO        ├ Filter         ├ Spring Security   ├ 配置中心
  ├ 并发编程       └ Tomcat         ├ Redis 缓存        └ 消息队列
  └ JVM 原理                        └ 单元测试
```

### 两层核心产物

```
【视频级 Layer 1】每个视频 → knowledge_{video_stem}.md
  主知识文档（含关键帧、生活类比、分步拆解）
  存入 portable-gpu-worker/output/{课程}/{章节}/{视频名}/

【章节级 Layer 2】一章全部视频处理完 → 章节学习包
  CHAPTER_SYNTHESIS_{章节名}.md    完整独立的全章知识文档
  CHAPTER_EXERCISES_{章节名}.md    全章练习题（含面试题专区）
  CHAPTER_ANKI_{章节名}.apkg       可直接导入的 Anki 卡包
  存入 portable-gpu-worker/output/{课程}/{章节}/CHAPTER_SYNTHESIS_{章节名}/
```

---

## 核心设计理念

### 信息流设计

```
视频文件（放入 portable-gpu-worker/videos/ 目录）
    │
    ├─[自动检测]────────────────────────────────
    │   └─ 是否超过90分钟？→ 自动分段
    │
    ├─[预处理阶段]─────────────────────────────
    │   运行 0_开始使用.bat → [3] 开始预处理：
    │   ├─ extract_audio.py → 音频 (.wav)
    │   ├─ transcribe.py → 字幕 (.srt + words.json)
    │   └─ extract_keyframes.py → 关键帧 (frames/*.jpg)
    │   └─ 产物存入 portable-gpu-worker/output/{课程}/{章节}/{视频名}/_preprocessing/
    │
    └─[AI 处理阶段]─────────────────────────────
        ├─ Stage 1: 字幕清洗 + 话题分段
        │   (字幕 = 话题线索，非事实来源)
        │
        ├─ Stage 2: 知识重建
        │   ├─ 生活类比 + 概念拆解
        │   ├─ 权威校验 (P1-P3)
        │   ├─ 版本差异标注
        │   └─ 视频级知识文档生成
        │
        └─ 产物存入 portable-gpu-worker/output/{课程}/{章节}/{视频名}/
            └─ knowledge_{video_stem}.md ← 视频级唯一产物

        （章节所有视频完成后，流程C自动生成章节学习包）
        └─ 章节学习包存入 CHAPTER_SYNTHESIS_{章节名}/
            ├─ CHAPTER_SYNTHESIS_{章节名}.md ← 主学习文档
            ├─ CHAPTER_EXERCISES_{章节名}.md
            └─ CHAPTER_ANKI_{章节名}.apkg
```

### 初学者友好设计

| 特性 | 说明 |
|------|------|
| 🌟 一句话理解 | 每个概念都有最通俗的一句话解释 |
| 🏠 生活类比 | 将技术概念映射到日常场景 |
| 📖 分步拆解 | 复杂概念分3步递进理解 |
| 💻 逐行解读 | 代码示例每行都有解释 |
| 💡 动手实验 | 引导修改代码验证理解 |
| 🔗 知识关联 | 标注前置/后续/易混淆概念 |
| 📌 记忆口诀 | 重要规则提供助记方法 |

---

## 项目结构

```
java-learning-workflow/
│
├── CLAUDE.md                            ← 项目级 Claude Code 指令（自动读取）
├── README.md                            ← 本文档
│
├── portable-gpu-worker/                 ← ★ 便携预处理包（视频、输出、预处理脚本）
│   ├── videos/                         ← 视频存放目录
│   ├── output/                         ← 输出目录
│   │   ├── course_knowledge_graph.json ← 全课知识图谱（差量处理核心，唯一实例）
│   │   └── Java基础-视频上/             ← 课程目录
│   │       └── day01-Java入门/          ← 章节目录
│   │           ├── 01-Java基础/         ← 视频目录（视频 stem）
│   │           │   ├── knowledge_01-Java基础.md ← 视频级唯一产物
│   │           │   └── _preprocessing/  ← 预处理产物（深层目录）
│   │           └── CHAPTER_SYNTHESIS_day01-Java入门/  ← 章节学习包
│   │               ├── CHAPTER_SYNTHESIS_day01-Java入门.md
│   │               ├── CHAPTER_EXERCISES_day01-Java入门.md
│   │               └── CHAPTER_ANKI_day01-Java入门.apkg
│   ├── scripts/                        ← 预处理脚本（extract_audio、transcribe、extract_keyframes、split_video）
│   ├── run_preprocess.py               ← 预处理交互式主脚本
│   └── 0_开始使用.bat                  ← ★ 统一入口（联网准备/离线准备/预处理/费用估算）
│
├── skills/
│   └── java-learning/
│       └── SKILL.md                     ← Claude Code Skill 定义
│
├── .claude/
│   └── commands/
│       ├── process-video.md             ← /process-video 斜杠命令
│       └── batch-process.md             ← /batch-process 斜杠命令
│
├── mcp-server/
│   ├── server.py                        ← MCP 服务器（17个工具）
│   ├── requirements.txt                 ← Python 依赖
│   └── mcp_config.json                 ← MCP 配置参考模板
│
├── scripts/
│   ├── bootstrap.py                     ← ★ 环境自检 + 自动配置（首次运行）
│   ├── gui_launcher.py                  ← ★ GUI 启动器（章节选择 + Session 规划）
│   ├── pipeline.py                      ← ★ 主流水线入口（scan、status）
│   ├── generate_anki.py                 ← CSV → .apkg 打包
│   ├── merge_anki.py                    ← 合并多个 Anki CSV 并生成章节级 .apkg
│   ├── write_anki_csv.py                ← UTF-8 无 BOM 的 CSV 写入工具
│   └── prepare_portable_pack.py         ← 便携包打包脚本
│
├── prompts/
│   ├── 0_standalone_system_role.md        ← AI角色设定（独立对话专用）
│   ├── A1_subtitle_analysis.md        ← Layer1 阶段1：字幕分析+话题分段+处理模式判断
│   ├── A2_knowledge_gen.md            ← Layer1 阶段2：知识文档生成（仅 knowledge_{stem}.md）
│   ├── C_chapter_synthesis.md          ← Layer2：完整独立章节学习手册
│   └── B_batch_coordinator.md      ← 批量协调（流程B） + COURSE_SUMMARY 模板
│
├── templates/
│   ├── knowledge_doc.md                 ← 知识文档输出模板（4 种处理模式头部）
│   ├── exercises_doc.md                 ← 章节练习题文档模板
│   └── anki_card.csv                    ← Anki CSV 模板
│
├── config/
│   └── config.yaml                      ← 全局配置
│
├── .mcp.json                            ← MCP 配置（Claude Code，bootstrap 自动生成）
├── .vscode/
│   ├── mcp.json                         ← MCP 配置（VS Code Copilot Agent 模式）
│   ├── settings.json                    ← 工作区设置（含 PowerShell UTF-8）
│   └── extensions.json                  ← 推荐插件列表
├── .cursor/
│   └── mcp.json                         ← MCP 配置（Cursor，bootstrap 自动生成）
```

---

## 快速开始

### 方式 A：全自动安装（推荐）

```bash
# 1. 克隆项目
cd <project-root>

# 2. 运行自动配置（检测环境 + 创建虚拟环境 + 安装依赖 + 配置 MCP）
python scripts/bootstrap.py

# 3. 将视频文件放入 portable-gpu-worker/videos/ 目录
# 支持格式：.mp4 .mkv .avi .mov .flv .wmv .webm .m4v

# 4. 在 Claude Code 或 Cursor 中启动
# Claude Code CLI：claude
# Cursor：直接打开项目文件夹，bootstrap 已生成 .cursor/mcp.json，重启 Cursor 后即可使用 MCP 工具

# 5. 在 AI 对话中启动 GUI 选择器
# AI 会自动启动 GUI 选择器（gui_launcher.py），在界面中选择章节后自动处理
# 也可以直接在对话中要求「批量处理视频」或「处理 day01」
```

### 方式 B：在 Claude Code 中自动处理

首次在项目目录下启动 Claude Code 时，AI 会自动：
1. 检测运行环境（Python、FFmpeg、Node.js、GPU）
2. 如有缺失，辅助安装
3. 创建虚拟环境并安装 Python 依赖
4. 配置 MCP Server
5. 安装 Skill
6. 扫描 portable-gpu-worker/videos/ 目录
7. 询问你要处理哪些视频

### 前置依赖

| 依赖 | 最低版本 | 安装方式 | 是否必须 |
|------|---------|---------|---------|
| Python | 3.10+ | 系统安装 | ✅ 必须 |
| FFmpeg | 4.0+ | 系统安装 | ✅ 必须 |
| Node.js | 18+ | 系统安装 | 可选（部分 Claude Code 集成可能需要） |
| NVIDIA GPU | - | CUDA 驱动 | 可选(加速Whisper) |

---

## 完整工作流

### 1. 扫描视频

```bash
python scripts/pipeline.py scan
```

输出：
```
 #   文件名                    时长      大小     状态      备注
  1  01-Java基础语法.mp4       01:25:30  850 MB   ○ 待处理
  2  02-面向对象.mp4            45:20    420 MB   ○ 待处理
  3  03-集合框架.mp4           02:15:00  1.2 GB   ○ 待处理  ⚠ 长视频(需分段)
```

### 2. 预处理（音频、字幕、关键帧）

将视频放入 `portable-gpu-worker/videos/`，在 portable-gpu-worker 目录下运行：

```bash
0_开始使用.bat
# 选择 [3] 开始预处理
```

系统会：
- 列出所有视频
- 询问你要处理哪些（全部/指定编号/范围）
- 自动识别长视频并分段
- 逐个完成预处理

### 3. AI 知识生成

```bash
# 在 Claude Code 中
/batch-process
```

AI 会：
- 分析知识依赖关系
- 按最优顺序处理
- 为每个视频生成知识文档（视频级）
- 每章完成后生成章节学习包（章节综合手册 + 练习题 + Anki 卡包）
- 最后生成 COURSE_SUMMARY.md

### 4. 查看状态

```bash
python scripts/pipeline.py status
```

> **提示**：预处理在 portable-gpu-worker 中完成；主项目 pipeline 的 scan/status 读取 portable-gpu-worker 的 videos/output。

---

## 长视频处理

对超过 90 分钟的视频，系统会自动：

1. **智能分段**：检测视频中的静音点，在自然停顿处切割（而非硬切）
2. **目标段时长**：约 45 分钟/段
3. **段间重叠**：30 秒重叠，避免语句被切断
4. **独立预处理**：每段独立提取音频、字幕、关键帧
5. **合并输出**：AI 处理时，分段生成后合并为统一文档

示例：一个 2 小时 15 分的视频会被分为 3 段（约 45 分钟/段）。

配置：
```yaml
# config/config.yaml
long_video:
  max_segment_duration: 5400   # 超过此秒数自动分段 (90分钟)
  target_segment_duration: 2700 # 目标段时长 (45分钟)
  overlap_seconds: 30          # 段间重叠
```

---

## 输出产物规格

### 目录结构

```
portable-gpu-worker/output/
├── course_knowledge_graph.json ← 全课知识图谱（差量处理核心）
│
└── Java基础-视频上/             ← 课程目录
    └── day01-Java入门/          ← 章节目录
        ├── 01-Java基础语法/     ← 视频目录（视频 stem）
        │   ├── knowledge_*.md  ← 视频级唯一产物
        │   └── _preprocessing/ ← 预处理产物
        │       ├── *_audio.wav
        │       ├── *.srt
        │       ├── *_words.json
        │       ├── segments/   ← 长视频分段（如有）
        │       └── frames/
        │
        └── CHAPTER_SYNTHESIS_day01-Java入门/  ← 章节学习包（流程C生成）★
            ├── CHAPTER_SYNTHESIS_day01-Java入门.md  ← 主学习文档
            ├── CHAPTER_EXERCISES_day01-Java入门.md  ← 全章练习题
            ├── CHAPTER_ANKI_day01-Java入门.csv
            ├── CHAPTER_ANKI_day01-Java入门.apkg     ← 导入 Anki
            └── chapter_completeness_audit.md
```

### COURSE_SUMMARY.md

批量处理后自动生成，包含：
- 📊 整体统计表（视频数、知识点数、章节学习包数）
- 🗺️ Mermaid 知识依赖关系图
- 🎯 分类学习路线（Java基础 → Web → Spring Boot → 微服务）
- 📁 各章节学习包索引（带链接）
- 🔄 推荐复习计划

### knowledge_{video_stem}.md

每个知识点包含：
- 🌟 一句话理解（最通俗版本）
- 🏠 生活类比（日常场景映射）
- 📌 精确定义
- 📖 分步概念拆解（3步递进）
- ⚠️ 常见陷阱（含错误原因 + 初学者提醒）
- 💻 完整可运行代码（含逐行解读）
- 🔩 底层原理（简单版 + 深入版）
- 📊 版本差异表
- 🔗 知识关联图

### CHAPTER_ANKI_{章节名}.apkg

章节学习包的 Anki 卡包，由流程 C 从章节综合文档从零生成，每章一包。

| 卡片类型 | 正面 | 背面 |
|---------|------|------|
| 定义 | 概念名 | 权威定义 + 生活类比 + 版本 |
| 代码填空 | 带空的代码 | 完整代码 + 解释 |
| 版本区别 | 版本比较问题 | 差异表 |
| 易错点 | 错误代码 | 原因 + 正确版本 |
| 底层原理 | "为什么..." | 机制解释 |

---

## 配置参考

编辑 `config/config.yaml`：

```yaml
# 字幕提取（Whisper）
whisper:
  model: "medium"          # tiny/base/small/medium/large-v3
  language: "zh"
  device: "auto"           # auto/cpu/cuda（bootstrap自动检测）

# 关键帧提取
keyframes:
  scene_threshold: 0.25    # 场景切换敏感度 (0-1)，推荐 0.25
  fallback_interval: 30    # 兜底采样间隔（秒）
  max_frames_per_video: 80

# 长视频处理
long_video:
  max_segment_duration: 5400   # 90分钟
  target_segment_duration: 2700 # 45分钟

# 学习者水平
learner_level: "beginner"  # beginner/intermediate/advanced

# 输出设置
output:
  base_dir: "./portable-gpu-worker/output"
  anki:
    deck_name: "Java全栈"
```

---

## API 兼容性

本项目设计为 **API 无关**，核心理念：

1. **预处理阶段**（Python 脚本）完全独立于任何 AI API
2. **知识生成阶段**通过 `prompts/` 目录的模板驱动
3. **MCP Server** 提供的工具函数与 AI API 无关
4. **配置文件**中不包含 API 密钥或端点

无论你使用：
- Anthropic Claude API
- OpenAI GPT API
- Google Gemini API
- 或其他 LLM

只要 AI 能读取提示词模板并按规范输出，工作流程完全一致。质量由六项工作原则保障，不依赖特定模型能力。

---

## MCP Server 工具列表

| 工具 | 功能 |
|------|------|
| `get_video_metadata` | 获取视频元数据（时长/分辨率/编码）|
| `transcribe_video` | Whisper 字幕转写（生成 .srt + words.json）|
| `extract_keyframes` | 场景关键帧提取（支持 words.json 难点引导）|
| `align_frames_to_transcript` | 帧-字幕时间戳对齐，生成映射表 |
| `export_anki_package` | CSV → .apkg Anki 卡包打包 |
| `list_video_files` | 扫描视频目录，返回元数据和处理状态 |
| `check_preprocessing_status` | 检查预处理产物完整性（含 A1 字幕分析状态）|
| `split_long_video` | 长视频按静音点智能分段 |
| `get_output_paths` | 获取视频对应的标准输出路径结构 |
| `check_environment` | 检查运行环境（依赖、FFmpeg、MCP 配置）|
| `run_bootstrap` | 运行环境初始化脚本 |
| `query_knowledge_graph` | 查询课程知识图谱（概念覆盖深度/位置）|
| `update_knowledge_graph` | 更新知识图谱（写入新视频的覆盖情况）|
| `read_chapter_summaries` | 读取章节内所有视频摘要，用于章节综合 |
| `scan_chapter_completeness` | 扫描章节知识完整性，生成待补全清单 |
| `validate_knowledge_graph` | 校验图谱完整性 + 深度分布统计 |
| `validate_video_products` | 校验章节视频级产物完整性 |

---

## FAQ

**Q：首次运行需要做什么？**
A：只需运行 `python scripts/bootstrap.py`，它会自动检测环境、安装依赖、配置 MCP。或者直接在 Claude Code 中启动项目，AI 会自动完成初始化。

**Q：视频超过2小时怎么办？**
A：系统会自动检测长视频并在静音点智能分段（每段约45分钟），无需手动处理。

**Q：如何选择处理哪些视频？**
A：运行 `/batch-process` 后，系统会列出所有视频并提供交互式选择（全部/指定编号/范围）。

**Q：换了电脑怎么迁移？**
A：复制整个项目目录，在新电脑上运行 `python scripts/bootstrap.py` 即可。bootstrap 会自动适配新环境。

**Q：字幕识别效果很差怎么办？**
A：在 `config.yaml` 的 `initial_prompt` 中加入更多该视频涉及的技术词汇。

**Q：AI 标注了 ⚠️【不确定】怎么处理？**
A：这是正常的诚实标注。可以查阅文档中建议的验证方式，或暂时跳过。

**Q：可以处理英文教程吗？**
A：可以。修改 `config.yaml` 中 `whisper.language: "en"`。

**Q：能和其他 AI API 一起用吗？**
A：可以。项目设计为 API 无关，所有处理通过提示词模板驱动。预处理阶段完全独立于 AI API。

**Q：在 Cursor 中如何配置 MCP？**
A：运行 `python scripts/bootstrap.py` 后，会自动生成 `.cursor/mcp.json`（Cursor 项目级 MCP 配置）。配置完成后需**完全重启 Cursor** 才能加载 MCP 工具。

**Q：在 VS Code + GitHub Copilot 中如何使用 MCP？**
A：项目已包含 `.vscode/mcp.json`，VS Code 1.99+ 内置 MCP 支持，无需额外插件。安装 `GitHub.copilot-chat` 扩展后，在 Copilot Chat 面板切换到 **Agent 模式**，工具栏会出现 MCP 工具图标，可直接调用所有 17 个工具。
