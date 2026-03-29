import bpy
import math
from mathutils import Vector

# ============================================================
# Scene Setup — Studio lighting for Blender 3.x / 4.x (Cycles)
#
# Creates a clean studio scene with:
#   - Shadow-catcher floor (for shadow-only PNG renders)
#   - 3 area lights: key, fill, rim
#   - 2 camera presets: hero angle + top-down
#   - Target empty that all cameras track
#
# Designed to work with box_generator.py and card_importer.py,
# but can be used as a general-purpose studio setup.
#
# Run from Blender's Script Editor.
# ============================================================


# ============================================================
# SETTINGS  —  edit here
# ============================================================

CLEAR_AND_REBUILD = True    # remove existing scene objects and start fresh

# Render
RESOLUTION        = 2000    # output: RESOLUTION x RESOLUTION px
SAMPLES           = 256
USE_DENOISE       = True
FILM_TRANSPARENT  = True    # transparent background (great for compositing)

# Color management
# "Standard" = safest for accurate JPG colors
# "AgX"      = nicer contrast (Blender 4.x)
VIEW_TRANSFORM = "Standard"
EXPOSURE       = 0.0

# World ambient light — keep at 0 for full control via area lights
WORLD_STRENGTH = 0.0

# Target empty — cameras and lights point here
TARGET_LOCATION = (0.0, 0.0, 0.03)

# Floor (shadow catcher)
FLOOR_SIZE_M = 2.0
FLOOR_Z      = 0.0

# Light power multiplier — scale all lights at once if scene is too bright/dark
LIGHT_POWER_MULT = 0.02

# Area lights: (name, location, base_power, width, height)
LIGHTS = [
    ("LIGHT_KEY",  ( 0.55, -0.55,  0.80), 500.0, 0.60, 0.45),
    ("LIGHT_FILL", (-0.70, -0.10,  0.65), 250.0, 0.70, 0.55),
    ("LIGHT_RIM",  ( 0.00,  0.85,  0.75), 180.0, 0.55, 0.35),
]

# Cameras: (name, location, lens_mm)
# CAM_HERO  — classic 3/4 product angle
# CAM_TOP   — flat lay / top-down
CAMERAS = [
    ("CAM_HERO", (0.32, -0.58, 0.38), 85),
    ("CAM_TOP",  (0.00, -0.05, 0.90), 70),
]
ACTIVE_CAMERA = "CAM_HERO"


# ============================================================
# HELPERS
# ============================================================

def look_at(from_loc, to_loc):
    """Euler rotation so that object's -Z points toward target (camera convention)."""
    direction = Vector(to_loc) - Vector(from_loc)
    if direction.length < 1e-6:
        return (0.0, 0.0, 0.0)
    return direction.to_track_quat('-Z', 'Y').to_euler()

def set_shadow_catcher(obj):
    for attr in ("is_shadow_catcher", "cycles.is_shadow_catcher"):
        try:
            parts = attr.split(".")
            target = obj
            for p in parts[:-1]:
                target = getattr(target, p)
            setattr(target, parts[-1], True)
            return
        except Exception:
            pass
    print("[Scene] Shadow catcher API not available on this Blender build.")

def ensure_collection(name, parent=None):
    coll = bpy.data.collections.get(name)
    if not coll:
        coll = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(coll)
    return coll

def move_to_collection(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)

def remove_if_exists(name):
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)


# ============================================================
# MAIN
# ============================================================

def main():
    scene = bpy.context.scene

    # --- Render settings ---
    scene.render.engine           = "CYCLES"
    scene.render.film_transparent = FILM_TRANSPARENT
    scene.render.resolution_x     = RESOLUTION
    scene.render.resolution_y     = RESOLUTION
    scene.render.resolution_percentage = 100

    if hasattr(scene, "cycles"):
        scene.cycles.samples               = SAMPLES
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.preview_samples       = min(64, SAMPLES)

    vl = bpy.context.view_layer
    if USE_DENOISE:
        try:    vl.cycles.use_denoising = True
        except Exception: pass
    try:        vl.use_pass_shadow_catcher = True
    except Exception: pass

    # --- Color management ---
    vs = scene.view_settings
    try:    vs.view_transform = VIEW_TRANSFORM
    except Exception:
        print(f"[Scene] View transform '{VIEW_TRANSFORM}' unavailable — using {vs.view_transform}")
    try:    vs.look     = "None"
    except Exception: pass
    try:    vs.exposure = EXPOSURE
    except Exception: pass

    # --- World ---
    world = scene.world or bpy.data.worlds.new("WORLD")
    scene.world   = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value    = (1.0, 1.0, 1.0, 1.0)
        bg.inputs["Strength"].default_value = WORLD_STRENGTH

    # --- Collections ---
    if CLEAR_AND_REBUILD:
        for name in (
            ["LIGHT_KEY", "LIGHT_FILL", "LIGHT_RIM",
             "CAM_HERO", "CAM_TOP",
             "SCENE_TARGET", "SCENE_FLOOR"]
        ):
            remove_if_exists(name)

    scene_coll = ensure_collection("SCENE")
    light_coll = ensure_collection("SCENE_LIGHTS",   parent=scene_coll)
    cam_coll   = ensure_collection("SCENE_CAMERAS",  parent=scene_coll)

    # --- Target empty ---
    target = bpy.data.objects.new("SCENE_TARGET", None)
    target.empty_display_type = 'PLAIN_AXES'
    target.empty_display_size = 0.04
    target.location           = TARGET_LOCATION
    move_to_collection(target, scene_coll)

    # --- Shadow catcher floor ---
    bpy.ops.mesh.primitive_plane_add(size=FLOOR_SIZE_M, location=(0.0, 0.0, FLOOR_Z))
    floor      = bpy.context.active_object
    floor.name = "SCENE_FLOOR"
    set_shadow_catcher(floor)
    move_to_collection(floor, scene_coll)

    # --- Lights ---
    for (name, loc, power, sx, sy) in LIGHTS:
        data         = bpy.data.lights.new(name, 'AREA')
        data.energy  = power * LIGHT_POWER_MULT
        data.shape   = 'RECTANGLE'
        data.size    = sx
        data.size_y  = sy
        data.color   = (1.0, 1.0, 1.0)

        obj               = bpy.data.objects.new(name, data)
        obj.location      = loc
        obj.rotation_euler = look_at(loc, TARGET_LOCATION)
        move_to_collection(obj, light_coll)

    # --- Cameras ---
    for (name, loc, lens) in CAMERAS:
        data       = bpy.data.cameras.new(name)
        data.lens  = float(lens)

        cam               = bpy.data.objects.new(name, data)
        cam.location      = loc
        cam.rotation_euler = look_at(loc, TARGET_LOCATION)

        # Track To constraint — camera follows target if you move cards
        con              = cam.constraints.new('TRACK_TO')
        con.name         = "TrackTarget"
        con.target       = target
        con.track_axis   = 'TRACK_NEGATIVE_Z'
        con.up_axis      = 'UP_Y'

        move_to_collection(cam, cam_coll)

    # Set active camera
    active_cam = bpy.data.objects.get(ACTIVE_CAMERA)
    if active_cam and active_cam.type == 'CAMERA':
        scene.camera = active_cam

    print(f"[Scene] Setup done — {len(LIGHTS)} lights, {len(CAMERAS)} cameras.")
    print(f"        Active camera: {ACTIVE_CAMERA}")
    print(f"        Render: {RESOLUTION}×{RESOLUTION}px, {SAMPLES} samples")


main()