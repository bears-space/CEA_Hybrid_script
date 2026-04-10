"""Axial mesh definitions for the quasi-1D hybrid internal ballistics model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.sizing.geometry_types import GeometryDefinition


@dataclass(frozen=True)
class AxialMesh:
    cell_edges_m: np.ndarray
    cell_centers_m: np.ndarray
    cell_lengths_m: np.ndarray
    prechamber_length_m: float
    grain_length_m: float
    postchamber_length_m: float

    @property
    def cell_count(self) -> int:
        return int(self.cell_centers_m.size)


def build_axial_mesh(geometry: GeometryDefinition, cell_count: int) -> AxialMesh:
    if int(cell_count) < 2:
        raise ValueError("Axial mesh requires at least two cells.")
    cell_edges_m = np.linspace(0.0, float(geometry.grain_length_m), int(cell_count) + 1, dtype=float)
    cell_centers_m = 0.5 * (cell_edges_m[:-1] + cell_edges_m[1:])
    cell_lengths_m = np.diff(cell_edges_m)
    return AxialMesh(
        cell_edges_m=cell_edges_m,
        cell_centers_m=cell_centers_m,
        cell_lengths_m=cell_lengths_m,
        prechamber_length_m=float(geometry.prechamber_length_m),
        grain_length_m=float(geometry.grain_length_m),
        postchamber_length_m=float(geometry.postchamber_length_m),
    )
