from solidifai import ShownObject, _registry, reset_registry, show


def setup_function():
    reset_registry()


def test_show_with_explicit_fields():
    show("FAKE", name="Bracket", color=(0.7, 0.7, 0.75))
    reg = _registry()
    assert len(reg) == 1
    obj = reg[0]
    assert isinstance(obj, ShownObject)
    assert obj.name == "Bracket"
    assert obj.shape == "FAKE"
    assert obj.color == (0.7, 0.7, 0.75)


def test_autoname():
    show("A")
    show("B")
    reg = _registry()
    assert len(reg) == 2
    assert reg[0].name == "object_1"
    assert reg[1].name == "object_2"
    assert reg[0].shape == "A"
    assert reg[1].shape == "B"
    assert reg[0].color is None


def test_reset_clears():
    show("A")
    assert len(_registry()) == 1
    reset_registry()
    assert _registry() == []
