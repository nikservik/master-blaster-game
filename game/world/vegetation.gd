class_name Vegetation
extends VoxelInstancer

## Растения и камни по рельефу: VoxelInstancer рассыпает их по сетке рельефа по плотности, уклону и высоте.
## Ровный грунт под руинами и полем (WorldTerrain.FLAT_Y) пропускается: растения проросли бы сквозь пол.
## Выкопанное и насыпанное (земля) не зарастает — фильтр по индексу текстуры вокселя.

## Полоса высот вокруг ровного грунта руин, где ничего не растёт.
const FLAT_GAP := 0.4
## Высоко над руинами — сухие охристые плато.
const PLATEAU_Y := 58.0

## Вид растения или камня: путь к модели, уровень детализации рельефа, плотность на м², масштаб,
## допустимый уклон в градусах, высоты и доля пятнами по шуму (0 — сплошь).
const KINDS := [
	["vegetation/palm_1", 1, 0.006, 0.8, 1.3, 0.0, 22.0, WorldTerrain.SEA_Y + 0.8, 50.0, 0.3],
	["vegetation/palm_2", 1, 0.006, 0.8, 1.2, 0.0, 22.0, WorldTerrain.SEA_Y + 0.8, 50.0, 0.3],
	["vegetation/palm_3", 1, 0.006, 0.8, 1.2, 0.0, 22.0, WorldTerrain.SEA_Y + 0.8, 50.0, 0.3],
	["vegetation/bush", 1, 0.03, 0.7, 1.3, 0.0, 30.0, WorldTerrain.SAND_TOP, PLATEAU_Y, 0.2],
	["vegetation/bush_flowers", 1, 0.006, 0.7, 1.2, 0.0, 30.0, WorldTerrain.SAND_TOP, PLATEAU_Y, 0.3],
	["vegetation/plant_big", 1, 0.01, 0.8, 1.4, 0.0, 30.0, WorldTerrain.SAND_TOP, PLATEAU_Y, 0.2],
	["vegetation/fern", 0, 0.04, 0.6, 1.1, 0.0, 30.0, WorldTerrain.SAND_TOP, PLATEAU_Y, 0.1],
	["vegetation/grass_tall", 0, 0.08, 0.6, 1.0, 0.0, 28.0, WorldTerrain.SAND_TOP, PLATEAU_Y, 0.0],
	["vegetation/grass_wispy_short", 0, 0.12, 0.8, 1.2, 0.0, 28.0, WorldTerrain.SAND_TOP - 0.6, PLATEAU_Y + 10.0, 0.0],
	["rocks/rock_1", 2, 0.004, 0.5, 1.5, 18.0, 70.0, 0.0, PLATEAU_Y, 0.0],
	["rocks/rock_2", 2, 0.004, 0.5, 1.5, 18.0, 70.0, 0.0, PLATEAU_Y, 0.0],
	["rocks/rock_desert_1", 2, 0.006, 0.6, 1.8, 0.0, 70.0, PLATEAU_Y - 4.0, 200.0, 0.0],
	["rocks/rock_desert_2", 2, 0.006, 0.6, 1.8, 0.0, 70.0, PLATEAU_Y - 4.0, 200.0, 0.0],
	["rocks/pebble_round_1", 0, 0.03, 0.6, 1.4, 0.0, 20.0, WorldTerrain.SEA_Y - 3.0, WorldTerrain.SAND_TOP + 1.0, 0.0],
]


func _init() -> void:
	var lib := VoxelInstanceLibrary.new()
	var id := 0
	for kind: Array in KINDS:
		var mesh := _mesh_of(kind[0])
		# Два диапазона высот: ниже и выше ровного грунта руин.
		for range_y in [Vector2(kind[7], WorldTerrain.FLAT_Y - FLAT_GAP), Vector2(WorldTerrain.FLAT_Y + FLAT_GAP, kind[8])]:
			if range_y.x >= range_y.y:
				continue
			var item := VoxelInstanceLibraryMultiMeshItem.new()
			item.set_mesh(mesh, 0)
			item.lod_index = kind[1]
			item.cast_shadow = RenderingServer.SHADOW_CASTING_SETTING_ON
			item.generator = _generator(kind, range_y)
			lib.add_item(id, item)
			id += 1
	library = lib


func _mesh_of(path: String) -> Mesh:
	var node := (load("res://assets/%s.gltf" % path) as PackedScene).instantiate()
	var mesh := (node.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D).mesh
	node.free()
	return mesh


func _generator(kind: Array, range_y: Vector2) -> VoxelInstanceGenerator:
	var gen := VoxelInstanceGenerator.new()
	gen.density = kind[2]
	gen.min_scale = kind[3]
	gen.max_scale = kind[4]
	gen.min_slope_degrees = kind[5]
	gen.max_slope_degrees = kind[6]
	gen.min_height = range_y.x
	gen.max_height = range_y.y
	gen.random_rotation = true
	gen.vertical_alignment = 0.0 if String(kind[0]).begins_with("vegetation/palm") else 0.6
	gen.offset_along_normal = -0.1
	gen.voxel_texture_filter_enabled = true
	gen.voxel_texture_filter_array = PackedInt32Array([WorldTerrain.INDEX_SURFACE, WorldTerrain.INDEX_STONE])
	if kind[9] > 0.0:
		var noise := FastNoiseLite.new()
		noise.frequency = 0.03
		gen.noise = noise
		gen.noise_threshold = kind[9] - 0.5
	return gen
