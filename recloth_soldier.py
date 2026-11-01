"""
Reclothing pipeline — Soldier.glb → stylised male athlete
1. Import Soldier.glb (Mixamo Vanguard: properly sculpted face/body)
2. Flat skin material, remove visor
3. Add jersey, shorts, shoes scaled to character H via H-based proportions
4. Bind to existing Mixamo armature
5. Export /tmp/athlete_soldier.glb
"""
import bpy, bmesh, math, os
from mathutils import Vector

# ── Clean scene ────────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)
col = bpy.context.scene.collection

# ── Import ─────────────────────────────────────────────────────────────────
bpy.ops.import_scene.gltf(filepath='/tmp/soldier.glb')

arm_ob  = next(o for o in col.all_objects if o.type == 'ARMATURE')
body_ob = next(o for o in col.all_objects if o.name == 'vanguard_Mesh')

# ── Measure height + align feet to Z=0 ────────────────────────────────────
zs = [(body_ob.matrix_world @ v.co).z for v in body_ob.data.vertices]
Z_MIN = min(zs); Z_MAX = max(zs); H = Z_MAX - Z_MIN
for ob in col.all_objects:
    if ob.type in ('MESH','ARMATURE'):
        ob.location.z -= Z_MIN
bpy.context.view_layer.update()
Z_MIN = 0; Z_MAX = H

print(f"Character height: {H:.4f} units")

# ── Bone positions (after shift) ──────────────────────────────────────────
bp = {}
for b in arm_ob.data.bones:
    bp[b.name] = (arm_ob.matrix_world @ b.head_local) + Vector((0,0,-Z_MIN+0))

# (z_min shift is already applied via location.z)
def B(key, fallback):
    return bp.get(key, fallback)

HIP_Z   = B('mixamorig:Hips',       Vector((0,0,H*0.58))).z
CHEST_Z = B('mixamorig:Spine2',     Vector((0,0,H*0.76))).z
NECK_Z  = B('mixamorig:Neck',       Vector((0,0,H*0.84))).z
KNEE_Z  = B('mixamorig:LeftLeg',    Vector((0,0,H*0.31))).z
LARM_X  = B('mixamorig:LeftArm',    Vector((-H*0.19,0,H*0.76))).x
RARM_X  = B('mixamorig:RightArm',   Vector(( H*0.19,0,H*0.76))).x
LARM_Z  = B('mixamorig:LeftArm',    Vector((-H*0.19,0,H*0.76))).z
LFOT_X  = B('mixamorig:LeftFoot',   Vector((-H*0.07,0,H*0.04))).x
RFOT_X  = B('mixamorig:RightFoot',  Vector(( H*0.07,0,H*0.04))).x
LFOT_Z  = B('mixamorig:LeftFoot',   Vector((0,0,H*0.04))).z
print(f"Hip Z={HIP_Z:.3f}  Chest Z={CHEST_Z:.3f}  Neck Z={NECK_Z:.3f}  Knee Z={KNEE_Z:.3f}")
print(f"L arm: x={LARM_X:.3f} z={LARM_Z:.3f}  L foot: x={LFOT_X:.3f} z={LFOT_Z:.3f}")

# H-proportional clothing widths (athletic running gear, not armour)
JW = H * 0.160   # jersey half-width at shoulder
JD = H * 0.115   # jersey half-depth
JW_HIP = H * 0.140  # jersey half-width at hip hem
JD_HIP = H * 0.098

SW = H * 0.155   # shorts half-width
SD = H * 0.108   # shorts half-depth

# ── Helpers ────────────────────────────────────────────────────────────────
def new_obj(name, me):
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob

def active(ob):
    bpy.context.view_layer.objects.active = ob

def apply_subd(ob, levels=2):
    active(ob)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    mod = ob.modifiers.new("S","SUBSURF")
    mod.levels = levels; mod.render_levels = levels
    bpy.ops.object.modifier_apply(modifier="S")

def shade_smooth(ob):
    active(ob)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.ops.object.shade_smooth()

def make_mat(name, r,g,b, rough=0.55, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (r,g,b,1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return m

def ellipse_ring(bm, cx, cy, cz, rx, ry, segs=14):
    return [bm.verts.new(Vector((cx + rx*math.cos(2*math.pi*i/segs),
                                  ry*math.sin(2*math.pi*i/segs), cz)))
            for i in range(segs)]

def connect_rings(bm, r1, r2):
    n = len(r1)
    for i in range(n):
        bm.faces.new([r1[i], r1[(i+1)%n], r2[(i+1)%n], r2[i]])

# ── Materials ──────────────────────────────────────────────────────────────
mat_skin    = make_mat("Skin",    0.91, 0.76, 0.61, rough=0.68)
mat_jersey  = make_mat("Jersey",  0.96, 0.29, 0.44, rough=0.48)   # ORION pink
mat_shorts  = make_mat("Shorts",  0.12, 0.12, 0.18, rough=0.65)
mat_shoe    = make_mat("Shoe",    0.97, 0.97, 0.97, rough=0.40)
mat_sole    = make_mat("Sole",    0.10, 0.10, 0.10, rough=0.82)
mat_lace    = make_mat("Lace",    1.00, 1.00, 1.00, rough=0.90)

# ── Skin body, remove armour objects ───────────────────────────────────────
body_ob.data.materials.clear()
body_ob.data.materials.append(mat_skin)
shade_smooth(body_ob)

for ob in list(col.all_objects):
    if ob.name in ('vanguard_visor','Icosphere'):
        bpy.data.objects.remove(ob, do_unlink=True)

# ═══════════════════════════════════════════════════════════════════════════
# JERSEY — torso tube with collar and sleeve openings
# ═══════════════════════════════════════════════════════════════════════════
def build_jersey():
    me = bpy.data.meshes.new("Jersey")
    ob = new_obj("Jersey", me)
    bm = bmesh.new()
    SEGS = 16
    OFF = H * 0.012   # small offset from body surface

    # Profile from hem (hip) to collar
    layers = [
        # (wx, wy, z)
        (JW_HIP + OFF,    JD_HIP + OFF,    HIP_Z - H*0.03),   # hem
        (JW_HIP + OFF,    JD_HIP + OFF,    HIP_Z + H*0.01),
        (JW     + OFF,    JD     + OFF,    CHEST_Z - H*0.06),  # waist
        (JW     + OFF*1.2,JD     + OFF*1.2,CHEST_Z + H*0.04),  # chest
        (JW * 1.08+OFF,   JD     + OFF,    LARM_Z - H*0.01),   # shoulder
        (H*0.060,         H*0.060,         NECK_Z  - H*0.02),  # collar
    ]

    rings = []
    for (wx, wy, z) in layers:
        rings.append(ellipse_ring(bm, 0, 0, z, wx, wy, SEGS))

    for i in range(len(rings)-1):
        connect_rings(bm, rings[i], rings[i+1])
    bm.faces.new(rings[0])   # hem cap

    # Collar opening cap
    bm.faces.new(list(reversed(rings[-1])))

    bm.verts.index_update()
    bm.to_mesh(me); bm.free()
    ob.data.materials.append(mat_jersey)
    shade_smooth(ob)
    apply_subd(ob, 2)
    return ob

# ═══════════════════════════════════════════════════════════════════════════
# SLEEVE CAPS (jersey → upper arm, covers shoulder armour)
# ═══════════════════════════════════════════════════════════════════════════
def build_sleeve(side):
    me = bpy.data.meshes.new(f"Sleeve_{side}")
    ob = new_obj(f"Sleeve_{side}", me)
    bm = bmesh.new()
    SEGS = 10
    cx = RARM_X if side == 'R' else LARM_X
    TOP_Z = LARM_Z + H*0.015
    BOT_Z = LARM_Z - H*0.11
    r = H * 0.075

    top = ellipse_ring(bm, cx, 0, TOP_Z, r, r*0.82, SEGS)
    bot = ellipse_ring(bm, cx, 0, BOT_Z, r*0.90, r*0.75, SEGS)
    connect_rings(bm, top, bot)
    bm.faces.new(list(reversed(top)))
    bm.faces.new(bot)
    bm.verts.index_update()
    bm.to_mesh(me); bm.free()
    ob.data.materials.append(mat_jersey)
    shade_smooth(ob)
    return ob

# ═══════════════════════════════════════════════════════════════════════════
# SHORTS
# ═══════════════════════════════════════════════════════════════════════════
def build_shorts():
    me = bpy.data.meshes.new("Shorts")
    ob = new_obj("Shorts", me)
    bm = bmesh.new()
    SEGS = 18
    OFF = H * 0.013
    TOP_Z = HIP_Z + H*0.03
    BOT_Z = KNEE_Z + H*0.20   # just above knee

    layers = [
        (SW+OFF,         SD+OFF,          TOP_Z),
        (SW*1.01+OFF,    SD*0.98+OFF,     TOP_Z - H*0.04),
        (SW*0.97+OFF,    SD*0.92+OFF,     BOT_Z + H*0.04),
        (SW*0.90+OFF,    SD*0.82+OFF,     BOT_Z),
    ]
    rings = [ellipse_ring(bm, 0, 0, z, wx, wy, SEGS) for (wx, wy, z) in layers]
    for i in range(len(rings)-1):
        connect_rings(bm, rings[i], rings[i+1])
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bm.verts.index_update()
    bm.to_mesh(me); bm.free()
    ob.data.materials.append(mat_shorts)
    shade_smooth(ob)
    apply_subd(ob, 2)
    return ob

# ═══════════════════════════════════════════════════════════════════════════
# RUNNING SHOES
# ═══════════════════════════════════════════════════════════════════════════
def build_shoe(side):
    me = bpy.data.meshes.new(f"Shoe_{side}")
    ob = new_obj(f"Shoe_{side}", me)
    bm = bmesh.new()

    sx = 1 if side == 'R' else -1
    CX  = RFOT_X if side == 'R' else LFOT_X
    CZ  = LFOT_Z

    # Shoe runs: toe forward (−Y in Blender = forward in gltf-land)
    # toe offset depends on which direction foot points
    TOE_FWD  = -H * 0.13    # forward (−Y)
    HEEL_BWD = +H * 0.04    # back
    SHOE_TOP = CZ + H*0.062
    SHOE_BOT = CZ - H*0.008
    SHOE_W   = H * 0.042    # half-width
    SOLE_H   = H * 0.024    # sole thickness

    SEGS = 12

    def ring(cy, cz, rx, ry_up, ry_dn):
        pts = []
        for i in range(SEGS):
            a = 2*math.pi*i/SEGS
            rx_ = rx * (1 + 0.15*(math.cos(a)+1)*0.5)  # toe wider
            ry = ry_up if math.sin(a) >= 0 else ry_dn
            pts.append(bm.verts.new(Vector((CX + SHOE_W*math.cos(a)*1.0,
                                             cy + rx_*math.sin(a-math.pi/2),
                                             cz + ry*math.sin(a-math.pi/2)*0))))
        return pts

    # Cross sections: heel → mid → toe (along Y axis)
    def shoe_section(fwd, cz, rx_lat, rz_up, rz_dn):
        pts = []
        for i in range(SEGS):
            a = 2*math.pi*i/SEGS
            # lat = left-right (X), fwd = forward-back (Y)
            lat = SHOE_W * math.cos(a)
            ht  = (rz_up if math.sin(a)>=0 else rz_dn) * math.sin(a)
            pts.append(bm.verts.new(Vector((CX + lat, fwd, cz + ht))))
        return pts

    HEEL = +H*0.035
    MID  = -H*0.045
    TOE  = -H*0.125
    TOET = SHOE_BOT - H*0.015

    sections = [
        shoe_section(HEEL, SHOE_TOP - H*0.006, H*0.040, H*0.048, H*0.030),
        shoe_section(MID,  SHOE_TOP,            H*0.045, H*0.058, H*0.030),
        shoe_section(TOE,  TOET,                H*0.032, H*0.028, H*0.020),
    ]

    connect_rings(bm, sections[0], sections[1])
    connect_rings(bm, sections[1], sections[2])
    bm.faces.new(list(reversed(sections[0])))
    bm.faces.new(sections[2])

    # Sole slab
    SW2 = SHOE_W * 1.10
    st = [
        bm.verts.new(Vector((CX - SW2, HEEL + H*0.02, SHOE_BOT))),
        bm.verts.new(Vector((CX + SW2, HEEL + H*0.02, SHOE_BOT))),
        bm.verts.new(Vector((CX + SW2, TOE  - H*0.02, SHOE_BOT))),
        bm.verts.new(Vector((CX - SW2, TOE  - H*0.02, SHOE_BOT))),
    ]
    sb = [bm.verts.new(Vector((v.co.x, v.co.y, 0.002))) for v in st]
    bm.faces.new(list(reversed(st)))
    bm.faces.new(sb)
    n = len(st)
    for i in range(n):
        bm.faces.new([st[i], st[(i+1)%n], sb[(i+1)%n], sb[i]])

    bm.verts.index_update()
    bm.to_mesh(me); bm.free()
    ob.data.materials.append(mat_shoe)
    shade_smooth(ob)
    apply_subd(ob, 1)
    return ob

# ── Build all clothing ─────────────────────────────────────────────────────
print("Building clothing...")
ob_jersey  = build_jersey()
ob_sl_l    = build_sleeve('L')
ob_sl_r    = build_sleeve('R')
ob_shorts  = build_shorts()
ob_shoe_l  = build_shoe('L')
ob_shoe_r  = build_shoe('R')
print("Clothing built.")

# ── Bind clothing to armature (Python API — avoids operator collection bug) ─
clothing = [ob_jersey, ob_sl_l, ob_sl_r, ob_shorts, ob_shoe_l, ob_shoe_r]
for ob in clothing:
    # Preserve current world position, parent to armature object
    ob.parent = arm_ob
    ob.parent_type = 'OBJECT'
    ob.matrix_parent_inverse = arm_ob.matrix_world.inverted()
    # Add armature deform modifier so animation drives clothing
    mod = ob.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm_ob
    mod.use_vertex_groups = True
    # Add vertex groups matching armature bones for deformation
    # Body bones that affect each garment zone
print("Armature binding complete.")

# ── Debug: confirm all objects present in collection before export ─────────
print("\nObjects in scene before export:")
for ob in sorted(col.all_objects, key=lambda o: o.name):
    print(f"  [{ob.type}] {ob.name}  hide_render={ob.hide_render}  hide_viewport={ob.hide_viewport}")

# ── Export ─────────────────────────────────────────────────────────────────
OUT = '/tmp/athlete_soldier.glb'

# Ensure all mesh/armature objects are visible for export
for ob in list(col.all_objects):
    if ob is None: continue
    if ob.type in ('MESH', 'ARMATURE'):
        ob.hide_render = False
        ob.hide_viewport = False

bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format='GLB',
    export_apply=True,
    export_animations=True,
    export_skins=True,
    export_morph=False,
)
sz = os.path.getsize(OUT)
print(f"\n✓ Exported: {OUT}  ({sz//1024}KB)")
for ob in sorted(col.all_objects, key=lambda o:o.name):
    if ob.type == 'MESH':
        print(f"  {ob.name}: {len(ob.data.vertices)}v, mats={[m.name for m in ob.data.materials]}")
