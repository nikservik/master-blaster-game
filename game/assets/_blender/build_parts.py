exec(open(r"C:\Dev\asset-cache\work\blib.py", encoding="utf-8").read())
import bpy, bmesh

sc = bpy.data.scenes.get("B_Build") or bpy.data.scenes.new("B_Build")
bpy.context.window.scene = sc
for o in list(sc.objects):
    bpy.data.objects.remove(o, do_unlink=True)
coll = collection("building")
M = mats()
BLOCKS, PLANKS = M['blocks'], M['planks']
OUT = GAME + r"\building"
made = []

SLAB, WALL_H, WALL_T = 0.2, 2.8, 0.2

# Foundations: sandstone blocks, top at 0, bottom at -0.2 (floor level origin, like BuildPart)
for w, d in ((2, 2), (2, 1), (1, 1)):
    bm = bmesh.new(); add_box(bm, (-w / 2, -d / 2, -SLAB), (w / 2, d / 2, 0), 0); bevel(bm, 0.015); box_uv(bm, 2.0)
    made.append(finish(f"foundation_{w}x{d}", bm, [BLOCKS], coll))

# Floors: plank slab with sandstone edge beams? keep planks all round
for w, d in ((2, 2), (2, 1), (1, 1)):
    bm = bmesh.new(); add_box(bm, (-w / 2, -d / 2, -SLAB), (w / 2, d / 2, 0), 0); bevel(bm, 0.01); box_uv(bm, 1.0)
    made.append(finish(f"floor_{w}x{d}", bm, [PLANKS], coll))

# Walls: length along X, thickness 0.2 centred, from floor 0 to 2.8
for L in (2, 1):
    bm = bmesh.new(); add_box(bm, (-L / 2, -WALL_T / 2, 0), (L / 2, WALL_T / 2, WALL_H), 0); bevel(bm, 0.01); box_uv(bm, 2.0)
    made.append(finish(f"wall_{L}m", bm, [BLOCKS], coll))

# Door wall: opening 1 x 2.2 centred; wooden lintel beam above opening
bm = bmesh.new()
add_box(bm, (-1, -WALL_T / 2, 0), (-0.5, WALL_T / 2, WALL_H), 0)
add_box(bm, (0.5, -WALL_T / 2, 0), (1, WALL_T / 2, WALL_H), 0)
add_box(bm, (-0.5, -WALL_T / 2, 2.2 + 0.18), (0.5, WALL_T / 2, WALL_H), 0)
add_box(bm, (-0.62, -WALL_T / 2 - 0.02, 2.2), (0.62, WALL_T / 2 + 0.02, 2.2 + 0.18), 1)
bevel(bm, 0.01); box_uv(bm, 2.0, {1: 1.0})
made.append(finish("wall_door_2m", bm, [BLOCKS, PLANKS], coll))

# Stairs 2 x 4, rise 3 in 10 steps; bottom at glTF +Z (Blender -Y), top at glTF -Z (Blender +Y)
bm = bmesh.new()
# profile: bottom edge, back vertical, then steps down to front
pts = [(-2, 0), (2, 0), (2, 3.0)]
for i in range(9, -1, -1):
    y0 = -2 + i * 0.4
    pts.append((y0, (i + 1) * 0.3))
    if i > 0:
        pts.append((y0, i * 0.3))
fs = add_prism(bm, pts, -1, 1, 0)
for v in bm.verts:
    v.co.x, v.co.y = v.co.y, v.co.x
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.normal_update()
box_uv(bm, 2.0)
made.append(finish("stairs_2x4", bm, [BLOCKS], coll))

# Support post: 0.3 x 0.3, from 0 down to -1 m (origin at top: hangs under a foundation, scale Y to reach ground)
bm = bmesh.new(); add_box(bm, (-0.15, -0.15, -1), (0.15, 0.15, 0), 0); bevel(bm, 0.015); box_uv(bm, 2.0)
made.append(finish("post_1m", bm, [BLOCKS], coll))

for o in made:
    export(o, OUT + "\\" + o.name + ".gltf")

# layout for preview
x = 0
for o in made:
    o.location.x = x
    x += o.dimensions.x + 0.8
print([o.name for o in made])
