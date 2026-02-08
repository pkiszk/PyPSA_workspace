"""
Utility functions for incremental PyPSA model building.

This module provides filtering, validation, and inspection utilities.
"""

import pandas as pd
import numpy as np
import logging


def filter_capacity_data(df_cap, filters):
    """
    Filter capacity data based on criteria.

    Args:
        df_cap (pd.DataFrame): Full capacity dataframe
        filters (dict): Filter criteria with keys like:
                       - 'technology': list of technology names
                       - 'area': list of area names
                       - 'carrier': list of carrier names
                       - 'component': list of component types ('Generator', 'Link', etc.)
                       - 'qualifier': list of qualifiers
                       - 'build_year': [min, max] or single year

    Returns:
        pd.DataFrame: Filtered capacity dataframe

    Examples:
        # Filter for wind and solar only
        filter_capacity_data(df, {'technology': ['wind_onshore', 'solar_PV_ground']})

        # Filter for PL area generators
        filter_capacity_data(df, {'area': ['PL'], 'component': ['Generator']})

        # Filter for electricity final use
        filter_capacity_data(df, {'carrier': ['electricity_final_use']})
    """
    df_filtered = df_cap.copy()

    # Filter by technology
    if 'technology' in filters:
        tech_list = filters['technology']
        if isinstance(tech_list, str):
            tech_list = [tech_list]
        # Use partial matching for technology names
        mask = df_filtered['technology'].apply(
            lambda x: any(tech in x for tech in tech_list)
        )
        df_filtered = df_filtered[mask]

    # Filter by area
    if 'area' in filters:
        area_list = filters['area']
        if isinstance(area_list, str):
            area_list = [area_list]
        df_filtered = df_filtered[df_filtered['area'].isin(area_list)]

    # Filter by carrier
    if 'carrier' in filters:
        carrier_list = filters['carrier']
        if isinstance(carrier_list, str):
            carrier_list = [carrier_list]
        # Use partial matching for carrier names
        mask = df_filtered['carrier'].apply(
            lambda x: any(carrier in x for carrier in carrier_list)
        )
        df_filtered = df_filtered[mask]

    # Filter by component type
    if 'component' in filters:
        comp_list = filters['component']
        if isinstance(comp_list, str):
            comp_list = [comp_list]
        df_filtered = df_filtered[df_filtered['component'].isin(comp_list)]

    # Filter by qualifier
    if 'qualifier' in filters:
        qual_list = filters['qualifier']
        if isinstance(qual_list, str):
            qual_list = [qual_list]
        df_filtered = df_filtered[df_filtered['qualifier'].isin(qual_list)]

    # Filter by build year
    if 'build_year' in filters:
        year_filter = filters['build_year']
        if isinstance(year_filter, (int, float)):
            # Single year
            df_filtered = df_filtered[df_filtered['build_year'] == year_filter]
        elif isinstance(year_filter, (list, tuple)) and len(year_filter) == 2:
            # Year range [min, max]
            min_year, max_year = year_filter
            df_filtered = df_filtered[
                (df_filtered['build_year'] >= min_year) &
                (df_filtered['build_year'] <= max_year)
            ]

    return df_filtered


def validate_network_state(network, validation_type='balance'):
    """
    Validate network and return results.

    Args:
        network: PyPSA Network object
        validation_type (str): Type of validation:
                              - 'structure': Check basic structure
                              - 'balance': Check supply/demand balance
                              - 'connectivity': Check network connectivity
                              - 'feasibility': Quick feasibility checks

    Returns:
        dict: Validation results with 'status' and 'warnings' keys
    """
    result = {
        'status': 'ok',
        'warnings': [],
        'info': {}
    }

    if validation_type == 'structure':
        # Check basic structure
        if len(network.buses) == 0:
            result['status'] = 'error'
            result['warnings'].append("No buses in network")

        if len(network.carriers) == 0:
            result['status'] = 'error'
            result['warnings'].append("No carriers in network")

        if len(network.snapshots) == 0:
            result['status'] = 'error'
            result['warnings'].append("No snapshots in network")

        result['info'] = {
            'buses': len(network.buses),
            'carriers': len(network.carriers),
            'snapshots': len(network.snapshots),
        }

    elif validation_type == 'balance':
        # Check supply/demand balance
        # Note: In this model, supply comes from both Generators and Links (thermal plants)
        if len(network.generators) == 0 and len(network.links) == 0:
            result['warnings'].append("No generators or links in network")
            return result

        # Calculate supply from positive generators (renewables, nuclear, supply)
        total_supply = 0
        if len(network.generators) > 0:
            supply_gens = network.generators[network.generators.sign > 0]
            total_supply += supply_gens.p_nom.sum()

        # Add supply from links (thermal plants convert fuel → electricity)
        if len(network.links) > 0:
            # Check correct bus based on reverse_links setting
            reverse_links = network.meta.get('reverse_links', False)
            elec_bus_attr = 'bus0' if reverse_links else 'bus1'
            supply_links = network.links[
                network.links[elec_bus_attr].str.contains('electricity', na=False)
            ]
            total_supply += supply_links.p_nom.sum()

        # Calculate demand from negative generators (final use)
        total_demand = 0
        if len(network.generators) > 0:
            demand_gens = network.generators[network.generators.sign < 0]
            # Use actual demand from p_set timeseries (peak across all timesteps)
            # instead of p_nom which contains placeholder values (999999)
            if len(demand_gens) > 0 and hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_set'):
                demand_timeseries = network.generators_t.p_set[demand_gens.index]
                # Sum the peak demand across all demand generators
                total_demand = abs(demand_timeseries.max().sum())
            else:
                # Fallback: if no timeseries, filter out placeholder values
                p_nom_values = demand_gens.p_nom
                # If p_nom is unrealistically high (>100k), assume it's a placeholder
                if (p_nom_values > 100000).any():
                    total_demand = 0  # Can't determine demand without timeseries
                else:
                    total_demand = abs(p_nom_values.sum())

        result['info'] = {
            'supply_capacity_MW': total_supply,
            'demand_capacity_MW': total_demand,
            'balance_ratio': total_supply / total_demand if total_demand > 0 else np.inf
        }

        if total_demand == 0:
            result['warnings'].append("No demand in network")
        elif total_supply == 0:
            result['warnings'].append("No supply in network")
        else:
            balance_ratio = total_supply / total_demand

            if balance_ratio < 0.5:
                result['status'] = 'warning'
                result['warnings'].append(
                    f"Severe supply deficit: only {balance_ratio:.1%} of demand can be met"
                )
            elif balance_ratio < 0.8:
                result['status'] = 'warning'
                result['warnings'].append(
                    f"Supply deficit: {balance_ratio:.1%} of demand capacity available"
                )
            elif balance_ratio > 2.5:
                result['status'] = 'warning'
                result['warnings'].append(
                    f"Excess supply: {balance_ratio:.1%} of demand capacity"
                )

    elif validation_type == 'connectivity':
        # Check if network is connected
        # This is a simplified check
        if len(network.buses) == 0:
            result['warnings'].append("No buses to check connectivity")
            return result

        if len(network.lines) == 0 and len(network.links) == 0:
            result['warnings'].append("No transmission lines or links in network")

        # Count isolated buses (buses with no connections)
        connected_buses = set()
        for line in network.lines.index:
            connected_buses.add(network.lines.loc[line, 'bus0'])
            connected_buses.add(network.lines.loc[line, 'bus1'])
        for link in network.links.index:
            connected_buses.add(network.links.loc[link, 'bus0'])
            connected_buses.add(network.links.loc[link, 'bus1'])

        isolated_buses = len(network.buses) - len(connected_buses)
        if isolated_buses > 0:
            result['warnings'].append(
                f"{isolated_buses} buses have no connections"
            )

        result['info'] = {
            'total_buses': len(network.buses),
            'connected_buses': len(connected_buses),
            'isolated_buses': isolated_buses,
        }

    elif validation_type == 'feasibility':
        # Quick feasibility checks
        if len(network.generators) == 0:
            result['status'] = 'error'
            result['warnings'].append("Cannot check feasibility: no generators")
            return result

        # Check for negative capacities
        if (network.generators.p_nom < 0).any():
            result['status'] = 'error'
            result['warnings'].append("Negative generator capacities detected")

        # Check for NaN values
        if network.generators.p_nom.isna().any():
            result['status'] = 'error'
            result['warnings'].append("NaN generator capacities detected")

        # Check if any generators can actually produce
        if hasattr(network.generators_t, 'p_max_pu'):
            max_generation = (network.generators.p_nom *
                            network.generators_t.p_max_pu.max()).sum()
            if max_generation == 0:
                result['status'] = 'warning'
                result['warnings'].append("No generators can produce power (p_max_pu all zero)")

    return result


def generate_inspection_report(network, aspect='summary', params=None):
    """
    Generate human-readable report of network state.

    Args:
        network: PyPSA Network object
        aspect (str): What to report on:
                     - 'summary': Basic component counts
                     - 'detailed': Per-technology breakdown
                     - 'balance': Supply/demand analysis
                     - 'optimization': Optimization results
                     - 'all': All of the above
        params (dict): Model parameters (optional)

    Returns:
        str: Formatted report text
    """
    lines = []

    def add_section(title):
        lines.append("\n" + "=" * 60)
        lines.append(title)
        lines.append("=" * 60)

    def add_subsection(title):
        lines.append("\n" + title)
        lines.append("-" * len(title))

    if aspect in ['summary', 'all']:
        add_section("NETWORK SUMMARY")

        lines.append(f"Network components:")
        lines.append(f"  Areas:      {len(network.areas) if hasattr(network, 'areas') else 0}")
        lines.append(f"  Buses:      {len(network.buses)}")
        lines.append(f"  Carriers:   {len(network.carriers)}")
        lines.append(f"  Snapshots:  {len(network.snapshots)}")
        lines.append(f"  Generators: {len(network.generators)}")
        lines.append(f"  Links:      {len(network.links)}")
        lines.append(f"  Lines:      {len(network.lines)}")
        lines.append(f"  Stores:     {len(network.stores)}")

        if hasattr(network, 'global_constraints'):
            lines.append(f"  Global constraints: {len(network.global_constraints)}")

    if aspect in ['detailed', 'all']:
        add_section("DETAILED BREAKDOWN")

        if len(network.generators) > 0:
            add_subsection("Generators by Technology")
            gen_by_tech = network.generators.groupby('technology').agg({
                'p_nom': ['count', 'sum']
            }).round(2)
            gen_by_tech.columns = ['Count', 'Total Capacity (MW)']
            for tech, row in gen_by_tech.iterrows():
                lines.append(f"  {tech:40s}: {row['Count']:3.0f} units, {row['Total Capacity (MW)']:10.2f} MW")

        if len(network.links) > 0:
            add_subsection("Links by Technology")
            link_by_tech = network.links.groupby('technology').agg({
                'p_nom': ['count', 'sum']
            }).round(2)
            link_by_tech.columns = ['Count', 'Total Capacity (MW)']
            for tech, row in link_by_tech.iterrows():
                lines.append(f"  {tech:40s}: {row['Count']:3.0f} units, {row['Total Capacity (MW)']:10.2f} MW")

        if len(network.stores) > 0:
            add_subsection("Stores by Technology")
            store_by_tech = network.stores.groupby('technology').agg({
                'e_nom': ['count', 'sum']
            }).round(2)
            store_by_tech.columns = ['Count', 'Total Energy (MWh)']
            for tech, row in store_by_tech.iterrows():
                lines.append(f"  {tech:40s}: {row['Count']:3.0f} units, {row['Total Energy (MWh)']:10.2f} MWh")

    if aspect in ['balance', 'all']:
        add_section("SUPPLY/DEMAND BALANCE")

        # Calculate total supply from generators + links
        total_supply = 0
        supply_from_gens = 0
        supply_from_links = 0

        if len(network.generators) > 0:
            supply_gens = network.generators[network.generators.sign > 0]
            supply_from_gens = supply_gens.p_nom.sum()
            total_supply += supply_from_gens

        if len(network.links) > 0:
            # Links that produce electricity (thermal plants)
            # Check correct bus based on reverse_links setting
            reverse_links = params.get('reverse_links', False) if params else False
            elec_bus_attr = 'bus0' if reverse_links else 'bus1'
            supply_links = network.links[
                network.links[elec_bus_attr].str.contains('electricity', na=False)
            ]
            supply_from_links = supply_links.p_nom.sum()
            total_supply += supply_from_links

        # Calculate demand
        total_demand = 0
        if len(network.generators) > 0:
            demand_gens = network.generators[network.generators.sign < 0]
            # Use actual demand from p_set timeseries (peak across all timesteps)
            # instead of p_nom which contains placeholder values (999999)
            if len(demand_gens) > 0 and hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_set'):
                demand_timeseries = network.generators_t.p_set[demand_gens.index]
                # Sum the peak demand across all demand generators
                total_demand = abs(demand_timeseries.max().sum())
            else:
                # Fallback: if no timeseries, filter out placeholder values
                p_nom_values = demand_gens.p_nom
                # If p_nom is unrealistically high (>100k), assume it's a placeholder
                if (p_nom_values > 100000).any():
                    total_demand = 0  # Can't determine demand without timeseries
                else:
                    total_demand = abs(p_nom_values.sum())

        lines.append(f"Total supply capacity:  {total_supply:12.2f} MW")
        lines.append(f"  From Generators:      {supply_from_gens:12.2f} MW")
        lines.append(f"  From Links:           {supply_from_links:12.2f} MW (thermal plants)")
        lines.append(f"Total demand capacity:  {total_demand:12.2f} MW")

        if total_demand > 0:
            balance_ratio = total_supply / total_demand
            lines.append(f"Balance ratio:          {balance_ratio:12.2f} ({balance_ratio:.1%})")

            if balance_ratio < 0.8:
                lines.append("\n⚠️  WARNING: Insufficient supply capacity!")
            elif balance_ratio > 1.5:
                lines.append("\n⚠️  WARNING: Significant excess supply capacity")
            else:
                lines.append("\n✓ Supply and demand are reasonably balanced")
        else:
            lines.append("\n⚠️  WARNING: No demand in network")

        # Breakdown by carrier/technology
        if len(network.generators) > 0 and len(network.generators[network.generators.sign > 0]) > 0:
            add_subsection("Generator Supply by Carrier")
            supply_gens = network.generators[network.generators.sign > 0]
            supply_by_carrier = supply_gens.groupby('carrier')['p_nom'].sum().round(2)
            for carrier, capacity in supply_by_carrier.items():
                lines.append(f"  {carrier:40s}: {capacity:10.2f} MW")

        if len(network.links) > 0:
            # Check correct bus based on reverse_links setting
            reverse_links = params.get('reverse_links', False) if params else False
            elec_bus_attr = 'bus0' if reverse_links else 'bus1'
            supply_links = network.links[
                network.links[elec_bus_attr].str.contains('electricity', na=False)
            ]
            if len(supply_links) > 0:
                add_subsection("Link Supply by Technology (Thermal Plants)")
                supply_by_tech = supply_links.groupby('technology')['p_nom'].sum().round(2)
                for tech, capacity in supply_by_tech.items():
                    lines.append(f"  {tech:40s}: {capacity:10.2f} MW")

        if len(network.generators) > 0 and len(network.generators[network.generators.sign < 0]) > 0:
            add_subsection("Demand by Carrier")
            demand_gens = network.generators[network.generators.sign < 0]
            # Use actual demand from p_set timeseries instead of p_nom placeholders
            if hasattr(network, 'generators_t') and hasattr(network.generators_t, 'p_set'):
                demand_timeseries = network.generators_t.p_set[demand_gens.index]
                # Get peak demand for each generator, then group by carrier
                peak_demands = demand_timeseries.max().abs()
                demand_gens_with_peak = demand_gens.copy()
                demand_gens_with_peak['peak_demand'] = peak_demands
                demand_by_carrier = demand_gens_with_peak.groupby('carrier')['peak_demand'].sum().round(2)
            else:
                # Fallback to p_nom if no timeseries available
                demand_by_carrier = demand_gens.groupby('carrier')['p_nom'].sum().abs().round(2)
            for carrier, capacity in demand_by_carrier.items():
                lines.append(f"  {carrier:40s}: {capacity:10.2f} MW")

    if aspect in ['optimization', 'all']:
        add_section("OPTIMIZATION RESULTS")

        if hasattr(network, 'meta') and 'solver_status' in network.meta:
            status = network.meta['solver_status']
            lines.append(f"Solver status: {status}")

            if status.startswith('ok'):
                lines.append(f"Objective value: {network.objective:,.2f}")

                # Check if optimization has been run
                if hasattr(network.generators_t, 'p'):
                    total_gen = network.generators_t.p.sum().sum()
                    lines.append(f"Total energy generated: {total_gen:,.2f} MWh")

                    add_subsection("Generation by Technology (Optimized)")
                    gen_by_tech = network.generators_t.p.sum().groupby(
                        network.generators.technology
                    ).sum().round(2)

                    for tech, energy in gen_by_tech.items():
                        if energy > 0:
                            lines.append(f"  {tech:40s}: {energy:12.2f} MWh")
            else:
                lines.append("\n❌ Optimization failed or is infeasible")
        else:
            lines.append("Optimization has not been run yet")

    return '\n'.join(lines)


def print_component_summary(df_cap, filters_applied=None):
    """
    Print summary of components in capacity dataframe.

    Args:
        df_cap (pd.DataFrame): Capacity dataframe
        filters_applied (dict): Filters that were applied (for display)
    """
    if filters_applied:
        print("\nFilters applied:")
        for key, value in filters_applied.items():
            print(f"  {key}: {value}")

    print(f"\nComponents found: {len(df_cap)}")

    if len(df_cap) == 0:
        return

    print("\nBreakdown by component type:")
    by_component = df_cap.groupby('component').size()
    for comp, count in by_component.items():
        print(f"  {comp:12s}: {count:4d}")

    print("\nBreakdown by technology (top 10):")
    by_tech = df_cap.groupby('technology').size().sort_values(ascending=False).head(10)
    for tech, count in by_tech.items():
        print(f"  {tech:40s}: {count:4d}")


def compare_network_states(network1, network2, name1="Before", name2="After"):
    """
    Compare two network states and print differences.

    Args:
        network1: First PyPSA Network
        network2: Second PyPSA Network
        name1 (str): Label for first network
        name2 (str): Label for second network

    Returns:
        dict: Comparison results
    """
    comparison = {}

    for component in ['generators', 'links', 'lines', 'stores']:
        count1 = len(getattr(network1, component))
        count2 = len(getattr(network2, component))
        comparison[component] = {
            name1: count1,
            name2: count2,
            'difference': count2 - count1
        }

    print("\nNetwork Comparison")
    print("=" * 60)
    print(f"{'Component':<15} {name1:>10} {name2:>10} {'Change':>10}")
    print("-" * 60)

    for component, values in comparison.items():
        print(f"{component:<15} {values[name1]:>10} {values[name2]:>10} "
              f"{values['difference']:>+10}")

    return comparison
