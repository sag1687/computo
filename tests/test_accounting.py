from COMPUTO.accounting import build_category_summary, compute_sal_totals


def test_build_category_summary_aggregates_totals():
    rows = [
        {"category": "Scavi", "total_price": 100.0},
        {"category": "Scavi", "total_price": 50.0},
        {"category": "Pavimenti", "total_price": 80.0},
    ]
    summary = build_category_summary(rows)
    assert summary[0]["category"] == "Pavimenti"
    assert summary[0]["total_price"] == 80.0
    assert summary[1]["category"] == "Scavi"
    assert summary[1]["total_price"] == 150.0


def test_compute_sal_totals_returns_due_and_vat():
    rows = [
        {"total_price": 100.0},
        {"total_price": 50.0},
    ]
    totals = compute_sal_totals(
        rows,
        security_costs=10.0,
        retention_percent=10.0,
        vat_percent=22.0,
        previous_paid=20.0,
    )
    assert totals["works_total"] == 150.0
    assert totals["gross_total"] == 160.0
    assert totals["retention_amount"] == 16.0
    assert totals["certified_to_date"] == 144.0
    assert totals["due_before_vat"] == 124.0
    assert totals["vat_due"] == 27.28
    assert totals["total_due"] == 151.28
