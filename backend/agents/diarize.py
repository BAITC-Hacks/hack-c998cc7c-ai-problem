"""Лёгкая диаризация (без GPU, без тяжёлых эмбеддинг-моделей).

Идея:
  1. Сегменты Whisper склеиваются в «реплики» (перерыв между репликами > TURN_GAP).
  2. Для каждой реплики считаются дешёвые акустические признаки из аудио:
     энергия, спектральный центроид, оценки основной частоты (F0, авто-корреляция).
  3. Реплики кластеризуются иерархической кластеризацией → «Говорящий 1..N».

Это эвристическая диаризация: надёжна на последовательных/непересекающихся
репликах, ошибается при наложении голосов (отмечено в README как ограничение).
"""
from __future__ import annotations

import numpy as np
from numpy.fft import rfft
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform

import config


# ---------------------------------------------------------------- признаки
def _rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0


def _spectral_centroid(y: np.ndarray, sr: int) -> float:
    if y.size == 0:
        return 0.0
    spec = np.abs(rfft(y * np.hanning(y.size)))
    if spec.sum() < 1e-9:
        return 0.0
    freqs = np.fft.rfftfreq(y.size, d=1.0 / sr)
    return float(np.sum(freqs * spec) / np.sum(spec))


def _f0_estimate(y: np.ndarray, sr: int, fmin: float = 70.0, fmax: float = 400.0) -> float:
    """Оценка основной частоты через автокорреляцию (в ограниченном диапазоне)."""
    if y.size < sr // 10:
        return 0.0
    y = y - y.mean()
    if np.std(y) < 1e-6:
        return 0.0
    y = y / (np.std(y) + 1e-9)
    lag_min = max(1, int(sr / fmax))
    lag_max = min(y.size - 1, int(sr / fmin))
    if lag_max <= lag_min:
        return 0.0
    corr = np.correlate(y[: y.size // 2], y, mode="valid")
    if corr.size < lag_max:
        lag_max = max(lag_min + 1, corr.size - 1)
    window = corr[lag_min:lag_max]
    if window.size < 2:
        return 0.0
    lag = lag_min + int(np.argmax(window))
    return float(sr / lag)


def features_for_turns(waveform: np.ndarray, turns: list[dict], sr: int = 16000) -> np.ndarray:
    """n_turns x 4: [rms, centroid/100, f0mean/100, f0std/100]."""
    feats = []
    for t in turns:
        a = max(0, int(t["start"] * sr))
        b = min(int(t["end"] * sr), waveform.size)
        y = waveform[a:b]
        f0 = _f0_estimate(y, sr)
        feats.append([
            _rms(y),
            _spectral_centroid(y, sr) / 100.0,
            f0 / 100.0,
            0.0,  # std одной реплики неинформативен — 0, см. ниже
        ])
    return np.asarray(feats, dtype=float)


# ---------------------------------------------------------------- кластеризация
def _silhouette(X: np.ndarray, labels: np.ndarray) -> float:
    """Средний силуэт (собственная реализация, без sklearn)."""
    n = len(labels)
    if n < 3:
        return 0.0
    D = squareform(pdist(X))
    total = 0.0
    for i in range(n):
        same = np.where(labels == labels[i])[0]
        same = same[same != i]
        if same.size == 0:
            continue
        a = np.mean(D[i, same])
        others = [c for c in np.unique(labels) if c != labels[i]]
        if not others:
            continue
        b = min(np.mean(D[i, np.where(labels == c)[0]]) for c in others)
        total += (b - a) / max(a, b, 1e-9)
    return float(total / n)


def cluster_speakers(feats: np.ndarray) -> list[int]:
    """Возвращает метки кластеров (0..k-1) для каждой реплики, либо все 0 при <2 репликах."""
    n = feats.shape[0]
    if n <= 1:
        return [0] * n
    # масштабирование признаков
    std = feats.std(axis=0)
    std[std == 0] = 1.0
    X = (feats - feats.mean(axis=0)) / std
    d = pdist(X)
    if d.size == 0 or np.isnan(d).any():
        return [0] * n
    Z = linkage(d, method="average")
    best_k, best_score = 1, -1.0
    for k in range(2, min(5, n)):
        lab = fcluster(Z, t=k, criterion="maxclust") - 1
        score = _silhouette(X, lab)
        if score > best_score:
            best_k, best_score = k, score
    if best_k == 1:
        return [0] * n
    # переупорядочим кластеры по времени первого появления → «Говорящий 1..»
    lab = (fcluster(Z, t=best_k, criterion="maxclust") - 1).tolist()
    order: list[int] = []
    mapping: dict[int, int] = {}
    for l in lab:
        if l not in mapping:
            mapping[l] = len(order)
            order.append(l)
    return [mapping[l] for l in lab]