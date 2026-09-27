# Helpers for building Master Blaster assets in Blender (run via exec in Blender MCP).
import bpy, bmesh, math, os, random
from mathutils import Vector, Matrix

TEX = r"C:\Dev\asset-cache\work\tex"
NAT = r"C:\Dev\asset-cache\nature\glTF"
VIL = r"C:\Dev\asset-cache\village\Medieval Village MegaKit[Standard]\glTF"
GAME = r"C:\Dev\master-blaster-game\.claude\worktrees\agent-ab1241e8dba017a59\game\assets"


def img(path, noncolor=False):
    name = os.path.basename(path)
    im = bpy.data.images.get(name)
    if im is None or im.filepath != path:
        im = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = 'Non-Color'
    return im


def pbr(name, base, normal=None, rough=None, rough_val=0.9, alpha=False, tint=None):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = img(base)
    if tint:
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        nt.links.new(t.outputs['Color'], mix.inputs[6])
        mix.inputs[7].default_value = (*tint, 1)
        nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])
    else:
        nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    if alpha:
        # glTF alpha-mask pattern: 1 - (alpha < 0.5) -> exported as alphaMode MASK, cutoff 0.5
        lt = nt.nodes.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'; lt.inputs[1].default_value = 0.5
        sub = nt.nodes.new('ShaderNodeMath'); sub.operation = 'SUBTRACT'; sub.inputs[0].default_value = 1.0
        nt.links.new(t.outputs['Alpha'], lt.inputs[0])
        nt.links.new(lt.outputs['Value'], sub.inputs[1])
        nt.links.new(sub.outputs['Value'], bsdf.inputs['Alpha'])
        m.blend_method = 'CLIP' if hasattr(m, 'blend_method') else None
        try:
            m.surface_render_method = 'DITHERED'
        except Exception:
            pass
        m.use_backface_culling = False
    if normal:
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = img(normal, True)
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    if rough:
        tr = nt.nodes.new('ShaderNodeTexImage'); tr.image = img(rough, True)
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(tr.outputs['Color'], sep.inputs['Color'])
        nt.links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
    else:
        bsdf.inputs['Roughness'].default_value = rough_val
    return m


def glow(name='M_Magitech', color=(0.373, 0.949, 0.902), strength=4.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    lin = tuple(((c + 0.055) / 1.055) ** 2.4 for c in color)
    bsdf.inputs['Base Color'].default_value = (*lin, 1)
    bsdf.inputs['Emission Color'].default_value = (*lin, 1)
    bsdf.inputs['Emission Strength'].default_value = strength
    bsdf.inputs['Roughness'].default_value = 0.3
    return m


def mats():
    return {
        'blocks': pbr('M_SandstoneBlocks', TEX + r"\T_SandstoneBlocks_BaseColor.png", TEX + r"\T_SandstoneBlocks_Normal.png", TEX + r"\T_SandstoneBlocks_Roughness.png"),
        'rubble': pbr('M_SandstoneRubble', TEX + r"\T_SandstoneRubble_BaseColor.png", TEX + r"\T_SandstoneRubble_Normal.png", TEX + r"\T_SandstoneRubble_Roughness.png"),
        'planks': pbr('M_Planks', TEX + r"\T_Planks_BaseColor.png", TEX + r"\T_Planks_Normal.png", TEX + r"\T_Planks_Roughness.png"),
        'glow': glow(),
    }


# ---------- mesh helpers (bmesh, Blender coords: Z up, -Y = glTF +Z) ----------

def add_box(bm, mn, mx, mat=0):
    x0, y0, z0 = mn; x1, y1, z1 = mx
    v = [bm.verts.new(p) for p in [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                   (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    out = []
    for f in faces:
        face = bm.faces.new([v[i] for i in f]); face.material_index = mat; out.append(face)
    return out


def add_prism(bm, pts2d, y0, y1, mat=0):
    """Extrude polygon given in XZ plane (counter-clockwise seen from -Y) between y0..y1."""
    front = [bm.verts.new((x, y0, z)) for x, z in pts2d]
    back = [bm.verts.new((x, y1, z)) for x, z in pts2d]
    fs = [bm.faces.new(front), bm.faces.new(list(reversed(back)))]
    n = len(pts2d)
    for i in range(n):
        j = (i + 1) % n
        fs.append(bm.faces.new([front[j], front[i], back[i], back[j]]))
    for f in fs:
        f.material_index = mat
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def add_cyl(bm, r0, r1, z0, z1, sides=16, cx=0, cy=0, mat=0, cap=True):
    b = [bm.verts.new((cx + r0 * math.cos(2 * math.pi * i / sides), cy + r0 * math.sin(2 * math.pi * i / sides), z0)) for i in range(sides)]
    t = [bm.verts.new((cx + r1 * math.cos(2 * math.pi * i / sides), cy + r1 * math.sin(2 * math.pi * i / sides), z1)) for i in range(sides)]
    fs = []
    for i in range(sides):
        j = (i + 1) % sides
        fs.append(bm.faces.new([b[i], b[j], t[j], t[i]]))
    if cap:
        fs.append(bm.faces.new(list(reversed(b))))
        fs.append(bm.faces.new(t))
    for f in fs:
        f.material_index = mat
    return fs, b, t


def box_uv(bm, tile=2.0, tiles=None):
    """Box projection by face normal. tiles: per material index tile size."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        s = (tiles or {}).get(f.material_index, tile)
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            co = l.vert.co
            if ax == 2:
                u, v = co.x, co.y * (1 if n.z > 0 else -1)
            elif ax == 0:
                u, v = co.y * (1 if n.x > 0 else -1), co.z
            else:
                u, v = co.x * (-1 if n.y > 0 else 1), co.z
            l[uv].uv = (u / s, v / s)


def cyl_uv(bm, faces, sides, circumference_tiles=1.0, tile=2.0):
    uv = bm.loops.layers.uv.verify()
    for f in faces:
        if abs(f.normal.z) > 0.9:
            continue
        for l in f.loops:
            a = math.atan2(l.vert.co.y, l.vert.co.x) % (2 * math.pi)
            u = a / (2 * math.pi) * circumference_tiles
            l[uv].uv = (u, l.vert.co.z / tile)
    # fix seam: faces spanning wrap
    for f in faces:
        if abs(f.normal.z) > 0.9:
            continue
        us = [l[uv].uv.x for l in f.loops]
        if max(us) - min(us) > circumference_tiles / 2:
            for l in f.loops:
                if l[uv].uv.x < circumference_tiles / 2:
                    l[uv].uv.x += circumference_tiles


def finish(name, bm, materials, coll, loc=(0, 0, 0), smooth=False):
    old = bpy.data.meshes.get(name)
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me); bm.free()
    for m in materials:
        me.materials.append(m)
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    coll.objects.link(ob)
    return ob


def bevel(bm, w=0.02):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=w, segments=1, affect='EDGES', clamp_overlap=True)


def orient_out(bm, mat):
    """Flip faces of material `mat` so they point away from the vertical axis of the object."""
    bm.normal_update()
    for f in bm.faces:
        if f.material_index == mat:
            c = f.calc_center_median()
            if f.normal.x * c.x + f.normal.y * c.y < 0:
                f.normal_flip()
    bm.normal_update()


def collection(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def export(obj_or_objs, path, texdir='textures', fmt='GLTF_SEPARATE', anim=False):
    objs = obj_or_objs if isinstance(obj_or_objs, (list, tuple)) else [obj_or_objs]
    for s in bpy.data.scenes:
        for vl in s.view_layers:
            for o in s.objects:
                o.select_set(False, view_layer=vl)
    saved = [(o, o.location.copy()) for o in objs]
    for o in objs:
        o.location = (0, 0, 0)
        o.select_set(True)
        for c in o.children_recursive:
            c.select_set(True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kw = dict(filepath=path, export_format=fmt, use_selection=True, export_yup=True,
              export_apply=True, export_animations=anim, export_image_format='AUTO',
              use_active_scene=True)
    if fmt == 'GLTF_SEPARATE':
        kw['export_texture_dir'] = texdir
    bpy.ops.export_scene.gltf(**kw)
    for o, l in saved:
        o.location = l
