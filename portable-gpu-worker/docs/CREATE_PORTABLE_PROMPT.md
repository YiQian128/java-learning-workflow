# 便携式预处理包 - 创建提示词

## 使用方式

1. 将本文件内容（或路径）交给 AI，并说明项目根目录路径
2. 若项目尚无 `portable-gpu-worker`，可将本文件放在项目根目录（如 `docs/` 或 `.cursor/prompts/`）供 AI 读取
3. AI 将在项目根目录下创建 `portable-gpu-worker` 文件夹及全部内容

## 创建任务说明

### 目标

在项目根目录创建 `portable-gpu-worker/` 文件夹，使其成为可独立复制到其他 Windows 设备（尤其是有 GPU 的机器）上运行的视频预处理包。支持离线使用，无需原项目开发环境。

### 核心原则：避免冗余

- **预处理脚本的唯一存放位置**：`extract_audio.py`、`transcribe.py`、`extract_keyframes.py`、`split_video.py` 等预处理脚本**直接放在** `portable-gpu-worker/scripts/` 中，作为该便携包的组成部分。
- **不复制、不引用父项目**：便携包自包含，不依赖从父项目 `scripts/` 复制脚本。父项目若需相同逻辑，应引用 `portable-gpu-worker/scripts/` 或与便携包共享这些脚本，避免在 `scripts/` 与 `portable-gpu-worker/scripts/` 之间维护两份相同代码。
- **配置同理**：`config/config.yaml` 直接放在 `portable-gpu-worker/config/`，可精简为便携包所需字段，不必与父项目保持完全一致。

## 必须创建的内容

### 1. 目录结构

```
portable-gpu-worker/
├── 0_开始使用.bat       统一入口（菜单选项：[1]联网准备 [2]离线准备 [3]开始预处理 [4]估算费用）
├── run.bat               封装层，转调 0_开始使用.bat
├── run_preprocess.py     预处理交互式主脚本（番号选择、进度显示）
├── setup/                环境准备脚本
│   ├── setup_env.py
│   ├── prepare_env.py
│   ├── bootstrap_standalone.py
│   ├── download_model.py
│   └── verify_offline.py
├── requirements.txt
├── README.txt
├── docs/
│   ├── AI_PROMPT.md
│   └── CREATE_PORTABLE_PROMPT.md
├── videos/
├── output/
├── scripts/
├── config/
└── _env/
```

### 2. 父项目需新增

- **scripts/prepare_portable_pack.py**：委托 portable-gpu-worker/prepare_env.py 下载资源到 `_env/`。
- **固定工作区**：项目固定使用 `portable-gpu-worker` 的 `videos/` 和 `output/`。

## 校验清单

- [ ] `portable-gpu-worker/scripts/` 下四个脚本可直接运行
- [ ] `0_开始使用.bat` 可执行，菜单各选项均正常调用
- [ ] README.txt 说明使用流程与离线准备步骤
