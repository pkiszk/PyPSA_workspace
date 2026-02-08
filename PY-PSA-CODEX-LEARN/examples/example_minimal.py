from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from incremental_builder import IncrementalBuilder, build_default_params

params = build_default_params(year=2025, timeseries="mini", copperplate=True, trade=True)

builder = IncrementalBuilder(params)
builder.build_base_model()

builder.add_components(
    "Generator",
    filters={"technology": ["wind onshore", "solar PV ground"]},
)

builder.add_components(
    "Link",
    filters={"technology": ["hard coal power old"]},
)

builder.add_components(
    "Generator",
    filters={
        "carrier": [
            "electricity HMV final use",
            "electricity LV final use",
        ]
    },
)

print(builder.inspect("balance"))
