# A1 · Stage 1：字幕分析 + 话题分段 + 图谱比对 + 处理模式判断

> 📌 **工作流位置**（对应 SKILL.md §工作流程 → 流程A Step 3）
> 上一步：流程A Step 2 — MCP 工具调用（`query_knowledge_graph` 结果作为 `KNOWLEDGE_GRAPH_DATA` 传入）
> 本步产物：`{safe_stem}_topics.json` + `{safe_stem}_teaching_style.json`（保存至 `_preprocessing/`；`safe_stem` = 特殊字符替换为 `_` 后的视频名）
> 下一步：`A2_knowledge_gen.md`（读取以上两个文件，只生成知识文档 `knowledge_{safe_stem}.md`）

## 任务说明

这是「四层渐进式知识体系」Layer 1 视频级处理的**第一步**。

**本阶段产物**（保存在 _preprocessing/ 目录）：
- {safe_stem}_topics.json — 话题清单（含处理模式 Full/Supplement/DeepDive/Practice）
- {safe_stem}_teaching_style.json — 教学风格简报（类比、节奏、难点时间段）

**下一步**：使用 A2_knowledge_gen.md 读取这两个 JSON，只生成知识文档（`knowledge_*.md`）。练习题和 Anki 在流程 C 章节综合阶段统一生成。

你有两个核心任务：
1. **话题分段**：从有噪声的字幕中提取结构化话题清单（不是知识内容）
2. **教学风格提取**：分析老师的讲解方式，为第二阶段生成教学质量更高的知识文档

**两个任务的输出都要保存到与字幕文件相同的 `_preprocessing/` 目录下。**

---

## 输入变量

```
VIDEO_FILENAME:       {VIDEO_FILENAME}
DIRECTORY_PATH:       {DIRECTORY_PATH}
VIDEO_STEM:           {VIDEO_STEM}          ← 不含扩展名的文件名，用于命名输出文件
PREPROCESSING_DIR:    {PREPROCESSING_DIR}   ← _preprocessing/ 目录路径
DURATION:             {DURATION}
VIDEO_IS_SEGMENT:     {true/false，是否为长视频分段}
SEGMENT_INDEX:        {分段序号，如 "1/3"（第1段/共3段），非分段时为 null}
SUBTITLE_TEXT:
---
{SUBTITLE_TEXT}
---

> ⚠️ **字幕来源说明**（调用本提示词前获取 SUBTITLE_TEXT 的方式）：
> - **非分段视频**（`is_segmented=false`）：读取 `check_preprocessing_status` 返回的 `artifacts.srt.path`
> - **分段视频**（`is_segmented=true`）：`artifacts.srt.path` 可能不存在，应逐一读取 `artifacts.srt.srt_paths` 列表中的各段 SRT 文件并拼接为 SUBTITLE_TEXT；`SEGMENT_INDEX` 需设为当前段序号（如 "1/3"）

WORDS_JSON_AVAILABLE: {true/false，词级时间戳是否可用}
KNOWLEDGE_GRAPH_DATA: {query_knowledge_graph(concept_ids=[...]) 的返回内容，JSON 格式}
                      ← 在调用本 Stage 1 前，AI 助手需先根据视频文件名 + 目录预判概念范围，
                         再调用 query_knowledge_graph(concept_ids=[预判列表]) 获取此数据
                      ← 仅返回与本视频相关的概念子集，不用 list_all=true（避免图谱庞大时 Token 膨胀）
                      ← 若图谱为空（首次运行）或 MCP 不可用，填入空对象 {} 直接使用 Full Mode
```

---

## 🔧 字幕预压缩（在执行步骤之前）

收到 `SUBTITLE_TEXT` 后，**在执行任何分析步骤之前**，先在脑内对字幕做以下三步压缩，压缩结果作为后续所有步骤的 `SUBTITLE_TEXT`：

1. **去结构行**：删除所有序号行（`1`、`2`、`3`...）和时间戳行（`HH:MM:SS,mmm --> HH:MM:SS,mmm` 格式），只保留字幕文字
2. **去连续重复**：相同文字连续出现 ≥ 2 次（Whisper 重复幻觉），只保留 1 条
3. **合并断句**：明显属于同一句子但被切成多行的相邻行，拼接为一行

> 时间戳信息已通过 `FRAMES_MAPPING`（`frames_index.json`）和 `words_json` 保存，字幕行中的时间戳不再需要。压缩后文本体积预期减少 35-50%。

---

## 执行步骤

### Step 1：话题边界框定

根据 `VIDEO_FILENAME` 和 `DIRECTORY_PATH`，判断本视频的核心教学主题。

同时判断课程类别（与 config.yaml 的 course_scope 一致）：
- Java 基础语法
- Java 面向对象
- Java 集合框架
- Java 异常与 IO
- Java 多线程与并发
- JVM 原理
- JDBC 数据库编程
- Java Web (Servlet/JSP)
- Maven/Gradle 构建工具
- Spring Framework
- Spring Boot
- Spring MVC
- MyBatis / MyBatis-Plus
- Spring Security
- Spring Cloud 微服务
- Redis 与缓存
- 消息队列 (RabbitMQ/Kafka)
- 课程引导（课程介绍/工具安装/环境配置类视频）
- 其他

输出：
```
本视频核心主题：{主题名称}
课程类别：{类别}
预期知识点范围（上限15个）：
  1. {知识点1}
  2. {知识点2}
  ...
本视频学习目标（用户学完后能做/知道什么）：
  {1-2 句可操作的结论，而非知识领域的罗列}
  正确示例："能用 Win+R 打开 CMD；理解 CMD 是命令行工具及其用途"
  错误示例："了解人机交互历史和 GUI/CLI 相关知识"
```

这个学习目标将作为 Step 3 中判断 `relevance_to_course` 的基准——只有直接服务于该学习目标的 segment 才标记为 `"direct"`。

### Step 2：噪声类型扫描

扫描字幕，识别以下噪声（仅标注位置，不修改原文）：

| 噪声类型 | 识别方式 |
|---------|---------|
| 技术术语识别错误 | 语义突变、不合上下文的词 |
| 代码片段断裂 | 出现不完整的标识符、括号不匹配 |
| 话题转换点 | 讲师明显切换话题、出现"下面我们来看"类型的过渡语 |
| 幻觉句子 | 与上下文完全无关、内容突兀的句子 |
| Spring/框架特有噪声 | 注解名称识别错误（如 @Autowired → @Auto Wired）、包名断裂 |

输出（扫描报告，简洁）：
```
噪声扫描报告：
  ⚠ [约 00:03:12] 技术词汇疑似识别错误："繁荣" → 可能是"泛型"
  ⚠ [约 00:07:45] 代码片段断裂：出现"Hash Map String Integer"
  ⚠ [约 00:15:20] 注解识别错误："at auto wired" → 可能是"@Autowired"
  🔀 [约 00:05:00] 话题转换点检测
  🔀 [约 00:12:30] 话题转换点检测
  ...
```

### Step 3：话题分段

**以话题转换点为边界**进行分段（不按时间均分）。

每个 segment 必须填写 `relevance_to_course` 字段，判断依据是 **Step 1 推断的学习目标**：
- 该段内容直接帮助用户完成学习目标中的动作/认知 → `"direct"`
- 该段解释了"为什么要学"，但无可操作知识 → `"motivational"`
- 历史故事、人物轶事，与学习目标操作层面无关 → `"historical_story"`
- 与本视频/本课程完全偏题  → `"tangent"`

每段输出：

```json
{
  "segment_id": 1,
  "time_range": "00:00:00 - 00:05:00",
  "core_topic": "Java 集合框架概述",
  "course_category": "Java 集合框架",
  "keywords": ["Collection", "List", "Map", "Set", "迭代器"],
  "noise_corrections": [
    {"original": "繁荣", "corrected": "泛型", "confidence": "high"},
    {"original": "at auto wired", "corrected": "@Autowired", "confidence": "high"}
  ],
  "signal_quality": "良",
  "signal_quality_reason": "字幕完整，技术词汇识别基本准确",
  "difficulty_level": "beginner",
  "difficulty_reason": "介绍基础概念，无复杂原理",
  "is_difficulty_peak": false,
  "difficulty_peak_reason": null,
  "pace": "normal",
  "estimated_knowledge_points": 3,
  "relevance_to_course": "direct",
  "relevance_reason": "直接讲解 CMD 是什么，是本视频学习目标的核心内容",
  "skip": false
}
```

字段说明：
- `signal_quality`：**优** / **良** / **差** / **极差**（极差时 `skip: true`）
- `difficulty_level`：**beginner** / **intermediate** / **advanced**
- `is_difficulty_peak`：该段是否是整个视频的难点高峰（true 时，Stage 2 知识文档需要更详细展开，且关键帧优先插入此处）
- `pace`：**fast**（快速讲过）/ **normal**（正常节奏）/ **slow**（放慢细讲，通常是难点）
- `relevance_to_course`：该段话题与视频学习目标的关联性（影响 A2 是否展开该段内容）
  - `"direct"`：直接服务于视频学习目标的操作/知识 → A2 正常展开
  - `"motivational"`：仅解释"为什么学"，无可操作知识（励志话语、学习价值宣传、行业数据等）→ A2 **完全跳过**，不写任何内容（同 `"historical_story"` / `"tangent"` 处理）
  - `"historical_story"`：历史故事、人物轶事、行业八卦，与学习目标无操作关联 → A2 完全跳过，不写任何内容（同 `"tangent"` 处理）
  - `"tangent"`：与当前课程方向完全无关 → A2 完全跳过
- `skip`：是否因**信号质量极差**跳过该段（`signal_quality: "极差"` 时设为 `true`）
  > ⚠️ `skip: true` 与 `relevance: "tangent"` 是两个独立的"不写"路径，不要混用：
  > `skip: true` = 字幕不可读，无法判断内容；`relevance: "tangent"` = 字幕可读但内容与课程无关

### Step 4：知识图谱比对 + 处理模式判断

> **本步骤产出的字段写入位置**：
> - `processing_mode`、`mode_reason`、`new_concept_ratio`、`max_depth_delta`、`reference_map` 等 → 合并到 topics.json 的 **`video_info`** 字段（Step 5 JSON 模板中已展示）
> - `implicit_concepts` → topics.json 的顶层 **`implicit_concepts`** 字段（Step 5 JSON 模板中已展示）

---

#### 4a. 图谱比对

对 Step 3 输出的每个话题 segment，查找 `KNOWLEDGE_GRAPH_DATA` 中是否存在对应概念：

```
对每个 segment：
  1. 在图谱中查找该话题对应的概念（concept_id）
  2. 如存在：
       a. 记录已有深度 current_depth
       b. 判断本视频对该概念的深度：是否比已有的更深？（Δdepth = 预期新深度 - current_depth）
       c. 判断本视频覆盖的面：是否是已有 aspects_covered 之外的新面？
  3. 如不存在 → 标记为"全新概念"
  4. 检查图谱中 first_implicit_video（非空）→ 若有，说明用户见过但未学，Stage 2 可加"你已见过这个"提示
```

#### 4b. 隐性知识扫描（Implicit Knowledge Scanner）

扫描字幕中出现的**代码片段、命令行操作、特殊关键字**，提取"在 SRT 中可见但老师没有口头解释的概念"：

重点扫描：
- 出现在代码框或命令中的 Java 关键字（`public`、`class`、`static`、`void`、`import` 等）
- 工具命令（`javac`、`java`、`mvn`、`git` 等）
- 类名/方法名（如 `System.out.println`、`String`、`Scanner` 等）

对每个发现的隐性概念，判断：
- 是否已在图谱中正式解释（`current_depth ≥ 1`）？→ 跳过（已学）
- 是否图谱中已有 `first_implicit_video` 字段（已隐性标记过）？→ 记录但不作为新概念
- 完全未出现过？→ 记录为"代码中首次出现"，后续 Stage 2 文档需加一句"我们会在后续章节正式学习 XX"

输出格式（追加到 topics.json 的 `implicit_concepts` 字段）：

> `concept_id` 命名约定：`java.` 前缀 + snake\_case 描述名。例：`System.out.println` → `java.system_out_println`；`public class` → `java.public_keyword`；`void` → `java.void_keyword`。

```json
"implicit_concepts": [
  {
    "concept_id": "java.system_out_println",
    "display_name": "System.out.println",
    "context": "HelloWorld.java 代码演示中出现",
    "depth_in_graph": 0
  }
]
```

#### 4c. 处理模式判断

> 📎 四种模式的触发条件摘要、文档特征和局部切换规则，见 SKILL.md §流程A → Stage 1 内部决策表。此处给出精确计算算法：

基于比对结果，按以下规则确定本视频的处理模式：

```
计算指标：
  - new_concept_ratio = 全新概念数 / 总话题数
  - max_depth_delta = max(各已有概念的 Δdepth)
    （Δdepth = 本视频预期深度 - 图谱中当前深度）

模式判断：
  IF new_concept_ratio ≥ 0.60 OR max_depth_delta ≥ 2:
    → Full Mode（完整知识文档）

  ELIF new_concept_ratio BETWEEN 0.20 AND 0.59 AND max_depth_delta ≤ 0:
    → Supplement Mode（补充模式：只写新内容，引用已有概念）

  ELIF new_concept_ratio < 0.30 AND max_depth_delta ≥ 1:
    → DeepDive Mode（深化模式：同一概念更深层的展开，不重复基础）

  ELIF new_concept_ratio < 0.20 AND max_depth_delta ≤ 0:
    → Practice Mode（实操模式：极简文档 + 丰富练习）

  ELSE:
    → Full Mode（默认兜底）
    ← 覆盖未被以上条件明确捕获的组合，例如：
       ratio 0.30-0.59 且 max_depth_delta = 1（有一定新内容+有一个概念要加深），
       此类情况生成完整文档最为稳妥

  EDGE CASE: 若 KNOWLEDGE_GRAPH_DATA 为空（首次处理）→ Full Mode
```

模式判断结果，追加到 topics.json 的 `video_info` 字段：
```json
"processing_mode": "Full",
"mode_reason": "70% 话题为全新概念（JVM/JRE/JDK、字节码、JIT 均首次出现）",
"new_concept_ratio": 0.75,
"max_depth_delta": 0,
"concepts_already_covered": [],
"concepts_to_deepen": [],
"full_new_concepts": ["java.jvm_jre_jdk", "java.bytecode", "java.jit", "java.gc"],
"reference_map": {
  "java.jvm_jre_jdk": {
    "existing_doc": "day01/01-Java学习介绍/knowledge_01.md#3",
    "existing_depth": 1,
    "new_depth": 2,
    "mode": "deepen"
  }
}
```

---

### Step 5：输出结构化话题清单

以 JSON 格式输出完整的话题清单，保存路径：`{PREPROCESSING_DIR}/{safe_stem}_topics.json`

```json
{
  "video_info": {
    "filename": "{VIDEO_FILENAME}",
    "directory": "{DIRECTORY_PATH}",
    "duration": "{DURATION}",
    "core_topic": "本视频核心主题",
    "course_category": "课程类别",
    "video_is_segment": false,
    "segment_index": null,
    "processing_timestamp": "ISO 8601 时间戳",
    "output_path": "{PREPROCESSING_DIR}/{safe_stem}_topics.json",
    "processing_mode": "Full",
    "mode_reason": "70% 话题为全新概念",
    "new_concept_ratio": 0.75,
    "max_depth_delta": 0,
    "concepts_already_covered": [],
    "concepts_to_deepen": [],
    "full_new_concepts": ["java.jvm_jre_jdk", "java.bytecode"],
    "reference_map": {
      "java.jvm_jre_jdk": {
        "existing_doc": "day01/01-Java学习介绍/knowledge_01.md#3",
        "existing_depth": 1,
        "new_depth": 2,
        "mode": "deepen"
      }
    }
  },
  "segments": [
    // 上面格式的所有分段
  ],
  "implicit_concepts": [
    {
      "concept_id": "java.system_out_println",
      "display_name": "System.out.println",
      "context": "HelloWorld.java 代码演示中出现",
      "depth_in_graph": 0
    }
  ],
  "summary": {
    "total_segments": 0,
    "skipped_segments": 0,
    "unique_topics": [],
    "overall_signal_quality": "良",
    "overall_difficulty": "beginner",
    "difficulty_peaks": [
      {"segment_id": 3, "topic": "HashSet 去重原理", "reason": "老师放慢节奏反复解释"}
    ],
    "noise_warnings": [],
    "suggested_prerequisites": [
      "建议先学: {前置知识}"
    ]
  }
}
```

> ⚠️ **重要**：`video_info.processing_mode`、`video_info.reference_map`、`implicit_concepts` 是 A2 Stage 2 的**必读字段**，缺少任一字段将导致 A2 无法正确选择处理模式或定位已有文档引用。不可省略。

### Step 6：教学风格提取（与 Step 5 并行输出）

分析字幕中老师的讲解风格，为 Stage 2 生成教学质量更高的知识文档提供依据。

**提取维度：**

#### 6.1 类比与比喻
扫描字幕中 "就像/好比/相当于/想象一下/你可以把它理解为" 等词语前后的句子。

输出格式：
```json
{
  "analogies": [
    {
      "timestamp": "00:12:30",
      "concept": "HashMap",
      "analogy": "就像一本字典，通过拼音索引快速找到词条",
      "original_quote": "你可以把HashMap想象成一本字典..."
    }
  ]
}
```

#### 6.2 节奏分析
统计每个话题段的时间跨度，换算为"每个知识点平均讲解时长"。时间越长 = 越重要或越难。

```json
{
  "pace_analysis": [
    {
      "segment_id": 1,
      "topic": "HashMap 概述",
      "duration_s": 120,
      "pace": "slow",
      "importance_signal": "high"
    }
  ],
  "avg_seconds_per_topic": 90
}
```

#### 6.3 强调点识别
识别以下语言特征（通常意味着重点）：
- "一定要记住" / "非常重要" / "这里很关键" / "必须要掌握"
- 同一概念在短时间内出现3次以上
- "接下来我们把这个搞清楚"

```json
{
  "emphasis_points": [
    {
      "timestamp": "00:08:15",
      "keyword": "hashCode",
      "signal": "老师说：'这个地方一定要记住'",
      "intensity": "high"
    }
  ]
}
```

#### 6.4 讲解切入方式
识别老师如何开始一个新话题：
- **问题驱动**："我们来想一个问题..."
- **场景驱动**："假设你现在需要..."
- **对比驱动**："之前我们学了...现在..."
- **直接定义**："XX 是指..."
- **代码先行**："我们先写一段代码..."

```json
{
  "teaching_approach": "problem_first",
  "approach_examples": [
    {"timestamp": "00:03:00", "approach": "problem_first", "quote": "我们来想一个问题，如果要存10000个用户..."}
  ]
}
```

#### 6.5 难点位置（结合 words.json）
如果词级时间戳可用（`WORDS_JSON_AVAILABLE: true`），分析以下特征以识别难点：
- 讲话语速突然降低（词级时间戳间隔变大）
- 出现长停顿（词间隔 > 2秒）
- 同一词汇短时间内重复出现

```json
{
  "difficulty_markers": [
    {
      "timestamp_range": "00:15:00 - 00:18:30",
      "topic": "GC 可达性分析",
      "signals": ["语速下降30%", "停顿3次", "重复提及'引用链'"],
      "keyframe_priority": "high"
    }
  ]
}
```

**教学风格提取输出，保存路径：`{PREPROCESSING_DIR}/{safe_stem}_teaching_style.json`**

完整输出结构：
```json
{
  "video_stem": "{VIDEO_STEM}",
  "output_path": "{PREPROCESSING_DIR}/{safe_stem}_teaching_style.json",
  "analogies": [...],
  "pace_analysis": [
    // Step 6.2 的数组内容
  ],
  "avg_seconds_per_topic": 90,
  "emphasis_points": [...],
  "teaching_approach": "...",
  "approach_examples": [...],
  "difficulty_markers": [...],
  "summary": {
    "primary_approach": "problem_first",
    "tone": "conversational",
    "difficulty_distribution": {
      "beginner": "60%",
      "intermediate": "30%",
      "advanced": "10%"
    },
    "key_analogies_for_stage2": [
      "在讲解 {概念} 时，老师用了 {类比}，Stage 2 应沿用此类比"
    ],
    "pacing_notes": "老师在 00:15-00:18 明显放慢节奏，该时间段对应的知识点需要在文档中重点展开",
    "teaching_style_summary": "{2-3句话总结老师的整体讲课风格}"
  }
}
```

---

## 输出文件保存指令

完成以上步骤后，**必须执行以下两个文件保存操作**：

```
1. 保存话题清单：
   路径：{PREPROCESSING_DIR}/{safe_stem}_topics.json
   内容：Step 5 的完整 JSON 输出（含 Step 4 的 processing_mode / reference_map）

2. 保存教学风格：
   路径：{PREPROCESSING_DIR}/{safe_stem}_teaching_style.json
   内容：Step 6 的完整 JSON 输出
```

这两个文件将作为 Stage 2 的持久化输入，确保即使对话中断也可以从这里恢复。

---

## 注意事项

**VIDEO_STEM 文件名安全化**：实际保存的文件名中，`VIDEO_STEM` 的特殊字符（`< > : " / \ | ? *`）会被替换为 `_`。例如视频名 `01:Java入门` 的 topics.json 文件名为 `01_Java入门_topics.json`。MCP 工具返回的 `artifacts.topics_json.path` 路径已包含正确的安全化文件名，直接使用该路径即可。

---

## 强制禁令

在 Stage 1 中，以下行为**严格禁止**：

- ❌ 禁止展开任何知识讲解
- ❌ 禁止从字幕中直接提取知识结论
- ❌ 禁止对字幕内容进行"理解性补全"
- ❌ 禁止将字幕的话语风格（口语化、填充词等）带入知识内容
- ❌ 禁止对"极差"质量的段落进行推测性话题判断

---

## 输出格式要求

- 先输出不超过5行的扫描报告摘要
- 再输出 `{safe_stem}_topics.json` 的 JSON 内容（供确认）
- 再输出 `{safe_stem}_teaching_style.json` 的 JSON 内容（供确认）
- 最后保存两个文件到 `{PREPROCESSING_DIR}/`
