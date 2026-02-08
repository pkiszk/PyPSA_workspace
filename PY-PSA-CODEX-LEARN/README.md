# PY-PSA-CODEX-LEARN

Incremental PyPSA-PL model builder for learning and debugging. This tool reuses the existing `pypsa_pl` build/optimisation pipeline, but lets you add components step by step.

## Quickstart

From the repo root:

```bash
python PY-PSA-CODEX-LEARN/incremental_builder.py --config PY-PSA-CODEX-LEARN/configs/minimal_model.yaml --inspect summary
```

Or run the programmatic example:

```bash
python PY-PSA-CODEX-LEARN/examples/example_minimal.py
```

## Config files

- YAML requires `PyYAML` installed. If you do not have it, use JSON configs instead.
- Technology names and carrier names must match `pypsa-pl/data/input/technology_carrier_definitions;variant=full.csv`.

Example config keys:

```yaml
base_model:
  year: 2025
  timeseries: mini
  copperplate: true
  trade: true
  scenario_base: instrat_ambitious+trade
  params_override:
    constrained_energy_flows: none

stages:
  vres_generation:
    enabled: true
    component: Generator
    technologies: [wind onshore, solar PV ground]
  electricity_demand:
    enabled: true
    component: Generator
    carriers: [electricity HMV final use, electricity LV final use]

constraints:
  enabled: false

optimization:
  enabled: false
```

## Output locations

- Optimisation outputs: `PY-PSA-CODEX-LEARN/runs/<run_name>/output_network`
- Checkpoints: `PY-PSA-CODEX-LEARN/checkpoints/<name>`

## Notes

- This uses `pypsa_pl` from `pypsa-pl/src`. If imports fail, install the package in editable mode:
  - `pip install -e pypsa-pl`
- The tool is intended for incremental learning. It does not try to mirror every constraint used in the full scenario unless you enable them.
