# PyPSA Learning - Incremental Model Builder

A tool for learning and understanding PyPSA models by building them incrementally from scratch.

## Quick Start

### 1. Run the minimal example

```bash
cd /home/magda/projects/pyPSA-PL/pyPSA-learning
python example_minimal.py
```

This will guide you through building a simple model step-by-step.

### 2. Interactive Python session

```python
from incremental_builder import IncrementalBuilder

# Create builder
builder = IncrementalBuilder(year=2025, timeseries='mini', copperplate=True)

# Build base structure
builder.build_base_model()

# Add coal generation (Links - thermal plants convert fuel to electricity)
builder.add_components('Link', {
    'technology': ['hard coal power old']
})

# Add demand
builder.add_components('Generator', {
    'carrier': ['electricity final use']
})

# Check balance
builder.inspect('balance')

# Add more generation (wind/solar are Generators, gas is Link)
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground']
})
builder.add_components('Link', {
    'technology': ['natural gas power CCGT']
})

# Optimize
builder.optimize()

# View results
builder.inspect('optimization')
```

## Key Concepts

### Understanding Component Types

**CRITICAL**: In this PyPSA model, different technologies use different component types:

- **Generators**: Renewables (wind, solar), nuclear, supply sources, and demand (negative generators)
  - Examples: `wind onshore`, `solar PV ground`, `nuclear power large`, `electricity final use`

- **Links**: Thermal plants (coal, gas, biomass), heat pumps, electrolysis, CHPs
  - Examples: `hard coal power old`, `natural gas power CCGT`, `heat pump large AW`
  - Links convert one energy carrier to another (e.g., fuel → electricity)

- **Lines**: Transmission infrastructure
  - Examples: `transmission line AC`, `distribution HMV`

- **Stores**: Energy storage
  - Examples: `battery large storage`, `hydro PSH storage`, `hydrogen storage`

**Important**: Always use the correct component type when adding technologies!

### Technology Names

**Technology names have SPACES, not underscores**:
- ✓ Correct: `'wind onshore'`, `'solar PV ground'`, `'hard coal power old'`
- ✗ Wrong: `'wind_onshore'`, `'solar_PV_ground'`, `'hard_coal_power_old'`

### Building Stages

1. **Base Model** - Empty network with structure (buses, carriers, snapshots)
2. **Add Components** - Progressively add generators, links, lines, stores
3. **Add Constraints** - Add global and capacity constraints
4. **Optimize** - Run solver and get results
5. **Inspect** - Examine network state and results

### Filtering Components

You can filter components by:

```python
# By technology (note: technology names have spaces, not underscores)
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground']
})

# For thermal plants, use Link component type
builder.add_components('Link', {
    'technology': ['hard coal power old', 'natural gas power CCGT']
})

# By carrier
builder.add_components('Generator', {
    'carrier': ['electricity final use']
})

# By area (useful for non-copperplate models)
builder.add_components('Generator', {
    'area': ['PL'],
    'technology': ['nuclear']
})

# By component type
builder.add_components('Store', {
    'technology': ['battery large']
})

# Multiple filters
builder.add_components('Link', {
    'area': ['PL'],
    'technology': ['heat pump']
})
```

### Inspection

View different aspects of your network:

```python
# Summary of component counts
builder.inspect('summary')

# Detailed breakdown by technology
builder.inspect('detailed')

# Supply/demand balance
builder.inspect('balance')

# Optimization results (after optimizing)
builder.inspect('optimization')

# Everything
builder.inspect('all')
```

### Validation

Check network state at any point:

```python
# Validate structure
builder.validate_stage('my_stage', validation_types=['structure'])

# Validate balance
builder.validate_stage('my_stage', validation_types=['balance'])

# Validate all
builder.validate_stage('my_stage', validation_types=['structure', 'balance', 'connectivity'])
```

### Checkpoints

Save and load network state:

```python
# Save current state
builder.save_checkpoint('my_checkpoint')

# Load saved state
builder.load_checkpoint('my_checkpoint')
```

## File Structure

```
pyPSA-learning/
├── README.md                       # This file
├── PLAN.md                        # Detailed implementation plan
├── incremental_builder.py         # Main builder class
├── incremental_builder_utils.py   # Utility functions
├── example_minimal.py             # Minimal example script
└── checkpoints/                   # Saved network states
    └── my_checkpoint/
        ├── network/               # Network CSV files
        ├── capacity_data.csv      # Component capacities
        └── stage_history.txt      # Build history
```

## Learning Path

### Beginner: Understand basic PyPSA

1. Run `example_minimal.py` and follow along
2. Experiment with adding different technologies
3. Observe how balance affects optimization
4. Try with different years (2025, 2030, 2035, 2040)

### Intermediate: Explore complexity

1. Start with electricity only
2. Add heat sector (heat pumps, boilers, storage)
3. Add hydrogen sector (electrolysis, storage)
4. Add transmission lines between regions
5. Compare copperplate vs voivodeship resolution

### Advanced: Understand constraints

1. Build full model incrementally
2. Add energy flow constraints
3. Add capacity constraints
4. Compare constrained vs unconstrained results
5. Analyze shadow prices and binding constraints

## Tips

- **Start simple**: Use `timeseries='mini'` for fast iteration
- **Check balance**: Always run `builder.inspect('balance')` after adding components
- **Save often**: Use checkpoints to save progress
- **Validate early**: Run validation after each major step
- **Read logs**: The logging output shows what's being added

## Common Issues

### Optimization fails

**Cause**: Insufficient generation capacity or infeasible constraints

**Solution**:
- Check balance: `builder.inspect('balance')`
- Add more generation capacity
- Check if demand is too high

### No components added

**Cause**: Filters don't match any components

**Solution**:
- Check technology names in the input data
- Use partial matching (e.g., 'wind' matches 'wind onshore')
- Print available technologies: `builder.df_cap_full.technology.unique()`

### Import errors

**Cause**: Python can't find pypsa-pl module

**Solution**:
- Make sure you're in the right directory
- The script adds pypsa-pl to path automatically
- Check that pypsa-pl is installed

## Next Steps

After understanding the basics:

1. Read [PLAN.md](PLAN.md) for the full design
2. Create custom scenarios
3. Experiment with different technologies
4. Analyze sensitivity to parameters
5. Compare scenarios

## Support

- Check the plan: [PLAN.md](PLAN.md)
- Read PyPSA docs: https://pypsa.readthedocs.io/
- Explore the main codebase: `../pypsa-pl/src/`
