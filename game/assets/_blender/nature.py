exec(open(r"C:\Dev\asset-cache\work\blib.py", encoding="utf-8").read())
import bpy, bmesh, math, random, os

sc = bpy.context.scene
PROPS = r"C:\Dev\asset-cache\props\Exports\glTF"


def imp(path, coll):
    before = set(sc.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in sc.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    meshes = [o for o in new if o.type == 'MESH']
    # flatten: keep meshes, apply parent transforms, drop empties
    for o in meshes:
        mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o, do_unlink=True)
    if len(meshes) > 1:
        with bpy.context.temp_override(active_object=meshes[0], selected_editable_objects=meshes, object=meshes[0]):
            bpy.ops.object.join()
    ob = meshes[0]
    return ob


def shrink_images(ob, size=1024):
    for m in ob.data.materials:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image and n.image.size[0] > size:
                n.image.scale(size, size)


def swap_image(ob, new_path):
    im = img(new_path)
    for m in ob.data.materials:
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image and n.image.name != im.name and 'Normal' not in n.image.name:
                n.image = im


def clear(coll):
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)


# ---------------- vegetation ----------------
veg = collection("vegetation"); clear(veg)
OUTV = GAME + r"\vegetation"
made = []
for src, dst in [("Bush_Common", "bush"), ("Bush_Common_Flowers", "bush_flowers"), ("Fern_1", "fern"),
                 ("Plant_1", "plant_small"), ("Plant_1_Big", "plant_big"), ("Clover_1", "clover"),
                 ("Grass_Common_Short", "grass_short"), ("Grass_Common_Tall", "grass_tall"),
                 ("Grass_Wispy_Short", "grass_wispy_short"), ("Grass_Wispy_Tall", "grass_wispy_tall")]:
    ob = imp(os.path.join(NAT, src + ".gltf"), veg)
    ob.name = dst
    if src == "Bush_Common":
        swap_image(ob, os.path.join(NAT, "Leaves_NormalTree_C.png"))
    shrink_images(ob)
    made.append(ob)

for src, dst in [("Prop_Vine1", "vine_1"), ("Prop_Vine2", "vine_2"), ("Prop_Vine4", "vine_3"),
                 ("Prop_Vine5", "vine_4"), ("Prop_Vine6", "vine_5"), ("Prop_Vine9", "vine_6")]:
    ob = imp(os.path.join(VIL, src + ".gltf"), veg)
    ob.name = dst
    made.append(ob)

# Palms: trunk with MegaKit bark, fronds cut from the fern leaf of MegaKit Leaves.png
frond_mat = pbr('M_PalmFrond', NAT + r"\Leaves.png", alpha=True, rough_val=0.8)
bark_mat = pbr('M_PalmBark', NAT + r"\Bark_NormalTree.png", NAT + r"\Bark_NormalTree_Normal.png", rough_val=0.95)
for m in (frond_mat, bark_mat):
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image.size[0] > 1024:
            n.image.scale(1024, 1024)

U0, U1, V0, V1 = 0.015, 0.28, 0.047, 0.5625


def palm(name, H, lean, nfr, flen, seed):
    r = random.Random(seed)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.verify()
    rings, sides = 14, 8
    ring_v = []
    for k in range(rings + 1):
        t = k / rings
        cx, cz = lean * t * t, H * t
        rad = (0.21 - 0.08 * t) * (1.07 if k % 2 else 1.0)
        ring_v.append([bm.verts.new((cx + rad * math.cos(2 * math.pi * i / sides), rad * math.sin(2 * math.pi * i / sides), cz)) for i in range(sides)])
    for k in range(rings):
        for i in range(sides):
            j = (i + 1) % sides
            f = bm.faces.new([ring_v[k][i], ring_v[k][j], ring_v[k + 1][j], ring_v[k + 1][i]])
            f.material_index = 0
            for l, (ii, kk) in zip(f.loops, [(i, k), (i + 1, k), (i + 1, k + 1), (i, k + 1)]):
                l[uv].uv = (ii / sides * 2, kk / rings * H / 1.5)
    top = Vector((lean, 0, H))
    for fi in range(nfr):
        yaw = 2 * math.pi * fi / nfr + r.uniform(-0.2, 0.2)
        young = fi % 4 == 3
        L = flen * (0.6 if young else r.uniform(0.9, 1.1))
        W = L * 0.47
        p0 = math.radians(r.uniform(55, 70) if young else r.uniform(25, 45))
        droop = math.radians(40 if young else r.uniform(90, 120))
        d = Vector((math.cos(yaw), math.sin(yaw), 0)); side = Vector((-math.sin(yaw), math.cos(yaw), 0))
        seg = 8
        pos = top.copy()
        rows = []
        for s in range(seg + 1):
            t = s / seg
            w = W / 2 * (0.35 + 0.65 * math.sin(min(1.0, t * 1.3) * math.pi / 2)) if s else W * 0.12
            fold = 0.1 * W * (1 if s else 0)
            rows.append([bm.verts.new(pos + side * w + Vector((0, 0, -fold))), bm.verts.new(pos.copy()),
                         bm.verts.new(pos - side * w + Vector((0, 0, -fold)))])
            pitch = p0 - droop * t
            pos = pos + (d * math.cos(pitch) + Vector((0, 0, math.sin(pitch)))) * (L / seg)
        for s in range(seg):
            for c in range(2):
                f = bm.faces.new([rows[s][c], rows[s][c + 1], rows[s + 1][c + 1], rows[s + 1][c]])
                f.material_index = 1
                us = [U0, (U0 + U1) / 2, U1]
                for l, (ss, cc) in zip(f.loops, [(s, c), (s, c + 1), (s + 1, c + 1), (s + 1, c)]):
                    l[uv].uv = (us[cc], V0 + (V1 - V0) * ss / seg)
    bm.normal_update()
    ob = finish(name, bm, [bark_mat, frond_mat], veg)
    for p in ob.data.polygons:
        p.use_smooth = p.material_index == 0
    return ob


made.append(palm("palm_1", 6.5, 1.2, 12, 3.0, 1))
made.append(palm("palm_2", 8.0, 2.0, 13, 3.2, 2))
made.append(palm("palm_3", 4.5, 0.5, 11, 2.6, 3))

for o in made:
    export(o, OUTV + "\\" + o.name + ".gltf")
x = 0
for o in made:
    o.location = (x, 24, 0); x += max(o.dimensions.x, 1) + 0.8

# ---------------- rocks ----------------
rk = collection("rocks"); clear(rk)
OUTR = GAME + r"\rocks"
rmade = []
for i in (1, 2, 3):
    ob = imp(os.path.join(NAT, f"Rock_Medium_{i}.gltf"), rk); ob.name = f"rock_{i}"; shrink_images(ob); rmade.append(ob)
    ob2 = ob.copy(); ob2.data = ob.data.copy(); ob2.name = f"rock_desert_{i}"; rk.objects.link(ob2)
    m = ob2.data.materials[0].copy(); m.name = "Rocks_Desert"; ob2.data.materials[0] = m
    swap_image(ob2, os.path.join(NAT, "Rocks_Desert_Diffuse.png")); shrink_images(ob2); rmade.append(ob2)
for src, dst in [("Pebble_Round_1", "pebble_round_1"), ("Pebble_Round_3", "pebble_round_2"), ("Pebble_Square_1", "pebble_square_1"), ("Pebble_Square_4", "pebble_square_2")]:
    ob = imp(os.path.join(NAT, src + ".gltf"), rk); ob.name = dst; shrink_images(ob); rmade.append(ob)

# desert plateau chunk: three desert rocks scaled and joined (~9 x 7 x 5 m)
parts = []
for i, (loc, rot, s) in enumerate([((0, 0, 0), 0.3, 2.6), ((3.2, 1.0, -0.4), 1.9, 2.2), ((-2.6, 1.4, -0.6), 4.0, 2.0)]):
    src = bpy.data.objects[f"rock_desert_{i + 1}"]
    p = src.copy(); p.data = src.data.copy(); rk.objects.link(p)
    p.location = loc; p.rotation_euler = (0, 0, rot); p.scale = (s, s, s * 1.1)
    parts.append(p)
with bpy.context.temp_override(active_object=parts[0], selected_editable_objects=parts, object=parts[0]):
    bpy.ops.object.join()
pl = parts[0]; pl.name = "plateau_desert"
with bpy.context.temp_override(active_object=pl, selected_editable_objects=[pl], object=pl):
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
rmade.append(pl)
for o in rmade:
    export(o, OUTR + "\\" + o.name + ".gltf")
x = 0
for o in rmade:
    o.location = (x, 32, 0); x += o.dimensions.x + 0.8

# ---------------- props ----------------
pr = collection("props"); clear(pr)
OUTP = GAME + r"\props"
crate = imp(os.path.join(PROPS, "Crate_Wooden.gltf"), pr); crate.name = "crate"
table = imp(os.path.join(PROPS, "Table_Large.gltf"), pr); table.name = "table"
for ob in (crate, table):
    with bpy.context.temp_override(active_object=ob, selected_editable_objects=[ob], object=ob):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    shrink_images(ob)


def fit(ob, size_xyz, cut_x=None):
    me = ob.data
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    for v in me.vertices:
        v.co.x -= cx; v.co.y -= cy; v.co.z -= min(zs)
    if cut_x:
        half = (max(xs) - min(xs)) / 2; shift = half - size_xyz[0] / 2
        for v in me.vertices:
            if v.co.x > 0:
                v.co.x = max(0.0, v.co.x - shift)
            else:
                v.co.x = min(0.0, v.co.x + shift)
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    sx = size_xyz[0] / (max(xs) - min(xs)); sy = size_xyz[1] / (max(ys) - min(ys)); sz = size_xyz[2] / (max(zs) - min(zs))
    for v in me.vertices:
        v.co.x *= sx; v.co.y *= sy; v.co.z *= sz
    me.update()


# Blender (x, y, z) = glTF (x, -z, y): crate 0.8 cube; table 1.4 (X) x 0.8 (depth) x 0.75 (height)
fit(crate, (0.8, 0.8, 0.8))
fit(table, (1.4, 0.8, 0.75), cut_x=True)
for o in (crate, table):
    export(o, OUTP + "\\" + o.name + ".gltf")
crate.location = (0, 40, 0); table.location = (2, 40, 0)
print([o.name for o in made + rmade], crate.dimensions, table.dimensions)
