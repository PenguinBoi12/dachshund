from dachshund.widgets.state import KeyedState


def test_upsert__expect_it_stored_under_a_string_key() -> None:
    state = KeyedState()

    state.upsert(42, {"name": "ada"}, at=1.0)

    assert state.entries == {"42": {"name": "ada"}}


def test_upsert_twice__expect_the_second_value_winning() -> None:
    state = KeyedState()

    state.upsert("ada", {"ip": "10.0.0.1"}, at=1.0)
    state.upsert("ada", {"ip": "10.0.0.9"}, at=2.0)

    assert state.entries == {"ada": {"ip": "10.0.0.9"}}


def test_remove__expect_the_entry_gone() -> None:
    state = KeyedState()
    state.upsert("ada", {}, at=1.0)

    state.remove("ada")

    assert state.entries == {}


def test_remove_unknown_key__expect_no_error() -> None:
    KeyedState().remove("nope")


def test_sweep__expect_only_stale_entries_removed() -> None:
    state = KeyedState()
    state.upsert("ada", {}, at=1.0)
    state.upsert("bob", {}, at=5.0)

    state.sweep(before=3.0)

    assert state.entries == {"bob": {}}


def test_upsert__expect_each_new_key_assigned_the_next_sequence() -> None:
    state = KeyedState()

    state.upsert("ada", {})
    state.upsert("bob", {})

    assert state.sequence == {"ada": 0, "bob": 1}


def test_upsert_twice__expect_the_sequence_unchanged() -> None:
    state = KeyedState()
    state.upsert("ada", {})

    state.upsert("ada", {"ip": "10.0.0.9"})

    assert state.sequence == {"ada": 0}


def test_remove__expect_the_sequence_gone_too() -> None:
    state = KeyedState()
    state.upsert("ada", {})

    state.remove("ada")

    assert state.sequence == {}


def test_snapshot_and_restore__expect_a_round_trip() -> None:
    state = KeyedState()
    state.upsert(42, {"name": "ada"}, at=1.0)

    restored = KeyedState()
    restored.restore(state.snapshot())

    assert restored.entries == {"42": {"name": "ada"}}
    assert restored.seen_at == {"42": 1.0}
    assert restored.sequence == {"42": 0}


def test_restore_then_upsert__expect_the_new_sequence_continuing_after_the_restored_one() -> (
    None
):
    state = KeyedState()
    state.upsert("ada", {})
    state.upsert("bob", {})

    restored = KeyedState()
    restored.restore(state.snapshot())
    restored.upsert("cleo", {})

    assert restored.sequence["cleo"] == 2
