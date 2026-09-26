extends RefCounted

## Драйвер спек: переводит действия игрока во ввод Godot и читает то, что видит игрок.
## Время — шаги физики: прогон идёт с --fixed-fps 60, один кадр = один шаг.

const MOVE_ACTIONS: Array[StringName] = [&"move_forward", &"move_back", &"move_left", &"move_right"]
## Сколько пикселей мыши поворачивает камеру на полный оборот.
const PIXELS_PER_TURN := TAU / CameraRig.MOUSE_SENSITIVITY

var _hero: Hero
var _tree: SceneTree


func _init(hero: Hero) -> void:
	_hero = hero
	_tree = hero.get_tree()


# --- Given ---------------------------------------------------------------

## Начальное состояние сценария: герой на старте, камера сзади, ввод отпущен, курсор захвачен.
func begin_on_start() -> void:
	for action in MOVE_ACTIONS + [&"jump"]:
		Input.action_release(action)
	_hero.respawn()
	_hero.camera_rig.reset_view()
	await click_in_window()
	await wait(5)


func stand_at(spot: Vector3) -> void:
	_hero.global_position = spot
	_hero.velocity = Vector3.ZERO
	_hero.reset_physics_interpolation()
	await wait(5)


# --- When ----------------------------------------------------------------

func run_forward(steps: int) -> void:
	await _hold(&"move_forward", steps)


func run_back(steps: int) -> void:
	await _hold(&"move_back", steps)


func run_left(steps: int) -> void:
	await _hold(&"move_left", steps)


func run_right(steps: int) -> void:
	await _hold(&"move_right", steps)


func start_running_forward() -> void:
	Input.action_press(&"move_forward")


func stop_running() -> void:
	for action in MOVE_ACTIONS:
		Input.action_release(action)


## Нажать и отпустить пробел.
func jump() -> void:
	Input.action_press(&"jump")
	await wait(1)
	Input.action_release(&"jump")


func wait(steps: int) -> void:
	for i in steps:
		await _tree.process_frame


## Провести мышью по горизонтали: положительные пиксели — вправо.
func turn_camera(pixels: float) -> void:
	await _move_mouse(Vector2(pixels, 0.0))


## Провести мышью по вертикали: положительные пиксели — вниз.
func tilt_camera(pixels: float) -> void:
	await _move_mouse(Vector2(0.0, pixels))


func press_escape() -> void:
	var press := InputEventKey.new()
	press.keycode = KEY_ESCAPE
	press.physical_keycode = KEY_ESCAPE
	press.pressed = true
	_hero.get_viewport().push_input(press)
	await wait(1)


func click_in_window() -> void:
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	_hero.get_viewport().push_input(click)
	await wait(1)


# --- Then ----------------------------------------------------------------

func position() -> Vector3:
	return _hero.global_position


func is_standing() -> bool:
	return _hero.is_on_floor()


func facing() -> Vector3:
	return _hero.facing()


func camera_position() -> Vector3:
	return _camera().global_position


## Куда смотрит камера по горизонтали, единичный вектор.
func camera_forward_flat() -> Vector3:
	var forward := -_camera().global_basis.z
	return Vector3(forward.x, 0.0, forward.z).normalized()


func camera_distance() -> float:
	return camera_position().distance_to(_hero.global_position + Vector3.UP * CameraRig.PIVOT_HEIGHT)


## Виден ли герой из камеры: луч от камеры до его груди не упирается в площадку.
func is_seen_by_camera() -> bool:
	var chest := _hero.global_position + Vector3.UP * 1.2
	var query := PhysicsRayQueryParameters3D.create(camera_position(), chest, 1)
	return _hero.get_world_3d().direct_space_state.intersect_ray(query).is_empty()


func is_cursor_captured() -> bool:
	return Input.mouse_mode == Input.MOUSE_MODE_CAPTURED


## Подождать и вернуть наибольшую высоту ступней героя за это время.
func wait_and_measure_peak(steps: int) -> float:
	var peak := _hero.global_position.y
	for i in steps:
		await _tree.process_frame
		peak = maxf(peak, _hero.global_position.y)
	return peak


func _hold(action: StringName, steps: int) -> void:
	Input.action_press(action)
	await wait(steps)
	Input.action_release(action)


func _move_mouse(total: Vector2) -> void:
	var chunks := ceili(total.length() / 100.0)
	for i in chunks:
		var motion := InputEventMouseMotion.new()
		motion.relative = total / chunks
		motion.screen_relative = total / chunks
		_hero.get_viewport().push_input(motion)
	await wait(3)


func _camera() -> Camera3D:
	return _hero.get_viewport().get_camera_3d()
