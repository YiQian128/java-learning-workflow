#!/usr/bin/env python3
"""
validate_aliyun.py - 阿里云 Paraformer + OSS 可行性验证

逐步验证：
  Step 1: 读取 config.yaml 配置
  Step 2: 验证 DashScope API Key（调用 Paraformer 转写一段公开示例音频）
  Step 3: 验证 OSS 凭证（上传一个 1KB 测试文件 → 生成签名 URL → 删除）
  Step 4: 端到端验证（上传真实音频 → Paraformer 转写 → 输出结果）
"""
from __future__ import annotations
import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"

SEP = "=" * 60

def load_config() -> dict:
    import yaml
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def step(n: int, title: str):
    print(f"\n{SEP}")
    print(f"  Step {n}: {title}")
    print(SEP)

def ok(msg: str):
    print(f"  [OK] {msg}")

def fail(msg: str):
    print(f"  [FAIL] {msg}")
    sys.exit(1)

# ─── Step 1: 读取配置 ──────────────────────────────────────────────────────────
step(1, "读取 config.yaml 配置")

cfg     = load_config()
api_cfg = cfg.get("api", {})
oss_cfg = api_cfg.get("aliyun_oss", {})

api_key    = api_cfg.get("api_key", "").strip()
provider   = api_cfg.get("provider", "")
model      = api_cfg.get("model", "paraformer-v2")
endpoint   = oss_cfg.get("endpoint", "").strip()
ak_id      = oss_cfg.get("access_key_id", "").strip()
ak_secret  = oss_cfg.get("access_key_secret", "").strip()
bucket     = oss_cfg.get("bucket_name", "").strip()
prefix     = oss_cfg.get("prefix", "paraformer-tmp/")

print(f"  provider        : {provider}")
print(f"  model           : {model}")
print(f"  api_key         : {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '(短)'}")
print(f"  oss.endpoint    : {endpoint}")
print(f"  oss.bucket      : {bucket}")
print(f"  oss.ak_id       : {ak_id[:8]}...{ak_id[-4:] if len(ak_id) > 12 else '(短)'}")

if not all([api_key, endpoint, ak_id, ak_secret, bucket]):
    fail("配置不完整，请检查 config.yaml")
ok("配置读取完成")

# ─── Step 2: 验证 DashScope API Key ───────────────────────────────────────────
step(2, "验证 DashScope API Key（转写公开示例音频）")

try:
    import dashscope
    from dashscope.audio.asr import Transcription
    from http import HTTPStatus
except ImportError:
    fail("dashscope 未安装，请运行: pip install dashscope")

dashscope.api_key = api_key

# 使用阿里云官方示例音频（公网可访问，无需上传）
TEST_AUDIO_URL = (
    "https://dashscope.oss-cn-beijing.aliyuncs.com"
    "/samples/audio/paraformer/hello_world_female2.wav"
)

print(f"  测试音频 : {TEST_AUDIO_URL}")
print(f"  提交转写任务...")

try:
    task_resp = Transcription.async_call(
        model=model,
        file_urls=[TEST_AUDIO_URL],
        language_hints=["zh", "en"],
        timestamp_alignment_enabled=True,
    )
    task_id = task_resp.output.task_id
    print(f"  任务 ID  : {task_id}")
    print(f"  等待完成...")

    result = Transcription.wait(task=task_id)

    if result.status_code != HTTPStatus.OK:
        fail(f"API 请求失败: HTTP {result.status_code} {result.message}")

    output = result.output
    task_status = getattr(output, "task_status", None) or output.get("task_status", "")
    results = getattr(output, "results", None) or output.get("results", [])

    if not results or results[0].get("subtask_status") != "SUCCEEDED":
        fail(f"任务状态异常: {task_status}, results={results}")

    # 下载并解析识别结果
    import urllib.request
    result_url = results[0]["transcription_url"]
    with urllib.request.urlopen(result_url, timeout=30) as resp:
        result_json = json.loads(resp.read().decode("utf-8"))

    sentences = result_json.get("transcripts", [{}])[0].get("sentences", [])
    text = " ".join(s.get("text", "") for s in sentences)
    words_count = sum(len(s.get("words", [])) for s in sentences)

    ok(f"API Key 有效，模型响应正常")
    ok(f"识别文本: 「{text[:80]}」")
    ok(f"词级时间戳: {words_count} 个词")

except Exception as e:
    fail(f"DashScope API 验证失败: {e}")

# ─── Step 3: 验证 OSS 凭证 ─────────────────────────────────────────────────────
step(3, "验证 OSS 凭证（上传测试文件 → 生成签名 URL → 删除）")

try:
    import oss2
except ImportError:
    fail("oss2 未安装，请运行: pip install oss2")

oss_endpoint = f"https://{endpoint}" if not endpoint.startswith("http") else endpoint
test_key = f"{prefix.rstrip('/')}/validate_test_{int(time.time())}.txt"
test_content = b"Paraformer OSS validate test - safe to delete"

try:
    auth   = oss2.Auth(ak_id, ak_secret)
    bkt    = oss2.Bucket(auth, oss_endpoint, bucket)

    # 上传
    bkt.put_object(test_key, test_content)
    ok(f"上传测试文件成功: {bucket}/{test_key}")

    # 生成签名 URL（确认有读取权限）
    signed_url = bkt.sign_url("GET", test_key, 60, slash_safe=True)
    ok(f"签名 URL 生成成功（60s 有效）")
    print(f"    URL 前缀: {signed_url[:80]}...")

    # 验证 URL 可访问
    with urllib.request.urlopen(signed_url, timeout=10) as resp:
        content = resp.read()
    assert content == test_content, "内容校验失败"
    ok(f"签名 URL 公网可访问，内容校验通过")

    # 删除
    bkt.delete_object(test_key)
    ok(f"测试文件已删除，OSS 清理正常")

except oss2.exceptions.OssError as e:
    fail(f"OSS 操作失败: [{e.code}] {e.message}")
except Exception as e:
    fail(f"OSS 验证失败: {e}")

# ─── Step 4: 端到端验证（用本项目已有的真实音频）──────────────────────────────
step(4, "端到端验证（上传真实音频 → Paraformer 转写）")

# 找一个已有的预处理音频文件（最短的那个）
output_dir = ROOT / "output"
wav_files = sorted(output_dir.rglob("*_audio.wav"), key=lambda p: p.stat().st_size)

if not wav_files:
    print("  未找到已有音频文件，跳过端到端验证")
    print("  （先运行一次预处理以生成音频文件，再执行本验证）")
else:
    wav = wav_files[0]
    size_mb = wav.stat().st_size / 1024 / 1024
    print(f"  测试音频 : {wav.name}（{size_mb:.1f} MB）")

    try:
        # 上传到 OSS
        obj_key = f"{prefix.rstrip('/')}/{wav.stem}_{int(time.time())}.wav"
        print(f"  上传到 OSS: {bucket}/{obj_key}")
        bkt.put_object_from_file(obj_key, str(wav))
        ok("上传完成")

        signed_url = bkt.sign_url("GET", obj_key, 3600, slash_safe=True)

        # 提交 Paraformer 任务
        print(f"  提交转写任务（模型: {model}）...")
        t0 = time.time()
        task_resp = Transcription.async_call(
            model=model,
            file_urls=[signed_url],
            language_hints=["zh", "en"],
            timestamp_alignment_enabled=True,
        )
        result = Transcription.wait(task=task_resp.output.task_id)
        elapsed = time.time() - t0

        if result.status_code != HTTPStatus.OK:
            fail(f"转写请求失败: {result.status_code}")

        results = getattr(result.output, "results", None) or result.output.get("results", [])
        if not results or results[0].get("subtask_status") != "SUCCEEDED":
            fail(f"转写子任务失败: {results}")

        # 解析结果
        with urllib.request.urlopen(results[0]["transcription_url"], timeout=30) as resp:
            rj = json.loads(resp.read().decode("utf-8"))

        sentences = rj.get("transcripts", [{}])[0].get("sentences", [])
        words     = sum(len(s.get("words", [])) for s in sentences)
        content_ms = rj.get("transcripts", [{}])[0].get("content_duration_in_milliseconds", 0)

        ok(f"转写完成，耗时 {elapsed:.1f}s")
        ok(f"识别段数: {len(sentences)} 句，词级时间戳: {words} 个词")
        ok(f"语音内容时长（计费）: {content_ms/1000:.1f}s")
        if sentences:
            print(f"\n  【前3句识别结果预览】")
            for s in sentences[:3]:
                ts = f"{s['begin_time']/1000:.1f}s → {s['end_time']/1000:.1f}s"
                print(f"    [{ts}] {s['text']}")

    except Exception as e:
        fail(f"端到端验证失败: {e}")
    finally:
        try:
            bkt.delete_object(obj_key)
            ok("OSS 临时文件已清理")
        except Exception:
            pass

# ─── 总结 ──────────────────────────────────────────────────────────────────────
print(f"\n{SEP}")
print("  全部验证通过！阿里云 Paraformer 配置可用")
print(f"  运行 0_开始使用.bat → [3] 开始预处理 即可正式使用")
print(SEP)
