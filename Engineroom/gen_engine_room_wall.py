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
# Mechanical-ventilation activation time [s].  0 = vents run from t=0 (original
# behaviour).  >0 = vents are held closed (VEL ramped to F=0) until VENT_START,
# then ramped up to full velocity over VENT_RAMP_UP seconds via RAMP_V.  This
# lets a case run "fire only" for the first VENT_START s, then start ventilation.
VENT_START   = 0.0
VENT_RAMP_UP = 1.0

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
FIRE_CENTER = (8.4, 1.45)
FIRE_D      = 0.89
FIRE_XB            = (FIRE_CENTER[0] - FIRE_D/2, FIRE_CENTER[0] + FIRE_D/2, 
                      FIRE_CENTER[1] - FIRE_D/2, FIRE_CENTER[1] + FIRE_D/2)
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
# SOOT_YIELD / CO_YIELD intentionally NOT overridden -- FDS uses its built-in
# n-heptane defaults (≈ 0.015 / 0.006).  Smoke still flows through the cabin
# and is captured by SMOKE3D + VISIBILITY/SOOT SLCFs on the Fig 6 planes
# (see slice block below).  Edit the &REAC line directly if a custom yield
# is needed later.

# ---- HRR ramp -- t² growth, then steady ; HRR_T2_POINTS=0 disables -------
HRR_T2_POINTS = 30          # >0 = generate t² ramp with N anchor points
HRR_T2_TPEAK  = 30.0        # time to peak HRR (s)
HRR_PEAK_KW   = 863.0       # peak HRR (paper Table 4)
HRRPUA        = 863.0       # peak HRRPUA [kW/m²] — set directly, not derived from area

# ---- Wall thickness ------------------------------------------------------
# Single source of truth — propagates to every &OBST wall position, every
# vent attachment face (Y_SOUTH, Y_NORTH, Y_OSR_N_OSR, X_E), every door HOLE
# margin, and the &SURF THICKNESS of all steel walls.  Change this one line
# and re-run to shrink/expand every wall consistently.
WALL_THICKNESS = 0.20          # m  general walls (outer + partition)
FLOOR_THICKNESS = 0.20         # m  floor surface only

# ---- Grid / time / mesh decomposition ------------------------------------
IJK         = (130, 100, 30)   # (NX, NY, NZ)
MESH_SPLIT  = (1, 1, 1)        # (MX, MY, MZ) sub-meshes for MPI
T_END       = 600.0            # seconds

# ---- Output cadence (seconds) --------------------------------------------
DT_DEVC   = 1.0
DT_HRR    = 1.0
DT_SLCF   = 2.0
DT_BNDF   = 30.0
DT_SL3D   = 2.0    # 3D SMOKE3D / soot density output for SmokeView

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
    
    wt = WALL_THICKNESS
    Domain_x0 = 0.0 - wt; Domain_xN = 13.0 + wt
    Domain_y0 = 0.0 - wt; Domain_yN = 10.0 + wt
    Domain_z0 = 0.0 - wt; Domain_zN =  3.0 + wt

    Y_SOUTH     = 0.0            # gas-side face of south outer wall (y=[-wt,0] → inner at y=0)
    Y_OSR_N     = 3.0 + wt/2    # MER-side face of osr_north_wall (unchanged)
    Y_OSR_N_OSR = 3.0 - wt/2    # OSR-side face of osr_north_wall (unchanged)
    Y_NORTH     = 10.0           # gas-side face of north outer wall (y=[10,10+wt] → inner at y=10)
    X_W = 4.0                    # west extreme of ventilated band (matches osr_north_wall x1)
    X_E = 13.0                   # gas-side face of east outer wall (x=[13,13+wt] → inner at x=13)
    Z_TOP = cfg.z_max            # interior ceiling = 3.0 (z not extended)
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
                     X_W,     X_W + L, Y_NORTH, Y_NORTH, Z_BOT,     Z_BOT + L, wall="outer_north"),
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
                     X_E - L, X_E,     Y_NORTH, Y_NORTH, Z_BOT, Z_BOT + L, wall="outer_north"),
            HVACVent("outlet_04", "exhaust",
                     X_W,     X_W + L, Y_NORTH, Y_NORTH, Z_BOT, Z_BOT + L, wall="outer_north"),
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
                     X_E - L, X_E,     Y_NORTH, Y_NORTH, Z_BOT, Z_BOT + L, wall="outer_north"),
            HVACVent("outlet_04", "exhaust",
                     X_W,     X_W + L, Y_NORTH, Y_NORTH, Z_BOT, Z_BOT + L, wall="outer_north"),
        ]

    return vents


# ---------- Fig 1 defaults ---------------------------------------------------

def default_equipment() -> list[Eq]:
    """Equipment OBSTs -- only items inside the Main Engine Room (OSR is empty)."""
    return [
        # main engine: 6.5 × 3.8 × 2.0 m  (in MER)
        Eq("main_engine",      3.5,  10.0, 5.2, 9.0, 0.0, 2.0, color="PURPLE"),
        # fuel oil supply unit: 2 × 1 × 1 m  (in MER, just north of divider)
        Eq("fuel_oil_supply",  4.5,   6.5, 3.7, 4.7, 0.0, 1.0, color="PURPLE"),
        # preheater: 0.2 × 1 × 0.5 m  (in MER, east of main engine)
        Eq("preheater",       11.8, 12.0, 4.5, 5.5, 0.0, 0.5, color="PURPLE"),
    ]


def default_walls() -> list[Wall]:
    """All walls for the sealed cabin + 7 internal rooms.  Thickness comes
    from module-level WALL_THICKNESS; every wall's "reference face" stays put
    and the wall extends inward (outer walls) or away from the room boundary
    (internal walls) by WALL_THICKNESS.

    Outer walls now sit OUTSIDE the interior room [0,13]×[0,10]×[0,3] so the
    mesh can extend by wt in every direction (domain = [-wt, 13+wt] × ...).
    Floor (z_bot) and ceiling (z_top) walls are included explicitly.
    """
    wt = WALL_THICKNESS
    # Interior room extents
    x0, xN = 0.0, 13.0
    y0, yN = 0.0, 10.0
    z0, zN = 0.0,  3.0
    # Extended domain extents
    dx0, dxN = x0 - wt, xN + wt
    dy0, dyN = y0 - wt, yN + wt
    dz0, dzN = z0 - wt, zN + wt
    return [
        # ---- outer perimeter (sealed cabin) -- walls now fully outside interior
        # x / y: extended by wt (OBSTs sit outside room).
        # z: NOT extended — floor/ceiling use MB='ZMIN'/'ZMAX' SURF instead.
        Wall("outer_west",  dx0,  x0,  dy0, dyN, z0, zN, color="WHITE"),
        Wall("outer_east",   xN, dxN,  dy0, dyN, z0, zN, color="WHITE"),
        Wall("outer_south", dx0, dxN,  dy0,  y0, z0, zN, color="WHITE"),
        Wall("outer_north", dx0, dxN,   yN, dyN, z0, zN, color="WHITE"),

        # ---- interior vertical walls (east walls of the small left rooms) ----
        # East wall of rooms 1+2+3: room-east face fixed at x=2.3, extends east by wt
        Wall("east_rooms_1to3", 2.2, 2.2 + wt, 4.1, 9.5 + wt, 0.0, 3.0, color="WHITE"),
        # East wall of rooms 4+5: room-east face fixed at x=3.8.  South end starts
        # at the interior room boundary (y = 0; outer_south wall is now at y=[-wt,0]).
        Wall("east_rooms_4_5",  4.0 - wt, 4.0, 0.0, 4.1, 0.0, 3.0, color="WHITE"),

        # ---- interior horizontal walls (between rooms / room tops) -----------
        # Each starts at the room-top y line and extends NORTH by wt.
        Wall("h_top_room1",   0.0, 2.2,  9.5, 9.5 + wt, 0.0, 3.0, color="WHITE"),
        Wall("h_room1_room2", 0.0, 2.2,  7.5, 7.5 + wt, 0.0, 3.0, color="WHITE"),
        Wall("h_room2_room3", 0.0, 2.2,  5.8, 5.8 + wt, 0.0, 3.0, color="WHITE"),
        Wall("h_room3_room4", 0.0, 4.0,  4.1, 4.1 + wt, 0.0, 3.0, color="WHITE"),
        Wall("h_room4_room5", 0.0, 4.0,  2.0, 2.0 + wt, 0.0, 3.0, color="WHITE"),
        # OSR-MER divider — MER-side face fixed at y=3.0, extends south by wt
        Wall("osr_north_wall", 4.0, 13.0, 3.0 - wt/2, 3.0 + wt/2, 0.0, 3.0, color="WHITE"),
    ]


def default_holes() -> list[Hole]:
    """Doors as &HOLE openings.  Holes span their host wall + 0.05 m margin
    on each side so FDS reliably carves out the wall cells regardless of
    mesh alignment.  Door y/x positions track WALL_THICKNESS automatically.
    """
    wt = WALL_THICKNESS
    margin = 0.05
    door1_center_y = (9.5 + 7.5 + wt)/2
    return [
        # Door 1 — east wall of room1 (east_rooms_1to3, x=[2.3, 2.3+wt])
        Hole("door1_main_to_room1",
             2.2 - margin, 2.2 + wt + margin,    # span the wall + margin
             door1_center_y - 0.2, door1_center_y + 0.2,
             0.0, 2.0),
        # Door 2 — north wall of OSR (osr_north_wall, y=[3.0-wt, 3.0]).
        # Centered on fire x (cx=8.25): x=[7.75, 8.75], width 1.0 m, h 2 m.
        # Drives Method 3's door-centred inlet position.
        Hole("door2_main_to_osr",
             8.1 - 0.5, 8.1 + 0.5,
             3.0 - wt/2 - margin, 3.0 + wt/2 + margin,
             0.0, 2.0),
    ]


def default_ext_vents() -> list[ExtVent]:
    """Sealed cabin → no external OPEN vents by default."""
    return []


# ---------- configuration ----------------------------------------------------

@dataclass
class Cfg:
    chid: str = "engine_room"
    title: str = "Marine engine-room fire (Lan et al. 2023, Fig 1)"

    # Domain XB [m]  — x/y extended by WALL_THICKNESS so outer-wall OBSTs sit
    # fully inside the mesh.  z is NOT extended: floor/ceiling are handled via
    # MB='ZMIN'/'ZMAX' SURF (steel) rather than floor/ceiling OBST blocks.
    # Interior room = [0,13]×[0,10]×[0,3].
    x_min: float = -WALL_THICKNESS
    x_max: float = 13.0 + WALL_THICKNESS
    y_min: float = -WALL_THICKNESS
    y_max: float = 10.0 + WALL_THICKNESS
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
    vent_start:    float = VENT_START      # >0 → vents closed until this time
    vent_ramp_up:  float = VENT_RAMP_UP    # seconds to ramp 0→full at vent_start
    hvac_vents: list[HVACVent] = field(default_factory=list)   # auto-populated

    # Fire VENT XB on the floor (z=0).  Defaults from module constant FIRE_XB
    # (1×1 m pool at (8.25, 1.45) matching paper Fig 6 monitoring slices).
    fire_x_min: float = FIRE_XB[0]
    fire_x_max: float = FIRE_XB[1]
    fire_y_min: float = FIRE_XB[2]
    fire_y_max: float = FIRE_XB[3]

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
    t_end: float = T_END

    dt_devc: float = DT_DEVC
    dt_hrr: float = DT_HRR
    dt_slcf: float = DT_SLCF
    dt_bndf: float = DT_BNDF
    dt_sl3d: float = DT_SL3D
    floor_thickness: float = FLOOR_THICKNESS

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

    coldflow: bool = False       # suppress fire SURF/RAMP/VENT; ventilation only
    restart_from: float = 0.0   # >0 → RESTART=.TRUE., T_BEGIN=restart_from, ramp shifted
    fire_start: float = 0.0     # >0 → fire RAMP starts at this time (F=0 before)
    engine_tz: bool = False     # emit engine-footprint x,y-avg T(z) VOLUME MEAN DEVC slabs
    ceiling_backing: str = "exposed"  # ZMAX ceiling: 'exposed'(steel, loses heat) |
                                      # 'insulated'(steel, back-face adiabatic) | 'adiabatic'(no heat transfer)


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
    # z_min is allowed to be negative when the domain is extended by WALL_THICKNESS
    if cfg.z_min > TOL:
        errs.append(f"z_min must be ≤ 0; got {cfg.z_min}")
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
    # z is NOT extended: domain top = interior ceiling
    wt = WALL_THICKNESS
    room_z_max = cfg.z_max             # = 3.0

    # Interior walls (z1=0) span to the room ceiling, not the extended domain top
    for w in cfg.walls:
        if w.z1 == 0.0:
            w.z2 = room_z_max

    # Auto-populate HVAC vents based on ventilation_method (Lan et al. Fig 2)
    if cfg.ventilation_method in (1, 2, 3) and not cfg.hvac_vents:
        cfg.hvac_vents = vents_for_method(cfg.ventilation_method, cfg)

    validate_geometry(cfg)

    peak = max(q for _, q in cfg.hrr_curve)
    fire_area = (cfg.fire_x_max - cfg.fire_x_min) * (cfg.fire_y_max - cfg.fire_y_min)
    hrrpua = HRRPUA
    dx = (cfg.x_max - cfg.x_min) / cfg.nx
    dy = (cfg.y_max - cfg.y_min) / cfg.ny
    dz = (cfg.z_max - cfg.z_min) / cfg.nz


    L: list[str] = []
    p = L.append

    p(f"&HEAD CHID='{cfg.chid}', TITLE='{cfg.title}' /")
    p("")
    p("! ============================================================")
    room_lx = cfg.x_max - cfg.x_min - 2*wt  # x/y extended by wt
    room_ly = cfg.y_max - cfg.y_min - 2*wt
    room_lz = cfg.z_max - cfg.z_min         # z not extended
    p(f"! Interior: {room_lx:.2g} × {room_ly:.2g} × {room_lz:.2g} m  "
      f"(x[0,{room_lx:.2g}] y[0,{room_ly:.2g}] z[0,{room_lz:.2g}])")
    p(f"! Domain   : x[{cfg.x_min},{cfg.x_max}] y[{cfg.y_min},{cfg.y_max}] z[{cfg.z_min},{cfg.z_max}]"
      f"  (wall ±{wt} m)")
    p(f"! Fire   : floor VENT x=[{cfg.fire_x_min},{cfg.fire_x_max}]  "
      f"y=[{cfg.fire_y_min},{cfg.fire_y_max}]  z=0  "
      f"({fire_area:.2f} m², peak HRR={peak:.0f} kW, HRRPUA={hrrpua:.1f} kW/m²)")
    p(f"! Floor  : steel THICKNESS={cfg.floor_thickness} m")
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
    p(f"&MISC TMPA={cfg.tmpa}, TURBULENCE_MODEL='CONSTANT SMAGORINSKY' /  ! paper §2.1 LES + Table 3 ambient air")
    p(f"&DUMP DT_DEVC={cfg.dt_devc}, DT_HRR={cfg.dt_hrr}, "
      f"DT_SLCF={cfg.dt_slcf}, DT_BNDF={cfg.dt_bndf}, "
      f"DT_SL3D={cfg.dt_sl3d}, SMOKE3D=.TRUE., MASS_FILE=.TRUE. /")
    p("")
    p(f"&REAC ID='DIESEL', FUEL='{cfg.fuel}', "
      f"HEAT_OF_COMBUSTION={cfg.heat_of_combustion_kjkg:.0f}, "
      f"RADIATIVE_FRACTION={cfg.radiative_fraction} /  ! paper Table 2 (diesel)")
    p(f"&RADI KAPPA0=1.7 /  ! paper Table 2 effective absorption coefficient")
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
          + (f", delayed start at t={cfg.vent_start:.0f} s "
             f"(fire-only for t<{cfg.vent_start:.0f} s)" if cfg.vent_start > 0 else ""))
        # Delayed activation: RAMP_V scales VEL by F(t); F=0 holds the vents
        # closed (no flow) until vent_start, then ramps to full over vent_ramp_up s.
        ramp_attr = ", RAMP_V='vent_ramp'" if cfg.vent_start > 0 else ""
        # SURF for intake: VEL < 0 means flow OUT of solid INTO gas (FDS sign convention)
        p(f"&SURF ID='vent_intake',  VEL=-{v_speed}{ramp_attr}, COLOR='GREEN', TMP_FRONT=20.0 /  ! supply (inflow, VEL<0)")
        p(f"&SURF ID='vent_exhaust', VEL={v_speed}{ramp_attr},  COLOR='BLUE' /  ! exhaust (outflow, VEL>0)")
        if cfg.vent_start > 0:
            p(f"&RAMP ID='vent_ramp', T=0.000, F=0.000 /")
            p(f"&RAMP ID='vent_ramp', T={cfg.vent_start:.3f}, F=0.000 /  ! vents closed: fire-only phase")
            p(f"&RAMP ID='vent_ramp', T={cfg.vent_start + cfg.vent_ramp_up:.3f}, F=1.000 /  ! vents at full velocity")
        for v in cfg.hvac_vents:
            sid = "vent_intake" if v.kind == "intake" else "vent_exhaust"
            p(f"&VENT XB={v.x1},{v.x2},{v.y1},{v.y2},{v.z1},{v.z2}, "
              f"SURF_ID='{sid}' /  ! {v.label} ({v.kind} on {v.wall})")
        p("")

    # ---- HRR ramp
    # fire_start > 0: prepend T=0/F=0 and T=fire_start/F=0, then shift curve
    # coldflow: t_offset = t_end (fire never starts)
    # restart_from: legacy cold+fire restart approach
    if cfg.coldflow:
        t_offset = cfg.t_end
    elif cfg.fire_start > 0:
        t_offset = cfg.fire_start
    else:
        t_offset = cfg.restart_from
    fire_desc = (f"fire starts at t={cfg.fire_start:.0f} s"
                 if cfg.fire_start > 0 else
                 "fire from t=0")
    p(f"! Fire HRR ramp ({fire_desc})")
    if cfg.fire_start > 0:
        p(f"&RAMP ID='fire_hrr', T=0.000, F=0.000000 /")
    for t, q in cfg.hrr_curve:
        frac = q / peak if peak > 0 else 0.0
        p(f"&RAMP ID='fire_hrr', T={t + t_offset:.3f}, F={frac:.6f} /")
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
    # All solid surfaces: steel, EXPOSED backing (heat conducts through to ambient).
    for sid, col in wall_surfs.items():
        p(f"&SURF ID='{sid}', MATL_ID='STEEL', THICKNESS={WALL_THICKNESS}, "
          f"BACKING='EXPOSED', COLOR='{col}' /")
    for sid, col in eq_surfs.items():
        p(f"&SURF ID='{sid}', MATL_ID='STEEL', THICKNESS={WALL_THICKNESS}, "
          f"BACKING='EXPOSED', COLOR='{col}' /")
    p(f"&SURF ID='surf_floor', MATL_ID='STEEL', THICKNESS={cfg.floor_thickness}, "
      "BACKING='EXPOSED', COLOR='GRAY' /")
    if cfg.ceiling_backing == "adiabatic":
        p("&SURF ID='surf_ceiling', ADIABATIC=.TRUE., COLOR='WHITE' /  "
          "! ADIABATIC ceiling (no heat transfer)")
    elif cfg.ceiling_backing == "insulated":
        p(f"&SURF ID='surf_ceiling', MATL_ID='STEEL', THICKNESS={WALL_THICKNESS}, "
          "BACKING='INSULATED', COLOR='WHITE' /  ! steel ceiling, back face insulated")
    p(f"&SURF ID='fire', COLOR='RED', HRRPUA={hrrpua:.3f}, RAMP_Q='fire_hrr' /")
    p("")

    # ---- walls
    p(f"! {len(cfg.walls)} internal walls (rooms partition) -- steel")
    for w in cfg.walls:
        sid = f"surf_wall_{w.color.lower()}"
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

    # ---- floor: 4 patches surrounding the fire footprint (no overlap → no warning)
    xd0, xdN = cfg.x_min, cfg.x_max
    yd0, ydN = cfg.y_min, cfg.y_max
    fx0, fxN = cfg.fire_x_min, cfg.fire_x_max
    fy0, fyN = cfg.fire_y_min, cfg.fire_y_max
    p(f"! floor except fire footprint (4 patches, z=0), thickness={cfg.floor_thickness} m")
    p(f"&VENT XB={xd0},{xdN},{yd0},{fy0},0,0, SURF_ID='surf_floor' /  ! floor south")
    p(f"&VENT XB={xd0},{xdN},{fyN},{ydN},0,0, SURF_ID='surf_floor' /  ! floor north")
    p(f"&VENT XB={xd0},{fx0},{fy0},{fyN},0,0, SURF_ID='surf_floor' /  ! floor west")
    p(f"&VENT XB={fxN},{xdN},{fy0},{fyN},0,0, SURF_ID='surf_floor' /  ! floor east")
    p("")

    # ---- ceiling
    if cfg.ceiling_backing in ("adiabatic", "insulated"):
        p(f"&VENT MB='ZMAX', SURF_ID='surf_ceiling' /  ! ceiling — {cfg.ceiling_backing}")
    else:
        p("&VENT MB='ZMAX', SURF_ID='surf_wall_white' /  ! ceiling — steel (exposed)")
    p("")

    # ---- fire VENT (no overlap with floor patches)
    p(f"&VENT XB={cfg.fire_x_min},{cfg.fire_x_max},"
      f"{cfg.fire_y_min},{cfg.fire_y_max},0,0, SURF_ID='fire' /  ! fire footprint")
    p("")

    # ---- grid-convergence vertical T lines (Lan et al. 2023 §3.3, Fig 5)
    cx = (cfg.fire_x_min + cfg.fire_x_max) / 2
    cy = (cfg.fire_y_min + cfg.fire_y_max) / 2
    # T(z) vertical lines at fire centerline x=cx, y = cy + Δy for
    # Δy in [0.0, 0.1, ..., 1.5].  Each uses POINTS=30.  Lines that pass
    # through solid cells are automatically dropped with a WARNING.
    gx = cx
    n_gridconv = 30                  # MUST equal npts_line (line.csv shared)
    proposed = [
        # (id,                    y,          z_min, z_max,              descr)
        (f"gridconv_T_dy{round(dy*10):02d}",
         cy + dy,
         0.05, room_z_max - 0.05,
         f"centre +{dy:.1f} m")
        for dy in [i * 0.1 for i in range(16)]   # +0.0, +0.1, ..., +1.5
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
    p(f"! Grid-convergence T(z) lines (paper §3.3 Fig 5)")
    for did, gy, z_lo, z_hi, descr in proposed:
        n_bad, blocker = _line_inside_solid(gx, gy, z_lo, z_hi)
        if n_bad > 0:
            msg = (f"WARNING: DEVC '{did}' ({descr}) at x={gx:.3f}, y={gy:.3f}: "
                   f"{n_bad}/{n_gridconv} sample points inside {blocker} — "
                   f"sample line drops INTO solid OBST.  DEVC OMITTED.")
            print(msg, file=_sys.stderr)
            p(f"! {msg}")
            continue
        p(f"&DEVC ID='{did}', XB={gx:.4f},{gx:.4f},{gy:.4f},{gy:.4f},"
          f"{z_lo:.4f},{z_hi:.4f}, POINTS={n_gridconv}, "
          f"QUANTITY='TEMPERATURE', HIDE_COORDINATES=.TRUE. /  "
          f"! {descr}, z=[{z_lo:.2f}, {z_hi:.2f}]")
    p("")

    # ---- main engine top sensor: vertical line z=[2,3] above engine centre ----
    # main_engine spans x=[3.5,10.0] y=[5.2,9.0] z=[0,2]; centre = (6.75, 7.1)
    me_cx = 6.75
    me_cy = 7.1
    me_z_lo, me_z_hi = 2.0, 3.0
    me_pts = 11   # 0.1 m spacing over 1 m
    for qty in ("TEMPERATURE", "HRRPUV"):
        p(f"&DEVC ID='main_eng_{qty.lower().replace('-','_')}', "
          f"XB={me_cx:.4f},{me_cx:.4f},{me_cy:.4f},{me_cy:.4f},"
          f"{me_z_lo:.4f},{me_z_hi:.4f}, POINTS={me_pts}, "
          f"QUANTITY='{qty}', HIDE_COORDINATES=.TRUE. /  "
          f"! above main engine centre, z=[{me_z_lo},{me_z_hi}]")
    p("")

    # ---- engine-footprint horizontal-average T(z) slabs (x,y VOLUME MEAN per z-cell)
    # One DEVC per z grid-cell spanning the FULL main-engine footprint in x,y and
    # exactly one cell in z, using SPATIAL_STATISTIC='VOLUME MEAN'.  Together they
    # give the x,y-averaged vertical temperature profile T̄(z,t) over the engine,
    # written to the DEVC .csv — cheap (scalars per DT_DEVC), no 3D/PLOT3D dump.
    # Range = engine top (solid below) → ceiling, i.e. the gas gap above the engine.
    if cfg.engine_tz:
        eng = next((e for e in cfg.equipment if e.label == "main_engine"), None)
        if eng is not None:
            p(f"! Engine-footprint x,y-averaged T(z): one VOLUME MEAN DEVC per z-cell")
            p(f"!   footprint x=[{eng.x1},{eng.x2}] y=[{eng.y1},{eng.y2}], "
              f"engine top z={eng.z2}, ceiling z={cfg.z_max}, dz={dz:.4f} m")
            k0 = 0
            for k in range(cfg.nz):
                zc = cfg.z_min + (k + 0.5) * dz          # z cell-centre
                if zc < eng.z2 - 1e-9 or zc > cfg.z_max + 1e-9:
                    continue                             # skip cells inside/below engine
                zlo, zhi = zc - dz / 2, zc + dz / 2       # this cell's z-bounds
                p(f"&DEVC ID='engTz_{k0:02d}', "
                  f"XB={eng.x1},{eng.x2},{eng.y1},{eng.y2},{zlo:.4f},{zhi:.4f}, "
                  f"QUANTITY='TEMPERATURE', SPATIAL_STATISTIC='VOLUME MEAN' /  "
                  f"! x,y-avg T at z={zc:.4f} m")
                k0 += 1
            p(f"! ({k0} engine-Tz slabs emitted)")
            p("")

    # ---- slices: paper Fig 6 monitoring planes (x=8.1, 8.4, y=1.45, z=2.0)
    # x=8.1 / x=8.4 flank the fire at x=[7.75,8.75] from each side, y=1.45 is
    # the fire's longitudinal centerline, z=2 captures the upper smoke layer.
    # y=7.1 passes through the main engine centre (XZ plane).
    # T + HRRPUV : flame/temperature ; VISIBILITY + SOOT : smoke visualization.
    # me_cx=6.75 / me_cy=7.1 = main-engine centre (defined just above).  Cut both
    # centre planes through the engine: PBX=me_cx (Y-Z plane) + PBY=me_cy (X-Z plane).
    SLCF_X = [me_cx, 8.1, 8.4]
    SLCF_Y = [1.45, me_cy]
    SLCF_Z = [0.3, 2.0, 2.7]
    for q in ("TEMPERATURE", "HRRPUV", "VISIBILITY",
              "U-VELOCITY", "V-VELOCITY", "W-VELOCITY"):
        for xs in SLCF_X:
            p(f"&SLCF PBX={xs:.3f}, QUANTITY='{q}' /")
        for ys in SLCF_Y:
            p(f"&SLCF PBY={ys:.3f}, QUANTITY='{q}' /")
        for zs in SLCF_Z:
            p(f"&SLCF PBZ={zs:.3f}, QUANTITY='{q}' /")
    # SOOT mass fraction on the same planes for smoke stratification (Fig 16/18)
    for xs in SLCF_X:
        p(f"&SLCF PBX={xs:.3f}, QUANTITY='MASS FRACTION', SPEC_ID='SOOT' /")
    for ys in SLCF_Y:
        p(f"&SLCF PBY={ys:.3f}, QUANTITY='MASS FRACTION', SPEC_ID='SOOT' /")
    for zs in SLCF_Z:
        p(f"&SLCF PBZ={zs:.3f}, QUANTITY='MASS FRACTION', SPEC_ID='SOOT' /")
    # Velocity vector field on all monitoring planes
    for xs in SLCF_X:
        p(f"&SLCF PBX={xs:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /")
    for ys in SLCF_Y:
        p(f"&SLCF PBY={ys:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /")
    for zs in SLCF_Z:
        p(f"&SLCF PBZ={zs:.3f}, QUANTITY='VELOCITY', VECTOR=.TRUE. /")
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
                   default=[-WALL_THICKNESS, 13.0 + WALL_THICKNESS,
                            -WALL_THICKNESS, 10.0 + WALL_THICKNESS,
                            0.0, 3.0],
                   metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"))
    p.add_argument("--ijk", nargs=3, type=int, default=list(IJK),
                   metavar=("NX", "NY", "NZ"))
    p.add_argument("--mesh-split", nargs=3, type=int, default=list(MESH_SPLIT),
                   metavar=("MX", "MY", "MZ"),
                   help="Sub-meshes per axis (must divide IJK).")
    p.add_argument("--fire-xb", nargs=4, type=float, default=list(FIRE_XB),
                   metavar=("XMIN", "XMAX", "YMIN", "YMAX"))
    p.add_argument("--fire-diameter", type=float, default=None, metavar="D",
                   help="Square fire pool of side D [m] centred at FIRE_CENTER "
                        f"({FIRE_CENTER[0]},{FIRE_CENTER[1]}). Overrides --fire-xb; "
                        "e.g. --fire-diameter 1.0 for a 1 m fire.")
    p.add_argument("--open", nargs="*", default=[],
                   choices=["XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"])
    p.add_argument("--fuel", default=FUEL)
    p.add_argument("--radiative-fraction", type=float, default=RADIATIVE_FRACTION)
    p.add_argument("--floor-thickness", type=float, default=FLOOR_THICKNESS,
                   help="Steel floor surface thickness [m]. Does not change wall geometry.")
    p.add_argument("--t-end", type=float, default=T_END)
    p.add_argument("--fire-off", type=float, default=None,
                   help="Extinguish fire at this time [s]. After fire_off the ramp "
                        "drops to 0 and stays 0 until T_END.")
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
    p.add_argument("--vent-start", type=float, default=VENT_START, metavar="T_VENT",
                   help="Hold mechanical vents closed until this time [s], then "
                        "ramp to full velocity (0 = vents on from t=0).")
    p.add_argument("--vent-ramp-up", type=float, default=VENT_RAMP_UP, metavar="DT",
                   help="Seconds to ramp vents 0→full velocity at --vent-start.")
    p.add_argument("--coldflow", action="store_true",
                   help="Ventilation-only run: omit fire SURF/RAMP/VENT")
    p.add_argument("--restart-from", type=float, default=0.0, metavar="T_BEGIN",
                   help="Restart run: add RESTART=.TRUE., T_BEGIN=T, shift HRR ramp by T")
    p.add_argument("--fire-start", type=float, default=0.0, metavar="T_FIRE",
                   help="Delay fire ignition: RAMP=0 for t<T_FIRE, then t² growth")
    p.add_argument("--engine-tz", action="store_true",
                   help="Emit engine-footprint x,y-averaged T(z) DEVCs: one VOLUME MEAN "
                        "temperature slab per z-cell from engine top to ceiling "
                        "(gives T̄(z,t) over the main-engine footprint as CSV, no PLOT3D).")
    p.add_argument("--ceiling-backing", choices=["exposed", "insulated", "adiabatic"],
                   default="exposed",
                   help="ZMAX ceiling thermal boundary: 'exposed'=steel losing heat to "
                        "ambient (default); 'insulated'=steel with adiabatic back face "
                        "(keeps heat, still absorbs into the slab); 'adiabatic'=no heat "
                        "transfer at all (hottest). Raises ceiling gas temp exposed<insulated<adiabatic.")
    p.add_argument("--ceiling-insulated", action="store_true",
                   help="Shortcut for --ceiling-backing adiabatic.")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    # --fire-diameter: build a square footprint of side D centred at FIRE_CENTER,
    # overriding --fire-xb so "1 m fire" is a single number.
    if a.fire_diameter is not None:
        cx, cy = FIRE_CENTER
        half = a.fire_diameter / 2.0
        a.fire_xb = [cx - half, cx + half, cy - half, cy + half]
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
        floor_thickness=a.floor_thickness,
        t_end=a.t_end,
        dt_devc=a.dt_devc, dt_hrr=a.dt_hrr,
        dt_slcf=a.dt_slcf, dt_bndf=a.dt_bndf,
        centerline_quantities=a.centerline_q,
        centerline_n_points=a.centerline_n_points,
        ventilation_method=a.ventilation_method,
        ventilation_velocity=a.ventilation_velocity,
        vent_start=a.vent_start,
        vent_ramp_up=a.vent_ramp_up,
        coldflow=a.coldflow,
        restart_from=a.restart_from,
        fire_start=a.fire_start,
        engine_tz=a.engine_tz,
        ceiling_backing=("adiabatic" if a.ceiling_insulated else a.ceiling_backing),
    )
    cfg.centerline_spec = []
    for item in a.centerline_spec:
        if ":" not in item:
            sys.exit(f"ERROR: --centerline-spec item '{item}' must be 'QUANTITY:SPEC_ID'")
        q, spec = item.split(":", 1)
        cfg.centerline_spec.append((q.strip(), spec.strip()))
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
        if a.fire_off is not None:
            # sustain at peak until fire_off, then extinguish
            if a.fire_off > tp:
                curve.append((a.fire_off, qp))
            curve.append((a.fire_off + 0.1, 0.0))
            if a.t_end > a.fire_off + 0.1:
                curve.append((a.t_end, 0.0))
        elif a.t_end > tp:
            curve.append((a.t_end, qp))
        cfg.hrr_curve = curve

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_input(cfg))

    peak = max(q for _, q in cfg.hrr_curve)
    cells = cfg.nx * cfg.ny * cfg.nz
    print(f"Wrote: {out}")
    wt = WALL_THICKNESS
    print(f"  Interior: {cfg.x_max-cfg.x_min-2*wt:.2g} × {cfg.y_max-cfg.y_min-2*wt:.2g} × {cfg.z_max-cfg.z_min:.2g} m  "
          f"(2 rooms: Main Engine + Oil Separator)")
    print(f"  Domain:   x[{cfg.x_min},{cfg.x_max}] y[{cfg.y_min},{cfg.y_max}] z[{cfg.z_min},{cfg.z_max}]")
    print(f"  Equip:  {len(cfg.equipment)} OBSTs (engine height = {cfg.z_max/2} m)")
    print(f"  Walls:  {len(cfg.walls)} internal walls (Y=3 + X=5)")
    print(f"  Doors:  {len(cfg.holes)} internal HOLE(s) + {len(cfg.ext_vents)} external OPEN vent(s)")
    print(f"  Fire:   ({(cfg.fire_x_min+cfg.fire_x_max)/2}, "
          f"{(cfg.fire_y_min+cfg.fire_y_max)/2}) in Oil Separator Room; peak {peak:.0f} kW")
    print(f"  Floor:  steel thickness = {cfg.floor_thickness} m")
    print(f"  Grid:   {cfg.nx}×{cfg.ny}×{cfg.nz} = {cells:,} cells")
    nsub = cfg.mx * cfg.my * cfg.mz
    print(f"  Split:  {cfg.mx}×{cfg.my}×{cfg.mz} = {nsub} sub-mesh{'es' if nsub>1 else ''}; "
          f"mpiexec -n {nsub}")


if __name__ == "__main__":
    main()
