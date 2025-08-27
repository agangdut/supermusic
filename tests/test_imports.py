def test_imports():
    import importlib

    for mod in ["enrichedmetadata", "mixtape_segmenter"]:
        importlib.import_module(mod)


def test_entry_points_exist():
    # smoke-check critical functions exist
    import enrichedmetadata as em
    import mixtape_segmenter as ms

    assert hasattr(em, "main")
    assert hasattr(ms, "main")
