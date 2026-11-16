"""glmm.py: random-intercept logistic regression recovers a known effect and finds none when the arms agree."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import numpy as np
    import glmm
except ImportError:  # macOS Python has no numpy/scipy
    glmm = None

real = lambda r: r["verdict"] == "real"  # noqa: E731


def simulate(n_faults, sigma, b0, b1, n, seed):
    rng = np.random.default_rng(seed)
    a, b = [], []
    for f in range(n_faults):
        u = rng.normal(0, sigma)
        for arm, eta, out in (("a", b0 + b1 + u, a), ("b", b0 + u, b)):
            p = 1 / (1 + np.exp(-eta))
            out += [{"problem_id": f"F{f}", "arm": arm, "verdict": "real" if rng.random() < p else "none"} for _ in range(n)]
    return a, b


@unittest.skipIf(glmm is None, "needs numpy and scipy")
class Glmm(unittest.TestCase):
    def test_recovers_known_odds_ratio_and_variance(self):
        a, b = simulate(300, 1.5, 0.0, np.log(4), 10, seed=1)
        res = glmm.glmm_contrast(a, b, real)
        self.assertAlmostEqual(np.log(res["or_"]), np.log(4), delta=0.25)
        self.assertAlmostEqual(res["sigma"], 1.5, delta=0.3)
        self.assertLess(res["lo"], 4)
        self.assertGreater(res["hi"], 4)
        self.assertLess(res["p"], 1e-6)

    def test_no_effect_when_arms_are_identical(self):
        a, _ = simulate(12, 2.0, 0.0, 0.0, 10, seed=2)
        b = [dict(r, arm="b") for r in a]
        res = glmm.glmm_contrast(a, b, real)
        self.assertAlmostEqual(res["or_"], 1.0, places=3)
        self.assertGreater(res["p"], 0.99)

    def test_quadrature_is_stable(self):
        a, b = simulate(12, 3.0, 0.5, -1.5, 10, seed=3)
        coarse = glmm.glmm_contrast(a, b, real, nodes=401)
        fine = glmm.glmm_contrast(a, b, real, nodes=1601)
        self.assertAlmostEqual(coarse["or_"], fine["or_"], delta=0.002 * fine["or_"])


if __name__ == "__main__":
    unittest.main()
