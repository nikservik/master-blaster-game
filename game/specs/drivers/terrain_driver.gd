extends RefCounted

## Драйвер спек рельефа: ставит героя на грунт, наводит прицел мышью, копает и насыпает кнопками мыши,
## выходит из игры или обрывает её и запускает снова на том же хранилище. Читает то, что видит игрок:
## форму рельефа, грунт поверхности, твёрдость грунта в точке.
## Время игры — кадры: прогон идёт с --fixed-fps 60. Сетку, коллизию и запись рельеф делает в потоках
## в настоящем времени, поэтому их драйвер ждёт по часам, пока потоки godot_voxel не опустеют.

const HeroDriver := preload("res://specs/drivers/hero_driver.gd")

const AIM_STEPS := 120
const AIM_TOLERANCE := 0.15
## Доля угловой ошибки прицела, которую драйвер исправляет мышью за кадр.
const AIM_GAIN := 0.7
## Предел ожидания потоков godot_voxel по часам.
const WAIT_LIMIT_MS := 10000
## Сколько загружает перезапущенный рельеф вокруг проверяемой точки: на чтение правок хватает.
const RELAUNCH_VIEW_DISTANCE := 64

var terrain: WorldTerrain
var _world: Node3D
var _hero: Hero
var _hero_driver: HeroDriver
var _digger: Digger
var _tree: SceneTree
var _relaunched: WorldTerrain
var _world_parent: Node
## Хранилище, с которым стартует следующий запуск.
var _launch_path := ""


func _init(world: Node3D, hero_driver: HeroDriver) -> void:
	_world = world
	terrain = world.get_node("Terrain") as WorldTerrain
	_hero = world.get_node("Ruins/Hero") as Hero
	_digger = world.get_node("Digger") as Digger
	_hero_driver = hero_driver
	_tree = world.get_tree()


# --- Given ---------------------------------------------------------------

## Дождаться, пока рельеф вокруг героя построен.
func wait_until_ready() -> void:
	var at := _hero.global_position
	await _until(func() -> bool: return terrain.is_ready_around(at, 16.0) and _voxel_idle(), "рельеф у %s" % at)


## Поставить героя на нетронутый грунт в (x, z): верхний или первый ниже высоты below.
## Пока рельеф там не построен, герой удерживается на месте.
func stand_on_ground(x: float, z: float, below := INF) -> Vector3:
	var spot := Vector3(x, generated_surface_y(x, z, below) + 0.05, z)
	await _until(func() -> bool: return terrain.is_ready_around(spot, 8.0) and _voxel_idle(),
		"рельеф у %s" % spot, _hold.bind(spot))
	_hold(spot)
	await _hero_driver.wait(10)
	return _hero.global_position


## Выкопать яму сразу, без прицела: подготовка сценария.
func dug_pit(point: Vector3) -> void:
	await _until(func() -> bool: return terrain.is_ready_around(point, 4.0), "рельеф у %s" % point)
	terrain.dig(point)
	await settle()


## Шахта от поверхности до дна мира под точкой (x, z).
func dug_shaft(x: float, z: float) -> void:
	var y := generated_surface_y(x, z)
	while y > WorldTerrain.BOUNDS.position.y:
		terrain.dig(Vector3(x, y, z))
		y -= WorldTerrain.BRUSH_RADIUS
	await settle()


# --- When ----------------------------------------------------------------

## Двигать мышь, пока точка под прицелом не окажется на цели, — как игрок.
func aim_at(target: Vector3) -> void:
	for i in AIM_STEPS:
		await _hero_driver.wait(1)
		var ray := _digger.aim_ray()
		var from: Vector3 = ray[0]
		var dir: Vector3 = ray[1]
		var point: Variant = crosshair_point()
		if point != null and (point as Vector3).distance_to(target) < AIM_TOLERANCE:
			return
		var want := (target - from).normalized()
		var yaw_error := Vector3(dir.x, 0, dir.z).signed_angle_to(Vector3(want.x, 0, want.z), Vector3.UP)
		var pitch_error := asin(clampf(want.y, -1, 1)) - asin(clampf(dir.y, -1, 1))
		var step := -Vector2(yaw_error, pitch_error) * AIM_GAIN / CameraRig.MOUSE_SENSITIVITY
		var motion := InputEventMouseMotion.new()
		motion.relative = step
		motion.screen_relative = step
		_hero.get_viewport().push_input(motion)
	push_error("прицел не дошёл до %s, точка под прицелом %s" % [target, crosshair_point()])


## Щелчок левой кнопкой мыши.
func click_left() -> void:
	await _click(MOUSE_BUTTON_LEFT)


## Щелчок правой кнопкой мыши.
func click_right() -> void:
	await _click(MOUSE_BUTTON_RIGHT)


## Прошла минута игры: минутный таймер срабатывает и заводится на следующую минуту, как сам Timer;
## запись доходит до диска.
func a_minute_passes() -> void:
	var timer := terrain.get_node("Autosave") as Timer
	timer.timeout.emit()
	timer.start()
	await _wait_saved()


## Игрок выходит из игры: мир уходит со сцены и записывает правки.
func quit_game() -> void:
	_world_parent = _world.get_parent()
	_world_parent.remove_child(_world)
	await _wait_saved()
	_launch_path = terrain.save_path


## Мир снова на сцене после quit_game(): горячий стенд для следующих спек.
func restore_world() -> void:
	_world_parent.add_child(_world)
	_world_parent = null
	await wait_until_ready()


## Игра оборвалась сейчас: следующий запуск видит хранилище таким, какое оно на диске в этот миг.
## Мир горячего стенда продолжает работать с исходным файлом, запуск — с его копией.
func crash_now() -> void:
	var store := terrain.save_path.get_base_dir()
	var copy := store.path_join("crash")
	DirAccess.make_dir_recursive_absolute(copy)
	var name := terrain.save_path.get_file()
	for suffix in ["", "-wal", "-shm", "-journal"]:
		if FileAccess.file_exists(store.path_join(name + suffix)):
			DirAccess.copy_absolute(store.path_join(name + suffix), copy.path_join(name + suffix))
		else:
			DirAccess.remove_absolute(copy.path_join(name + suffix))
	_launch_path = copy.path_join(name)


## Следующий запуск игры: новый рельеф на хранилище после выхода или обрыва, загруженный вокруг точки.
func launch_again(around: Vector3) -> void:
	_relaunched = WorldTerrain.new()
	_relaunched.save_path = _launch_path
	_relaunched.view_distance = RELAUNCH_VIEW_DISTANCE
	var viewer := VoxelViewer.new()
	viewer.view_distance = RELAUNCH_VIEW_DISTANCE
	_relaunched.add_child(viewer)
	viewer.position = around
	var parent: Node = _world_parent if _world_parent != null else _world.get_parent()
	parent.add_child(_relaunched)
	await _until(func() -> bool: return _relaunched.is_ready_around(around, 4.0) and _voxel_idle(),
		"перезапущенный рельеф у %s" % around)


func close_relaunched() -> void:
	_relaunched.free()
	_relaunched = null


# --- Then ----------------------------------------------------------------

## Точка под прицелом: первое, во что упирается луч из центра экрана; null — луч ушёл в небо.
func crosshair_point() -> Variant:
	var ray := _digger.aim_ray()
	var from: Vector3 = ray[0]
	var hit := _ray(from, from + (ray[1] as Vector3) * 50.0)
	return null if hit.is_empty() else hit.position


func is_solid(point: Vector3) -> bool:
	return terrain.is_solid(point)


func is_solid_after_relaunch(point: Vector3) -> bool:
	return _relaunched.is_solid(point)


func ground_after_relaunch(point: Vector3) -> WorldTerrain.Ground:
	return _relaunched.ground_at(point, Vector3.UP)


## Грунт поверхности, в которую упирается луч; -1 — луч попал не в рельеф.
func ground_hit_by(from: Vector3, to: Vector3) -> int:
	var hit := _ray(from, to)
	if hit.is_empty() or hit.collider != terrain:
		return -1
	return terrain.ground_at(hit.position, hit.normal)


## Поверхность, в которую упирается луч: {position, normal, collider}; пусто — ни во что.
func surface_hit_by(from: Vector3, to: Vector3) -> Dictionary:
	return _ray(from, to)


## Высота поверхности рельефа в (x, z) по лучу сверху; NAN — рельефа там нет.
func surface_y(x: float, z: float) -> float:
	var top := WorldTerrain.BOUNDS.end.y
	var hit := _ray(Vector3(x, top, z), Vector3(x, WorldTerrain.BOUNDS.position.y, z))
	return NAN if hit.is_empty() or hit.collider != terrain else float(hit.position.y)


func world_size() -> Vector3:
	return WorldTerrain.BOUNDS.size


## Столбец рельефа, каким его создал мир, снизу вверх с шагом 1 м: true — грунт.
func generated_column(x: float, z: float) -> Array[bool]:
	var sdf := _generated_sdf(x, z)
	var result: Array[bool] = []
	for s in sdf:
		result.append(s < 0.0)
	return result


## Высота поверхности нетронутого рельефа в (x, z): верхней или первой ниже высоты below.
func generated_surface_y(x: float, z: float, below := INF) -> float:
	var sdf := _generated_sdf(x, z)
	var top := sdf.size() - 2
	if below != INF:
		top = mini(top, floori(below - WorldTerrain.BOUNDS.position.y))
	for i in range(top, -1, -1):
		if sdf[i] < 0.0 and sdf[i + 1] >= 0.0:
			return WorldTerrain.BOUNDS.position.y + i + sdf[i] / (sdf[i] - sdf[i + 1])
	return NAN


# --- Внутреннее ----------------------------------------------------------

## Дождаться, пока правки рельефа дойдут до сетки и коллизии.
func settle() -> void:
	await _until(_voxel_idle, "потоки godot_voxel")
	await _tree.physics_frame


## Ждать кадр за кадром, пока check() не вернёт true; each_frame — что делать перед каждым кадром.
func _until(check: Callable, what: String, each_frame := Callable()) -> void:
	var deadline := Time.get_ticks_msec() + WAIT_LIMIT_MS
	while true:
		if each_frame.is_valid():
			each_frame.call()
		await _tree.process_frame
		if check.call():
			return
		if Time.get_ticks_msec() > deadline:
			push_error("не дождался: " + what)
			return


func _wait_saved() -> void:
	await _until(func() -> bool: return terrain.last_save.is_complete(), "запись правок рельефа")


## Потоки godot_voxel простаивают: генерация, сетки, загрузка и запись закончены.
func _voxel_idle() -> bool:
	var tasks: Dictionary = VoxelEngine.get_stats().tasks
	for key in tasks:
		if int(tasks[key]) > 0:
			return false
	return true


func _generated_sdf(x: float, z: float) -> PackedFloat32Array:
	var bounds := WorldTerrain.BOUNDS
	var buffer := VoxelBuffer.new()
	buffer.create(1, int(bounds.size.y), 1)
	buffer.set_channel_depth(VoxelBuffer.CHANNEL_INDICES, VoxelBuffer.DEPTH_8_BIT)
	terrain.generator.generate_block(buffer, Vector3i(roundi(x), int(bounds.position.y), roundi(z)), 0)
	var result := PackedFloat32Array()
	for i in int(bounds.size.y):
		result.append(buffer.get_voxel_f(0, i, 0, VoxelBuffer.CHANNEL_SDF))
	return result


func _hold(spot: Vector3) -> void:
	_hero.global_position = spot
	_hero.velocity = Vector3.ZERO
	_hero.reset_physics_interpolation()


func _ray(from: Vector3, to: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(from, to, 1)
	return _hero.get_world_3d().direct_space_state.intersect_ray(query)


func _click(button: MouseButton) -> void:
	var press := InputEventMouseButton.new()
	press.button_index = button
	press.pressed = true
	_hero.get_viewport().push_input(press)
	var release := press.duplicate() as InputEventMouseButton
	release.pressed = false
	_hero.get_viewport().push_input(release)
	await _hero_driver.wait(2)
	await settle()


# --- Берег ---------------------------------------------------------------

## Уровень моря.
func sea_y() -> float:
	return WorldTerrain.SEA_Y


## Сколько растений и камней рассыпано по рельефу вокруг героя.
func plants_count() -> int:
	var vegetation := _world.get_node("Terrain/Vegetation") as VoxelInstancer
	var total := 0
	for count: int in vegetation.debug_get_instance_counts().values():
		total += count
	return total


## Модули руин над бухтой: имя → положение.
func ruin_modules() -> Dictionary:
	var result := {}
	for module: Node3D in _world.get_node("Decor").get_children():
		if module.scene_file_path.contains("/ruins/"):
			result[module.name] = module.global_position
	return result
