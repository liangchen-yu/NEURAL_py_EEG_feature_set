"""amplitude_skew and amplitude_kurtosis as defined in neural_eeg_features 0.6.1
(the reference package; its docs/definitions.md, "Skewness and kurtosis:
correction to the earlier audit"):

- absolute bias-corrected sample skewness, abs(scipy.stats.skew(x, bias=False));
- bias-corrected Pearson kurtosis, scipy.stats.kurtosis(x, fisher=False, bias=False);
- on the finite values only (NaN and +/-inf are ignored);
- NaN for fewer than 3 (skewness) or 4 (kurtosis) values, or constant values.

The expected values come from the closed-form bias-corrected formulas, written
out with numpy below (no scipy), and from the reference package's own example.
That the regression results match the original NEURAL with these definitions
is checked by test_regression.py and test_edge_cases.py (fix section
"with_neural_eeg_features_0.6.1_moments").

Synthetic data only.
"""
import numpy as np
import pytest

from NEURAL_py_EEG import amplitude_features

RTOL = 1e-12


def closed_form(x):
    """Bias-corrected skewness G1 and Pearson kurtosis (G2 + 3) from the
    biased central moments m2, m3, m4 of the n values x."""
    x = np.asarray(x, dtype=float)
    n = x.size
    d = x - x.mean()
    m2, m3, m4 = (np.mean(d ** k) for k in (2, 3, 4))
    g1 = m3 / m2 ** 1.5
    skew = np.sqrt(n * (n - 1)) / (n - 2) * g1
    if n < 4:
        return abs(skew), np.nan
    excess = (n - 1) / ((n - 2) * (n - 3)) * ((n + 1) * m4 / m2 ** 2 - 3 * (n - 1))
    return abs(skew), excess + 3


def seeded(n, seed=2026):
    rng = np.random.default_rng(seed)
    return rng.standard_gamma(2.0, size=n) + np.sin(np.arange(n) / 7.0)


def test_reference_package_example():
    """docs/definitions.md of the reference package, [-2, -1, 0, 1, 2]:
    absolute skewness 0, Pearson kurtosis 1.8 (the original NEURAL: 1.7)."""
    x = np.array([-2.0, -1, 0, 1, 2])
    assert amplitude_features.amplitude_skew(x) == pytest.approx(0, abs=1e-15)
    assert amplitude_features.amplitude_kurtosis(x) == pytest.approx(1.8, rel=RTOL)


@pytest.mark.parametrize("x", [
    [3, 7, 8, 9, 1],
    [1, 2, 4, 8],
    [1, 2, 4, 8, 16, 32, 64],
    seeded(100),
    seeded(4096),
], ids=["docstring", "4 values", "7 values", "100 values", "4096 values"])
def test_matches_closed_form(x):
    skew, kurtosis = closed_form(x)
    assert amplitude_features.amplitude_skew(x) == pytest.approx(skew, rel=RTOL)
    assert amplitude_features.amplitude_kurtosis(x) == pytest.approx(kurtosis, rel=RTOL)


def test_correction_can_lower_kurtosis_of_flat_data():
    """The bias correction does not always raise the kurtosis: for very flat
    data, 4096 alternating -1/+1 values, the biased Pearson kurtosis m4 / m2**2
    is 1.0 and the corrected one is lower (0.99902...). The skewness magnitude
    is the biased one times sqrt(n(n-1))/(n-2) > 1, so it never decreases;
    here both are 0."""
    x = np.tile([-1.0, 1.0], 2048)
    d = x - x.mean()
    biased = np.mean(d ** 4) / np.mean(d ** 2) ** 2
    corrected = amplitude_features.amplitude_kurtosis(x)
    assert biased == 1.0
    assert corrected < biased
    assert corrected == pytest.approx(closed_form(x)[1], rel=RTOL)
    assert corrected == pytest.approx(0.99902272172, rel=1e-10)
    assert amplitude_features.amplitude_skew(x) == pytest.approx(0, abs=1e-15)


def test_docstring_values():
    x = [3, 7, 8, 9, 1]
    assert amplitude_features.amplitude_skew(x) == pytest.approx(0.6069, abs=5e-5)
    assert amplitude_features.amplitude_kurtosis(x) == pytest.approx(0.9618, abs=5e-5)


def test_returns_python_float():
    x = seeded(50)
    assert type(amplitude_features.amplitude_skew(x)) is float
    assert type(amplitude_features.amplitude_kurtosis(x)) is float


@pytest.mark.parametrize("n", [0, 1, 2])
def test_skew_needs_three_values(n):
    assert np.isnan(amplitude_features.amplitude_skew(np.arange(n, dtype=float) ** 2))


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_kurtosis_needs_four_values(n):
    assert np.isnan(amplitude_features.amplitude_kurtosis(np.arange(n, dtype=float) ** 2))


def test_three_values_give_skew_but_no_kurtosis():
    x = [1.0, 2.0, 4.0]
    assert amplitude_features.amplitude_skew(x) == pytest.approx(closed_form(x)[0], rel=RTOL)
    assert np.isnan(amplitude_features.amplitude_kurtosis(x))


@pytest.mark.parametrize("x", [
    [5.0] * 10,
    [0.0] * 10,
    [1.0] * 9 + [1.0 + 2.0 ** -52],  # range = eps, not above eps * max(1, 1)
    [1e6] * 9 + [1e6 + 1.1641532182693481e-10],  # one step above 1e6, below eps * 1e6
], ids=["constant 5", "zeros", "range eps", "range below eps * max"])
def test_constant_values_give_nan(x):
    assert np.isnan(amplitude_features.amplitude_skew(x))
    assert np.isnan(amplitude_features.amplitude_kurtosis(x))


def test_nan_and_inf_are_ignored():
    finite = seeded(200)
    with_gaps = np.concatenate([finite[:50], [np.nan, np.inf], finite[50:120], [-np.inf, np.nan], finite[120:]])
    assert amplitude_features.amplitude_skew(with_gaps) == amplitude_features.amplitude_skew(finite)
    assert amplitude_features.amplitude_kurtosis(with_gaps) == amplitude_features.amplitude_kurtosis(finite)


def test_only_non_finite_values_give_nan():
    x = [np.nan, np.inf, -np.inf, np.nan]
    assert np.isnan(amplitude_features.amplitude_skew(x))
    assert np.isnan(amplitude_features.amplitude_kurtosis(x))
