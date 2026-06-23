from __future__ import annotations

import math
from dataclasses import dataclass
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


def summary_height(stats: ConversionStats) -> float:
    if not stats.layer_lengths:
        return 0
    return 44 + len(stats.layer_lengths) * 11


def draw_summary(page: fitz.Page, stats: ConversionStats, mm_per_unit: float) -> None:
    if not stats.layer_lengths:
        return

    left = PAGE_MARGIN
    y = PAGE_MARGIN
    row_height = 11
    total_mm = stats.total_cut_length * mm_per_unit

    page.insert_text(fitz.Point(left, y), f"DXF length summary: total included = {total_mm:.2f} mm", fontsize=8, color=(0, 0, 0))
    y += 14
    page.insert_text(fitz.Point(left, y), "Layer", fontsize=7, color=(0, 0, 0))
    page.insert_text(fitz.Point(left + 190, y), "Length, mm", fontsize=7, color=(0, 0, 0))
    page.insert_text(fitz.Point(left + 260, y), "In total", fontsize=7, color=(0, 0, 0))
    y += row_height

    for layer, length in sorted(stats.layer_lengths.items(), key=lambda item: item[0].lower()):
        included = stats.included_layers.get(layer, False)
        page.insert_text(fitz.Point(left, y), layer[:36], fontsize=6.5, color=(0, 0, 0))
        page.insert_text(fitz.Point(left + 190, y), f"{length * mm_per_unit:.2f}", fontsize=6.5, color=(0, 0, 0))
        page.insert_text(fitz.Point(left + 260, y), "yes" if included else "no", fontsize=6.5, color=(0, 0, 0))
        y += row_height
