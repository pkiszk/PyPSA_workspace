# Simple PyPSA Tutorial - FIXED VERSION

Your tutorial had **disconnected buses**. Here's the fix:

## The Problem

- Coal/gas thermal plants are **Links** that connect fuel buses to electricity buses
- Renewables inject into **vRES** buses  
- Demand withdraws from **output** buses
- These buses are NOT connected - electricity can't flow!

## The Solution - Two Options:

### Option 1: Add Infrastructure Links (Keep Thermal Plants)

After adding coal/gas/renewables/demand, add:

```python
# Add network infrastructure
summary = builder.add_components(
    'Link',
    {
        'technology': [
            'transformation EHV-HMV',  # Connect thermal to HMV
            'distribution HMV',        # HMV in → out
            'distribution LV',         # LV in → out  
            'transformation HMV-LV',   # HMV → LV
            'connection vRES-HMV'      # Connect renewables to HMV
        ],
        'area': ['PL']
    }
)
```

### Option 2: Use Supply Generators (SIMPLER!)

Replace thermal **Links** with supply **Generators**:

```python
# INSTEAD OF:
# builder.add_components('Link', {'technology': ['hard coal power old', ...]})

# USE:
builder.add_components('Generator', {'technology': ['hard coal supply'], 'area': ['PL']})
builder.add_components('Generator', {'technology': ['natural gas supply'], 'area': ['PL']})
```

This connects supply directly to electricity buses - no fuel buses needed!

## Which Option?

- **Option 1**: More realistic (models fuel conversion, efficiency losses)
- **Option 2**: **Simpler for learning** - I recommend this!

## Your Fixed Notebook

Replace cell 13 (coal) and cell 40 (gas) with:

```python
# Add coal SUPPLY (simpler than thermal links)
summary = builder.add_components(
    'Generator',
    {
        'technology': ['hard coal supply'],
        'area': ['PL']
    }
)
print(f"\n✓ Added {summary['added']} coal supply")

# Later... add gas supply
summary = builder.add_components(
    'Generator',
    {
        'technology': ['natural gas supply'],
        'area': ['PL']
    }
)
print(f"\n✓ Added {summary['added']} gas supply")
```

That's it! No infrastructure links needed.
