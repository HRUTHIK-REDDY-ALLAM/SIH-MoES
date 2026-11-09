"""
Varsha — Active/break regime model (2-state Gaussian HMM, pure numpy).

Observation: log(1 + 7-day trailing mean rainfall) for a block. States are
ordered so that state 0 = break (low rain) and state 1 = active.

Used for
  * a model feature: filtered P(break) using observations up to t-1
  * the current regime shown on the dashboard
  * expected active/break spell durations from the transition matrix
"""

from __future__ import annotations

import numpy as np

LOG2PI = np.log(2 * np.pi)


def regime_obs(rain: np.ndarray, window: int = 7) -> np.ndarray:
    """log1p of trailing `window`-day mean rain (axis 0 = time)."""
    c = np.vstack([np.zeros((1,) + rain.shape[1:]), np.cumsum(rain, axis=0)])
    t = np.arange(1, rain.shape[0] + 1)
    lo = np.maximum(t - window, 0)
    mean = (c[t] - c[lo]) / (t - lo)[:, None] if rain.ndim == 2 else (c[t] - c[lo]) / (t - lo)
    return np.log1p(mean)


class RegimeHMM:
    def __init__(self, means=None, variances=None, trans=None, start=None):
        self.means = np.asarray(means if means is not None else [0.3, 2.0], dtype=float)
        self.vars = np.asarray(variances if variances is not None else [0.3, 0.3], dtype=float)
        self.A = np.asarray(trans if trans is not None else [[0.9, 0.1], [0.1, 0.9]], dtype=float)
        self.pi = np.asarray(start if start is not None else [0.5, 0.5], dtype=float)

    # ── emissions ──
    def _emis(self, x: np.ndarray) -> np.ndarray:
        x = x[..., None]
        return np.exp(-0.5 * (LOG2PI + np.log(self.vars) + (x - self.means) ** 2 / self.vars))

    # ── fitting ──
    @classmethod
    def fit(cls, X: np.ndarray, n_iter: int = 60, tol: float = 1e-5) -> "RegimeHMM":
        """Baum-Welch on N equal-length sequences, X: [T, N] (vectorised over sequences)."""
        T, N = X.shape
        m = cls(means=np.quantile(X, [0.25, 0.8]), variances=[X.var() / 2] * 2)
        prev = -np.inf
        for _ in range(n_iter):
            B = m._emis(X) + 1e-300                      # [T, N, 2]
            alpha = np.zeros((T, N, 2))
            c = np.zeros((T, N))
            alpha[0] = m.pi * B[0]
            c[0] = alpha[0].sum(axis=1)
            alpha[0] /= c[0][:, None]
            for t in range(1, T):
                alpha[t] = (alpha[t - 1] @ m.A) * B[t]
                c[t] = alpha[t].sum(axis=1)
                alpha[t] /= c[t][:, None]
            beta = np.ones((T, N, 2))
            for t in range(T - 2, -1, -1):
                beta[t] = ((B[t + 1] * beta[t + 1]) @ m.A.T) / c[t + 1][:, None]
            gamma = alpha * beta
            gamma /= gamma.sum(axis=2, keepdims=True)
            xi = (alpha[:-1, :, :, None] * m.A[None, None] * (B[1:] * beta[1:])[:, :, None, :]) / c[1:, :, None, None]
            s_g = gamma.sum(axis=(0, 1))
            m.means = (gamma * X[..., None]).sum(axis=(0, 1)) / s_g
            m.vars = np.maximum((gamma * X[..., None] ** 2).sum(axis=(0, 1)) / s_g - m.means ** 2, 0.06)
            s_xi = xi.sum(axis=(0, 1))
            m.A = s_xi / s_xi.sum(axis=1, keepdims=True)
            m.pi = gamma[0].sum(axis=0) / N
            ll = np.log(c).sum()
            if ll - prev < tol * abs(ll):
                break
            prev = ll
        # order states: 0 = break (low mean), 1 = active
        if m.means[0] > m.means[1]:
            order = [1, 0]
            m.means, m.vars, m.pi = m.means[order], m.vars[order], m.pi[order]
            m.A = m.A[np.ix_(order, order)]
        return m

    @classmethod
    def fit_climate(cls, cd, years, doy_range=(160, 280)) -> "RegimeHMM":
        seqs = []
        for y in years:
            sl = cd.year_slice(y)
            doys = cd.dates[sl].dayofyear.values
            keep = (doys >= doy_range[0]) & (doys <= doy_range[1])
            seqs.append(regime_obs(cd.rain[sl])[keep])
        return cls.fit(np.hstack(seqs))

    # ── inference ──
    def filter_break_probability(self, rain: np.ndarray) -> np.ndarray:
        """Filtered P(break | obs up to and including t) for each block. rain: [T, nb]."""
        x = regime_obs(rain)
        B = self._emis(x) + 1e-300  # [T, nb, 2]
        T, nb = x.shape
        out = np.zeros((T, nb))
        a = np.tile(self.pi, (nb, 1)) * B[0]
        a /= a.sum(axis=1, keepdims=True)
        out[0] = a[:, 0]
        for t in range(1, T):
            a = (a @ self.A) * B[t]
            a /= a.sum(axis=1, keepdims=True)
            out[t] = a[:, 0]
        return out

    def expected_durations(self) -> dict:
        return {
            "break_days": float(1 / max(1 - self.A[0, 0], 1e-6)),
            "active_days": float(1 / max(1 - self.A[1, 1], 1e-6)),
        }

    def to_dict(self) -> dict:
        return {"means": self.means.tolist(), "variances": self.vars.tolist(),
                "trans": self.A.tolist(), "start": self.pi.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "RegimeHMM":
        return cls(d["means"], d["variances"], d["trans"], d["start"])
