import bpy
import bmesh
import math
from mathutils import Vector

# ============================================================
# Box Generator for Blender 3.x / 4.x
#
# Creates a two-piece assembled box (lid + bottom) with:
#   - Procedural cardboard materials (no external textures needed)
#   - Solidify + Bevel + WeightedNormal modifiers
#   - Simple studio scene: 3 area lights + camera
#   - Optional inner lip on the lid
#   - CLOSED or OPEN display mode
#
# Run this script from Blender's Script Editor.
# ============================================================


# ============================================================
# SETTINGS  —  edit here
# ============================================================

# Box dimensions in mm  (Width, Depth, Height)
LID_OUTER    = (211.0, 119.0, 45.0)
BOTTOM_OUTER = (206.0, 114.0, 55.0)

# Cardboard thickness and edge rounding
WALL_THICKNESS = 2.0    # mm
BEVEL_RADIUS   = 0.9    # mm
BEVEL_SEGMENTS = 3      # 2–4

# Assembly fit
CLEARANCE_GAP  = 0.4    # mm  — tiny gap so lid doesn't intersect bottom
OVERLAP_DEPTH  = 22.0   # mm  — how deep lid sits over bottom

# Lid inner lip (helps alignment)
ADD_LIP       = True
LIP_HEIGHT    = 10.0    # mm
LIP_INSET     = 2.5     # mm
LIP_THICKNESS = 1.2     # mm

# Display pose
DISPLAY_MODE   = "CLOSED"   # "CLOSED" or "OPEN"
OPEN_ANGLE_DEG = 25.0
OPEN_OFFSET_MM = 25.0

# Scene
LIGHT_POWER_MULT = 0.05     # reduce if scene looks too bright


# ============================================================
# HELPERS
# ============================================================

def mm(v): return v / 1000.0

def ensure_object_mode():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

def deselect_all():
    bpy.ops.object.select_all(action='DESELECT')

def delete_if_exists(name):
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)

def set_bsdf(bsdf, name, value):
    sock = bsdf.inputs.get(name)
    if sock:
        sock.default_value = value


# ============================================================
# MATERIALS  —  procedural, no textures required
# ============================================================

def make_cardboard_material(name, base_color=(0.72, 0.65, 0.55, 1.0)):
    """
    Matte cardboard-like material using Principled BSDF.
    Slightly warm grey-beige — looks neutral for portfolio renders.
    Change base_color to match your product.
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out  = nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (0, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if bsdf.inputs.get("Base Color"):
        bsdf.inputs["Base Color"].default_value = base_color

    set_bsdf(bsdf, "Roughness", 0.60)
    for name_ in ("Specular", "Specular IOR Level"):
        set_bsdf(bsdf, name_, 0.20)

    return mat

def make_inner_material(name):
    """Slightly lighter inner surface."""
    return make_cardboard_material(name, base_color=(0.88, 0.85, 0.80, 1.0))


# ============================================================
# GEOMETRY
# ============================================================

def create_box_mesh(name, w_m, d_m, h_m):
    ensure_object_mode()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (w_m, d_m, h_m)
    bpy.ops.object.transform_apply(scale=True)
    return obj

def delete_face(obj, direction: Vector, threshold=0.98):
    """Remove the face whose normal best matches direction (local space)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    best, best_dot = None, -1.0
    for f in bm.faces:
        d = f.normal.dot(direction)
        if d > best_dot:
            best_dot, best = d, f

    if best and best_dot >= threshold:
        bmesh.ops.delete(bm, geom=[best], context='FACES')
    else:
        print(f"[WARN] Opening face not found on {obj.name} (dot={best_dot:.3f})")

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

def add_solidify(obj, thickness_m):
    mod = obj.modifiers.new("Solidify", 'SOLIDIFY')
    mod.thickness = thickness_m
    mod.offset = -1.0           # inward — keeps outer dimensions exact
    if hasattr(mod, "use_even_offset"):   mod.use_even_offset = True
    if hasattr(mod, "use_rim"):           mod.use_rim = True
    if hasattr(mod, "material_offset"):   mod.material_offset = 1
    return mod

def add_bevel(obj, radius_m, segments):
    mod = obj.modifiers.new("Bevel", 'BEVEL')
    mod.width        = radius_m
    mod.segments     = max(1, segments)
    mod.profile      = 0.7
    mod.limit_method = 'ANGLE'
    mod.angle_limit  = math.radians(35.0)
    return mod

def add_weighted_normal(obj):
    mod = obj.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')
    if hasattr(mod, "keep_sharp"):
        mod.keep_sharp = True
    return mod

def shade_smooth(obj):
    ensure_object_mode()
    deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    angle = math.radians(45.0)
    try:
        bpy.ops.object.shade_auto_smooth(angle=angle)
    except Exception:
        me = obj.data
        if hasattr(me, "use_auto_smooth"):
            me.use_auto_smooth = True
            me.auto_smooth_angle = angle

def build_open_box(name, dims_mm, open_top, mat_outer, mat_inner):
    """
    Create one half of the box (lid or bottom).
    open_top=True  → lid (opens downward, sits over bottom)
    open_top=False → bottom (opens upward)
    """
    w, d, h = dims_mm
    obj = create_box_mesh(name, mm(w), mm(d), mm(h))

    direction = Vector((0, 0, -1)) if open_top else Vector((0, 0, 1))
    delete_face(obj, direction)

    obj.data.materials.clear()
    obj.data.materials.append(mat_outer)   # slot 0 → outer faces
    obj.data.materials.append(mat_inner)   # slot 1 → inner faces (via Solidify)

    add_solidify(obj, mm(WALL_THICKNESS))
    add_bevel(obj, mm(BEVEL_RADIUS), BEVEL_SEGMENTS)
    add_weighted_normal(obj)
    shade_smooth(obj)

    return obj


# ============================================================
# LID LIP (inner alignment skirt)
# ============================================================

def build_lip(lid_obj, lid_dims_mm, bot_dims_mm, mat_inner):
    lw, ld, lh = lid_dims_mm
    bw, bd, _  = bot_dims_mm

    bot_inner_w = bw - 2 * WALL_THICKNESS
    bot_inner_d = bd - 2 * WALL_THICKNESS

    lip_outer_w = min(lw - 2 * WALL_THICKNESS - 2 * LIP_INSET, bot_inner_w - 2 * CLEARANCE_GAP)
    lip_outer_d = min(ld - 2 * WALL_THICKNESS - 2 * LIP_INSET, bot_inner_d - 2 * CLEARANCE_GAP)

    if lip_outer_w < 2 or lip_outer_d < 2:
        print("[WARN] Lip too small — skipping.")
        return None

    thick = min(LIP_THICKNESS, lip_outer_w * 0.4, lip_outer_d * 0.4)

    obj = create_box_mesh("BOX_LIP", mm(lip_outer_w), mm(lip_outer_d), mm(LIP_HEIGHT))
    delete_face(obj, Vector((0, 0,  1)))
    delete_face(obj, Vector((0, 0, -1)))

    obj.data.materials.clear()
    obj.data.materials.append(mat_inner)

    add_solidify(obj, mm(thick))
    add_bevel(obj, mm(min(0.5, BEVEL_RADIUS * 0.7)), max(1, BEVEL_SEGMENTS - 1))
    add_weighted_normal(obj)
    shade_smooth(obj)

    obj.parent = lid_obj
    obj.location.z = mm(-lh / 2.0 + CLEARANCE_GAP + LIP_HEIGHT / 2.0)
    return obj


# ============================================================
# PLACEMENT  —  uses evaluated bounds (modifiers applied)
# ============================================================

def world_bounds(obj):
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj  = obj.evaluated_get(depsgraph)
    mesh      = eval_obj.to_mesh()
    coords    = [eval_obj.matrix_world @ v.co for v in mesh.vertices]
    eval_obj.to_mesh_clear()
    if not coords:
        return None
    lo = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
    hi = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
    return lo, hi

def place_on_floor(obj, z=0.0):
    b = world_bounds(obj)
    if b:
        obj.location.z += z - b[0].z
        bpy.context.view_layer.update()

def fit_lid_over_bottom(lid, bot):
    bb = world_bounds(bot)
    bl = world_bounds(lid)
    if not bb or not bl:
        return

    # Center XY
    c_bot = (bb[0] + bb[1]) * 0.5
    c_lid = (bl[0] + bl[1]) * 0.5
    lid.location.x += c_bot.x - c_lid.x
    lid.location.y += c_bot.y - c_lid.y
    bpy.context.view_layer.update()

    # Z: overlap
    bot_top  = world_bounds(bot)[1].z
    lid_base = world_bounds(lid)[0].z
    target_z = bot_top - mm(OVERLAP_DEPTH) + mm(CLEARANCE_GAP)
    lid.location.z += target_z - lid_base
    bpy.context.view_layer.update()


# ============================================================
# SCENE SETUP  —  lights + camera, no HDRI needed
# ============================================================

def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.render.film_transparent = True

    if hasattr(scene, "cycles"):
        scene.cycles.samples = 128
        if hasattr(scene.cycles, "use_adaptive_sampling"):
            scene.cycles.use_adaptive_sampling = True

    # Neutral grey world background
    world = scene.world or bpy.data.worlds.new("WORLD")
    scene.world = world
    world.use_nodes = True
    wn = world.node_tree.nodes
    wn.clear()
    out = wn.new("ShaderNodeOutputWorld"); out.location = (300, 0)
    bg  = wn.new("ShaderNodeBackground");  bg.location  = (0, 0)
    bg.inputs["Color"].default_value    = (0.90, 0.90, 0.90, 1.0)
    bg.inputs["Strength"].default_value = 0.8
    world.node_tree.links.new(bg.outputs["Background"], out.inputs["Surface"])

    # Shadow-catcher floor
    delete_if_exists("SCENE_FLOOR")
    bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "SCENE_FLOOR"
    try:
        floor.cycles.is_shadow_catcher = True
    except Exception:
        pass

    # Three area lights: key, fill, rim
    def area_light(name, loc, rot_deg, power, size):
        delete_if_exists(name)
        data = bpy.data.lights.new(name, 'AREA')
        obj  = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        obj.location      = loc
        obj.rotation_euler = tuple(math.radians(r) for r in rot_deg)
        data.energy = power * LIGHT_POWER_MULT
        data.size   = size
        return obj

    area_light("LIGHT_KEY",  ( 0.65, -0.55, 0.75), (65,  0,  25), 900, 0.8)
    area_light("LIGHT_FILL", (-0.75, -0.35, 0.55), (75,  0, -25), 450, 1.2)
    area_light("LIGHT_RIM",  ( 0.00,  0.95, 0.85), (110, 0,   0), 300, 1.0)

    # Camera
    delete_if_exists("SCENE_CAM")
    cam_data = bpy.data.cameras.new("SCENE_CAM")
    cam      = bpy.data.objects.new("SCENE_CAM", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location      = (0.45, -0.95, 0.55)
    cam.rotation_euler = (math.radians(68), 0, math.radians(20))
    cam_data.lens = 55
    scene.camera = cam


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_object_mode()

    # Clean up previous run
    for name in ["BOX_LID", "BOX_BOTTOM", "BOX_LIP", "BOX_CTRL",
                 "SCENE_FLOOR", "SCENE_CAM",
                 "LIGHT_KEY", "LIGHT_FILL", "LIGHT_RIM"]:
        delete_if_exists(name)

    setup_scene()

    # Materials
    mat_outer = make_cardboard_material("MAT_OUTER", base_color=(0.72, 0.65, 0.55, 1.0))
    mat_inner = make_inner_material("MAT_INNER")

    # Geometry
    lid = build_open_box("BOX_LID",    LID_OUTER,    open_top=True,  mat_outer=mat_outer, mat_inner=mat_inner)
    bot = build_open_box("BOX_BOTTOM", BOTTOM_OUTER, open_top=False, mat_outer=mat_outer, mat_inner=mat_inner)

    # Position
    place_on_floor(bot)
    fit_lid_over_bottom(lid, bot)

    # Open pose
    if DISPLAY_MODE.upper() == "OPEN":
        lid.location.y    += mm(BOTTOM_OUTER[1] * 0.6 + OPEN_OFFSET_MM)
        lid.rotation_euler.x = math.radians(OPEN_ANGLE_DEG)

    # Lip
    lip = build_lip(lid, LID_OUTER, BOTTOM_OUTER, mat_inner) if ADD_LIP else None

    # Group under empty
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    ctrl = bpy.context.active_object
    ctrl.name = "BOX_CTRL"

    for obj in [lid, bot] + ([lip] if lip else []):
        obj.matrix_parent_inverse = ctrl.matrix_world.inverted()
        obj.parent = ctrl

    print("[DONE] Box created:", [o.name for o in [ctrl, lid, bot] if o])
    print(f"       Lip: {lip.name if lip else 'none'}")


main()