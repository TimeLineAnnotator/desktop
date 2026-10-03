import examples


def test_load_counts_and_fixtures():
    data = examples.load()
    assert [e.n for e in data["examples"]] == list(range(1, 91))
    assert set(data["fixtures"]) == {
        "exposition",
        "sonata",
        "pop",
        "strophic",
        "harmony",
        "repeat",
        "recipe",
        "scripts",
    }


def test_every_fixture_exists():
    data = examples.load()
    assert all(e.fixture in data["fixtures"] for e in data["examples"])


def test_first_example():
    first = examples.load()["examples"][0]
    assert first.query == "ST[continuation{2}] IN form"
    assert first.fixture == "exposition"
    assert first.rows == ["ST@10"]


def test_some_example_writes():
    assert any(e.writes for e in examples.load()["examples"])
