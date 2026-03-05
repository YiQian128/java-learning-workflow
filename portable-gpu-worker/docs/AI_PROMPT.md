# 便携式 GPU 预处理包 - AI 协作说明

## 用途

本目录为可独立复制的视频预处理包，用于在带 GPU 的 Windows 设备上离线运行：
- 音频提取（FFmpeg）
- 字幕转写（faster-whisper）
- 关键帧提取（FFmpeg 场景检测）
- 长视频分段（按静音点切割）

## 与父项目关系

- **脚本唯一实现**：预处理脚本位于 `portable-gpu-worker/scripts/`，父项目在检测到便携包时，应调用此目录下的脚本，避免维护两份代码。
- **固定工作区**：项目固定使用 `portable-gpu-worker` 的 `videos/` 和 `output/`，父项目 pipeline 直接读取。

## 路径约定

- 脚本以 `Path(__file__).resolve().parent` 为基准，不假设父项目存在。
- 配置：`portable-gpu-worker/config/config.yaml`
- 模型缓存：`portable-gpu-worker/_env/models/`

## 预处理产物结构

> 路径跟随 `videos/` 目录结构镜像到 `output/`：
> - 若视频在 `videos/Java基础-视频上/day01-Java入门/01-xxx.mp4`，产物路径为 `output/Java基础-视频上/day01-Java入门/01-xxx/_preprocessing/`
> - 若视频直接在 `videos/01-xxx.mp4`（无子目录），产物路径为 `output/01-xxx/_preprocessing/`（以下示例为此简化情形）

```
output/{video_stem}/
└── _preprocessing/
    ├── {stem}_audio.wav
    ├── {stem}.srt
    ├── {stem}_words.json
    ├── frames/
    │   ├── scene_*.jpg
    │   └── interval_*.jpg
    └── segments/          # 长视频分段时
        ├── _split_info.json
        └── {stem}_part*.mp4
```

## 调用脚本示例

```bash
# 从便携包根目录或父项目调用
python portable-gpu-worker/scripts/extract_audio.py --video X.mp4 --output out.wav
python portable-gpu-worker/scripts/transcribe.py --video X.mp4 --output-dir out/ --model medium
python portable-gpu-worker/scripts/extract_keyframes.py --video X.mp4 --output-dir frames/
python portable-gpu-worker/scripts/split_video.py --video X.mp4 --output-dir segs/ --json
```
