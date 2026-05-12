"""
元数据分析器 - 通过 EXIF / PNG text 元数据检测 AI 生成图片
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image
from PIL.ExifTags import TAGS


AI_SOFTWARE_SIGNATURES = {
    "midjourney": {"name": "Midjourney", "confidence": 0.95},
    "dall-e": {"name": "DALL-E", "confidence": 0.95},
    "dall·e": {"name": "DALL-E", "confidence": 0.95},
    "openai": {"name": "OpenAI (DALL-E)", "confidence": 0.90},
    "stable diffusion": {"name": "Stable Diffusion", "confidence": 0.95},
    "stability ai": {"name": "Stability AI", "confidence": 0.90},
    "automatic1111": {"name": "Stable Diffusion (A1111)", "confidence": 0.95},
    "comfyui": {"name": "ComfyUI", "confidence": 0.95},
    "novelai": {"name": "NovelAI", "confidence": 0.95},
    "adobe firefly": {"name": "Adobe Firefly", "confidence": 0.90},
    "gemini": {"name": "Google Gemini", "confidence": 0.90},
    "imagen": {"name": "Google Imagen", "confidence": 0.90},
    "flux": {"name": "Flux", "confidence": 0.90},
    "leonardo ai": {"name": "Leonardo AI", "confidence": 0.90},
    "ideogram": {"name": "Ideogram", "confidence": 0.90},
    "negative prompt": {"name": "Stable Diffusion (推测)", "confidence": 0.75},
    "cfg scale": {"name": "Stable Diffusion (推测)", "confidence": 0.70},
}

C2PA_MARKERS = [b"c2pa", b"C2PA", b"contentcredentials"]


@dataclass
class MetadataResult:
    has_ai_signature: bool = False
    ai_tool_detected: Optional[str] = None
    ai_signature_confidence: float = 0.0
    has_c2pa: bool = False
    c2pa_details: dict = field(default_factory=dict)
    has_camera_info: bool = False
    has_gps: bool = False
    has_datetime: bool = False
    missing_natural_metadata: bool = False
    software: Optional[str] = None
    ai_parameters_found: list = field(default_factory=list)
    all_metadata: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    score: float = 0.0


class MetadataAnalyzer:
    def analyze(self, image_path: str) -> MetadataResult:
        result = MetadataResult()
        try:
            img = Image.open(image_path)
        except Exception as e:
            result.warnings.append(f"无法打开图片: {e}")
            return result

        self._check_exif(img, result)
        self._check_png_text(img, result)
        self._check_c2pa(image_path, result)
        self._check_completeness(result)
        self._compute_score(result)
        return result

    def _check_exif(self, img, result):
        exif_data = {}
        try:
            raw = img._getexif()
            if raw:
                for tag_id, val in raw.items():
                    name = TAGS.get(tag_id, tag_id)
                    if isinstance(val, bytes):
                        try: val = val.decode("utf-8", errors="replace")
                        except: val = str(val)
                    exif_data[str(name)] = str(val)
        except Exception:
            pass
        result.all_metadata.update(exif_data)

        for f in ["Software", "ProcessingSoftware", "CreatorTool"]:
            if f in exif_data:
                result.software = exif_data[f]
                self._match_sig(exif_data[f], result)

        for f in ["ImageDescription", "UserComment"]:
            if f in exif_data:
                self._match_sig(exif_data[f], result)

        result.has_camera_info = any(f in exif_data for f in ["Make", "Model"])
        result.has_gps = "GPSInfo" in exif_data
        result.has_datetime = any(f in exif_data for f in ["DateTimeOriginal", "DateTime"])

    def _check_png_text(self, img, result):
        info = getattr(img, "info", {}) or {}
        for key, val in info.items():
            if isinstance(val, bytes):
                try: val = val.decode("utf-8", errors="replace")
                except: continue
            s = str(val)
            result.all_metadata[f"PNG:{key}"] = s[:500]
            self._match_sig(s, result)
            sd_kw = ["Steps:", "Sampler:", "CFG scale:", "Seed:", "Negative prompt:"]
            found = [k for k in sd_kw if k.lower() in s.lower()]
            if found:
                result.ai_parameters_found.extend(found)
                if not result.has_ai_signature:
                    result.has_ai_signature = True
                    result.ai_tool_detected = "Stable Diffusion (参数检测)"
                    result.ai_signature_confidence = max(
                        result.ai_signature_confidence, min(0.6 + len(found)*0.08, 0.95))

    def _check_c2pa(self, path, result):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return

        matches = []
        matched_offsets = set()
        lower_data = data.lower()
        for marker in C2PA_MARKERS:
            start = 0
            marker_lower = marker.lower()
            while True:
                idx = lower_data.find(marker_lower, start)
                if idx == -1:
                    break
                if idx not in matched_offsets:
                    matched_offsets.add(idx)
                    matches.append({
                        "marker": marker.decode("ascii", errors="ignore").lower(),
                        "offset": idx,
                    })
                start = idx + len(marker)

        if not matches:
            return

        result.has_c2pa = True
        result.warnings.append("检测到 C2PA 标记")
        result.c2pa_details = {
            "marker_count": len(matches),
            "markers": sorted({m["marker"] for m in matches}),
            "offsets": [m["offset"] for m in matches[:10]],
            "readable_snippets": self._extract_c2pa_snippets(data, matches),
            "note": "完整解析和签名验证需要 c2patool 或 C2PA SDK",
        }

    def _extract_c2pa_snippets(self, data: bytes, matches: list) -> list:
        snippets = []
        seen = set()
        for match in matches[:5]:
            offset = match["offset"]
            start = max(0, offset - 512)
            end = min(len(data), offset + 2048)
            chunk = data[start:end]
            text_parts = []
            for found in re.findall(rb"[\x20-\x7e]{4,}", chunk):
                text = found.decode("utf-8", errors="replace").strip()
                if text and text not in seen:
                    seen.add(text)
                    text_parts.append(text)
                if len(text_parts) >= 12:
                    break
            if text_parts:
                snippets.append({
                    "offset": offset,
                    "text": " | ".join(text_parts)[:1200],
                })
        return snippets

    def _match_sig(self, text, result):
        t = text.lower()
        for sig, info in AI_SOFTWARE_SIGNATURES.items():
            if sig in t and info["confidence"] > result.ai_signature_confidence:
                result.has_ai_signature = True
                result.ai_tool_detected = info["name"]
                result.ai_signature_confidence = info["confidence"]

    def _check_completeness(self, result):
        if not result.has_camera_info and not result.has_gps and not result.has_datetime:
            if not result.has_ai_signature:
                result.missing_natural_metadata = True
                result.warnings.append("缺少相机/GPS/日期元数据")

    def _compute_score(self, result):
        score = 0.0
        if result.has_ai_signature:
            score = max(score, result.ai_signature_confidence)
        if result.has_c2pa:
            score = max(score, 0.60)
        if result.ai_parameters_found:
            score = max(score, min(0.5 + len(result.ai_parameters_found)*0.1, 0.95))
        if result.missing_natural_metadata and score < 0.3:
            score = max(score, 0.15)
        if result.has_camera_info and result.has_gps:
            score *= 0.3
        result.score = round(score, 4)
