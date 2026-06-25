from __future__ import annotations

import html
import math
from pathlib import Path

import ezdxf
import ezdxf.path
from ezdxf.entities import DXFGraphic

from .constants import DXF_INSUNITS_TO_MM
from .geometry import Bounds, collect_bounds, iter_entity_paths, iter_text_entities, text_value
from .layer_styles import LayerStyle, entity_style, layer_include_in_total, parse_layer_styles


def rgb_hex(color: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(color[0] * 255), int(color[1] * 255), int(color[2] * 255))


def svg_escape(value: str) -> str:
    return html.escape(value, quote=True)


def path_d(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    parts = [f"M {points[0][0]:.6f} {points[0][1]:.6f}"]
    for x, y in points[1:]:
        parts.append(f"L {x:.6f} {y:.6f}")
    return " ".join(parts)


def convert_dxf_to_svg(
    input_path: Path,
    output_path: Path,
    raw_layer_styles: str | None = None,
    doc: ezdxf.EzdxfDocument | None = None,
) -> None:
    if doc is None:
        try:
            doc = ezdxf.readfile(input_path)
        except ezdxf.DXFError as exc:
            raise ValueError("Could not read DXF file") from exc

    modelspace = list(doc.modelspace())
    bounds = collect_bounds(modelspace)
    if bounds.is_empty:
        raise ValueError("DXF file does not contain supported drawable entities")

    mm_per_unit = DXF_INSUNITS_TO_MM.get(
        int(doc.header.get("$INSUNITS", 0) or 0), 1.0
    )
    layer_styles = parse_layer_styles(raw_layer_styles)

    width = bounds.width * mm_per_unit
    height = bounds.height * mm_per_unit
    margin = 5
    svg_width = width + margin * 2
    svg_height = height + margin * 2

    def to_svg(x: float, y: float) -> tuple[float, float]:
        sx = (x - bounds.min_x) * mm_per_unit + margin
        sy = (bounds.max_y - y) * mm_per_unit + margin
        return sx, sy

    layer_order: list[str] = []
    entities_by_layer: dict[str, list[DXFGraphic]] = {}
    for entity in modelspace:
        layer = str(entity.dxf.layer or "0")
        if layer not in entities_by_layer:
            entities_by_layer[layer] = []
            layer_order.append(layer)
        entities_by_layer[layer].append(entity)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{svg_width:.6f}mm" height="{svg_height:.6f}mm" '
        f'viewBox="0 0 {svg_width:.6f} {svg_height:.6f}">',
        f'<g id="Layer_0">',
    ]

    for layer in layer_order:
        entities = entities_by_layer[layer]
        lines.append(f'  <g id="{svg_escape(layer)}" '
                     f'inkscape:groupmode="layer" '
                     f'inkscape:label="{svg_escape(layer)}">')

        for entity in entities:
            style = entity_style(entity, layer_styles)
            stroke = rgb_hex(style.color)
            stroke_width = style.width * mm_per_unit
            dash_array = "4 3" if style.dash == "dashed" else "none"
            dash_attr = f' stroke-dasharray="{dash_array}"' if dash_array != "none" else ""

            if entity.dxftype() in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
                try:
                    path = ezdxf.path.make_path(entity)
                except TypeError:
                    continue

                points = []
                for point in path.flattening(distance=0.05):
                    points.append(to_svg(float(point.x), float(point.y)))

                if len(points) >= 2:
                    d = path_d(points)
                    lines.append(
                        f'    <path d="{d}" fill="none" '
                        f'stroke="{stroke}" stroke-width="{stroke_width:.4f}"{dash_attr}/>'
                    )

            elif entity.dxftype() in {"TEXT", "MTEXT"}:
                t = text_value(entity)
                if not t.strip():
                    continue
                insert = entity.dxf.insert
                sx, sy = to_svg(float(insert.x), float(insert.y))
                font_size = float(getattr(entity.dxf, "height", 2.5)) * mm_per_unit
                rotation = float(getattr(entity.dxf, "rotation", 0) or 0)
                lines.append(
                    f'    <text x="{sx:.6f}" y="{sy:.6f}" '
                    f'font-size="{font_size:.4f}" fill="{stroke}" '
                    f'transform="rotate({rotation:.2f} {sx:.6f} {sy:.6f})">'
                    f'{svg_escape(t)}</text>'
                )

        lines.append("  </g>")

    lines.extend(["</g>", "</svg>"])

    output_path.write_text("\n".join(lines), encoding="utf-8")
