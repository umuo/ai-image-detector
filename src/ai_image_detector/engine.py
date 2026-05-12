"""
检测引擎 - 整合所有分析器，输出综合检测结果
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional

from .analyzers.metadata_analyzer import MetadataAnalyzer, MetadataResult
from .analyzers.spectrum_analyzer import SpectrumAnalyzer, SpectrumResult
from .analyzers.statistical_analyzer import StatisticalAnalyzer, StatisticalResult


@dataclass
class DetectionReport:
    """综合检测报告"""
    filename: str = ""
    file_size: int = 0
    image_width: int = 0
    image_height: int = 0
    analysis_time_ms: float = 0.0

    # 综合判定
    is_ai_generated: bool = False
    confidence: float = 0.0  # 0-1
    verdict: str = ""        # 人类可读的结论
    risk_level: str = ""     # low / medium / high

    # 各维度结果
    metadata: Optional[MetadataResult] = None
    spectrum: Optional[SpectrumResult] = None
    statistical: Optional[StatisticalResult] = None

    # 各维度评分
    metadata_score: float = 0.0
    spectrum_score: float = 0.0
    statistical_score: float = 0.0

    # 检测到的关键特征
    key_findings: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class DetectionEngine:
    """多维度 AI 图片检测引擎"""

    # 各维度权重
    WEIGHTS = {
        "metadata": 0.40,     # 元数据是最可靠的信号
        "spectrum": 0.35,     # 频谱分析相当可靠
        "statistical": 0.25,  # 统计特征是辅助信号
    }

    def __init__(self):
        self.metadata_analyzer = MetadataAnalyzer()
        self.spectrum_analyzer = SpectrumAnalyzer()
        self.statistical_analyzer = StatisticalAnalyzer()

    def detect(self, image_path: str) -> DetectionReport:
        """执行完整的多维度检测"""
        report = DetectionReport()
        start_time = time.time()

        # 基础文件信息
        report.filename = os.path.basename(image_path)
        try:
            report.file_size = os.path.getsize(image_path)
        except OSError:
            pass

        try:
            from PIL import Image
            with Image.open(image_path) as img:
                report.image_width, report.image_height = img.size
        except Exception:
            pass

        # 1. 元数据分析
        try:
            report.metadata = self.metadata_analyzer.analyze(image_path)
            report.metadata_score = report.metadata.score
        except Exception as e:
            report.warnings.append(f"元数据分析失败: {e}")
            report.metadata_score = 0.0

        # 2. 频谱分析
        try:
            report.spectrum = self.spectrum_analyzer.analyze(image_path)
            report.spectrum_score = report.spectrum.score
        except Exception as e:
            report.warnings.append(f"频谱分析失败: {e}")
            report.spectrum_score = 0.0

        # 3. 统计分析
        try:
            report.statistical = self.statistical_analyzer.analyze(image_path)
            report.statistical_score = report.statistical.score
        except Exception as e:
            report.warnings.append(f"统计分析失败: {e}")
            report.statistical_score = 0.0

        # 综合评分
        self._compute_verdict(report)

        report.analysis_time_ms = (time.time() - start_time) * 1000
        return report

    def _compute_verdict(self, report: DetectionReport):
        """计算综合判定"""
        graphic_like = self._is_graphic_like(report)
        strong_metadata = self._has_strong_metadata_evidence(report)

        metadata_score = report.metadata_score
        spectrum_score = report.spectrum_score
        statistical_score = report.statistical_score

        if graphic_like and not strong_metadata:
            spectrum_score = min(spectrum_score, 0.20)
            statistical_score = min(statistical_score, 0.10)

        report.metadata_score = round(metadata_score, 4)
        report.spectrum_score = round(spectrum_score, 4)
        report.statistical_score = round(statistical_score, 4)

        # 加权评分
        weighted_score = (
            metadata_score * self.WEIGHTS["metadata"] +
            spectrum_score * self.WEIGHTS["spectrum"] +
            statistical_score * self.WEIGHTS["statistical"]
        )

        # 如果元数据有确凿证据，直接采信
        if report.metadata and report.metadata.has_ai_signature:
            if report.metadata.ai_signature_confidence > 0.85:
                weighted_score = max(weighted_score, report.metadata.ai_signature_confidence)

        # SynthID 检测到也是强信号
        if report.spectrum and report.spectrum.synthid_detected and not graphic_like:
            weighted_score = max(weighted_score, report.spectrum.synthid_confidence)

        report.confidence = round(min(weighted_score, 1.0), 4)

        # 判定阈值
        if report.confidence >= 0.70:
            report.is_ai_generated = True
            report.risk_level = "high"
            report.verdict = "高度疑似 AI 生成"
        elif report.confidence >= 0.45:
            report.is_ai_generated = True
            report.risk_level = "medium"
            report.verdict = "可能是 AI 生成"
        elif report.confidence >= 0.25:
            report.is_ai_generated = False
            report.risk_level = "low"
            report.verdict = "存在少量 AI 特征，但证据不足"
        else:
            report.is_ai_generated = False
            report.risk_level = "low"
            report.verdict = "未检测到明显 AI 生成特征"

        # 收集关键发现
        self._collect_findings(report)

    def _is_graphic_like(self, report: DetectionReport) -> bool:
        return bool(report.statistical and report.statistical.is_graphic_like)

    def _has_strong_metadata_evidence(self, report: DetectionReport) -> bool:
        if not report.metadata:
            return False
        return (
            report.metadata.has_ai_signature
            and report.metadata.ai_signature_confidence >= 0.70
        ) or bool(report.metadata.ai_parameters_found)

    def _collect_findings(self, report: DetectionReport):
        """收集关键发现用于展示"""
        findings = []
        graphic_like = self._is_graphic_like(report)
        strong_metadata = self._has_strong_metadata_evidence(report)

        if graphic_like and report.statistical:
            findings.append({
                "type": "content",
                "level": "info",
                "icon": "🔵",
                "title": "检测到截图/界面类图像",
                "detail": (
                    f"图形化特征 {report.statistical.graphic_likelihood:.0%}，"
                    "已降低自然照片型特征权重"
                ),
            })

        if report.metadata:
            m = report.metadata
            if m.has_ai_signature:
                findings.append({
                    "type": "metadata",
                    "level": "critical",
                    "icon": "🔴",
                    "title": f"检测到 AI 工具签名: {m.ai_tool_detected}",
                    "detail": f"置信度 {m.ai_signature_confidence:.0%}",
                })
            if m.has_c2pa:
                findings.append({
                    "type": "metadata",
                    "level": "warning",
                    "icon": "🟡",
                    "title": "检测到 C2PA Content Credentials",
                    "detail": "图片包含内容来源认证信息",
                })
            if m.ai_parameters_found:
                findings.append({
                    "type": "metadata",
                    "level": "critical",
                    "icon": "🔴",
                    "title": "发现 AI 生成参数",
                    "detail": f"参数: {', '.join(m.ai_parameters_found[:5])}",
                })
            if m.missing_natural_metadata and not graphic_like:
                findings.append({
                    "type": "metadata",
                    "level": "info",
                    "icon": "🔵",
                    "title": "缺少自然拍摄元数据",
                    "detail": "无相机型号、GPS、拍摄时间等信息",
                })
            if m.has_camera_info:
                findings.append({
                    "type": "metadata",
                    "level": "good",
                    "icon": "🟢",
                    "title": "包含相机拍摄信息",
                    "detail": "存在相机型号、拍摄参数等自然拍摄元数据",
                })

        if report.spectrum:
            s = report.spectrum
            if s.synthid_detected and not (graphic_like and not strong_metadata):
                findings.append({
                    "type": "spectrum",
                    "level": "critical",
                    "icon": "🔴",
                    "title": "检测到 SynthID 水印",
                    "detail": (
                        f"reverse-SynthID 置信度 {s.synthid_confidence:.0%}，"
                        f"相位匹配度 {s.synthid_phase_match:.2f}"
                    ),
                })
            elif s.synthid_detected:
                findings.append({
                    "type": "spectrum",
                    "level": "info",
                    "icon": "🔵",
                    "title": "频谱载波命中已降权",
                    "detail": (
                        f"相位匹配度 {s.synthid_phase_match:.2f}，"
                        "截图/界面类图像容易误触发该信号"
                    ),
                })
            if s.periodicity_score > 0.3:
                findings.append({
                    "type": "spectrum",
                    "level": "warning",
                    "icon": "🟡",
                    "title": "频谱中发现周期性伪影",
                    "detail": f"伪影分数 {s.periodicity_score:.2f}，可能来自 GAN 模型",
                })
            if s.high_freq_ratio < 0.15:
                findings.append({
                    "type": "spectrum",
                    "level": "warning",
                    "icon": "🟡",
                    "title": "高频细节能量偏低",
                    "detail": f"高频比 {s.high_freq_ratio:.3f}，AI 图片通常缺乏高频细节",
                })

        if report.statistical and not graphic_like:
            st = report.statistical
            if st.noise_uniformity > 0.85:
                findings.append({
                    "type": "statistical",
                    "level": "warning",
                    "icon": "🟡",
                    "title": "噪声分布异常均匀",
                    "detail": f"均匀度 {st.noise_uniformity:.2f}，自然照片噪声通常不均匀",
                })
            if st.noise_std < 1.0:
                findings.append({
                    "type": "statistical",
                    "level": "info",
                    "icon": "🔵",
                    "title": "噪声水平极低",
                    "detail": f"σ={st.noise_std:.2f}，AI 图片通常噪声很少",
                })

        if not findings:
            findings.append({
                "type": "general",
                "level": "good",
                "icon": "🟢",
                "title": "未发现明显 AI 生成特征",
                "detail": "各项指标均在正常范围内",
            })

        report.key_findings = findings
