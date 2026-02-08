"""
Basic test to verify the incremental builder framework works.
"""

import sys
import logging
from pathlib import Path

# Setup minimal logging
logging.basicConfig(level=logging.WARNING)

# Test imports
print("Testing imports...")
try:
    from incremental_builder import IncrementalBuilder, create_minimal_builder
    from incremental_builder_utils import filter_capacity_data, validate_network_state
    print("✓ All imports successful!")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

print("\nFramework is ready to use!")
print("\nNext steps:")
print("  1. Run the example: python example_minimal.py")
print("  2. Or use interactive mode: python interactive.py")
print("  3. Or use Python directly:")
print()
print("     from incremental_builder import IncrementalBuilder")
print("     builder = IncrementalBuilder(year=2025, timeseries='mini')")
print("     builder.build_base_model()")
print("     # ... add components and optimize ...")
