"""
Incremental PyPSA Model Builder

This module provides tools to build PyPSA networks incrementally,
allowing you to start with a blank model and progressively add components
while testing results at each step.
"""

import sys
import os
import logging
import pandas as pd
import numpy as np
from pathlib import Path

# Add pypsa-pl to path
sys.path.insert(0, str(Path(__file__).parent.parent / "pypsa-pl" / "src"))

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
from pypsa_pl.define_time_dependent_attributes import (
    define_time_dependent_attributes,
)
from pypsa_pl.optimise_network import optimise_network

from incremental_builder_utils import (
    filter_capacity_data,
    validate_network_state,
    generate_inspection_report,
)


class IncrementalBuilder:
    """
    Build PyPSA networks incrementally for learning and debugging.

    Attributes:
        params (dict): Model parameters
        inputs (dict): Input data from CSV files
        network: PyPSA Network object
        df_cap: Capacity dataframe
        df_attr_t: Time-dependent attributes
        stage_history (list): List of completed stages
    """

    def __init__(self, year=2025, timeseries='mini', copperplate=True,
                 custom_params=None, custom_input_operation=None):
        """
        Initialize the incremental builder.

        Args:
            year (int): Model year (2025, 2030, 2035, 2040)
            timeseries (str): Time resolution ('mini', 'medium', 'full')
            copperplate (bool): Single area (True) vs voivodeships (False)
            custom_params (dict): Additional parameters to override defaults
            custom_input_operation (callable): Custom function to modify inputs
        """
        self.year = year
        self.timeseries = timeseries
        self.copperplate = copperplate
        self.custom_input_operation = custom_input_operation

        # Initialize with minimal parameters
        self.params = self._create_minimal_params(custom_params)

        # Storage for network components
        self.network = None
        self.inputs = None
        self.df_cap = None
        self.df_attr_t = None
        self.stage_history = []

        # Storage for full capacity data (before filtering)
        self.df_cap_full = None

        logging.info(f"Initialized IncrementalBuilder: year={year}, "
                    f"timeseries={timeseries}, copperplate={copperplate}")

    def _create_minimal_params(self, custom_params=None):
        """Create minimal parameter set for model building."""

        # Determine scenario suffix
        suffix = "+copperplate" if self.copperplate else ""
        input_suffix = "" if self.copperplate else "_voivodeships"

        # Determine installed capacity variants based on year
        if self.year == 2024:
            installed_capacity = [f"historical_totals{input_suffix}"]
        else:
            installed_capacity = [f"historical+instrat_projection{input_suffix}"]

        # Add trade-related capacity if needed
        installed_capacity += [f"interconnectors{input_suffix}", "neighbours"]

        # Annual energy flows
        if self.year == 2024:
            annual_energy_flows = [f"historical{input_suffix}"]
        else:
            annual_energy_flows = [f"instrat_projection{input_suffix}", "constraints", "neighbours"]

        # Capacity utilisation
        if self.year == 2024:
            capacity_utilisation = ["historical"]
        else:
            capacity_utilisation = ["instrat_projection", "neighbours"]

        # Capacity addition potentials
        capacity_addition_potentials = [
            "instrat_projection",
            f"instrat_res_potentials{input_suffix}",
        ]
        # Only add voivodeship potentials if NOT copperplate
        if not self.copperplate:
            capacity_addition_potentials.append("instrat_other_potentials_voivodeships")

        # Minimal investment/retirement technologies for basic modeling
        investment_technologies = [
            # Allow grid components to adjust
            "distribution HMV",
            "transformation HMV-LV",
            "transformation LV-HMV",
            "distribution LV",
            "transformation EHV-HMV",
            "transformation HMV-EHV",
        ]

        retirement_technologies = [
            # Virtual components that must be present
            "centralised space heating",
            "centralised water heating",
            "centralised other heating",
            "decentralised space heating",
            "decentralised water heating",
            "light vehicle mobility",
            "hydrogen",
        ]

        # For years >= 2030, add more technologies
        if self.year >= 2030:
            investment_technologies += [
                "wind onshore", "wind offshore",
                "solar PV ground", "solar PV roof",
                "battery large storage", "battery large power", "battery large charger",
                "hydro PSH power", "hydro PSH pump", "hydro PSH storage",
                "natural gas power CCGT", "natural gas power peaker",
                "heat pump large AW", "heat pump small AW",
                "BEV", "BEV battery", "BEV charger",
                "hydrogen electrolysis", "hydrogen storage",
                "transmission line AC",
            ]
            retirement_technologies += [
                "hard coal power old", "hard coal power SC",
                "lignite power old", "lignite power SC",
            ]

        # Constrained energy flows
        constrained_energy_flows = [
            "space heating final use",
            "water heating final use",
            "other heating final use",
            "light vehicle mobility final use",
            "hydrogen final use",
            "biomass agriculture supply",
            "biogas substrate supply",
        ]

        # For copperplate, add more constrained flows
        if self.copperplate:
            constrained_energy_flows += [
                "natural gas final use",
                "hard coal final use",
                "biomass wood final use",
                "other fuel final use",
                "process emissions final use",
                "lulucf final use",
            ]

        params = {
            # Run identification
            "run_name": f"incremental_{self.year}_{self.timeseries}",
            "year": self.year,

            # Input data variants
            "technology_carrier_definitions": "full",
            "technology_cost_data": "instrat_2025",
            "installed_capacity": installed_capacity,
            "annual_energy_flows": annual_energy_flows,
            "capacity_utilisation": capacity_utilisation,
            "capacity_addition_potentials": capacity_addition_potentials,
            "timeseries": self.timeseries,

            # CO2 emissions
            "co2_emissions": 0 if self.year == 2050 else None,

            # Economic parameters
            "weather_year": 2012,
            "discount_rate": 0.045,
            "investment_cost_start_year": 2021,
            "invest_from_zero": True,
            "optimise_industrial_capacities": False,

            # Technologies
            "investment_technologies": investment_technologies,
            "retirement_technologies": retirement_technologies,
            "constrained_energy_flows": constrained_energy_flows,

            # CHP behavior
            "fix_public_chp": False,
            "fix_industrial_chp": True,
            "share_space_heating": None,

            # Electricity sector
            "prosumer_self_consumption": 0 if self.year > 2024 else 0.2,
            "p_min_synchronous": 0 if self.year < 2030 else (
                4500 if self.year == 2030 else
                2700 if self.year == 2035 else
                1800 if self.year == 2040 else 0
            ),
            "synchronous_carriers": [
                "hard coal power", "lignite power", "natural gas power",
                "natural gas power peaker", "biomass wood power", "nuclear power",
                "hydrogen power", "hard coal CHP", "natural gas CHP",
                "other CHP", "biomass wood CHP", "biomass agriculture CHP",
                "biomass agriculture CHP CC", "hydrogen CHP", "biogas CHP",
                "hydro ROR",
            ],
            "proportional_expansion": [
                "wind onshore", "wind offshore",
                "solar PV ground", "solar PV roof",
                "heat pump small", "BEV",
            ],

            # Heating sector
            "heat_capacity_utilisation": 0.2,
            "centralised_heating_shares": None,

            # Mobility sector
            "light_vehicle_mobility_utilisation": 0.021,
            "bev_flexibility_factor": 0.5,
            "bev_flexibility_max_to_mean_ratio": 1.33,
            "bev_flexible_share": 0.5,
            "bev_availability_max": 0.9,
            "bev_availability_mean": 0.7,
            "minimum_bev_charge_hour": 6,
            "minimum_bev_charge_level": 0,

            # Technical details
            "hydrogen_utilisation": 1,
            "space_heating_utilisation": 0.1,
            "water_heating_utilisation": 1,
            "other_heating_utilisation": 1,
            "inf": 999999,
            "reverse_links": True,  # Required by pypsa-pl custom constraints

            # Solver settings
            "solver": "highs",
            "solver_tolerance": 1e-5,
            "solver_options": {},
            "solver_extra_flags": [],
            "reoptimise_with_fixed_capacities": False,
        }

        # Override with custom params if provided
        if custom_params:
            params.update(custom_params)

        return params

    def load_inputs(self):
        """Load and preprocess all input data."""
        if self.inputs is not None:
            logging.info("Inputs already loaded, skipping...")
            return

        logging.info("Loading and preprocessing inputs...")
        self.inputs = load_and_preprocess_inputs(
            self.params,
            custom_operation=self.custom_input_operation
        )
        logging.info(f"Loaded {len(self.inputs)} input datasets")

    def build_base_model(self):
        """
        Stage 0: Create network structure without components.

        This creates:
        - Empty PyPSA network with custom attributes
        - Time snapshots
        - Energy carriers
        - Buses and areas

        But does NOT add any generators, links, lines, or stores yet.
        """
        logging.info("=" * 60)
        logging.info("STAGE 0: Building base model structure")
        logging.info("=" * 60)

        # Load inputs if not already loaded
        if self.inputs is None:
            self.load_inputs()

        # Create network
        logging.info("Creating custom network...")
        self.network = create_custom_network(self.params)

        # Add temporal dimension
        logging.info("Adding snapshots...")
        add_snapshots(self.network, self.params)

        # Add energy carriers
        logging.info("Adding carriers...")
        add_carriers(self.network, self.inputs, self.params)

        # Add buses and areas
        logging.info("Adding buses and areas...")
        add_buses_and_areas(self.network, self.inputs, self.params)

        # Process full capacity data (but don't add to network yet)
        logging.info("Processing capacity data...")
        self.df_cap_full = process_capacity_data(self.inputs, self.params)

        # Initialize with empty capacity data
        self.df_cap = pd.DataFrame()

        self.stage_history.append("base_model")

        logging.info("Base model structure created successfully!")
        self.inspect('summary')

    def add_components(self, component_type=None, filters=None, capacity_data=None):
        """
        Add specific components to the network based on filters.

        Args:
            component_type (str): 'Generator', 'Link', 'Line', or 'Store'.
                                 If None, adds all types matching filters.
            filters (dict): Filter criteria, e.g.:
                           {'technology': ['wind_onshore', 'solar_PV_ground'],
                            'area': ['PL'],
                            'carrier': ['electricity']}
            capacity_data (pd.DataFrame): Optional pre-filtered capacity data.
                                         If provided, filters are ignored.

        Returns:
            dict: Summary of components added
        """
        if self.network is None:
            raise RuntimeError("Must call build_base_model() first!")

        # Use provided capacity data or filter from full dataset
        if capacity_data is not None:
            df_cap_filtered = capacity_data
        elif filters is not None:
            df_cap_filtered = filter_capacity_data(self.df_cap_full, filters)
        else:
            raise ValueError("Must provide either filters or capacity_data")

        if len(df_cap_filtered) == 0:
            logging.warning("No components match the filters!")
            return {'added': 0}

        # Filter by component type if specified
        if component_type is not None:
            df_cap_filtered = df_cap_filtered[
                df_cap_filtered['component'] == component_type
            ]
            if len(df_cap_filtered) == 0:
                logging.warning(f"No {component_type} components match the filters!")
                return {'added': 0}

        # Append to existing capacity data
        self.df_cap = pd.concat([self.df_cap, df_cap_filtered], ignore_index=True)

        # Remove duplicates (if any)
        self.df_cap = self.df_cap.drop_duplicates(subset='name', keep='last')

        # Define time-dependent attributes
        logging.info("Defining time-dependent attributes...")
        self.df_attr_t = define_time_dependent_attributes(self.df_cap, self.params)

        # Add capacities to network
        logging.info(f"Adding {len(df_cap_filtered)} components to network...")
        add_capacities(self.network, self.df_cap, self.df_attr_t, self.params)

        # Summary
        summary = {
            'added': len(df_cap_filtered),
            'total_components': len(self.df_cap),
            'generators': len(self.network.generators),
            'links': len(self.network.links),
            'lines': len(self.network.lines),
            'stores': len(self.network.stores),
        }

        logging.info(f"Added {summary['added']} components. "
                    f"Network now has: {summary['generators']} generators, "
                    f"{summary['links']} links, {summary['lines']} lines, "
                    f"{summary['stores']} stores")

        return summary

    def add_constraints(self, constraint_type='all'):
        """
        Add constraints to the network.

        Args:
            constraint_type (str): 'energy_flow', 'capacity', or 'all'
        """
        if self.network is None:
            raise RuntimeError("Must call build_base_model() first!")

        logging.info("=" * 60)
        logging.info(f"Adding {constraint_type} constraints")
        logging.info("=" * 60)

        if constraint_type in ['energy_flow', 'all']:
            logging.info("Adding energy flow constraints...")
            add_energy_flow_constraints(self.network, self.inputs, self.params)

        if constraint_type in ['capacity', 'all']:
            logging.info("Adding capacity constraints...")
            add_capacity_constraints(self.network, self.inputs, self.params)

        self.stage_history.append(f"constraints_{constraint_type}")
        logging.info("Constraints added successfully!")

    def optimize(self, solver=None, solver_options=None):
        """
        Run optimization on the current network state.

        Args:
            solver (str): Solver to use (default: from params)
            solver_options (dict): Solver options (default: from params)

        Returns:
            bool: True if optimization succeeded, False otherwise
        """
        if self.network is None:
            raise RuntimeError("Must call build_base_model() first!")

        if len(self.network.generators) == 0:
            logging.error("Cannot optimize: network has no components!")
            return False

        logging.info("=" * 60)
        logging.info("Running optimization...")
        logging.info("=" * 60)

        # Override solver settings if provided
        if solver:
            self.params['solver'] = solver
        if solver_options:
            self.params['solver_options'] = solver_options

        # Create temporary directory for logs
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            networks = optimise_network(self.network, self.params, log_dir=lambda *x: os.path.join(tmpdir, *x))

            if len(networks) > 0:
                self.network = networks[-1]  # Use last network (fixed capacities if applicable)

        # Check solver status
        status = self.network.meta.get('solver_status', 'unknown')

        if status.startswith('ok'):
            logging.info(f"Optimization succeeded! Status: {status}")
            logging.info(f"Objective value: {self.network.objective:.2f}")
            self.stage_history.append('optimized')
            return True
        else:
            logging.error(f"Optimization failed! Status: {status}")
            return False

    def validate_stage(self, stage_name=None, validation_types=None):
        """
        Run validation checks on current network state.

        Args:
            stage_name (str): Name of current stage (for logging)
            validation_types (list): Types of validation to run
                                    ['structure', 'balance', 'connectivity', 'feasibility']
                                    Default: all

        Returns:
            dict: Validation results
        """
        if self.network is None:
            return {'error': 'No network to validate'}

        if validation_types is None:
            validation_types = ['structure', 'balance']

        results = {}
        for vtype in validation_types:
            results[vtype] = validate_network_state(self.network, vtype)

        # Print results
        if stage_name:
            logging.info(f"\nValidation results for stage '{stage_name}':")
        else:
            logging.info("\nValidation results:")

        for vtype, result in results.items():
            logging.info(f"  {vtype}: {result['status']}")
            if result.get('warnings'):
                for warning in result['warnings']:
                    logging.warning(f"    - {warning}")

        return results

    def inspect(self, aspect='summary'):
        """
        Inspect current network state and print report.

        Args:
            aspect (str): What to inspect
                         'summary': Component counts and basic info
                         'detailed': Detailed breakdown by technology
                         'balance': Supply/demand analysis
                         'optimization': Optimization results
                         'all': All of the above
        """
        if self.network is None:
            logging.info("No network created yet. Call build_base_model() first.")
            return

        report = generate_inspection_report(self.network, aspect, self.params)
        print(report)

    def save_checkpoint(self, name):
        """
        Save current network state to checkpoint.

        Args:
            name (str): Checkpoint name
        """
        if self.network is None:
            raise RuntimeError("No network to save!")

        checkpoint_dir = Path(__file__).parent / "checkpoints" / name
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Export network to CSV
        self.network.export_to_csv_folder(str(checkpoint_dir / "network"))

        # Save capacity data
        self.df_cap.to_csv(checkpoint_dir / "capacity_data.csv", index=False)

        # Save time-dependent attributes
        if self.df_attr_t is not None and len(self.df_attr_t) > 0:
            self.df_attr_t.to_csv(checkpoint_dir / "time_attributes.csv")

        # Save stage history
        with open(checkpoint_dir / "stage_history.txt", 'w') as f:
            f.write('\n'.join(self.stage_history))

        logging.info(f"Checkpoint saved to: {checkpoint_dir}")

    def load_checkpoint(self, name):
        """
        Load network state from checkpoint.

        Args:
            name (str): Checkpoint name
        """
        checkpoint_dir = Path(__file__).parent / "checkpoints" / name

        if not checkpoint_dir.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_dir}")

        # Import network from CSV
        import pypsa
        self.network = pypsa.Network()
        self.network.import_from_csv_folder(str(checkpoint_dir / "network"))

        # Load capacity data
        self.df_cap = pd.read_csv(checkpoint_dir / "capacity_data.csv")

        # Load time-dependent attributes
        attr_file = checkpoint_dir / "time_attributes.csv"
        if attr_file.exists():
            self.df_attr_t = pd.read_csv(attr_file, index_col=0)

        # Load stage history
        history_file = checkpoint_dir / "stage_history.txt"
        if history_file.exists():
            with open(history_file, 'r') as f:
                self.stage_history = [line.strip() for line in f.readlines()]

        logging.info(f"Checkpoint loaded from: {checkpoint_dir}")
        logging.info(f"Stage history: {self.stage_history}")


# Convenience function for quick start
def create_minimal_builder(year=2025):
    """
    Create a minimal builder with sensible defaults for quick experimentation.

    Args:
        year (int): Model year

    Returns:
        IncrementalBuilder: Initialized builder with base model
    """
    builder = IncrementalBuilder(year=year, timeseries='mini', copperplate=True)
    builder.build_base_model()
    return builder


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.INFO)

    print("\n" + "=" * 60)
    print("Testing Incremental Builder")
    print("=" * 60 + "\n")

    # Create minimal builder
    builder = create_minimal_builder(year=2025)

    print("\nBase model created successfully!")
    print("Next steps:")
    print("  1. builder.add_components('Generator', {'technology': ['hard_coal_power_old']})")
    print("  2. builder.add_components('Generator', {'carrier': ['electricity_final_use']})")
    print("  3. builder.optimize()")
    print("  4. builder.inspect('all')")
