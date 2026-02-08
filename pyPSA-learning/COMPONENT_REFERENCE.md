# PyPSA Component Type Reference

## Component Types in This Model

This PyPSA-PL model uses 4 main component types. Understanding which type each technology uses is **critical** for using the incremental builder.

---

## 1. Generators

Generators inject or withdraw energy at a bus. In this model:
- **Positive generators** (sign > 0): Supply sources (renewables, nuclear)
- **Negative generators** (sign < 0): Demand sinks (final use)

### Supply Generators

#### Renewables
- `wind onshore` - Onshore wind turbines
- `wind offshore` - Offshore wind turbines
- `solar PV ground` - Ground-mounted solar PV
- `solar PV ground E` - East-facing solar
- `solar PV ground W` - West-facing solar
- `solar PV roof` - Rooftop solar PV
- `hydro ROR` - Run-of-river hydropower

#### Nuclear
- `nuclear power large` - Large nuclear power plants

#### Fuel Supply (at source)
- `hard coal supply` - Hard coal at mine
- `lignite supply` - Lignite at mine
- `natural gas supply` - Natural gas at source
- `biomass wood supply` - Wood biomass supply
- `biomass agriculture supply` - Agricultural biomass supply
- `biogas substrate supply` - Biogas feedstock supply
- `other fuel supply` - Other fuel supplies

### Demand Generators (Negative)

#### Electricity Demand
- `electricity final use` - Electricity demand (aggregate)
- `electricity HMV final use` - Medium voltage demand
- `electricity LV final use` - Low voltage demand

#### Heating Demand
- `space heating final use` - Space heating demand
- `water heating final use` - Water heating demand
- `other heating final use` - Other heating demand

#### Other Demand
- `light vehicle mobility final use` - Transport demand
- `hydrogen final use` - Hydrogen demand
- `hard coal final use` - Hard coal final consumption
- `natural gas final use` - Natural gas final consumption
- `biomass wood final use` - Biomass final consumption
- `other fuel final use` - Other fuel final consumption
- `process emissions final use` - Process emissions
- `lulucf final use` - Land use emissions

---

## 2. Links

Links convert energy from one carrier to another with a specified efficiency.
Format: `bus0 (input)` → Link → `bus1 (output1)` [+ `bus2 (output2)` for CHP]

### Thermal Power Plants

#### Coal-Fired
- `hard coal power old` - Old hard coal power plant
- `hard coal power SC` - Supercritical hard coal plant
- `lignite power old` - Old lignite power plant
- `lignite power SC` - Supercritical lignite plant

#### Gas-Fired
- `natural gas power CCGT` - Combined cycle gas turbine
- `natural gas power peaker` - Gas peaker plant

#### Hydrogen-Fired
- `hydrogen power CCGT` - Hydrogen combined cycle
- `hydrogen power peaker` - Hydrogen peaker plant

#### Biomass/Biogas
- `biomass wood power` - Biomass wood power plant
- `biogas CHP` - Biogas combined heat and power

### Combined Heat and Power (CHP)

Produce both electricity and heat (2 outputs: bus1 and bus2)

- `hard coal CHP` - Hard coal CHP plant
- `natural gas CHP old` - Old gas CHP
- `natural gas CHP CCGT` - Gas combined cycle CHP
- `natural gas CHP CCGT old` - Old gas CC CHP
- `other CHP` - Other fuel CHP
- `biomass wood CHP` - Biomass wood CHP
- `biomass agriculture CHP` - Agricultural biomass CHP
- `biomass agriculture CHP CC` - Biomass CHP with carbon capture
- `hydrogen CHP CCGT` - Hydrogen CHP

### Heating Links

#### Boilers (fuel → heat)
- `hard coal heat` - Hard coal boiler
- `natural gas heat` - Gas boiler (centralised)
- `natural gas boiler` - Gas boiler (decentralised)
- `biomass wood heat` - Biomass boiler
- `biomass agriculture heat` - Agricultural biomass boiler
- `hydrogen heat` - Hydrogen boiler
- `other heat` - Other fuel boiler

#### Heat Pumps
- `heat pump large AW` - Large air-water heat pump (centralised)
- `heat pump small AW` - Small air-water heat pump (decentralised)

#### Electric Heaters
- `resistive heater large` - Large electric heater (centralised)
- `resistive heater small` - Small electric heater (decentralised)

### Hydrogen Production

- `hydrogen electrolysis` - Water electrolysis (electricity → hydrogen)
- `natural gas reforming` - Natural gas reforming (gas → hydrogen)
- `biogas production` - Anaerobic digestion (substrate → biogas)
- `biogas upgrading` - Biogas upgrading (biogas → biomethane)

### Electric Vehicles

- `BEV charger` - EV charger (electricity → battery)
- `BEV V2G` - Vehicle-to-grid (battery → electricity)
- `ICE vehicle` - Internal combustion engine vehicle

### Transmission & Distribution

- `transmission line AC` - AC transmission lines (special case: modeled as Link with reverse capability)
- `distribution HMV` - Medium voltage distribution
- `distribution LV` - Low voltage distribution
- `transformation EHV-HMV` - Transformer EHV to MV
- `transformation HMV-EHV` - Transformer MV to EHV
- `transformation HMV-LV` - Transformer MV to LV
- `transformation LV-HMV` - Transformer LV to MV
- `connection HMV-vRES` - vRES connection to grid
- `connection vRES-HMV` - Grid connection from vRES

### Trade

- `electricity import` - Import electricity
- `electricity export` - Export electricity

---

## 3. Lines

High-voltage transmission lines with impedance and losses.

- `transmission line AC` - AC transmission lines (between regions)

Note: Some transmission is modeled as Links for flexibility, while true AC lines with impedance use the Line component.

---

## 4. Stores

Energy storage devices with capacity (e_nom) and losses.

### Electricity Storage

#### Battery Storage
- `battery large storage` - Large battery energy capacity (MWh)
- `battery large power` - Large battery power capacity (MW, charge/discharge)
- `battery large charger` - Battery charging interface

Note: Battery systems have 3 linked components (storage, power, charger) that work together.

#### Pumped Hydro Storage
- `hydro PSH storage` - Pumped storage energy (MWh)
- `hydro PSH power` - Turbine capacity (MW)
- `hydro PSH pump` - Pump capacity (MW)

### Heat Storage

- `heat storage large tank` - Large thermal storage (centralised)
- `heat storage large tank charge` - Charging link
- `heat storage large tank discharge` - Discharging link
- `heat storage small` - Small thermal storage (decentralised)
- `heat storage small charge` - Charging link
- `heat storage small discharge` - Discharging link

### Hydrogen Storage

- `hydrogen storage` - Hydrogen storage tanks/caverns

### Vehicle Battery Storage

- `BEV battery` - Electric vehicle battery storage

---

## Usage Examples

### Add Renewables (Generators)
```python
builder.add_components('Generator', {
    'technology': ['wind onshore', 'solar PV ground']
})
```

### Add Thermal Plants (Links)
```python
builder.add_components('Link', {
    'technology': ['hard coal power old', 'natural gas power CCGT']
})
```

### Add Demand (Negative Generators)
```python
builder.add_components('Generator', {
    'carrier': ['electricity final use']
})
```

### Add Storage (Stores)
```python
builder.add_components('Store', {
    'technology': ['battery large storage', 'hydro PSH storage']
})
```

### Add Heat Pumps (Links)
```python
builder.add_components('Link', {
    'technology': ['heat pump large AW', 'heat pump small AW']
})
```

### Add Transmission (Links or Lines)
```python
# As Links (more common in this model)
builder.add_components('Link', {
    'technology': ['transmission line AC']
})

# Or as Lines (with impedance)
builder.add_components('Line', {
    'technology': ['transmission line AC']
})
```

---

## Quick Reference Table

| Technology | Component Type | Purpose |
|------------|---------------|---------|
| Wind, Solar | Generator | Renewable generation |
| Nuclear | Generator | Nuclear generation |
| Coal, Gas plants | Link | Thermal conversion |
| Heat pumps | Link | Heat generation |
| Electrolysis | Link | Hydrogen production |
| CHPs | Link | Combined heat & power |
| Batteries, PSH | Store | Energy storage |
| Transmission | Link or Line | Power transfer |
| Final use | Generator (negative) | Demand |

---

## Finding Available Technologies

To see all technologies in your model:

```python
builder.load_inputs()
from pypsa_pl.build_network import process_capacity_data
df_cap = process_capacity_data(builder.inputs, builder.params)

# Show all technologies
print(df_cap.technology.unique())

# Show technologies by component type
for comp_type in ['Generator', 'Link', 'Store', 'Line']:
    print(f"\n{comp_type}:")
    techs = df_cap[df_cap.component == comp_type].technology.unique()
    for tech in sorted(techs):
        print(f"  - {tech}")
```

---

## Common Mistakes

### ❌ Wrong: Using underscores in technology names
```python
builder.add_components('Generator', {
    'technology': ['wind_onshore']  # WRONG - no match!
})
```

### ✓ Correct: Using spaces
```python
builder.add_components('Generator', {
    'technology': ['wind onshore']  # CORRECT
})
```

### ❌ Wrong: Thermal plants as Generators
```python
builder.add_components('Generator', {
    'technology': ['hard coal power old']  # WRONG type!
})
```

### ✓ Correct: Thermal plants as Links
```python
builder.add_components('Link', {
    'technology': ['hard coal power old']  # CORRECT
})
```

---

## Understanding the Model Logic

**Why are thermal plants Links?**
- They convert fuel (input carrier) to electricity (output carrier)
- Input: hard coal, natural gas, biomass, hydrogen
- Output: electricity (and heat for CHPs)
- PyPSA models this as a Link with efficiency

**Why is demand a negative Generator?**
- Generators can have negative sign to represent consumption
- Simpler than creating separate Load components
- Final use generators have sign = -1

**Why do batteries have 3 components?**
- Storage: Energy capacity (MWh)
- Power: Charge/discharge power (MW)
- Charger: Charging interface
- This allows independent sizing of energy vs. power

---

*This reference is based on `technology_carrier_definitions;variant=full.csv`*
