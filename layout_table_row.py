import bpy
import math
from mathutils import Vector

# ============================================================
# Layout: Table Row
#
# Arranges all mesh objects from a collection in a straight
# line on the floor — useful for comparison or overview shots.
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

# Starting position of the first card (x, y) in meters
ORIGIN_XY = (0.0, 0.0)

# Layout direction: "X" = left-to-right, "Y" = front-to-back
DIRECTION = "X"

# Distance between card centers (cm)
SPACING_CM = 8.0

# Rotate the entire row around Z (degrees)
ROTATE_Z_DEG = 0.0

# Lift cards slightly off the floor so they don't z-fight (mm)
LIFT_MM = 0.12

# Auto-frame the active scene camera to fit all cards
AUTO_FRAME_CAMERA = True
CAMERA_PADDING    = 1.25    # extra breathing room around the cards


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
    """
    Move camera along its current view direction so all cards fit in frame.
    Works with any lens length — uses the camera's actual FOV.
    """
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


# ============================================================
# MAIN
# ============================================================

def main():
    cards = get_cards(COLLECTION_NAME)
    if not cards:
        return

    spacing = SPACING_CM / 100.0
    lift    = LIFT_MM / 1000.0
    rz      = math.radians(ROTATE_Z_DEG)
    x0, y0  = ORIGIN_XY

    for i, obj in enumerate(cards):
        # Use stored thickness if available, otherwise fall back to bounding box
        thickness = obj.get("CARD_THICKNESS_M")
        if thickness is None:
            lo, hi = world_bounds([obj])
            thickness = max(hi.z - lo.z, 0.0005)

        z = thickness * 0.5 + lift

        if DIRECTION.upper() == "Y":
            obj.location = (x0, y0 + i * spacing, z)
        else:
            obj.location = (x0 + i * spacing, y0, z)

        obj.rotation_euler = (0.0, 0.0, rz)

    print(f"[Layout] Table Row — placed {len(cards)} card(s).")

    # Auto-frame active camera
    if AUTO_FRAME_CAMERA and bpy.context.scene.camera:
        lo, hi = world_bounds(cards)
        center = (lo + hi) * 0.5
        radius = (hi - lo).length * 0.5
        frame_camera(bpy.context.scene.camera, center, max(0.01, radius), CAMERA_PADDING)
        print(f"[Layout] Camera framed. Center={center}, radius={radius:.3f}")
    elif AUTO_FRAME_CAMERA:
        print("[Layout] No active camera in scene — skipping auto-frame.")


main()