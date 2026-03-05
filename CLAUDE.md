# Java 学习工作流 - 项目指令

> 本文件是本项目的 AI 指令入口，适用于 Claude Code、GitHub Copilot、Cursor 等 AI 助手。
> Claude Code 在项目目录下自动读取；GitHub Copilot 通过 VS Code 指令机制加载；Cursor 通过 `.cursor/rules/` 加载。
> **完整工作规范见 `skills/java-learning/SKILL.md`**（初始化后必须激活该 Skill）。

---

## 系统定位（必须先理解）

**最终产物是章节级学习包，不是单个视频的文档。**

视频级处理（流程 A）是管道过程，不是终点。用户实际学习时打开的是：
- `CHAPTER_SYNTHESIS_{day}.md` — 连贯完整的全章知识文档
- `CHAPTER_EXERCISES_{day}.md` — 覆盖全章的练习题集
- `CHAPTER_ANKI_{day}.apkg` — 章节 Anki 卡包

视频级文档（`knowledge_*.md`）是原材料，供溯源细节用。

**差量处理机制（核心设计）**：视频教程天然存在内容重叠。系统通过知识图谱（`course_knowledge_graph.json`）追踪每个概念的覆盖状态和深度，每个视频按其相对已有内容的新增量，自动分配处理模式：
- **Full Mode**：大量全新概念 → 完整知识文档
- **Supplement Mode**：已有概念的新侧面 → 只写新内容，引用已有文档
- **DeepDive Mode**：已有概念达到更高深度 → 从当前深度切入，不重复基础
- **Practice Mode**：纯实操练习 → 极简步骤文档 + 丰富练习题

这意味着：内容高度重叠的视频（如"JDK安装"在"Java介绍"之后）会自动生成短小精悍的 Supplement/Practice 文档，而不是重复解释同一概念。

---

## 首次启动检查

当用户首次在本项目中与你对话时，**按以下顺序执行**：

### 1. 激活 Skill

本项目通过 Skill 机制提供完整工作规范。确认 `skills/java-learning/SKILL.md` 可读取，并按其中的规范执行所有后续操作。

### 2. 环境检查

检查以下条件是否满足：
- `.venv/` 虚拟环境是否存在
- `.mcp.json`（Claude Code）、`.cursor/mcp.json`（Cursor）或 `.vscode/mcp.json`（GitHub Copilot）配置是否存在
- `portable-gpu-worker/videos/` 目录是否存在

如果任一条件不满足，运行：
```bash
python scripts/bootstrap.py
```

### 3. 依赖验证

调用 MCP 工具 `check_environment` 验证依赖是否就绪（工具在进程内用 `importlib` 检测，全平台可靠）：

- ✅ `all_dependencies_ok: true` → **立即进入 Step 4，不执行任何安装操作**
- ❌ `all_dependencies_ok: false` → 查看 `dependencies` 字段找到缺失包，然后安装：

```bash
# Windows
.venv\Scripts\pip install -r mcp-server/requirements.txt
# macOS/Linux
.venv/bin/pip install -r mcp-server/requirements.txt
```

### 4. 运行 GUI 启动器，弹出选择界面

**Step 4a — 自我识别 AI 环境，确定 `--env` 参数**：

> 在启动 GUI 之前，先判断你当前运行在哪个 AI 环境中，对应关系如下：
>
> | 你是谁 | 传入参数 |
> |--------|----------|
> | GitHub Copilot（VS Code Copilot Chat / Agent） | `--env copilot` |
> | Claude Code（Anthropic CLI 或 claude.ai）     | `--env claude-code` |
> | Cursor AI Chat / Cursor Agent                | `--env cursor` |
> | OpenAI Codex                                 | `--env codex` |
> | 其他 / 不确定                                 | `--env generic` |
>
> ❗ 不要依赖文件系统自动探测 — 项目目录下可能存有其他 AI 工具的配置文件（如 `.cursor/`），会导致误判。**必须由 AI 自己明确传入。**

**Step 4b — 启动 GUI（`isBackground=true`，命令立即返回，GUI 在后台独立运行）**：
```bash
# Windows（isBackground=true，命令立即返回，GUI 窗口在后台独立运行）
.venv\Scripts\python scripts/gui_launcher.py --env copilot
# macOS/Linux
.venv/bin/python scripts/gui_launcher.py --env copilot
```
> - 将 `copilot` 替换为上方表格确定的值。
> - 此命令以 **`isBackground=true`** 运行，立即返回一个终端 ID；GUI 窗口在后台独立运行。
> - 命令返回后，**立即向用户说**：「✅ GUI 已弹出，请在界面中选择章节并点击确认按钮。**选择完成后，发送任意消息继续。**」
> - 用户点击确认后，结果写入 `scripts/_gui_result.json`，GUI 自动关闭。
> - **收到用户的下一条消息后**，读取 `scripts/_gui_result.json`，按 `action` 字段执行后续流程。
> - 若文件不存在或内容为空，提示用户先在 GUI 中完成选择并点击确认，再发送消息。
> - **GUI 每次启动都实时重新扫描视频目录和已有产物**，始终反映最新进度，无需维护任何缓存。

GUI 界面会自动检测当前 AI 环境（Claude Code / GitHub Copilot / Cursor / Codex），并展示：
- 顶部环境徽章（显示当前识别到的 AI 环境）
- 每个章节的视频总数和彩色进度条（绿=已完成、黄=已预处理、灰=待处理）
- 底部模型选择器（仅显示当前环境支持的模型，含真实上下文大小和 Session 预算）
- 点击章节行选择 → 右侧面板显示 Session 规划预览 → 悬停按钮查看操作说明 → 点击按钮确认

GUI 关闭后输出 JSON（例）：
```json
{
  "action": "process_chapter",
  "env": "copilot",
  "chapter_key": "Java基础-视频上/day01-Java入门",
  "course": "Java基础-视频上",
  "day": "day01-Java入门",
  "day_path": "...",
  "chapter_output_dir": "...portable-gpu-worker/output/Java基础-视频上/day01-Java入门",
  "total": 16,
  "completed": 1,
  "preprocessed": 15,
  "pending": 0,
  "model": "cop-claude-sonnet-4.6",
  "token_budget": 70000,
  "total_sessions": 3,
  "current_session_index": 0,
  "current_session_videos": ["视频1", "视频2", "视频3"],
  "current_session_est_tokens": 68400,
  "is_resume": false
}
```

**读取这个 JSON 结果，按其中的 `action` 字段执行后续流程：**

| `action` 字段 | 操作 |
|------------|------|
| `process_chapter` | **只处理 `current_session_videos` 列表中的视频**（不多不少），每个完整执行流程 A 全部 6 步；若 `current_session_index + 1 < total_sessions` → 提示用户**重新运行 GUI 启动器**；若是最后一 Session → **按下方流程 C 步骤执行章节综合（多轮）** |
| `synthesis` | 直接执行流程 C：先调用 `read_chapter_summaries` + `scan_chapter_completeness`，再按 SKILL.md Steps C2-C4 多轮生成学习包（outline→synthesis→exercises→anki，每轮独立响应保存后等用户确认，严禁合并为一次响应） |
| `manual` | 读取 `SKILL.md` 并按字面出现的询问引导用户 |
| `cancelled` | 用户取消，不执行任何操作 |

**Session 处理完成后**：
1. 若 `current_session_index + 1 < total_sessions` → 告知用户"Session {current_session_index+1}/{total_sessions} 已完成，请**重新运行 GUI 启动器**继续下一 Session"（GUI 启动时自动扫描最新进度，无需手动维护状态）
2. 若是最后一个 Session → **直接触发流程 C**（见下方"流程 C"节，分轮执行）

> ⚠️ **不需要再调用 `list_video_files`** 获取标题中的视频数量，当 GUI 已将 `total`/`completed`/`preprocessed`/`pending` 包含在 JSON 输出中。

---

## 三条主要流程

**详细规范见 `skills/java-learning/SKILL.md`，此处为快速导航：**

### 流程 A：单视频差量处理

每个视频的处理步骤（**按序执行，批量处理时每个视频都必须完整走完全部 6 步，不可跳过、合并或简化**）：
1. 预处理检查（有无 `.srt` 和 `frames/`）
2. 调用 MCP 工具获取上下文（视频元数据 + 预处理状态 + **知识图谱范围查询**）
3. 加载 `prompts/A1_subtitle_analysis.md` → 字幕分析 + 图谱比对 + **模式判断**（Full/Supplement/DeepDive/Practice）
4. 加载 `prompts/A2_knowledge_gen.md` → 按模式生成知识文档（唯一产物：`knowledge_*.md`；练习题/Anki 在流程 C 统一生成）
5. 产物保存到 `portable-gpu-worker/output/{course}/{day}/{video_stem}/`
6. **调用 `update_knowledge_graph`**（强制，不可省略 — 后续视频模式判断依赖它）

> ❌ **批量处理时严禁的行为**：跳过 Step 2 MCP 调用、跳过 Step 3 Stage 1 分析、合并多个视频一次生成、Step 6 推迟到全部视频处理完后统一调用。每个视频必须独立完整走一遍。

### 流程 B：批量处理

扫描目录 → 加载 `prompts/B_batch_coordinator.md` → 逐个执行流程 A → 完成后自动询问是否触发流程 C。

### 流程 C：章节综合（生成最终学习包）

**触发时机**（任意满足即可）：
- 用户明确要求（如"帮我整合 day01"）
- 检测到该章节所有视频均已完成流程 A
- 开始处理新章节的第一个视频时，询问"上一章节是否要先生成学习包？"

> ❌ **严禁在一次响应内同时生成多件产物**（超时根因）。三件产物必须拆分为独立响应轮次，每轮保存后等用户确认才继续。`PASS_MODE = "full"` 已废弃。

**执行步骤（完整规范见 SKILL.md §流程C → Steps C1-C4）**：

1. **Step C1（工具调用，强制前置）**：
   - `read_chapter_summaries(chapter_dir)` → 获取所有视频摘要与知识图谱数据
   - `scan_chapter_completeness(chapter_dir)` → 生成 `chapter_completeness_audit.md`（兜底机制2）

2. **Step C2（策略选择）**：根据知识点总数选择对话轮次（≤15点→跳过outline，直接4轮；16-40点→5轮；>40点→N+4轮）

3. **Step C3（多轮生成）**：加载 `prompts/C_chapter_synthesis.md`，按以下 Pass 顺序各占一轮对话依次执行：
   - `PASS_MODE = "outline"`（可选，标准/大型章节）→ 保存 `chapter_outline.json`
   - `PASS_MODE = "synthesis"` → 生成并保存 `CHAPTER_SYNTHESIS_*.md`（知识点>20时分节写入）
   - `PASS_MODE = "exercises"` → 读取磁盘 synthesis 文件，生成并保存 `CHAPTER_EXERCISES_*.md`
   - `PASS_MODE = "anki"` → 读取磁盘 synthesis 文件，生成 CSV + 调用 `export_anki_package` 打包

**最终产物**（均保存在 `{chapter_dir}/CHAPTER_SYNTHESIS_{chapter_dir_name}/` 下，其中 `chapter_dir_name = Path(chapter_dir).name`，如 `day01-Java入门`）：
- `CHAPTER_SYNTHESIS_{chapter_dir_name}.md` — **主学习文档** ★（连贯全章，概念间有显式贯通，独立可读）
- `CHAPTER_EXERCISES_{chapter_dir_name}.md` — 全章练习（基于 CHAPTER_SYNTHESIS 从零生成，完整覆盖全章知识点）
- `CHAPTER_ANKI_{chapter_dir_name}.csv/.apkg` — 章节 Anki 包（基于 CHAPTER_SYNTHESIS 统一从零生成）★
- `chapter_completeness_audit.md` — 本章待补全清单（未完全讲解的知识点预报）

---

## 输出目录结构

```
portable-gpu-worker/output/
├── course_knowledge_graph.json              ← Layer 0：全课知识图谱（贯穿整个课程）
│
└── {课程文件夹}/                            如：Java基础-视频上/
    └── {章节文件夹}/                        如：day01-Java入门/
        │
        ├── {video_stem}/                    ← Layer 1：视频级产物（每视频一个）
        │   ├── knowledge_{stem}.md          ← 唯一视频级产物（Full/Supplement/DeepDive/Practice 之一）
        │   └── _preprocessing/              ← 练习题/Anki 在流程 C 章节综合时从零生成，不在视频级生成
        │       ├── *.srt / *_words.json
        │       ├── *_topics.json            ← A1 输出（含处理模式）
        │       ├── *_teaching_style.json    ← A1 输出（教学风格）
        │       └── frames/
        │   （注：chapter_summary 数据存入 course_knowledge_graph.json，不作为独立文件）
        │
        └── CHAPTER_SYNTHESIS_{chapter_dir_name}/  ← Layer 2：章节级产物（流程C生成，chapter_dir_name = 章节文件夹名）★
            ├── CHAPTER_SYNTHESIS_{chapter_dir_name}.md  ← 主学习文档（用户实际学习的文件）
            ├── CHAPTER_EXERCISES_{chapter_dir_name}.md  ← 全章练习题
            ├── CHAPTER_ANKI_{chapter_dir_name}.csv
            ├── CHAPTER_ANKI_{chapter_dir_name}.apkg     ← 导入 Anki 的文件
            └── chapter_completeness_audit.md
```

---

## 提示词文件索引

| 文件 | 用途 | 调用时机 |
|------|------|---------|
| `prompts/A1_subtitle_analysis.md` | 字幕分析 + 图谱比对 + **模式判断** | 流程A Step 3 |
| `prompts/A2_knowledge_gen.md` | 按模式生成知识文档（唯一输出：`knowledge_*.md`） | 流程A Step 4 |
| `prompts/B_batch_coordinator.md` | 多视频批量调度 | 流程B |
| `prompts/C_chapter_synthesis.md` | 章节综合 → 完整独立章节学习包（**每个 Pass 独立调用一次**：outline/synthesis/exercises/anki） | 流程C Step C3 |
| `prompts/0_standalone_system_role.md` | AI 角色设定（非 Skill 环境使用）| 独立 API 对话时作为 System Prompt |

---

## 课程范围

Java 全栈系列：Java 基础语法 · 面向对象 · 集合框架 · 异常与IO · 多线程与并发 · JVM 原理 · JDBC · Java Web · Maven/Gradle · Spring Framework · Spring Boot · Spring MVC · MyBatis/MyBatis-Plus · Spring Security · Spring Cloud · Redis · 消息队列

---

## Python 运行约定

```bash
# Windows
.venv\Scripts\python scripts/pipeline.py <command>
# macOS/Linux
.venv/bin/python scripts/pipeline.py <command>
```

## API 兼容性

工作流为 API 无关设计。预处理（Python 脚本）、知识生成（prompts/ 模板）、工具函数（MCP Server）均不依赖特定 LLM API。