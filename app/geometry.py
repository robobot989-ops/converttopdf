from __future__ import annotations

import math
from typing import Iterable

import ezdxf.path
import fitz
from ezdxf.entities import DXFGraphic

from .constants import FLATTENING_DISTANCE, PAGE_MARGIN


class Bounds:
    def __init__(self) -> None:
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf

    def add_point(self, x: float, y: float) -> None:
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    @property
    def is_empty(self) -> bool:
        return not all(math.isfinite(value) for value in (self.min_x, self.min_y, self.max_x, self.max_y))

    @property
    def width(self) -> float:
        return max(self.max_x - self.min_x, 1e-9)

    @property
    def height(self) -> float:
        return max(self.max_y - self.min_y, 1e-9)


def path_to_points(entity: DXFGraphic) -> list[tuple[float, float]]:
    path = ezdxf.path.make_path(entity)
    return [(float(point.x), float(point.y)) for point in path.flattening(distance=FLATTENING_DISTANCE)]


def iter_entity_paths(entity: DXFGraphic) -> Iterable[list[tuple[float, float]]]:
    entity_type = entity.dxftype()
    if entity_type in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
        try:
            points = path_to_points(entity)
        except TypeError:
            points = []
        if len(points) >= 2:
            yield points


def text_value(entity: DXFGraphic) -> str:
    if entity.dxftype() == "MTEXT":
        return entity.plain_text()
    return str(getattr(entity.dxf, "text", ""))


def iter_text_entities(entities: Iterable[DXFGraphic]) -> Iterable[DXFGraphic]:
    for entity in entities:
        if entity.dxftype() in {"TEXT", "MTEXT"} and text_value(entity).strip():
            yield entity


def collect_bounds(entities: Iterable[DXFGraphic]) -> Bounds:
    bounds = Bounds()
    for entity in entities:
        for path in iter_entity_paths(entity):
            for x, y in path:
                bounds.add_point(x, y)
        if entity.dxftype() in {"TEXT", "MTEXT"}:
            insert = entity.dxf.insert
            bounds.add_point(float(insert.x), float(insert.y))
    return bounds


def convert_point(x: float, y: float, bounds: Bounds, scale: float, page_height: float) -> fitz.Point:
    page_x = PAGE_MARGIN + (x - bounds.min_x) * scale
    page_y = page_height - PAGE_MARGIN - (y - bounds.min_y) * scale
    return fitz.Point(page_x, page_y)
