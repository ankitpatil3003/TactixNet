def test_scaffold_health() -> None:
    from gateway.app import app

    assert app.title == "TactixNet Gateway"
