# C · 章节综合：完整独立章节学习手册

> 📌 **工作流位置**（对应 SKILL.md §工作流程 → 流程C Steps C1-C4）
> 上一步：流程A 全部完成（章节所有视频均已完成 A1→A2→Step 6）
> 本步产物：`CHAPTER_SYNTHESIS_*.md` / `CHAPTER_EXERCISES_*.md` / `CHAPTER_ANKI_*.csv/.apkg`
> 兜底机制 2（知识完整性核查）和兜底机制 3（深度完整性预报）在本文件中落地（定义见 SKILL.md）

## 任务说明

这是「四层渐进式知识体系」**Layer 2** 章节综合阶段。

**触发时机**：当前章节所有视频均完成**流程 A**（逐视频 A1→A2→Step 6 图谱更新）后。
**输入**：各视频通过 `update_knowledge_graph` 工具写入知识图谱的章节摘要数据，由 `read_chapter_summaries` 工具聚合读取。
**产物**：CHAPTER_SYNTHESIS_{name}.md — 完整独立章节学习手册（用户主要阅读材料）

在本章所有（或绝大多数）视频的 Layer 1 处理完成后，使用本提示词生成一份**完整独立的章节学习手册**。

**核心定位（必须牢记）**：
> 用户在实际学习时**不会逐个打开视频级文档**——那样太慢、太碎。他们会直接阅读本章节综合文档完成整章学习。  
> 因此，CHAPTER_SYNTHESIS 必须是一份**可以独立完成整章学习的文档**：读者无需查阅任何视频级 knowledge_*.md 即可理解本章所有知识点，并完成所有练习题。

视频级文档（Layer 1）仅作为：① 原始素材来源；② 细节溯源备查。它们**不是**本文档的前置阅读。

---

> ⚠️ **前置步骤（本提示词执行前必须完成）**
>
> 1. 调用 `read_chapter_summaries(chapter_dir)` 获取所有视频摘要与知识图谱数据
> 2. 调用 `scan_chapter_completeness(chapter_dir)` 生成 `chapter_completeness_audit.md`（**兜底机制 2**，不可省略）
>
> 将上述两个工具的返回内容分别作为 `CHAPTER_SUMMARIES` 和 `COMPLETENESS_AUDIT` 传入。

---

## 输入变量

```
CHAPTER_DIR:        章节目录路径（如 portable-gpu-worker/output/Java基础-视频上/day01-Java入门）
chapter_dir_name:   [派生变量，非用户传入] = Path(CHAPTER_DIR).name，即路径最后一段（如 "day01-Java入门"）
                    用于所有产物的文件名和子目录名，如 CHAPTER_SYNTHESIS_day01-Java入门.md
CHAPTER_NAME:       章节名称（如 "Day01 · Java 入门"）
CHAPTER_SUMMARIES:  read_chapter_summaries 工具的返回内容（含所有视频摘要、图谱数据）
COMPLETENESS_AUDIT: scan_chapter_completeness 工具的返回内容（待补全清单）
PASS_MODE:          "outline" | "synthesis" | "exercises" | "anki"
                    outline    = Pass 1：生成章节大纲 JSON（标准/大型章节分多轮时的第一步）
                    synthesis  = Pass 2a：仅生成 CHAPTER_SYNTHESIS_*.md（保存后返回，禁止继续生成其他产物）
                    exercises  = Pass 2b：仅生成 CHAPTER_EXERCISES_*.md（要求 synthesis 已保存到磁盘）
                    anki       = Pass 2c：仅生成 CHAPTER_ANKI_*.csv + .apkg（要求 synthesis 已保存到磁盘）
                    ← "full" 已废弃：三件产物必须拆分为独立响应，防止单次输出超 12000 字导致超时
CHAPTER_OUTLINE:    （synthesis/exercises/anki pass 时需要）上一步 outline 生成的大纲 JSON；
                    轻量章节跳过 outline pass 时此字段为 null
```

---

## 处理策略选择

> 🔴 **核心防超时规则（所有策略均适用）**：三件产物（CHAPTER_SYNTHESIS / CHAPTER_EXERCISES / CHAPTER_ANKI）
> **必须分成三个独立响应轮次生成**，对应 Pass 2a / 2b / 2c，每轮保存文件后才启动下一轮。
> 严禁在一次响应内同时生成超过一件产物——即使是轻量章节亦然。

**判断维度：章节知识体量**（依据知识点密度，而非视频数量——同样 6 个视频，内容量可能相差 3 倍）

从 `read_chapter_summaries` 数据中估算体量：将各视频的 depth≥1 知识点数量汇总为 `total_knowledge_points`，并合计各视频 `word_count_target` 得到预估产物字数。

---

### 轻量章节（知识点 ≤ 15 个 / 预估产物 ≤ 8000 字）— 三轮 Pass

> 💡 **本提示词内的三轮 Pass**，不含 C1 前置工具调用（`read_chapter_summaries` + `scan_chapter_completeness`，在 SKILL.md Step C1 中已完成）。

- 对话 1：PASS_MODE = "synthesis"（跳过 Outline Pass，在 synthesis pass 内执行 Stage 0 分类门）→ 保存 CHAPTER_SYNTHESIS
- 对话 2：PASS_MODE = "exercises" → 保存 CHAPTER_EXERCISES
- 对话 3：PASS_MODE = "anki" → 保存 CSV + 打包 apkg

> 轻量章节的 synthesis pass 预估输出 ≤ 5000 字，单轮可完成；知识点超 20 个时使用分节写入（见 Pass 2a 说明）。

---

### 标准章节（知识点 16-40 个 / 预估产物 8000-20000 字）— 四轮 Pass

> 💡 **本提示词内的四轮 Pass**，不含 C1 前置工具调用（已在 SKILL.md Step C1 完成）。

- 对话 1：PASS_MODE = "outline" → 生成并保存 chapter_outline.json（Token ~8-12k）
- 对话 2：PASS_MODE = "synthesis" → 生成并保存 CHAPTER_SYNTHESIS（超 20 个知识点时分节写入，见 Pass 2a）
- 对话 3：PASS_MODE = "exercises" → 生成并保存 CHAPTER_EXERCISES
- 对话 4：PASS_MODE = "anki" → 生成 CSV + 打包 apkg

---

### 大型章节（知识点 > 40 个 / 预估产物 > 20000 字）— N+4 轮 Pass（含 C1 共 N+5 轮）

**对话 1-N（Group Summaries）**：
- 按内容关联度分组（每组预估约 5000 字），同一话题族的视频尽量归入同组
- 不按视频数量机械分组；内容密度低的视频可多个合并为一组
- 每次处理一组，生成 group_summary_N.json
- Token 消耗：每次 ~8k tokens

**对话 N+1（Outline Pass）**：
- 合并所有 group_summary，生成 chapter_outline.json

**对话 N+2（Synthesis Pass 2a）**：
- PASS_MODE = "synthesis"，使用分节写入机制（见 Pass 2a 说明）

**对话 N+3（Exercises Pass 2b）**：
- PASS_MODE = "exercises"

**对话 N+4（Anki Pass 2c）**：
- PASS_MODE = "anki"

---

## Pass 1 · Outline Pass（`PASS_MODE = "outline"`）

### 步骤

**【强制前置】Stage 0 — 内容价值分类门（在 C0 之前执行，结果写入各知识点 `content_type` 字段）**

在读取任何视频摘要后，立即将全章所有内容按**内容性质**分入三个桶，并按下表规则决定其在 CHAPTER_SYNTHESIS 中的处置：

| 桶 | 核心判断标准 | 典型示例 | 章节综合处置规则 |
|---|------------|---------|----------------|
| **SKILL** | 用户学完后能写出代码、执行命令、做出技术选型决策 | 语法、命令、环境安装、工具使用、API 用法、JDK/JRE/JVM 安装选择 | ✅ 正常进入知识点列表，按深度完整展开 |
| **MENTAL_MODEL** | 直接影响用户理解和调试代码的概念模型 | JVM 字节码执行原理、三层架构关系、跨平台实现机制 | ✅ 正常进入知识点列表，完整展开 |
| **EXCLUDE** | 删掉后用户仍能正常写/调试/部署代码，对技术决策无影响 | ①励志/学习价值内容（"Java改变了世界"、"坚持就有未来"）<br>②历史故事/命名趣闻（Green计划、Oak→Java命名、发布年表）<br>③行业统计/市场地位（"GitHub上Java项目数量第×位"）<br>④课程广告/自我介绍（讲师背景、机构宣传）<br>⑤"这章讲什么"元描述（若无技术内容）| ❌ **完全排除，不以任何形式出现在任何产物中** |

> ⚠️ **版本号不等于 HISTORY**：Java 8/11/17/21 LTS 版本选型 → 属于 SKILL（影响实际选型，必须保留）；  
> 1.0→5.0→8 的发布年份时间线 → 属于 EXCLUDE。

> 🔑 **分类唯一判据**："如果删掉这段内容，用户在理解技术原理、写代码、调试或部署时会受到影响吗？"  
> 受影响（含"帮助理解底层原理/工作原理"）→ SKILL 或 MENTAL_MODEL；  
> 不受影响（删掉后技术认知与操作能力完全无损）→ EXCLUDE，无条件丢弃。  
>  
> 典型 **EXCLUDE**（技术认知完全无损）：励志话语 · "Java 很重要" · 发布年份时间线 · GitHub 排名数据 · 讲师背景 · 广告口号  
> 典型 **不能 EXCLUDE**（影响技术理解）：JVM 字节码执行原理 · CLI 与 GUI 的本质区别 · 为什么需要字节码中间层 · LTS 版本选型依据

**分类结果写入**：每个知识点的 `content_type` 字段（`"skill"` / `"mental_model"` / `"exclude"`）；仅 skill / mental_model 类知识点进入列表，exclude 类直接丢弃，不写入 outline.json 任何字段。

---

0. **（C0）章节蓝图设计**（优先执行，输出写入 `central_metaphor` / `blueprint` 顶层字段）：
   - 确定本章 `central_metaphor`（全章核心比喻/类比，将贯穿所有知识点的连接语句）
   - 梳理 3-5 个可验证学习目标（"学完能做到…"格式）
   - 初步评估各概念优先级：⭐ 核心（初学必须掌握）/ 📦 扩展（深入理解时读）/ 🔍 参考（遇到时查阅）
   - 规划 30 分钟速通路径（仅含 ⭐ 核心概念）和完整学习路径（全量按 narrative_position 顺序）

1. 读取 `CHAPTER_SUMMARIES` 中所有视频的摘要和知识点列表
2. **知识点去重与整合**：
   - 将相同概念（即使来自不同视频）合并为一个条目
   - 记录每个知识点最深的讲解来源
   - 标记哪些视频是该知识点的"主讲视频"
3. **建立叙事顺序与知识关联**：
   - 按认知递进顺序排列知识点（不完全按视频顺序，而是按"学习理解的最优顺序"）
   - 标注知识点之间的依赖关系，**并记录"为什么 A 必须在 B 之前学"（`depends_on.reason`）**
   - 提炼 `learning_chain`：只含 ⭐ 核心概念的最短依赖路径（速通时的阅读主线）
   - 结合 C0 的初步评估，确定每个知识点的最终 `priority`
4. **规划连接语句**（`central_metaphor` 一致性约束）：
   - 为每个相邻知识点对，规划一句"承接语"（如"有了上面对 X 的认识，Y 就好理解了"）
   - **所有 connectors 必须引用 C0 确定的 `central_metaphor`**，保持全章叙事主线一致
   - 标注需要"对比分析"的知识点组合
5. **关键帧分配**：
   - 扫描各视频的 `_preprocessing/frames/` 目录
   - 为章节综合文档中的难点知识点分配最合适的关键帧（来自任意视频）

### 输出：chapter_outline.json

```json
{
  "chapter_name": "Day01 · Java 入门",
  "chapter_dir": "{CHAPTER_DIR}",
  "total_word_count_target": 6000,
  "independence_requirement": "读者仅凭本文档，无需任何视频级文档，应能完成 CHAPTER_EXERCISES 的全部题目",
  "central_metaphor": "建造并开工第一条 Java 流水线——JDK 是整套工具箱，JRE 是厂房，JVM 是流水线，HelloWorld 是第一次试生产",
  "learning_chain": ["java.hci_intro", "java.wora", "java.jdk_jre_jvm", "java.hello_world"],
  "blueprint": {
    "learning_goals": [
      "能用一句话解释 Java 跨平台是怎么实现的",
      "能区分 JDK / JRE / JVM 并说出各自用途",
      "能独立写出并运行 HelloWorld 程序",
      "能在命令行中切换目录、运行 javac/java 命令"
    ],
    "speedrun_30min": ["java.wora", "java.jdk_jre_jvm", "java.hello_world"],
    "full_path_2hr": "按目录顺序全量阅读",
    "prerequisites": "无，本章是课程起点",
    "next_chapter_dependency": "学完本章后可进入 day02（变量与数据类型）"
  },
  "knowledge_points": [
    {
      "id": "java.hci_intro",
      "display_name": "人机交互与程序的概念",
      "priority": "extend",
      "source_videos": ["02-人机交互-图形化界面的小故事"],
      "depth": 1,
      "narrative_position": 1,
      "summary": "程序是人与机器沟通的桥梁，操作系统是中间人",
      "key_frame": null,
      "depth_treatment": "完整展开",
      "word_count_target": 400,
      "content_type": "mental_model",
      "synthesis_treatment": "full",
      "max_words": null,
      "depends_on": [],
      "connectors": {
        "from_previous": null,
        "to_next": "有了对'程序是什么'的认识，我们来看 Java 程序特别在哪里——它为什么可以跨平台运行"
      }
    },
    {
      "id": "java.wora",
      "display_name": "WORA 与字节码跨平台原理",
      "priority": "core",
      "source_videos": ["01-Java学习介绍", "08-HelloWorld小程序"],
      "depth": 2,
      "narrative_position": 5,
      "summary": "javac 编译 → .class 字节码 → JVM 执行，一次编写到处运行",
      "key_frame": "08-HelloWorld小程序/_preprocessing/frames/scene_000003.jpg",
      "depends_on": [
        { "id": "java.hci_intro", "reason": "需要先理解'什么是程序'，才能理解 Java 为何要多一个字节码层" }
      ],
      "depth_treatment": "完整展开",
      "word_count_target": 800,
      "content_type": "mental_model",
      "synthesis_treatment": "full",
      "max_words": null,
      "connectors": {
        "from_previous": "有了上面对 JVM 是什么的认识，现在来看为什么它能做到跨平台——这正是我们这条流水线的核心设计",
        "to_next": "理解了字节码，我们就能看懂为什么安装 JDK 和只安装 JRE 是不同的事"
      }
    }
  ],
  "implicit_knowledge_to_mention": [
    {
      "concept": "public/static/void/class 关键字",
      "seen_in": "08-HelloWorld小程序",
      "note": "用户在 HelloWorld 代码中见过，正式讲解在 OOP 章节"
    }
  ],
  "chapter_narrative_arc": "从安装 Java 开发环境出发，通过编写和运行第一个 HelloWorld 程序，理解完整的从源码到运行的认知链路，掌握 JDK/JRE/JVM 三者组成与关系。",
  "chapter_intro": {
    "opening_sentence": "（1-2 句纯技术导语，点明本章结束后用户能做什么；禁止写学习价值、历史背景或励志内容）"
  }
}
```

> 🔴 **强制保存（Pass 1 必须）**：JSON 生成后，立即调用 `create_file` 将上述 JSON 保存到：
> `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/chapter_outline.json`
> 保存成功后告知用户 "✅ Pass 1 完成，请发送任意消息继续 Pass 2a（综合知识文档）"，**等待用户确认后才继续**。

---

## Pass 2a · 综合知识文档（`PASS_MODE = "synthesis"`）

> 🔴 **强制输出卡点（防超时核心机制）**：本轮次**唯一任务**是生成并保存 `CHAPTER_SYNTHESIS_*.md`。  
> 生成完成后立即调用 `create_file` 写入磁盘，**严禁在同一响应内开始生成练习题或 Anki CSV**。  
> 保存成功后告知用户"✅ Pass 2a 完成，请发送任意消息继续 Pass 2b（练习题）"。

**前置**（若使用了 Outline Pass）：使用 `read_file` 从磁盘加载 `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/chapter_outline.json`（Pass 1 产物）作为本轮的 `CHAPTER_OUTLINE` 输入；轻量章节跳过 Outline Pass 时直接忽略此步骤。

**输入**：`CHAPTER_OUTLINE`（若有）或直接基于 `CHAPTER_SUMMARIES`

> ⚠️ **跳过 Outline Pass 时的 Stage 0 强制提示**：
> 轻量章节直接进入 synthesis pass 时，**Stage 0 内容价值分类门仍然必须执行**——在读取 CHAPTER_SUMMARIES 后、开始写正文之前，先按 Stage 0 三桶分类规则把所有内容标记为 skill / mental_model / **exclude**。  
> **exclude 类内容直接丢弃，不以任何形式写入文档。**  
> Stage 0 不因跳过 Outline Pass 而豁免。

**超大综合文档分节写入**（当 `knowledge_points` 数量 > 20 时，**必须分两步保存**以避免单次输出超限）：
1. 生成文档头部 + 学习蓝图 + 本章导读 + 目录 + **前 10 个知识点节** → 末尾追加占位符 `<!-- SYNTHESIS_CONTINUE -->` → 调用 `create_file` 保存
2. 生成第 11 个起的所有知识点节 + 末尾各区块（预报表 / 练习索引）→ 调用 `replace_string_in_file` 替换占位符 `<!-- SYNTHESIS_CONTINUE -->`

---

### 产物（Pass 2a）：章节综合知识文档（CHAPTER_SYNTHESIS.md）

#### 文档结构

```markdown
# {CHAPTER_NAME}

> 📋 **本文档是本章完整学习手册，无需查看任何视频级文档即可独立学习。**
> 来源：综合本章 {N} 个视频的知识内容（视频级原始文档见各视频子目录）
> 参考：[JavaGuide](https://javaguide.cn) · [JLS 21](…) · [JVMS 21](…)

## 📋 本章学习蓝图

### 🎯 学完本章，你能做到：
{blueprint.learning_goals — 3-5 个可验证陈述，每条用"能…"格式}

### 🗺 知识关联总览
{用文本依赖图展示 learning_chain 中各核心概念的前后依赖关系及原因（depends_on.reason），例如：}
```
[概念A] ──→ [概念B（依赖A：因为…）] ──→ [概念C]
              │
              └──→ [概念D（并行，不阻塞主线）]
↑ 以上为核心链路（⭐），速通时按此顺序学习
📦 [扩展概念X]：理解更深时阅读，不阻塞主链路
🔍 [参考概念Y]：遇到时查阅即可
```

### ⭐ 30 分钟速通（只看核心概念）
{blueprint.speedrun_30min — 只列 ⭐ 核心知识点及对应章节内跳转链接}

### 📚 完整学习路径（建议 2 小时）
{全量知识点列表，按 narrative_position 顺序，每项后注明优先级标记}

### 🔗 本章与前后章节的连接
- **前置要求**：{blueprint.prerequisites}
- **学完后可以**：{blueprint.next_chapter_dependency}

---

## 本章导读

{chapter_intro.opening_sentence：1-2 句纯技术导语，说明本章教什么、学完能做什么操作。
严格禁止内容：学习动力/价值观 · 历史故事 · 行业数据 · 讲师背景 · 任何非技术前言
正确示例："本章从安装 JDK 出发，通过编写并运行 HelloWorld，建立从源码到字节码到 JVM 执行的完整认知链路。"
错误示例："Java 是全球最流行的语言之一，学好 Java 将让你……"}

**本章核心概念链**：{以"→"表示依赖顺序的概念链，只含 ⭐ 核心概念}

---

## 目录

{按 narrative_position 排列的知识点列表，带内部跳转链接，每项后注明预估阅读时间}

---

{各知识点的完整展开讲解，按 narrative_position 顺序}

节格式：
## {编号}. {知识点名称} {⭐|📦|🔍}
（优先级标记来自 outline.json 的 `priority` 字段：core=⭐，extend=📦，reference=🔍）

{connector.from_previous — 承接上一节的过渡语，让读者感受到连贯叙事；必须引用 central_metaphor}

{切入段：模仿老师开场方式，用问题/场景/类比引出}

{完整知识讲解：定义 + 类比 + 图示/表格 + 代码示例 + 常见陷阱}

{前置知识补充块（如有依赖）：
> 💡 回顾：{前置概念} 是指 {一句话}，在本章第 X 节中介绍过。}

{隐性知识提示块（如适用）：
> 💡 **你已经见过它了**：在本章视频 {X} 的代码演示中出现过 `{term}`。当时先跑起来了，现在来正式学习它。}

{connector.to_next — 预告下一节，引发读者期待}

---

## 📌 本章已引入但后续才完整的概念

| 概念 | 当前深度 | 预期完整深度 | 何时完整讲解 |
|------|---------|------------|------------|
| {概念名} | {depth}/4 | {max_depth}/4 | {后续章节} |

---

## 📝 本章练习索引

| 知识点 | 对应练习 |
|-------|---------|
| {知识点}（第 N 节） | Q{n} · Q{m} |

---

*练习题 → [CHAPTER_EXERCISES_{chapter_dir_name}.md](./CHAPTER_EXERCISES_{chapter_dir_name}.md)*
```

#### 写作原则（按重要性排序）

**原则 1：独立完整（首要原则）**

读者无需查阅任何视频级文档即可独立完成本章学习。视频级 knowledge_*.md 是原材料，不是本文档的前置阅读。

- 验证方法：写完后问自己——"一个对本章完全陌生的人，仅凭本文档，能否回答所有练习题？" 能 = 合格。不能 = 找出缺失的讲解，补充完整。
- **严禁**写"详见 knowledge_XXX.md"之类的引用来代替解释。

**原则 2：深度展开，禁止摘要**

每个 `depth≥1` 的核心概念**必须完整展开**，不能只写摘要。完整展开的字数参考：

| 知识点深度 | 必须包含 | 字数参考 |
|-----------|---------|--------|
| depth=1（引介） | 定义 + 类比 + 简单示例 + 常见误解 | 400-700 字 |
| depth=2（运用） | 完整语法 + ≥2 个可运行代码示例 + 常见陷阱 + 相关概念对比 | 700-1200 字 |
| depth=3（原理） | depth=2 的全部 + 底层机制 + JVM/规范层解释 + 版本差异 | 1200-2000 字 |

整章文档**最低总字数**：≥4000字；核心概念≥5个的章节应达6000+字。

**原则 3：概念贯通，显式连接（章节综合文档的核心价值）**

视频文档各自孤立，章节综合文档的核心价值在于"串联"。必须在合适位置显式指出概念间关联：

- **承接**：「有了上面对 {概念A} 的认识，下面的 {概念B} 就好理解了——」
- **对比**：「{概念A} 和 {概念B} 很容易混淆，我们来专门对比一下：」
- **呼应**：「还记得本章第2节提到的 {概念A} 吗？这里的 {概念B} 正是它的具体体现」
- **铺垫**：在讲某概念前，先用真实场景引出（"假设你现在需要..."）
- **依赖说明**：当一个概念 depends_on 另一个时，在该节开头用一句"要理解 {概念B}，需要先有 {概念A} 的基础——{depends_on.reason}"，使读者明白学习顺序的内在逻辑。

**outline.json 中 `connectors` 字段已规划了每个知识点的连接语句，Full Pass 时必须将它们写进正文。所有连接语必须引用 `central_metaphor`。**

**原则 3.5：中心比喻一致性（`central_metaphor` 约束）**

Outline 设计阶段确定了 `central_metaphor`（全章核心比喻）。Full Pass 时：
- 每个知识点节的切入段或 connector 中，至少有一处引用该比喻
- 比喻不要生硬重复，而是用不同角度延伸（同一个类比，讲不同侧面）
- 若某知识点实在无法自然引用比喻，可以省略，**严禁强行套用造成牵强感**

**原则 4：最优叙事顺序（不是视频顺序）**

按 `narrative_position` 排序，不是按视频编号。原则：
1. 先全局概念（"这章讲什么"），再具体知识点
2. `depends_on` 非空的概念，被依赖方先写
3. 相关概念相邻，不拆散

**原则 5：去重合并升级**

若同一概念在多个视频都有涉及：取最深讲解为主体，其他视频的补充角度（不同类比、不同示例）融入同一节作为"补充视角"——不是合并成摘要，而是保留所有好的解释。

**原则 6：隐性知识妥善安置**

在第一次正式讲解相关语法时，插入：
> 💡 **你已经见过它了**：在本章视频 {X} 的代码演示中，出现过 `{term}` 这个词。当时先跑起来了，现在来正式学习它。

**原则 7：关键帧重新分配**

只插入对本文档叙事有帮助的帧（三步判断法同 A2_knowledge_gen.md），不受视频文档的帧分配约束。插入格式：
```markdown
![{帧内容描述}]({视频目录的相对路径}/_preprocessing/frames/{filename})
> *📍 视频 {HH:MM:SS} — {描述}*
```

**原则 8：零基础原则**

每个新术语首次出现时都要解释，不假设读者已看过任何视频文档。

**原则 9：优先级标注规则**

每个知识点节标题后**必须**带优先级标记（来自 outline.json `priority` 字段）：
- `⭐ 核心`：初学者必须完整阅读，速通路径包含
- `📦 扩展`：强烈建议读，不在速通路径但有助于深理解
- `🔍 参考`：背景知识，可跳过，遇到问题时回来查

**同时**，文档开头"学习蓝图"中的 30 分钟速通清单仅列 ⭐ 核心概念。读者可自主选择速通还是精读，不强制全量。

**原则 10：内容类型硬约束（Stage 0 分类结果具有强制力，不可绕过）**

`outline.json` 的 Stage 0 分类结果对 synthesis pass 具有强制约束力：

| 字段值 | Synthesis Pass 必须执行的规则 |
|-------|------------------------------|
| `content_type: "exclude"` | **该知识点不得以任何形式出现在 CHAPTER_SYNTHESIS / CHAPTER_EXERCISES / CHAPTER_ANKI 任何位置**； 历史故事、励志内容、行业数据、讲师介绍均属此类，一字不写 |
| `synthesis_treatment: "brief"` | 该知识点字数硬上限为 `max_words`，超出部分截断，仅保留核心定义 |
| `max_words` 不为 null | 该节实际字数（含代码块、表格）不得超过此值，优先删减示例 |

> 💡 **避免误判**：技术决策依据（如"Java 8/17/21 是 LTS 需要选用"）即使来自教师的铺垫性叙述，仍属于 SKILL，不受 exclude 约束。  
> 判据：**删掉这段内容后，用户在理解技术原理、写代码、调试或部署时会受到影响吗？** 受影响（含影响技术理解）→ SKILL/MENTAL_MODEL；不受影响 → EXCLUDE，无条件丢弃。

---

> ✅ **Pass 2a 完成检查点**：确认 `create_file` 保存成功（文件存在且非空）后，告知用户  
> "✅ CHAPTER_SYNTHESIS 已保存，请发送任意消息继续 Pass 2b（练习题）"。**等待用户确认后才继续。**

---

## Pass 2b · 章节练习文档（`PASS_MODE = "exercises"`）

> 🔴 **强制输出卡点**：本轮次**唯一任务**是生成并保存 `CHAPTER_EXERCISES_*.md`，生成后立即 `create_file`，**不得继续生成 Anki**。  
> **前置**：使用 `read_file` 读取磁盘上 Pass 2a 保存的：  
> `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/CHAPTER_SYNTHESIS_{chapter_dir_name}.md`  
> （禁止依赖上一轮内存中的内容——新轮次上下文已刷新）。  
> 保存成功后告知用户"✅ Pass 2b 完成，请发送任意消息继续 Pass 2c（Anki）"。

### 产物（Pass 2b）：章节练习文档（CHAPTER_EXERCISES.md）

```markdown
# 练习题 · {CHAPTER_NAME}

> 来源：综合本章 {N} 个视频的知识内容
> 本章知识文档：[CHAPTER_SYNTHESIS_{chapter_dir_name}.md](./CHAPTER_SYNTHESIS_{chapter_dir_name}.md)

---
```

#### 出题原则

> 📌 **章节练习 = 从章节知识文档出发，全面覆盖，系统生成**
> 视频级不再生成练习题，章节练习是本学习包中唯一的练习来源，必须完整覆盖本章所有知识点。

**阶段 1：基于 CHAPTER_SYNTHESIS.md 系统生成全章题目集**

以 CHAPTER_SYNTHESIS.md 为唯一知识源，为每个知识点（depth≥1）生成题目：

1. **覆盖性要求**：每个 `priority=core`（⭐）概念出 2-3 道；`priority=extend`（📦）概念出 1-2 道；`priority=reference`（🔍）概念视难度出 0-1 道
2. **题型分布**：每个概念至少有一道"概念理解题"；有代码示例的概念出"代码题"；易混淆概念出"对比题"
3. **深度匹配**：题目深度与 CHAPTER_SYNTHESIS.md 的展开深度对齐（depth=1 出 ⭐ 题，depth=2 出 ⭐⭐ 题）

**阶段 2：跨知识点综合题（章节练习的核心价值）**

在单知识点题目基础上新增：
1. **联合考查题**（至少 3 道）：需要综合本章多个 ⭐ 核心概念才能回答的题目，考查知识点之间的关联（如"JVM / JRE / JDK 的关系，以及字节码在其中的位置"）
2. **章节主线题**：围绕 `central_metaphor` 出 1-2 道综合性叙述题（如"请用自己的话描述一个 Java 程序从源码到运行的完整流程"）
3. **深化题**：若章节综合对某概念做了深度展开（depth≥2），出对应深度的题目

**阶段 3：面试题专区（强化，可选独立区块）**

> 💬 本章高频面试题是本章练习的重要组成部分，**必须单独成一个"面试题精选"区块**。

面试题生成规范：
- 优先参考 JavaGuide 对应章节的高频面试题列表
- 每题标注 `💬 面试高频` + 难度（⭐/⭐⭐/⭐⭐⭐）
- 答案按面试场景组织：先给"一句话答案"，再给"完整展开版"，让用户知道面试时说多少合适
- 经典面试题即使涉及后续章节内容也可纳入，但答案中必须注明"关于 {后续概念} 的细节，在 {后续章节} 中会详细说"
- 数量：初学章节（day01-05）出 3-5 道；后期高密度章节出 8-12 道

**总量与格式**：
- 总量无硬性上限，取决于章节知识密度
- 不因"题量多"而删减任何 ⭐ 核心概念对应的练习
- Q&A 联排格式（格式规范见 `templates/exercises_doc.md`，严禁 `<details>` 标签）
- 每题答案后标注 `📖 参考：CHAPTER_SYNTHESIS 第 X 节`

---

> ✅ **Pass 2b 完成检查点**：确认文件保存成功后，告知用户  
> "✅ CHAPTER_EXERCISES 已保存，请发送任意消息继续 Pass 2c（Anki）"。**等待用户确认后才继续。**

---

## Pass 2c · Anki 卡包（`PASS_MODE = "anki"`）

> 🔴 **强制输出卡点**：本轮次**唯一任务**是生成 CSV 并打包 apkg。  
> **前置**：使用 `read_file` 读取磁盘上的：  
> `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/CHAPTER_SYNTHESIS_{chapter_dir_name}.md`  
> CSV 生成后立即 `create_file`，再调用 `export_anki_package`。  
> 完成后告知用户"✅ Pass 2c 完成，章节学习包生成完毕"。

### 产物（Pass 2c）：章节 Anki CSV（CHAPTER_ANKI.csv）

基于 CHAPTER_SYNTHESIS.md 的知识点从零生成全章 Anki 卡包（视频级不再有 CSV 可合并）。

**牌组命名**：
```
Java全栈::{课程文件夹}::{chapter文件夹}
示例：Java全栈::Java基础-视频上::day01-Java入门
```

**卡片生成规则**：
- 每个 depth≥1 的核心概念生成 2-4 张（定义 / 代码填空 / 对比 / 原理）
- `priority=core`（⭐）概念优先覆盖，`priority=reference`（🔍）只出最核心的 1-2 张
- 章节综合中的"贯通洞察"（跨概念关联）单独出 1 张背面较长的综合卡
- 面试高频题各出 1 张（正面=面试问题，背面=简洁答案）
- 不出超纲卡片（后续章节才讲的概念不出）

**输出格式**：格式规范见 `templates/anki_card.csv`（含 `#separator:Comma` 头部、5 列、5 种卡片类型）；用 `create_file` 写入 CSV 后调用 `export_anki_package` MCP 工具打包。

---

## 产物保存位置

```
{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/
├── CHAPTER_SYNTHESIS_{chapter_dir_name}.md    ← 主知识文档（章节完整学习手册）
├── CHAPTER_EXERCISES_{chapter_dir_name}.md    ← 章节练习
├── CHAPTER_ANKI_{chapter_dir_name}.csv        ← 基于 CHAPTER_SYNTHESIS 从零生成（非合并，视频级不再有 Anki CSV）
├── CHAPTER_ANKI_{chapter_dir_name}.apkg       ← 调用 MCP 工具生成：
│                                                  export_anki_package(
│                                                    csv_path="…/CHAPTER_ANKI_{chapter_dir_name}.csv",
│                                                    output_path="…/CHAPTER_ANKI_{chapter_dir_name}.apkg",
│                                                    deck_name="Java全栈::{课程文件夹}::{chapter_dir_name}"
│                                                  )
└── chapter_completeness_audit.md              ← 待补全清单（由 scan_chapter_completeness 工具生成）
```

---

## 质量检查清单

**独立性验证（最重要）**
- [ ] **独立性测试**：单独阅读本文档（不看任何视频级文档），能否回答 CHAPTER_EXERCISES 的全部题目？如不能 → 找出缺失的讲解，补充完整
- [ ] 文档总字数 ≥ 4000 字（核心概念≥5个的章节应达 6000+ 字）
- [ ] 每个 depth≥1 的核心概念都有完整展开（含类比 + 代码示例，不只是摘要引用）
- [ ] 文档中无"详见 knowledge_XXX.md"之类的替代引用

**结构与顺序**
- [ ] 文档开头有"📋 本章学习蓝图"区块（含学习目标、知识关联总览、速通清单、完整路径、前后章连接）
- [ ] 完整目录，带内部跳转链接
- [ ] 所有知识点按"最优认知顺序"排列（`narrative_position`），非按视频顺序
- [ ] 每个知识点节标题带优先级标记（⭐/📦/🔍）
- [ ] 节与节之间有承接语（来自 outline.json `connectors`），且引用了 `central_metaphor`
- [ ] 有依赖关系的知识点节开头有"理解 B 需要先有 A 的基础——{reason}"说明

**内容纯洁性（Stage 0 强制检查）**
- [ ] **文档中不存在任何** 励志话语 / 历史故事 / Java 市场排名 / 讲师介绍 / 广告语 / "为什么学 Java" 类内容
- [ ] 每个知识点节的第一句话是技术内容，而非学习价值说明
- [ ] 文档导读段仅含技术性说明（学完后能做什么），无任何非技术前言

**内容完整性**
- [ ] 同一概念在多个视频涉及的 → 已合并为一个完整节（不是多处摘要）
- [ ] 隐性知识（`implicit_concepts`）已在正式讲解处加"你已经见过它了"提示
- [ ] 末尾有"📌 本章已引入但后续才完整的概念"预报表（含 current/max depth 列）
- [ ] 末尾有"📝 本章练习索引"（知识点 → 题目编号对应表）

**练习与 Anki**
- [ ] 每个 ⭐ 核心概念均有 2-3 道对应练习题
- [ ] 至少 3 道跨知识点联合题（包含 `central_metaphor` 对应的章节主线题）
- [ ] 有"💬 面试题精选"独立区块，题目标注 `💬 面试高频` + 难度
- [ ] 每题答案后有 `📖 参考：CHAPTER_SYNTHESIS 第 X 节`
- [ ] Anki 牌组命名使用章节级，每个 ⭐ 概念有卡片覆盖

**辅助工具（前置检查）**
- [ ] 确认本章所有视频均已执行 Step 6（`update_knowledge_graph`），否则图谱数据不完整
- [ ] 已调用 `scan_chapter_completeness` 生成 `chapter_completeness_audit.md`（兜底机制 2）
- [ ] `COMPLETENESS_AUDIT` 中列出的所有「待补全清单」项已在以下某处被处理：正文中有说明 / 预报表中已标注

**兜底机制 3 — 深度完整性预报**
- [ ] CHAPTER_SYNTHESIS 末尾包含「📌 本章已引入但后续才完整的概念」预报表（**兜底机制 3，必备**）
- [ ] 预报表包含 current_depth / expected_max_depth / 何时完整讲解 三列
- [ ] 图谱中所有 `implicit_concepts`（depth=0.5）已出现在预报表或正文的「你已经见过它了」提示块中