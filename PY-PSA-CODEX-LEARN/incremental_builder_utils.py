from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import logging
import numpy as np
import pandas as pd


class FilterError(ValueError):
    pass


def _ensure_list(value: Any) -> Optional[List[Any]]:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def apply_filters(df: pd.DataFrame, filters: Optional[Dict[str, Any]]) -> pd.DataFrame:
    if not filters:
        return df

    filtered = df
    for key, values in filters.items():
        if values is None:
            continue
        if key not in filtered.columns:
            raise FilterError(
                f"Filter key '{key}' not in columns. Available: {sorted(filtered.columns)}"
            )

        if isinstance(values, dict) and (
            "min" in values or "max" in values or "equals" in values
        ):
            if "equals" in values:
                filtered = filtered[filtered[key] == values["equals"]]
                continue
            min_v = values.get("min", -np.inf)
            max_v = values.get("max", np.inf)
            filtered = filtered[(filtered[key] >= min_v) & (filtered[key] <= max_v)]
        else:
            vals = _ensure_list(values)
            filtered = filtered[filtered[key].isin(vals)]

    return filtered


def filter_capacity_data(inputs: Dict[str, pd.DataFrame], filters: Dict[str, Any]):
    df_cap = inputs["installed_capacity"].copy()
    if not filters:
        return df_cap

    df_carr = inputs["technology_carrier_definitions"][
        [
            "technology",
            "carrier",
            "component",
            "aggregation",
            "bus_carrier",
            "input_carrier",
            "output_carrier",
            "output2_carrier",
        ]
    ]

    df = df_cap.merge(df_carr, on="technology", how="left")
    df = apply_filters(df, filters)

    return df[df_cap.columns].reset_index(drop=True)


def _connected_buses(network) -> set:
    buses = set()
    for component, cols in [
        ("Generator", ["bus"]),
        ("Link", ["bus0", "bus1", "bus2"]),
        ("Line", ["bus0", "bus1"]),
        ("Store", ["bus"]),
    ]:
        df = network.static(component)
        if df.empty:
            continue
        for col in cols:
            if col in df.columns:
                buses.update(df[col].dropna().astype(str).tolist())
    buses.discard("")
    return buses


def validate_network_state(network, check_type: str = "all") -> List[str]:
    warnings: List[str] = []
    check_type = check_type.lower()

    if check_type in ("structure", "all"):
        if network.buses.empty:
            warnings.append("No buses defined")
        if network.carriers.empty:
            warnings.append("No carriers defined")
        if len(network.snapshots) == 0:
            warnings.append("No snapshots defined")

    if check_type in ("balance", "all"):
        if not network.generators.empty:
            gen = network.generators
            pos_cap = gen.loc[gen["sign"] > 0, "p_nom"].sum()
            neg_cap = -gen.loc[gen["sign"] < 0, "p_nom"].sum()
            if neg_cap > 0:
                ratio = pos_cap / neg_cap if neg_cap else np.inf
                if ratio < 0.8:
                    warnings.append(
                        f"Low generation capacity vs demand ({ratio:.1%})"
                    )
                elif ratio > 2.0:
                    warnings.append(
                        f"High generation capacity vs demand ({ratio:.1%})"
                    )

    if check_type in ("connectivity", "all"):
        connected = _connected_buses(network)
        if connected:
            missing = set(network.buses.index) - connected
            if missing:
                warnings.append(
                    f"{len(missing)} buses have no connected components"
                )

    if check_type in ("feasibility", "all"):
        solver_status = network.meta.get("solver_status")
        if solver_status and not solver_status.startswith("ok"):
            warnings.append(f"Solver status not ok: {solver_status}")

    return warnings


def _weighted_sum(df: pd.DataFrame, weights: pd.Series) -> float:
    aligned = df.mul(weights, axis=0)
    return aligned.sum().sum()


def generate_inspection_report(network, detail: str = "summary") -> str:
    detail = detail.lower()
    lines: List[str] = []

    if detail in ("summary", "all"):
        lines.append("Network summary")
        lines.append(f"  buses: {len(network.buses)}")
        lines.append(f"  carriers: {len(network.carriers)}")
        lines.append(f"  snapshots: {len(network.snapshots)}")
        lines.append(f"  generators: {len(network.generators)}")
        lines.append(f"  links: {len(network.links)}")
        lines.append(f"  lines: {len(network.lines)}")
        lines.append(f"  stores: {len(network.stores)}")
        lines.append(f"  global_constraints: {len(network.global_constraints)}")

    if detail in ("balance", "all") and not network.generators.empty:
        gen = network.generators
        pos_cap = gen.loc[gen["sign"] > 0, "p_nom"].sum()
        neg_cap = -gen.loc[gen["sign"] < 0, "p_nom"].sum()
        lines.append("Capacity balance")
        lines.append(f"  generation p_nom (MW): {pos_cap:,.2f}")
        lines.append(f"  demand p_nom (MW): {neg_cap:,.2f}")

    if detail in ("detailed", "all"):
        if not network.generators.empty:
            gen = (
                network.generators
                .assign(sign=lambda df: df["sign"].map({1: "supply", -1: "demand"}))
                .groupby(["carrier", "sign"], dropna=False)["p_nom"]
                .sum()
                .sort_values(ascending=False)
            )
            lines.append("Generators by carrier")
            for (carrier, sign), value in gen.items():
                lines.append(f"  {carrier} ({sign}): {value:,.2f} MW")

        if not network.links.empty:
            link = (
                network.links.groupby("carrier", dropna=False)["p_nom"]
                .sum()
                .sort_values(ascending=False)
            )
            lines.append("Links by carrier")
            for carrier, value in link.items():
                lines.append(f"  {carrier}: {value:,.2f} MW")

        if not network.stores.empty:
            store = (
                network.stores.groupby("carrier", dropna=False)["e_nom"]
                .sum()
                .sort_values(ascending=False)
            )
            lines.append("Stores by carrier")
            for carrier, value in store.items():
                lines.append(f"  {carrier}: {value:,.2f} MWh")

    if detail in ("optimization", "all"):
        solver_status = network.meta.get("solver_status", "unknown")
        lines.append("Optimization")
        lines.append(f"  solver_status: {solver_status}")
        objective = getattr(network, "objective", None)
        if objective is not None:
            lines.append(f"  objective: {objective:,.4f}")

        if hasattr(network, "generators_t") and not network.generators_t.p.empty:
            weights = network.snapshot_weightings["generators"]
            gen_energy = _weighted_sum(network.generators_t.p, weights)
            lines.append(f"  total generator energy (MWh): {gen_energy:,.2f}")

        if hasattr(network, "links_t") and not network.links_t.p0.empty:
            weights = network.snapshot_weightings["generators"]
            sign = -1 if network.meta.get("reverse_links", True) else 1
            link_energy = _weighted_sum(network.links_t.p0 * sign, weights)
            lines.append(f"  total link energy at bus0 (MWh): {link_energy:,.2f}")

    return "\n".join(lines)
