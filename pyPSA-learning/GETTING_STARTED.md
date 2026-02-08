# Getting Started with PyPSA Learning Framework

## ✅ Framework is Installed and Ready!

You now have a working incremental PyPSA model builder in:
```
/home/magda/projects/pyPSA-PL/pyPSA-learning/
```

## 🚀 Three Ways to Use It

### Option 1: Run the Guided Example (Recommended for First Time)

```bash
cd /home/magda/projects/pyPSA-PL/pyPSA-learning
python example_minimal.py
```

This will walk you through building a model step-by-step with explanations.

### Option 2: Interactive Mode

```bash
cd /home/magda/projects/pyPSA-PL/pyPSA-learning
python interactive.py
```

Commands you can use:
- `init` - Initialize builder
- `base` - Build base model structure
- `add Generator technology=wind,solar` - Add components
- `inspect balance` - Check supply/demand
- `optimize` - Run optimization
- `save my_model` - Save checkpoint
- `help` - See all commands

### Option 3: Python Script/Notebook

```python
from incremental_builder import IncrementalBuilder

# Create builder
builder = IncrementalBuilder(year=2025, timeseries='mini', copperplate=True)

# Build base model (empty structure)
builder.build_base_model()

# Add coal generation (thermal plants are Links, not Generators!)
builder.add_components('Link', {
    'technology': ['hard coal power old']
})

# Add demand
builder.add_components('Generator', {
    'carrier': ['electricity final use']
})

# Check if balanced
builder.inspect('balance')

# Add more generation
# Wind and solar are Generators
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground']
})

# Gas plants are Links (thermal conversion)
builder.add_components('Link', {
    'technology': ['natural gas power CCGT']
})

# Optimize
builder.optimize()

# View results
builder.inspect('optimization')

# Save for later
builder.save_checkpoint('my_first_model')
```

## 📖 Key Concepts

### ⚠️ CRITICAL: Understanding Component Types

In this PyPSA model, different technologies use different component types:

**Generators**: Renewables, nuclear, supply sources, and demand
- Examples: `'wind onshore'`, `'solar PV ground'`, `'electricity final use'`
- Demand is modeled as negative generators (sign < 0)

**Links**: Thermal plants (coal, gas), heat pumps, CHPs
- Examples: `'hard coal power old'`, `'natural gas power CCGT'`, `'heat pump large AW'`
- Convert one energy carrier to another (fuel → electricity)

**Lines**: Transmission infrastructure

**Stores**: Energy storage (batteries, PSH, hydrogen)

**Technology names have SPACES**: `'wind onshore'` not `'wind_onshore'`

### 1. Start with Empty Model
```python
builder = IncrementalBuilder(year=2025, timeseries='mini')
builder.build_base_model()
```

This creates:
- Network structure (buses, carriers, snapshots)
- But NO generators, links, or stores yet

### 2. Add Components Gradually

```python
# Add specific technologies
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground']
})

# Add by carrier (e.g., demand)
builder.add_components('Generator', {
    'carrier': ['electricity final use']
})

# Add storage
builder.add_components('Store', {
    'technology': ['battery large']
})
```

### 3. Check Balance Before Optimizing

```python
builder.inspect('balance')
```

This shows:
- Total supply capacity
- Total demand capacity
- Balance ratio (should be ~1.0 to 1.5)

### 4. Optimize When Ready

```python
success = builder.optimize()

if success:
    builder.inspect('optimization')
else:
    print("Need more generation capacity!")
```

### 5. Save Your Work

```python
# Save current state
builder.save_checkpoint('balanced_model')

# Load it later
builder2 = IncrementalBuilder(year=2025)
builder2.load_checkpoint('balanced_model')
```

## 🎯 Learning Path

### Day 1: Basics
1. Run `example_minimal.py` to see the full workflow
2. Understand how balance affects optimization
3. Experiment with different technologies

### Day 2: Complexity
1. Add storage (batteries, PSH)
2. Add different demand types (heat, hydrogen)
3. Add links (heat pumps, electrolysis)

### Day 3: Constraints
1. Add global constraints
2. Add capacity limits
3. See how constraints affect results

## 🔍 Understanding Your Model

### View Component Counts
```python
builder.inspect('summary')
```

### Detailed Technology Breakdown
```python
builder.inspect('detailed')
```

### Supply/Demand Analysis
```python
builder.inspect('balance')
```

### Optimization Results
```python
builder.inspect('optimization')
```

### Everything at Once
```python
builder.inspect('all')
```

## ⚠️ Common Issues

### "Optimization failed"
**Cause**: Not enough generation to meet demand

**Solution**:
```python
# Check balance first
builder.inspect('balance')

# If supply < demand, add more generation
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground', 'natural gas power CCGT']
})
```

### "No components match filters"
**Cause**: Technology name doesn't exist or typo

**Solution**:
```python
# See available technologies
# (Need to load inputs first)
builder.load_inputs()
print(builder.df_cap_full.technology.unique())
```

### "Import error"
**Cause**: Wrong directory

**Solution**:
```bash
# Make sure you're in the right directory
cd /home/magda/projects/pyPSA-PL/pyPSA-learning
```

## 📚 More Resources

- **Full Plan**: See [PLAN.md](PLAN.md) for detailed design
- **Quick Reference**: See [README.md](README.md) for API reference
- **PyPSA Docs**: https://pypsa.readthedocs.io/

## 💡 Tips

1. **Use 'mini' timeseries** for fast iteration (168 hours = 1 week)
2. **Check balance often** with `builder.inspect('balance')`
3. **Save checkpoints** so you can return to working states
4. **Start simple** - electricity only, then add sectors
5. **Use copperplate** initially (single PL area, faster)

## Next Steps

Ready to start? Try this:

```bash
cd /home/magda/projects/pyPSA-PL/pyPSA-learning
python example_minimal.py
```

Or dive right in:

```python
from incremental_builder import create_minimal_builder

# Quick start - creates base model automatically
builder = create_minimal_builder(year=2025)

# Now add components and explore!
builder.add_components('Generator', {'technology': ['wind onshore']})
builder.inspect('summary')
```

Happy learning! 🚀
