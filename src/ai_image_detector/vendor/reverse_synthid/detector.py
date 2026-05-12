"""SynthID detector adapted from reverse-SynthID.

This module uses the calibrated carrier phase/codebook approach from:
  reverse-SynthID by Alosh Denny — github.com/aloshdenny/reverse-SynthID

The vendored codebook and methodology are covered by the reverse-SynthID
Research License v1.0. It permits non-commercial use only and requires
attribution when distributed or publicly described.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import cv2
import numpy as np
import pywt
from scipy import ndimage
from scipy.fft import fft2, fftshift, ifft2


@dataclass
class ReverseSynthIDResult:
    is_watermarked: bool = False
    confidence: float = 0.0
    phase_match: float = 0.0
    correlation: float = 0.0
    structure_ratio: float = 0.0
    carrier_strength: float = 0.0
    cvr_noise: float = 0.0
    best_set: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class ReverseSynthIDDetector:
    """Calibrated SynthID detector from reverse-SynthID's robust extractor."""

    carriers_dark = [
        (-5, -3), (5, 3), (-5, 3), (5, -3),
        (-3, -4), (3, 4), (-3, 4), (3, -4),
        (-4, -3), (4, 3), (-4, 3), (4, -3),
        (-5, -1), (5, 1), (-5, 1), (5, -1),
        (-5, -2), (5, 2), (-5, 2), (5, -2),
        (-2, -5), (2, 5), (-2, 5), (2, -5),
        (-1, -5), (1, 5), (-1, 5), (1, -5),
        (-4, -4), (4, 4), (-4, 4), (4, -4),
        (-1, -6), (1, 6), (-3, -5), (3, 5),
    ]
    carriers_white = [
        (0, -7), (0, 7), (0, -8), (0, 8),
        (0, -9), (0, 9), (0, -10), (0, 10),
        (0, -11), (0, 11), (0, -12), (0, 12),
        (0, -20), (0, 20), (0, -21), (0, 21),
        (0, -22), (0, 22), (0, -23), (0, 23),
    ]

    def __init__(self, codebook_path: str | None = None):
        self.wavelets = ["db4", "sym8", "coif3"]
        self.codebook = self._load_codebook(codebook_path)

    def detect_path(self, image_path: str) -> ReverseSynthIDResult:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")
        image_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return self.detect_array(image_rgb)

    def detect_array(self, image: np.ndarray) -> ReverseSynthIDResult:
        target_size = int(self.codebook["image_size"])
        img_resized = cv2.resize(image, (target_size, target_size))
        center = target_size // 2

        gray = (
            np.mean(img_resized, axis=2)
            if len(img_resized.shape) == 3
            else img_resized
        )
        f_img = fftshift(fft2(gray.astype(np.float32)))
        img_phase = np.angle(f_img)
        img_mag = np.abs(f_img)

        carrier_refs = self.codebook.get("carrier_refs", {})
        set_results: dict[str, dict[str, Any]] = {}

        for set_name, carriers, ref_key in [
            ("dark", self.carriers_dark, "dark_ref_phases"),
            ("white", self.carriers_white, "white_ref_phases"),
        ]:
            ref_phases = carrier_refs.get(ref_key)
            if ref_phases is None or not carriers:
                continue

            phase_matches = []
            for i, (fy, fx) in enumerate(carriers):
                y, x = fy + center, fx + center
                if 0 <= y < target_size and 0 <= x < target_size and i < len(ref_phases):
                    diff = np.abs(np.angle(np.exp(1j * (img_phase[y, x] - ref_phases[i]))))
                    phase_matches.append(1 - diff / np.pi)

            if phase_matches:
                set_results[set_name] = {
                    "phase_match": float(np.mean(phase_matches)),
                    "phase_std": float(np.std(phase_matches)),
                    "n_carriers": len(phase_matches),
                }

        if set_results:
            best_set = max(set_results, key=lambda k: set_results[k]["phase_match"])
            best_phase_match = float(set_results[best_set]["phase_match"])
        else:
            best_set = ""
            best_phase_match = 0.0

        noise = self._extract_noise_fused(img_resized)
        noise_gray = np.mean(noise, axis=2) if len(noise.shape) == 3 else noise
        f_noise = fftshift(fft2(noise_gray))
        noise_mag = np.abs(f_noise)

        all_carriers = self.carriers_dark + self.carriers_white
        carrier_mags = [
            noise_mag[fy + center, fx + center]
            for fy, fx in all_carriers
            if 0 <= fy + center < target_size and 0 <= fx + center < target_size
        ]

        rng = np.random.RandomState(42)
        random_mags = []
        for _ in range(len(all_carriers) * 4):
            ry = rng.randint(10, target_size - 10)
            rx = rng.randint(10, target_size - 10)
            if abs(ry - center) < 5 and abs(rx - center) < 5:
                continue
            random_mags.append(noise_mag[ry, rx])

        cvr_noise = float(np.mean(carrier_mags)) / (float(np.mean(random_mags)) + 1e-10)
        structure_ratio = float(np.std(noise_gray) / (np.mean(np.abs(noise_gray)) + 1e-10))

        ref_noise = self.codebook["reference_noise"]
        correlation = float(np.corrcoef(noise.ravel(), ref_noise.ravel())[0, 1])

        carrier_mags_img = [
            img_mag[fy + center, fx + center]
            for fy, fx in all_carriers
            if 0 <= fy + center < target_size and 0 <= fx + center < target_size
        ]
        carrier_strength = float(np.mean(carrier_mags_img)) if carrier_mags_img else 0.0

        phase_score = float(1.0 / (1.0 + np.exp(-20.0 * (best_phase_match - 0.78))))
        cvr_score = float(1.0 / (1.0 + np.exp(-2.0 * (cvr_noise - 2.0))))
        confidence = float(min(1.0, 0.80 * phase_score + 0.20 * cvr_score))

        return ReverseSynthIDResult(
            is_watermarked=bool(confidence > 0.50),
            confidence=confidence,
            phase_match=best_phase_match,
            correlation=correlation,
            structure_ratio=structure_ratio,
            carrier_strength=carrier_strength,
            cvr_noise=cvr_noise,
            best_set=best_set,
            details={
                "source": "reverse-SynthID robust extractor",
                "phase_score": phase_score,
                "cvr_score": cvr_score,
                "set_results": set_results,
            },
        )

    def _extract_noise_fused(self, image: np.ndarray) -> np.ndarray:
        noises = []
        weights = []

        for wavelet in self.wavelets:
            noises.append(self._extract_noise_single(image, "wavelet", wavelet=wavelet))
            weights.append(1.0)

        noises.append(self._extract_noise_single(image, "bilateral"))
        weights.append(0.8)

        noises.append(self._extract_noise_single(image, "nlm"))
        weights.append(0.7)

        noises.append(self._extract_noise_single(image, "wiener"))
        weights.append(0.6)

        weights_arr = np.array(weights) / sum(weights)
        return np.tensordot(weights_arr, np.array(noises), axes=([0], [0]))

    def _extract_noise_single(self, image: np.ndarray, method: str, **kwargs) -> np.ndarray:
        img_f = image.astype(np.float32)
        if img_f.max() > 1:
            img_f = img_f / 255.0

        if method == "wavelet":
            wavelet = kwargs.get("wavelet", "db4")
            if len(img_f.shape) == 2:
                denoised = self._wavelet_denoise(img_f, wavelet)
            else:
                denoised = np.zeros_like(img_f)
                for c in range(img_f.shape[2]):
                    denoised[:, :, c] = self._wavelet_denoise(img_f[:, :, c], wavelet)
        elif method == "bilateral":
            denoised = self._bilateral_denoise(img_f)
        elif method == "nlm":
            denoised = self._nlm_denoise(img_f)
        elif method == "wiener":
            if len(img_f.shape) == 2:
                denoised = self._wiener_filter(img_f)
            else:
                denoised = np.zeros_like(img_f)
                for c in range(img_f.shape[2]):
                    denoised[:, :, c] = self._wiener_filter(img_f[:, :, c])
        else:
            raise ValueError(f"Unknown denoising method: {method}")

        return img_f - denoised

    def _wavelet_denoise(self, channel: np.ndarray, wavelet: str, level: int = 3) -> np.ndarray:
        coeffs = pywt.wavedec2(channel, wavelet, level=level)
        detail = coeffs[-1][0]
        sigma = np.median(np.abs(detail)) / 0.6745
        threshold = sigma * np.sqrt(2 * np.log(channel.size))

        new_coeffs = [coeffs[0]]
        for details in coeffs[1:]:
            new_coeffs.append(tuple(pywt.threshold(d, threshold, mode="soft") for d in details))

        denoised = pywt.waverec2(new_coeffs, wavelet)
        return denoised[: channel.shape[0], : channel.shape[1]]

    def _bilateral_denoise(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return cv2.bilateralFilter(image.astype(np.float32), 9, 75, 75)
        result = np.zeros_like(image)
        for c in range(image.shape[2]):
            result[:, :, c] = cv2.bilateralFilter(image[:, :, c].astype(np.float32), 9, 75, 75)
        return result

    def _nlm_denoise(self, image: np.ndarray) -> np.ndarray:
        img_uint8 = (image * 255).clip(0, 255).astype(np.uint8)
        if len(image.shape) == 2:
            denoised = cv2.fastNlMeansDenoising(img_uint8, None, 10, 7, 21)
        else:
            denoised = cv2.fastNlMeansDenoisingColored(img_uint8, None, 10, 10, 7, 21)
        return denoised.astype(np.float32) / 255.0

    def _wiener_filter(self, image: np.ndarray) -> np.ndarray:
        noise_variance = np.var(image - ndimage.gaussian_filter(image, sigma=2))
        f = fft2(image)
        power = np.abs(f) ** 2
        signal_power = np.maximum(power - noise_variance, 0)
        wiener_ratio = signal_power / (signal_power + noise_variance + 1e-10)
        return np.real(ifft2(f * wiener_ratio))

    def _load_codebook(self, codebook_path: str | None) -> dict[str, Any]:
        if codebook_path:
            with open(codebook_path, "rb") as f:
                return pickle.load(f)

        with resources.files("ai_image_detector.resources").joinpath(
            "robust_codebook.pkl"
        ).open("rb") as f:
            return pickle.load(f)


class ReverseSynthIDV4Detector:
    """Native-resolution V4 consensus detector from reverse-SynthID."""

    def __init__(self, codebook_path: str | None = None, model: str | None = None):
        self.codebook_path = codebook_path
        self.model = model
        self._npz = None
        self._keys: list[tuple[str, int, int]] | None = None
        self._profile_cache: dict[tuple[str, int, int], tuple[np.ndarray, np.ndarray]] = {}

    def detect_path(self, image_path: str) -> ReverseSynthIDResult:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")
        image_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return self.detect_array(image_rgb)

    def detect_array(
        self,
        image: np.ndarray,
        model: str | None = None,
        top_k: int = 128,
        consensus_floor: float = 0.75,
    ) -> ReverseSynthIDResult:
        image_u8 = self._to_uint8(image)
        h, w = image_u8.shape[:2]
        key, exact = self._select_key(h, w, model or self.model)
        consensus, phase = self._load_profile(key)

        if exact:
            work = image_u8.astype(np.float64)
        else:
            _, ph, pw = key
            work = cv2.resize(image_u8, (pw, ph), interpolation=cv2.INTER_AREA).astype(np.float64)

        per_channel_scores = []
        per_channel_n = []
        for ch in range(3):
            fft_ch = np.fft.fft2(work[:, :, ch])
            img_phase = np.angle(fft_ch)

            cons_ch = consensus[:, :, ch].copy()
            cons_ch[0, 0] = 0.0
            if not np.any(cons_ch >= consensus_floor):
                continue

            candidates = np.argsort(cons_ch.ravel())[-top_k:]
            rows, cols = np.unravel_index(candidates, cons_ch.shape)

            matches = []
            for y, x in zip(rows, cols):
                if cons_ch[y, x] < consensus_floor:
                    continue
                diff = np.abs(np.angle(np.exp(1j * (img_phase[y, x] - phase[y, x, ch]))))
                matches.append(1.0 - diff / np.pi)

            if matches:
                per_channel_scores.append(float(np.mean(matches)))
                per_channel_n.append(len(matches))

        if not per_channel_scores:
            return ReverseSynthIDResult(
                details={
                    "source": "reverse-SynthID V4 consensus detector",
                    "profile_key": f"{key[0]}/{key[1]}x{key[2]}",
                    "exact_match": exact,
                    "reason": "no consensus bins above floor",
                }
            )

        weights = [0.25, 0.55, 0.20][: len(per_channel_scores)]
        phase_match = float(
            sum(s * w for s, w in zip(per_channel_scores, weights)) / sum(weights)
        )
        confidence = float(1.0 / (1.0 + np.exp(-18.0 * (phase_match - 0.52))))

        return ReverseSynthIDResult(
            is_watermarked=bool(confidence > 0.50),
            confidence=confidence,
            phase_match=phase_match,
            best_set=f"{key[0]}/{key[1]}x{key[2]}",
            details={
                "source": "reverse-SynthID V4 consensus detector",
                "profile_key": f"{key[0]}/{key[1]}x{key[2]}",
                "exact_match": exact,
                "per_channel_scores": per_channel_scores,
                "per_channel_n": per_channel_n,
                "top_k": top_k,
                "consensus_floor": consensus_floor,
            },
        )

    def _select_key(self, h: int, w: int, model: str | None) -> tuple[tuple[str, int, int], bool]:
        keys = self._get_keys()
        if model is not None and (model, h, w) in keys:
            return (model, h, w), True
        if model is None:
            for key in keys:
                if key[1:] == (h, w):
                    return key, True

        target_ar = h / (w + 1e-9)
        best_key = None
        best_score = float("inf")
        for key in keys:
            key_model, kh, kw = key
            if model is not None and key_model != model:
                continue
            ar_diff = abs(kh / (kw + 1e-9) - target_ar) / (target_ar + 1e-9)
            px_diff = abs(kh * kw - h * w) / (h * w + 1e-9)
            score = ar_diff * 2.0 + px_diff
            if score < best_score:
                best_score = score
                best_key = key

        if best_key is None:
            return self._select_key(h, w, model=None)
        return best_key, False

    def _load_profile(self, key: tuple[str, int, int]) -> tuple[np.ndarray, np.ndarray]:
        cached = self._profile_cache.get(key)
        if cached is not None:
            return cached

        d = self._open_npz()
        model, h, w = key
        prefix = f"{model}|{h}x{w}/"

        consensus_r = d[prefix + "cons"].astype(np.float64) / 255.0
        if int(d["format_version"]) >= 5:
            phase_scale = float(d[prefix + "phase__scale"])
            phase_r = d[prefix + "phase"].astype(np.float64) * phase_scale
        else:
            phase_r = d[prefix + "phase"].astype(np.float64)

        consensus = self._rfft_to_full_sym(consensus_r, h, w).astype(np.float32)
        phase = self._rfft_to_full_anti(phase_r, h, w).astype(np.float32)
        self._profile_cache[key] = (consensus, phase)
        return consensus, phase

    def _get_keys(self) -> list[tuple[str, int, int]]:
        if self._keys is not None:
            return self._keys

        d = self._open_npz()
        keys = []
        for entry in d["keys"]:
            model, h_str, w_str = str(entry).split("|")
            keys.append((model, int(h_str), int(w_str)))
        self._keys = keys
        return keys

    def _open_npz(self):
        if self._npz is not None:
            return self._npz

        if self.codebook_path:
            self._npz = np.load(self.codebook_path, allow_pickle=True)
        else:
            with resources.as_file(
                resources.files("ai_image_detector.resources").joinpath(
                    "spectral_codebook_v4.npz"
                )
            ) as path:
                self._npz = np.load(path, allow_pickle=True)

        return self._npz

    @staticmethod
    def _to_uint8(image: np.ndarray) -> np.ndarray:
        if image.dtype == np.uint8:
            return image
        arr = np.asarray(image)
        if np.max(arr) <= 1.5:
            arr = arr * 255.0
        return np.clip(arr, 0, 255).astype(np.uint8)

    @staticmethod
    def _rfft_to_full_sym(rfft_half: np.ndarray, h: int, w: int) -> np.ndarray:
        rw = w // 2 + 1
        full = np.zeros((h, w) + rfft_half.shape[2:], dtype=rfft_half.dtype)
        full[:, :rw] = rfft_half
        if w > 2:
            sky = (h - np.arange(h)) % h
            skx = w - np.arange(rw, w)
            full[:, rw:] = full[sky[:, None], skx[None, :]]
        return full

    @staticmethod
    def _rfft_to_full_anti(rfft_half: np.ndarray, h: int, w: int) -> np.ndarray:
        rw = w // 2 + 1
        full = np.zeros((h, w) + rfft_half.shape[2:], dtype=rfft_half.dtype)
        full[:, :rw] = rfft_half
        if w > 2:
            sky = (h - np.arange(h)) % h
            skx = w - np.arange(rw, w)
            full[:, rw:] = -full[sky[:, None], skx[None, :]]
        return full
