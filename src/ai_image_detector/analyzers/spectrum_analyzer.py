"""
频谱分析器 - 通过 FFT 频域特征检测 AI 生成图片

检测维度：
1. 频谱衰减模式（AI 图片 vs 自然照片有不同的功率谱密度分布）
2. 周期性伪影（GAN 常产生的棋盘格频谱特征）
3. 高频能量比（AI 图片通常高频细节不足）
4. SynthID 水印载波检测
"""

import numpy as np
import cv2
from scipy.fft import fft2, fftshift
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from ..vendor.reverse_synthid import ReverseSynthIDV4Detector


@dataclass
class SpectrumResult:
    high_freq_ratio: float = 0.0        # 高频能量占比
    spectral_slope: float = 0.0         # 频谱斜率（自然图像 ≈ -2）
    periodicity_score: float = 0.0      # 周期性伪影分数
    grid_artifact_score: float = 0.0    # 棋盘格伪影分数
    synthid_phase_match: float = 0.0    # SynthID 相位匹配度
    synthid_confidence: float = 0.0
    synthid_best_set: str = ""
    synthid_cvr_noise: float = 0.0
    synthid_source: str = ""
    synthid_detected: bool = False
    anomaly_bins: List[Tuple[int, int]] = field(default_factory=list)
    warnings: list = field(default_factory=list)
    score: float = 0.0


# SynthID 已知载波频率（512px 归一化）
SYNTHID_CARRIERS_DARK = [
    (-5, -3), (5, 3), (-5, 3), (5, -3),
    (-3, -4), (3, 4), (-3, 4), (3, -4),
    (-4, -3), (4, 3), (-4, 3), (4, -3),
    (-5, -1), (5, 1), (-5, 1), (5, -1),
]
SYNTHID_CARRIERS_WHITE = [
    (0, -7), (0, 7), (0, -8), (0, 8),
    (0, -9), (0, 9), (0, -10), (0, 10),
    (0, -11), (0, 11), (0, -12), (0, 12),
]


class SpectrumAnalyzer:
    """频谱分析检测器"""

    def __init__(self, analysis_size: int = 512):
        self.analysis_size = analysis_size
        self._synthid_detector: Optional[ReverseSynthIDV4Detector] = None

    def analyze(self, image_path: str) -> SpectrumResult:
        result = SpectrumResult()
        try:
            img = cv2.imread(image_path)
            if img is None:
                result.warnings.append("无法读取图片")
                return result
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        except Exception as e:
            result.warnings.append(f"图片读取错误: {e}")
            return result

        resized = cv2.resize(img_rgb, (self.analysis_size, self.analysis_size))
        gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY).astype(np.float64)

        fft_result = fftshift(fft2(gray))
        magnitude = np.abs(fft_result)
        phase = np.angle(fft_result)
        log_mag = np.log1p(magnitude)

        # 1. 高频能量比
        self._analyze_freq_ratio(log_mag, result)

        # 2. 频谱斜率
        self._analyze_spectral_slope(magnitude, result)

        # 3. 周期性伪影
        self._analyze_periodicity(magnitude, result)

        # 4. 棋盘格伪影（GAN 特征）
        self._analyze_grid_artifacts(magnitude, result)

        # 5. SynthID 水印检测
        self._check_synthid(image_path, result)

        # 综合评分
        self._compute_score(result)
        return result

    def _analyze_freq_ratio(self, log_mag, result):
        """分析高频/低频能量比"""
        h, w = log_mag.shape
        center = h // 2
        total_energy = np.sum(log_mag ** 2)
        if total_energy == 0:
            return

        # 低频区域：中心 1/8
        low_r = h // 8
        y, x = np.ogrid[:h, :w]
        low_mask = ((y - center)**2 + (x - center)**2) < low_r**2
        low_energy = np.sum(log_mag[low_mask] ** 2)

        # 高频区域：外围 1/4
        high_r = h // 4
        high_mask = ((y - center)**2 + (x - center)**2) > high_r**2
        high_energy = np.sum(log_mag[high_mask] ** 2)

        result.high_freq_ratio = float(high_energy / (total_energy + 1e-10))

    def _analyze_spectral_slope(self, magnitude, result):
        """计算径向平均功率谱的斜率"""
        h, w = magnitude.shape
        center = h // 2
        max_r = min(center, w // 2) - 1

        radial_profile = np.zeros(max_r)
        counts = np.zeros(max_r)

        y, x = np.ogrid[:h, :w]
        r = np.sqrt((y - center)**2 + (x - center)**2).astype(int)

        for ri in range(1, max_r):
            mask = (r == ri)
            if mask.any():
                radial_profile[ri] = np.mean(magnitude[mask])
                counts[ri] = mask.sum()

        # 拟合 log-log 斜率
        valid = (radial_profile > 0) & (counts > 0)
        indices = np.where(valid)[0]
        if len(indices) > 10:
            log_freq = np.log(indices)
            log_power = np.log(radial_profile[indices])
            coeffs = np.polyfit(log_freq, log_power, 1)
            result.spectral_slope = float(coeffs[0])

    def _analyze_periodicity(self, magnitude, result):
        """检测频谱中的周期性峰值（GAN 伪影）"""
        h, w = magnitude.shape
        center = h // 2
        log_mag = np.log1p(magnitude)

        # 排除 DC 和极低频
        y, x = np.ogrid[:h, :w]
        dc_mask = ((y - center)**2 + (x - center)**2) > 25

        masked_mag = log_mag * dc_mask
        mean_val = np.mean(masked_mag[dc_mask])
        std_val = np.std(masked_mag[dc_mask])

        if std_val > 0:
            # 找极端峰值（>5σ）
            threshold = mean_val + 5 * std_val
            peaks = np.sum(masked_mag > threshold)
            # 归一化
            result.periodicity_score = float(min(peaks / 50.0, 1.0))

    def _analyze_grid_artifacts(self, magnitude, result):
        """检测棋盘格伪影（典型的转置卷积 GAN 特征）"""
        h, w = magnitude.shape
        center_y, center_x = h // 2, w // 2

        # 检查频谱的四个象限边缘是否有异常峰值
        edge_positions = [
            (center_y, 0), (center_y, w-1),
            (0, center_x), (h-1, center_x),
            (0, 0), (0, w-1), (h-1, 0), (h-1, w-1)
        ]

        log_mag = np.log1p(magnitude)
        median_val = np.median(log_mag)
        edge_vals = [log_mag[y, x] for y, x in edge_positions]
        edge_mean = np.mean(edge_vals)

        if median_val > 0:
            ratio = edge_mean / median_val
            result.grid_artifact_score = float(min(max(ratio - 1.5, 0) / 3.0, 1.0))

    def _check_synthid(self, image_path, result):
        """检测 SynthID 水印，使用 reverse-SynthID 的校准 codebook。"""
        try:
            if self._synthid_detector is None:
                self._synthid_detector = ReverseSynthIDV4Detector()
            detected = self._synthid_detector.detect_path(image_path)
        except Exception as e:
            result.warnings.append(f"reverse-SynthID 检测失败: {e}")
            return

        result.synthid_phase_match = detected.phase_match
        result.synthid_confidence = detected.confidence
        result.synthid_best_set = detected.best_set
        result.synthid_cvr_noise = detected.cvr_noise
        result.synthid_source = detected.details.get("source", "reverse-SynthID V4")
        result.synthid_detected = detected.is_watermarked

    def _compute_score(self, result):
        """综合频谱评分"""
        score = 0.0

        # SynthID 强信号
        if result.synthid_detected:
            score = max(score, result.synthid_confidence)

        # 高频能量异常低（AI 图片特征）
        # 自然照片通常 high_freq_ratio > 0.3
        if result.high_freq_ratio < 0.15:
            score = max(score, 0.40)
        elif result.high_freq_ratio < 0.22:
            score = max(score, 0.25)

        # 频谱斜率异常（自然图像 ≈ -2，AI 图像通常更陡）
        if result.spectral_slope < -3.0:
            score = max(score, 0.35)

        # 周期性伪影（GAN 特征）
        if result.periodicity_score > 0.3:
            score = max(score, result.periodicity_score * 0.6)

        # 棋盘格伪影
        if result.grid_artifact_score > 0.2:
            score = max(score, result.grid_artifact_score * 0.5)

        result.score = round(score, 4)
