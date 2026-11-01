"""
Stylised athletic male character generator — bpy 5.2
Approach: bmesh box-modelling + SubDiv → connected organic surfaces (no visible seams)
Output: /tmp/athlete_male.glb
"""
import bpy, bmesh, math, os
from mathutils import Vector, Matrix

# ── 0. Clean scene ─────────────────────────────────────────────────────────
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col = scene.collection

# ── Helpers ────────────────────────────────────────────────────────────────

def new_obj(name, me):
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob

def active(ob):
    bpy.context.view_layer.objects.active = ob
    return ob

def apply_subd(ob, levels=2):
    active(ob)
    mod = ob.modifiers.new("S", "SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    bpy.ops.object.modifier_apply(modifier="S")

def assign_mat(ob, mat):
    if not ob.data.materials:
        ob.data.materials.append(mat)
    else:
        ob.data.materials[0] = mat

def make_mat(name, r, g, b, roughness=0.55, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return m

# ── Materials ──────────────────────────────────────────────────────────────
mat_skin   = make_mat("skin",   0.91, 0.77, 0.60, roughness=0.7)
mat_jersey = make_mat("jersey", 0.96, 0.28, 0.43, roughness=0.5)  # ORION pink
mat_shorts = make_mat("shorts", 0.16, 0.16, 0.22, roughness=0.6)
mat_shoes  = make_mat("shoes",  0.95, 0.95, 0.95, roughness=0.4)
mat_sole   = make_mat("sole",   0.15, 0.15, 0.15, roughness=0.8)
mat_hair   = make_mat("hair",   0.16, 0.09, 0.03, roughness=0.8)
mat_eye_w  = make_mat("eye_white", 0.95, 0.95, 0.95, roughness=0.2)
mat_iris   = make_mat("iris",   0.22, 0.14, 0.07, roughness=0.3)
mat_pupil  = make_mat("pupil",  0.02, 0.02, 0.02, roughness=0.1)

# ═══════════════════════════════════════════════════════════════════════════
# BODY MESH — built from a single box-modelled mesh so all joints merge
# We create a T-pose humanoid using bmesh operations:
#  1. torso box (8 verts)
#  2. extrude neck up
#  3. extrude arms from shoulder faces
#  4. extrude legs from hip faces
#  5. apply subdivision surface
# ═══════════════════════════════════════════════════════════════════════════

me_body = bpy.data.meshes.new("Body")
ob_body = new_obj("Body", me_body)
bm = bmesh.new()

# ── Torso cage (hip to shoulder) ──────────────────────────────────────────
# Z: ground=0, character height=2.0
# Torso: Z 0.55 → 1.35
# Neck:  Z 1.35 → 1.50
# Head centre: Z 1.75

HIP_Z   = 0.55;  HIP_W  = 0.20;  HIP_D  = 0.14
WAIST_Z = 0.72;  WAIST_W = 0.17; WAIST_D = 0.12
CHEST_Z = 0.90;  CHEST_W = 0.24; CHEST_D = 0.16
SHLDR_Z = 1.25;  SHLDR_W = 0.26; SHLDR_D = 0.16
NECK_Z  = 1.35

def box_verts(w, d, z):
    return [
        Vector((-w, -d, z)), Vector(( w, -d, z)),
        Vector(( w,  d, z)), Vector((-w,  d, z)),
    ]

layers = [
    box_verts(HIP_W,   HIP_D,   HIP_Z),
    box_verts(WAIST_W, WAIST_D, WAIST_Z),
    box_verts(CHEST_W, CHEST_D, CHEST_Z),
    box_verts(SHLDR_W, SHLDR_D, SHLDR_Z),
]

# Add all verts
all_verts = []
for ring in layers:
    row = []
    for pos in ring:
        v = bm.verts.new(pos)
        row.append(v)
    all_verts.append(row)

# Connect rings with quad faces
for i in range(len(all_verts) - 1):
    lo = all_verts[i]
    hi = all_verts[i+1]
    n = len(lo)
    for j in range(n):
        bm.faces.new([lo[j], lo[(j+1)%n], hi[(j+1)%n], hi[j]])

# Close top and bottom
bm.faces.new(all_verts[0])   # hip bottom
bm.faces.new(list(reversed(all_verts[-1])))  # shoulder top

# ── Neck ──────────────────────────────────────────────────────────────────
NECK_R = 0.08
neck_bot_z = SHLDR_Z
neck_top_z = 1.50
NECK_SEGS = 8
neck_bot = []
neck_top = []
for i in range(NECK_SEGS):
    a = 2*math.pi*i/NECK_SEGS
    nb = bm.verts.new(Vector((NECK_R*math.cos(a), NECK_R*math.sin(a), neck_bot_z)))
    nt = bm.verts.new(Vector((NECK_R*0.85*math.cos(a), NECK_R*0.85*math.sin(a), neck_top_z)))
    neck_bot.append(nb)
    neck_top.append(nt)
for i in range(NECK_SEGS):
    bm.faces.new([neck_bot[i], neck_bot[(i+1)%NECK_SEGS],
                  neck_top[(i+1)%NECK_SEGS], neck_top[i]])
bm.faces.new(list(reversed(neck_top)))

# ── Arms (8-segment cylinders, tapered) ───────────────────────────────────
def add_arm(side):
    sx = -1 if side == 'L' else 1
    SEGS = 8
    # Upper arm: shoulder → elbow
    UA_R_S = 0.075; UA_R_E = 0.060
    UA_SZ = SHLDR_Z - 0.05
    UA_EZ = 0.90
    UA_X  = sx * (SHLDR_W + 0.08)
    # Lower arm: elbow → wrist
    LA_R_S = 0.058; LA_R_E = 0.048
    LA_EZ = 0.55
    # Hand: wrist
    H_R = 0.055; H_Z = 0.42

    def cyl_ring(cx, cz, r, n=SEGS):
        ring = []
        for i in range(n):
            a = 2*math.pi*i/n
            ring.append(bm.verts.new(Vector((cx + r*math.cos(a), r*math.sin(a), cz))))
        return ring

    def connect_rings(r1, r2):
        n = len(r1)
        for i in range(n):
            bm.faces.new([r1[i], r1[(i+1)%n], r2[(i+1)%n], r2[i]])

    # Upper arm shoulder ring → elbow ring
    ua_s = cyl_ring(UA_X, UA_SZ, UA_R_S)
    ua_e = cyl_ring(UA_X, UA_EZ, UA_R_E)
    connect_rings(ua_s, ua_e)
    bm.faces.new(list(reversed(ua_s)))  # cap

    # Lower arm elbow → wrist
    la_s = cyl_ring(UA_X, UA_EZ, LA_R_S)
    la_e = cyl_ring(UA_X, LA_EZ, LA_R_E)
    connect_rings(la_s, la_e)

    # Hand
    h_r = cyl_ring(UA_X, H_Z, H_R)
    connect_rings(la_e, h_r)
    bm.faces.new(list(reversed(h_r)))  # hand tip

add_arm('L')
add_arm('R')

# ── Legs (tapered cylinders, inset from hip) ──────────────────────────────
def add_leg(side):
    sx = -1 if side == 'L' else 1
    SEGS = 10
    LX = sx * 0.115

    # Thigh: hip bottom → knee
    TH_R_TOP = 0.115; TH_R_BOT = 0.095
    TH_TOP_Z = HIP_Z - 0.02
    TH_BOT_Z = 0.32

    # Calf: knee → ankle
    CA_R_TOP = 0.090; CA_R_BOT = 0.060
    CA_BOT_Z = 0.10

    # Foot placeholder (will be replaced by shoe mesh)
    FT_Z = 0.05

    def cyl_ring(cz, r):
        ring = []
        for i in range(SEGS):
            a = 2*math.pi*i/SEGS
            ring.append(bm.verts.new(Vector((LX + r*math.cos(a), r*0.80*math.sin(a), cz))))
        return ring

    def connect_rings(r1, r2):
        n = len(r1)
        for i in range(n):
            bm.faces.new([r1[i], r1[(i+1)%n], r2[(i+1)%n], r2[i]])

    th_top = cyl_ring(TH_TOP_Z, TH_R_TOP)
    th_bot = cyl_ring(TH_BOT_Z, TH_R_BOT)
    connect_rings(th_top, th_bot)
    bm.faces.new(list(reversed(th_top)))

    ca_top = cyl_ring(TH_BOT_Z, CA_R_TOP)
    ca_bot = cyl_ring(CA_BOT_Z, CA_R_BOT)
    connect_rings(th_bot, ca_top)
    connect_rings(ca_top, ca_bot)
    bm.faces.new(list(reversed(ca_bot)))  # foot bottom

add_leg('L')
add_leg('R')

bm.verts.index_update()
bm.edges.index_update()
bm.to_mesh(me_body)
bm.free()
ob_body.data.update()

assign_mat(ob_body, mat_skin)
apply_subd(ob_body, levels=2)
print(f"Body: {len(ob_body.data.vertices)} verts after SubDiv")

# ═══════════════════════════════════════════════════════════════════════════
# HEAD — sphere base, deformed for stylised face
# ═══════════════════════════════════════════════════════════════════════════
HEAD_Z = 1.75
HEAD_R = 0.26  # 1:4 ratio → head = 0.52 / height 2.0

bpy.ops.mesh.primitive_uv_sphere_add(
    segments=24, ring_count=16, radius=HEAD_R,
    location=(0, 0, HEAD_Z)
)
ob_head = bpy.context.active_object
ob_head.name = "Head"

# Shape head: slightly wider at cheeks, narrower at chin
bm = bmesh.new()
bm.from_mesh(ob_head.data)

for v in bm.verts:
    nz = (v.co.z - HEAD_Z) / HEAD_R  # normalised -1..1
    # Wider face at eye level (nz ≈ 0) — slightly squash into oval
    if abs(nz) < 0.6:
        stretch = 1.0 + 0.12 * (1 - abs(nz/0.6)**2)
        v.co.x *= stretch
    # Taper chin (nz ≈ -1)
    if nz < -0.3:
        chin_t = (-nz - 0.3) / 0.7
        v.co.x *= (1 - 0.35 * chin_t)
        v.co.y *= (1 - 0.25 * chin_t)
    # Flatten face (forward push)
    if v.co.y < 0:  # front of head
        face_t = max(0, -v.co.y / HEAD_R)
        v.co.y -= 0.04 * face_t * math.sin(math.pi * (nz + 1) / 2)

bm.to_mesh(ob_head.data)
bm.free()
ob_head.data.update()
assign_mat(ob_head, mat_skin)
apply_subd(ob_head, levels=2)

# ── Eyes ──────────────────────────────────────────────────────────────────
def add_eye(side, mat_w, mat_i, mat_p):
    sx = -1 if side == 'L' else 1
    EYE_X = sx * 0.095
    EYE_Z = HEAD_Z + 0.03
    EYE_Y = -(HEAD_R * 0.78)

    # White
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8,
        radius=0.052, location=(EYE_X, EYE_Y, EYE_Z))
    ew = bpy.context.active_object; ew.name = f"Eye_White_{side}"
    # Scale to almond shape
    ew.scale.x = 1.15; ew.scale.y = 0.42; ew.scale.z = 0.85
    assign_mat(ew, mat_w)
    bpy.ops.object.transform_apply(scale=True)

    # Iris
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8,
        radius=0.038, location=(EYE_X, EYE_Y - 0.004, EYE_Z))
    ei = bpy.context.active_object; ei.name = f"Iris_{side}"
    ei.scale.x = 1.08; ei.scale.y = 0.30; ei.scale.z = 0.80
    assign_mat(ei, mat_i)
    bpy.ops.object.transform_apply(scale=True)

    # Pupil
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=8,
        radius=0.020, location=(EYE_X, EYE_Y - 0.006, EYE_Z))
    ep = bpy.context.active_object; ep.name = f"Pupil_{side}"
    ep.scale.x = 1.0; ep.scale.y = 0.25; ep.scale.z = 0.70
    assign_mat(ep, mat_p)
    bpy.ops.object.transform_apply(scale=True)

add_eye('L', mat_eye_w, mat_iris, mat_pupil)
add_eye('R', mat_eye_w, mat_iris, mat_pupil)

# ── Nose ──────────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=6,
    radius=0.032, location=(0, -(HEAD_R * 0.90), HEAD_Z - 0.065))
ob_nose = bpy.context.active_object; ob_nose.name = "Nose"
ob_nose.scale = (0.9, 0.6, 0.7)
assign_mat(ob_nose, mat_skin)
bpy.ops.object.transform_apply(scale=True)
apply_subd(ob_nose, 1)

# ── Mouth (smile curve) ───────────────────────────────────────────────────
# Create a small torus-based smile
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.065, minor_radius=0.014,
    major_segments=24, minor_segments=8,
    location=(0, -(HEAD_R * 0.88), HEAD_Z - 0.115)
)
ob_mouth = bpy.context.active_object; ob_mouth.name = "Mouth"
# Only keep bottom half (smile arc) by scaling Z
ob_mouth.scale.z = 0.4
ob_mouth.scale.x = 1.1
ob_mouth.rotation_euler.x = math.radians(8)
assign_mat(ob_mouth, make_mat("lips", 0.75, 0.38, 0.30, 0.6))
bpy.ops.object.transform_apply(scale=True, rotation=True)
apply_subd(ob_mouth, 1)

# ── Hair (short sculpted clumps) ──────────────────────────────────────────
def add_hair_clump(x, y_fwd, z, rx, ry, rz, sx=0.1, sy=0.085, sz=0.12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=8,
        radius=0.08, location=(x, y_fwd, z))
    h = bpy.context.active_object
    h.scale = (sx/0.08, sy/0.08, sz/0.08)
    h.rotation_euler = (math.radians(rx), math.radians(ry), math.radians(rz))
    assign_mat(h, mat_hair)
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    apply_subd(h, 1)
    return h

HTOP = HEAD_Z + HEAD_R - 0.03
add_hair_clump( 0.00,  0.00, HTOP + 0.05,  0,  0,  0, 0.16, 0.14, 0.10)
add_hair_clump( 0.10,  0.02, HTOP,         0,  0, 15, 0.10, 0.09, 0.10)
add_hair_clump(-0.10,  0.02, HTOP,         0,  0,-15, 0.10, 0.09, 0.10)
add_hair_clump( 0.05, -0.06, HTOP - 0.02,  8,  0,  5, 0.12, 0.10, 0.09)
add_hair_clump(-0.05, -0.06, HTOP - 0.02,  8,  0, -5, 0.12, 0.10, 0.09)
# Side hair (ears covered)
HEAR_Z = HEAD_Z + 0.00
add_hair_clump( HEAD_R*0.88,  0.02, HEAR_Z,  0,  0, 20, 0.09, 0.07, 0.13)
add_hair_clump(-HEAD_R*0.88,  0.02, HEAR_Z,  0,  0,-20, 0.09, 0.07, 0.13)

# ═══════════════════════════════════════════════════════════════════════════
# JERSEY — slightly inflated torso shape with collar and number detail
# ═══════════════════════════════════════════════════════════════════════════
me_j = bpy.data.meshes.new("Jersey")
ob_j = new_obj("Jersey", me_j)
bm = bmesh.new()

# Jersey is the torso box scaled out slightly
JER_HIP_Z = HIP_Z - 0.01; JER_HIP_W = HIP_W + 0.028; JER_HIP_D = HIP_D + 0.022
JER_WS_Z  = WAIST_Z; JER_WS_W  = WAIST_W + 0.025; JER_WS_D  = WAIST_D + 0.018
JER_CH_Z  = CHEST_Z; JER_CH_W  = CHEST_W + 0.020; JER_CH_D  = CHEST_D + 0.016
JER_SH_Z  = SHLDR_Z + 0.04; JER_SH_W  = SHLDR_W + 0.012; JER_SH_D  = SHLDR_D + 0.010
JER_NECK_Z = 1.32

j_layers = [
    box_verts(JER_HIP_W,  JER_HIP_D,  JER_HIP_Z),
    box_verts(JER_WS_W,   JER_WS_D,   JER_WS_Z),
    box_verts(JER_CH_W,   JER_CH_D,   JER_CH_Z),
    box_verts(JER_SH_W,   JER_SH_D,   JER_SH_Z),
]
j_verts = []
for ring in j_layers:
    row = [bm.verts.new(p) for p in ring]
    j_verts.append(row)
for i in range(len(j_verts) - 1):
    lo = j_verts[i]; hi = j_verts[i+1]; n = len(lo)
    for j in range(n):
        bm.faces.new([lo[j], lo[(j+1)%n], hi[(j+1)%n], hi[j]])
bm.faces.new(j_verts[0])

# Collar ring
COLL_R = 0.10; COLL_SEGS = 12; COLL_Z = JER_NECK_Z
coll_verts = []
for i in range(COLL_SEGS):
    a = 2*math.pi*i/COLL_SEGS
    coll_verts.append(bm.verts.new(Vector((COLL_R*math.cos(a), COLL_R*math.sin(a), COLL_Z))))
bm.faces.new(list(reversed(coll_verts)))

# Sleeve stubs (caps where arms attach)
def sleeve_cap(sx):
    SEGS = 8; SL_R = 0.085; SL_X = sx*(JER_SH_W + 0.025); SL_Z = SHLDR_Z
    ring = [bm.verts.new(Vector((SL_X + SL_R*math.cos(a), SL_R*math.sin(a), SL_Z)))
            for a in (2*math.pi*i/SEGS for i in range(SEGS))]
    bm.faces.new(list(reversed(ring)))
sleeve_cap(-1); sleeve_cap(1)

bm.verts.index_update()
bm.to_mesh(me_j)
bm.free()
assign_mat(ob_j, mat_jersey)
apply_subd(ob_j, levels=2)

# ═══════════════════════════════════════════════════════════════════════════
# SHORTS
# ═══════════════════════════════════════════════════════════════════════════
me_sh = bpy.data.meshes.new("Shorts")
ob_sh = new_obj("Shorts", me_sh)
bm = bmesh.new()

SH_TOP_Z = HIP_Z - 0.02; SH_BOT_Z = 0.42

def shorts_layer(z, wx, wz_scale=1.0):
    pts = []
    SEGS = 16
    for i in range(SEGS):
        a = 2*math.pi*i/SEGS
        r = wx * (1 + 0.15*abs(math.sin(a)))  # slightly irregular
        pts.append(bm.verts.new(Vector((r*math.cos(a), r*math.sin(a)*wz_scale, z))))
    return pts

s_top = shorts_layer(SH_TOP_Z, 0.215, 0.72)
s_bot = shorts_layer(SH_BOT_Z, 0.185, 0.70)
n = len(s_top)
for i in range(n):
    bm.faces.new([s_top[i], s_top[(i+1)%n], s_bot[(i+1)%n], s_bot[i]])
bm.faces.new(list(reversed(s_top)))
bm.faces.new(s_bot)

bm.verts.index_update()
bm.to_mesh(me_sh)
bm.free()
assign_mat(ob_sh, mat_shorts)
apply_subd(ob_sh, levels=2)

# ═══════════════════════════════════════════════════════════════════════════
# SHOES (running shoe silhouette)
# ═══════════════════════════════════════════════════════════════════════════
def add_shoe(side):
    sx = -1 if side == 'L' else 1
    SX = sx * 0.115

    me = bpy.data.meshes.new(f"Shoe_{side}")
    ob = new_obj(f"Shoe_{side}", me)
    bm = bmesh.new()

    # Shoe as elongated oval viewed from side — roughly:
    # front: toe; back: heel; top: ankle; bottom: sole
    # Build as a rounded box with specific proportions

    # Upper shoe body
    SEGS = 12
    def shoe_ring(cx, cz, rx, rz_top, rz_bot):
        pts = []
        for i in range(SEGS):
            a = 2*math.pi*i/SEGS
            rx_ = rx * (1 + 0.18*(math.cos(a)+1)*0.5)  # longer at front
            rz = rz_top if math.sin(a) > 0 else rz_bot
            pts.append(bm.verts.new(Vector((SX + rx_*math.cos(a), rz*math.sin(a), cz))))
        return pts

    # Cross sections: heel, mid, toe
    r_heel = shoe_ring(SX - 0.06, 0.09, 0.06, 0.055, 0.04)
    r_mid  = shoe_ring(SX,        0.09, 0.10, 0.065, 0.04)
    r_toe  = shoe_ring(SX + 0.09, 0.06, 0.07, 0.04,  0.03)

    def cr(r1, r2):
        n = len(r1)
        for i in range(n):
            bm.faces.new([r1[i], r1[(i+1)%n], r2[(i+1)%n], r2[i]])

    cr(r_heel, r_mid); cr(r_mid, r_toe)
    bm.faces.new(list(reversed(r_heel)))
    bm.faces.new(r_toe)

    # Sole slab
    SOLE_Z = 0.00
    SOLE_THICK = 0.03
    sole_verts = [
        bm.verts.new(Vector((SX - 0.09, -0.04, SOLE_Z))),
        bm.verts.new(Vector((SX + 0.13, -0.04, SOLE_Z))),
        bm.verts.new(Vector((SX + 0.14,  0.03, SOLE_Z))),
        bm.verts.new(Vector((SX - 0.10,  0.03, SOLE_Z))),
    ]
    sole_bot = [bm.verts.new(Vector((v.co.x, v.co.y, SOLE_Z - SOLE_THICK)))
                for v in sole_verts]
    bm.faces.new(list(reversed(sole_verts)))
    bm.faces.new(sole_bot)
    n = len(sole_verts)
    for i in range(n):
        bm.faces.new([sole_verts[i], sole_verts[(i+1)%n],
                      sole_bot[(i+1)%n], sole_bot[i]])

    bm.verts.index_update()
    bm.to_mesh(me)
    bm.free()
    ob.data.update()
    assign_mat(ob, mat_shoes)
    apply_subd(ob, levels=1)

add_shoe('L')
add_shoe('R')

# ═══════════════════════════════════════════════════════════════════════════
# ARMATURE — humanoid rig for run animation compatibility
# ═══════════════════════════════════════════════════════════════════════════
bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
arm_ob = bpy.context.active_object
arm_ob.name = "Armature"
arm = arm_ob.data
arm.name = "Armature"

eb = arm.edit_bones

# Helper: add bone
def add_bone(name, head, tail, parent_name=None, roll=0):
    b = eb.new(name)
    b.head = Vector(head)
    b.tail = Vector(tail)
    b.roll = roll
    if parent_name and parent_name in eb:
        b.parent = eb[parent_name]
        b.use_connect = False
    return b

# Clear default bone
for b in list(eb):
    eb.remove(b)

# Spine chain
add_bone("Hips",        (0,0,0.60), (0,0,0.72))
add_bone("Spine",       (0,0,0.72), (0,0,0.90), "Hips")
add_bone("Spine1",      (0,0,0.90), (0,0,1.10), "Spine")
add_bone("Spine2",      (0,0,1.10), (0,0,1.28), "Spine1")
add_bone("Neck",        (0,0,1.28), (0,0,1.50), "Spine2")
add_bone("Head",        (0,0,1.50), (0,0,1.90), "Neck")

# Left arm
add_bone("LeftShoulder",  (-0.10,0,1.25), (-0.26,0,1.22), "Spine2")
add_bone("LeftArm",       (-0.26,0,1.22), (-0.38,0,0.93), "LeftShoulder")
add_bone("LeftForeArm",   (-0.38,0,0.93), (-0.40,0,0.58), "LeftArm")
add_bone("LeftHand",      (-0.40,0,0.58), (-0.40,0,0.43), "LeftForeArm")

# Right arm (mirror)
add_bone("RightShoulder", ( 0.10,0,1.25), ( 0.26,0,1.22), "Spine2")
add_bone("RightArm",      ( 0.26,0,1.22), ( 0.38,0,0.93), "RightShoulder")
add_bone("RightForeArm",  ( 0.38,0,0.93), ( 0.40,0,0.58), "RightArm")
add_bone("RightHand",     ( 0.40,0,0.58), ( 0.40,0,0.43), "RightForeArm")

# Left leg
add_bone("LeftUpLeg",   (-0.115,0,0.55), (-0.115,0,0.33), "Hips")
add_bone("LeftLeg",     (-0.115,0,0.33), (-0.115,0,0.10), "LeftUpLeg")
add_bone("LeftFoot",    (-0.115,0,0.10), (-0.115,-0.10,0.03), "LeftLeg")
add_bone("LeftToeBase", (-0.115,-0.10,0.03), (-0.115,-0.18,0.0), "LeftFoot")

# Right leg
add_bone("RightUpLeg",  ( 0.115,0,0.55), ( 0.115,0,0.33), "Hips")
add_bone("RightLeg",    ( 0.115,0,0.33), ( 0.115,0,0.10), "RightUpLeg")
add_bone("RightFoot",   ( 0.115,0,0.10), ( 0.115,-0.10,0.03), "RightLeg")
add_bone("RightToeBase",( 0.115,-0.10,0.03), ( 0.115,-0.18,0.0), "RightFoot")

bpy.ops.object.mode_set(mode='OBJECT')

# ── Parent all mesh objects to armature with auto weights ──────────────────
meshes = [ob_body, ob_head, ob_j, ob_sh]
for ob in meshes:
    ob.select_set(True)
arm_ob.select_set(True)
bpy.context.view_layer.objects.active = arm_ob
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
bpy.ops.object.select_all(action='DESELECT')

print("Rigging complete.")

# ── Add a simple idle pose (arms slightly down, natural stance) ────────────
bpy.context.view_layer.objects.active = arm_ob
bpy.ops.object.posemode_toggle()
pose = arm_ob.pose
import math

def pose_bone(name, rx=0, ry=0, rz=0):
    if name in pose.bones:
        b = pose.bones[name]
        b.rotation_mode = 'XYZ'
        b.rotation_euler = (math.radians(rx), math.radians(ry), math.radians(rz))

# Arms hang naturally down from shoulder (~20° forward, 5° out)
pose_bone("LeftArm",     rx=15, ry=5,  rz=10)
pose_bone("LeftForeArm", rx=10, ry=0,  rz=5)
pose_bone("RightArm",    rx=15, ry=-5, rz=-10)
pose_bone("RightForeArm",rx=10, ry=0,  rz=-5)

bpy.ops.object.posemode_toggle()

# ═══════════════════════════════════════════════════════════════════════════
# EXPORT GLB
# ═══════════════════════════════════════════════════════════════════════════
OUT = '/tmp/athlete_male.glb'

# Select everything and export
bpy.ops.object.select_all(action='SELECT')
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
print(f"  Objects: {len([o for o in bpy.context.scene.objects])}")
for ob in sorted(bpy.context.scene.objects, key=lambda o: o.name):
    if ob.type == 'MESH':
        print(f"  Mesh '{ob.name}': {len(ob.data.vertices)} verts")
