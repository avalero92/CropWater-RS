"""Beta 2.1 visual design tokens. No scientific dependencies."""
from types import MappingProxyType

PALETTES = {
    "hybrid": {
        "bg": "#EDF2F6", "surface": "#FFFFFF", "surface_alt": "#F5F8FB",
        "border": "#D6E1EA", "text": "#192C3C", "muted": "#607589",
        "primary": "#122536", "primary_hover": "#214358", "accent": "#14A9B0",
        "success": "#20845E", "warning": "#B77A26",
        "button": "#087DA9", "button_hover": "#08698E",
        "secondary": "#E6EEF3", "secondary_hover": "#D6E5EC",
        "tab": "#E3EBF1", "input": "#FFFFFF", "selection": "#087DA9",
    },
    "classic": {
        "bg": "#F4F7FA", "surface": "#FFFFFF", "surface_alt": "#F8FAFC",
        "border": "#D8E0E8", "text": "#1D2A35", "muted": "#667788",
        "primary": "#176B87", "primary_hover": "#135A72", "accent": "#64CCC5",
        "success": "#2F855A", "warning": "#B7791F",
        "button": "#176B87", "button_hover": "#135A72",
        "secondary": "#EAF1F5", "secondary_hover": "#DCE8EE",
        "tab": "#E8EEF2", "input": "#FFFFFF", "selection": "#176B87",
    },
}

def get_palette(name="hybrid"):
    if name not in PALETTES:
        raise ValueError(f"Unknown UI theme: {name}")
    return dict(PALETTES[name])
