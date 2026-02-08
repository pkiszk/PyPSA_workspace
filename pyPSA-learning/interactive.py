"""
Interactive PyPSA Model Builder

A simple command-line interface for building models incrementally.
"""

import sys
import logging
import pandas as pd
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

from incremental_builder import IncrementalBuilder
from incremental_builder_utils import print_component_summary

def print_help():
    """Print available commands."""
    print("\nAvailable commands:")
    print("  init [year] [timeseries]  - Initialize builder (default: 2025 mini)")
    print("  base                       - Build base model")
    print("  add <type> <filters>       - Add components")
    print("  inspect [aspect]           - Inspect network (default: summary)")
    print("  validate [types]           - Validate network")
    print("  optimize                   - Run optimization")
    print("  save <name>                - Save checkpoint")
    print("  load <name>                - Load checkpoint")
    print("  show technologies          - Show available technologies")
    print("  show carriers              - Show available carriers")
    print("  help                       - Show this help")
    print("  quit                       - Exit")
    print("\nExamples:")
    print("  add Generator technology=wind")
    print("  add Generator carrier=electricity_final_use")
    print("  add Store technology=battery")
    print("  inspect balance")
    print("  validate balance")


def parse_filters(args):
    """Parse filter arguments like 'technology=wind carrier=electricity'."""
    filters = {}
    for arg in args:
        if '=' in arg:
            key, value = arg.split('=', 1)
            # Handle multiple values separated by comma
            if ',' in value:
                filters[key] = value.split(',')
            else:
                filters[key] = [value]
    return filters


def main():
    print("\n" + "=" * 70)
    print("  Interactive PyPSA Model Builder")
    print("=" * 70)
    print("\nType 'help' for available commands, 'quit' to exit")

    builder = None

    while True:
        try:
            # Get command
            cmd_input = input("\npypsa> ").strip()

            if not cmd_input:
                continue

            parts = cmd_input.split()
            cmd = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []

            # Execute command
            if cmd == 'quit' or cmd == 'exit':
                print("Goodbye!")
                break

            elif cmd == 'help':
                print_help()

            elif cmd == 'init':
                year = int(args[0]) if len(args) > 0 else 2025
                timeseries = args[1] if len(args) > 1 else 'mini'
                builder = IncrementalBuilder(year=year, timeseries=timeseries)
                print(f"✓ Builder initialized: year={year}, timeseries={timeseries}")

            elif cmd == 'base':
                if builder is None:
                    print("❌ Initialize builder first with 'init'")
                    continue
                builder.build_base_model()

            elif cmd == 'add':
                if builder is None:
                    print("❌ Initialize builder first with 'init'")
                    continue
                if builder.network is None:
                    print("❌ Build base model first with 'base'")
                    continue

                if len(args) < 2:
                    print("❌ Usage: add <component_type> <filters>")
                    print("   Example: add Generator technology=wind,solar")
                    continue

                component_type = args[0]
                filters = parse_filters(args[1:])

                if not filters:
                    print("❌ No filters provided")
                    continue

                summary = builder.add_components(component_type, filters)
                print(f"✓ Added {summary['added']} components")

            elif cmd == 'inspect':
                if builder is None or builder.network is None:
                    print("❌ No network to inspect")
                    continue

                aspect = args[0] if len(args) > 0 else 'summary'
                builder.inspect(aspect)

            elif cmd == 'validate':
                if builder is None or builder.network is None:
                    print("❌ No network to validate")
                    continue

                validation_types = args if len(args) > 0 else None
                builder.validate_stage(validation_types=validation_types)

            elif cmd == 'optimize':
                if builder is None or builder.network is None:
                    print("❌ No network to optimize")
                    continue

                success = builder.optimize()
                if success:
                    print("✓ Optimization succeeded!")
                else:
                    print("❌ Optimization failed")

            elif cmd == 'save':
                if builder is None or builder.network is None:
                    print("❌ No network to save")
                    continue

                if len(args) == 0:
                    print("❌ Usage: save <checkpoint_name>")
                    continue

                builder.save_checkpoint(args[0])

            elif cmd == 'load':
                if builder is None:
                    print("❌ Initialize builder first with 'init'")
                    continue

                if len(args) == 0:
                    print("❌ Usage: load <checkpoint_name>")
                    continue

                builder.load_checkpoint(args[0])

            elif cmd == 'show':
                if len(args) == 0:
                    print("❌ Usage: show <technologies|carriers|areas>")
                    continue

                what = args[0].lower()

                if builder is None:
                    print("❌ Initialize builder first with 'init'")
                    continue

                if builder.df_cap_full is None:
                    builder.load_inputs()
                    from pypsa_pl.build_network import process_capacity_data
                    builder.df_cap_full = process_capacity_data(builder.inputs, builder.params)

                if what == 'technologies':
                    techs = sorted(builder.df_cap_full['technology'].unique())
                    print(f"\nAvailable technologies ({len(techs)}):")
                    for i, tech in enumerate(techs, 1):
                        print(f"  {i:3d}. {tech}")

                elif what == 'carriers':
                    carriers = sorted(builder.df_cap_full['carrier'].unique())
                    print(f"\nAvailable carriers ({len(carriers)}):")
                    for i, carrier in enumerate(carriers, 1):
                        print(f"  {i:3d}. {carrier}")

                elif what == 'areas':
                    areas = sorted(builder.df_cap_full['area'].unique())
                    print(f"\nAvailable areas ({len(areas)}):")
                    for i, area in enumerate(areas, 1):
                        print(f"  {i:3d}. {area}")

                else:
                    print(f"❌ Unknown show target: {what}")

            else:
                print(f"❌ Unknown command: {cmd}")
                print("   Type 'help' for available commands")

        except KeyboardInterrupt:
            print("\n\nUse 'quit' to exit")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
