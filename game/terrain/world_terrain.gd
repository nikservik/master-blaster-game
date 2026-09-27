class_name WorldTerrain
extends VoxelLodTerrain

## Гладкий воксельный рельеф мира ([TER]): генератор, материал по вокселям, копание и насыпание,
## сохранение изменённых блоков в SQLite при выходе и раз в минуту.

## Грунт, который видит игрок.
enum Ground { GRASS, STONE, DIRT }

## Индекс текстуры в канале INDICES. SURFACE — поверхность, как её создал генератор:
## трава на пологом, камень на крутом. STONE — камень независимо от уклона, DIRT — тронутый героем грунт.
const INDEX_SURFACE := 0
const INDEX_STONE := 1
const INDEX_DIRT := 2

## Трава — где нормаль поверхности SURFACE круче этого значения вверх; шейдер смешивает в полосе ±GRASS_BLEND.
const GRASS_MIN_NORMAL_Y := 0.78
const GRASS_BLEND := 0.07

## Участок 1 × 1 км. Низ — чуть ниже нижней границы мира (Hero.FALL_LIMIT_Y = −10 м):
## кто прокопался до дна, падает ниже границы и возвращается на старт.
const BOUNDS := AABB(Vector3(-512, -16, -512), Vector3(1024, 160, 1024))

## Высота верха пола руин; рельеф под руинами на 0,1 м ниже — герой переходит с пола на грунт.
const RUINS_FLOOR_Y := 40.0
const FLAT_Y := RUINS_FLOOR_Y - 0.1
## Ровная площадка под руинами и полем: прямоугольник с центром (x, z) и полуразмерами, с запасом.
const FLAT_CENTER := Vector2(16.0, 0.0)
const FLAT_HALF := Vector2(32.0, 24.0)
## Ширина перехода от ровной площадки к холмам.
const FLAT_BLEND := 24.0
## Обрыв: вдоль z = CLIFF_Z рельеф поднимается на CLIFF_HEIGHT м. Объёмный шум сдвигает линию обрыва
## до ±CLIFF_WARP м — так получаются нависания.
const CLIFF_Z := -70.0
const CLIFF_HEIGHT := 25.0
const CLIFF_WARP := 8.0
## Пол и стены пещер — камень: грунт глубже высоты по карте больше чем на CAVE_DEPTH
## или с твёрдым грунтом на одной из высот COVER_HEIGHTS над ним — под навесом.
const CAVE_DEPTH := 2.5
const COVER_HEIGHTS: Array[float] = [3.0, 6.0, 9.0]

const BRUSH_RADIUS := 1.5
## Грунт в этом радиусе вокруг шара становится землёй: стенки ямы и насыпь.
const DIRT_RADIUS := BRUSH_RADIUS + 1.0
const AUTOSAVE_SECONDS := 60.0

## Файл хранилища правок. Задаётся до добавления в дерево; спеки пишут во временный каталог.
@export var save_path := "user://terrain.sqlite"

## Последнее запущенное сохранение: запись идёт в потоках, это его отметка готовности.
var last_save: VoxelSaveCompletionTracker

var _tool: VoxelToolLodTerrain
var _autosave: Timer


## Участок и его устройство целиком задаются здесь: новый WorldTerrain — тот же мир.
func _init() -> void:
	voxel_bounds = BOUNDS
	view_distance = int(BOUNDS.size.x)
	lod_count = 6
	lod_distance = 48.0
	generate_collisions = true
	collision_layer = 1
	var voxel_format := VoxelFormat.new()
	voxel_format.set_channel_depth(VoxelBuffer.CHANNEL_INDICES, VoxelBuffer.DEPTH_8_BIT)
	format = voxel_format
	generator = make_generator()
	var mesher_transvoxel := VoxelMesherTransvoxel.new()
	mesher_transvoxel.texturing_mode = VoxelMesherTransvoxel.TEXTURES_SINGLE_S4
	mesher = mesher_transvoxel
	material = _make_material()


func _ready() -> void:
	var sqlite := VoxelStreamSQLite.new()
	sqlite.database_path = ProjectSettings.globalize_path(save_path)
	stream = sqlite
	_tool = get_voxel_tool()
	_tool.channel = VoxelBuffer.CHANNEL_SDF

	_autosave = Timer.new()
	_autosave.name = "Autosave"
	_autosave.wait_time = AUTOSAVE_SECONDS
	_autosave.autostart = true
	_autosave.timeout.connect(save)
	add_child(_autosave)


func _enter_tree() -> void:
	# Окно закрывается только после записи правок на диск.
	get_tree().auto_accept_quit = false


func _exit_tree() -> void:
	save()
	get_tree().auto_accept_quit = true


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_save_and_quit()


## Записать изменённые блоки в хранилище. Запись асинхронная; готовность — last_save.is_complete().
func save() -> VoxelSaveCompletionTracker:
	last_save = save_modified_blocks()
	return last_save


func _save_and_quit() -> void:
	var tracker := save()
	while not tracker.is_complete() and not tracker.is_aborted():
		await get_tree().process_frame
	get_tree().quit()


# --- Правка --------------------------------------------------------------

## Убрать шар грунта; стенки ямы становятся землёй.
func dig(center: Vector3) -> void:
	_tool.mode = VoxelTool.MODE_REMOVE
	_tool.do_sphere(center, BRUSH_RADIUS)
	_paint_dirt(center)


## Насыпать шар грунта; насыпь — земля.
func fill(center: Vector3) -> void:
	_tool.mode = VoxelTool.MODE_ADD
	_tool.do_sphere(center, BRUSH_RADIUS)
	_paint_dirt(center)


func _paint_dirt(center: Vector3) -> void:
	_tool.channel = VoxelBuffer.CHANNEL_INDICES
	_tool.mode = VoxelTool.MODE_SET
	_tool.value = INDEX_DIRT
	_tool.do_sphere(center, DIRT_RADIUS)
	_tool.channel = VoxelBuffer.CHANNEL_SDF


# --- Наблюдаемое состояние -----------------------------------------------

## Твёрдый ли грунт в точке. Точка должна быть в загруженной области.
func is_solid(point: Vector3) -> bool:
	return _tool.get_voxel_f_interpolated(point) < 0.0


## Грунт поверхности в точке с нормалью: так же красит шейдер.
func ground_at(point: Vector3, normal: Vector3) -> Ground:
	_tool.channel = VoxelBuffer.CHANNEL_INDICES
	var index := _tool.get_voxel(Vector3i((point - normal * 0.5).round()))
	_tool.channel = VoxelBuffer.CHANNEL_SDF
	return ground_of(index, normal)


## Грунт по индексу текстуры вокселя и нормали поверхности — правило шейдера рельефа.
static func ground_of(index: int, normal: Vector3) -> Ground:
	if index == INDEX_DIRT:
		return Ground.DIRT
	if index == INDEX_STONE or normal.y < GRASS_MIN_NORMAL_Y:
		return Ground.STONE
	return Ground.GRASS


## Готова ли область вокруг точки: данные загружены, сетка и коллизия построены.
func is_ready_around(point: Vector3, radius: float) -> bool:
	var box := AABB(point - Vector3.ONE * radius, Vector3.ONE * radius * 2.0)
	return _tool.is_area_editable(box) and is_area_meshed(box, 0)


# --- Генератор -----------------------------------------------------------

## Граф генератора: холмы, ровная площадка под руинами, обрыв с нависаниями.
## Высоту по карте считает одно выражение; из неё — расстояние до поверхности и материал.
static func make_generator() -> VoxelGeneratorGraph:
	var gen := VoxelGeneratorGraph.new()
	gen.texture_mode = VoxelGeneratorGraph.TEXTURE_MODE_SINGLE
	var g: VoxelGraphFunction = gen.get_main_function()
	var x := g.create_node(VoxelGraphFunction.NODE_INPUT_X, Vector2())
	var y := g.create_node(VoxelGraphFunction.NODE_INPUT_Y, Vector2())
	var z := g.create_node(VoxelGraphFunction.NODE_INPUT_Z, Vector2())

	var hills_noise := FastNoiseLite.new()
	hills_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	hills_noise.frequency = 0.004
	hills_noise.fractal_octaves = 4
	var hills := g.create_node(VoxelGraphFunction.NODE_NOISE_2D, Vector2())
	g.set_node_param_by_name(hills, "noise", hills_noise)
	g.add_connection(x, 0, hills, 0)
	g.add_connection(z, 0, hills, 1)

	var warp_noise := FastNoiseLite.new()
	warp_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	warp_noise.frequency = 0.05
	warp_noise.fractal_octaves = 2

	# Высота по карте: холмы ±30 м вокруг уровня руин и ступень обрыва; у руин — ровно.
	# Доля холмов: 0 на площадке руин, 1 дальше FLAT_BLEND от неё.
	var dx := "max(abs(x - %s) - %s, 0.0)" % [_num(FLAT_CENTER.x), _num(FLAT_HALF.x)]
	var dz := "max(abs(z - %s) - %s, 0.0)" % [_num(FLAT_CENTER.y), _num(FLAT_HALF.y)]
	var hills_share := _expression(g, "clamp(sqrt(%s * %s + %s * %s) / %s, 0.0, 1.0)" % [dx, dx, dz, dz, _num(FLAT_BLEND)],
		["x", "z"], [x, z])
	var natural := "(%s + hills * 30.0 + %s)" % [_num(RUINS_FLOOR_Y), _cliff("z")]
	var height := _expression(g, "%s + (%s - %s) * w * w * (3.0 - 2.0 * w)" % [_num(FLAT_Y), natural, _num(FLAT_Y)],
		["z", "hills", "w"], [z, hills, hills_share])
	var sdf := _sdf(g, warp_noise, x, y, z, height)
	var out := g.create_node(VoxelGraphFunction.NODE_OUTPUT_SDF, Vector2())
	g.add_connection(sdf, 0, out, 0)

	# Камень — пол и стены пещер: глубоко под высотой по карте или под навесом, твёрдым на одной из высот
	# COVER_HEIGHTS над точкой. Признак «a < 0» в выражении — clamp(floor(0 - a) + 1, 0, 1):
	# сравнений выражения не знают.
	var stone := _expression(g, "clamp(floor(h - %s - y) + 1.0, 0.0, 1.0)" % _num(CAVE_DEPTH), ["y", "h"], [y, height])
	for cover in COVER_HEIGHTS:
		var y_above := _expression(g, "y + %s" % _num(cover), ["y"], [y])
		var sdf_above := _sdf(g, warp_noise, x, y_above, z, height)
		stone = _expression(g, "max(s, clamp(floor(0.0 - a) + 1.0, 0.0, 1.0))", ["s", "a"], [stone, sdf_above])
	var texture := _expression(g, "s * %s" % _num(INDEX_STONE), ["s"], [stone])
	var texture_out := g.create_node(VoxelGraphFunction.NODE_OUTPUT_SINGLE_TEXTURE, Vector2())
	g.add_connection(texture, 0, texture_out, 0)

	var result: Dictionary = gen.compile()
	assert(result.get("success", false), "генератор рельефа не собрался: %s" % result)
	return gen


## Расстояние до поверхности в точке (x, y, z) графа. Нависания: линия обрыва сдвигается объёмным шумом,
## поэтому на разной высоте стена выступает по-разному. Обрыв далеко от руин, там доля холмов равна 1.
static func _sdf(g: VoxelGraphFunction, noise: FastNoiseLite, x: int, y: int, z: int, height: int) -> int:
	var warp := g.create_node(VoxelGraphFunction.NODE_NOISE_3D, Vector2())
	g.set_node_param_by_name(warp, "noise", noise)
	g.add_connection(x, 0, warp, 0)
	g.add_connection(y, 0, warp, 1)
	g.add_connection(z, 0, warp, 2)
	var overhang := "(%s - %s)" % [_cliff("z + n * %s" % _num(CLIFF_WARP)), _cliff("z")]
	return _expression(g, "y - h - " + overhang, ["y", "z", "h", "n"], [y, z, height, warp])


## Ступень обрыва в выражении графа: 0 со стороны +Z, CLIFF_HEIGHT за линией CLIFF_Z.
static func _cliff(z_term: String) -> String:
	return "clamp((%s - (%s)) / 2.0, 0.0, 1.0) * %s" % [_num(CLIFF_Z), z_term, _num(CLIFF_HEIGHT)]


## Число для выражения графа: отрицательных литералов выражения не понимают.
static func _num(v: float) -> String:
	return "%.2f" % v if v >= 0.0 else "(0.0 - %.2f)" % -v


static func _expression(g: VoxelGraphFunction, text: String, names: Array[String], inputs: Array[int]) -> int:
	var node := g.create_node(VoxelGraphFunction.NODE_EXPRESSION, Vector2())
	g.set_node_param_by_name(node, "expression", text)
	g.set_expression_node_inputs(node, PackedStringArray(names))
	for i in inputs.size():
		g.add_connection(inputs[i], 0, node, i)
	return node


# --- Материал ------------------------------------------------------------

## Временные цвета из палитры арт-направления; позже их заменят текстуры из ассетов.
func _make_material() -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://terrain/terrain.gdshader")
	mat.set_shader_parameter("grass_tex", _noise_texture(Color("5E7D3A"), Color("7FA650"), 0.08))
	mat.set_shader_parameter("stone_tex", _noise_texture(Color("A9784A"), Color("C9955B"), 0.05))
	mat.set_shader_parameter("dirt_tex", _noise_texture(Color("5C4030"), Color("7A5A3C"), 0.12))
	mat.set_shader_parameter("grass_min_normal_y", GRASS_MIN_NORMAL_Y)
	mat.set_shader_parameter("grass_blend", GRASS_BLEND)
	return mat


static func _noise_texture(dark: Color, light: Color, freq: float) -> NoiseTexture2D:
	var noise := FastNoiseLite.new()
	noise.frequency = freq
	noise.fractal_octaves = 5
	var ramp := Gradient.new()
	ramp.set_color(0, dark)
	ramp.set_color(1, light)
	var tex := NoiseTexture2D.new()
	tex.width = 256
	tex.height = 256
	tex.seamless = true
	tex.noise = noise
	tex.color_ramp = ramp
	tex.generate_mipmaps = true
	return tex
