# /batch-process

批量处理 Java 课程章节视频（流程 B），逐个执行流程 A，章节完成后询问是否触发流程 C 生成章节学习包。

> **架构说明**：
> - **视频级（流程 A）**：每个视频只生成 `knowledge_{stem}.md`，知识图谱实时更新
> - **章节级（流程 C）**：所有章节视频完成后，从头生成 `CHAPTER_SYNTHESIS`、`CHAPTER_EXERCISES`、`CHAPTER_ANKI`

## 使用方式

```
/batch-process [options]
```

## 变量约定（复用参数）

- `WORKSPACE_ROOT`：项目根目录（示例：`<project-root>`）
- `COURSE`：课程目录名（示例：`Java基础-视频上`）
- `DAY`：章节目录名（示例：`day01-Java入门`）
- `CHAPTER_KEY`：章节相对路径，格式：`{COURSE}/{DAY}`

实际调用参数时优先使用 `CHAPTER_KEY`，避免重复硬编码章节字符串。

## 参数

- `--all` — 处理选定章节的全部待处理视频，不逐个询问
- `--plan-only` — 仅输出处理计划，不实际执行
- `--resume` — 跳过已有 `knowledge_{stem}.md` 的视频（默认行为）
- `--chapter <章节路径>` — 指定处理的章节，如 `Java基础-视频上/day01-Java入门`

## 执行流程

### Step 0：环境检查

检查 `.venv/` 是否存在。如不存在，先运行：
```bash
python scripts/bootstrap.py
```

### Step 1：扫描章节视频

扫描 `portable-gpu-worker/videos/{课程}/{章节}/`，列出所有视频文件及处理状态：

```
📋 章节视频列表：Java基础-视频上/day01-Java入门
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 #   文件名                    时长       状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1  01-Java概述.mp4           28:30     ✅ 已完成
  2  02-JDK安装.mp4            15:20     🟡 已预处理
  3  03-HelloWorld.mp4         22:10     🟡 已预处理
  4  04-变量与类型.mp4          35:40     ⬜ 待预处理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅=已有 knowledge.md  🟡=有预处理产物  ⬜=无预处理产物
```

### Step 2：用户确认

如未指定 `--all`，展示处理计划并询问：
```
将处理 {n} 个视频，跳过 {m} 个已完成视频。
预处理不足的视频请先在 portable-gpu-worker 中处理。
确认继续？(y/n)
```

### Step 3：加载 B_batch_coordinator.md

读取 `prompts/B_batch_coordinator.md`，分析章节整体情况：
1. **依赖分析**：视频间的知识前置关系
2. **差量评估**：对照知识图谱，判断每个视频的预期处理模式（Full/Supplement/DeepDive/Practice）

### Step 4：逐个执行流程 A

对每个待处理视频，**按顺序**完整执行流程 A 全部 6 步（不可跳过或并行）：

```
处理中 [2/3]：02-JDK安装.mp4
  Step 1 预处理检查 ✅  (有 .srt + frames/)
  Step 2 MCP 工具调用：
    → check_preprocessing_status ✅
    → query_knowledge_graph → 模式判断：Supplement（JDK概念已在 01 中引介）
  Step 3 A1 字幕分析 ✅
  Step 4 A2 知识文档生成（Supplement 模式）✅
  Step 5 产物保存 ✅  output/Java基础-视频上/day01-Java入门/02-JDK安装/
  Step 6 知识图谱更新 ✅  已更新 3 个概念
```

> ⚠️ **每个视频的 Step 6（`update_knowledge_graph`）必须在下一个视频开始前完成**，否则后续视频的模式判断会基于过期的图谱状态。

产物输出结构：
```
portable-gpu-worker/output/{课程}/{章节}/{safe_stem}/
└── knowledge_{safe_stem}.md   ← 唯一视频级产物
    _preprocessing/
```

### Step 5：章节处理完成 → 询问是否执行流程 C

所有视频的 `knowledge_{safe_stem}.md` 生成完成后，提示用户是否执行章节综合（流程 C）：

```
所有 {n} 个视频已处理完成。是否立即执行流程 C（章节综合）生成章节学习包？
  y — 立即执行（生成 CHAPTER_SYNTHESIS、CHAPTER_EXERCISES、CHAPTER_ANKI）
  n — 跳过，稍后手动执行
```

若用户确认，按以下步骤执行流程 C（**每个 Pass 独立响应，严禁合并为一次**）：

1. **前置 MCP 工具调用**：
   - `read_chapter_summaries(chapter_dir)` → 获取所有视频摘要与知识图谱数据
   - `scan_chapter_completeness(chapter_dir)` → 生成待补全清单
2. **加载 `prompts/C_chapter_synthesis.md`，按 Pass 分轮生成**：
   - `PASS_MODE = "outline"` → 保存 `chapter_outline.json`（可选，中/大型章节建议执行）
   - `PASS_MODE = "synthesis"` → 使用**占位符追加链**逐组写入，生成并保存 `CHAPTER_SYNTHESIS_{章节名}.md`
   - `PASS_MODE = "exercises"` → 读取磁盘 synthesis 文件，生成并保存 `CHAPTER_EXERCISES_{章节名}.md`
   - `PASS_MODE = "anki"` → 读取磁盘 synthesis 文件，生成 CSV + 调用 `export_anki_package` 打包

最终产物保存在：
```
portable-gpu-worker/output/{课程}/{章节}/CHAPTER_SYNTHESIS_{章节名}/
├── CHAPTER_SYNTHESIS_{章节名}.md    ← 主学习文档（连贯全章，独立可读）★
├── CHAPTER_EXERCISES_{章节名}.md   ← 全章练习题（含不同难度 + 面试题专区）
├── CHAPTER_ANKI_{章节名}.csv        ← Anki CSV
├── CHAPTER_ANKI_{章节名}.apkg       ← Anki 卡包（可直接导入）★
└── chapter_completeness_audit.md   ← 本章待补全清单
```

> 章节级产物完全独立于视频级产物，基于 CHAPTER_SYNTHESIS 从零生成，而非拼接各视频文档。

### Step 6：输出总结

```
✅ 章节处理完成！

📊 处理统计：
   - 视频总数：{n}  已完成：{n}  跳过（已有）：{n}
   - Full 模式：{n} 个 | Supplement：{n} 个 | DeepDive：{n} 个 | Practice：{n} 个

📚 章节学习包：
   - CHAPTER_SYNTHESIS_{章节名}.md  — 主学习文档
   - CHAPTER_EXERCISES_{章节名}.md  — 练习题（{n} 题）
   - CHAPTER_ANKI_{章节名}.apkg     — Anki 卡包（{n} 张卡片）

📈 知识图谱：已累计 {n} 个概念
```

## 示例

```bash
/batch-process --chapter "{CHAPTER_KEY}"                  # 处理指定章节
/batch-process --all                                        # 处理全部待处理视频
/batch-process --plan-only                                  # 仅查看计划
/batch-process --resume                                     # 跳过已完成，断点续传
```
