import bpy
import math
from mathutils import Vector

# ============================================================
# Layout: Fan
#
# Arranges cards in a hand-held fan arc on the floor.
# Each card is rotated and offset along a circular curve,
# with a small Z increment to prevent z-fighting.
#
# Works with cards created by card_importer.py, but accepts
# any mesh objects in the target collection.
#
# Run from Blender's Script Editor after importing cards.
# ============================================================


# ============================================================
# SETTINGS  —  edit here
# ============================================================

# Collection that holds the card objects
COLLECTION_NAME = "CARDS"

# Fan shape
FAN_SPREAD_DEG = 40.0   # total angle of the fan (degrees)
FAN_RADIUS_CM  = 28.0   # arc radius — larger = more spread out

# Fan center position (x, y) in meters
PIVOT_XY = (0.0, 0.0)

# Vertical placement
LIFT_MM   = 0.12    # base lift above floor (mm)
Z_STEP_MM = 0.06    # each card slightly higher than the previous (avoids z-fighting)

# Optional tilt — rotate all cards forward for a presentation angle
TILT_X_DEG = 0.0    # 0 = flat on table, e.g. 15 = leaning toward camera

# Auto-frame the active scene camera to fit all cards
AUTO_FRAME_CAMERA = True
CAMERA_PADDING    = 1.25


# ============================================================
# HELPERS
# ============================================================

def get_cards(collection_name):
    """Return mesh objects from the collection, sorted by name."""
    coll = bpy.data.collections.get(collection_name)
    if not coll:
        print(f"[Layout] Collection '{collection_name}' not found.")
        return []
    objs = [o for o in coll.objects if o.type == "MESH"]
    return sorted(objs, key=lambda o: o.name)

def world_bounds(objects):
    """Bounding box of a list of objects in world space."""
    lo = Vector(( 1e9,  1e9,  1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        for corner in obj.bound_box:
            v = obj.matrix_world @ Vector(corner)
            lo.x = min(lo.x, v.x);  hi.x = max(hi.x, v.x)
            lo.y = min(lo.y, v.y);  hi.y = max(hi.y, v.y)
            lo.z = min(lo.z, v.z);  hi.z = max(hi.z, v.z)
    return lo, hi

def frame_camera(camera_obj, center, radius, padding):
    """Move camera so all cards fit in frame, preserving view direction."""
    cam = camera_obj.data
    try:
        fov = min(cam.angle_x, cam.angle_y)
    except Exception:
        fov = cam.angle

    distance  = (radius / max(1e-6, math.sin(fov * 0.5))) * padding
    direction = camera_obj.location - center
    if direction.length < 1e-6:
        direction = Vector((0.0, -1.0, 0.3))
    direction.normalize()
    camera_obj.location = center + direction * distance

def get_thickness(obj):
    """Read stored thickness or estimate from bounding box."""
    t = obj.get("CARD_THICKNESS_M")
    if t is not None:
        return float(t)
    lo, hi = world_bounds([obj])
    return max(hi.z - lo.z, 0.0005)


# ============================================================
# MAIN
# ============================================================

def main():
    cards = get_cards(COLLECTION_NAME)
    n = len(cards)
    if n == 0:
        return

    spread = math.radians(FAN_SPREAD_DEG)
    R      = FAN_RADIUS_CM / 100.0
    lift   = LIFT_MM   / 1000.0
    zstep  = Z_STEP_MM / 1000.0
    tilt   = math.radians(TILT_X_DEG)
    px, py = PIVOT_XY

    if n == 1:
        # Single card — place flat at pivot
        th = get_thickness(cards[0])
        cards[0].location      = (px, py, th * 0.5 + lift)
        cards[0].rotation_euler = (tilt, 0.0, 0.0)
    else:
        for i, obj in enumerate(cards):
            th = get_thickness(obj)

            # Evenly distribute cards across the fan angle
            t   = i / (n - 1)
            ang = -spread * 0.5 + spread * t

            # Position along arc: cards curve away from camera
            x = px + R * math.sin(ang)
            y = py - R * (1.0 - math.cos(ang))
            z = th * 0.5 + lift + i * zstep

            obj.location      = (x, y, z)
            obj.rotation_euler = (tilt, 0.0, ang)

    print(f"[Layout] Fan — placed {n} card(s), spread={FAN_SPREAD_DEG}°, radius={FAN_RADIUS_CM}cm.")

    # Auto-frame active camera
    if AUTO_FRAME_CAMERA and bpy.context.scene.camera:
        lo, hi = world_bounds(cards)
        center = (lo + hi) * 0.5
        radius = (hi - lo).length * 0.5
        frame_camera(bpy.context.scene.camera, center, max(0.01, radius), CAMERA_PADDING)
        print(f"[Layout] Camera framed.")
    elif AUTO_FRAME_CAMERA:
        print("[Layout] No active camera — skipping auto-frame.")


main()