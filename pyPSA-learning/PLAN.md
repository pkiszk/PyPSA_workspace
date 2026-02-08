# Implementation Plan: Incremental PyPSA Model Builder

## Problem Statement

You're struggling to understand how the PyPSA-PL model works and how different components affect the results. The current codebase builds a complete, complex model with 100+ technologies all at once, making it difficult to:
- Understand cause and effect of individual components
- Debug issues in the model
- Learn how PyPSA optimization works
- Validate intermediate results

## Solution: Incremental Model Builder

Create a new script that allows you to start with a blank model and progressively add components while testing results at each step. This will help you understand:
- What each component contributes to the model
- How the optimizer behaves with minimal vs. complete models
- Which constraints are binding
- How results change as complexity increases

---

## Architecture Overview

### Core Principle: Reuse + Control

The incremental builder will **wrap existing functions** from the codebase with:
- **Filtering logic** to select which components to add
- **Validation checks** after each step
- **Inspection utilities** to examine current state
- **Checkpoint system** to save/load progress

### Build Progression

```
Stage 0: Base Model
  ↓ (network structure, no components)
Stage 1: Minimal Generation
  ↓ (e.g., just coal power)
Stage 2: Add Demand
  ↓ (electricity final use)
Stage 3: Expand Generation Mix
  ↓ (add wind, solar, gas, nuclear)
Stage 4: Add Storage
  ↓ (batteries, PSH)
Stage 5: Add Links/Transmission
  ↓ (lines, converters)
Stage 6: Add Constraints
  ↓ (global constraints, capacity limits)
Stage 7: Optimize & Analyze
  ↓ (run solver, examine results)
```

---

## Implementation Details

### File Structure

```
/home/magda/projects/pyPSA-PL/pypsa-pl/scripts/
├── incremental_builder.py           # Main script (NEW)
├── incremental_builder_config.yaml  # Configuration (NEW)
├── incremental_builder_utils.py     # Utilities (NEW)
└── run_pypsa_pl_2025_example.py     # Reference (existing)

/home/magda/projects/pyPSA-PL/pypsa-pl/data/
└── incremental_checkpoints/         # Saved states (NEW)
```

### Core Components to Implement

#### 1. IncrementalBuilder Class

**Purpose**: Main interface for progressive model building

**Key Methods**:
```python
class IncrementalBuilder:
    def __init__(self, params_subset):
        """Initialize with minimal parameters"""

    def build_base_model(self):
        """Stage 0: Create network structure only"""
        # Calls: create_custom_network, add_snapshots,
        #        add_carriers, add_buses_and_areas

    def add_components(self, component_type, filters):
        """Add specific components with filtering"""
        # Filters capacity data, then calls:
        # process_capacity_data, add_capacities

    def validate_stage(self, stage_name):
        """Run checks after adding components"""
        # Check: connectivity, balance, feasibility

    def optimize(self, params=None):
        """Run optimization on current state"""
        # Calls: optimise_network

    def inspect(self, aspect='summary'):
        """Examine current network state"""
        # Generate reports on capacities, balance, etc.

    def save_checkpoint(self, name):
        """Save current state"""

    def load_checkpoint(self, name):
        """Restore saved state"""
```

#### 2. Helper Functions

**filter_capacity_data(df, filters)**
- Filter by technology list
- Filter by area
- Filter by year range
- Returns: subset of capacity dataframe

**validate_network_state(network, check_type)**
- 'structure': buses/carriers exist
- 'balance': generation vs. demand capacity
- 'connectivity': network is connected
- 'feasibility': basic constraint checks
- Returns: validation report dict

**generate_inspection_report(network, detail)**
- 'summary': component counts, total capacities
- 'detailed': per-technology breakdown
- 'balance': supply/demand analysis
- 'optimization': results if optimized
- Returns: formatted text report

#### 3. Configuration System

YAML config to control what gets built:

```yaml
base_model:
  year: 2025
  timeseries: mini  # mini, medium, or full
  copperplate: true  # single PL area vs. voivodeships

stages:
  generation:
    enabled: true
    technologies:
      - hard_coal_power_old
      - hard_coal_power_SC
      - wind_onshore
      - solar_PV_ground
    areas: ["PL"]

  demand:
    enabled: true
    carriers: ["electricity_final_use"]

  storage:
    enabled: false
    technologies:
      - battery_large_storage
      - hydro_PSH_storage

  links:
    enabled: false

optimization:
  enabled: false
  solver: highs
```

---

## Reusable Existing Functions

### From `/home/magda/projects/pyPSA-PL/pypsa-pl/src/pypsa_pl/build_network.py`

**Core building blocks to wrap**:
- `load_and_preprocess_inputs(params, custom_operation)` - Load 6 input CSVs
- `create_custom_network(params)` - Create PyPSA network with custom components
- `add_snapshots(network, params)` - Add time dimension
- `add_carriers(network, inputs, params)` - Add energy carriers
- `add_buses_and_areas(network, inputs, params)` - Add network nodes
- `process_capacity_data(inputs, params)` - Merge capacity with costs/constraints
- `add_capacities(network, df_cap, df_attr_t, params)` - Add generators/links/stores
- `add_energy_flow_constraints(network, inputs, params)` - Add global constraints
- `add_capacity_constraints(network, inputs, params)` - Add capacity limits

### From `/home/magda/projects/pyPSA-PL/pypsa-pl/src/pypsa_pl/run_simulation.py`

**Orchestration pattern to follow**:
- Lines 58-70: Shows exact sequence of function calls
- This is the "recipe" we'll make incremental

### From `/home/magda/projects/pyPSA-PL/pypsa-pl/src/pypsa_pl/optimise_network.py`

**Optimization to wrap**:
- `optimise_network(network, params, log_dir)` - Run solver

### From `/home/magda/projects/pyPSA-PL/pypsa-pl/src/pypsa_pl/define_time_dependent_attributes.py`

**Time-varying profiles**:
- `define_time_dependent_attributes(df_cap, params)` - Create time-series attributes
- Need to call this whenever adding components

---

## Example Usage Workflow

### Minimal Model Example

```python
from incremental_builder import IncrementalBuilder

# Create builder with minimal params
builder = IncrementalBuilder(year=2025, timeseries='mini')

# Stage 0: Build base (structure only)
builder.build_base_model()
builder.inspect('summary')
# Output: "Network created: 5 buses, 3 carriers, 168 snapshots, 0 components"

# Stage 1: Add coal generation
builder.add_components('Generator', {
    'technology': ['hard_coal_power_old'],
    'area': ['PL']
})
builder.inspect('generation')
# Output: "Added 1 generator, 2500 MW capacity"

# Stage 2: Add demand (more than generation!)
builder.add_components('Generator', {
    'carrier': ['electricity_final_use']
})
builder.inspect('balance')
# Output: "Generation: 2500 MW, Demand: 25000 MW, UNBALANCED!"

# Stage 3: Try to optimize (will fail - infeasible)
try:
    builder.optimize()
except Exception as e:
    print(f"Optimization failed: {e}")
# Output: "Infeasible - insufficient generation capacity"

# Stage 4: Add more generation
builder.add_components('Generator', {
    'technology': ['wind_onshore', 'solar_PV_ground',
                   'natural_gas_power_CCGT']
})
builder.inspect('balance')
# Output: "Generation: 30000 MW, Demand: 25000 MW, BALANCED!"

# Stage 5: Optimize (should work now)
builder.optimize()
builder.inspect('optimization')
# Output: "Optimal objective: 1234567 EUR, Status: ok"

# Stage 6: Save progress
builder.save_checkpoint('base_with_renewables')
```

### Configuration-Driven Example

```python
# Build from YAML config
builder = IncrementalBuilder.from_config('minimal_model.yaml')

# Execute all enabled stages
builder.build_all_stages()

# Inspect final result
builder.inspect('detailed')
```

---

## Validation Strategy

### After Each Stage

```python
def validate_stage(network, stage_name):
    checks = []

    # 1. Structure check
    if len(network.buses) == 0:
        checks.append("ERROR: No buses in network")

    # 2. Balance check
    gen_capacity = network.generators[network.generators.sign > 0].p_nom.sum()
    demand_capacity = abs(network.generators[network.generators.sign < 0].p_nom.sum())

    if demand_capacity > 0:
        balance_ratio = gen_capacity / demand_capacity
        if balance_ratio < 0.8:
            checks.append(f"WARNING: Insufficient generation ({balance_ratio:.1%})")
        elif balance_ratio > 2.0:
            checks.append(f"WARNING: Excess generation ({balance_ratio:.1%})")

    # 3. Connectivity check (for links/lines)
    if len(network.lines) > 0 or len(network.links) > 0:
        # Check if buses are connected
        pass

    return checks
```

### Testing Strategy

Each increment should have automated validation:

1. **Base Model Tests**
   - Assert buses exist
   - Assert carriers exist
   - Assert snapshots exist
   - Print summary

2. **Component Addition Tests**
   - Assert expected components added
   - Check capacities are reasonable
   - Verify attributes are set correctly

3. **Balance Tests**
   - Compare total generation vs. demand
   - Warn if severely imbalanced

4. **Optimization Tests**
   - Check solver status
   - Verify objective value is reasonable
   - Ensure components are used (not all zero)

---

## Implementation Phases

### Phase 1: Core Infrastructure (Essential)

**Priority: HIGH**

**Tasks**:
1. Create `incremental_builder.py` with `IncrementalBuilder` class skeleton
2. Implement `build_base_model()` method
   - Reuse: `create_custom_network`, `add_snapshots`, `add_carriers`, `add_buses_and_areas`
3. Implement `filter_capacity_data()` utility function
4. Implement `add_components()` method
   - Reuse: `process_capacity_data`, `add_capacities`
5. Create minimal test script to verify it works

**Success Criteria**:
- Can create empty network
- Can add filtered components
- No errors in basic workflow

**Estimated Complexity**: Medium

---

### Phase 2: Validation & Inspection (Essential)

**Priority: HIGH**

**Tasks**:
1. Implement `validate_network_state()` utility
   - Structure checks
   - Balance checks
   - Connectivity checks
2. Implement `generate_inspection_report()` utility
   - Summary reports
   - Detailed breakdowns
   - Balance analysis
3. Add `inspect()` method to builder
4. Add `validate_stage()` method to builder
5. Create test cases for validation logic

**Success Criteria**:
- Can detect imbalanced networks
- Can generate human-readable reports
- Validation catches common issues

**Estimated Complexity**: Low-Medium

---

### Phase 3: Optimization Integration (Important)

**Priority: MEDIUM-HIGH

**Tasks**:
1. Implement `optimize()` method
   - Wrap `optimise_network` from existing code
   - Add error handling for infeasible models
   - Add validation of optimization results
2. Add optimization result inspection
3. Create test cases for optimization
   - Test with balanced model (should succeed)
   - Test with unbalanced model (should fail gracefully)

**Success Criteria**:
- Can run optimization on incrementally built model
- Clear error messages when infeasible
- Results inspection shows meaningful data

**Estimated Complexity**: Low (mostly reusing existing code)

---

### Phase 4: Configuration & Persistence (Important)

**Priority: MEDIUM**

**Tasks**:
1. Implement YAML configuration parsing
2. Add `from_config()` class method
3. Implement `save_checkpoint()` method
4. Implement `load_checkpoint()` method
5. Create example configuration files
   - `minimal_model.yaml`
   - `electricity_only.yaml`
   - `progressive_build.yaml`

**Success Criteria**:
- Can build from YAML config
- Can save and restore network state
- Checkpoints are portable

**Estimated Complexity**: Medium

---

### Phase 5: Advanced Features (Optional)

**Priority: LOW**

**Tasks**:
1. Interactive command-line mode
2. Scenario comparison utility
3. Sensitivity analysis utility
4. Component impact analysis
5. Visualization helpers

**Success Criteria**:
- User can interactively build model
- Can compare multiple scenarios
- Can analyze parameter sensitivity

**Estimated Complexity**: High

---

## Key Design Decisions

### 1. Filtering Approach

**Decision**: Filter at the capacity data level, before processing

**Rationale**:
- Cleaner than filtering after processing
- Reduces unnecessary computation
- Easier to understand what's included

**Implementation**: `filter_capacity_data()` function

### 2. Existing Code Reuse

**Decision**: Maximum reuse of existing functions

**Rationale**:
- Proven, tested code
- Maintains compatibility with main codebase
- Reduces maintenance burden
- Faster implementation

**Key Functions Reused**: All building functions from `build_network.py`

### 3. Configuration vs. Code

**Decision**: Support both YAML config and programmatic API

**Rationale**:
- YAML for reproducibility and simple cases
- Programmatic API for flexibility and experimentation
- Users can choose their preference

### 4. Validation Strategy

**Decision**: Optional validation with clear warnings

**Rationale**:
- Don't block user from building "bad" models (learning tool)
- But warn them about issues
- Let them learn from failures

---

## Critical Files Reference

### To Understand

1. **[run_simulation.py:48-107](src/pypsa_pl/run_simulation.py#L48-L107)**
   - The `run_simulation` function shows the complete orchestration
   - Lines 58-70 show exact sequence: load inputs → create network → add components → optimize

2. **[build_network.py:40-126](src/pypsa_pl/build_network.py#L40-L126)**
   - `load_and_preprocess_inputs`: Loads 6 CSV files and pivots them
   - Shows how inputs are structured

3. **[build_network.py:129-319](src/pypsa_pl/build_network.py#L129-L319)**
   - `create_custom_network`: Creates network with custom Area component
   - Shows network initialization

4. **[build_network.py:861-1132](src/pypsa_pl/build_network.py#L861-L1132)**
   - `add_capacities`: Main function that adds all component types
   - Shows how generators, links, lines, stores are added

5. **[run_pypsa_pl_2025_example.py:35-279](scripts/run_pypsa_pl_2025_example.py#L35-L279)**
   - `define_scenarios`: Shows how parameters are structured
   - `custom_input_operation`: Shows how to filter/modify inputs
   - Good reference for parameter values

### To Modify/Create

1. **`scripts/incremental_builder.py`** (NEW)
   - Main implementation file
   - ~500-800 lines estimated

2. **`scripts/incremental_builder_utils.py`** (NEW)
   - Utility functions
   - ~200-300 lines estimated

3. **`scripts/incremental_builder_config.yaml`** (NEW)
   - Example configuration
   - ~50-100 lines

---

## Testing & Verification Plan

### Unit Tests

Create `tests/test_incremental_builder.py`:

```python
def test_base_model_creation():
    """Test empty network creation"""
    builder = IncrementalBuilder(year=2025, timeseries='mini')
    builder.build_base_model()
    assert len(builder.network.buses) > 0
    assert len(builder.network.carriers) > 0

def test_component_filtering():
    """Test filtering capacity data"""
    df_filtered = filter_capacity_data(df, {'technology': ['wind_onshore']})
    assert 'wind_onshore' in df_filtered.technology.unique()
    assert len(df_filtered.technology.unique()) == 1

def test_add_generation():
    """Test adding generators"""
    builder = IncrementalBuilder(year=2025, timeseries='mini')
    builder.build_base_model()
    builder.add_components('Generator', {'technology': ['hard_coal_power_old']})
    assert len(builder.network.generators) > 0

def test_optimization_infeasible():
    """Test optimization with insufficient generation"""
    builder = IncrementalBuilder(year=2025, timeseries='mini')
    builder.build_base_model()
    builder.add_components('Generator', {'technology': ['hard_coal_power_old']})
    builder.add_components('Generator', {'carrier': ['electricity_final_use']})
    # Should fail or warn - insufficient generation
    with pytest.raises(OptimizationFailedError):
        builder.optimize()

def test_optimization_feasible():
    """Test optimization with sufficient generation"""
    builder = IncrementalBuilder(year=2025, timeseries='mini')
    builder.build_base_model()
    # Add sufficient generation
    builder.add_components('Generator', {
        'technology': ['hard_coal_power_old', 'wind_onshore', 'solar_PV_ground']
    })
    builder.add_components('Generator', {'carrier': ['electricity_final_use']})
    # Should succeed
    builder.optimize()
    assert builder.network.meta['solver_status'].startswith('ok')
```

### Integration Tests

**Minimal Model Test**:
1. Build base model
2. Add single generator
3. Add demand
4. Verify imbalance detected
5. Add more generation
6. Optimize
7. Verify results

**Progressive Build Test**:
1. Build from configuration
2. Execute all stages
3. Verify each stage adds expected components
4. Optimize at end
5. Verify feasible solution

### Manual Testing Workflow

**Day 1: Basic Functionality**
1. Create minimal model with just coal
2. Add demand
3. Try to optimize (should fail)
4. Add more generation
5. Optimize (should succeed)
6. Inspect results

**Day 2: Storage & Links**
1. Start with balanced model from Day 1
2. Add batteries
3. Optimize and compare with/without storage
4. Add transmission lines
5. Optimize and analyze

**Day 3: Constraints**
1. Start with full generation model
2. Add CO2 constraints
3. Observe how generation mix changes
4. Add capacity constraints
5. Observe investment decisions

---

## Success Criteria

### Phase 1 Complete
✓ Can create empty network structure
✓ Can add filtered components
✓ Basic workflow runs without errors

### Phase 2 Complete
✓ Validation detects common issues
✓ Inspection reports are clear and useful
✓ Can track balance and feasibility

### Phase 3 Complete
✓ Can optimize incrementally built models
✓ Clear error messages for infeasible models
✓ Results inspection shows meaningful data

### Phase 4 Complete
✓ Can build from YAML configuration
✓ Can save and restore checkpoints
✓ Example configs work out of the box

### Overall Success
✓ User understands how PyPSA model works
✓ User can experiment with different configurations
✓ User can debug model issues systematically
✓ Learning curve is significantly reduced

---

## Risks & Mitigations

### Risk 1: Complexity Underestimation

**Risk**: The model has many interdependencies that break when built incrementally

**Mitigation**:
- Start with simplest possible model (single area, single carrier)
- Test each increment thoroughly
- Add complexity gradually

### Risk 2: Performance Issues

**Risk**: Loading full inputs for filtering is slow

**Mitigation**:
- Profile code if performance is an issue
- Consider caching inputs
- Use mini timeseries for testing

### Risk 3: Maintenance Burden

**Risk**: Changes to main codebase break incremental builder

**Mitigation**:
- Maximize reuse of existing functions
- Minimize custom logic
- Document dependencies clearly

### Risk 4: Optimization Solver Sensitivity

**Risk**: Small models behave differently than full models

**Mitigation**:
- Document expected behavior
- Add warnings for "unusual" configurations
- Provide examples that work well

---

## Next Steps After Implementation

1. **Documentation**
   - Write user guide for incremental builder
   - Create tutorial notebooks
   - Document common patterns

2. **Examples**
   - Create example scripts for common use cases
   - Add to documentation

3. **Integration**
   - Consider adding to main package
   - Add tests to CI/CD
   - Update main README

4. **Advanced Features**
   - Add visualization helpers
   - Add comparison utilities
   - Add sensitivity analysis tools

---

## Questions to Resolve Before Implementation

1. **Parameter Handling**: Should the builder use full params dict or minimal subset?
   - **Recommendation**: Start with minimal subset, expand as needed

2. **Timeseries**: Which default timeseries to use (mini/medium/full)?
   - **Recommendation**: Default to 'mini' for fast iteration

3. **Checkpoints**: Format for saving state (CSV folder vs. single file)?
   - **Recommendation**: Use network.export_to_csv_folder() for compatibility

4. **Configuration**: YAML structure - flat or nested?
   - **Recommendation**: Nested by stage (as shown in examples)

---

## Appendix: Component Type Details

### Generators
- **Positive** (supply): coal, gas, nuclear, wind, solar, hydro
- **Negative** (demand): electricity final use, heat final use, etc.
- Key attributes: p_nom, p_min_pu, p_max_pu, marginal_cost

### Links
- Energy converters: heat pumps, boilers, electrolysis
- Transmission: interconnectors
- Key attributes: p_nom, efficiency, bus0, bus1

### Lines
- High-voltage transmission (AC)
- Key attributes: s_nom, length, x (reactance)

### Stores
- Energy storage: batteries, PSH, hydrogen storage
- Key attributes: e_nom, standing_loss, e_cyclic

### GlobalConstraints
- Operational limits: flow constraints
- Investment limits: capacity addition potentials
- Key attributes: sense (==, >=, <=), constant (limit value)

---

## Appendix: Data Flow Diagram

```
Input CSV Files (6 files)
        ↓
load_and_preprocess_inputs()
        ↓
create_custom_network() → Empty Network
        ↓
add_snapshots() → + Time Dimension
        ↓
add_carriers() → + Energy Types
        ↓
add_buses_and_areas() → + Network Nodes
        ↓
process_capacity_data() → Capacity Data + Costs + Constraints
        ↓
define_time_dependent_attributes() → Time-Varying Profiles
        ↓
add_capacities() → + Generators, Links, Lines, Stores
        ↓
add_energy_flow_constraints() → + Global Constraints
        ↓
add_capacity_constraints() → + Capacity Limits
        ↓
optimise_network() → Optimized Network
        ↓
Results & Analysis
```

**Incremental Builder Approach**: Allow user to stop and inspect at any arrow (↓) in this flow!

---

*End of Implementation Plan*
