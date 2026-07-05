from app.global_prices import _percentile, global_estimate
from app.models import GlobalProduct


def _v(*prices):
    return [GlobalProduct(name=f"p{i}", normalized_name=f"p{i}", price=p)
            for i, p in enumerate(prices)]


def test_percentile_basics():
    assert _percentile([10.0], 0.25) == 10.0
    # 0..100 -> 25th percentile is 25
    assert _percentile([0.0, 50.0, 100.0, 150.0, 200.0], 0.25) == 50.0


def test_weighed_uses_low_percentile_not_median():
    # Fresh cucumber 6 among pricey pickled/packaged variants.
    variants = _v(6.0, 12.0, 15.0, 20.0)
    # Median would be ~13.5; weighed low-percentile stays near the cheap fresh item.
    assert global_estimate(variants, weighed=False) == 13.5
    assert global_estimate(variants, weighed=True) < 11.0


def test_non_weighed_unchanged_median():
    variants = _v(4.0, 6.0, 8.0)
    assert global_estimate(variants, weighed=False) == 6.0


def test_empty_none():
    assert global_estimate([], weighed=True) is None
