"""
统计分析器 - 通过像素级统计特征检测 AI 生成图片

检测维度：
1. 噪声模式分析（AI 图片的噪声分布与自然照片不同）
2. 色彩直方图分析（AI 图片通常色彩分布更均匀/异常）
3. JPEG 量化异常
4. 局部一致性检测
"""

import numpy as np
import cv2
from dataclasses import dataclass, field
from typing import List
import pywt


@dataclass
class StatisticalResult:
    noise_std: float = 0.0
    noise_uniformity: float = 0.0     # 噪声空间均匀性
    color_histogram_entropy: float = 0.0
    color_saturation_mean: float = 0.0
    jpeg_ghost_score: float = 0.0
    local_variance_consistency: float = 0.0
    edge_sharpness: float = 0.0
    texture_regularity: float = 0.0
    graphic_likelihood: float = 0.0
    is_graphic_like: bool = False
    warnings: list = field(default_factory=list)
    score: float = 0.0


class StatisticalAnalyzer:
    """基于统计特征的 AI 图片检测"""

    def analyze(self, image_path: str) -> StatisticalResult:
        result = StatisticalResult()
        try:
            img = cv2.imread(image_path)
            if img is None:
                result.warnings.append("无法读取图片")
                return result
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        except Exception as e:
            result.warnings.append(f"读取错误: {e}")
            return result

        # 统一大小处理
        h, w = img_rgb.shape[:2]
        max_dim = 1024
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img_rgb = cv2.resize(img_rgb, (int(w*scale), int(h*scale)))

        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY).astype(np.float64)

        self._analyze_noise(gray, result)
        self._analyze_color(img_rgb, result)
        self._analyze_graphic_likelihood(img_rgb, gray, result)
        self._analyze_edges(gray, result)
        self._analyze_texture(gray, result)
        self._analyze_local_consistency(gray, result)
        self._compute_score(result)
        return result

    def _analyze_noise(self, gray, result):
        """分析噪声特征"""
        # 小波去噪提取噪声
        coeffs = pywt.dwt2(gray, 'db4')
        _, (cH, cV, cD) = coeffs
        noise_est = np.median(np.abs(cD)) / 0.6745
        result.noise_std = float(noise_est)

        # 噪声空间均匀性（分块计算噪声水平）
        h, w = gray.shape
        block_size = max(h, w) // 8
        if block_size < 16:
            return

        block_noises = []
        for by in range(0, h - block_size, block_size):
            for bx in range(0, w - block_size, block_size):
                block = gray[by:by+block_size, bx:bx+block_size]
                bc = pywt.dwt2(block, 'db4')
                _, (_, _, bD) = bc
                bn = np.median(np.abs(bD)) / 0.6745
                block_noises.append(bn)

        if block_noises:
            mean_noise = np.mean(block_noises)
            std_noise = np.std(block_noises)
            # AI 图片通常噪声更均匀
            result.noise_uniformity = float(
                1.0 - min(std_noise / (mean_noise + 1e-10), 1.0)
            )

    def _analyze_color(self, img_rgb, result):
        """分析色彩分布"""
        # 色彩直方图熵
        hist_entropy = 0.0
        for ch in range(3):
            hist = cv2.calcHist([img_rgb], [ch], None, [256], [0, 256])
            hist = hist.flatten() / hist.sum()
            hist = hist[hist > 0]
            hist_entropy += -np.sum(hist * np.log2(hist))
        result.color_histogram_entropy = float(hist_entropy / 3.0)

        # 平均饱和度
        hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
        result.color_saturation_mean = float(np.mean(hsv[:, :, 1]) / 255.0)

    def _analyze_graphic_likelihood(self, img_rgb, gray, result):
        """Estimate whether the image is a screenshot/UI/graphic rather than a photo."""
        h, w = img_rgb.shape[:2]
        max_dim = 512
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            small_rgb = cv2.resize(img_rgb, (int(w * scale), int(h * scale)))
            small_gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        else:
            small_rgb = img_rgb
            small_gray = gray

        pixels = small_rgb.shape[0] * small_rgb.shape[1]
        if pixels == 0:
            return

        quantized = (small_rgb // 16).astype(np.uint8).reshape(-1, 3)
        unique_colors, counts = np.unique(quantized, axis=0, return_counts=True)
        unique_count = len(unique_colors)
        unique_ratio = unique_count / pixels
        dominant_ratio = float(counts.max() / pixels) if len(counts) else 0.0

        kernel = np.ones((7, 7), dtype=np.float64) / 49.0
        mean_map = cv2.filter2D(small_gray, -1, kernel)
        sq_mean_map = cv2.filter2D(small_gray**2, -1, kernel)
        var_map = np.maximum(sq_mean_map - mean_map**2, 0)
        flat_ratio = float(np.mean(var_map < 6.0))

        grad_x = cv2.Sobel(small_gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(small_gray, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.hypot(grad_x, grad_y)
        edge_threshold = max(float(np.percentile(magnitude, 90)), 12.0)
        edge_mask = magnitude > edge_threshold
        axis_aligned_ratio = 0.0
        if np.count_nonzero(edge_mask) > 100:
            angles = np.abs(np.degrees(np.arctan2(grad_y[edge_mask], grad_x[edge_mask])))
            angles = np.minimum(angles, 180 - angles)
            axis_aligned = (angles < 12) | (np.abs(angles - 90) < 12)
            axis_aligned_ratio = float(np.mean(axis_aligned))

        score = 0.0
        if unique_count <= 128 or unique_ratio < 0.0025:
            score += 0.35
        elif unique_count <= 256 or unique_ratio < 0.006:
            score += 0.20

        if dominant_ratio > 0.35:
            score += 0.25
        elif dominant_ratio > 0.22:
            score += 0.12

        if flat_ratio > 0.65:
            score += 0.30
        elif flat_ratio > 0.50:
            score += 0.15

        if result.color_histogram_entropy < 4.5:
            score += 0.20

        if axis_aligned_ratio > 0.65:
            score += 0.15

        result.graphic_likelihood = round(min(score, 1.0), 4)
        result.is_graphic_like = result.graphic_likelihood >= 0.65

    def _analyze_edges(self, gray, result):
        """分析边缘锐度"""
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        result.edge_sharpness = float(np.std(laplacian))

    def _analyze_texture(self, gray, result):
        """分析纹理规律性"""
        # 使用 LBP 简化版本检测纹理
        h, w = gray.shape
        if h < 3 or w < 3:
            return

        # 计算局部方差图
        kernel = np.ones((5, 5)) / 25.0
        mean_map = cv2.filter2D(gray, -1, kernel)
        sq_mean_map = cv2.filter2D(gray**2, -1, kernel)
        var_map = sq_mean_map - mean_map**2
        var_map = np.maximum(var_map, 0)

        # 纹理规律性 = 方差图的自相关性
        if var_map.std() > 0:
            var_norm = (var_map - var_map.mean()) / (var_map.std() + 1e-10)
            # 检查纹理的空间一致性
            h4, w4 = h//4, w//4
            if h4 > 0 and w4 > 0:
                quadrants = [
                    var_norm[:h//2, :w//2],
                    var_norm[:h//2, w//2:],
                    var_norm[h//2:, :w//2],
                    var_norm[h//2:, w//2:],
                ]
                q_means = [np.mean(q) for q in quadrants]
                result.texture_regularity = float(
                    1.0 - min(np.std(q_means) / (np.mean(np.abs(q_means)) + 1e-10), 1.0)
                )

    def _analyze_local_consistency(self, gray, result):
        """分析局部区域一致性"""
        h, w = gray.shape
        block_size = 64
        block_features = []

        for by in range(0, h - block_size, block_size):
            for bx in range(0, w - block_size, block_size):
                block = gray[by:by+block_size, bx:bx+block_size]
                feat = [np.mean(block), np.std(block),
                        np.mean(np.abs(np.diff(block, axis=0))),
                        np.mean(np.abs(np.diff(block, axis=1)))]
                block_features.append(feat)

        if len(block_features) > 4:
            features = np.array(block_features)
            # 特征的一致性（AI 图片通常各区域风格更统一）
            consistency = 1.0 - np.mean(np.std(features, axis=0) / (np.mean(features, axis=0) + 1e-10))
            result.local_variance_consistency = float(max(0, min(consistency, 1.0)))

    def _compute_score(self, result):
        """计算统计维度的 AI 概率评分"""
        score = 0.0

        # 噪声过于均匀（AI 特征）
        if result.noise_uniformity > 0.85:
            score = max(score, 0.35)
        elif result.noise_uniformity > 0.75:
            score = max(score, 0.20)

        # 噪声水平极低（AI 图片通常噪声很少）
        if result.noise_std < 1.0:
            score = max(score, 0.30)

        # 极高的局部一致性
        if result.local_variance_consistency > 0.8:
            score = max(score, 0.25)

        # 色彩熵异常（太高或太低）
        if result.color_histogram_entropy > 7.5:
            score = max(score, 0.20)

        if result.is_graphic_like:
            score = min(score, 0.10)

        result.score = round(score, 4)
