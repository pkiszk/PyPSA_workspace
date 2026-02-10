#!/usr/bin/env python3
"""
PSE API Streamlit GUI

Interactive browser-based tool to pull data from the PSE (Polskie Sieci
Elektroenergetyczne) market-data API at https://api.raporty.pse.pl/api.

Usage:
    streamlit run pse_gui.py

Known endpoints are pre-loaded with field descriptions. Any other endpoint
can be explored via the "Custom" option with automatic field discovery.
"""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.raporty.pse.pl/api"

# Fields that are common to (almost) every endpoint — shown but not filtered
COMMON_FIELDS = {
    "dtime_utc": "UTC timestamp of the 15-min interval",
    "period_utc": "UTC period range label (e.g. '00:00 – 00:15')",
    "dtime": "Local (Polish) timestamp",
    "period": "Local period range label",
    "business_date": "Trading/business date (YYYY-MM-DD)",
    "publication_ts": "Data publication timestamp – local time",
    "publication_ts_utc": "Data publication timestamp – UTC",
}

# ---------------------------------------------------------------------------
# Endpoint catalog  (hard-coded; PSE API has no $metadata endpoint)
# Verified live 2026-02-10 by probing api.raporty.pse.pl
# ---------------------------------------------------------------------------

# Common fields for daily-resolution endpoints (no period/period_utc)
DAILY_FIELDS = {
    "dtime_utc": "UTC timestamp (daily)",
    "dtime": "Local timestamp (daily)",
    "business_date": "Business/trading date (YYYY-MM-DD)",
    "publication_ts": "Data publication timestamp – local time",
    "publication_ts_utc": "Data publication timestamp – UTC",
}

ENDPOINT_CATALOG: dict[str, dict] = {

    # ── Generation & demand ──────────────────────────────────────────────────

    "his-wlk-cal": {
        "label": "his-wlk-cal – Historical generation & demand",
        "description": (
            "15-minute actual generation by technology and total system demand. "
            "Primary source for wind, PV, coal/gas/hydro, and system demand analysis."
        ),
        "fields": {
            **COMMON_FIELDS,
            "jg": "Total gross generation of the KSE system [MW]",
            "pv": "Solar PV generation [MW]",
            "wi": "Wind generation [MW]",
            "demand": "Total system demand [MW]",
            "jga": "Generation – cogeneration / other [MW]",
            "jgm": "Generation – hard coal [MW]",
            "jgo": "Generation – lignite [MW]",
            "jgm1": "Generation – hard coal group 1 [MW]",
            "jgm2": "Generation – hard coal group 2 [MW]",
            "jgw1": "Generation – hydro group 1 [MW]",
            "jgw2": "Generation – hydro group 2 (pumped storage) [MW]",
            "jgz1": "Generation – gas group 1 [MW]",
            "jgz2": "Generation – gas group 2 [MW]",
            "jgz3": "Generation – gas group 3 [MW]",
            "jnwrb": "Non-schedulable RES generation (JNWRB) [MW]",
            "swm_p": "Pumped-storage pumping consumption [MW]",
            "swm_np": "Pumped-storage turbine generation [MW]",
        },
    },

    "kse-load": {
        "label": "kse-load – System load actual & forecast",
        "description": (
            "15-minute actual and day-ahead forecast of KSE total system load. "
            "Useful for demand analysis and forecast accuracy evaluation."
        ),
        "fields": {
            **COMMON_FIELDS,
            "load_actual": "Actual measured system load [MW]",
            "load_fcst": "Day-ahead forecast system load [MW]",
        },
    },

    "gen-jw": {
        "label": "gen-jw – Per-unit actual generation",
        "description": (
            "15-minute actual generation at individual generating unit level. "
            "Each row = one unit × one interval. Multiple rows share dtime_utc. "
            "Large dataset: ~hundreds of units × 96 intervals/day."
        ),
        "fields": {
            **COMMON_FIELDS,
            "power_plant": "Power plant name (e.g. 'Bełchatów')",
            "resource_code": "Generating unit code (e.g. 'BEL 2-02')",
            "operating_mode": "Operating mode – Polish (e.g. 'Generacja')",
            "operating_mode_eng": "Operating mode – English (e.g. 'Generation')",
            "wartosc": "Generation / power value [MW]",
        },
    },

    "pdgopkd": {
        "label": "pdgopkd – Generation dispatch plan (with cross-border flows)",
        "description": (
            "15-minute generation dispatch plan including cross-border parallel flows. "
            "Contains technology-level generation and available capacity forecasts used in balancing."
        ),
        "fields": {
            **COMMON_FIELDS,
            "kse_pow_dem": "KSE power demand forecast [MW]",
            "gen_fv": "Forecast solar PV generation [MW]",
            "gen_wi": "Forecast wind generation [MW]",
            "gen_jga": "Forecast cogeneration / other generation [MW]",
            "gen_jgo": "Forecast lignite generation [MW]",
            "gen_jgm_zak_1": "Forecast hard coal group 1 generation [MW]",
            "gen_jgm_zak_2": "Forecast hard coal group 2 generation [MW]",
            "gen_jgw_zak_1": "Forecast hydro group 1 generation [MW]",
            "gen_jgw_zak_2": "Forecast pumped-storage group 2 generation [MW]",
            "gen_jgz_zak_1": "Forecast gas group 1 generation [MW]",
            "gen_jgz_zak_2": "Forecast gas group 2 generation [MW]",
            "gen_jgz_zak_3": "Forecast gas group 3 generation [MW]",
            "gen_jgw_jgm_jgz_jga": "Total thermal+hydro+gas+cogen generation [MW]",
            "capacity_jga": "Available capacity – cogeneration [MW]",
            "capacity_jgo": "Available capacity – lignite [MW]",
            "capacity_jgm_zak_1": "Available capacity – hard coal group 1 [MW]",
            "capacity_jgm_zak_2": "Available capacity – hard coal group 2 [MW]",
            "capacity_jgw_zak_1": "Available capacity – hydro group 1 [MW]",
            "capacity_jgw_zak_2": "Available capacity – pumped storage group 2 [MW]",
            "capacity_jgz_zak_1": "Available capacity – gas group 1 [MW]",
            "capacity_jgz_zak_2": "Available capacity – gas group 2 [MW]",
            "capacity_jgz_zak_3": "Available capacity – gas group 3 [MW]",
            "capacity_jgw_jgm_jgz_jga": "Total available thermal+hydro+gas+cogen capacity [MW]",
            "rez_under": "Under-generation reserve [MW]",
            "rez_over_demand": "Over-demand reserve [MW]",
            "ogr_mwe": "MWe network constraints [MW]",
            "tot_jgm_char_pow": "Total characteristic power of coal units [MW]",
            "gen_not_activ_part": "Generation not in active participation [MW]",
            "dom_balance_exchange_par": "Domestic balance exchange – parallel [MW]",
            "dom_balance_exchange_non_par": "Domestic balance exchange – non-parallel [MW]",
        },
    },

    "pdgobpkd": {
        "label": "pdgobpkd – Generation dispatch plan (without cross-border flows)",
        "description": (
            "15-minute generation dispatch plan excluding cross-border parallel flows. "
            "Same structure as pdgopkd; used for domestic-only balancing analysis."
        ),
        "fields": {
            **COMMON_FIELDS,
            "kse_pow_dem": "KSE power demand forecast [MW]",
            "gen_fv": "Forecast solar PV generation [MW]",
            "gen_wi": "Forecast wind generation [MW]",
            "gen_jga": "Forecast cogeneration / other generation [MW]",
            "gen_jgo": "Forecast lignite generation [MW]",
            "gen_jgm_zak_1": "Forecast hard coal group 1 generation [MW]",
            "gen_jgm_zak_2": "Forecast hard coal group 2 generation [MW]",
            "gen_jgw_zak_1": "Forecast hydro group 1 generation [MW]",
            "gen_jgw_zak_2": "Forecast pumped-storage group 2 generation [MW]",
            "gen_jgz_zak_1": "Forecast gas group 1 generation [MW]",
            "gen_jgz_zak_2": "Forecast gas group 2 generation [MW]",
            "gen_jgz_zak_3": "Forecast gas group 3 generation [MW]",
            "gen_jgw_jgm_jgz_jga": "Total thermal+hydro+gas+cogen generation [MW]",
            "capacity_jga": "Available capacity – cogeneration [MW]",
            "capacity_jgo": "Available capacity – lignite [MW]",
            "capacity_jgm_zak_1": "Available capacity – hard coal group 1 [MW]",
            "capacity_jgm_zak_2": "Available capacity – hard coal group 2 [MW]",
            "capacity_jgw_zak_1": "Available capacity – hydro group 1 [MW]",
            "capacity_jgw_zak_2": "Available capacity – pumped storage group 2 [MW]",
            "capacity_jgz_zak_1": "Available capacity – gas group 1 [MW]",
            "capacity_jgz_zak_2": "Available capacity – gas group 2 [MW]",
            "capacity_jgz_zak_3": "Available capacity – gas group 3 [MW]",
            "capacity_jgw_jgm_jgz_jga": "Total available thermal+hydro+gas+cogen capacity [MW]",
            "rez_under": "Under-generation reserve [MW]",
            "rez_over_demand": "Over-demand reserve [MW]",
            "ogr_mwe": "MWe network constraints [MW]",
            "tot_jgm_char_pow": "Total characteristic power of coal units [MW]",
            "gen_not_activ_part": "Generation not in active participation [MW]",
            "dom_balance_exchange_par": "Domestic balance exchange – parallel [MW]",
            "dom_balance_exchange_non_par": "Domestic balance exchange – non-parallel [MW]",
        },
    },

    "pdwkseub": {
        "label": "pdwkseub – Available capacity per generating unit",
        "description": (
            "15-minute available generation capacity reported at individual unit level. "
            "Each row = one unit × one interval. Includes grid and non-US limitations."
        ),
        "fields": {
            **COMMON_FIELDS,
            "power_plant": "Power plant name",
            "resource_code": "Generating unit code",
            "available_capacity": "Total available capacity [MW]",
            "grid_lim": "Grid-related capacity limitation [MW]",
            "non_us_cap": "Non-US (non-balancing-service) available capacity [MW]",
        },
    },

    # ── Renewable & curtailment ──────────────────────────────────────────────

    "poze-redoze": {
        "label": "poze-redoze – Wind / PV curtailment",
        "description": (
            "15-minute wind and PV curtailment by cause: balance-driven (national oversupply) "
            "and network-driven (congestion). Values in MW; ×0.25 = MWh."
        ),
        "fields": {
            **COMMON_FIELDS,
            "pv_red_balance": "PV curtailment – balance reason [MW]",
            "pv_red_network": "PV curtailment – network congestion [MW]",
            "wi_red_balance": "Wind curtailment – balance reason [MW]",
            "wi_red_network": "Wind curtailment – network congestion [MW]",
        },
    },

    "wsp-wrm": {
        "label": "wsp-wrm – Wind/PV forecast correction coefficients (WRM)",
        "description": (
            "15-minute WRM correction coefficients used to adjust wind and PV generation "
            "forecasts for balancing. Also includes aFRR coefficients and max WMB value."
        ),
        "fields": {
            **COMMON_FIELDS,
            "ojnz_id": "Balancing period identifier",
            "az": "Wind generation forecast correction coefficient",
            "ws": "Solar PV generation correction coefficient",
            "afw": "aFRR – wind correction coefficient",
            "apv": "aFRR – PV correction coefficient",
            "wmb_max": "Maximum WMB (balancing reserve) value [MW]",
        },
    },

    # ── Grid & power flows ───────────────────────────────────────────────────

    "przeplywy-mocy": {
        "label": "przeplywy-mocy – Power flows on network sections",
        "description": (
            "15-minute actual power flows on designated KSE network cross-sections. "
            "Each row = one section × one interval. Positive = forward direction."
        ),
        "fields": {
            **COMMON_FIELDS,
            "section_code": "Network cross-section identifier",
            "value": "Power flow on the section [MW]",
        },
    },

    "pdgsz": {
        "label": "pdgsz – Grid conditions forecast",
        "description": (
            "Grid utilisation forecast showing whether a constrained condition is active, "
            "the forecast usage level, and total power demand. Validity window included."
        ),
        "fields": {
            "dtime_utc": "UTC timestamp",
            "dtime": "Local timestamp",
            "business_date": "Business/trading date (YYYY-MM-DD)",
            "is_active": "Grid constraint active flag [bool]",
            "usage_fcst": "Grid usage forecast [%]",
            "total_power_demand": "Total power demand forecast [MW]",
            "valid_from_ts": "Forecast validity start timestamp (local)",
            "valid_to_ts": "Forecast validity end timestamp (local)",
            "publication_ts": "Data publication timestamp – local time",
            "publication_ts_utc": "Data publication timestamp – UTC",
        },
    },

    "lolp": {
        "label": "lolp – Loss of Load Probability",
        "description": (
            "15-minute Loss of Load Probability across 10 scenario bands (b0–b9) "
            "with corresponding power shortfall values (p0–p9) for each band."
        ),
        "fields": {
            **COMMON_FIELDS,
            "ojnz_id": "Balancing period identifier",
            "b0": "LOLP probability – scenario band 0",
            "b1": "LOLP probability – scenario band 1",
            "b2": "LOLP probability – scenario band 2",
            "b3": "LOLP probability – scenario band 3",
            "b4": "LOLP probability – scenario band 4",
            "b5": "LOLP probability – scenario band 5",
            "b6": "LOLP probability – scenario band 6",
            "b7": "LOLP probability – scenario band 7",
            "b8": "LOLP probability – scenario band 8",
            "b9": "LOLP probability – scenario band 9",
            "p0": "Power shortfall – scenario band 0 [MW]",
            "p1": "Power shortfall – scenario band 1 [MW]",
            "p2": "Power shortfall – scenario band 2 [MW]",
            "p3": "Power shortfall – scenario band 3 [MW]",
            "p4": "Power shortfall – scenario band 4 [MW]",
            "p5": "Power shortfall – scenario band 5 [MW]",
            "p6": "Power shortfall – scenario band 6 [MW]",
            "p7": "Power shortfall – scenario band 7 [MW]",
            "p8": "Power shortfall – scenario band 8 [MW]",
            "p9": "Power shortfall – scenario band 9 [MW]",
        },
    },

    # ── Ancillary services ───────────────────────────────────────────────────

    "zmb": {
        "label": "zmb – Ancillary services demand (ZMB)",
        "description": (
            "15-minute demand for balancing ancillary services by product: "
            "FCR, aFRR, and mFRRd, in both up (g) and down (d) directions."
        ),
        "fields": {
            **COMMON_FIELDS,
            "zmb_fcrd": "FCR downward demand [MW]",
            "zmb_fcrg": "FCR upward demand [MW]",
            "zmb_afrrd": "aFRR downward demand [MW]",
            "zmb_afrrg": "aFRR upward demand [MW]",
            "zmb_frrd": "mFRRd downward demand [MW]",
            "zmb_frrg": "mFRRd upward demand [MW]",
            "zmb_rrd": "RR downward demand [MW]",
            "zmb_rrg": "RR upward demand [MW]",
        },
    },

    "mbp-tp": {
        "label": "mbp-tp – Ancillary services capacity plan (bid-based, daily)",
        "description": (
            "Daily contracted ancillary service capacity plan from the balancing market, "
            "broken down by FCR, aFRR, mFRRd, and RR. Daily resolution (no period field)."
        ),
        "fields": {
            **DAILY_FIELDS,
            "onmbp": "Required minimum operating reserve [MW]",
            "rr_d": "Replacement Reserve downward [MW]",
            "rr_g": "Replacement Reserve upward [MW]",
            "fcr_d": "Frequency Containment Reserve downward [MW]",
            "fcr_g": "Frequency Containment Reserve upward [MW]",
            "afrr_d": "aFRR downward capacity [MW]",
            "afrr_g": "aFRR upward capacity [MW]",
            "mfrrd_d": "mFRRd downward capacity [MW]",
            "mfrrd_g": "mFRRd upward capacity [MW]",
        },
    },

    "cmbp-tp": {
        "label": "cmbp-tp – Total ancillary services capacity plan (daily)",
        "description": (
            "Daily total contracted ancillary service capacity plan (from all sources). "
            "Daily resolution. Similar to mbp-tp but includes all procurement channels."
        ),
        "fields": {
            **DAILY_FIELDS,
            "onmb": "Required operating reserve [MW]",
            "rr_d": "Replacement Reserve downward [MW]",
            "rr_g": "Replacement Reserve upward [MW]",
            "fcr_d": "Frequency Containment Reserve downward [MW]",
            "fcr_g": "Frequency Containment Reserve upward [MW]",
            "afrr_d": "aFRR downward capacity [MW]",
            "afrr_g": "aFRR upward capacity [MW]",
            "mfrrd_d": "mFRRd downward capacity [MW]",
            "mfrrd_g": "mFRRd upward capacity [MW]",
        },
    },

    "mbu-tu": {
        "label": "mbu-tu – Ancillary services actual utilisation (15-min)",
        "description": (
            "15-minute actual utilisation of contracted ancillary services by product "
            "(FCR, aFRR, mFRRd), in both up (g) and down (d) directions."
        ),
        "fields": {
            **COMMON_FIELDS,
            "fcr_d": "FCR downward utilisation [MW]",
            "fcr_g": "FCR upward utilisation [MW]",
            "afrr_d": "aFRR downward utilisation [MW]",
            "afrr_g": "aFRR upward utilisation [MW]",
            "mfrrd_d": "mFRRd downward utilisation [MW]",
            "mfrrd_g": "mFRRd upward utilisation [MW]",
        },
    },

    "cmbu-tu": {
        "label": "cmbu-tu – Total ancillary services utilisation (15-min)",
        "description": (
            "15-minute total utilisation of ancillary services from all sources. "
            "Same structure as mbu-tu but aggregated across procurement channels."
        ),
        "fields": {
            **COMMON_FIELDS,
            "fcr_d": "FCR downward utilisation [MW]",
            "fcr_g": "FCR upward utilisation [MW]",
            "afrr_d": "aFRR downward utilisation [MW]",
            "afrr_g": "aFRR upward utilisation [MW]",
            "mfrrd_d": "mFRRd downward utilisation [MW]",
            "mfrrd_g": "mFRRd upward utilisation [MW]",
        },
    },

    "popmb-rmb": {
        "label": "popmb-rmb – Ancillary services procurement volumes (daily)",
        "description": (
            "Daily ancillary services capacity procured on the balancing market (RMB), "
            "broken down by reserve type. One row per reserve product per day."
        ),
        "fields": {
            **DAILY_FIELDS,
            "reserve_type": "Reserve product type (e.g. FCR, aFRR, mFRRd, RR)",
            "com": "Contracted capacity [MW]",
            "pom": "Offered capacity [MW]",
            "comrr": "Replacement Reserve contracted [MW]",
            "onmbp": "Required minimum operating reserve [MW]",
        },
    },

    # ── Balancing market prices ──────────────────────────────────────────────

    "rce-pln": {
        "label": "rce-pln – Real-time Clearing Energy price (PLN/MWh)",
        "description": (
            "15-minute Real-time Clearing Energy (RCE) price used for imbalance settlement. "
            "This is the key balancing market price signal in the Polish system."
        ),
        "fields": {
            **COMMON_FIELDS,
            "rce_pln": "RCE price [PLN/MWh]",
        },
    },

    "sk": {
        "label": "sk – Supplementary Contract price (SK)",
        "description": (
            "15-minute Supplementary Contract (SK) price – actual and two forecasts. "
            "SK is an ancillary price component in Polish balancing settlement."
        ),
        "fields": {
            **COMMON_FIELDS,
            "sk_cost": "Supplementary Contract actual price [PLN/MWh]",
            "sk_d_fcst": "SK forecast for current day (D) [PLN/MWh]",
            "sk_d1_fcst": "SK forecast for next day (D+1) [PLN/MWh]",
        },
    },

    "cor": {
        "label": "cor – Cost of Reserves (COR) forecast & actual",
        "description": (
            "15-minute Cost of Reserves (COR) – actual settlement cost and day-ahead forecast. "
            "COR is a system services charge allocated across market participants."
        ),
        "fields": {
            **COMMON_FIELDS,
            "cor_cost": "Actual cost of reserves [PLN/MWh]",
            "cor_fcst": "Day-ahead forecast cost of reserves [PLN/MWh]",
        },
    },

    "csdac-pln": {
        "label": "csdac-pln – CSDAC day-ahead market price (PLN/MWh)",
        "description": (
            "15-minute Cross-border Single Day-Ahead Coupling (CSDAC) clearing price in PLN. "
            "Reflects the European day-ahead market price converted to PLN."
        ),
        "fields": {
            **COMMON_FIELDS,
            "csdac_pln": "CSDAC day-ahead price [PLN/MWh]",
        },
    },

    "energy-prices": {
        "label": "energy-prices – Comprehensive energy price table",
        "description": (
            "15-minute combined table of all key energy prices and system balance: "
            "SK, COR, CSDAC, settlement costs, balance power. Useful as a single-source price dataset."
        ),
        "fields": {
            **COMMON_FIELDS,
            "balance": "System energy balance (imbalance volume) [MWh]",
            "balance_power": "System balance power [MW]",
            "sk_cost": "Supplementary Contract price [PLN/MWh]",
            "sk_cost_power": "Supplementary Contract power-weighted price [PLN/MWh]",
            "cen_cost": "Balancing energy price (CEN) [PLN/MWh]",
            "cor_cost": "Cost of reserves (COR) [PLN/MWh]",
            "csdac_pln": "CSDAC day-ahead price [PLN/MWh]",
            "ceb_pp_cost": "Energy balance settlement cost – downward [PLN/MWh]",
            "ceb_sr_cost": "Energy balance settlement cost – upward [PLN/MWh]",
        },
    },

    "ro-prog": {
        "label": "ro-prog – Regulation Obligation forecast (RO)",
        "description": (
            "15-minute forecast of the Regulation Obligation (RO) – "
            "the anticipated volume of regulation energy required."
        ),
        "fields": {
            **COMMON_FIELDS,
            "ro_fcst": "Regulation Obligation forecast [MW]",
        },
    },

    "ro-rozl": {
        "label": "ro-rozl – Regulation Obligation settlement cost",
        "description": (
            "15-minute Regulation Obligation (RO) settlement cost. "
            "Represents the cost charged to participants for regulation energy."
        ),
        "fields": {
            **COMMON_FIELDS,
            "ro_cost": "Regulation Obligation settlement cost [PLN]",
        },
    },

    # ── Settlement ───────────────────────────────────────────────────────────

    "en-rozl": {
        "label": "en-rozl – Imbalance energy settlement",
        "description": (
            "15-minute imbalance energy settlement volumes: "
            "energy delivered downward (en_d) and upward (en_w), plus net balance."
        ),
        "fields": {
            **COMMON_FIELDS,
            "balance": "Net system energy balance [MWh]",
            "en_d": "Imbalance energy – downward (delivered) [MWh]",
            "en_w": "Imbalance energy – upward (delivered) [MWh]",
        },
    },

    "eb-rozl": {
        "label": "eb-rozl – Energy balance settlement",
        "description": (
            "15-minute energy balance settlement volumes split by direction and type: "
            "power plant contributions and aFRR volumes."
        ),
        "fields": {
            **COMMON_FIELDS,
            "eb_d_pp": "Energy balance downward – power plant contribution [MWh]",
            "eb_w_pp": "Energy balance upward – power plant contribution [MWh]",
            "eb_afrrd": "Energy balance – aFRR downward [MWh]",
            "eb_afrrg": "Energy balance – aFRR upward [MWh]",
        },
    },

    "zeb-rozl": {
        "label": "zeb-rozl – ZEB (external balancing energy) settlement",
        "description": (
            "15-minute settlement of external balancing energy (ZEB): "
            "volume and aFRR cost components."
        ),
        "fields": {
            **COMMON_FIELDS,
            "zebpp": "ZEB settlement volume [MWh]",
            "pzeb_afrrd_cost": "ZEB aFRR downward cost [PLN]",
            "pzeb_afrrg_cost": "ZEB aFRR upward cost [PLN]",
        },
    },

    "crb-rozl": {
        "label": "crb-rozl – Balancing market settlement costs",
        "description": (
            "15-minute balancing market settlement cost components: "
            "CEN, cross-border corrective energy, and energy balance settlement."
        ),
        "fields": {
            **COMMON_FIELDS,
            "cen_cost": "Balancing energy cost (CEN) [PLN]",
            "ckoeb_cost": "Cross-border corrective energy cost [PLN]",
            "ceb_pp_cost": "Energy balance settlement – downward [PLN]",
            "ceb_sr_cost": "Energy balance settlement – upward [PLN]",
            "ceb_sr_afrrd_cost": "aFRR downward energy balance settlement cost [PLN]",
            "ceb_sr_afrrg_cost": "aFRR upward energy balance settlement cost [PLN]",
        },
    },

    "krb-rozl": {
        "label": "krb-rozl – Capacity market settlement (KRB)",
        "description": (
            "15-minute capacity market (KRB) settlement: "
            "capacity obligations, contracts, and shortfalls."
        ),
        "fields": {
            **COMMON_FIELDS,
            "kb": "Capacity obligation [MW]",
            "ko": "Capacity contract [MW]",
            "kcz": "Capacity shortage / non-delivery [MW]",
        },
    },

    "kmb-kro-rozl": {
        "label": "kmb-kro-rozl – KMB/KRO settlement volumes",
        "description": (
            "15-minute KMB (balancing market capacity correction) and "
            "KRO (corrective operations) settlement volumes."
        ),
        "fields": {
            **COMMON_FIELDS,
            "kmb": "KMB balancing market capacity correction [MWh]",
            "kro": "KRO corrective operations volume [MWh]",
        },
    },

    "use-sprz-rbb": {
        "label": "use-sprz-rbb – Participant sales volume on balancing market (daily)",
        "description": (
            "Daily volume sold by balancing market participants on the RBB (balancing market). "
            "Daily resolution (no period field)."
        ),
        "fields": {
            **DAILY_FIELDS,
            "sprz_volume": "Sales volume on balancing market [MWh]",
        },
    },

    "use-sprz-rbn": {
        "label": "use-sprz-rbn – Participant day-ahead sales volume (daily)",
        "description": (
            "Daily day-ahead transaction volume per participant on the RBN (day-ahead market). "
            "Daily resolution (no period field)."
        ),
        "fields": {
            **DAILY_FIELDS,
            "day_ahead_tr_vol": "Day-ahead transaction volume [MWh]",
        },
    },
}

CUSTOM_OPTION = "— Custom endpoint —"

# ---------------------------------------------------------------------------
# Shared fetch utilities (ported from pse_export_cli.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchConfig:
    start_dt: datetime
    end_dt_exclusive: datetime
    page_size: int
    timeout_seconds: int


def format_dt(dt_value: datetime) -> str:
    return dt_value.strftime("%Y-%m-%d %H:%M:%S")


def build_filter(start_dt: datetime, end_dt_exclusive: datetime) -> str:
    return (
        f"dtime_utc ge '{format_dt(start_dt)}'"
        f" and dtime_utc lt '{format_dt(end_dt_exclusive)}'"
    )


def encode_params(params: dict) -> str:
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def fetch_json(url: str, params: dict | None, timeout_seconds: int) -> dict:
    if params:
        url = f"{url}?{encode_params(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "PSE-GUI/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as r:
        return json.load(r)


def fetch_all(
    endpoint: str,
    params: dict,
    timeout_seconds: int,
    progress_cb=None,
) -> list[dict]:
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    page = 0
    records: list[dict] = []
    next_url: str | None = url
    next_params: dict | None = dict(params)

    while next_url:
        page += 1
        data = fetch_json(next_url, next_params, timeout_seconds)
        values = data.get("value", [])
        records.extend(values)
        next_url = data.get("nextLink")
        next_params = None
        if progress_cb:
            progress_cb(page, len(values), len(records))

    return records


def normalize_dtime_utc(df: pd.DataFrame) -> pd.DataFrame:
    if "dtime_utc" not in df.columns:
        return df
    dt = pd.to_datetime(df["dtime_utc"], errors="coerce")
    invalid = dt.isna()
    if invalid.any():
        df = df.loc[~invalid].copy()
        dt = dt.loc[~invalid]
    df["dtime_utc"] = dt.dt.strftime("%Y-%m-%d %H:%M:%S")
    return df.sort_values("dtime_utc").reset_index(drop=True)


def coerce_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Dynamic endpoint discovery
# ---------------------------------------------------------------------------


def probe_endpoint(endpoint: str, timeout: int = 15) -> list[str] | str:
    """Return field names for an arbitrary endpoint by fetching 1 recent record.

    Returns a list of field names on success, or an error string on failure.
    """
    params = {"$first": 1, "$orderby": "dtime_utc desc"}
    try:
        data = fetch_json(
            f"{BASE_URL}/{endpoint.strip().lstrip('/')}",
            params,
            timeout,
        )
        values = data.get("value", [])
        if not values:
            return "Endpoint returned no records (may need a date filter)."
        return list(values[0].keys())
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Streamlit app
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="PSE API Explorer",
        page_icon="⚡",
        layout="wide",
    )
    st.title("⚡ PSE API Explorer")
    st.caption(
        "Pull data from [api.raporty.pse.pl](https://api.raporty.pse.pl/api) "
        "and download as CSV."
    )

    # ── Sidebar ─────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Date range")
        start_date = st.date_input(
            "Start date",
            value=date(2025, 1, 1),
            min_value=date(2020, 1, 1),
            max_value=date.today(),
        )
        end_date = st.date_input(
            "End date (inclusive)",
            value=datetime.now(timezone.utc).date() - timedelta(days=1),
            min_value=date(2020, 1, 1),
            max_value=date.today(),
        )

        st.header("Settings")
        page_size = st.number_input("Page size", min_value=100, max_value=5000, value=1000, step=100)
        timeout = st.number_input("Timeout (s)", min_value=10, max_value=300, value=60, step=10)
        out_dir = st.text_input("Output directory", value=".")

        st.divider()
        st.caption("Tip: large date ranges with per-unit data (gen-jw) can be tens of thousands of rows per day.")

    # ── Main – Endpoint selection ────────────────────────────────────────────
    endpoint_options = list(ENDPOINT_CATALOG.keys()) + [CUSTOM_OPTION]
    endpoint_labels = [ENDPOINT_CATALOG[k]["label"] for k in ENDPOINT_CATALOG] + [CUSTOM_OPTION]
    label_to_key = dict(zip(endpoint_labels, endpoint_options))

    selected_label = st.selectbox("Endpoint", endpoint_labels)
    selected_key = label_to_key[selected_label]

    # ── Custom endpoint probe ───────────────────────────────────────────────
    discovered_fields: list[str] = []

    if selected_key == CUSTOM_OPTION:
        col_inp, col_btn = st.columns([3, 1])
        custom_ep = col_inp.text_input(
            "Endpoint name", placeholder="e.g.  gen-jw  or  his-wlk-cal"
        )
        probe_clicked = col_btn.button("Probe", use_container_width=True)

        if "probed_ep" not in st.session_state:
            st.session_state.probed_ep = ""
            st.session_state.probed_fields = []
            st.session_state.probe_error = ""

        if probe_clicked and custom_ep.strip():
            result = probe_endpoint(custom_ep.strip(), timeout=int(timeout))
            if isinstance(result, list):
                st.session_state.probed_ep = custom_ep.strip()
                st.session_state.probed_fields = result
                st.session_state.probe_error = ""
            else:
                st.session_state.probe_error = result
                st.session_state.probed_fields = []

        if st.session_state.probe_error:
            st.error(st.session_state.probe_error)

        if st.session_state.probed_fields:
            st.success(
                f"Discovered {len(st.session_state.probed_fields)} fields "
                f"from `{st.session_state.probed_ep}`."
            )
            discovered_fields = st.session_state.probed_fields
            active_endpoint = st.session_state.probed_ep
            field_map = {f: f for f in discovered_fields}  # no descriptions
        else:
            st.info("Enter an endpoint name and click **Probe** to discover its fields.")
            st.stop()
    else:
        active_endpoint = selected_key
        catalog_entry = ENDPOINT_CATALOG[selected_key]
        st.info(catalog_entry["description"])
        field_map = catalog_entry["fields"]  # name → description

    # ── Field selector ──────────────────────────────────────────────────────
    st.subheader("Fields")

    # Build display labels: "field_name — description" (or just name)
    all_field_names = list(field_map.keys())
    field_display = {
        name: (f"{name} — {desc}" if desc != name else name)
        for name, desc in field_map.items()
    }
    display_to_name = {v: k for k, v in field_display.items()}
    display_labels = list(field_display.values())

    col_all, col_none = st.columns([1, 6])
    select_all = col_all.button("Select all")
    deselect_all = col_none.button("Deselect all")

    if "selected_displays" not in st.session_state or selected_key != st.session_state.get("last_endpoint"):
        st.session_state.selected_displays = display_labels
        st.session_state.last_endpoint = selected_key

    if select_all:
        st.session_state.selected_displays = display_labels
    if deselect_all:
        st.session_state.selected_displays = []

    chosen_displays = st.multiselect(
        "Select fields to export",
        options=display_labels,
        default=st.session_state.selected_displays,
        label_visibility="collapsed",
    )
    st.session_state.selected_displays = chosen_displays
    chosen_fields = [display_to_name[d] for d in chosen_displays]

    if not chosen_fields:
        st.warning("Select at least one field.")

    # ── Export ───────────────────────────────────────────────────────────────
    st.divider()

    if st.button("🚀 Export to CSV", disabled=(not chosen_fields or end_date < start_date)):

        if end_date < start_date:
            st.error("End date must be on or after start date.")
            st.stop()

        start_dt = datetime.combine(start_date, time.min)
        end_dt_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)
        config = FetchConfig(
            start_dt=start_dt,
            end_dt_exclusive=end_dt_exclusive,
            page_size=int(page_size),
            timeout_seconds=int(timeout),
        )

        params = {
            "$filter": build_filter(config.start_dt, config.end_dt_exclusive),
            "$orderby": "dtime_utc asc",
            "$first": config.page_size,
            "$select": ",".join(chosen_fields),
        }

        log_area = st.empty()
        log_lines: list[str] = []

        def on_page(page: int, count: int, total: int) -> None:
            log_lines.append(
                f"page {page}: +{count} records &nbsp;&nbsp;→ &nbsp;&nbsp;total {total}"
            )
            log_area.markdown("\n\n".join(log_lines[-10:]))

        with st.spinner("Fetching data…"):
            try:
                records = fetch_all(active_endpoint, params, config.timeout_seconds, on_page)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Fetch failed: {exc}")
                st.stop()

        if not records:
            st.warning("No records returned for the selected date range.")
            st.stop()

        df = pd.DataFrame.from_records(records)
        keep = [c for c in chosen_fields if c in df.columns]
        df = df[keep].copy()

        # Coerce numeric columns (non-string, non-date fields)
        skip_numeric = {
            "dtime_utc", "period_utc", "dtime", "period",
            "business_date", "publication_ts", "publication_ts_utc",
            "power_plant", "resource_code", "operating_mode", "operating_mode_eng",
        }
        numeric_cols = [c for c in df.columns if c not in skip_numeric]
        df = coerce_numeric(df, numeric_cols)
        df = normalize_dtime_utc(df)

        st.success(f"Fetched **{len(df):,} rows** × **{len(df.columns)} columns**.")

        # Save to disk
        from pathlib import Path
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = Path(out_dir) / f"PSE_{active_endpoint}_{timestamp}.csv"
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            df.to_csv(out_path, index=False)
            st.info(f"Saved to `{out_path}`")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Could not save to disk: {exc}")

        # In-browser download
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇ Download CSV",
            data=csv_bytes,
            file_name=out_path.name,
            mime="text/csv",
        )

        # Preview
        st.subheader(f"Preview (first 50 rows of {len(df):,})")
        st.dataframe(df.head(50), use_container_width=True)


def _running_in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:  # pragma: no cover - fallback for older streamlit
        return False
    return get_script_run_ctx() is not None


if __name__ == "__main__":
    # If invoked directly, re-launch via `streamlit run`.
    if _running_in_streamlit():
        main()
    else:
        import subprocess
        import sys
        raise SystemExit(
            subprocess.call(["streamlit", "run", __file__] + sys.argv[1:])
        )
