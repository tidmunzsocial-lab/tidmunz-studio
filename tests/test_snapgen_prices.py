import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "snapgen_modules"))
from snapgen_prices import image_cost


def test_image_cost_reads_live_credit_price():
    rows = [{"model_name": "gpt-image-2.5-lower", "effective_price": 1,
             "currency": "CREDIT", "price_unit": "image"}]
    assert image_cost(rows, "gpt-image-2.5-lower") == 1


def test_image_cost_does_not_guess_when_price_rows_conflict():
    rows = [
        {"model_name": "gpt-image-2.5-lower", "effective_price": 1,
         "currency": "CREDIT", "price_unit": "image"},
        {"model_name": "gpt-image-2.5-lower", "effective_price": 2,
         "currency": "CREDIT", "price_unit": "image"},
    ]
    assert image_cost(rows, "gpt-image-2.5-lower") is None
