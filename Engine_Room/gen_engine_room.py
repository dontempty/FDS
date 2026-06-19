#!/usr/bin/env python3
"""
gen_engine_room.py — FDS input for the marine engine-room fire from
Lan et al. 2023 (Ocean Engineering 281:114890), Fig 1.

Geometry from Fig 1 (top view) + paper text:
  Domain         : 13 × 10 m floor plan, height 3 m (room height inferred
                   from Fig 6 monitoring planes z=2 m).
  Rooms          : (1) Main Engine Room  -- the larger, irregular area
                                            (most of the floor),
                   (2) Oil Separator Room -- bottom-right enclosed area,
                                            bounded by an internal wall at
                                            Y=3 and an internal wall at X=5.
  Internal walls : Y=3 wall (X=5..13) -- the long wall separating the two
                                          rooms, with a DOOR opening.
                   X=5 wall (Y=0..3)  -- short wall on the west side of
                                          the Oil Separator Room.
  Doors          : (a) South door -- opening in the Y=3 wall, around
                                     X=7..8.5, connecting Main Engine Room
                                     to Oil Separator Room.
                   (b) North door -- partial OPEN vent on the Y=10 outer
                                     wall, around X=2..3, connecting the
                                     Main Engine Room to outside.
  Equipment      : main engine (6.5 × 3.8 m, height = z_max/2),
                   preheater, fuel oil supply unit,
                   main engine oil setting tank ×2,
                   fuel oil setting tank ×2.
  Fire           : floor &VENT in the Oil Separator Room at X≈8..9, Y≈1.5..2.5
                   (Fig 1 red square).

z dimensions of equipment are reasonable assumptions (top view shows no
heights).  Main engine z2 is auto-rescaled to z_max/2 in build_input().

Strict geometry validation:
  - z_min must be 0.
  - Every equipment OBST and every wall OBST must fit inside the room.
  - Fire VENT must be inside the room.
  - Fire footprint must not overlap any floor-resting equipment.
  - mesh-split must divide IJK evenly.
"""

from __future__ import annotations
import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ============================================================================
# USER-EDITABLE SETTINGS  -- change ANY value here, then run
#     python3 gen_engine_room.py
# CLI flags (--chid, --ijk, --ventilation-method, ...) still override these
# at runtime so existing sbatch scripts continue to work.
# ============================================================================

# ---- Ventilation (Lan et al. 2023 Fig 2 + Table 4) ------------------------
# 1 = Method 1 (asymmetric): 1 intake outer_south top east (L=0.8485)
#                          + 1 exhaust OSR-MER divider OSR-face bottom west
# 2 = Method 2 (symmetric) : 2 intakes outer_south top corners (L=0.6)
#                          + 2 exhausts divider OSR-face bottom corners
# 3 = Method 3 (central)   : 1 intake divider top door-centred (L=0.8485)
#                          + 2 exhausts divider OSR-face bottom corners (L=0.6)
VENTILATION_METHOD   = 2
VENTILATION_VELOCITY = 1.0     # m/s (paper uses 1 or 3)

# ---- Ambient cabin air (Lan et al. 2023 Table 3) -------------------------
# TMPA = 20 °C (= 293.15 K).  Paper writes 293 K; the 0.15 K difference is
# negligible.  FDS computes ρ, Cp, ν, k, α, Pr internally from its standard
# air database at this temperature — at 20 °C, dry air gives:
#   ρ ≈ 1.204 kg/m³ (paper 1.205) ; Cp ≈ 1.005 kJ/(kg·K) ✓ ;
#   ν ≈ 1.51e-5 m²/s (paper 1.506e-5) ; k ≈ 0.0257 W/(m·K) (paper 0.0259) ;
#   α ≈ 2.12e-5 m²/s (paper 2.14e-5) ; Pr ≈ 0.713 (paper 0.703).
# Humidity left at FDS default (40 %); it shifts Cp by < 1 %.
TMPA = 20.0     # ambient air temperature (°C)

# ---- Fire (paper: D=1 m circular pool, area π/4 = 0.7854 m²) -------------
# We use a SQUARE pool of equal area centered at (8.25, 1.45):
#   side = √(π/4) = 0.8862 m  →  FIRE_XB = (7.807, 8.693, 1.007, 1.893)
# Pool matches paper Fig 6 monitoring slices x=8.1 / 8.4 (flank fire) and
# y=1.45 (longitudinal centerline) and z=2 (upper smoke layer).
# Resulting HRRPUA = HRR_PEAK_KW / 0.7854 ≈ 1099 kW/m² (matches paper Eq 2
# evaluation: 0.035·(1-e^-1.7)·42600·0.9 ≈ 861 ≈ 863 kW total).
FIRE_XB            = (7.807, 8.693, 1.007, 1.893)
# ---- Diesel fuel (paper Table 2) -----------------------------------------
# FDS predefined N-HEPTANE used as a diesel surrogate (matches the surrogate
# choice cited by Wang et al. 2022 in paper §2).  We override its built-in
# heat of combustion to the paper Table 2 diesel ΔH so the per-mass HRR↔MLR
# conversion inside FDS matches paper.  Other paper Table 2 fields
# (m_f,∞, X_chem, χ_conv, k_abs) are NOT directly settable in FDS:
#   - m_f,∞ and X_chem are already baked into the HRR peak via paper Eq (2),
#     and we drive the fire by HRRPUA = Q/A → FDS derives MLR from this.
#   - χ_conv is computed by FDS from the energy balance (≈ 1−χ_rad ≈ 0.7,
#     close to paper 0.6 once the 10% non-combustion loss is accounted for).
#   - k_abs is computed by FDS RadCal (paper §2.1 uses the same model).
FUEL                  = "N-HEPTANE"
HEAT_OF_COMBUSTION_KJKG = 42600.0  # paper Table 2 (kJ/kg)
RADIATIVE_FRACTION    = 0.3        # paper Table 2 ("Radiative heat transfer coefficient")
# Override soot/CO yields to represent diesel rather than the FDS n-heptane
# default.  Diesel produces substantially more soot (~0.04-0.05 kg/kg fuel)
# than n-heptane (~0.015), and the additional soot strengthens the ceiling
# hot-layer radiation feedback (paper §2.1 uses RadCal with k_abs=1.7).
# Set either to None to keep the FDS default for that species.
SOOT_YIELD            = 0.05       # diesel typical (n-heptane default ≈ 0.015)
CO_YIELD              = 0.02       # diesel typical (n-heptane default ≈ 0.006)
# Effective gas absorption coefficient (paper Table 2 = 1.7 m^-1).  FDS default
# RadCal computes a wavelength-resolved κ from soot+CO2+H2O; setting KAPPA0
# overrides it with a constant value across the whole spectrum.  When KAPPA0
# > 0 it replaces RadCal entirely.  Set to None to keep RadCal (FDS default).
KAPPA0                = 1.7        # paper Table 2 ("Effective absorption coefficient")

# ---- HRR ramp -- t² growth, then steady ; HRR_T2_POINTS=0 disables -------
HRR_T2_POINTS = 30          # >0 = generate t² ramp with N anchor points
HRR_T2_TPEAK  = 30.0        # time to peak HRR (s)
HRR_PEAK_KW   = 863.0       # paper Table 4 exact total HRR (HRRPUA = 863 with 1 m² pool)

# ---- Grid convergence T(z) -- instant + time-averaged --------------------
# For each gridconv sensor we emit two DEVCs: an instantaneous snapshot and
# a TEMPORAL_STATISTIC='TIME AVERAGE' that averages from GRIDCONV_AVG_START
# to T_END.  Pick AVG_START past the transient (t² growth reaches peak at
# HRR_T2_TPEAK, so steady state is typically t > ~3×HRR_T2_TPEAK).
GRIDCONV_AVG_START = 100.0   # seconds; t² ramp peaks at 30 s, so 100 s skips transient

# ---- Grid / time / mesh decomposition ------------------------------------
IJK         = (130, 100, 30)   # (NX, NY, NZ)
MESH_SPLIT  = (1, 1, 1)        # (MX, MY, MZ) sub-meshes for MPI
T_END       = 60.0             # seconds

# ---- Output cadence (seconds) --------------------------------------------
DT_DEVC   = 1.0
DT_HRR    = 1.0
DT_SLCF   = 2.0
DT_BNDF   = 30.0
DT_SL3D   = 2.0          # 3D SMOKE3D output cadence (only used when SMOKE3D_OUTPUT=True)
SMOKE3D_OUTPUT = False   # 3D SMOKE3D ON/OFF.  False → 5-15 % faster wall-clock
                         # but no SmokeView 3D smoke rendering.

# ---- Centerline DEVCs above fire ------------------------------------------
CENTERLINE_Q = ["THERMOCOUPLE", "TEMPERATURE", "W-VELOCITY",
                "VELOCITY", "HRRPUV", "VISIBILITY"]
CENTERLINE_SPEC = ["VOLUME FRACTION:CARBON MONOXIDE",
                   "VOLUME FRACTION:SOOT",
                   "VOLUME FRACTION:OXYGEN"]
CENTERLINE_N_POINTS = 10       # single-point DEVCs at evenly-spaced heights
# ============================================================================


# ---------- geometric primitives --------------------------------------------

@dataclass
class Eq:
    """A solid block (equipment).  XB = (x1,x2,y1,y2,z1,z2)."""
    label: str
    x1: float; x2: float
    y1: float; y2: float
    z1: float; z2: float
    color: str = "GRAY"


@dataclass
class Wall:
    """A solid thin wall (no SURF_IDS — just a building partition)."""
    label: str
    x1: float; x2: float
    y1: float; y2: float
    z1: float; z2: float
    color: str = "WHITE"


@dataclass
class Hole:
    """An &HOLE block that removes part of an existing OBST (door / window)."""
    label: str
    x1: float; x2: float
    y1: float; y2: float
    z1: float; z2: float


@dataclass
class ExtVent:
    """Partial OPEN vent on a domain face (a door / opening to outside)."""
    label: str
    x1: float; x2: float
    y1: float; y2: float
    z1: float; z2: float


@dataclass
class HVACVent:
    """Mechanical ventilation vent (intake or exhaust) on an outer-wall inner
    face.  Each is emitted as &VENT XB=... SURF_ID=... with VEL imposed."""
    label: str
    kind: str        # 'intake' or 'exhaust'
    x1: float; x2: float
    y1: float; y2: float
    z1: float; z2: float
    wall: str        # 'west' / 'east' / 'north' / 'south' (for labelling)


def vents_for_method(method: int, cfg) -> list[HVACVent]:
    """Vent layouts per Lan et al. 2023, Fig 2  --  per user spec.

    All vents face the y direction (rectangles in the X-Z plane), placed on
    one of three y walls:
        y = 0.2  -- inner (gas-side) face of the south outer wall (in OSR)
        y = 3.0  -- Main-Engine-Room-side face of the OSR ↔ MER divider wall
                   (the wall OBST occupies y=2.8..3.0; y=3.0 is the MER side)
        y = 9.8  -- inner (gas-side) face of the north outer wall
                    (user spec writes this wall as "y=10"; the vent face
                    is at y=9.8 because the wall OBST occupies y=9.8..10.0
                    and y=10 is the mesh boundary)

    Each square vent has edge length L (set per Method).  The notation
    `a~` means "starts at a, extends by L"; `~b` means "ends at b, starts
    at b-L".

    Method 1 (L = 0.8485)  -- asymmetric
        inlet_01 : x ends 13,  y=0.2,  z ends 3        (top-east of OSR south wall)
        inlet_02 : x ends 13,  y=3.0,  z ends 3        (top-east of MER-side divider)
        outlet_01: x starts 4, y=3.0,  z starts 0      (floor-west of MER-side divider)
        outlet_02: x starts 4, y=9.8,  z starts 0      (floor-west of north outer wall)

    Method 2 (L = 0.6)     -- symmetric
        4 inlets : both ends of x at y=0.2 and y=3.0, all at top (z ends 3)
        4 outlets: both ends of x at y=3.0 and y=9.8, all at floor (z starts 0)

    Method 3 (L = 0.8485 / outlets 0.6)  -- optimum
        2 inlets : centred on the OSR-MER door (x≈7.5±L/2),
                   at y=0.2 and y=3.0, top
        4 outlets: same 4 corner outlets as Method 2
    """
    if method not in (1, 2, 3):
        return []

    Y_SOUTH = 0.2     # OSR's south outer wall (gas side, in OSR)
    Y_OSR_N = 3.0     # OSR ↔ Main Engine Room divider (MER-side face; wall is y=2.8..3.0)
    Y_OSR_N_OSR = 2.8 # OSR-side face of the SAME divider wall (for outlets extracting FROM OSR)
    Y_NORTH = 9.8     # north outer wall (gas side, in Main Engine Room)
    X_W = 4.0         # west extreme of OSR + ventilated band (matches osr_north_wall x1)
    X_E = 13.0 - 0.2        # east extreme (= cfg.x_max)
    Z_TOP = cfg.z_max # 3.0
    Z_BOT = 0.0

    # Door between Main Engine Room and OSR (Hole "door2_main_to_osr") --
    # used to centre Method 3 inlets.  Falls back to x=7.5 if not present.
    door_cx = 7.5
    for h in cfg.holes:
        if "osr" in h.label.lower():
            door_cx = (h.x1 + h.x2) / 2
            break

    vents: list[HVACVent] = []

    if method == 1:
        # Paper Table 4 No.1: 1 inlet + 1 outlet, edge 0.8485 (area 0.72 m²),
        # v=1 m/s → 0.72 m³/s total.  Asymmetric: intake on outer_south top
        # east, exhaust on OSR-side of OSR-MER divider, bottom west.
        L = 0.8485
        vents += [
            HVACVent("inlet_01",  "intake",
                     X_E - L, X_E,     Y_SOUTH, Y_SOUTH, Z_TOP - L, Z_TOP, wall="outer_south"),
            HVACVent("inlet_02",  "intake",
                     X_E - L, X_E,    Y_OSR_N, Y_OSR_N, Z_TOP - L, Z_TOP, wall="osr_north_wall"),
            HVACVent("outlet_01", "exhaust",
                     X_W,     X_W + L, Y_OSR_N_OSR, Y_OSR_N_OSR, Z_BOT,     Z_BOT + L, wall="osr_north"),
            HVACVent("outlet_02", "exhaust",
                     X_W,     X_W + L, 10 - 0.2, 10 - 0.2, Z_BOT,     Z_BOT + L, wall="outer_north"),
        ]

    elif method == 2:
        # Paper Table 4 No.3: 2 inlets + 2 outlets, edge 0.6 (area 0.36 m² each),
        # 2 × 0.36 = 0.72 m³/s total at v=1 m/s.  Symmetric east/west pair:
        # inlets at outer_south top corners, outlets at OSR-side of divider
        # bottom corners.
        L = 0.6
        vents += [
            HVACVent("inlet_01", "intake",
                     X_E - L, X_E,     Y_SOUTH, Y_SOUTH, Z_TOP - L, Z_TOP, wall="outer_south"),
            HVACVent("inlet_02", "intake",
                     X_W,     X_W + L, Y_SOUTH, Y_SOUTH, Z_TOP - L, Z_TOP, wall="outer_south"),
            HVACVent("inlet_03", "intake",
                     X_E - L, X_E,     Y_OSR_N, Y_OSR_N, Z_TOP - L, Z_TOP, wall="osr_north_wall"),
            HVACVent("inlet_04", "intake",
                     X_W,     X_W + L, Y_OSR_N, Y_OSR_N, Z_TOP - L, Z_TOP, wall="osr_north_wall"),

            HVACVent("outlet_01", "exhaust",
                     X_E - L, X_E,     Y_OSR_N_OSR, Y_OSR_N_OSR, Z_BOT, Z_BOT + L, wall="osr_north"),
            HVACVent("outlet_02", "exhaust",
                     X_W,     X_W + L, Y_OSR_N_OSR, Y_OSR_N_OSR, Z_BOT, Z_BOT + L, wall="osr_north"),
            HVACVent("outlet_03", "exhaust",
                     X_E - L, X_E,     10 - 0.2, 10 - 0.2, Z_BOT, Z_BOT + L, wall="outer_north"),
            HVACVent("outlet_04", "exhaust",
                     X_W,     X_W + L, 10 - 0.2, 10 - 0.2, Z_BOT, Z_BOT + L, wall="outer_north"),
        ]

    elif method == 3:
        # Paper Table 4 No.5 + §5 conclusion: 1 central intake on upper side,
        # 2 outlets symmetric on both sides.  Inlet edge 0.8485 (area 0.72),
        # outlet edge 0.6 (area 0.36 × 2 = 0.72) → 0.72 m³/s at v=1 m/s.
        # The single intake sits on osr_north MER-face, door-centred (so it
        # aligns with the fire below the door).
        L_in = 0.8485
        x1 = door_cx - L_in / 2
        x2 = door_cx + L_in / 2
        vents += [
            HVACVent("inlet_01", "intake",
                     x1, x2, Y_SOUTH, Y_SOUTH, Z_TOP - L_in, Z_TOP, wall="outer_south"),
            HVACVent("inlet_02", "intake",
                     x1, x2, Y_OSR_N, Y_OSR_N, Z_TOP - L_in, Z_TOP, wall="osr_north"),
        ]
        L = 0.6
        vents += [
            HVACVent("outlet_01", "exhaust",
                     X_E - L, X_E,     Y_OSR_N_OSR, Y_OSR_N_OSR, Z_BOT, Z_BOT + L, wall="osr_north"),
            HVACVent("outlet_02", "exhaust",
                     X_W,     X_W + L, Y_OSR_N_OSR, Y_OSR_N_OSR, Z_BOT, Z_BOT + L, wall="osr_north"),
            HVACVent("outlet_03", "exhaust",
                     X_E - L, X_E,     10 - 0.2, 10 - 0.2, Z_BOT, Z_BOT + L, wall="outer_north"),
            HVACVent("outlet_04", "exhaust",
                     X_W,     X_W + L, 10 - 0.2, 10 - 0.2, Z_BOT, Z_BOT + L, wall="outer_north"),
        ]

    return vents


# ---------- Fig 1 defaults ---------------------------------------------------

def default_equipment() -> list[Eq]:
    """Equipment OBSTs -- only items inside the Main Engine Room (OSR is empty)."""
    return [
        # main engine: 6.5 × 3.8 × 2.0 m  (in MER)
        Eq("main_engine",      3.5,  10.0, 5.0, 8.8, 0.0, 2.0, color="PURPLE"),
        # fuel oil supply unit: 2 × 1 × 1 m  (in MER, just north of divider)
        Eq("fuel_oil_supply",  4.5,   6.5, 3.2, 4.2, 0.0, 1.0, color="PURPLE"),
        # preheater: 0.2 × 1 × 0.5 m  (in MER, east of main engine)
        Eq("preheater",       11.5, 11.7, 4.5, 5.5, 0.0, 0.5, color="PURPLE"),
    ]


def default_walls() -> list[Wall]:
    """All walls (0.2 m thick) for the sealed cabin + 7 internal rooms.
    Naming reflects what each wall encloses.  All walls go z=0..3 (full height).
    """
    return [
        # ---- outer perimeter (sealed cabin) ----
        Wall("outer_west",    0.0,  0.2,  0.0, 10.0, 0.0, 3.0, color="WHITE"),
        Wall("outer_east",   12.8, 13.0,  0.0, 10.0, 0.0, 3.0, color="WHITE"),
        Wall("outer_south",   0.0, 13.0,  0.0,  0.2, 0.0, 3.0, color="WHITE"),
        Wall("outer_north",   0.0, 13.0,  9.8, 10.0, 0.0, 3.0, color="WHITE"),

        # ---- interior vertical walls (east walls of the small left rooms) ----
        # East wall of rooms 1+2+3 (rooms have interior x = 0.2..2.3)
        Wall("east_rooms_1to3", 2.3, 2.5, 4.2,  9.3, 0.0, 3.0, color="WHITE"),
        # East wall of rooms 4+5 (interior x = 0.2..3.8)
        # Extends from south wall up to room4 top (also serves as west wall of OSR)
        Wall("east_rooms_4_5",  3.8, 4.0, 0.2,  4.0, 0.0, 3.0, color="WHITE"),

        # ---- interior horizontal walls (between rooms / room tops) ----
        # north wall of room1 (between room1 top y=9.3 and rest of MER)
        Wall("h_top_room1",   0.0, 2.5,   9.3,  9.5, 0.0, 3.0, color="WHITE"),
        # between room1 (y=7.5-9.3) and room2 (y=6.0-7.3)
        Wall("h_room1_room2", 0.0, 2.5,  7.3,  7.5, 0.0, 3.0, color="WHITE"),
        # between room2 and room3
        Wall("h_room2_room3", 0.0, 2.5,  5.8,  6.0, 0.0, 3.0, color="WHITE"),
        # between room3 (interior x ≤ 2.3) and room4 (interior x ≤ 3.8) — wall spans full width
        Wall("h_room3_room4", 0.0, 4.0,  4.0,  4.2, 0.0, 3.0, color="WHITE"),
        # between room4 and room5
        Wall("h_room4_room5", 0.0, 4.0,  2.3,  2.5, 0.0, 3.0, color="WHITE"),
        # north wall of Oil Separator Room (y=2.8..3.0, x=4.0..12.8)
        Wall("osr_north_wall", 4.0, 12.8, 2.8,  3.0, 0.0, 3.0, color="WHITE"),
    ]


def default_holes() -> list[Hole]:
    """Doors as &HOLE openings (door = 0.9 m wide × 2 m tall)."""
    return [
        # Door 1 — east wall of room1 (Room1 ↔ Main Engine Room)
        Hole("door1_main_to_room1", 2.2, 2.6, 8.2,  9.1, 0.0, 2.0),
        # Door 2 — north wall of Oil Separator Room (OSR ↔ Main Engine Room).
        # User-set: x=[7.5, 8.5] aligned with fire footprint.
        Hole("door2_main_to_osr",   7.5, 8.5, 2.7,  3.1, 0.0, 2.0),
    ]


def default_ext_vents() -> list[ExtVent]:
    """Sealed cabin → no external OPEN vents by default."""
    return []


# ---------- configuration ----------------------------------------------------

@dataclass
class Cfg:
    chid: str = "engine_room"
    title: str = "Marine engine-room fire (Lan et al. 2023, Fig 1)"

    # Domain XB [m]  (Fig 1 floor 13 × 10; height 3 m from Fig 6 z=2 m slice)
    x_min: float = 0.0
    x_max: float = 13.0
    y_min: float = 0.0
    y_max: float = 10.0
    z_min: float = 0.0
    z_max: float = 3.0

    # Uniform grid (total cells) -- defaults from module constant IJK
    nx: int = IJK[0]
    ny: int = IJK[1]
    nz: int = IJK[2]

    # Mesh splitting (1,1,1 = single mesh; product = MPI rank count).
    # Defaults from module constant MESH_SPLIT.
    mx: int = MESH_SPLIT[0]
    my: int = MESH_SPLIT[1]
    mz: int = MESH_SPLIT[2]

    # Geometry lists (defaults match Fig 1)
    equipment:  list[Eq]      = field(default_factory=default_equipment)
    walls:      list[Wall]    = field(default_factory=default_walls)
    holes:      list[Hole]    = field(default_factory=default_holes)
    ext_vents:  list[ExtVent] = field(default_factory=default_ext_vents)

    # Mechanical ventilation — defaults read from module constants at the top
    # of this file (edit VENTILATION_METHOD / VENTILATION_VELOCITY there).
    ventilation_method:   int   = VENTILATION_METHOD
    ventilation_velocity: float = VENTILATION_VELOCITY
    hvac_vents: list[HVACVent] = field(default_factory=list)   # auto-populated

    # Fire VENT XB on the floor (z=0).  Defaults from module constant FIRE_XB
    # (1×1 m pool at (8.25, 1.45) matching paper Fig 6 monitoring slices).
    fire_x_min: float = FIRE_XB[0]
    fire_x_max: float = FIRE_XB[1]
    fire_y_min: float = FIRE_XB[2]
    fire_y_max: float = FIRE_XB[3]

    # If set, MER equipment OBSTs use a no-MATL SURF with TMP_FRONT=value,
    # making them an isothermal cold sink (default None = normal steel shell).
    engine_tmp: float | None = None

    # If True, six interior partition walls (rooms 1-5 boundaries) become
    # isothermal 20°C cold sinks colored GRAY for visual verification.
    cold_walls: bool = False

    # If True, swap intake/exhaust vent z ranges: intakes → floor (0-0.6),
    # exhausts → ceiling (z_max-0.6 to z_max).  For Lan 2023 test of
    # displacement-vs-overhead ventilation effect on +1m profile.
    vent_z_swap: bool = False

    # If True, drop the sign-flip on vent_intake/vent_exhaust VEL.
    no_vent_sign_flip: bool = False

    # --- Sensitivity-study tunables (per-surface overrides) -----------------
    # Floor / ceiling SURF (DEFAULT=.TRUE.).  If floor_tmp is set, becomes
    # isothermal cold sink (no MATL_ID + TMP_FRONT=value).
    floor_thickness: float = 0.01
    floor_backing:   str   = "INSULATED"   # EXPOSED | INSULATED | ADIABATIC
    floor_tmp:       "float | None" = None

    # osr_north_wall (steel divider).  If divider_inert is True, becomes INERT
    # (FDS default cold sink at TMPA) and overrides MATL_ID/THICKNESS/BACKING.
    divider_thickness: float = 0.2
    divider_backing:   str   = "EXPOSED"
    divider_inert:     bool  = False

    # Engine + equipment SURF (overrides only when engine_tmp is NOT set).
    engine_thickness: float = 0.01
    engine_backing:   str   = "INSULATED"

    # Other interior partition walls (currently INERT by default).
    # If walls_tmp is set, the 7 partition walls become isothermal cold sink.
    # If walls_exposed_steel is True, they become EXPOSED steel 0.2m.
    walls_tmp:           "float | None" = None
    walls_exposed_steel: bool           = False

    # Whole-face OPEN flags (separate from ExtVent partial doors).
    open_xmin: bool = False
    open_xmax: bool = False
    open_ymin: bool = False
    open_ymax: bool = False
    open_zmin: bool = False
    open_zmax: bool = False

    # HRR ramp [(t_s, HRR_kW)] -- if HRR_T2_POINTS > 0 (default), main()
    # replaces this curve with a t²-growth one at runtime.  The static curve
    # below is kept only as a fallback when HRR_T2_POINTS == 0.
    hrr_curve: list[tuple[float, float]] = field(default_factory=lambda: [
        (0.0,    0.0),
        (5.0,    100.0),
        (15.0,   450.0),
        (30.0,   HRR_PEAK_KW),
        (60.0,   HRR_PEAK_KW),
        (300.0,  HRR_PEAK_KW),
    ])

    # Diesel surrogate + paper Table 2 χ_rad + ΔH.  Defaults from constants.
    fuel: str = FUEL
    heat_of_combustion_kjkg: float = HEAT_OF_COMBUSTION_KJKG
    radiative_fraction: float = RADIATIVE_FRACTION
    soot_yield: "float | None" = SOOT_YIELD
    co_yield:   "float | None" = CO_YIELD
    kappa0:     "float | None" = KAPPA0
    t_end: float = T_END

    dt_devc: float = DT_DEVC
    dt_hrr: float = DT_HRR
    dt_slcf: float = DT_SLCF
    dt_bndf: float = DT_BNDF
    dt_sl3d: float = DT_SL3D

    # Ambient air (paper Table 3) — TMPA is the only knob; FDS computes ρ,
    # Cp, ν, k, α, Pr from its standard air database at this temperature.
    tmpa: float = TMPA

    centerline_quantities: list[str] = field(
        default_factory=lambda: list(CENTERLINE_Q))
    centerline_spec: list[tuple[str, str]] = field(default_factory=lambda: [
        ("VOLUME FRACTION", "CARBON MONOXIDE"),
        ("VOLUME FRACTION", "SOOT"),
        ("VOLUME FRACTION", "OXYGEN"),
    ])
    centerline_n_points: int = CENTERLINE_N_POINTS


# ---------- validation -------------------------------------------------------

def _in_room(label: str, x1, x2, y1, y2, z1, z2, cfg: Cfg, TOL=1e-6) -> list[str]:
    errs = []
    if not (cfg.x_min - TOL <= x1 and x2 <= cfg.x_max + TOL):
        errs.append(f"{label} x [{x1}, {x2}] outside room x [{cfg.x_min}, {cfg.x_max}]")
    if not (cfg.y_min - TOL <= y1 and y2 <= cfg.y_max + TOL):
        errs.append(f"{label} y [{y1}, {y2}] outside room y [{cfg.y_min}, {cfg.y_max}]")
    if not (cfg.z_min - TOL <= z1 and z2 <= cfg.z_max + TOL):
        errs.append(f"{label} z [{z1}, {z2}] outside room z [{cfg.z_min}, {cfg.z_max}]")
    return errs


def validate_geometry(cfg: Cfg) -> None:
    TOL = 1e-6
    errs: list[str] = []
    if abs(cfg.z_min) > TOL:
        errs.append(f"z_min must be 0 (floor); got {cfg.z_min}")
    for e in cfg.equipment:
        errs += _in_room(e.label, e.x1, e.x2, e.y1, e.y2, e.z1, e.z2, cfg)
    for w in cfg.walls:
        errs += _in_room(w.label, w.x1, w.x2, w.y1, w.y2, w.z1, w.z2, cfg)
    for h in cfg.holes:
        errs += _in_room(h.label, h.x1, h.x2, h.y1, h.y2, h.z1, h.z2, cfg)
    # Fire footprint
    if not (cfg.x_min - TOL <= cfg.fire_x_min and cfg.fire_x_max <= cfg.x_max + TOL):
        errs.append(f"fire x [{cfg.fire_x_min}, {cfg.fire_x_max}] outside room x")
    if not (cfg.y_min - TOL <= cfg.fire_y_min and cfg.fire_y_max <= cfg.y_max + TOL):
        errs.append(f"fire y [{cfg.fire_y_min}, {cfg.fire_y_max}] outside room y")
    for e in cfg.equipment:
        if e.z1 > TOL:
            continue
        fx = cfg.fire_x_min < e.x2 - TOL and cfg.fire_x_max > e.x1 + TOL
        fy = cfg.fire_y_min < e.y2 - TOL and cfg.fire_y_max > e.y1 + TOL
        if fx and fy:
            errs.append(f"fire footprint overlaps {e.label}")
    if cfg.nx % cfg.mx or cfg.ny % cfg.my or cfg.nz % cfg.mz:
        errs.append(f"mesh-split ({cfg.mx},{cfg.my},{cfg.mz}) must divide IJK "
                    f"({cfg.nx},{cfg.ny},{cfg.nz}) evenly")
    if errs:
        sys.exit("ERROR: geometry validation failed:\n  " + "\n  ".join(errs))


# ---------- CSV reader -------------------------------------------------------

def load_hrr_csv(path: Path) -> list[tuple[float, float]]:
    rows = []
    with open(path) as f:
        for r in csv.reader(f):
            if not r:
                continue
            cell0 = r[0].strip()
            if not cell0 or cell0.startswith("#"):
                continue
            try:
                t, q = float(cell0), float(r[1].strip())
            except (ValueError, IndexError):
                continue
            rows.append((t, q))
    if not rows:
        sys.exit(f"ERROR: no (time, HRR) rows parsed from {path}")
    rows.sort(key=lambda x: x[0])
    return rows


# ---------- FDS input --------------------------------------------------------

def build_input(cfg: Cfg) -> str:
    # walls span full room height (in case user changes z_max)
    for w in cfg.walls:
        if w.z1 == 0.0:
            w.z2 = cfg.z_max

    # Auto-populate HVAC vents based on ventilation_method (Lan et al. Fig 2)
    if cfg.ventilation_method in (1, 2, 3) and not cfg.hvac_vents:
        cfg.hvac_vents = vents_for_method(cfg.ventilation_method, cfg)

    validate_geometry(cfg)

    peak = max(q for _, q in cfg.hrr_curve)
    fire_area = (cfg.fire_x_max - cfg.fire_x_min) * (cfg.fire_y_max - cfg.fire_y_min)
    hrrpua = peak / fire_area
    dx = (cfg.x_max - cfg.x_min) / cfg.nx
    dy = (cfg.y_max - cfg.y_min) / cfg.ny
    dz = (cfg.z_max - cfg.z_min) / cfg.nz

    L: list[str] = []
    p = L.append

    p(f"&HEAD CHID='{cfg.chid}', TITLE='{cfg.title}' /")
    p("")
    p("! ============================================================")
    p(f"! Room    : {cfg.x_max-cfg.x_min} × {cfg.y_max-cfg.y_min} × {cfg.z_max-cfg.z_min} m  "
      f"(x[{cfg.x_min},{cfg.x_max}] y[{cfg.y_min},{cfg.y_max}] z[{cfg.z_min},{cfg.z_max}])")
    p(f"! Fire   : floor VENT x=[{cfg.fire_x_min},{cfg.fire_x_max}]  "
      f"y=[{cfg.fire_y_min},{cfg.fire_y_max}]  z=0  "
      f"({fire_area:.2f} m², peak HRR={peak:.0f} kW, HRRPUA={hrrpua:.1f} kW/m²)")
    p(f"! Cells  : {cfg.nx} × {cfg.ny} × {cfg.nz} = {cfg.nx*cfg.ny*cfg.nz:,}")
    p(f"! Split  : {cfg.mx} × {cfg.my} × {cfg.mz} = {cfg.mx*cfg.my*cfg.mz} sub-mesh(es) → MPI ranks")
    p(f"! dx={dx:.4f} dy={dy:.4f} dz={dz:.4f} m")
    p(f"! Equipment ({len(cfg.equipment)}):")
    for e in cfg.equipment:
        p(f"!   {e.label:28s} x=[{e.x1},{e.x2}] y=[{e.y1},{e.y2}] z=[{e.z1},{e.z2}]")
    p(f"! Walls ({len(cfg.walls)}):")
    for w in cfg.walls:
        p(f"!   {w.label:28s} x=[{w.x1},{w.x2}] y=[{w.y1},{w.y2}] z=[{w.z1},{w.z2}]")
    p(f"! Doors as HOLEs ({len(cfg.holes)}):")
    for h in cfg.holes:
        p(f"!   {h.label:28s} x=[{h.x1},{h.x2}] y=[{h.y1},{h.y2}] z=[{h.z1},{h.z2}]")
    p(f"! Doors to outside (partial OPEN vents) ({len(cfg.ext_vents)}):")
    for v in cfg.ext_vents:
        p(f"!   {v.label:28s} x=[{v.x1},{v.x2}] y=[{v.y1},{v.y2}] z=[{v.z1},{v.z2}]")
    p("! ============================================================")
    p("")

    # ---- mesh
    n_submesh = cfg.mx * cfg.my * cfg.mz
    if n_submesh == 1:
        p(f"&MESH IJK={cfg.nx},{cfg.ny},{cfg.nz}, "
          f"XB={cfg.x_min},{cfg.x_max},{cfg.y_min},{cfg.y_max},{cfg.z_min},{cfg.z_max} /")
    else:
        DX = (cfg.x_max - cfg.x_min) / cfg.mx
        DY = (cfg.y_max - cfg.y_min) / cfg.my
        DZ = (cfg.z_max - cfg.z_min) / cfg.mz
        ix = cfg.nx // cfg.mx
        iy = cfg.ny // cfg.my
        iz = cfg.nz // cfg.mz
        p(f"! Multi-mesh: each sub-mesh {ix}×{iy}×{iz} = {ix*iy*iz:,} cells.")
        p(f"&MULT ID='m1', DX={DX}, DY={DY}, DZ={DZ}, "
          f"I_LOWER=0, I_UPPER={cfg.mx-1}, J_LOWER=0, J_UPPER={cfg.my-1}, "
          f"K_LOWER=0, K_UPPER={cfg.mz-1} /")
        p(f"&MESH IJK={ix},{iy},{iz}, "
          f"XB={cfg.x_min},{cfg.x_min+DX},{cfg.y_min},{cfg.y_min+DY},"
          f"{cfg.z_min},{cfg.z_min+DZ}, MULT_ID='m1' /")
    p("")
    p(f"&TIME T_END={cfg.t_end} /")
    p(f"&MISC TMPA={cfg.tmpa} /  ! ambient cabin air (paper Table 3, T=293 K)")
    # Note: paper §2.1 cites Smagorinsky, but tested in 757261 it gave WORSE
    # agreement with paper Fig 5 than the FDS 6 DEARDORFF default
    # (mean |Δ| at center+1m: 15.8 °C vs 10.9 °C with Deardorff/756869).
    # Reverted to default; the discrepancy with paper text is unresolved.
    s3d_flag = ".TRUE." if SMOKE3D_OUTPUT else ".FALSE."
    s3d_dt   = f", DT_SL3D={cfg.dt_sl3d}" if SMOKE3D_OUTPUT else ""
    p(f"&DUMP DT_DEVC={cfg.dt_devc}, DT_HRR={cfg.dt_hrr}, "
      f"DT_SLCF={cfg.dt_slcf}, DT_BNDF={cfg.dt_bndf}{s3d_dt}, "
      f"SMOKE3D={s3d_flag}, MASS_FILE=.TRUE. /")
    p("")
    soot_str = f", SOOT_YIELD={cfg.soot_yield}" if cfg.soot_yield is not None else ""
    co_str   = f", CO_YIELD={cfg.co_yield}"     if cfg.co_yield   is not None else ""
    p(f"&REAC FUEL='{cfg.fuel}', "
      f"HEAT_OF_COMBUSTION={cfg.heat_of_combustion_kjkg:.0f}, "
      f"RADIATIVE_FRACTION={cfg.radiative_fraction}{soot_str}{co_str} /")
    if cfg.kappa0 is not None:
        p(f"&RADI KAPPA0={cfg.kappa0} /  ! constant absorption coefficient (paper Table 2)")
    p("")

    # ---- whole-face OPEN
    open_faces = [f for f, b in [
        ("XMIN", cfg.open_xmin), ("XMAX", cfg.open_xmax),
        ("YMIN", cfg.open_ymin), ("YMAX", cfg.open_ymax),
        ("ZMIN", cfg.open_zmin), ("ZMAX", cfg.open_zmax),
    ] if b]
    if open_faces:
        p(f"! Whole-face OPEN: {', '.join(open_faces)}")
        for f in open_faces:
            p(f"&VENT MB='{f}', SURF_ID='OPEN' /")
    else:
        p("! All 6 outer faces solid by default; doors below are explicit openings.")
    p("")

    # ---- partial OPEN vents (external doors)
    for v in cfg.ext_vents:
        p(f"&VENT XB={v.x1},{v.x2},{v.y1},{v.y2},{v.z1},{v.z2}, "
          f"SURF_ID='OPEN' /  ! {v.label}")
    if cfg.ext_vents:
        p("")

    # ---- HVAC vents (mechanical ventilation, Method 1/2/3)
    if cfg.hvac_vents:
        v_speed = cfg.ventilation_velocity
        p(f"! HVAC vents — Method {cfg.ventilation_method}, "
          f"v={v_speed} m/s normal velocity"
          + (" [VENT-Z-SWAP]" if cfg.vent_z_swap else "")
          + (" [NO-SIGN-FLIP]" if cfg.no_vent_sign_flip else " [SIGN-FLIPPED]"))
        # Default SIGN-FLIPPED: vent_intake VEL=-{v} acts as supply (FDS:
        # VEL<0 = flow into domain from this face); vent_exhaust VEL=+{v}
        # acts as exhaust.  With --no-vent-sign-flip the conventional FDS
        # mapping is restored (intake VEL=+ outward = exhaust, etc.).
        if cfg.no_vent_sign_flip:
            intake_vel, exhaust_vel = f"+{v_speed}", f"-{v_speed}"
        else:
            intake_vel, exhaust_vel = f"-{v_speed}", f"+{v_speed}"
        p(f"&SURF ID='vent_intake',  VEL={intake_vel}, COLOR='GREEN', TMP_FRONT=20.0 /")
        p(f"&SURF ID='vent_exhaust', VEL={exhaust_vel}, COLOR='BLUE' /")
        for v in cfg.hvac_vents:
            sid = "vent_intake" if v.kind == "intake" else "vent_exhaust"
            # --vent-z-swap: swap intake and exhaust z ranges so the physical
            # vent position is moved.  Keeps wall surface (y) the same.
            z1, z2 = v.z1, v.z2
            if cfg.vent_z_swap:
                if v.kind == "intake":
                    z1, z2 = 0.0, 0.6                  # move intakes to floor
                elif v.kind == "exhaust":
                    z1, z2 = cfg.z_max - 0.6, cfg.z_max  # move exhausts to ceiling
            p(f"&VENT XB={v.x1},{v.x2},{v.y1},{v.y2},{z1},{z2}, "
              f"SURF_ID='{sid}' /  ! {v.label} ({v.kind} on {v.wall})")
        p("")

    # ---- HRR ramp
    p("! Fire HRR ramp (normalized to peak)")
    for t, q in cfg.hrr_curve:
        frac = q / peak if peak > 0 else 0.0
        p(f"&RAMP ID='fire_hrr', T={t:.3f}, F={frac:.6f} /")
    p("")

    # ---- MATL + SURFs (steel walls / equipment, per Lan et al. Table 1)
    p("! Steel material (Lan et al. 2023, Table 1)")
    p("&MATL ID='STEEL', DENSITY=7850.0, SPECIFIC_HEAT=0.46, "
      "CONDUCTIVITY=45.8, EMISSIVITY=0.95 /")
    p("")
    wall_surfs: dict[str, str] = {}
    for w in cfg.walls:
        wall_surfs[f"surf_wall_{w.color.lower()}"] = w.color
    eq_surfs: dict[str, str] = {}
    for e in cfg.equipment:
        eq_surfs[f"surf_eq_{e.color.lower()}"] = e.color
    # Walls (osr_north_wall divider): per --divider-* overrides
    for sid, col in wall_surfs.items():
        p(f"&SURF ID='{sid}', MATL_ID='STEEL', THICKNESS={cfg.divider_thickness}, "
          f"BACKING='{cfg.divider_backing}', COLOR='{col}' /")
    # Floor + ceiling SURF: either isothermal (no MATL_ID + TMP_FRONT) or steel
    if cfg.floor_tmp is not None:
        p(f"&SURF ID='surf_floor_ceiling', TMP_FRONT={cfg.floor_tmp}, "
          f"COLOR='GRAY', DEFAULT=.TRUE. /  ! isothermal floor/ceiling cold sink")
    else:
        p(f"&SURF ID='surf_floor_ceiling', MATL_ID='STEEL', "
          f"THICKNESS={cfg.floor_thickness}, BACKING='{cfg.floor_backing}', "
          f"COLOR='GRAY', DEFAULT=.TRUE. /")
    # Equipment SURF — two modes:
    #   default: thin steel shell, insulated backing (surface heats up freely)
    #   --engine-tmp T: no MATL_ID + TMP_FRONT=T → surface HELD at T (cold sink)
    if cfg.engine_tmp is not None:
        for sid, col in eq_surfs.items():
            p(f"&SURF ID='{sid}', TMP_FRONT={cfg.engine_tmp}, COLOR='{col}' /  "
              f"! isothermal cold sink (no MATL_ID)")
    else:
        for sid, col in eq_surfs.items():
            p(f"&SURF ID='{sid}', MATL_ID='STEEL', "
              f"THICKNESS={cfg.engine_thickness}, "
              f"BACKING='{cfg.engine_backing}', COLOR='{col}' /")
    # NOTE: 757930 tested DEFAULT=.TRUE. INSULATED steel on floor/ceiling and
    # ceiling z=2.95 DROPPED from 225 → 187 °C (cold inlet jets equilibrate
    # with warmed steel and dilute the smoke layer).  Reverted to INERT default.
    p(f"&SURF ID='fire', COLOR='RED', HRRPUA={hrrpua:.3f}, RAMP_Q='fire_hrr', "
      f"TMP_FRONT=400. /")
    p("")

    # ---- walls
    # Only the OSR-MER divider (osr_north_wall) gets the steel surf_wall_<col>
    # SURF; all other walls fall back to INERT (FDS default cold-sink at 20 °C).
    # Test variant per user request to isolate the divider radiation effect.
    STEEL_WALL_LABELS = {"osr_north_wall"}
    COLD_SINK_WALL_LABELS = {
        "h_top_room1", "h_room1_room2", "h_room2_room3",
        "h_room3_room4", "h_room4_room5",
        "east_rooms_4_5", "east_rooms_1to3",
    }
    # Partition-wall SURF (group D sweep):
    #   default            : INERT (FDS cold sink at TMPA)
    #   --cold-walls       : INSULATED steel 0.01 m YELLOW
    #   --walls-tmp T      : isothermal cold sink at T°C (no MATL_ID)
    #   --walls-exposed-steel: EXPOSED steel 0.2 m
    partition_sid = None   # None = use INERT
    if cfg.walls_tmp is not None:
        partition_sid = "surf_wall_partition_iso"
        p(f"&SURF ID='{partition_sid}', TMP_FRONT={cfg.walls_tmp}, "
          f"COLOR='CYAN' /  ! isothermal partition cold sink")
    elif cfg.walls_exposed_steel:
        partition_sid = "surf_wall_partition_steel"
        p(f"&SURF ID='{partition_sid}', MATL_ID='STEEL', THICKNESS=0.2, "
          f"BACKING='EXPOSED', COLOR='ORANGE' /  ! EXPOSED steel partition")
    elif cfg.cold_walls:
        partition_sid = "surf_wall_coldsink"
        p(f"&SURF ID='{partition_sid}', MATL_ID='STEEL', THICKNESS=0.01, "
          "BACKING='INSULATED', COLOR='YELLOW' /  ! INSULATED steel partition")
    p(f"! {len(cfg.walls)} internal walls (rooms partition)")
    for w in cfg.walls:
        if w.label in STEEL_WALL_LABELS:
            # OSR-MER divider: INERT if --divider-inert, else steel SURF
            sid = "INERT" if cfg.divider_inert else f"surf_wall_{w.color.lower()}"
        elif partition_sid is not None and w.label in COLD_SINK_WALL_LABELS:
            sid = partition_sid
        else:
            sid = "INERT"
        p(f"&OBST XB={w.x1},{w.x2},{w.y1},{w.y2},{w.z1},{w.z2}, "
          f"SURF_ID='{sid}' /  ! wall: {w.label}")
    p("")

    # ---- holes (door openings in walls)
    if cfg.holes:
        p(f"! {len(cfg.holes)} door openings (&HOLE removes wall cells)")
        for h in cfg.holes:
            p(f"&HOLE XB={h.x1},{h.x2},{h.y1},{h.y2},{h.z1},{h.z2} /  ! door: {h.label}")
        p("")

    # ---- equipment
    p(f"! {len(cfg.equipment)} equipment OBSTs from Fig 1 -- steel shell")
    for e in cfg.equipment:
        sid = f"surf_eq_{e.color.lower()}"
        p(f"&OBST XB={e.x1},{e.x2},{e.y1},{e.y2},{e.z1},{e.z2}, "
          f"SURF_ID='{sid}' /  ! {e.label}")
    p("")

    # ---- fire VENT on the floor
    p(f"&VENT XB={cfg.fire_x_min},{cfg.fire_x_max},"
      f"{cfg.fire_y_min},{cfg.fire_y_max},0,0, SURF_ID='fire' /  ! fire footprint")
    p("")

    # ---- centerline DEVCs above fire
    cx = (cfg.fire_x_min + cfg.fire_x_max) / 2
    cy = (cfg.fire_y_min + cfg.fire_y_max) / 2
    z_start = 0.05
    # NOTE: every POINTS-based DEVC in this file writes into the SHARED
    # <CHID>_line.csv. FDS pads shorter columns with NaN to match the longest
    # POINTS, so all line DEVCs MUST share the same N to avoid NaN rows.
    # Keep n_line_points == n_gridconv (30) across the whole file.
    npts_line = 30
    p(f"! Centerline above fire: x={cx:.3f}, y={cy:.3f}, z=[{z_start:.3f}..{cfg.z_max}]")
    need_tc = any(q.upper() == "THERMOCOUPLE" for q in cfg.centerline_quantities)
    if need_tc:
        p("&PROP ID='TC', TIME_CONSTANT=3 /")
    for q in cfg.centerline_quantities:
        qu = q.upper()
        safe = qu.replace("-", "_").replace(" ", "_").lower()
        extras = ["PROP_ID='TC'", "Z_ID='Height'"] if qu == "THERMOCOUPLE" else ["HIDE_COORDINATES=.TRUE."]
        extra_str = ", " + ", ".join(extras)
        p(f"&DEVC ID='line_{safe}', XB={cx:.4f},{cx:.4f},{cy:.4f},{cy:.4f},"
          f"{z_start:.4f},{cfg.z_max:.4f}, POINTS={npts_line}, "
          f"QUANTITY='{q}'{extra_str} /")
    for q, spec in cfg.centerline_spec:
        safe = (q + "_" + spec).lower().replace(" ", "_").replace("-", "_")
        p(f"&DEVC ID='line_{safe}', XB={cx:.4f},{cx:.4f},{cy:.4f},{cy:.4f},"
          f"{z_start:.4f},{cfg.z_max:.4f}, POINTS={npts_line}, "
          f"QUANTITY='{q}', SPEC_ID='{spec}', HIDE_COORDINATES=.TRUE. /")

    if cfg.centerline_n_points > 0:
        p(f"! {cfg.centerline_n_points} single-point DEVCs at evenly-spaced heights")
        if cfg.centerline_n_points == 1:
            zs = [(z_start + cfg.z_max) / 2]
        else:
            step = (cfg.z_max - z_start) / (cfg.centerline_n_points - 1)
            zs = [z_start + k * step for k in range(cfg.centerline_n_points)]
        for z in zs:
            tag = f"z{z:.2f}".replace(".", "p")
            for q in cfg.centerline_quantities:
                qu = q.upper()
                safe = qu.replace("-", "_").replace(" ", "_").lower()
                extras = ["PROP_ID='TC'"] if qu == "THERMOCOUPLE" else []
                extra_str = (", " + ", ".join(extras)) if extras else ""
                p(f"&DEVC ID='pt_{safe}_{tag}', XYZ={cx:.4f},{cy:.4f},{z:.4f}, "
                  f"QUANTITY='{q}'{extra_str} /")
            for q, spec in cfg.centerline_spec:
                safe = (q + "_" + spec).lower().replace(" ", "_").replace("-", "_")
                p(f"&DEVC ID='pt_{safe}_{tag}', XYZ={cx:.4f},{cy:.4f},{z:.4f}, "
                  f"QUANTITY='{q}', SPEC_ID='{spec}' /")
        # NOTE: visual marker cubes REMOVED — earlier they were emitted at
        # y = cy − 0.3 m, i.e. INSIDE the fire footprint (y=[1,2]), where they
        # acted as 0.16 m steel cubes obstructing the plume and corrupted the
        # solution.  The single-point DEVCs above are gas-phase virtual
        # samplers (no physical body); no marker is needed for them.
    p("")

    # ---- grid-convergence vertical T lines (Lan et al. 2023 §3.3, Fig 5)
    # Paper: "vertical temperature distribution at 1 m from the fire source in
    # the y-direction".  Two interpretations, each with its own DEVC name:
    #   gridconv_T_center : (cx, cy + 1.0)             centre-ref +y (in OSR gas)
    #   gridconv_T_edge   : (cx, fire_y_max + 1.0)     edge-ref +y
    # The edge sensor lands at y = fire_y_max+1; with our pool that is y=2.95,
    # which is INSIDE the OSR-MER divider wall (y=[2.8, 3.0]).  The divider
    # door HOLE (x=[7.75, 8.75], y=[2.7, 3.1], z=[0, 2.0]) carves a void
    # through the wall in this x-range, so the edge sensor's z range is
    # truncated to [0.05, 1.95] to keep all 30 sample points inside the door
    # void (= gas).  Both DEVCs use POINTS=30 → no NaN padding in line.csv.
    # Any sensor whose sample line falls in solid is dropped with a warning.
    gx = cx
    n_gridconv = 30                  # MUST equal npts_line (line.csv shared)
    proposed = [
        # (id,                       y,                     z_min, z_max, descr)
        ("gridconv_T_center",        cy + 1.0,              0.05, cfg.z_max - 0.05, "centre +1 m"),
        ("gridconv_T_center_05m",    cy + 0.5,              0.05, cfg.z_max - 0.05, "centre +0.5 m"),
        ("gridconv_T_edge",          cfg.fire_y_max + 1.0,  0.05, 1.95,             "edge   +1 m"),
    ]

    def _inside_box(x, y, z, b):
        return (b.x1 <= x <= b.x2 and b.y1 <= y <= b.y2 and b.z1 <= z <= b.z2)

    def _line_inside_solid(x, y, z_lo, z_hi) -> tuple[int, str]:
        """Return (n_inside, first-blocker-label) over the line's own z grid."""
        z_pts = [z_lo + i * (z_hi - z_lo) / (n_gridconv - 1)
                 for i in range(n_gridconv)]
        blocker, n = "", 0
        for z in z_pts:
            in_solid = False
            for w in cfg.walls:
                if _inside_box(x, y, z, w):
                    in_solid = True; label = f"wall '{w.label}'"; break
            if not in_solid:
                for e in cfg.equipment:
                    if _inside_box(x, y, z, e):
                        in_solid = True; label = f"equipment '{e.label}'"; break
            if in_solid:
                for h in cfg.holes:                     # hole carves a void
                    if _inside_box(x, y, z, h):
                        in_solid = False; break
            if in_solid:
                n += 1
                if not blocker:
                    blocker = label
        return n, blocker

    import sys as _sys
    p(f"! Grid-convergence T(z) lines (paper §3.3 Fig 5).  Each sensor emits "
      f"TWO DEVCs:")
    p(f"!   '<id>'      = instantaneous T(z) at last dump time")
    p(f"!   '<id>_avg'  = TIME AVERAGE from t={GRIDCONV_AVG_START} s to T_END")
    for did, gy, z_lo, z_hi, descr in proposed:
        n_bad, blocker = _line_inside_solid(gx, gy, z_lo, z_hi)
        if n_bad > 0:
            msg = (f"WARNING: DEVC '{did}' ({descr}) at x={gx:.3f}, y={gy:.3f}: "
                   f"{n_bad}/{n_gridconv} sample points inside {blocker} — "
                   f"sample line drops INTO solid OBST.  DEVC OMITTED.")
            print(msg, file=_sys.stderr)
            p(f"! {msg}")
            continue
        # instantaneous
        p(f"&DEVC ID='{did}', XB={gx:.4f},{gx:.4f},{gy:.4f},{gy:.4f},"
          f"{z_lo:.4f},{z_hi:.4f}, POINTS={n_gridconv}, "
          f"QUANTITY='TEMPERATURE', HIDE_COORDINATES=.TRUE. /  "
          f"! {descr}, z=[{z_lo:.2f}, {z_hi:.2f}] -- instant")
        # time-averaged from GRIDCONV_AVG_START to end of sim
        p(f"&DEVC ID='{did}_avg', XB={gx:.4f},{gx:.4f},{gy:.4f},{gy:.4f},"
          f"{z_lo:.4f},{z_hi:.4f}, POINTS={n_gridconv}, "
          f"QUANTITY='TEMPERATURE', HIDE_COORDINATES=.TRUE., "
          f"TEMPORAL_STATISTIC='TIME AVERAGE', "
          f"STATISTICS_START={GRIDCONV_AVG_START} /  "
          f"! {descr}, z=[{z_lo:.2f}, {z_hi:.2f}] -- time avg from {GRIDCONV_AVG_START}s")
    p("")

    # ---- slices: paper Fig 6 monitoring planes (x=8.1, 8.4, y=1.45, z=2.0)
    # x=8.1 / x=8.4 flank the fire at x=[7.75,8.75] from each side, y=1.45 is
    # the fire's longitudinal centerline, z=2 captures the upper smoke layer.
    # T + HRRPUV : flame/temperature ; VISIBILITY + SOOT : smoke visualization.
    # FIXED slice positions (paper-aligned, no longer fire-following):
    #   PBY = 1.45             (XZ longitudinal plane, paper Fig 6)
    #   PBX = 8.10             (YZ flank plane, paper Fig 6 monitoring slice)
    #   PBZ = 2.0, 2.7, 0.3    (XY horizontal planes: engine top / ceiling smoke / floor)
    SLCF_Y_LIST = [1.45]
    SLCF_X_LIST = [8.10]
    SLCF_Z_LIST = [2.0, 2.7, 0.3]
    for q in ("TEMPERATURE", "HRRPUV", "VISIBILITY"):
        for xs in SLCF_X_LIST:
            p(f"&SLCF PBX={xs:.3f}, QUANTITY='{q}' /")
        for ys in SLCF_Y_LIST:
            p(f"&SLCF PBY={ys:.3f}, QUANTITY='{q}' /")
        for zs in SLCF_Z_LIST:
            p(f"&SLCF PBZ={zs:.3f}, QUANTITY='{q}' /")
    # SOOT mass fraction on the same planes (Fig 16/18 smoke stratification)
    for xs in SLCF_X_LIST:
        p(f"&SLCF PBX={xs:.3f}, QUANTITY='MASS FRACTION', SPEC_ID='SOOT' /")
    for ys in SLCF_Y_LIST:
        p(f"&SLCF PBY={ys:.3f}, QUANTITY='MASS FRACTION', SPEC_ID='SOOT' /")
    for zs in SLCF_Z_LIST:
        p(f"&SLCF PBZ={zs:.3f}, QUANTITY='MASS FRACTION', SPEC_ID='SOOT' /")
    # Velocity vector fields for streamline visualization
    for ys in SLCF_Y_LIST:
        p(f"&SLCF PBY={ys:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /")
    for xs in SLCF_X_LIST:
        p(f"&SLCF PBX={xs:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /")
    for zs in SLCF_Z_LIST:
        p(f"&SLCF PBZ={zs:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /")
    # ---- vent monitoring: horizontal slices at the z-mid of every HVAC vent.
    # Lets us see how each inlet pushes air in and each exhaust draws it out.
    if cfg.hvac_vents:
        vent_z_mids = sorted({round((v.z1 + v.z2) / 2, 3) for v in cfg.hvac_vents})
        p(f"! vent z-mid monitoring slices ({len(vent_z_mids)} z heights from "
          f"{len(cfg.hvac_vents)} vents)")
        for z_mid in vent_z_mids:
            p(f"&SLCF PBZ={z_mid:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /  "
              f"! z-mid of vents at this height")
            p(f"&SLCF PBZ={z_mid:.3f}, QUANTITY='TEMPERATURE' /")
            p(f"&SLCF PBZ={z_mid:.3f}, QUANTITY='W-VELOCITY' /  "
              f"! vertical flow component at vent height")
    p("")
    p("! Fig 9/10/12 data: DEVCs for L_x/L_y/L_z, V_flame, H_f (Heskestad 99%), v_y, T_f")

    # Flame-envelope bounding box around the fire vent (XB chosen to be a
    # neighborhood of the burner; MAXLOC/MINLOC over QUANTITY give the cell
    # coordinate of the extremum -> L_x, L_y, L_z of flame envelope).
    flame_box = "6.0,11.0,0.0,3.0,0.0,3.0"
    p(f"&DEVC ID='flame_xmin',   QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='MINLOC X' /")
    p(f"&DEVC ID='flame_xmax',   QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='MAXLOC X' /")
    p(f"&DEVC ID='flame_ymin',   QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='MAXLOC Y' /")
    p(f"&DEVC ID='flame_ymax',   QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='MINLOC Y' /")
    p(f"&DEVC ID='flame_zmin',   QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='MINLOC Z' /")
    p(f"&DEVC ID='flame_zmax',   QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='MAXLOC Z' /")
    # Flame volume + total HRR inside flame (cells with HRRPUV>=200 kW/m^3).
    p(f"&DEVC ID='flame_volume', QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='VOLUME', QUANTITY_RANGE=200.0,1.0E10 /")
    p(f"&DEVC ID='flame_hrr_in_box', QUANTITY='HRRPUV', XB={flame_box}, "
      f"SPATIAL_STATISTIC='VOLUME INTEGRAL', QUANTITY_RANGE=200.0,1.0E10 /")

    # Heskestad-style 99%-HRR flame height H_f: 30 stratified VOLUME INTEGRAL
    # DEVCs above the burner footprint -- each DEVC writes one z-slab's total
    # HRR per time step.  H_f is computed in post-processing (extract_flame.py)
    # by cumulative-summing along z and finding the z where the sum reaches
    # 99% of the total at each time step.  (FDS6 has no single-CTRL form that
    # produces a percentile over a list of DEVCs.)
    n_hf = 30
    dz_hf = cfg.z_max / n_hf
    for k in range(n_hf):
        z1 = k * dz_hf
        z2 = (k + 1) * dz_hf
        p(f"&DEVC ID='Hf_int_{k:02d}', QUANTITY='HRRPUV', "
          f"XB={cfg.fire_x_min:.4f},{cfg.fire_x_max:.4f},"
          f"{cfg.fire_y_min:.4f},{cfg.fire_y_max:.4f},{z1:.4f},{z2:.4f}, "
          f"SPATIAL_STATISTIC='VOLUME INTEGRAL', HIDE_COORDINATES=.TRUE. /")

    # Velocity / temperature DEVCs for the Lan tilt correlation X-group.
    # vy_inlet = bulk ventilation v_y at upstream-inlet centerline (paper);
    # vy_flame_box, T_flame_box = box-averaged sensitivity cross-checks;
    # T_tip = centerline TC near expected H_f ~ z_max/2 for T_f estimate.
    p(f"&DEVC ID='vy_inlet',     QUANTITY='U-VELOCITY', "
      f"XYZ=0.5,{cy:.4f},1.0 /")
    p(f"&DEVC ID='vy_flame_box', QUANTITY='U-VELOCITY', XB={flame_box}, "
      f"SPATIAL_STATISTIC='VOLUME MEAN' /")
    p(f"&DEVC ID='T_flame_box',  QUANTITY='TEMPERATURE', XB={flame_box}, "
      f"SPATIAL_STATISTIC='VOLUME MEAN' /")
    p(f"&DEVC ID='T_tip',        QUANTITY='THERMOCOUPLE', PROP_ID='TC', "
      f"XYZ={cx:.4f},{cy:.4f},{cfg.z_max/2:.4f} /")
    p("")

    p("&BNDF QUANTITY='WALL TEMPERATURE' /")
    p("&BNDF QUANTITY='NET HEAT FLUX' /")
    p("")
    p("&TAIL /")
    return "\n".join(L) + "\n"


# ---------- CLI --------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate FDS input for the Lan et al. 2023 engine-room (Fig 1).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # All defaults come from the USER-EDITABLE SETTINGS block at the top of
    # this file.  CLI flags below act as one-shot overrides.
    p.add_argument("--chid", default="engine_room")
    p.add_argument("--out",  default="inputs/engine_room.fds")
    p.add_argument("--xb", nargs=6, type=float,
                   default=[0.0, 13.0, 0.0, 10.0, 0.0, 3.0],
                   metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"))
    p.add_argument("--ijk", nargs=3, type=int, default=list(IJK),
                   metavar=("NX", "NY", "NZ"))
    p.add_argument("--mesh-split", nargs=3, type=int, default=list(MESH_SPLIT),
                   metavar=("MX", "MY", "MZ"),
                   help="Sub-meshes per axis (must divide IJK).")
    p.add_argument("--fire-xb", nargs=4, type=float, default=list(FIRE_XB),
                   metavar=("XMIN", "XMAX", "YMIN", "YMAX"))
    p.add_argument("--open", nargs="*", default=[],
                   choices=["XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"])
    p.add_argument("--fuel", default=FUEL)
    p.add_argument("--radiative-fraction", type=float, default=RADIATIVE_FRACTION)
    p.add_argument("--t-end", type=float, default=T_END)
    p.add_argument("--hrr-csv", default=None,
                   help="External CSV (t_s,q_kw).  Takes priority over --hrr-t2-*.")
    p.add_argument("--hrr-t2-points", type=int, default=HRR_T2_POINTS)
    p.add_argument("--hrr-t2-tpeak", type=float, default=HRR_T2_TPEAK)
    p.add_argument("--hrr-peak", type=float, default=HRR_PEAK_KW)
    p.add_argument("--centerline-q", nargs="+", default=CENTERLINE_Q)
    p.add_argument("--centerline-spec", nargs="+", default=CENTERLINE_SPEC,
                   metavar="QUANTITY:SPEC_ID")
    p.add_argument("--centerline-n-points", type=int, default=CENTERLINE_N_POINTS)
    p.add_argument("--dt-devc", type=float, default=DT_DEVC)
    p.add_argument("--dt-hrr",  type=float, default=DT_HRR)
    p.add_argument("--dt-slcf", type=float, default=DT_SLCF)
    p.add_argument("--dt-bndf", type=float, default=DT_BNDF)
    # Ventilation system (Lan et al. Fig 2) — defaults come from the module
    # constants VENTILATION_METHOD / VENTILATION_VELOCITY at the top of this
    # file.  Pass these CLI flags only when you want a one-shot override.
    p.add_argument("--ventilation-method", type=int, default=VENTILATION_METHOD,
                   choices=[0, 1, 2, 3],
                   help="0 = no ventilation; 1/2/3 = paper Method 1/2/3")
    p.add_argument("--ventilation-velocity", type=float, default=VENTILATION_VELOCITY,
                   help="Normal velocity at each vent [m/s] (paper uses 1 or 3)")
    p.add_argument("--close-osr-mer-door", action="store_true",
                   help="Remove door2_main_to_osr HOLE so OSR is fully isolated "
                        "from MER (keeps MER ≈ 20°C, no hot smoke crossing).")
    p.add_argument("--engine-tmp", type=float, default=None,
                   help="If set, MER equipment OBSTs (main_engine etc.) get a "
                        "no-MATL SURF with TMP_FRONT=this value — surface "
                        "temperature is HELD constant (e.g. 20°C cold sink).")
    p.add_argument("--cold-walls", action="store_true",
                   help="Make the 6 west-room partition walls (h_top_room1, "
                        "h_room1_room2, h_room2_room3, h_room3_room4, "
                        "east_rooms_4_5, east_rooms_1to3) isothermal 20°C cold "
                        "sinks colored GRAY for visual verification.")
    p.add_argument("--vent-z-swap", action="store_true",
                   help="Swap intake/exhaust vent z ranges so intakes are at "
                        "floor (z=0-0.6) and exhausts at ceiling (z=z_max-0.6 "
                        "to z_max).  Tests displacement vs overhead venting.")
    p.add_argument("--no-vent-sign-flip", action="store_true",
                   help="Drop the SIGN-FLIPPED vent_intake/exhaust VEL "
                        "convention.  intake VEL=+v acts as outflow, exhaust "
                        "VEL=-v acts as inflow.")
    # --- sensitivity-study tunables --------------------------------------
    p.add_argument("--kappa0", type=float, default=None,
                   help="Constant absorption coefficient KAPPA0 (default 1.7).")
    p.add_argument("--soot-yield", type=float, default=None,
                   help="Soot yield in REAC (default 0.05).")
    p.add_argument("--co-yield", type=float, default=None,
                   help="CO yield in REAC (default 0.02).")
    # Floor/ceiling
    p.add_argument("--floor-thickness", type=float, default=0.01)
    p.add_argument("--floor-backing", default="INSULATED",
                   choices=["EXPOSED", "INSULATED"])
    p.add_argument("--floor-tmp", type=float, default=None,
                   help="Isothermal floor/ceiling at given T°C (no MATL_ID).")
    # osr_north_wall (divider)
    p.add_argument("--divider-thickness", type=float, default=0.2)
    p.add_argument("--divider-backing", default="EXPOSED",
                   choices=["EXPOSED", "INSULATED"])
    p.add_argument("--divider-inert", action="store_true",
                   help="Make osr_north_wall INERT (FDS cold sink at TMPA).")
    # Engine + equipment
    p.add_argument("--engine-thickness", type=float, default=0.01)
    p.add_argument("--engine-backing", default="INSULATED",
                   choices=["EXPOSED", "INSULATED"])
    # Other interior walls
    p.add_argument("--walls-tmp", type=float, default=None,
                   help="Isothermal partition walls (rooms 1-5) at T°C.")
    p.add_argument("--walls-exposed-steel", action="store_true",
                   help="Partition walls = EXPOSED steel 0.2 m (ORANGE).")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    cfg = Cfg(
        chid=a.chid,
        x_min=a.xb[0], x_max=a.xb[1],
        y_min=a.xb[2], y_max=a.xb[3],
        z_min=a.xb[4], z_max=a.xb[5],
        nx=a.ijk[0], ny=a.ijk[1], nz=a.ijk[2],
        mx=a.mesh_split[0], my=a.mesh_split[1], mz=a.mesh_split[2],
        fire_x_min=a.fire_xb[0], fire_x_max=a.fire_xb[1],
        fire_y_min=a.fire_xb[2], fire_y_max=a.fire_xb[3],
        open_xmin=("XMIN" in a.open), open_xmax=("XMAX" in a.open),
        open_ymin=("YMIN" in a.open), open_ymax=("YMAX" in a.open),
        open_zmin=("ZMIN" in a.open), open_zmax=("ZMAX" in a.open),
        fuel=a.fuel,
        radiative_fraction=a.radiative_fraction,
        t_end=a.t_end,
        dt_devc=a.dt_devc, dt_hrr=a.dt_hrr,
        dt_slcf=a.dt_slcf, dt_bndf=a.dt_bndf,
        centerline_quantities=a.centerline_q,
        centerline_n_points=a.centerline_n_points,
        ventilation_method=a.ventilation_method,
        ventilation_velocity=a.ventilation_velocity,
        engine_tmp=a.engine_tmp,
        cold_walls=a.cold_walls,
        vent_z_swap=a.vent_z_swap,
        no_vent_sign_flip=a.no_vent_sign_flip,
        floor_thickness=a.floor_thickness,
        floor_backing=a.floor_backing,
        floor_tmp=a.floor_tmp,
        divider_thickness=a.divider_thickness,
        divider_backing=a.divider_backing,
        divider_inert=a.divider_inert,
        engine_thickness=a.engine_thickness,
        engine_backing=a.engine_backing,
        walls_tmp=a.walls_tmp,
        walls_exposed_steel=a.walls_exposed_steel,
    )
    if a.kappa0 is not None: cfg.kappa0 = a.kappa0
    if a.soot_yield is not None: cfg.soot_yield = a.soot_yield
    if a.co_yield is not None: cfg.co_yield = a.co_yield
    cfg.centerline_spec = []
    for item in a.centerline_spec:
        if ":" not in item:
            sys.exit(f"ERROR: --centerline-spec item '{item}' must be 'QUANTITY:SPEC_ID'")
        q, spec = item.split(":", 1)
        cfg.centerline_spec.append((q.strip(), spec.strip()))
    if a.close_osr_mer_door:
        cfg.holes = [h for h in cfg.holes if h.label != "door2_main_to_osr"]
    if a.hrr_csv:
        cfg.hrr_curve = load_hrr_csv(Path(a.hrr_csv))
    elif a.hrr_t2_points > 0:
        # t² growth (Lan et al. 2023 §2.2): Q(t) = (t/t_peak)² · Q_peak for
        # t ∈ [0, t_peak], then steady at Q_peak until T_END.  N uniformly
        # spaced anchor points so FDS can linear-interp a smooth curve.
        n = max(2, a.hrr_t2_points)
        tp, qp = a.hrr_t2_tpeak, a.hrr_peak
        curve = [(k * tp / (n - 1), ((k * tp / (n - 1)) / tp) ** 2 * qp)
                 for k in range(n)]
        if a.t_end > tp:
            curve.append((a.t_end, qp))
        cfg.hrr_curve = curve

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_input(cfg))

    peak = max(q for _, q in cfg.hrr_curve)
    cells = cfg.nx * cfg.ny * cfg.nz
    print(f"Wrote: {out}")
    print(f"  Room:   {cfg.x_max-cfg.x_min} × {cfg.y_max-cfg.y_min} × {cfg.z_max-cfg.z_min} m  "
          f"(2 rooms: Main Engine + Oil Separator)")
    print(f"  Equip:  {len(cfg.equipment)} OBSTs (engine height = {cfg.z_max/2} m)")
    print(f"  Walls:  {len(cfg.walls)} internal walls (Y=3 + X=5)")
    print(f"  Doors:  {len(cfg.holes)} internal HOLE(s) + {len(cfg.ext_vents)} external OPEN vent(s)")
    print(f"  Fire:   ({(cfg.fire_x_min+cfg.fire_x_max)/2}, "
          f"{(cfg.fire_y_min+cfg.fire_y_max)/2}) in Oil Separator Room; peak {peak:.0f} kW")
    print(f"  Grid:   {cfg.nx}×{cfg.ny}×{cfg.nz} = {cells:,} cells")
    nsub = cfg.mx * cfg.my * cfg.mz
    print(f"  Split:  {cfg.mx}×{cfg.my}×{cfg.mz} = {nsub} sub-mesh{'es' if nsub>1 else ''}; "
          f"mpiexec -n {nsub}")


if __name__ == "__main__":
    main()
