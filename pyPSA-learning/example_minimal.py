"""
Example: Build a minimal PyPSA model incrementally

This script demonstrates how to:
1. Start with an empty network
2. Add components progressively
3. Validate at each step
4. Optimize when ready
5. Inspect results
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

# Import incremental builder
from incremental_builder import IncrementalBuilder

def main():
    print("\n" + "=" * 70)
    print("  Incremental PyPSA Model Builder - Minimal Example")
    print("=" * 70)

    # =========================================================================
    # STEP 1: Create builder and build base model
    # =========================================================================
    print("\n📦 STEP 1: Creating base model structure...")

    builder = IncrementalBuilder(
        year=2025,
        timeseries='mini',  # Use mini for fast testing
        copperplate=True    # Single PL area (simpler)
    )

    builder.build_base_model()
    print("\n✓ Base model created!")

    input("\nPress Enter to continue to Step 2...")

    # =========================================================================
    # STEP 2: Add some generation (but not enough!)
    # =========================================================================
    print("\n⚡ STEP 2: Adding coal generation...")
    print("   Note: Coal plants are Link components (fuel → electricity)")

    builder.add_components('Link', {
        'technology': ['hard coal power old', 'hard coal power SC']
    })

    builder.inspect('balance')

    input("\nPress Enter to continue to Step 3...")

    # =========================================================================
    # STEP 3: Add demand (more than generation!)
    # =========================================================================
    print("\n🏭 STEP 3: Adding electricity demand...")

    builder.add_components('Generator', {
        'carrier': ['electricity final use']
    })

    builder.inspect('balance')
    builder.validate_stage('demand_added')

    input("\nPress Enter to continue to Step 4...")

    # =========================================================================
    # STEP 4: Try to optimize (will likely fail due to insufficient capacity)
    # =========================================================================
    print("\n🔧 STEP 4: Attempting optimization (likely to fail)...")

    success = builder.optimize()

    if not success:
        print("\n❌ As expected, optimization failed!")
        print("   We need more generation capacity.")

    input("\nPress Enter to continue to Step 5...")

    # =========================================================================
    # STEP 5: Add renewables and gas
    # =========================================================================
    print("\n🌬️ STEP 5: Adding renewables and gas generation...")
    print("   Note: Wind and solar are Generators, gas plants are Links")

    # Add renewables (Generators)
    builder.add_components('Generator', {
        'technology': ['wind onshore', 'solar PV ground']
    })

    # Add gas (Links - thermal plants)
    builder.add_components('Link', {
        'technology': ['natural gas power CCGT']
    })

    builder.inspect('balance')
    builder.validate_stage('renewables_added')

    input("\nPress Enter to continue to Step 6...")

    # =========================================================================
    # STEP 6: Optimize again (should work now!)
    # =========================================================================
    print("\n🎯 STEP 6: Optimizing with sufficient capacity...")

    success = builder.optimize()

    if success:
        print("\n✓ Optimization succeeded!")
        builder.inspect('optimization')
    else:
        print("\n❌ Optimization still failed. Might need even more capacity.")

    input("\nPress Enter to continue to Step 7...")

    # =========================================================================
    # STEP 7: Save checkpoint
    # =========================================================================
    print("\n💾 STEP 7: Saving checkpoint...")

    builder.save_checkpoint('minimal_balanced_model')
    print("✓ Checkpoint saved!")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    builder.inspect('summary')

    print("\n✓ Example completed successfully!")
    print("\nNext steps you could try:")
    print("  - Add storage: builder.add_components('Store', {'technology': ['battery large']})")
    print("  - Add links: builder.add_components('Link', {'technology': ['heat pump']})")
    print("  - Add constraints: builder.add_constraints()")
    print("  - Load checkpoint: builder.load_checkpoint('minimal_balanced_model')")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
