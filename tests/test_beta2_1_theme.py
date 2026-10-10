from cropwater_rs.ui.theme import get_palette


def test_hybrid_theme_has_complete_tokens():
    p = get_palette("hybrid")
    assert all(p[key].startswith("#") and len(p[key]) == 7 for key in (
        "bg", "surface", "surface_alt", "border", "text", "muted",
        "primary", "primary_hover", "accent", "success", "warning",
        "button", "button_hover", "secondary", "secondary_hover",
        "tab", "input", "selection",
    ))


def test_classic_theme_is_reversible():
    assert get_palette("classic")["primary"] == "#176B87"
    palette = get_palette("hybrid")
    palette["primary"] = "#000000"
    assert get_palette("hybrid")["primary"] != "#000000"
