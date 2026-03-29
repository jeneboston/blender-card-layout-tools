import bpy
import bmesh
import os
import re
import math

# ============================================================
# Card Importer for Blender 3.x / 4.x
#
# Creates 3D playing cards from a folder of front/back images.
# Each card is a rounded-rectangle prism with:
#   - Front face  (Questions image or procedural grey)
#   - Back face   (Answers image or procedural grey)
#   - Edge        (white or cardboard-textured)
#
# Supported filename format:
#   0307 Questions.jpg  /  0307_Questions.png
#   0307 Answers.jpg    /  0307_Answers.png
#
# OUTPUT_MODE:
#   "SINGLE"  — 1 object per card (front=Questions, back=Answers)
#   "DOUBLE"  — 2 objects per card (one per side, both faces same image)
#
# If CARD_FOLDER is empty or images are missing, procedural
# placeholder materials are used so the script always runs.
#
# Run from Blender's Script Editor.
# ============================================================


# ============================================================
# SETTINGS  —  edit here
# ============================================================

# Folder with card images.
# Leave empty ("") to generate placeholder cards without textures.
CARD_FOLDER = ""   # e.g. r"C:\my_project\cards"

# Which card numbers to import.
# CARD_NUMBERS — explicit list, e.g. [1, 2, 3]
# CARD_RANGE   — inclusive range, e.g. (1, 10)
# Both empty   — import everything found in the folder
CARD_NUMBERS = []
CARD_RANGE   = None    # e.g. (1, 5)

# How many placeholder cards to create when no folder is set
PLACEHOLDER_COUNT = 6

# Card dimensions
CARD_WIDTH_CM  = 7.0    # cm
CARD_HEIGHT_CM = 10.0   # cm
THICKNESS_MM   = 0.5    # mm

# Rounded corners
CORNER_RADIUS_MM = 3.0
ARC_SEGMENTS     = 10   # 8–16 — corner smoothness

# Keywords to identify front/back images
FRONT_KEYWORD = "Questions"   # front face
BACK_KEYWORD  = "Answers"     # back face

# Edge style: "WHITE" or "CARDBOARD"
EDGE_STYLE = "WHITE"

# Output mode: "SINGLE" or "DOUBLE"
OUTPUT_MODE = "SINGLE"

# Auto-spacing when placing cards in the scene
AUTO_SPACING  = True
SPACING_X     = 1.35   # multiplier of card width
SPACING_Y     = 1.50   # multiplier of card height (DOUBLE mode offset)

# Collection name
COLLECTION_NAME = "CARDS"
CLEAR_OLD_CARDS = True


# ============================================================
# FILE SCANNING
# ============================================================

FILE_RE = re.compile(
    r"^(?P<num>\d{1,5})\s*[_\- ]\s*(?P<rest>.+?)\.(?P<ext>jpg|jpeg|png)$",
    re.IGNORECASE
)

def scan_folder(folder):
    """
    Returns dict:  card_number (int) -> {"front": path, "back": path}
    Accepts filenames like:  0307 Questions.jpg  /  0307_Answers.png
    """
    result = {}
    if not folder or not os.path.isdir(folder):
        return result

    for fn in os.listdir(folder):
        m = FILE_RE.match(fn)
        if not m:
            continue
        num  = int(m.group("num"))
        rest = m.group("rest").lower()
        path = os.path.join(folder, fn)

        if FRONT_KEYWORD.lower() in rest:
            result.setdefault(num, {})["front"] = path
        elif BACK_KEYWORD.lower() in rest:
            result.setdefault(num, {})["back"] = path

    return result

def resolve_numbers(mapping):
    """Return sorted list of card numbers to process."""
    if CARD_NUMBERS:
        return sorted(int(n) for n in CARD_NUMBERS)
    if CARD_RANGE:
        a, b = CARD_RANGE
        return list(range(int(a), int(b) + 1))
    if mapping:
        return sorted(mapping.keys())
    return list(range(1, PLACEHOLDER_COUNT + 1))


# ============================================================
# MATERIALS
# ============================================================

def _new_bsdf_mat(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (0, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    # Matte — no specular highlights
    for sock in ("Specular", "Specular IOR Level", "Clearcoat"):
        if sock in bsdf.inputs:
            bsdf.inputs[sock].default_value = 0.0
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 1.0
    return mat, bsdf, nt

def make_placeholder_material(name, color=(0.80, 0.80, 0.80, 1.0)):
    """Flat grey — used when no image file is available."""
    mat, bsdf, _ = _new_bsdf_mat(name)
    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = color
    return mat

def make_image_material(name, image_path):
    """Loads an image file and connects it to Principled BSDF Base Color."""
    mat, bsdf, nt = _new_bsdf_mat(name)

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-280, 0)

    if os.path.exists(image_path):
        img = bpy.data.images.load(image_path, check_existing=True)
        try:
            img.colorspace_settings.name = "sRGB"
        except Exception:
            pass
        tex.image = img
    else:
        print(f"[WARN] Image not found: {image_path}")

    if "Base Color" in bsdf.inputs:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    return mat

def make_edge_material(name):
    """
    White matte edge (EDGE_STYLE='WHITE') or
    cardboard with subtle noise bump (EDGE_STYLE='CARDBOARD').
    """
    mat, bsdf, nt = _new_bsdf_mat(name)

    if EDGE_STYLE.upper() == "CARDBOARD":
        color = (0.72, 0.62, 0.50, 1.0)
        noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-480, -120)
        bump  = nt.nodes.new("ShaderNodeBump");     bump.location  = (-240, -120)
        if "Scale"    in noise.inputs: noise.inputs["Scale"].default_value    = 240.0
        if "Detail"   in noise.inputs: noise.inputs["Detail"].default_value   = 2.0
        if "Strength" in bump.inputs:  bump.inputs["Strength"].default_value  = 0.06
        nt.links.new(noise.outputs["Fac"],    bump.inputs["Height"])
        if "Normal" in bsdf.inputs:
            nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        color = (1.0, 1.0, 1.0, 1.0)

    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = color

    return mat

def get_face_material(name, image_path):
    """Returns image material if path exists, otherwise placeholder."""
    if image_path and os.path.exists(image_path):
        return make_image_material(name, image_path)
    return make_placeholder_material(name)


# ============================================================
# CARD GEOMETRY
# ============================================================

def rounded_rect_verts(width_m, height_m, radius_m, segments):
    """Returns list of (x, y) points tracing a rounded rectangle."""
    r  = min(radius_m, width_m * 0.49, height_m * 0.49)
    cx = width_m  * 0.5 - r
    cy = height_m * 0.5 - r

    pts = []
    corners = [
        ( cx,  cy,          0.0,              math.pi * 0.5),
        (-cx,  cy,          math.pi * 0.5,    math.pi),
        (-cx, -cy,          math.pi,          math.pi * 1.5),
        ( cx, -cy,          math.pi * 1.5,    math.pi * 2.0),
    ]
    for (ox, oy, a0, a1) in corners:
        for i in range(segments + 1):
            t = i / segments
            a = a0 + (a1 - a0) * t
            pts.append((ox + math.cos(a) * r, oy + math.sin(a) * r))

    # remove duplicate closing point
    if len(pts) > 1:
        pts.pop()
    return pts

def build_card_mesh(name, width_m, height_m, thickness_m, radius_m, arc_segments):
    """
    Builds a rounded-rectangle prism.
    Origin at center. +Z = front face, -Z = back face.

    Material slots:
      0 → front (top)
      1 → back  (bottom)
      2 → edge  (sides)
    """
    bm = bmesh.new()

    pts   = rounded_rect_verts(width_m, height_m, radius_m, arc_segments)
    verts = [bm.verts.new((x, y, 0.0)) for (x, y) in pts]
    face  = bm.faces.new(verts)
    bmesh.ops.recalc_face_normals(bm, faces=[face])

    # Extrude to thickness, then center on Z
    res     = bmesh.ops.extrude_face_region(bm, geom=[face])
    top_v   = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top_v, vec=(0.0, 0.0, thickness_m))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, -thickness_m * 0.5))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # UV map: flat projection from Z for top/bottom, pass-through for edges
    uv = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")

    z_top = thickness_m * 0.5
    z_bot = -thickness_m * 0.5
    eps   = thickness_m * 0.02 + 1e-6

    for f in bm.faces:
        zs   = [v.co.z for v in f.verts]
        zmin = min(zs)
        zmax = max(zs)
        is_top = abs(zmax - z_top) <= eps and abs(zmin - z_top) <= eps
        is_bot = abs(zmax - z_bot) <= eps and abs(zmin - z_bot) <= eps

        for loop in f.loops:
            x, y = loop.vert.co.x, loop.vert.co.y
            u = x / width_m + 0.5
            v = y / height_m + 0.5
            if is_bot:
                u = 1.0 - u   # flip so text reads correctly when card is turned over
            loop[uv].uv = (u, v)

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh

def assign_material_slots(mesh, thickness_m):
    """Tag each polygon: 0=front, 1=back, 2=edge."""
    z_top = thickness_m * 0.5
    z_bot = -thickness_m * 0.5
    eps   = thickness_m * 0.02 + 1e-6
    verts = mesh.vertices

    for poly in mesh.polygons:
        zs   = [verts[i].co.z for i in poly.vertices]
        zmin = min(zs)
        zmax = max(zs)
        if abs(zmax - z_top) <= eps and abs(zmin - z_top) <= eps:
            poly.material_index = 0
        elif abs(zmax - z_bot) <= eps and abs(zmin - z_bot) <= eps:
            poly.material_index = 1
        else:
            poly.material_index = 2
    mesh.update()


# ============================================================
# SCENE HELPERS
# ============================================================

def ensure_collection(name):
    coll = bpy.data.collections.get(name)
    if not coll:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll

def clear_collection(coll):
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

def add_to_collection(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)

def make_card_object(obj_name, mesh, mat_front, mat_back, mat_edge, thickness_m, coll):
    obj = bpy.data.objects.new(obj_name, mesh)
    obj.data.materials.clear()
    obj.data.materials.append(mat_front)
    obj.data.materials.append(mat_back)
    obj.data.materials.append(mat_edge)
    assign_material_slots(obj.data, thickness_m)
    add_to_collection(obj, coll)
    return obj


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    mapping = scan_folder(CARD_FOLDER)
    numbers = resolve_numbers(mapping)

    coll = ensure_collection(COLLECTION_NAME)
    if CLEAR_OLD_CARDS:
        clear_collection(coll)

    w_m = CARD_WIDTH_CM  / 100.0
    h_m = CARD_HEIGHT_CM / 100.0
    t_m = THICKNESS_MM   / 1000.0
    r_m = CORNER_RADIUS_MM / 1000.0

    edge_mat = make_edge_material("MAT_EDGE")

    x_step = w_m * SPACING_X
    y_step = h_m * SPACING_Y

    created = 0

    for idx, num in enumerate(numbers):
        entry         = mapping.get(num, {})
        front_path    = entry.get("front", "")
        back_path     = entry.get("back",  "")

        mat_front = get_face_material(f"MAT_{num:04d}_FRONT", front_path)
        mat_back  = get_face_material(f"MAT_{num:04d}_BACK",  back_path)

        base_x = idx * x_step if AUTO_SPACING else 0.0

        if OUTPUT_MODE == "DOUBLE":
            # Front-only card
            mesh_f = build_card_mesh(f"MESH_{num:04d}_F", w_m, h_m, t_m, r_m, ARC_SEGMENTS)
            obj_f  = make_card_object(f"CARD_{num:04d}_F", mesh_f,
                                      mat_front, mat_front, edge_mat, t_m, coll)
            if AUTO_SPACING:
                obj_f.location = (base_x, 0.0, t_m * 0.5)

            # Back-only card
            mesh_b = build_card_mesh(f"MESH_{num:04d}_B", w_m, h_m, t_m, r_m, ARC_SEGMENTS)
            obj_b  = make_card_object(f"CARD_{num:04d}_B", mesh_b,
                                      mat_back, mat_back, edge_mat, t_m, coll)
            if AUTO_SPACING:
                obj_b.location = (base_x, y_step, t_m * 0.5)

            created += 2

        else:  # SINGLE
            mesh = build_card_mesh(f"MESH_{num:04d}", w_m, h_m, t_m, r_m, ARC_SEGMENTS)
            obj  = make_card_object(f"CARD_{num:04d}", mesh,
                                    mat_front, mat_back, edge_mat, t_m, coll)
            if AUTO_SPACING:
                obj.location = (base_x, 0.0, t_m * 0.5)

            created += 1

    mode = "with images" if mapping else "placeholder (no folder set)"
    print(f"[Card Importer] Done — {created} objects created ({mode})")
    if not CARD_FOLDER:
        print("  Tip: set CARD_FOLDER to a folder with your card images.")


main()