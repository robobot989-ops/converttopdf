from __future__ import annotations

from dataclasses import dataclass

from ezdxf.entities import DXFGraphic


ACAD_COLORS = {
    1: (255 / 255, 0 / 255, 0 / 255),
    2: (255 / 255, 255 / 255, 0 / 255),
    3: (0 / 255, 255 / 255, 0 / 255),
    4: (0 / 255, 255 / 255, 255 / 255),
    5: (0 / 255, 0 / 255, 255 / 255),
    6: (255 / 255, 0 / 255, 255 / 255),
    7: (0 / 255, 0 / 255, 0 / 255),
    8: (128 / 255, 128 / 255, 128 / 255),
    9: (192 / 255, 192 / 255, 192 / 255),
    12: (189 / 255, 0 / 255, 0 / 255),
}

DEFAULT_LAYER_STYLES = [
    {"match": "cut", "color": "#ff0000", "width": 1, "dash": "solid", "include_in_total": True},
    {"match": "Board", "color": "#000000", "width": 0.5, "dash": "dashed", "include_in_total": False},
    {"match": "big", "color": "#008000", "width": 1, "dash": "solid", "include_in_total": True},
    {"match": "ric", "color": "#0000ff", "width": 1, "dash": "solid", "include_in_total": True},
    {"match": "prf", "color": "#008000", "width": 1, "dash": "dashed", "include_in_total": True},
    {"match": "text", "color": "#808080", "width": 0.5, "dash": "solid", "include_in_total": False},
]


@dataclass
class LayerStyle:
    match: str
    color: tuple[float, float, float]
    width: float
    dash: str
    include_in_total: bool


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        return ACAD_COLORS[7]
    try:
        return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)
    except ValueError:
        return ACAD_COLORS[7]


def parse_layer_styles(raw_styles: str | None) -> list[LayerStyle]:
    import json

    source = DEFAULT_LAYER_STYLES
    if raw_styles:
        try:
            loaded = json.loads(raw_styles)
            if isinstance(loaded, list):
                source = loaded
        except json.JSONDecodeError:
            source = DEFAULT_LAYER_STYLES

    styles = []
    for item in source:
        if not isinstance(item, dict) or not str(item.get("match", "")).strip():
            continue
        styles.append(
            LayerStyle(
                match=str(item.get("match", "")).strip(),
                color=hex_to_rgb(str(item.get("color", "#000000"))),
                width=max(float(item.get("width", 0.7) or 0.7), 0.1),
                dash="dashed" if str(item.get("dash", "solid")).lower() == "dashed" else "solid",
                include_in_total=bool(item.get("include_in_total", True)),
            )
        )
    return styles


def entity_color(entity: DXFGraphic) -> tuple[float, float, float]:
    color_index = int(entity.dxf.color or 7)
    return ACAD_COLORS.get(color_index, ACAD_COLORS[7])


def entity_style(entity: DXFGraphic, layer_styles: list[LayerStyle]) -> LayerStyle:
    layer = str(entity.dxf.layer or "")
    layer_lower = layer.lower()
    for style in layer_styles:
        if style.match.lower() in layer_lower:
            return style
    return LayerStyle(match="", color=entity_color(entity), width=0.7, dash="solid", include_in_total=True)


def layer_include_in_total(layer: str, layer_styles: list[LayerStyle]) -> bool:
    layer_lower = layer.lower()
    for style in layer_styles:
        if style.match.lower() in layer_lower:
            return style.include_in_total
    return not (layer_lower == "0" or "board" in layer_lower or "text" in layer_lower)
