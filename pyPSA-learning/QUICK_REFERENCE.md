# Quick Reference Card - PyPSA Incremental Builder

## 🚀 Quick Start

```python
from incremental_builder import IncrementalBuilder

# Create builder
builder = IncrementalBuilder(year=2025, timeseries='mini', copperplate=True)

# Build base
builder.build_base_model()

# Add components
builder.add_components('Link', {'technology': ['hard coal power old']})
builder.add_components('Generator', {'carrier': ['electricity final use']})

# Check & optimize
builder.inspect('balance')
builder.optimize()
builder.inspect('optimization')
```

---

## ⚠️ CRITICAL: Component Types

| Technology Type | Component | Example |
|----------------|-----------|---------|
| **Renewables** | Generator | `'wind onshore'`, `'solar PV ground'` |
| **Nuclear** | Generator | `'nuclear power large'` |
| **Thermal Plants** | Link | `'hard coal power old'`, `'natural gas power CCGT'` |
| **Demand** | Generator (negative) | `'electricity final use'` |
| **Heat Pumps** | Link | `'heat pump large AW'` |
| **Storage** | Store | `'battery large storage'`, `'hydro PSH storage'` |
| **Transmission** | Line or Link | `'transmission line AC'` |

### Remember
- ✓ Technology names use **SPACES**: `'hard coal power old'`
- ✗ NOT underscores: `'hard_coal_power_old'`

---

## 📊 Component Type Decision Tree

```
Is it thermal conversion (fuel → electricity)?
├─ YES → Use Link
│   Examples: coal, gas, biomass plants
│
└─ NO → Is it energy storage?
    ├─ YES → Use Store
    │   Examples: batteries, PSH, hydrogen storage
    │
    └─ NO → Is it direct electricity injection?
        ├─ YES → Use Generator
        │   Examples: wind, solar, nuclear, demand (negative)
        │
        └─ NO → Use Link or Line
            Examples: heat pumps, electrolysis, transmission
```

---

## 🎯 Common Operations

### Adding Components

```python
# By technology (with spaces!)
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground']
})

# By carrier
builder.add_components('Generator', {
    'carrier': ['electricity final use']
})

# By area (for non-copperplate)
builder.add_components('Generator', {
    'area': ['PL'],
    'technology': ['nuclear power large']
})

# Multiple filters
builder.add_components('Link', {
    'area': ['PL'],
    'technology': ['heat pump large AW']
})
```

### Inspection

```python
builder.inspect('summary')       # Component counts
builder.inspect('detailed')      # Per-technology breakdown
builder.inspect('balance')       # Supply/demand analysis
builder.inspect('optimization')  # Results after optimizing
builder.inspect('all')          # Everything
```

### Validation

```python
builder.validate_stage('my_stage')  # All validations

builder.validate_stage('my_stage',
    validation_types=['structure', 'balance'])  # Specific checks
```

### Optimization

```python
success = builder.optimize()

if success:
    builder.inspect('optimization')
else:
    # Check balance, add more capacity
    builder.inspect('balance')
```

### Checkpoints

```python
# Save
builder.save_checkpoint('my_model')

# Load
builder.load_checkpoint('my_model')
```

---

## ⚖️ Balance Interpretation

| Balance Ratio | Meaning | Action |
|--------------|---------|--------|
| < 0.5 | Severe deficit | Add much more generation |
| 0.5 - 0.8 | Insufficient | Add generation or reduce demand |
| 0.8 - 1.5 | Good | Proceed with optimization |
| 1.5 - 2.5 | Slight excess | OK, provides reliability margin |
| > 2.5 | Excessive | May be inefficient, but OK |

**Note**: Balance includes **both** Generators AND Links!

---

## 🐛 Common Mistakes & Fixes

### ❌ Mistake 1: Thermal plants as Generators
```python
# WRONG
builder.add_components('Generator', {
    'technology': ['hard coal power old']
})
```

### ✅ Fix: Use Link
```python
# CORRECT
builder.add_components('Link', {
    'technology': ['hard coal power old']
})
```

---

### ❌ Mistake 2: Underscores in names
```python
# WRONG
builder.add_components('Generator', {
    'technology': ['wind_onshore']  # No match!
})
```

### ✅ Fix: Use spaces
```python
# CORRECT
builder.add_components('Generator', {
    'technology': ['wind onshore']
})
```

---

### ❌ Mistake 3: Optimize before balance check
```python
# WRONG - might waste time on infeasible model
builder.optimize()
```

### ✅ Fix: Check balance first
```python
# CORRECT
builder.inspect('balance')
# Fix any issues, then:
builder.optimize()
```

---

## 🔍 Debugging Tips

### Model won't optimize?

1. **Check balance**:
   ```python
   builder.inspect('balance')
   ```
   Need supply ≥ demand

2. **Check for components**:
   ```python
   builder.inspect('summary')
   ```
   Need both supply AND demand

3. **Check logs**:
   Look for error messages in the output

4. **Validate**:
   ```python
   builder.validate_stage(validation_types=['balance', 'structure'])
   ```

### No components added?

```python
# Check what's available
from pypsa_pl.build_network import process_capacity_data
df = process_capacity_data(builder.inputs, builder.params)

# See all technologies
print(df.technology.unique())

# Check component types
print(df[['technology', 'component']].drop_duplicates())
```

---

## 📈 Typical Workflow

```
1. Create Builder
   ↓
2. Build Base Model
   ↓
3. Add Supply (thermal plants as Links!)
   ↓
4. Add Demand (negative Generators)
   ↓
5. Check Balance (supply vs demand)
   ↓
6. Add More Supply if needed
   ↓
7. Validate
   ↓
8. Optimize
   ↓
9. Inspect Results
   ↓
10. Save Checkpoint
```

---

## 🎓 Learning Path

### Beginner
1. Run tutorial notebook
2. Understand component types
3. Build electricity-only model
4. Check balance before optimizing

### Intermediate
1. Add storage
2. Add heat sector
3. Add hydrogen sector
4. Compare scenarios

### Advanced
1. Add constraints
2. Multi-region models (copperplate=False)
3. Sensitivity analysis
4. Custom cost scenarios

---

## 📚 Where to Get Help

### Files in This Directory
- **tutorial_incremental_builder.ipynb** - This reference card as a notebook
- **COMPONENT_REFERENCE.md** - All technologies listed
- **README.md** - Full API documentation
- **GETTING_STARTED.md** - Quick start guide
- **example_minimal.py** - Working example script

### Common Questions

**Q: How do I know which component type to use?**
A: Check COMPONENT_REFERENCE.md or the technology_carrier_definitions CSV

**Q: Why is my model infeasible?**
A: Run `builder.inspect('balance')` - usually insufficient supply

**Q: Can I see all available technologies?**
A: Yes, see "No components added?" section above

**Q: How long does optimization take?**
A: mini=30-60s, medium=5-10min, full=30-60min

**Q: Can I add multiple technologies at once?**
A: Yes! Use a list: `{'technology': ['wind onshore', 'solar PV ground', 'nuclear power large']}`

---

## 💡 Pro Tips

1. **Start with mini timeseries** - Fast iteration while learning
2. **Use copperplate=True** - Simpler, faster
3. **Check balance BEFORE optimizing** - Saves time
4. **Save checkpoints often** - Don't lose working models
5. **Read component types from CSV** - When in doubt, check the source
6. **Use validation early** - Catches issues before optimization
7. **Compare before/after** - Add component, optimize, compare
8. **Filter by partial match** - 'wind' matches 'wind onshore' and 'wind offshore'

---

## 🚨 Critical Things to Remember

1. **Thermal plants are Links, not Generators**
2. **Technology names have spaces, not underscores**
3. **Demand is negative Generators**
4. **Balance includes Generators + Links**
5. **Check balance before optimizing**

---

*Last updated: 2026-02-07*
*Based on corrected framework with all critical fixes applied*
