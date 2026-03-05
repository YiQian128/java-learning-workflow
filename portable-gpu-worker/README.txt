========================================
  便携式 GPU 预处理包 - 使用说明
========================================

【拆开即用】在联网环境准备好 _env 后，复制到目标机器即可离线运行。
所有脚本均使用本地 _env 资源，不依赖系统环境。

零、快速开始（推荐）

  双击 0_开始使用.bat，通过菜单完成所有操作。

  菜单选项：
    [1] 联网准备   — 首次使用，下载 Python/FFmpeg/模型（需联网）
    [2] 离线准备   — 将整包复制到新机器后运行，重建 venv
    [3] 开始预处理 — 扫描 videos/，转写字幕，提取关键帧
    [4] 估算费用   — 扫描视频时长，输出各 API 转写费用对比报价
    [0] 退出

  环境已就绪时直接回车将自动进入预处理，否则自动引导联网准备。

一、准备阶段（联网环境，网络良好时）

  在 0_开始使用.bat 主菜单选 [1] 联网准备
  或运行：python setup/setup_env.py --online

  首次使用需系统已安装 Python 3.12；若未安装会提示。

  将执行：
    1. 校验 _env 内容，下载/更新缺失资源（Python、FFmpeg、wheels）
    2. 设置环境（venv、依赖、FFmpeg 路径）
    3. 下载 Whisper 模型到 _env/models
    4. 校验 _env 资源完整
    5. 校验预处理脚本可正常运行

  _env/ 将包含：
    - python/        便携 Python
    - get-pip.py     便携 Python 安装 pip 用
    - ffmpeg/        FFmpeg 便携版
    - wheels/*.whl   pip 离线包
    - models/        Whisper 各体量模型（tiny/base/small/medium/large-v2/large-v3）

二、目标机器使用（网络差或离线、GPU 好）

  1. 将整个 portable-gpu-worker 文件夹复制到目标机器

  2. 双击 0_开始使用.bat，选 [2] 离线准备
     - 校验 _env 内容
     - 设置环境（venv、依赖）
     - 校验预处理脚本可运行
     - 不发起任何网络请求

  3. 将视频放入 videos/ 目录

  4. 双击 0_开始使用.bat，选 [3] 开始预处理（建议以管理员身份运行以获得 GPU 加速）
     - 扫描 videos/，交互选择要处理的视频
     - 选择转写方式：0=在线 API 或 1-6=本地模型
     - 根据当前 GPU 显存自动推荐模型，或手动选择（tiny/base/small/medium/large-v2/large-v3）
     - 自动执行：音频提取 → 字幕转写 → 关键帧提取
     - 长视频（>90分钟）自动按静音点分段

  5. 输出在 output/ 下，目录结构与 videos/ 保持一致
     例：videos/新建文件夹/01.mp4 → output/新建文件夹/01/_preprocessing/
     产物：*_audio.wav、*.srt、*_words.json、frames/*.jpg

三、目录结构

portable-gpu-worker/
├── 0_开始使用.bat      唯一入口（菜单式，含联网准备/离线准备/预处理/费用估算）
├── setup/              环境准备脚本
│   ├── setup_env.py    统一入口
│   ├── prepare_env.py  资源下载
│   ├── bootstrap_standalone.py
│   ├── download_model.py
│   └── verify_offline.py
├── run_preprocess.py   预处理主入口
├── requirements.txt
├── README.txt          本说明
├── docs/               AI 协作与创建提示词
├── videos/             放入视频
├── output/             预处理产物
├── scripts/            预处理脚本
├── config/             配置
└── _env/               环境资源（由 0_开始使用.bat → [1] 联网准备 填充）

四、与父项目协作

output/ 位于便携包内，主项目 pipeline 直接读取，可继续执行知识生成、Anki 卡包等流程。

五、BAT 脚本说明

只有一个入口文件：0_开始使用.bat（UTF-8 编码 + chcp 65001，IDE 与 CMD 均正确显示中文）

  双击后显示主菜单：
    [1] 联网准备   — 下载/更新 Python、FFmpeg、Whisper 模型、pip 依赖
    [2] 离线准备   — 校验 _env、创建/重建 venv，不发起网络请求
    [3] 开始预处理 — 若 venv 不存在会自动触发离线准备；建议以管理员身份运行
    [4] 估算费用   — 扫描 videos/ 时长，给出各 API 实时报价对比（SiliconFlow 目前免费）
    [0] 退出

  环境已就绪时直接回车进入预处理，未就绪时直接回车进行联网准备。
  每次操作完成后返回主菜单，便于连续操作。

六、在线 API 转写（可选，支持多家提供商）

  优点：无需下载本地模型、可快速开始；缺点：消耗 API 额度、需联网。
  大文件（>25MB）自动分片上传；多片转写时自动将上一片末尾文本作为 prompt，
  保证跨片技术术语一致。API 请求失败后自动重试（指数退避，最多 3 次）。

  支持的提供商（在 config/config.yaml 的 api.provider 中配置）：

  ┌─────────────┬────────────────────────────────────────────────────────────┐
  │ provider    │ 说明                                                        │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ openai      │ OpenAI 官方，model: whisper-1 或 gpt-4o-transcribe          │
  │             │ 环境变量: OPENAI_API_KEY                                    │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ groq        │ Groq，228x 实时速度，$0.04/h，段落级时间戳                  │
  │             │ model: whisper-large-v3-turbo（默认）或 whisper-large-v3    │
  │             │ 环境变量: GROQ_API_KEY（或 OPENAI_API_KEY 兜底）             │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ siliconflow │ 国内提供商，中文效果最佳，目前完全免费，无时间戳             │
  │             │ model: FunAudioLLM/SenseVoiceSmall（默认）                  │
  │             │ 环境变量: SILICONFLOW_API_KEY（或 OPENAI_API_KEY 兜底）      │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ aliyun      │ ★ 综合最优：中文专项，词级时间戳，每月 10h 完全免费         │
  │             │ model: paraformer-v2（支持普通话/方言/英文/日韩）            │
  │             │ 需额外配置 OSS 凭证，见 config/config.yaml → api.aliyun_oss  │
  │             │ 环境变量: DASHSCOPE_API_KEY                                  │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ azure       │ Azure OpenAI，需在 base_url 填写部署端点                    │
  │             │ 环境变量: AZURE_OPENAI_API_KEY（或 OPENAI_API_KEY 兜底）     │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ assemblyai  │ AssemblyAI，高准确率，支持说话人分离                        │
  │             │ 需先安装: pip install assemblyai                            │
  │             │ 环境变量: ASSEMBLYAI_API_KEY                                │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ deepgram    │ Deepgram，低延迟，nova-3 中文支持好                         │
  │             │ 需先安装: pip install deepgram-sdk                          │
  │             │ 环境变量: DEEPGRAM_API_KEY                                  │
  ├─────────────┼────────────────────────────────────────────────────────────┤
  │ custom      │ 任意 OpenAI 兼容接口（本地 Ollama、OneAPI、各类代理等）      │
  │             │ 需在 base_url 填写接口地址                                  │
  │             │ 环境变量: OPENAI_API_KEY                                    │
  └─────────────┴────────────────────────────────────────────────────────────┘

  配置示例（编辑 config/config.yaml）：

    # 使用 Groq（推荐新手，免费额度大）
    api:
      provider: "groq"
      model: "whisper-large-v3-turbo"
    然后设置环境变量: set GROQ_API_KEY=gsk_xxx

    # 使用国内 SiliconFlow
    api:
      provider: "siliconflow"
    然后设置环境变量: set SILICONFLOW_API_KEY=sk-xxx

  注意：api_key 也可直接填在 config.yaml 的 api.api_key 字段，
        但建议用环境变量，避免密钥意外提交到版本库。

七、模型下载说明

- 若模型下载失败（如 "peer closed connection"）：脚本会自动重试 3 次；若 tiny/base/medium 已成功则仍可继续使用，稍后重跑 0_开始使用.bat → [1] 联网准备 补齐。
- 若出现 "[WARN] faster_whisper 导入校验未通过"：先尝试运行 0_开始使用.bat → [3] 开始预处理，若预处理正常则可忽略；若失败，请查看输出的具体错误信息。
- 若出现 "Unsupported model binary version" 错误：多为 ctranslate2 版本与 faster-whisper 不兼容。
  解决步骤：
  1) 删除 _env/wheels 和 _env/venv，重新运行 0_开始使用.bat → [1] 联网准备（requirements 已限制 ctranslate2<=4.4.0）
  2) 若仍报错，删除 _env/models 后重新运行 0_开始使用.bat → [1] 联网准备 以重新下载模型
  3) 确认未使用嵌套目录（如 portable-gpu-worker\portable-gpu-worker），解压到单层路径
  4) 若使用国内镜像仍报错，可尝试从官网下载：设置 HF_TOKEN=hf_xxx 后运行 0_开始使用.bat → [1]
  5) 最后手段：先用 tiny 模型验证流程（选择模型时输入 1），再尝试 medium/large-v2
- 默认使用国内镜像 hf-mirror.com，无需令牌
- 若需从 HuggingFace 官网下载，请设置环境变量 HF_TOKEN=hf_xxx 后运行
- 将下载全部 6 个体量：tiny(~75MB)、base(~145MB)、small(~465MB)、medium(~1.5GB)、large-v2(~3GB)、large-v3(~3GB)
- 总约 10GB+，首次下载需较长时间，可分批多次运行 0_开始使用.bat → [1] 联网准备 补齐
