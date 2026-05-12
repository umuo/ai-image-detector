"""
FastAPI Web 服务 - AI 图片检测 Web 界面
"""

import os
import uuid
import shutil
import numpy as np
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .engine import DetectionEngine, DetectionReport


# 路径配置
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 全局检测引擎
engine = DetectionEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # 清理上传文件
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="AI Image Detector",
    description="多维度 AI 生成图片检测工具",
    version="0.1.0",
    lifespan=lifespan,
)

# 静态文件和模板
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页"""
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/detect")
async def detect_image(file: UploadFile = File(...)):
    """检测上传的图片"""
    # 验证文件类型
    allowed_types = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"}
    if file.content_type not in allowed_types:
        return JSONResponse(
            status_code=400,
            content={"error": f"不支持的文件类型: {file.content_type}"}
        )

    # 限制文件大小（50MB）
    max_size = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        return JSONResponse(
            status_code=400,
            content={"error": "文件大小超过 50MB 限制"}
        )

    # 保存临时文件
    ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
    temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    try:
        with open(temp_path, "wb") as f:
            f.write(content)

        # 执行检测
        report = engine.detect(str(temp_path))

        # 转换为 JSON 可序列化的格式
        return _json_safe(_report_to_dict(report))

    finally:
        # 清理临时文件
        if temp_path.exists():
            temp_path.unlink()


def _report_to_dict(report: DetectionReport) -> dict:
    """将检测报告转换为 dict"""
    result = {
        "filename": report.filename,
        "file_size": report.file_size,
        "image_width": report.image_width,
        "image_height": report.image_height,
        "analysis_time_ms": round(report.analysis_time_ms, 1),
        "is_ai_generated": report.is_ai_generated,
        "confidence": report.confidence,
        "verdict": report.verdict,
        "risk_level": report.risk_level,
        "scores": {
            "metadata": report.metadata_score,
            "spectrum": report.spectrum_score,
            "statistical": report.statistical_score,
        },
        "key_findings": report.key_findings,
        "warnings": report.warnings,
    }

    # 元数据详情
    if report.metadata:
        m = report.metadata
        result["metadata_detail"] = {
            "has_ai_signature": m.has_ai_signature,
            "ai_tool_detected": m.ai_tool_detected,
            "has_c2pa": m.has_c2pa,
            "c2pa_marker_count": m.c2pa_details.get("marker_count"),
            "c2pa_markers": m.c2pa_details.get("markers"),
            "c2pa_offsets": m.c2pa_details.get("offsets"),
            "c2pa_readable_snippets": m.c2pa_details.get("readable_snippets"),
            "c2pa_note": m.c2pa_details.get("note"),
            "has_camera_info": m.has_camera_info,
            "has_gps": m.has_gps,
            "has_datetime": m.has_datetime,
            "software": m.software,
            "ai_parameters": m.ai_parameters_found,
        }

    # 频谱详情
    if report.spectrum:
        s = report.spectrum
        result["spectrum_detail"] = {
            "high_freq_ratio": round(s.high_freq_ratio, 4),
            "spectral_slope": round(s.spectral_slope, 4),
            "periodicity_score": round(s.periodicity_score, 4),
            "grid_artifact_score": round(s.grid_artifact_score, 4),
            "synthid_detected": s.synthid_detected,
            "synthid_confidence": round(s.synthid_confidence, 4),
            "synthid_phase_match": round(s.synthid_phase_match, 4),
            "synthid_best_set": s.synthid_best_set,
            "synthid_cvr_noise": round(s.synthid_cvr_noise, 4),
            "synthid_source": s.synthid_source,
        }

    # 统计详情
    if report.statistical:
        st = report.statistical
        result["statistical_detail"] = {
            "noise_std": round(st.noise_std, 4),
            "noise_uniformity": round(st.noise_uniformity, 4),
            "color_histogram_entropy": round(st.color_histogram_entropy, 4),
            "edge_sharpness": round(st.edge_sharpness, 4),
            "texture_regularity": round(st.texture_regularity, 4),
            "local_consistency": round(st.local_variance_consistency, 4),
            "graphic_likelihood": round(st.graphic_likelihood, 4),
            "is_graphic_like": st.is_graphic_like,
        }

    return result


def _json_safe(value):
    """Convert NumPy scalars nested in detection results to JSON-native values."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value
