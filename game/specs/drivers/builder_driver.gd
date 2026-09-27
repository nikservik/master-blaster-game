extends RefCounted

## Драйвер спек строительства: клавиши и мышь режима строительства, наведение прицела
## и чтение того, что видит игрок: призрак, поставленные детали и предметы.

const HeroDriver := preload("res://specs/drivers/hero_driver.gd")

## Сколько кадров драйвер доводит прицел до цели, как игрок — мышью.
const AIM_STEPS := 150
const AIM_TOLERANCE := 0.04
const PIXELS_PER_METER := 12.0

var _builder: Builder
var _hero: HeroDriver
var _tree: SceneTree


func _init(builder: Builder, hero: HeroDriver) -> void:
	_builder = builder
	_hero = hero
	_tree = builder.get_tree()


# --- Given ---------------------------------------------------------------

## Площадка без построек и предметов, режим строительства выключен, выбор сброшен.
func begin_empty() -> void:
	for child in _builder.buildings() + _builder.items():
		child.free()
	_builder.active = false
	_builder.slot = Builder.Slot.FOUNDATION
	_builder.size_index = 0
	_builder.quarter_turns = 0
	_builder.item_turn = 0.0
	await _hero.wait(2)


# --- When: клавиши и мышь ------------------------------------------------

func press_build_key() -> void:
	await _key(KEY_B)


func enter_build_mode() -> void:
	if not _builder.active:
		await press_build_key()


func choose_foundation() -> void:
	await _key(KEY_1)


func choose_floor() -> void:
	await _key(KEY_2)


func choose_wall() -> void:
	await _key(KEY_3)


func choose_door_wall() -> void:
	await _key(KEY_4)


func choose_stairs() -> void:
	await _key(KEY_5)


func choose_box() -> void:
	await _key(KEY_6)


func choose_table() -> void:
	await _key(KEY_7)


func next_size() -> void:
	await _key(KEY_TAB)


func rotate_part() -> void:
	await _key(KEY_R)


## Колесо мыши: положительные щелчки — от себя.
func turn_item(notches: int) -> void:
	for i in absi(notches):
		await _mouse_button(MOUSE_BUTTON_WHEEL_UP if notches > 0 else MOUSE_BUTTON_WHEEL_DOWN)


func place() -> void:
	await _mouse_button(MOUSE_BUTTON_LEFT)


func remove() -> void:
	await _mouse_button(MOUSE_BUTTON_RIGHT)


## Двигает мышь, пока точка в центре экрана не окажется на цели, — как игрок наводит прицел.
func aim_at(target: Vector3) -> void:
	for i in AIM_STEPS:
		await _hero.wait(1)
		var hero_at := _hero.position()
		var to_target := Vector3(target.x - hero_at.x, 0.0, target.z - hero_at.z)
		var yaw_error := _hero.camera_forward_flat().signed_angle_to(to_target.normalized(), Vector3.UP)
		var aim: Variant = _builder.aim_point()
		var distance_error := 1.0
		if aim != null:
			var aim_at_point: Vector3 = aim
			if aim_at_point.distance_to(target) < AIM_TOLERANCE:
				return
			distance_error = Vector2(aim_at_point.x - hero_at.x, aim_at_point.z - hero_at.z).length() - to_target.length()
		var motion := InputEventMouseMotion.new()
		var step := Vector2(-yaw_error / CameraRig.MOUSE_SENSITIVITY, clampf(distance_error * PIXELS_PER_METER * _pitch_gain(to_target.length()), -60.0, 60.0))
		motion.relative = step
		motion.screen_relative = step
		_builder.get_viewport().push_input(motion)
	push_error("прицел не дошёл до %s, точка под прицелом %s" % [target, _builder.aim_point()])


## Вдали дальность прицела резко меняется от наклона камеры: шаг мыши уменьшается с расстоянием.
func _pitch_gain(distance: float) -> float:
	return clampf(16.0 / (distance * distance), 0.05, 1.0)


# --- Then ----------------------------------------------------------------

func is_in_build_mode() -> bool:
	return _builder.active


func ghost_visible() -> bool:
	return _builder.is_ghost_visible()


func ghost_green() -> bool:
	return _builder.is_ghost_green()


func ghost_yaw() -> float:
	var forward := -_builder.ghost_transform().basis.z
	return atan2(-forward.x, -forward.z)


## Размер призрака по его осям: x — длина, z — ширина, y — высота.
func ghost_size() -> Vector3:
	var total := AABB()
	var first := true
	for child in _ghost_meshes():
		var box := child.transform * child.get_aabb()
		total = box if first else total.merge(box)
		first = false
	return total.size


func building_count() -> int:
	return _builder.buildings().size()


## Детали постройки: вид, габарит в сетке постройки, центр и поворот в мире.
func parts(building := 0) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var b: Building = _builder.buildings()[building]
	for part in b.parts():
		var forward := -part.global_basis.z
		result.append({
			"kind": BuildPart.Kind.keys()[part.kind].to_lower(),
			"grid": b.bounds_of(part),
			"center": part.global_position,
			"yaw": atan2(-forward.x, -forward.z),
		})
	return result


func part_count(kind: String) -> int:
	var count := 0
	for b in _builder.buildings().size():
		for p in parts(b):
			if p.kind == kind:
				count += 1
	return count


## Мировая точка по координатам сетки постройки.
func grid_point(local: Vector3, building := 0) -> Vector3:
	return _builder.buildings()[building].to_global(local)


func building_yaw(building := 0) -> float:
	var forward := -_builder.buildings()[building].global_basis.z
	return atan2(-forward.x, -forward.z)


func items() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for item in _builder.items():
		var forward := -item.global_basis.z
		result.append({
			"kind": BuildItem.Kind.keys()[item.kind].to_lower(),
			"position": item.global_position,
			"yaw": atan2(-forward.x, -forward.z),
		})
	return result


func _ghost_meshes() -> Array[MeshInstance3D]:
	var result: Array[MeshInstance3D] = []
	var ghost := _builder.get_children().filter(func(c): return (c is BuildPart or c is BuildItem) and c.visible and c.collision_layer == 0)
	if not ghost.is_empty():
		for child in (ghost[0] as Node).get_children():
			if child is MeshInstance3D:
				result.append(child)
	return result


func _key(code: Key) -> void:
	var press := InputEventKey.new()
	press.physical_keycode = code
	press.keycode = code
	press.pressed = true
	_builder.get_viewport().push_input(press)
	var release := press.duplicate() as InputEventKey
	release.pressed = false
	_builder.get_viewport().push_input(release)
	await _hero.wait(2)


func _mouse_button(button: MouseButton) -> void:
	var press := InputEventMouseButton.new()
	press.button_index = button
	press.pressed = true
	_builder.get_viewport().push_input(press)
	var release := press.duplicate() as InputEventMouseButton
	release.pressed = false
	_builder.get_viewport().push_input(release)
	await _hero.wait(2)
