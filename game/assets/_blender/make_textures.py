# Sandstone and plank textures for ruins/building, derived from Quaternius Medieval Village MegaKit (CC0).
# Run in Blender: exec(open(r"...\make_textures.py").read()). Writes 1K PNGs to C:\Dev\asset-cache\work\tex.
import bpy, numpy as np, os

SRC = r"C:\Dev\asset-cache\village\Medieval Village MegaKit[Standard]"
COLOR = SRC + r"\glTF"                                  # base color / roughness
NORMAL = SRC + r"\Textures\Normals Godot-Unity"         # OpenGL (+Y) normals; glTF folder ships DirectX ones
OUT = r"C:\Dev\asset-cache\work\tex"
os.makedirs(OUT, exist_ok=True)


def load(path, noncolor=False):
    im = bpy.data.images.load(path, check_existing=False)
    if noncolor:
        im.colorspace_settings.name = 'Non-Color'
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(im)
    return a


def save(a, name, noncolor=False, size=1024):
    h, w = a.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=False)
    if noncolor:
        im.colorspace_settings.name = 'Non-Color'
    im.pixels[:] = np.ascontiguousarray(a).ravel()
    im.scale(size, size)
    im.filepath_raw = os.path.join(OUT, name + '.png'); im.file_format = 'PNG'; im.save()
    bpy.data.images.remove(im)


def tint(a, hexcol, amt=0.8):
    """Keep the painted luminance, recolour to the palette tone (80 % tint, 20 % neutral)."""
    tgt = np.array([int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)], dtype=np.float32)
    lum = a[..., :3].mean(-1, keepdims=True)
    lumn = lum / lum.mean()
    out = a.copy()
    out[..., :3] = np.clip(lumn * tgt * amt + lumn * tgt.mean() * (1 - amt), 0, 1)
    return out


save(tint(load(COLOR + r"\T_Brick_BaseColor.png"), '#D2A46C'), 'T_SandstoneBlocks_BaseColor')
save(load(NORMAL + r"\T_Brick_Normal.png", True), 'T_SandstoneBlocks_Normal', True)
save(load(COLOR + r"\T_Brick_Roughness.png", True), 'T_SandstoneBlocks_Roughness', True)
save(tint(load(COLOR + r"\T_UnevenBrick_BaseColor.png"), '#C9955B'), 'T_SandstoneRubble_BaseColor')
save(load(NORMAL + r"\T_UnevenBrick_Normal.png", True), 'T_SandstoneRubble_Normal', True)
save(load(COLOR + r"\T_UnevenBrick_Roughness.png", True), 'T_SandstoneRubble_Roughness', True)
# Planks: the light plank band at the top of the wood trim sheet (rows 8..590 from the top of 2048)
for path, name, nc in ((COLOR + r"\T_WoodTrim_BaseColor.png", 'T_Planks_BaseColor', False),
                       (NORMAL + r"\T_WoodTrim_Normal.png", 'T_Planks_Normal', True),
                       (COLOR + r"\T_WoodTrim_Roughness.png", 'T_Planks_Roughness', True)):
    save(load(path, nc)[2048 - 590:2048 - 8], name, nc)
