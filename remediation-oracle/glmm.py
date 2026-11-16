"""Mixed-effects logistic regression for one arm contrast, the model the pre-registration first named (sensitivity analysis).

logit P(y = 1) = b0 + b1 * [run is in arm a] + u_fault,  u_fault ~ N(0, s^2)

Fitted by maximum likelihood; the random intercept is integrated out numerically on a fine grid of the standardized
effect z = u / s (Simpson's rule on [-10, 10]; fixed Gauss-Hermite nodes converge slowly when s is large, as here).
Only numpy and scipy (requirements.txt), because the analysis environment has no mixed-model library. Reports the odds
ratio exp(b1) with a Wald 95% interval and a likelihood-ratio p-value (b1 = 0).
"""
from collections import defaultdict

import numpy as np
from scipy import optimize, special, stats

NODES = 801  # grid points for z, odd for Simpson's rule
BOUND = 20.0  # |b0|, |b1| at most 20 on the logit scale; an estimate at the bound means separation
LOG_S = (-8.0, 3.0)


def _counts(rows_a, rows_b, pred):
    """Per fault present in both arms: (successes a, runs a, successes b, runs b)."""
    by = defaultdict(lambda: [0, 0, 0, 0])
    for r in rows_a:
        by[r["problem_id"]][0] += bool(pred(r))
        by[r["problem_id"]][1] += 1
    for r in rows_b:
        by[r["problem_id"]][2] += bool(pred(r))
        by[r["problem_id"]][3] += 1
    return np.array([v for v in by.values() if v[1] and v[3]], dtype=float)


def _loglik(theta, c, x, w):
    b0, b1, log_s = theta
    u = np.exp(log_s) * x  # grid points for u = s * z
    eta_a = b0 + b1 + u[None, :]
    eta_b = b0 + u[None, :]
    ka, na, kb, nb = (c[:, i:i + 1] for i in range(4))
    # binomial log-likelihood without the constant; log(sigmoid(e)) = -log1p(exp(-e)), stable through logaddexp
    ll = (ka * -np.logaddexp(0, -eta_a) + (na - ka) * -np.logaddexp(0, eta_a)
          + kb * -np.logaddexp(0, -eta_b) + (nb - kb) * -np.logaddexp(0, eta_b))
    return float(np.sum(special.logsumexp(ll, b=w[None, :], axis=1)))


def _grid(n):
    """Simpson weights for the integral over z of f(z) * phi(z) on [-10, 10]."""
    x = np.linspace(-10.0, 10.0, n)
    h = x[1] - x[0]
    simpson = np.ones(n)
    simpson[1:-1:2], simpson[2:-1:2] = 4, 2
    return x, simpson * h / 3 * stats.norm.pdf(x)


def _fit(c, x, w, fix_b1):
    def neg(t):
        theta = (t[0], 0.0, t[1]) if fix_b1 else t
        return -_loglik(theta, c, x, w)
    bounds = [(-BOUND, BOUND), (LOG_S[0], LOG_S[1])] if fix_b1 else [(-BOUND, BOUND)] * 2 + [LOG_S]
    best = None
    for s0 in (0.0, 1.0):  # two starting points for the variance; keep the better optimum
        start = [0.0, s0] if fix_b1 else [0.0, 0.0, s0]
        res = optimize.minimize(neg, start, method="L-BFGS-B", bounds=bounds)
        if best is None or res.fun < best.fun:
            best = res
    return best


def _hessian(f, t, h=1e-4):
    k = len(t)
    hess = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            def at(di, dj):
                p = np.array(t, dtype=float)
                p[i] += di
                p[j] += dj
                return f(p)
            hess[i, j] = (at(h, h) - at(h, -h) - at(-h, h) + at(-h, -h)) / (4 * h * h)
    return hess


def glmm_contrast(rows_a, rows_b, pred, nodes=NODES):
    """Returns dict(or_, lo, hi, p, sigma, separated) for arm a versus arm b, random intercept per fault."""
    c = _counts(rows_a, rows_b, pred)
    x, w = _grid(nodes)
    full = _fit(c, x, w, fix_b1=False)
    null = _fit(c, x, w, fix_b1=True)
    b1 = full.x[1]
    p = float(stats.chi2.sf(max(0.0, 2 * (null.fun - full.fun)), 1))
    separated = abs(b1) > BOUND - 1e-3
    lo = hi = float("nan")
    if not separated:
        hess = _hessian(lambda t: _loglik(t, c, x, w), full.x)
        try:
            var = np.linalg.inv(-hess)[1, 1]
            if var > 0:
                se = np.sqrt(var)
                lo, hi = float(np.exp(b1 - 1.96 * se)), float(np.exp(b1 + 1.96 * se))
        except np.linalg.LinAlgError:
            pass
    return {"or_": float(np.exp(b1)), "lo": lo, "hi": hi, "p": p, "sigma": float(np.exp(full.x[2])), "separated": separated}
