#!/usr/bin/env python3
"""Draw a 2D top-view of the current engine-room geometry interpretation.

Run:  python3 visualize_layout.py
Output: layout.png  in this directory.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

fig, ax = plt.subplots(figsize=(13, 10))

# Domain
DX, DY = 13.0, 10.0
ax.add_patch(mpatches.Rectangle((0, 0), DX, DY, fill=False, edgecolor="black", linewidth=2))

# --- Equipment (yellow-filled) ---------------------------------------------
def eq(x1, x2, y1, y2, color, label, fontsize=9):
    ax.add_patch(mpatches.Rectangle((x1, y1), x2-x1, y2-y1, facecolor=color,
                                     edgecolor="black", alpha=0.7))
    ax.text((x1+x2)/2, (y1+y2)/2, label, ha="center", va="center", fontsize=fontsize)

eq(5.0, 11.5, 4.2, 8.0, "green", "Main engine\n6.5 × 3.8 m", fontsize=11)
eq(12.0, 13.0, 5.0, 6.0, "lightgray", "preheater\n1 × 1 m", fontsize=7)
eq(5.5,  7.5, 3.5, 4.5, "purple", "Fuel oil\nsupply unit\n2 × 1 m", fontsize=7)
eq(3.2, 4.0,  6.5, 8.0, "lightgray", "MEOST-A", fontsize=7)
eq(3.2, 4.0,  5.0, 6.5, "lightgray", "MEOST-B", fontsize=7)
eq(2.0, 4.0,  2.5, 4.0, "lightgray", "FOST-A", fontsize=8)
eq(2.0, 4.0,  1.0, 2.5, "lightgray", "FOST-B", fontsize=8)

# --- Fire -------------------------------------------------------------------
ax.add_patch(mpatches.Rectangle((8.0, 1.5), 1.0, 1.0,
                                 facecolor="red", edgecolor="darkred", alpha=0.85))
ax.text(8.5, 2.0, "FIRE", ha="center", va="center", fontsize=10, color="white", fontweight="bold")

# --- Internal walls (current interpretation = 2 walls) ----------------------
def wall(x1, x2, y1, y2, label=""):
    ax.add_patch(mpatches.Rectangle((x1, y1), x2-x1, y2-y1, facecolor="dimgray",
                                     edgecolor="black"))
    if label:
        ax.text((x1+x2)/2, (y1+y2)/2, label, ha="center", va="center",
                fontsize=6, color="white")

# CURRENT INTERPRETATION: only 2 walls (Y=3 + X=5)
wall(5.0, 13.0, 2.95, 3.05)  # oil_sep north wall  (Y=3)
wall(4.95, 5.05, 0.0, 3.0)   # oil_sep west wall   (X=5)

# --- Doors (HOLE-style gaps + external OPEN) --------------------------------
# Internal door (HOLE in Y=3 wall): X=7..8.5
ax.add_patch(mpatches.Rectangle((7.0, 2.85), 1.5, 0.3,
                                 facecolor="white", edgecolor="white"))
ax.text(7.75, 3.0, "door", ha="center", va="center", fontsize=8, color="brown")

# External door (north OPEN vent at Y=10): X=2..3
ax.add_patch(mpatches.Rectangle((2.0, 9.9), 1.0, 0.2,
                                 facecolor="cyan", edgecolor="blue"))
ax.text(2.5, 9.6, "door", ha="center", va="center", fontsize=8, color="blue")

# --- Labels for rooms -------------------------------------------------------
ax.text(9.0,  7.0, "MAIN ENGINE ROOM", fontsize=14, color="black", fontweight="bold",
        ha="center", alpha=0.4)
ax.text(9.5, 0.7, "Oil Separator Room", fontsize=10, color="darkred",
        ha="center", style="italic")

# --- Axes ---
ax.set_xlim(-0.5, 13.5)
ax.set_ylim(-0.5, 10.5)
ax.set_xticks(range(0, 14))
ax.set_yticks(range(0, 11))
ax.set_xlabel("X (m)", fontsize=11)
ax.set_ylabel("Y (m)", fontsize=11)
ax.set_aspect("equal")
ax.grid(True, alpha=0.3)
ax.set_title("Current engine-room layout interpretation (TOP VIEW)\n"
             "Compare with Fig 1.  Are the rooms / walls / doors correct?",
             fontsize=11)

# Annotation about my count
note = ("Current interpretation:\n"
        "  Walls (gray)   : 2  (Y=3 + X=5)\n"
        "  Doors          : 1 internal (between rooms) + 1 external (north)\n"
        "  Equipment      : 7 boxes\n"
        "  Rooms enclosed : just 2  (Main Engine Room + Oil Separator Room)\n\n"
        "User says ROOMS = 7 total\n"
        "  3 to the LEFT of Main Engine Room\n"
        "  1 Oil Separator Room\n"
        "  1 in the middle\n"
        "Please correct my room/wall layout if wrong.")
ax.text(0.2, -1.8, note, fontsize=9, family="monospace",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.7))

plt.tight_layout()
out = "/scratch/x3319a05/fds/Engine_Room/layout.png"
plt.savefig(out, dpi=110, bbox_inches="tight")
print(f"Wrote: {out}")
