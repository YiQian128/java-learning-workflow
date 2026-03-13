# C · 章节综合：完整独立章节学习手册

> 📌 **工作流位置**（对应 SKILL.md §工作流程 → 流程C Steps C1-C4）
> 上一步：流程A 全部完成（章节所有视频均已完成 A1→A2→Step 6）
> 本步产物：`CHAPTER_SYNTHESIS_*.md` / `CHAPTER_EXERCISES_*.md` / `CHAPTER_ANKI_*.csv/.apkg`
> 兜底机制 2（知识完整性核查，即 scan_chapter_completeness）在本文件中落地（定义见 SKILL.md）

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
                    ← "full" 已废弃；防超时规则见上方规则 A / 规则 B
CHAPTER_OUTLINE:    （synthesis/exercises/anki pass 时需要）上一步 outline 生成的大纲 JSON；
                    轻量章节跳过 outline pass 时此字段为 null
```

---

## 处理策略选择

> � **产物级生成策略（规则 A）**：三件产物（CHAPTER_SYNTHESIS / CHAPTER_EXERCISES / CHAPTER_ANKI）必须**按序生成并逐件保存到磁盘**，前一件完整写入后才可开始下一件。
> **AI 自主判断是否在同一轮对话中继续**：每件产物保存完成后，评估当前轮次剩余输出容量——
> - 剩余容量充足且下一件产物预估生成量在安全范围内 → **直接继续生成下一件产物**，无需等待用户确认
> - 剩余容量不足或接近上限 → **停止并告知用户**发送消息以继续下一件
>
> 占位符追加链（规则 B）始终强制执行——即使在同一轮对话中生成多件产物，每件内部仍必须分步写入。

> 🔴 **核心防超时规则 B（节级，强制执行）：每次调用 `create_file` 或 `replace_string_in_file` 前，当前响应内生成的文字量必须在模型单次响应的安全上限内**（不同模型上限各异；分组时以每组 **3-5 个知识点**为基准，depth=3 的知识点取低限 1-2 个，不确定时宁小勿大）。  
> 实现方式：**outline pass / synthesis pass / exercises pass 内部均须使用占位符追加链（Placeholder-Chain）**分步写入——outline pass：O1（骨架）→ O2 至 ON（逐组填写 KP）→ ON+1（synthesis_plan）；synthesis pass：S1（写头部）→ S2 至 SN（逐组 KP 节）→ SN+1（收尾）；exercises pass：E1（写头部）→ E2 至 EN（逐组题）→ EN+1（面试题）→ EN+2（索引）（各 Pass 详细规范见下方相应章节）。  
> ⚠️ 违反此规则的症状：AI 在一次响应中生成完整的长文档后才调用 create_file → 文档超出模型单次输出 token 上限导致截断/超时。

**判断维度：章节知识体量**（依据知识点密度，而非视频数量——同样 6 个视频，内容量可能相差 3 倍）

从 `read_chapter_summaries` 数据中估算体量：将各视频的 depth≥1 知识点数量汇总为 `total_knowledge_points`，并合计各视频 `word_count_target` 得到预估产物字数。

> ⚠️ **输入超限预防**：若 `read_chapter_summaries` 返回的数据量明显偏大（章节视频多、内容密集），应主动升级处理路径（轻量→标准、标准→大型），以减少后续每轮的输入量——Outline Pass 会将原始摘要压缩为结构化 JSON，Group Summary Pass 则按组分批处理，两者都能有效缓解输入超限风险。

---

### 轻量章节（知识点 ≤ 15 个 / 预估产物 ≤ 8000 字，参考值）— 三轮 Pass

> 💡 **本提示词内的三轮 Pass**，不含 C1 前置工具调用（`read_chapter_summaries` + `scan_chapter_completeness`，在 SKILL.md Step C1 中已完成）。

- Pass 1：PASS_MODE = "synthesis"（跳过 Outline Pass，在 synthesis pass 内执行 Stage 0 分类闸）→ 使用占位符追加链写入，保存 CHAPTER_SYNTHESIS
- Pass 2：PASS_MODE = "exercises" → 保存 CHAPTER_EXERCISES
- Pass 3：PASS_MODE = "anki" → 保存 CSV + 打包 apkg

> 每件产物保存完成后，AI 自行评估剩余容量，充足则直接继续下一件，不足则等待用户确认（规则 A）。

> 轻量章节即使预估 ≤ 8000 字，synthesis pass 也**必须**使用占位符追加链（见 Pass 2a），保证每次写盘前生成量在单次响应安全范围内（参考 3-5 个知识点）。

---

### 标准章节（知识点 16-40 个 / 预估产物 8000-20000 字，参考值）— 四轮 Pass

> 💡 **本提示词内的四轮 Pass**，不含 C1 前置工具调用（已在 SKILL.md Step C1 完成）。

- Pass 1：PASS_MODE = "outline" → 生成并保存 chapter_outline.json（含 `synthesis_plan.groups` 字段，见 Pass 1 详细规范）
- Pass 2：PASS_MODE = "synthesis" → 读取 `synthesis_plan.groups`，使用占位符追加链分组写入，保存 CHAPTER_SYNTHESIS
- Pass 3：PASS_MODE = "exercises" → 保存 CHAPTER_EXERCISES
- Pass 4：PASS_MODE = "anki" → 生成 CSV + 打包 apkg

> 每件产物保存完成后，AI 自行评估剩余容量，充足则直接继续下一件，不足则等待用户确认（规则 A）。

---

### 大型章节（知识点 > 40 个 / 预估产物 > 20000 字，参考值）— N+4 轮 Pass（含 C1 共 N+5 轮）

**Pass 1-N（Group Summaries）**：
- 按内容关联度分组（每组 3-6 个视频，控制每轮读入的知识文档总量在模型安全输入范围内），同一话题族的视频尽量归入同组
- 不按视频数量机械分组；内容密度低的视频可多个合并为一组
- 每次处理一组，生成 group_summary_N.json  
  保存路径：`{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/group_summary_{N}.json`

**Pass N+1（Outline Pass）**：
- 合并所有 group_summary，生成 chapter_outline.json

**Pass N+2（Synthesis）**：
- PASS_MODE = "synthesis"，使用占位符追加链逐组写入

**Pass N+3（Exercises）**：
- PASS_MODE = "exercises"

**Pass N+4（Anki）**：
- PASS_MODE = "anki"

> 每件产物保存完成后，AI 自行评估剩余容量，充足则直接继续下一件，不足则等待用户确认（规则 A）。

---

## Pass 1 · Outline Pass（`PASS_MODE = "outline"`）

### 步骤

**【强制前置】Stage 0 — 内容价值分类闸（与步骤 1 同步进行，在 C0 之前完成分类，结果写入各知识点 `content_type` 字段）**

> 💡 **执行时序说明**：Stage 0 与**步骤 1**（读取 CHAPTER\_SUMMARIES）并行执行——读到每条摘要时立即分类；全部摘要读取并分类完成后，再执行步骤 0（C0 蓝图设计）。C0 依赖 Stage 0 + 步骤 1 的输出，不可在读取摘要之前执行。

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

0. **（C0）章节蓝图设计**（在 Stage 0 + 步骤 1 完成后执行，输出写入 `central_metaphor` / `blueprint` 顶层字段）：
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
4. **规划承接语句**（`central_metaphor` 一致性约束）：
   - 为每个知识点规划一句 `from_previous` 承接语（如“有了上面对 X 的认识，Y 就好理解了”）
   - **所有 connectors 必须引用 C0 确定的 `central_metaphor`**，保持全章叙事主线一致
   - **不规划“预告下一节”类型的连接语**——每个知识点以技术内容自然结束，不分散读者专注力
   - 标注需要"对比分析"的知识点组合
5. **关键帧分配**：
   - 扫描各视频的 `_preprocessing/frames/` 目录
   - 为章节综合文档中的难点知识点分配最合适的关键帧（来自任意视频）

### 输出：chapter_outline.json（占位符追加链写入，严禁一次性生成）

> 🔴 **Outline Pass 与 Synthesis Pass 面临同等超时风险**：chapter_outline.json 的 `knowledge_points` 数组通常包含 15-40 个 KP，每个 KP 含 code_anchors / connectors / synthesis_depth 等多字段，总输出量可达 5000-12000 tokens——**禁止一次性生成完整 JSON 后再调用 `create_file`**，必须使用以下占位符追加链分步写入。

#### 🔴 Outline Pass 占位符追加链写入规范

**步骤 O1：写骨架 JSON**（`create_file`，本步仅写顶层元数据 + blueprint + 两个占位符，不生成任何 KP 对象，生成量极小）

保存路径：`{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/chapter_outline.json`

> `chapter_outline.json` 属于可持久化产物，`chapter_dir` 字段**禁止写绝对路径**。若工具输入或 GUI JSON 提供的是绝对路径，必须先转换为相对于项目根目录的可移植路径，例如 `portable-gpu-worker/output/Java基础-视频上/day01-Java入门`。

骨架模板（步骤 O1 的完整文件内容）：
```json
{
  "chapter_name": "{章节名}",
   "chapter_dir": "portable-gpu-worker/output/{课程文件夹}/{chapter_dir_name}",
  "total_word_count_target": 0,
  "independence_requirement": "读者仅凭本文档，无需任何视频级文档，应能完成 CHAPTER_EXERCISES 的全部题目",
  "central_metaphor": "{C0 确定的全章核心比喻}",
  "learning_chain": ["{KP_id_1}", "{KP_id_2}", "...仅含 core 的最短依赖路径..."],
  "blueprint": {
    "learning_goals": ["能…", "能…", "能…"],
    "speedrun_30min": ["{core KP id 列表}"],
    "full_path_2hr": "按目录顺序全量阅读",
    "prerequisites": "{前置要求}",
    "next_chapter_dependency": "{下一章依赖说明}"
  },
  "chapter_narrative_arc": "{本章叙事主线一句话}",
  "chapter_intro": {
    "opening_sentence": "{1-2 句纯技术导语}"
  },
  "knowledge_points": [
    "<!-- KP_PENDING -->"
  ],
  "implicit_knowledge_to_mention": [],
  "synthesis_plan": "<!-- SYNPLAN_PENDING -->"
}
```

> ❗ `"<!-- KP_PENDING -->"` 和 `"<!-- SYNPLAN_PENDING -->"` 是 JSON 内的字符串占位符，后续 replace 操作依赖它们，**必须原样写入**。O1 完成后 JSON 文件暂时不是合法格式——这是预期状态。

---

**步骤 O2 ~ ON：逐组填充 KP 对象**（每组 `replace_string_in_file`，每组 **3-5 个 KP**，生成量控制在单次响应安全范围内）

每个 KP 对象包含以下全部字段（参考下方 KP 字段说明）：`id` / `display_name` / `priority` / `source_videos` / `depth` / `narrative_position` / `summary` / `key_frame` / `depends_on` / `depth_treatment` / `word_count_target` / `content_type` / `synthesis_treatment` / `synthesis_depth` / `deferred_credibility` / `deferred_aspects` / `max_words` / `connectors` / `code_anchors`

对第 G 组（G = 1 … N-1）：
- `old_string` = `"<!-- KP_PENDING -->"`
- `new_string` = `{KP_(G组第1个) JSON 对象},\n    {KP_(G组第2个) JSON 对象},\n    ...\n    "<!-- KP_PENDING -->"`

对最后一组（G = N）：
- `old_string` = `"<!-- KP_PENDING -->"`
- `new_string` = `{KP_(N组第1个) JSON 对象},\n    ...\n    {KP_(N组最后1个) JSON 对象}` **（无尾随占位符，数组自然闭合）**

> ⚠️ O2 至 ON 过程中文件内含有字符串占位符，暂不是合法 JSON——这是预期行为，ON+1 完成才恢复合法性。

**KP 对象字段填写规则（O2 至 ON 写入每个 KP 对象时填写，与 ON+1 步骤无关）**：

> **`code_anchors` 字段**（Pass 2b/2c 精准出题锚点，每个非 exclude 的 KP 必须填写）：在阅读 `CHAPTER_SUMMARIES` 过程中，为每个 KP 提炼 3-5 个"出题精华片段"。**格式**：每条 ≤ 25 字，包含具体命令/报错信息/语法/数字。`code_anchors` 为空或只有泛泛描述时，exercises pass 无法出精准题。
>
> **`synthesis_depth` / `deferred_credibility` / `deferred_aspects` 字段**：
>    - `priority=core AND depth < 2 AND 本章需独立编写/执行` → `synthesis_depth = 2`（**强制地板**）
>    - `priority=core AND depth < 2 AND 属于模板背记或一次性决策` → `synthesis_depth = 1`
>    - `priority=core AND depth ≥ 2` → `synthesis_depth = depth`
>    - `priority=extend` → `synthesis_depth = min(depth, 1)`（受 **≤400字** 上限约束）
>    - `priority=reference` → `synthesis_depth = min(depth, 1)`（受 **≤150字** 上限约束）
>    - `deferred_credibility`：`next_expected_in` 含具体章节名 → `"confirmed"`；模糊或缺失 → `"speculative"/"none"`
>    - `deferred_aspects`：仅 `deferred_credibility="confirmed"` 时填写，仅列高阶内容面（depth≥3）
>
> **`depth_gate_result` 字段**（开发者深度门控 + 图谱交叉参照，每个 KP 必须填写）：
>    - **前置依赖**：SKILL.md Step C1.5 的预合成图谱扫描结果（`chapter_depth_scan`），含每个概念的 `depth_verdict` 和 `developer_min_depth`
>    - 对每个 `priority=core` 的 KP：
>      1. 查找 `chapter_depth_scan` 中该概念的 `depth_verdict`
>      2. `depth_verdict = "escalate"` → `synthesis_depth` 设为 `developer_min_depth`，`depth_gate_result = "escalated"`
>      3. `depth_verdict = "supplement"` → 确保新侧面完整展开，`depth_gate_result = "escalated"`
>      4. `depth_verdict = "adequate"` → `depth_gate_result = "pass"`
>      5. `depth_verdict = "defer"` → `depth_gate_result = "deferred"`，记录到 `deferred_aspects` 并在末尾速查表中体现
>    - **type_system 类概念额外约束**（概念类别含 type/cast/conversion/primitive）：即使 `"adequate"`，也检查 `aspects_covered` 是否含 `"pitfall"`——若缺少，补充 ≥1 个陷阱代码示例
>    - `priority=extend/reference` → `depth_gate_result = "pass"`（不强制提升）

---

**步骤 ON+1：填入 synthesis_plan**（`replace_string_in_file`，JSON 至此成为合法格式）

按以下规则计算 `synthesis_plan` 后：
1. 将所有 `content_type ≠ "exclude"` 的 KP，按 `narrative_position` 排序
2. 从第 1 个 KP 开始累加 `word_count_target`，累计值超过当次安全写盘阈值时切割出一组（当前 KP 放入下一组）；基准：每组 **3-5 个 KP**，depth=3 偏多时取低限，不确定时宁小勿大
3. 每组写入 `groups[].kp_ids`（id 列表）、`est_words`（本组估算词数）、`note`（一句话描述本组主题）
4. `total_estimate_words` = 所有 KP 的 `word_count_target` 之和；`group_size_limit` = 本次实际使用的分组阈值
5. 只有一组时（章节很小）也必须写 `groups` 数组（含 1 个元素）

**gap_fill_group 自动插入（ON+1 步骤中，synthesis_plan 分组完成后）**：
>    扫描 `COMPLETENESS_AUDIT` 中所有 `priority=core` 的浅层核心概念：
>    - 若已被常规 `groups[].kp_ids` 覆盖 → 仅在对应 KP 上设 `synthesis_depth ≥ 2`，无需新增分组
>    - 若**未被任何常规分组覆盖** → 在 `groups` 末尾追加：
>      ```json
>      { "id": "gap_fill", "is_gap_fill": true, "kp_ids": ["..."], "est_words": 600,
>        "note": "兜底补写区：视频讲浅但后续未能充分深化的核心概念，以 synthesis_depth=2 展开" }
>      ```

> ⚠️ `synthesis_plan` **不可省略**——Synthesis Pass 依赖它决定占位符追加链的循环次数；`code_anchors` **不可为空**——Pass 2b/2c 依赖它生成精准题目和 Anki 卡片。

**全部步骤（O1 ~ ON+1）完成后**，告知用户“✅ Pass 1 完成”。然后 **AI 自行评估剩余输出容量**：充足则直接继续 Pass 2a，不足则告知用户“请发送任意消息继续 Pass 2a（综合知识文档）”。

---

## Pass 2a · 综合知识文档（`PASS_MODE = "synthesis"`）

> 🔴 **强制输出卡点（防超时核心机制）**：本 Pass 的任务是生成并保存 `CHAPTER_SYNTHESIS_*.md`。  
> **必须使用占位符追加链逐组写入**（见下方“占位符追加链写入规范”），**严禁一次性生成整个文档后再调用 `create_file`**。  
> SYNTHESIS 完整保存后，AI 自行评估剩余容量决定是否继续生成 EXERCISES（规则 A）。  
> 所有组写入完成的标志：占位符 `<!-- SYNTHESIS_PENDING -->` 已在步骤 SN+1 中消亡（见下方 ✅ Pass 2a 完成检查点）。

**前置**（若使用了 Outline Pass）：使用 `read_file` 从磁盘加载 `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/chapter_outline.json`（Pass 1 产物），读取 `synthesis_plan.groups` 作为分组依据。轻量章节跳过 Outline Pass 时直接忽略此步骤，按步骤 S0 自动计算分组。

**输入**：`CHAPTER_OUTLINE`（若有）或直接基于 `CHAPTER_SUMMARIES`

> ⚠️ **跳过 Outline Pass 时的 Stage 0 强制提示**：
> 轻量章节直接进入 synthesis pass 时，**Stage 0 内容价值分类门仍然必须执行**——在读取 CHAPTER_SUMMARIES 后、开始写正文之前，先按 Stage 0 三桶分类规则把所有内容标记为 skill / mental_model / **exclude**。  
> **exclude 类内容直接丢弃，不以任何形式写入文档。**  
> Stage 0 不因跳过 Outline Pass 而豁免。  
> （Stage 0 完整规则及分类表——见本文件 §Pass 1 · Outline Pass → 【强制前置】Stage 0 章节）
>
> **跳过 Outline Pass 时的深度门控**：
> 轻量章节在 S0 分组后、S1 开始写文档前，需执行 SKILL.md Step C1.5 的预合成图谱扫描，然后对每个 `priority=core` 的概念执行开发者深度门控检查（规则同 Outline Pass 的 `depth_gate_result` 字段说明）。基于 `chapter_depth_scan` 的 `depth_verdict` 决定是否提升写作深度。

---

### 🔴 占位符追加链（Placeholder-Chain）写入规范（**所有章节必须执行**）

> **为什么不能一次性生成整个文档**：AI 生成文字进入响应流，`create_file` 在生成结束后才调用。  
> 若一次生成 15,000 字（典型标准章节），超过模型单响应输出 token 上限后文件永远无法保存。  
> 占位符追加链将每次写盘前的生成量控制在单次响应安全范围内（每组 3-5 个知识点），彻底消除溢出风险。

**执行步骤（严格按序，不可跳过任何步骤）**：

**步骤 S0：确定分组**
- 若有 `chapter_outline.json`：读取 `synthesis_plan.groups`（Pass 1 已计算好），直接使用
- 若无 outline（轻量章节）：从 `CHAPTER_SUMMARIES` 中列出所有 depth≥1 且非 exclude 概念，按认知递进顺序排列；根据各概念 depth 估算字数（depth=1 → 约 500词，depth=2 → 约 900词，depth=3 → 约 1500词），从第 1 个概念开始累加，超过当次安全阈值时切割出一组（基准：每组 3-5 个概念，不确定时宁小勿大）；即使整章仅 1 组也须走完以下流程

**步骤 S1：写文档头部**（`create_file`，**本步骤仅含标题、导航、目录等骨架，生成量较小**）

生成并立即以 `create_file` 保存以下内容（注意末尾占位符）：
```
# {CHAPTER_NAME}

> **中心类比**：{central_metaphor}

**学习目标：**
{blueprint.learning_goals — 3-5 个可验证陈述，每条用"能…"格式}

---

## 快速导航

| 学习路径 | 推荐内容 |
|---------|---------|
| **30 分钟速读** | {speedrun_30min 核心知识点跳转链接} |
| **完整学习（2小时）** | 按目录顺序全量阅读 |
| **前置要求** | {blueprint.prerequisites} |
| **下一章依赖** | {blueprint.next_chapter_dependency} |

---

## 目录
[完整目录，带跳转链接；相关知识点以"第X部分"分组]

---

<!-- SYNTHESIS_PENDING -->
```

> ❗ `<!-- SYNTHESIS_PENDING -->` 是追加链占位符，**必须原样写入**，后续 replace 操作依赖它。

**步骤 S2 ~ SN：逐组追加 KP 节**（每组 `replace_string_in_file`，**每步生成量控制在单次响应安全范围内，基准 3-5 个 KP**）

对 groups 中的第 G 组（G = 1, 2, ..., N），按以下方式执行：

1. 生成第 G 组内所有 KP 的完整节文本（遵循节格式规范，见下方"产物"部分；分部标题用 `## 第X部分`，单个 KP 节用 `### {编号}.`）
2. 调用 `replace_string_in_file`，将：
   - `old_string` = `<!-- SYNTHESIS_PENDING -->`
   - `new_string` = `{第 G 组的所有节文本}\n\n<!-- SYNTHESIS_PENDING -->`
3. 保存确认后，继续第 G+1 组

> 💡 每次 replace 都把占位符向后推移一组——文档不断增长，占位符始终在末尾。

**步骤 SN+1：写参考来源表 + 速查表 + 收尾**（`replace_string_in_file`，**本步骤含末尾三部分：参考来源表 → 速查表 → 结束行**）

调用 `replace_string_in_file` 将 `<!-- SYNTHESIS_PENDING -->` 替换为：
```
---

## 📚 权威参考来源

| 知识点 | 权威来源 |
|--------|----------|
{遍历本章所有知识点（按节编号顺序），每个知识点一行：
 - "知识点"：知识点名称（与正文节标题一致）
 - "权威来源"：该知识点依据的 P1/P2/P3 锚点（如 JLS §4.2 / JVMS §2.3.4 / Effective Java Item 6 等）
 注意：正文中不出现任何内联 `> 来源：` 标注，所有权威来源统一在此表列出。}

---

## 📋 知识点深度与后续规划速查表

| 知识点 | 本章深度 | 目标深度 | 后续规划 | 说明 |
|--------|---------|---------|---------|------|
{遍历 outline.json 中所有 deferred_credibility ≠ null 或 depth < expected_max_depth 的 KP，逐行填写：
 - "本章深度"：当前 synthesis_depth 对应的层级描述（如"depth=1 引介"）
 - "目标深度"：expected_max_depth 对应的层级描述
 - "后续规划"：✅ {confirmed_in 章节} / ❓ 本课程可能不覆盖 / ✅ {正式讲解章节}（隐性知识）
 - "说明"：一句话描述缺口或状态

 同时遍历 implicit_concepts（depth=0.5 的隐性知识），填入表格：
 - "本章深度"：depth=0.5 隐性（代码中出现）
 - "后续规划"：✅ {预期讲解章节}
 - "说明"：{首次出现的视频} 代码中已出现

 若没有需要列入速查表的条目，则不生成此表（直接写收尾行）。}

---

*本章学习手册完 · 共 {N} 个知识点*  
*下一章：{blueprint.next_chapter_name} | 练习题 → [CHAPTER_EXERCISES_{chapter_dir_name}.md](./CHAPTER_EXERCISES_{chapter_dir_name}.md)*
```
（本步骤不添加新占位符，占位符至此消亡）

**全部步骤完成后**，告知用户“✅ CHAPTER_SYNTHESIS 已保存（共写入 N 组）”。然后 **AI 自行评估剩余输出容量**：充足则直接继续 Pass 2b，不足则告知用户“请发送任意消息继续 Pass 2b（练习题）”。

---

### 产物（Pass 2a）：章节综合知识文档（CHAPTER_SYNTHESIS.md）

#### 文档结构

```markdown
# {CHAPTER_NAME}

> **中心类比**：{central_metaphor}

**学习目标：**
{blueprint.learning_goals — 3-5 个可验证陈述，每条用"能…"格式}

---

## 快速导航

| 学习路径 | 推荐内容 |
|---------|---------|
| **30 分钟速读** | {speedrun_30min 核心知识点跳转链接} |
| **完整学习（2小时）** | 按目录顺序全量阅读 |
| **前置要求** | {blueprint.prerequisites} |
| **下一章依赖** | {blueprint.next_chapter_dependency} |

---

## 目录

{按 narrative_position 排列知识点，带内部跳转链接；相关知识点按主题分组，格式："## 第X部分：主题名"}

---

{各知识点完整展开，按 narrative_position 顺序，以"## 第X部分：主题名"分组}

分部格式：
## 第X部分：{主题名}（汇集同属一个技术主题的相邻知识点）

> **叙事定位**：{一句话说明此部分在全章位置及承上启下作用}

---

知识点节格式：
### {编号}. {知识点名称} {⭐|📦|🔍}
（编号为全章连续递增的序号——如第一部分含 1-5，第二部分从 6 开始，不按部分重新编号）
（优先级标记来自 outline.json 的 `priority` 字段：core=⭐，extend=📦，reference=🔍）

{connector.from_previous — 承接上一节的过渡语，让读者感受到连贯叙事；必须引用 central_metaphor}

{切入段：模仿老师开场方式，用问题/场景/类比引出}

{完整知识讲解：定义 + 类比 + 图示/表格 + 代码示例 + 常见陷阱}

{前置知识补充块（如有依赖）：
> 💡 回顾：{前置概念} 是指 {一句话}，在本章第 X 节中介绍过。}

{注意：正文中不插入任何推迟注解（不使用"后续深入""你已经见过它了""扩展了解"等标记）。
 正文中不插入 `> 来源：` 内联标注——所有权威来源统一在文档末尾「📚 权威参考来源」表格中列出。
 隐性知识在正式讲解处自然展开，无需提示"你已经见过"。
 深度缺口和后续规划信息统一收录到文档末尾的「知识点深度与后续规划速查表」中。
 正文只写纯粹的技术内容，保持阅读流畅不中断。}

---

*本章学习手册完 · 共 {N} 个知识点*  
*下一章：{blueprint.next_chapter_name} | 练习题 → [CHAPTER_EXERCISES_{chapter_dir_name}.md](./CHAPTER_EXERCISES_{chapter_dir_name}.md)*
```

#### 写作原则（按重要性排序）

**原则 1：独立完整（首要原则）**

读者无需查阅任何视频级文档即可独立完成本章学习。视频级 knowledge_*.md 是原材料，不是本文档的前置阅读。

- 验证方法：写完后问自己——"一个对本章完全陌生的人，仅凭本文档，能否回答所有练习题？" 能 = 合格。不能 = 找出缺失的讲解，补充完整。
- **严禁**写"详见 knowledge_XXX.md"之类的引用来代替解释。

**原则 2：深度合理，不摘要也不过度展开**

每个知识点的写作深度由 **`priority`（⭐📦🔍）× `synthesis_depth`** 共同决定：`priority` 定上限，`synthesis_depth` 定下限（gap_fill 机制）。两者冲突时 **priority 上限优先**。

**① `priority` 上限（天花板，先查此表）**

| 优先级 | 语义 | 字数上限 | 写法要求 |
|--------|------|---------|----------|
| ⭐ `core` | 初学必须掌握 | 无硬限（按 synthesis_depth 弹性展开） | 正常深度展开 |
| 📦 `extend` | 深入理解时读 | **≤ 400 字** | 定义 + 一句类比 + 要点列表；无需代码示例，无需完整陷阱分析 |
| 🔍 `reference` | 遇到时查阅 | **≤ 150 字** | 一句话定义 + 查阅入口（链接/书名）；禁止大篇展开 |

> ⚠️ **priority 上限是硬约束**：即使 `extend` 概念的 `synthesis_depth=2`，也不得超过 400 字展开。extend/reference 概念在章节综合文档中应"点到为止"，详细内容留给后续真正以它为主题的章节去讲。

**② `synthesis_depth` 下限（地板，仅适用于 `priority=core`）**

| 知识点深度 | 必须包含 | 字数参考 |
|-----------|---------|--------|
| depth=1（引介） | 定义 + 类比 + 简单示例 + 常见误解 | 400-700 字 |
| depth=2（运用） | **本章场景内**的完整用法 + ≥2 个可运行代码示例 + 本章常见陷阱 + 与直接相关概念对比 | 700-1200 字 |
| depth=3（原理） | depth=2 的全部 + 底层机制 + JVM/规范层解释 + 版本差异 | 1200-2000 字 |

> ⚠️ **depth=2 的"完整"是章节范围内完整，不是工具/API 文档级完整**。  
> 示例：javac depth=2 → 会用 `javac HelloWorld.java`、能读懂报错行号和 `error:` 信息、知道常见的 `cannot find symbol` 原因 ✅  
> 不是 → javac 所有命令行参数（`-cp`、`-d`、`-encoding` 等）、交叉编译选项 ❌（那些属于 depth=3+，后续章节按需引入）

整章文档**最低总字数**：≥4000字；核心概念≥5个的章节应达6000+字。

**原则 2.5：差量深度保障（gap_fill 兜底，不可绕过）**

对于 `synthesis_treatment = "gap_fill"` 的知识点（视频 `depth < 2` 的 `priority=core` 概念）：

1. **写作深度目标以 `synthesis_depth` 为准，不以视频实际 `depth` 为准。** 视频只讲到 depth=1 → 综合文档必须写到 `synthesis_depth=2`（**本章场景内**的完整用法 + ≥2 个可运行示例 + 本章常见陷阱 + 直接相关概念对比，字数参考 700-1200 字）。

   > **"本章场景内"的约束（防过度展开）**：gap_fill 输出的 depth=2 内容必须锚定在**当前章节实际用到的操作范围**内，不得扩展到后续章节才会用到的高级用法。
   > - ✅ 应写：`javac HelloWorld.java` 用法 + 编译报错的行号/错误类型阅读方式
   > - ❌ 不写：`-classpath`、`-d`、`-encoding` 等参数（day01 用不到，后续按需引入）
   > - ✅ 应写：`cd 文件夹名`、`D:` 盘符切换、`dir` 列目录
   > - ❌ 不写：`xcopy`、重定向符、批处理脚本（day01 用不到）
   >
   > 判据：**"在完成本章所有练习题时，学习者是否会用到这个操作？"** 会用到 → 写；不会用到 → 不写（哪怕它属于该工具的"基础"知识）。

2. **严禁**对 `synthesis_depth ≤ 2` 的内容使用任何推迟注解来替代正文展开——这是 gap_fill 机制的核心约束。正文中不出现"后续深入""扩展了解"等标记，所有后续规划信息统一写入末尾速查表。

3. **速查表收录规则**（根据 `deferred_credibility`，仅适用于 depth≥3 的高阶内容面）：
   - `"confirmed"` → 速查表"后续规划"列填 `✅ {confirmed_in 章节}`
   - `"speculative"` / `"none"` → 速查表"后续规划"列填 `❓ 本课程可能不覆盖` + 推荐资料

4. **gap_fill_group 位置**：若 outline.json 中存在 `"is_gap_fill": true` 分组，在占位符追加链末尾写入。节结构同常规 KP 节（无特殊标注），对读者完全透明。

**原则 3：概念贯通，显式连接（仅用承接语，不预告后续）**

视频文档各自孤立，章节综合文档的核心价值在于“串联”。必须在合适位置显式指出概念间关联：

- **承接**：「有了上面对 {概念A} 的认识，下面的 {概念B} 就好理解了——」
- **对比**：「{概念A} 和 {概念B} 很容易混淆，我们来专门对比一下：」
- **呼应**：「还记得本章第2节提到的 {概念A} 吗？这里的 {概念B} 正是它的具体体现」
- **铺垫**：在讲某概念前，先用真实场景引出（“假设你现在需要...”）
- **依赖说明**：当一个概念 depends_on 另一个时，在该节开头用一句“要理解 {概念B}，需要先有 {概念A} 的基础——{depends_on.reason}”

> ❌ **不预告后续内容**：知识点结尾处**不预告下一节内容或该知识点在后续章节的发展**。正文中不出现 `后续深入`、`你已经见过它了`、`扩展了解` 等推迟注解——这些信息统一收录到文档末尾的「知识点深度与后续规划速查表」中。每个知识点以最后一个技术内容自然结束，避免分散读者对当前知识点的专注力。
>
> **区分**：上述规则禁止的是**结构化推迟标记**（blockquote + emoji + 明确说"后续讲/已规划"），而非所有前向提及。正文中为了技术准确性而简短提及后续概念是允许的（如"小范围类型的值可以自动放进大范围类型的容器里"暗示类型转换），只要不使用推迟注解格式、不以此替代正文展开即可。

**outline.json 中 `connectors` 字段仅含 `from_previous`**（承接上一节的过渡语），synthesis pass 时必须将它们写进正文。所有连接语必须引用 `central_metaphor`。

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

隐性知识（代码中出现过但未正式讲解的概念）在正式讲解处**自然展开**，无需插入"你已经见过它了"等提示。正文中像讲解任何新概念一样完整讲解即可。隐性知识的追踪信息（首次出现的视频、正式讲解位置）统一收录到文档末尾的「知识点深度与后续规划速查表」中。

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

**同时**，文档开头「快速导航」表中的 30 分钟速读列仅列 ⭐ 核心概念。读者可自主选择速读还是精读，不强制全量。

**原则 10：内容类型硬约束（Stage 0 分类结果具有强制力，不可绕过）**

`outline.json` 的 Stage 0 分类结果对 synthesis pass 具有强制约束力：

| 字段值 | Synthesis Pass 必须执行的规则 |
|-------|------------------------------|
| `content_type: "exclude"` | **该知识点不得以任何形式出现在 CHAPTER_SYNTHESIS / CHAPTER_EXERCISES / CHAPTER_ANKI 任何位置**； 历史故事、励志内容、行业数据、讲师介绍均属此类，一字不写 |
| `synthesis_treatment: "brief"` | 该知识点字数硬上限为 `max_words`，超出部分截断，仅保留核心定义 |
| `max_words` 不为 null | 该节实际字数（含代码块、表格）不得超过此值，优先删减示例 |

> 💡 **避免误判**：技术决策依据（如"Java 8/17/21 是 LTS 需要选用"）即使来自教师的铺垫性叙述，仍属于 SKILL，不受 exclude 约束。  
> 判据：**删掉这段内容后，用户在理解技术原理、写代码、调试或部署时会受到影响吗？** 受影响（含影响技术理解）→ SKILL/MENTAL_MODEL；不受影响 → EXCLUDE，无条件丢弃。

**原则 11：权威来源集中展示（正文不内联来源标注）**

正文中**不使用** `> 来源：{锚点}` 内联标注。每个知识点的权威来源统一收录到文档末尾的「📚 权威参考来源」表格中（见步骤 SN+1），按知识点→来源的映射关系列出。正文保持纯粹的技术讲解，不被来源标注打断阅读流。

---

> ✅ **Pass 2a 完成检查点**：确认步骤 SN+1（尾部区块 replace）成功、`<!-- SYNTHESIS_PENDING -->` 占位符已消亡后，告知用户  
> “✅ CHAPTER_SYNTHESIS 已保存（共 N 组写入）”，然后按规则 A 自行判断是否继续。

---

## Pass 2b · 章节练习文档（`PASS_MODE = "exercises"`）

> 🔴 **强制输出卡点**：本 Pass 的任务是生成并保存 `CHAPTER_EXERCISES_*.md`。必须使用占位符追加链分步写入，严禁一次性生成。
> EXERCISES 完整保存后，AI 自行评估剩余容量决定是否继续生成 ANKI（规则 A）。

### 🔴 Pass 2b 执行协议（占位符追加链 + code_anchors 主源）

**前置步骤（禁止跳过）**：
1. **若有 Outline Pass 产物**：使用 `read_file` 加载 `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/chapter_outline.json`（Pass 1 产物，禁止依赖上一轮内存）
   - 获取 `synthesis_plan.groups`（分组规划，与 synthesis pass 同一套分组）
   - 获取每个 KP 的 `code_anchors`（精准出题锚点）
   - 获取 `total_estimate_words`（决定走哪条输入策略）
   **若轻量章节（无 outline.json）**：使用 `read_file` 一次性读取 CHAPTER_SYNTHESIS 全文作为出题依据，从文中提取知识点和代码示例作为出题锚点
2. 根据章节体量选择输入策略：

| synthesis 预估字数 | 主出题源 | 补充读取 |
|---|---|---|
| < 8,000 字（轻量）| `read_file` 一次性读取 SYNTHESIS 全文 | 无需额外操作 |
| 8,000 – 20,000 字（标准）| outline.json 各 KP 的 `code_anchors` | 可选：按 groups 分段读 SYNTHESIS 对应节强化细节 |
| > 20,000 字（大型）| **仅用 outline.json + `code_anchors`**，不读取 SYNTHESIS 文件 | 无 |

**执行步骤（占位符追加链，输入输出双侧受控）**：

**步骤 E0：确认分组**
复用 `synthesis_plan.groups` 的分组（与 synthesis pass 完全一致），确保每组练习与综合文档节结构对齐。

**步骤 E1：写练习文档头部**（`create_file`，仅头部骨架，生成量极小）

```
# 练习题 · {CHAPTER_NAME}

> 来源：综合本章 {N} 个视频的知识内容
> 本章知识文档：[CHAPTER_SYNTHESIS_{chapter_dir_name}.md](./CHAPTER_SYNTHESIS_{chapter_dir_name}.md)

---

<!-- EXERCISES_PENDING -->
```

> ❗ `<!-- EXERCISES_PENDING -->` 是追加链占位符，**必须原样写入**，后续 replace 操作依赖它。

**步骤 E2 ~ EN：逐组生成练习题**（每组 `replace_string_in_file`，每步生成量控制在安全范围内）

对第 G 组（按 `synthesis_plan.groups` 顺序）：
1. 从已读入的 outline.json 取该组所有 KP 的 `code_anchors` 作为出题锚点
2. 若是轻量章节，可直接引用已读入的 SYNTHESIS 文本对应节
3. 基于锚点生成该组练习题（含题干 + 参考答案 + `📖 参考：CHAPTER_SYNTHESIS 第 X 节`）
4. 调用 `replace_string_in_file`：
   - `old_string` = `<!-- EXERCISES_PENDING -->`
   - `new_string` = `{第 G 组的所有练习题文本}` + 两个换行 + `<!-- EXERCISES_PENDING -->`

> 💡 占位符逐组向后推移，每次写盘前生成量控制在安全范围内，彻底消除输出截断风险。

**步骤 EN+1：面试题专区**（`replace_string_in_file`，**占位符后移，继续留存**）

基于 outline.json 中全部 ⭐（`priority=core`）KP 的 `code_anchors` + `central_metaphor` 生成"面试题精选"区块（生成量可能较大，因此独立成一步）：
- `old_string` = `<!-- EXERCISES_PENDING -->`
- `new_string` = `{面试题精选区块，含全部面试题 Q&A}` + 两个换行 + `<!-- EXERCISES_PENDING -->`

**步骤 EN+2：总练习索引**（`replace_string_in_file`，**占位符消亡**）

生成本章练习的简洁知识点→题号映射索引（内容极小，约 50-100 字）：
- `old_string` = `<!-- EXERCISES_PENDING -->`
- `new_string` = `{总练习索引}`（不添加新占位符，占位符至此消亡）

两步全部完成后，告知用户“✅ Pass 2b 完成”。然后 **AI 自行评估剩余输出容量**：充足则直接继续 Pass 2c，不足则告知用户“请发送任意消息继续 Pass 2c（Anki）”。

---

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

**阶段 1：系统生成全章题目集**

以 CHAPTER_SYNTHESIS.md（或 outline.json 的 `code_anchors`，取决于上方执行协议中的输入策略）为知识源，为每个知识点（depth≥1）生成题目：

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
> “✅ CHAPTER_EXERCISES 已保存”，然后按规则 A 自行判断是否继续。

---

## Pass 2c · Anki 卡包（`PASS_MODE = "anki"`）

> 🔴 **强制输出卡点**：本轮次**唯一任务**是生成 CSV 并打包 apkg。  
> **前置**：
> 1. **若有 Outline Pass 产物**：读取 `{CHAPTER_DIR}/CHAPTER_SYNTHESIS_{chapter_dir_name}/chapter_outline.json`——获取各 KP 的 `code_anchors`、`depth`、`priority`、`content_type`，这是 Anki 卡片类型和数量决策的主依据（禁止依赖上一轮内存）
>    **若轻量章节（无 outline.json）**：使用 `read_file` 读取 CHAPTER_SYNTHESIS 全文，从文中提取知识点和代码示例作为卡片生成依据
> 2. 标准/大型章节根据 `total_estimate_words` 决定是否补充读取 SYNTHESIS：< 8,000 字时可 `read_file` 读取全文补充细节；≥ 8,000 字时仅凭 outline.json 的 `code_anchors` 生成，不读取大文件  
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
- [ ] 文档开头有"学习目标"列表 + "快速导航"表（含 30分钟速读、完整学习、前置要求、下一章依赖四行）
- [ ] 完整目录，带内部跳转链接
- [ ] 所有知识点按"最优认知顺序"排列（`narrative_position`），非按视频顺序
- [ ] 每个知识点节标题带优先级标记（⭐/📦/🔍）
- [ ] 节与节之间有承接语（来自 outline.json `connectors.from_previous`），且引用了 `central_metaphor`
- [ ] 知识点结尾处无"预告下一节"或"后续发展方向"类叙事过渡，无内联推迟注解
- [ ] 有依赖关系的知识点节开头有"理解 B 需要先有 A 的基础——{reason}"说明

**内容纯洁性（Stage 0 强制检查）**
- [ ] **文档中不存在任何** 励志话语 / 历史故事 / Java 市场排名 / 讲师介绍 / 广告语 / "为什么学 Java" 类内容
- [ ] 每个知识点节的第一句话是技术内容，而非学习价值说明
- [ ] 文档导读段仅含技术性说明（学完后能做什么），无任何非技术前言

**内容完整性**
- [ ] 同一概念在多个视频涉及的 → 已合并为一个完整节（不是多处摘要）
- [ ] 隐性知识（`implicit_concepts`）已在正式讲解处自然展开（无需"你已经见过它了"内联提示）
- [ ] 正文中**不存在**任何 `💡 后续深入`、`📚 扩展了解`、`💡 你已经见过它了` 等内联推迟注解
- [ ] 深度缺口和后续规划信息已在文档末尾「📋 知识点深度与后续规划速查表」中列出（若有需要列入的条目）
- [ ] 文档末尾结构为：权威参考来源表 → 速查表（若有）→ 收尾行（"本章学习手册完 · 共 N 个知识点"）

**来源标注**
- [ ] **正文中无任何 `> 来源：` 内联标注**（所有权威来源统一在末尾「📚 权威参考来源」表格中列出）
- [ ] 末尾「📚 权威参考来源」表格覆盖了所有 ⭐ 核心概念的权威来源（P1/P2/P3 锚点）

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

**隐性知识与深度提示**
- [ ] 图谱中所有 `implicit_concepts`（depth=0.5）已在正文相关讲解处自然展开（不使用"你已经见过"提示）
- [ ] 隐性知识的追踪信息（首次出现视频 + 正式讲解位置）已写入末尾速查表
- [ ] depth < expected_max_depth 的概念已按 `deferred_credibility` 写入末尾速查表：`confirmed` → ✅ + 后续章节；`speculative/none` → ❓ + 推荐资料
- [ ] **正文中无任何内联推迟注解**（`💡 后续深入` / `📚 扩展了解` / `💡 你已经见过它了` 均不得出现在正文中）
- [ ] **gap_fill 兜底检查（强制）**：`COMPLETENESS_AUDIT` 中所有 `priority=core` 的浅层核心概念（在本章视频中 `depth < 2`），要么已在正文以 `synthesis_depth=2` 完整展开；要么已归入 `gap_fill_group`；【不允许】仅在速查表标注了事
- [ ] **开发者深度门控检查**：每个 `priority=core` 的 KP 均已通过深度门控（outline.json `depth_gate_result` 字段为 `"pass"` 或 `"escalated"`）