exec(open(r"C:\Dev\asset-cache\work\blib.py", encoding="utf-8").read())
import bpy, bmesh, math, random

sc = bpy.context.scene
coll = collection("ruins")
for o in list(coll.objects):
    bpy.data.objects.remove(o, do_unlink=True)
M = mats()
BL, RU, GL = M['blocks'], M['rubble'], M['glow']
OUT = GAME + r"\ruins"
made = []
rnd = random.Random(7)


def column(name, height, broken=False, rings=()):
    bm = bmesh.new()
    add_box(bm, (-0.5, -0.5, 0), (0.5, 0.5, 0.3), 0)
    add_box(bm, (-0.42, -0.42, 0.3), (0.42, 0.42, 0.42), 0)
    top = height - (0 if broken else 0.42)
    fs, b, t = add_cyl(bm, 0.36, 0.32, 0.42, top, 16, mat=0)
    if broken:
        for v in t:
            v.co.z = top - rnd.uniform(0, 0.45)
    else:
        add_box(bm, (-0.42, -0.42, top), (0.42, 0.42, top + 0.12), 0)
        add_box(bm, (-0.5, -0.5, top + 0.12), (0.5, 0.5, height), 0)
    extra = []
    for z in rings:
        f2, _, _ = add_cyl(bm, 0.365, 0.365 * 0.99, z, z + 0.07, 16, mat=1)
        extra += f2
    bm.normal_update()
    box_uv(bm, 2.0)
    cyl_uv(bm, fs + extra, 16, circumference_tiles=1.0, tile=2.0)
    return finish(name, bm, [BL, GL], coll)


made.append(column("column", 4.0))
made.append(column("column_broken", 2.4, broken=True))
made.append(column("column_magitech", 4.0, rings=(1.3, 2.7)))

# Rubble walls 4 m long (X), 0.8 m thick
bm = bmesh.new(); add_box(bm, (-2, -0.4, 0), (2, 0.4, 3), 0); add_box(bm, (-2.1, -0.5, 3), (2.1, 0.5, 3.2), 1)
bevel(bm, 0.03); box_uv(bm, 2.0)
made.append(finish("wall", bm, [RU, BL], coll))

bm = bmesh.new()
hs = [3.0, 2.8, 2.5, 2.6, 1.9, 1.3, 1.5, 0.9]
for i, h in enumerate(hs):
    add_box(bm, (-2 + i * 0.5, -0.4, 0), (-1.5 + i * 0.5, 0.4, h + rnd.uniform(-0.1, 0.1)), 0)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
box_uv(bm, 2.0)
made.append(finish("wall_broken", bm, [RU], coll))

# Stepped terrace wall: 3 tiers, 4 m wide, 3 m deep, highest at back (+Y in Blender = -Z in glTF)
bm = bmesh.new()
for k, h in enumerate((1.0, 2.0, 3.0)):
    add_box(bm, (-2, -1.5 + k * 1.0, 0), (2, -0.5 + k * 1.0, h), 0)
    add_box(bm, (-2.05, -1.55 + k * 1.0, h), (2.05, -0.5 + k * 1.0, h + 0.15), 1)
bevel(bm, 0.02); box_uv(bm, 2.0)
made.append(finish("wall_stepped", bm, [RU, BL], coll))

# Aqueduct arch: 4 m wide, 1 m deep, 5.3 m high, opening 2.4 m, springing at 2.6 m
bm = bmesh.new()
add_box(bm, (-2, -0.5, 0), (-1.2, 0.5, 5), 0)
add_box(bm, (1.2, -0.5, 0), (2, 0.5, 5), 0)
seg = 12
for i in range(seg):
    a0 = math.pi * i / seg; a1 = math.pi * (i + 1) / seg
    x0, z0 = 1.2 * math.cos(a0), 2.6 + 1.2 * math.sin(a0)
    x1, z1 = 1.2 * math.cos(a1), 2.6 + 1.2 * math.sin(a1)
    add_prism(bm, [(x1, z1), (x0, z0), (x0, 5.0), (x1, 5.0)], -0.5, 0.5, 0)
add_box(bm, (-2.15, -0.6, 5), (2.15, 0.6, 5.3), 1)
# glowing keystone inlay
add_box(bm, (-0.12, -0.52, 3.95), (0.12, -0.49, 4.45), 2)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
bm.normal_update()
box_uv(bm, 2.0)
made.append(finish("arch", bm, [BL, BL, GL], coll))

# Floor slab 4 x 4 x 0.3, top at 0
bm = bmesh.new(); add_box(bm, (-2, -2, -0.3), (2, 2, 0), 0); bevel(bm, 0.03); box_uv(bm, 2.0)
made.append(finish("floor_slab", bm, [BL], coll))

# Ruined stairs: 3 m wide, 5 steps of 0.3 x 0.5, rising towards +Y (glTF -Z)
bm = bmesh.new()
for i in range(5):
    add_box(bm, (-1.5, -1.25 + i * 0.5, 0), (1.5, 1.25, (i + 1) * 0.3), 0)
bevel(bm, 0.02); box_uv(bm, 2.0)
made.append(finish("stairs", bm, [BL], coll))


def chunk(bm, size, loc, rot, mat=0):
    fs = add_box(bm, tuple(-s / 2 for s in size), tuple(s / 2 for s in size), mat)
    vs = list({v for f in fs for v in f.verts})
    for v in vs:
        v.co += Vector((rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04)))
    Mx = Matrix.Translation(loc) @ Matrix.Rotation(rot[2], 4, 'Z') @ Matrix.Rotation(rot[1], 4, 'Y') @ Matrix.Rotation(rot[0], 4, 'X')
    bmesh.ops.transform(bm, matrix=Mx, verts=vs)


for name, parts in {
    "debris_block": [((0.9, 0.6, 0.5), (0, 0, 0.22), (0.05, 0.1, 0.3))],
    "debris_slab": [((1.6, 1.0, 0.25), (0, 0, 0.1), (0.08, 0.02, 0.5))],
    "debris_pile": [((0.9, 0.6, 0.5), (0, 0, 0.25), (0, 0, 0.2)), ((0.7, 0.5, 0.4), (0.7, 0.3, 0.2), (0.2, 0.1, 1.0)),
                    ((0.6, 0.5, 0.35), (0.2, -0.1, 0.62), (0.3, -0.2, 0.7)), ((0.5, 0.4, 0.3), (-0.6, 0.4, 0.14), (0.1, 0.2, -0.4)),
                    ((0.4, 0.35, 0.3), (-0.3, -0.5, 0.13), (0, 0.3, 0.9))],
}.items():
    bm = bmesh.new()
    for size, loc, rot in parts:
        chunk(bm, size, loc, rot)
    bm.normal_update(); box_uv(bm, 2.0)
    made.append(finish(name, bm, [BL], coll))

# Fallen column drum lying on its side
bm = bmesh.new()
fs, b, t = add_cyl(bm, 0.34, 0.34, -0.45, 0.45, 16, mat=0)
bm.normal_update(); cyl_uv(bm, fs, 16); box_uv_faces = [f for f in fs if abs(f.normal.z) > 0.9]
uv = bm.loops.layers.uv.verify()
for f in box_uv_faces:
    for l in f.loops:
        l[uv].uv = (l.vert.co.x / 2, l.vert.co.y / 2)
bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
bmesh.ops.translate(bm, verts=bm.verts[:], vec=(0, 0, 0.34))
made.append(finish("debris_drum", bm, [BL], coll))

# Magitech obelisk: tapered square shaft with glowing glyph strips
bm = bmesh.new()
add_box(bm, (-0.7, -0.7, 0), (0.7, 0.7, 0.4), 0)
v0 = [bm.verts.new(p) for p in [(-0.4, -0.4, 0.4), (0.4, -0.4, 0.4), (0.4, 0.4, 0.4), (-0.4, 0.4, 0.4)]]
v1 = [bm.verts.new(p) for p in [(-0.24, -0.24, 5.0), (0.24, -0.24, 5.0), (0.24, 0.24, 5.0), (-0.24, 0.24, 5.0)]]
tip = bm.verts.new((0, 0, 5.6))
for i in range(4):
    j = (i + 1) % 4
    bm.faces.new([v0[i], v0[j], v1[j], v1[i]])
    f = bm.faces.new([v1[i], v1[j], tip]); f.material_index = 1
for side in range(4):
    for k, (z0, z1) in enumerate(((0.9, 2.2), (2.5, 3.4), (3.7, 4.6))):
        # strip on -Y face, then rotate copy for each side
        def half(z):
            return 0.4 + (0.24 - 0.4) * (z - 0.4) / 4.6
        w = 0.05
        q = [bm.verts.new((-w, -half(z0) - 0.012, z0)), bm.verts.new((w, -half(z0) - 0.012, z0)),
             bm.verts.new((w, -half(z1) - 0.012, z1)), bm.verts.new((-w, -half(z1) - 0.012, z1))]
        f = bm.faces.new(q); f.material_index = 1
        bmesh.ops.rotate(bm, verts=q, cent=(0, 0, 0), matrix=Matrix.Rotation(side * math.pi / 2, 3, 'Z'))
orient_out(bm, 1); box_uv(bm, 2.0)
made.append(finish("obelisk_magitech", bm, [BL, GL], coll))

# Magitech wall panel: 1 x 1 stone plate, back at y=0 (glTF z=0), faces glTF +Z (Blender -Y); glowing rune ring
bm = bmesh.new()
add_box(bm, (-0.5, -0.1, -0.5), (0.5, 0, 0.5), 0)
n = 24
outer = [bm.verts.new((0.32 * math.cos(2 * math.pi * i / n), -0.105, 0.32 * math.sin(2 * math.pi * i / n))) for i in range(n)]
inner = [bm.verts.new((0.26 * math.cos(2 * math.pi * i / n), -0.105, 0.26 * math.sin(2 * math.pi * i / n))) for i in range(n)]
for i in range(n):
    j = (i + 1) % n
    f = bm.faces.new([outer[i], outer[j], inner[j], inner[i]]); f.material_index = 1
for a in (0, math.pi / 2):
    q = [bm.verts.new(p) for p in [(-0.2, -0.105, -0.025), (0.2, -0.105, -0.025), (0.2, -0.105, 0.025), (-0.2, -0.105, 0.025)]]
    f = bm.faces.new(q); f.material_index = 1
    bmesh.ops.rotate(bm, verts=q, cent=(0, -0.105, 0), matrix=Matrix.Rotation(a, 3, 'Y'))
orient_out(bm, 1); box_uv(bm, 2.0)
made.append(finish("magitech_panel", bm, [BL, GL], coll))

for o in made:
    export(o, OUT + "\\" + o.name + ".gltf")
x = 0
for o in made:
    o.location = (x, 12, 0)
    x += o.dimensions.x + 1.0
print([o.name for o in made])
