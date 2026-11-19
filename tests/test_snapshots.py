from scripts.etl.treatment.snapshots import build_snapshot


def test_snapshot_key_is_unique_per_ad_and_day():
    a = build_snapshot("h1", 1000, None, 150, "19/11/2026")
    b = build_snapshot("h1", 1200, None, 150, "19/11/2026")
    c = build_snapshot("h1", 1000, None, 150, "20/11/2026")
    assert a["snapshot_key"] == b["snapshot_key"] != c["snapshot_key"]
    assert a == {
        "hash": "h1", "snapshot_key": "h1_19/11/2026", "preco": 1000,
        "condominio": None, "iptu": 150, "data_coleta": "19/11/2026",
    }
