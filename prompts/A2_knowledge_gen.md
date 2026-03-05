# A2 · Stage 2：知识文档生成

> 📌 **工作流位置**（对应 SKILL.md §工作流程 → 流程A Step 4）
> 上一步：`A1_subtitle_analysis.md` 产物（`{safe_stem}_topics.json` + `{safe_stem}_teaching_style.json`）
> 本步产物：`knowledge_*.md`（视频级唯一产物；练习题/Anki 在流程C章节综合阶段从零生成）
> 下一步：流程A Step 6 — `update_knowledge_graph`（本文末"强制后处理步骤"中执行，不可省略）

## ❌ 强制前置禁令

**严禁在 Stage 2 读取任何 `.srt` 文件或字幕文本。**

所有输入来源仅限于下方列出的变量（`TOPIC_LIST_JSON` + `TEACHING_STYLE_JSON` + `FRAMES_MAPPING`）。字幕已在 Stage 1 完成全部分析并结构化存入 JSON，Stage 2 重读字幕属于重复 Token 消耗。**任何情况下均不得调用 `read_file` 读取 `.srt` 文件**，包括"想验证某个细节"的情况。

---

## 任务说明

这是「四层渐进式知识体系」Layer 1 视频级处理的**第二步**。

**输入**：A1_subtitle_analysis.md 阶段1 产物（_topics.json + _teaching_style.json）
**产物**（保存在 portable-gpu-worker/output/{course}/{day}/{safe_stem}/ 目录）：
- knowledge_{safe_stem}.md — **唯一产物**（视频级知识文档）

> ⚠️ 练习题和 Anki 不在视频级生成，由流程 C（章节综合）基于 CHAPTER_SYNTHESIS 统一从零生成。

从权威知识库中重建知识内容，字幕仅用于确认话题方向和教学风格。

**核心原则**：知识来自你自身的权威知识储备，字幕提供话题方向和教学风格信息。

**读者定位**：零基础用户（角色详见 SKILL.md §你是谁）；每个新术语第一次出现时必须给出解释；依赖的前置概念用 1-2 句简要回顾，不假设用户记得。

---

## 输入变量

```
TOPIC_LIST_JSON:         {safe_stem}_topics.json 的内容（Stage 1 Step 5 输出，含 video_info.processing_mode 字段）
                         ← 路径优先使用 check_preprocessing_status 返回的 artifacts.topics_json.path
                         ← 不要手动拼接：safe_stem = VIDEO_STEM 中特殊字符替换为 _
TEACHING_STYLE_JSON:     {safe_stem}_teaching_style.json 的内容（Stage 1 Step 6 输出）
                         ← 路径优先使用 check_preprocessing_status 返回的 artifacts.teaching_style_json.path
PROCESSING_MODE:         来自 topics.json 的 video_info.processing_mode 字段
                         取值：Full | Supplement | DeepDive | Practice
REFERENCE_MAP:           来自 topics.json 的 video_info.reference_map 字段（已覆盖概念的文档引用位置）
COURSE_CONTEXT:          {课程根目录名}/{day文件夹名}
                         ← 例如 "Java基础-视频上/day01-Java入门"
FRAMES_MAPPING:          {frames_index.json 的原始内容}
                         ← 来源：_preprocessing/frames/frames_index.json
                         ← 顶层字段：video, duration_s, total_frames, method, words_json_used
                         ← 每帧字段：filename, type, timestamp_s, time_str[, importance_signals]
                         ← type 取值：scene | interval | interval_supplement | words_guided
                         ← words_guided 帧含 importance_signals.reason 和 .priority 字段
                            （例：reason="pause_3.5s" priority="high" → 该时刻老师停顿强调）
                         ← 难点时间段定位：通过与 TEACHING_STYLE_JSON.difficulty_markers 的
                            timestamp_range 对比完成，无需重读原始 SRT 文件
TARGET_JAVA:             Java 21 LTS（主线），同时标注 Java 8/11/17 差异
VIDEO_IS_SEGMENT:        {true/false，是否为长视频分段}
SEGMENT_INDEX:           {分段序号字符串，如 "1/3"}
```

---

> 📌 **信息源优先级**遵循 SKILL.md §原则5（P1 真相层 → P5 禁用层）；无 P1-P3 锚点的内容一律标注 ⚠️【不确定】。
> 引用格式：正文中以 `> 来源：{P1/P2/P3 锚点}` 注明。

---

## 教学风格运用原则

> 📎 提取维度定义见 SKILL.md §原则6；以下为在**文档写作**中的具体运用规则。

在生成知识文档前，**先读取 `TEACHING_STYLE_JSON`**，提取以下信息并在写作中运用：

1. **类比复用**：老师在视频中使用的类比（如"HashMap 就像字典"），知识文档中优先沿用相同类比
2. **切入方式匹配**：老师的 `teaching_approach` 是"problem_first"，文档也用问题切入；若是"code_first"，文档也先给代码
3. **难点标记**：`difficulty_markers` 中标注的时间段对应的知识点，在文档中**额外展开**（多给例子、多给图示）
4. **节奏对齐**：老师花了较多时间讲的话题，文档篇幅相应放大；一笔带过的话题，文档也简洁处理
5. **强调点保留**：`emphasis_points` 中的内容，在文档中用**加粗**或专门的段落特别强调

---

## 知识深度适配规则

**最重要的原则之一。不要把简单问题复杂化，也不要对复杂问题浅尝辄止。**

### 规则优先级（先判高优先级，命中则不再看低优先级）

**优先级 1（最高）：`relevance_to_course` — 该 segment 该不该写**

> 该字段由 A1 Step 3 写入每个 segment，表示该话题段与课程学习目标的关联性。
> 只要此字段不为 `"direct"`，`pace` / `difficulty_level` 规则一律失效，不得套用。

| 值 | 行为 |
|---|---|
| `"tangent"` | 完全跳过，不写任何内容；与 `skip: true` 效果相同但原因不同（相关性问题，非信号质量问题） |
| `"historical_story"` | 完全跳过，不写任何内容（同 `"tangent"` 处理） |
| `"motivational"` | **完全跳过，不写任何内容**（同 `"historical_story"` / `"tangent"` 处理）；励志话语、行业数据、学习价值等非技术内容一律不进入知识文档 |
| `"direct"` | 进入下方优先级 2 的 `pace + difficulty_level` 规则正常处理 |

---

**优先级 2（仅当 `relevance = "direct"` 时）：`pace` + `difficulty_level` — 写多深**

判断一个知识点应该讲多深，参考以下三个维度：

| 维度 | 判断方法 |
|------|---------|
| 视频深度 | 老师在 SRT 中花了多少时间？ `pace: slow` 且 `is_difficulty_peak: true` = 重点深讲 |
| 权威来源深度 | JavaGuide 对该话题的覆盖深度；《Effective Java》是否有专门 Item |
| 学习阶段 | 课程的 day/序号；day01-05 通常是基础，不延伸到 JVM 内部实现 |

**具体规则：**

- **`beginner` + `pace: fast`**：1-2 段，给定义 + 一句类比 + 一个简单代码示例即可
- **`beginner` + `pace: slow`（老师重点讲）**：3-5 段，展开类比 + 代码演示 + 常见陷阱
- **`intermediate`**：完整讲解 + 陷阱 + 与其他概念对比
- **`advanced`**：完整讲解 + 底层原理 + 版本差异（仅当学习阶段匹配时）

**严禁行为**：
- ❌ 在讲"变量定义"时展开介绍 JVM 栈帧内存布局
- ❌ 在讲"数组基础"时介绍泛型协变/逆变
- ❌ 对老师快速带过的知识点（`pace: fast`）写超过2段的说明
- ❌ 对 `relevance ≠ "direct"` 的 segment 套用 pace/difficulty 规则展开（relevance 已定性，pace 规则不再生效）

---

## 处理模式总览（阶段1 Step 4c 已决定，此处执行）

**在生成任何产物之前，先读取 `PROCESSING_MODE` 确定行为模式。**

> 📎 模式已由 A1 Stage 1 Step 4c 决定并写入 `topics.json`，此处直接按对应模式执行行为，无需重新判断触发条件。触发条件定义见 SKILL.md §Stage 1 内部决策表。

---

### Full Mode（完整模式）— `PROCESSING_MODE = "Full"`

行为：
- 按正常流程生成完整知识文档
- **对 `REFERENCE_MAP` 中 depth≥2 的已知概念**：只写一句引用（如"JDK/JRE/JVM 的概念已在 [day01/01 §3] 介绍"），不重新展开解释
- **对 `implicit_concepts` 中的隐性概念**（已在代码中出现过的）：在正式讲解时加一句"你在 {视频} 的代码示例中已经见过这个词了"

---

### Supplement Mode（补充模式）— `PROCESSING_MODE = "Supplement"`

> 典型场景：同一概念的新侧面，深度不变（如"JDK 概念已有，本节是安装步骤"）。

行为：

**知识文档结构固定为**：
```markdown
# {视频名} · {核心主题}

> 📎 本节在以下内容的基础上展开（请先阅读）：
> - [{已有文档名} §{章节}]({路径})：{一句话说明已覆盖内容}

{新内容正文 — 与已有文档不重叠}

> 来源：{P1-P3 锚点}
```

**固定规则**：
- 文档开头**必须**有"📎 前置阅读"引用块
- 正文只写本视频带来的**新侧面**（安装步骤 / 命令行操作 / 代码演示 / 实际使用案例）
- 绝对不重复解释引用块中已有文档覆盖的概念
- **漏洞修复**：若本视频虽是"补充"但在某概念上达到了更高深度（Δdepth≥1），则对该概念使用 DeepDive 局部模式写一个加深小节

---

### DeepDive Mode（深化模式）— `PROCESSING_MODE = "DeepDive"`

典型场景："JVM 内存结构详解"（JVM 在 day01 引介过，这里到第 3 层原理）。

行为：

**知识文档结构固定为**：
```markdown
# {视频名} · 深化：{概念名}

> 🔍 本节是 [{概念}] 的深化讲解（第 {N} 层：{层级名称}）
> 前置阅读：[{引介文档} §{章节}]({路径}) — 建议先看完再读本节
>
> 本节侧重：{本节聚焦的新方面，如"底层原理 / 性能调优 / 源码分析"}

{直接从该深度切入，不重复引介层的内容}
```

**固定规则**：
- **直接从新深度展开**，不重复已在引介文档中解释过的基础
- 文档中可有"回顾"小节（一句话），但只是导航，不是重新解释
- **漏洞修复**：对于深化文档中偶尔出现的"新概念附带品"（DeepDive 视频里顺带引入的新知识点），为这些新概念使用标准 Full 模式局部处理并记入图谱

---

### Practice Mode（实操模式）— `PROCESSING_MODE = "Practice"`

典型场景："CMD 操作练习"、"HelloWorld 跑起来"。

行为：

**知识文档结构固定为**：
```markdown
# {视频名} · 实操：{操作主题}

> ⚡ 本节为实操练习，知识前提见：[{前置文档}]({路径})

## 操作步骤

1. {步骤1}
2. {步骤2}

## 验证方式

{如何确认操作成功}

## 🔍 你在本节代码/操作中见到了这些"新面孔"

> 以下内容现在不需要理解，只是提前打个招呼，后续章节会正式讲解：
> - `public class`、`static`、`void` — 将在 OOP 章节学习
> - `String[] args` — 将在数组/String 章节学习
```

**固定规则**：
- 极简知识文档（操作步骤为主，不超过 1000 字）
- **隐性知识一定要有"新面孔"列表**，明确告诉用户这些词现在先认个脸，后面会学

---

## 产物 1：知识文档（主文档）

**格式原则**：流畅的教学文档，而非刚性的"卡片表格"。每个章节根据知识点复杂度灵活调整篇幅和结构，不强制每个知识点都有相同的固定子节。

**Full Mode 使用以下模板；Supplement/DeepDive/Practice 模式使用上方对应的固定结构。**

→ 完整格式结构见 `templates/knowledge_doc.md`（含各模式头部、知识点节格式）

**知识点写法由 `pace` 和 `is_difficulty_peak` 决定（三档）：**
- `beginner` + `pace: fast` → **轻量**：2-4段自然段落，定义→类比→代码
- `beginner` + `pace: slow` 或 `intermediate` → **标准**：切入段→概念段→前置回顾（可选）→图示/表格→代码→陷阱（可选）
- `is_difficulty_peak: true` 或 `advanced` → **深度**：背景切入→完整概念→图示→代码演示→底层原理（当阶段合适时）→陷阱（必须有反例）→版本差异（有时）

每节末尾均附：`> 来源：{P1/P2/P3 锚点}`

---

### 关键帧插入规则（核心规则，严格执行）

**不是所有关键帧都插入知识文档，只在真正有意义的位置插入。**

**三步判断法：**

**第一步：该帧类型是否有内容价值？**
（读取 `FRAMES_MAPPING` 中 `frames` 数组，每个帧对象包含 `filename`、`timestamp_s`、`type` 字段）
- `type: "scene"`（PySceneDetect 场景切换帧）= 画面内容发生变化，可能有价值 → 进入第二步
- `type: "words_guided"`（词级时间戳引导帧）= 老师语速骤降/停顿/关键词密集的时刻
  - 若 `importance_signals.priority = "high"` → **直接建议插入**（通常已是难点）
  - 若 `importance_signals.priority = "medium"` → 进入第二步进一步验证
- `type: "interval_supplement"`（定时补充帧）= 场景检测成功时用于填补 >60s 时间空白的间隔帧，默认不插入，除非后续判断为难点
- `type: "interval"`（内容无关）= 场景检测失败时的兄底间隔帧，**默认不插入**

**第二步：该帧时间戳是否落在难点区间？**
参考 `TEACHING_STYLE_JSON` 中的 `difficulty_markers`：
- 若帧的时间戳落在某个 `difficulty_markers` 的 `timestamp_range` 内，且 `keyframe_priority: "high"` → **强烈建议插入**
- 若落在 `emphasis_points` 的时间戳附近（±30秒）→ **建议插入**
- 若不在任何难点区间 → **不插入**

**第三步：该帧是否与当前知识点直接相关？**
- 帧时间戳必须与正在讲解的知识点时间范围（来自 `TOPIC_LIST_JSON` 的 `time_range`）重叠
- 即使满足第二步，若帧属于其他话题时段 → **不插入到当前知识点**

**只有同时满足三个步骤判断"应插入"的帧，才在知识点下插入：**

```markdown
![{对帧内容的描述：如"老师演示 HashMap.put 流程" 或 "板书展示 GC Roots 引用链"}](_preprocessing/frames/{filename})
> *📍 视频 {HH:MM:SS} — {描述帧内容：代码演示 / 板书 / PPT图表 / 运行结果}*
```

**对于课程引导类视频（无技术演示）**：几乎不插入关键帧。如有片头场景帧，可在文档顶部插一张作为视觉引导，但不在技术内容章节中插入。

---

### 文档尾部

文档末尾干净结束，不附练习链接。章节学习包（`CHAPTER_SYNTHESIS`）是用户实际学习的主体，视频级知识文档作为原材料和细节溯源使用。

**长视频分段处理**（`VIDEO_IS_SEGMENT: true`）：
- 标题中标注分段：`# 知识文档：{节名}（第 {SEGMENT_INDEX} 部分）`
- 知识点编号连续递增，不因分段重置
- 第2段起，开头补一句"上段回顾"

---

## 产物输出：只输出一个文件

**保存**：`knowledge_{safe_stem}.md` → `portable-gpu-worker/output/{course}/{day}/{safe_stem}/`

> 练习题、Anki CSV/apkg **不在视频级生成**。这些在流程 C（章节综合）阶段统一生成，覆盖全章所有知识点，质量更高、体系更完整。

---

## 特殊视频类型处理

### 课程引导 / 工具安装 / 环境配置类视频

此类视频（课程类别为"课程引导"）的知识文档：
- 不套用常规知识点模板
- 从视频提及的技术概念出发，建立"全局认知地图"（本节处理的就是这类）
- 重点讲解后续课程会用到的核心概念，篇幅适中（2-4个主要概念，每个2-3段）
- 结尾给出学习路线图

### Spring Boot 相关视频

- 标注所需 Starter 依赖（Maven/Gradle）
- 给出 application.yml 配置示例
- 标注 Spring Boot 2.x vs 3.x 差异（javax → jakarta）

### 含已废弃特性的视频

- 标注 🚫【Java {版本} 已废弃/已移除】
- 给迁移指南，不推荐使用废弃 API

---

## 强制后处理步骤：更新知识图谱

**所有产物生成完毕后，必须立即调用 `update_knowledge_graph` MCP 工具**，将本视频覆盖的知识点写入图谱，否则后续视频无法正确判断处理模式。

调用时提供：
- `video_stem`：视频文件名
- `video_path`：视频完整路径（用于在图谱 video_index 中记录来源位置）
- `processing_mode`：本次使用的模式
- `knowledge_doc_path`：生成的知识文档路径
- `covered_concepts`：本文档正式讲解的每个概念（含 concept_id、depth、aspect、summary）
- `implicit_concepts`：代码中出现但未正式解释的概念（来自 topics.json 的 implicit_concepts）
- `chapter_summary`：2-3 句话概括本视频知识文档的核心内容

---

## 质量检查清单

生成完成后，对照以下清单自检：

- [ ] **处理模式正确**：按 `PROCESSING_MODE` 使用了对应的文档结构
- [ ] **Supplement/DeepDive 模式**：文档开头有"📎 前置阅读"或"🔍 深化标注"引用块
- [ ] **Practice 模式**：文档末尾有"新面孔"列表，标注了隐性知识的后续学习位置
- [ ] **Full 模式中**：`REFERENCE_MAP` 中 depth≥2 的概念只有引用，没有重新展开解释
- [ ] 知识文档中**没有**"面试高频"等面试标签（面试内容在章节练习文档中）
- [ ] 知识文档中每个新术语**首次出现时**都有解释
- [ ] 关键帧**只出现在**通过三步判断法确认的位置
- [ ] 文档末尾干净结束（无练习索引表、无练习链接）
- [ ] 已调用 **`update_knowledge_graph`** 更新图谱（强制，最后一步，不可省略）
