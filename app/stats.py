from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Callable, Iterable

import fitz
from ezdxf.entities import DXFGraphic

from .constants import PAGE_MARGIN
from .geometry import iter_entity_paths


@dataclass
class ConversionStats:
    layer_lengths: dict[str, float]
    included_layers: dict[str, bool]
    total_cut_length: float


def path_length(path: list[tuple[float, float]]) -> float:
    return sum(math.dist(start, end) for start, end in zip(path, path[1:]))


def is_total_excluded_layer(layer: str) -> bool:
    layer_lower = layer.lower()
    return layer_lower == "0" or "board" in layer_lower or "text" in layer_lower


def collect_stats(entities: Iterable[DXFGraphic], include_layer: Callable[[str], bool] | None = None) -> ConversionStats:
    layer_lengths: dict[str, float] = {}
    for entity in entities:
        layer = str(entity.dxf.layer or "0")
        for path in iter_entity_paths(entity):
            layer_lengths[layer] = layer_lengths.get(layer, 0) + path_length(path)

    included_layers = {
        layer: include_layer(layer) if include_layer else not is_total_excluded_layer(layer)
        for layer in layer_lengths
    }
    total_cut_length = sum(length for layer, length in layer_lengths.items() if included_layers[layer])
    return ConversionStats(layer_lengths=layer_lengths, included_layers=included_layers, total_cut_length=total_cut_length)


def stats_to_dict(stats: ConversionStats, mm_per_unit: float) -> dict:
    sorted_layers = sorted(stats.layer_lengths.items(), key=lambda item: item[0].lower())
    return {
        "layers": [
            {
                "name": layer,
                "length_mm": round(length * mm_per_unit, 2),
                "included": stats.included_layers.get(layer, False),
            }
            for layer, length in sorted_layers
        ],
        "total_mm": round(stats.total_cut_length * mm_per_unit, 2),
    }


def summary_height(stats: ConversionStats) -> float:
    if not stats.layer_lengths:
        return 0
    row_h = 9
    header_h = 22
    total_h = 16
    padding = 14
    return padding + header_h + len(stats.layer_lengths) * row_h + total_h + padding


def draw_summary(page: fitz.Page, stats: ConversionStats, mm_per_unit: float) -> None:
    if not stats.layer_lengths:
        return

    left = PAGE_MARGIN
    col_layer = left
    col_len = left + 200
    col_total = left + 290
    row_h = 9
    y = PAGE_MARGIN

    header_h = 18
    table_width = 340

    def draw_rect(x0, y0, x1, y1, stroke=0.5, fill=None):
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x0, y0, x1, y1))
        if fill:
            shape.finish(color=(0, 0, 0), width=stroke, fill=fill)
        else:
            shape.finish(color=(0, 0, 0), width=stroke)
        shape.commit()

    def draw_line(x0, yy0, x1, yy1, stroke=0.5):
        shape = page.new_shape()
        shape.draw_line(fitz.Point(x0, yy0), fitz.Point(x1, yy1))
        shape.finish(color=(0, 0, 0), width=stroke)
        shape.commit()

    draw_rect(left, y, left + table_width, y + header_h, stroke=0.8)

    page.insert_text(fitz.Point(col_layer + 4, y + 13), "Layer", fontsize=7, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(col_len + 4, y + 13), "Length, mm", fontsize=7, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(col_total + 4, y + 13), "In total", fontsize=7, fontname="helv", color=(0, 0, 0))

    draw_line(col_len, y, col_len, y + header_h)
    draw_line(col_total, y, col_total, y + header_h)
    y += header_h

    sorted_layers = sorted(stats.layer_lengths.items(), key=lambda item: item[0].lower())
    for i, (layer, length) in enumerate(sorted_layers):
        included = stats.included_layers.get(layer, False)
        row_bottom = y + row_h

        if i % 2 == 0:
            draw_rect(left, y, left + table_width, row_bottom, stroke=0.3, fill=(0.95, 0.95, 0.95))
        else:
            draw_rect(left, y, left + table_width, row_bottom, stroke=0.3)

        draw_line(col_len, y, col_len, row_bottom)
        draw_line(col_total, y, col_total, row_bottom)

        page.insert_text(fitz.Point(col_layer + 4, y + 7), layer[:36], fontsize=6, fontname="helv", color=(0, 0, 0))
        page.insert_text(fitz.Point(col_len + 4, y + 7), f"{length * mm_per_unit:.2f}", fontsize=6, fontname="helv", color=(0, 0, 0))
        checkmark = "X" if included else "-"
        page.insert_text(fitz.Point(col_total + 12, y + 7), checkmark, fontsize=6, fontname="helv", color=(0, 0, 0))
        y = row_bottom

    total_bottom = y + 14
    draw_rect(left, y, left + table_width, total_bottom, stroke=0.8)
    draw_line(col_len, y, col_len, total_bottom)
    draw_line(col_total, y, col_total, total_bottom)

    total_mm = stats.total_cut_length * mm_per_unit
    page.insert_text(fitz.Point(col_layer + 4, y + 10), "TOTAL", fontsize=7, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(col_len + 4, y + 10), f"{total_mm:.2f}", fontsize=7, fontname="helv", color=(0, 0, 0))
