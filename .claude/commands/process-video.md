# /process-video

处理单个 Java 教程视频（流程 A），生成视频级知识文档（`knowledge_{safe_stem}.md`）。

> **注意**：练习题、Anki 卡包是章节级产物，在所有章节视频处理完成后通过流程 C（`/batch-process` 末尾或手动触发章节综合）统一生成，**不在此命令中生成**。

## 使用方式

```
/process-video <video_path>
```

## 变量约定（复用参数）

- `WORKSPACE_ROOT`：项目根目录（示例：`<project-root>`）
- `COURSE`：课程目录名（示例：`Java基础-视频上`）
- `DAY`：章节目录名（示例：`day01-Java入门`）
- `VIDEO_FILE`：视频文件名（示例：`01-Java概述.mp4`）
- `VIDEO_PATH`：完整视频路径，推荐由前四项拼接：`portable-gpu-worker/videos/{COURSE}/{DAY}/{VIDEO_FILE}`
- `SAFE_STEM`：视频文件名（不含扩展名）中特殊字符（`:`、`*`、`?`、`"`、`<`、`>`、`|` 等）替换为 `_` 后的目录安全名，由 MCP 工具自动推断

实际执行时优先引用变量名，避免在不同机器上反复修改硬编码路径。

## 参数

- `<video_path>` — 视频文件路径（必须）
- `--skip-preprocess` — 跳过预处理检查（已有 .srt 和 frames/ 时使用）
- `--force` — 强制重新生成知识文档，覆盖已有 `knowledge_{safe_stem}.md`

## 输出产物

此命令**只生成视频级产物**：

```
portable-gpu-worker/output/{课程文件夹}/{章节文件夹}/{safe_stem}/
├── knowledge_{safe_stem}.md     ← 唯一产物（Full/Supplement/DeepDive/Practice 之一）
└── _preprocessing/              ← 预处理产物
    ├── *.srt
    ├── *_words.json
    ├── {safe_stem}_topics.json          ← A1 输出（含处理模式）
    ├── {safe_stem}_teaching_style.json  ← A1 输出
    └── frames/
        ├── *.jpg
        └── frames_index.json    ← 关键帧索引（A2 FRAMES_MAPPING 来源）
（注：chapter_summary 通过 update_knowledge_graph 存入 course_knowledge_graph.json，无独立文件）
```

章节级产物（`CHAPTER_SYNTHESIS_*.md`、`CHAPTER_EXERCISES_*.md`、`CHAPTER_ANKI_*.apkg`）
由流程 C 在所有章节视频完成后分多轮生成（outline → synthesis → exercises → anki，每轮独立响应）。

## 执行流程

### Step 0：环境检查

检查 `.venv/` 是否存在。如不存在，先运行：
```bash
python scripts/bootstrap.py
```

### Step 1：预处理检查

检查对应 `_preprocessing/` 目录下是否存在：
- `{video_stem}.srt`（字幕文件）
- `frames/` 目录（关键帧）

如不存在且未指定 `--skip-preprocess`，提示用户先使用 portable-gpu-worker 进行预处理：
- 将视频放入 `portable-gpu-worker/videos/{课程}/{章节}/`
- 运行 `0_开始使用.bat`，选择 **[3] 开始预处理**

### Step 2：调用 MCP 工具获取上下文

```
get_video_metadata(video_path)               → 视频时长/帧率等信息
check_preprocessing_status(video_path)       → 预处理产物状态（含 artifacts.frames_dir.frames_index_json）
align_frames_to_transcript(...)              → 【可选】帧-字幕对齐调试，非必须
query_knowledge_graph(concept_ids=[...])     → 查询已覆盖概念状态（按范围查，勿用 list_all）
```

**知识图谱查询**：根据视频文件名 + 目录路径预判本视频涉及的 10-15 个概念 ID，传入 `concept_ids` 参数按范围查询，避免 `list_all=true` 随课程增长大量消耗 Token。首次处理时图谱为空，可直接使用 Full Mode，跳过此查询。

### Step 3：加载 A1_subtitle_analysis.md — 字幕分析 + 模式判断

加载并执行 `prompts/A1_subtitle_analysis.md` 的完整流程：
- 字幕清洗与话题分段
- 与知识图谱比对
- 判断处理模式：**Full / Supplement / DeepDive / Practice**

输出并保存至预处理目录（`_preprocessing/`）：
  - `{safe_stem}_topics.json`
  - `{safe_stem}_teaching_style.json`

### Step 4：加载 A2_knowledge_gen.md — 知识文档生成

加载并执行 `prompts/A2_knowledge_gen.md`，按 Step 3 判定的模式生成对应知识文档：

| 模式 | 触发条件 | 文档特点 |
|------|---------|---------|
| **Full** | 大量全新概念 | 完整知识文档，含所有知识点、代码示例、关键帧 |
| **Supplement** | 已有概念的新侧面 | 只写增量内容，引用已有文档 |
| **DeepDive** | 已有概念达到更高深度 | 从当前深度切入，不重复基础 |
| **Practice** | 纯实操练习 | 极简步骤文档 + 操作记录 |

> **FRAMES_MAPPING 来源**：`check_preprocessing_status` 返回的 `artifacts.frames_dir.frames_index_json` 即为 A2 所需关键帧索引文件的完整路径，直接使用，无需手动构造路径。

输出：`knowledge_{safe_stem}.md`

### Step 5：保存产物

将 `knowledge_{safe_stem}.md` 保存到标准路径：
```
portable-gpu-worker/output/{课程文件夹}/{章节文件夹}/{safe_stem}/
```

### Step 6：更新知识图谱（强制执行，不可省略）

调用 MCP 工具：
```
update_knowledge_graph(
    video_stem=...,
    covered_concepts=[{concept_id, depth, aspect, summary}, ...],
    implicit_concepts=[...],
    processing_mode="Full|Supplement|DeepDive|Practice",
    chapter_summary="...",
    knowledge_doc_path=...
)
```

> ⚠️ **此步骤必须执行**：后续同章节视频的模式判断依赖知识图谱状态。

### Step 7：输出总结

```
✅ 视频处理完成！

📄 知识文档：output/{课程}/{章节}/{safe_stem}/knowledge_{safe_stem}.md
   - 处理模式：{Full/Supplement/DeepDive/Practice}
   - 知识点数量：{n}
   - 含关键帧：{n} 张
   - 知识图谱：已更新 {n} 个概念

💡 提示：练习题和 Anki 卡包在章节所有视频完成后，通过流程 C 统一生成。
```

## 示例

```bash
# 假设：COURSE=Java基础-视频上, DAY=day01-Java入门
/process-video "portable-gpu-worker/videos/{COURSE}/{DAY}/01-Java概述.mp4"
/process-video "portable-gpu-worker/videos/{COURSE}/{DAY}/02-JDK安装.mp4" --skip-preprocess
```
