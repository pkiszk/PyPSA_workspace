from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure pypsa_pl is importable when running from repo root
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYPSA_PL_SRC = _REPO_ROOT / "pypsa-pl" / "src"
if _PYPSA_PL_SRC.exists():
    import sys

    sys.path.insert(0, str(_PYPSA_PL_SRC))

from pypsa_pl.build_network import (
    load_and_preprocess_inputs,
    create_custom_network,
    add_snapshots,
    add_carriers,
    add_buses_and_areas,
    process_capacity_data,
    add_capacities,
    add_energy_flow_constraints,
    add_capacity_constraints,
)
from pypsa_pl.define_time_dependent_attributes import define_time_dependent_attributes
from pypsa_pl.optimise_network import optimise_network

from incremental_builder_utils import (
    filter_capacity_data,
    generate_inspection_report,
    validate_network_state,
)


def build_default_params(
    *,
    year: int = 2025,
    timeseries: str = "mini",
    copperplate: bool = True,
    trade: bool = True,
    scenario_base: str = "instrat_ambitious+trade",
    weather_year: int = 2012,
) -> Dict[str, Any]:
    input_suffix = "" if copperplate else "_voivodeships"

    scenario = scenario_base
    if copperplate and "copperplate" not in scenario:
        scenario = f"{scenario}+copperplate"
    if not copperplate and "copperplate" in scenario:
        scenario = scenario.replace("+copperplate", "")

    installed_capacity = [f"historical+instrat_projection{input_suffix}"]
    annual_energy_flows = [f"instrat_projection{input_suffix}", "constraints"]
    capacity_utilisation = ["instrat_projection"]
    capacity_addition_potentials = [
        "instrat_projection",
        f"instrat_res_potentials{input_suffix}",
    ]
    if not copperplate:
        capacity_addition_potentials += ["instrat_other_potentials_voivodeships"]

    if trade:
        installed_capacity += [f"interconnectors{input_suffix}", "neighbours"]
        annual_energy_flows += ["neighbours"]
        capacity_utilisation += ["neighbours"]

    if year > 2025:
        installed_capacity = [scenario]

    investment_technologies = [
        "distribution HMV",
        "transformation HMV-LV",
        "transformation LV-HMV",
        "distribution LV",
        "transformation EHV-HMV",
        "transformation HMV-EHV",
    ]
    retirement_technologies = [
        "centralised space heating",
        "centralised water heating",
        "centralised other heating",
        "decentralised space heating",
        "decentralised water heating",
        "light vehicle mobility",
        "hydrogen",
    ]

    if year < 2030:
        investment_technologies += ["ICE vehicle", "natural gas boiler"]
        retirement_technologies += ["ICE vehicle", "natural gas boiler"]

    params = {
        "run_name": f"pypsa_pl;scenario={scenario};year={year}",
        "year": year,
        "technology_carrier_definitions": "full",
        "technology_cost_data": "instrat_2025",
        "installed_capacity": installed_capacity,
        "annual_energy_flows": annual_energy_flows,
        "capacity_utilisation": capacity_utilisation,
        "capacity_addition_potentials": capacity_addition_potentials,
        "timeseries": timeseries,
        "co2_emissions": 0 if year == 2050 else None,
        "weather_year": weather_year,
        "discount_rate": 0.045,
        "investment_cost_start_year": 2021,
        "invest_from_zero": True,
        "optimise_industrial_capacities": False,
        "investment_technologies": investment_technologies,
        "retirement_technologies": retirement_technologies,
        "constrained_energy_flows": "none",
        "reoptimise_with_fixed_capacities": False,
        "fix_public_chp": False,
        "fix_industrial_chp": True,
        "share_space_heating": None,
        "prosumer_self_consumption": 0,
        "p_min_synchronous": 0,
        "synchronous_carriers": [],
        "proportional_expansion": [],
        "heat_capacity_utilisation": 0.2,
        "centralised_heating_shares": None,
        "light_vehicle_mobility_utilisation": 0.021,
        "bev_flexibility_factor": 0.5,
        "bev_flexibility_max_to_mean_ratio": 1.33,
        "bev_flexible_share": 0.5,
        "bev_availability_max": 0.9,
        "bev_availability_mean": 0.7,
        "minimum_bev_charge_hour": 6,
        "minimum_bev_charge_level": 0,
        "hydrogen_utilisation": 1,
        "space_heating_utilisation": 0.1,
        "water_heating_utilisation": 1,
        "other_heating_utilisation": 1,
        "inf": 999999,
        "reverse_links": True,
        "solver": "highs",
        "solver_tolerance": 1e-5,
        "solver_extra_flags": [],
    }
    return params


def _load_config(path: Path) -> Dict[str, Any]:
    if path.suffix.lower() in {".json"}:
        return json.loads(path.read_text())

    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "YAML config requested but PyYAML is not installed. "
                "Install it or use JSON config instead."
            ) from exc
        return yaml.safe_load(path.read_text())

    raise ValueError(f"Unsupported config extension: {path.suffix}")


def _merge_params(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            continue
        merged[key] = value
    return merged


class IncrementalBuilder:
    def __init__(
        self,
        params: Dict[str, Any],
        *,
        custom_input_operation=None,
        work_dir: Optional[Path] = None,
    ):
        self.params = params
        self.custom_input_operation = custom_input_operation
        self.work_dir = work_dir or Path(__file__).resolve().parent / "runs"
        self.inputs: Optional[Dict[str, Any]] = None
        self.network = None

    @classmethod
    def from_config(cls, config_path: str | Path) -> "IncrementalBuilder":
        config_path = Path(config_path)
        config = _load_config(config_path)

        base_cfg = config.get("base_model", {})
        params_override = config.get("params_override", {})

        params = build_default_params(
            year=base_cfg.get("year", 2025),
            timeseries=base_cfg.get("timeseries", "mini"),
            copperplate=base_cfg.get("copperplate", True),
            trade=base_cfg.get("trade", True),
            scenario_base=base_cfg.get("scenario_base", "instrat_ambitious+trade"),
            weather_year=base_cfg.get("weather_year", 2012),
        )
        params = _merge_params(params, base_cfg.get("params_override", {}))
        params = _merge_params(params, params_override)

        builder = cls(params)
        builder.config = config
        return builder

    def load_inputs(self):
        if self.inputs is None:
            self.inputs = load_and_preprocess_inputs(
                self.params, custom_operation=self.custom_input_operation
            )
        return self.inputs

    def build_base_model(self):
        self.load_inputs()
        self.network = create_custom_network(self.params)
        add_snapshots(self.network, self.params)
        add_carriers(self.network, self.inputs, self.params)
        add_buses_and_areas(self.network, self.inputs, self.params)
        return self.network

    def add_components(
        self,
        component_type: Optional[str | list[str]] = None,
        *,
        filters: Optional[Dict[str, Any]] = None,
        drop_existing: bool = True,
    ):
        if self.network is None:
            raise RuntimeError("Call build_base_model() before adding components")

        inputs = self.load_inputs()
        df_cap_filtered = filter_capacity_data(inputs, filters or {})

        local_inputs = dict(inputs)
        local_inputs["installed_capacity"] = df_cap_filtered
        df_cap = process_capacity_data(local_inputs, self.params)

        if component_type is not None:
            components = (
                [component_type]
                if isinstance(component_type, str)
                else list(component_type)
            )
            df_cap = df_cap[df_cap["component"].isin(components)]

        if df_cap.empty:
            logging.warning("No capacities matched filters; nothing added")
            return

        if drop_existing:
            existing = set()
            for comp in df_cap["component"].unique():
                existing.update(self.network.static(comp).index)
            df_cap = df_cap[~df_cap["name"].isin(existing)]

        if df_cap.empty:
            logging.warning("All matched capacities already exist in the network")
            return

        df_attr_t = define_time_dependent_attributes(df_cap, self.params)
        add_capacities(self.network, df_cap, df_attr_t, self.params)

    def add_constraints(self, *, energy_flow: bool = True, capacity: bool = True):
        if self.network is None:
            raise RuntimeError("Call build_base_model() before adding constraints")
        inputs = self.load_inputs()
        if energy_flow:
            add_energy_flow_constraints(self.network, inputs, self.params)
        if capacity:
            add_capacity_constraints(self.network, inputs, self.params)

    def validate_stage(self, stage_name: str, check_type: str = "all"):
        if self.network is None:
            raise RuntimeError("No network to validate")
        warnings = validate_network_state(self.network, check_type=check_type)
        if warnings:
            logging.warning("Stage '%s' validation warnings: %s", stage_name, warnings)
        return warnings

    def inspect(self, detail: str = "summary") -> str:
        if self.network is None:
            raise RuntimeError("No network to inspect")
        report = generate_inspection_report(self.network, detail=detail)
        return report

    def optimize(self):
        if self.network is None:
            raise RuntimeError("No network to optimize")
        run_dir = lambda *p: self.work_dir / self.params["run_name"] / Path(*p)
        os.makedirs(run_dir(), exist_ok=True)
        networks = optimise_network(self.network, self.params, log_dir=run_dir)

        if len(networks) == 1:
            networks[0].export_to_csv_folder(run_dir("output_network"))
            self.network = networks[0]
        elif len(networks) == 2:
            networks[0].export_to_csv_folder(run_dir("output_network_non_fixed"))
            networks[1].export_to_csv_folder(run_dir("output_network"))
            self.network = networks[1]

        return self.network

    def save_checkpoint(self, name: str, *, base_dir: Optional[Path] = None):
        if self.network is None:
            raise RuntimeError("No network to save")
        base_dir = base_dir or Path(__file__).resolve().parent / "checkpoints"
        path = base_dir / name
        os.makedirs(path, exist_ok=True)
        self.network.export_to_csv_folder(path)
        return path

    def load_checkpoint(self, name: str, *, base_dir: Optional[Path] = None):
        base_dir = base_dir or Path(__file__).resolve().parent / "checkpoints"
        path = base_dir / name
        if not path.exists():
            raise FileNotFoundError(path)
        self.network = create_custom_network(self.params)
        self.network.import_from_csv_folder(path)
        return self.network

    def build_all_stages(self):
        if not hasattr(self, "config"):
            raise RuntimeError("Builder has no config loaded")

        self.build_base_model()

        stages = self.config.get("stages", {})
        for stage_name, stage_cfg in stages.items():
            if not stage_cfg or not stage_cfg.get("enabled", False):
                continue

            filters = dict(stage_cfg.get("filters", {}))
            mapping = {
                "technologies": "technology",
                "carriers": "carrier",
                "areas": "area",
                "qualifiers": "qualifier",
                "components": "component",
            }
            for key, target in mapping.items():
                if key in stage_cfg:
                    filters[target] = stage_cfg[key]

            component_type = stage_cfg.get("component")
            if component_type is None and "components" in stage_cfg:
                component_type = stage_cfg["components"]

            self.add_components(component_type, filters=filters)
            self.validate_stage(stage_name, check_type=stage_cfg.get("validate", "all"))

        constraints_cfg = self.config.get("constraints", {})
        if constraints_cfg.get("enabled", False):
            self.add_constraints(
                energy_flow=constraints_cfg.get("energy_flow", True),
                capacity=constraints_cfg.get("capacity", True),
            )

        opt_cfg = self.config.get("optimization", {})
        if opt_cfg.get("enabled", False):
            overrides = opt_cfg.get("params_override", {})
            if overrides:
                self.params = _merge_params(self.params, overrides)
            self.optimize()


def main():
    parser = argparse.ArgumentParser(description="Incremental PyPSA-PL builder")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML/JSON config",
    )
    parser.add_argument(
        "--inspect",
        default="summary",
        help="Inspection level: summary, balance, detailed, optimization, all",
    )
    args = parser.parse_args()

    builder = IncrementalBuilder.from_config(args.config)
    builder.build_all_stages()

    report = builder.inspect(args.inspect)
    print(report)


if __name__ == "__main__":
    main()
