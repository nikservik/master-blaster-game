class_name CameraRig
extends Node3D

## Камера от третьего лица. Следует за героем, вращается мышью при захваченном курсоре.
## У стен камеру придвигает дочерний SpringArm3D. Центр вращения выше головы, а камера
## всегда смотрит на героя: прижатая к стене, она оказывается над ним, а не внутри него.

## Центр вращения выше макушки героя (капсула 1,8 м).
const PIVOT_HEIGHT := 2.2
## Куда смотрит камера: грудь героя.
const LOOK_HEIGHT := 1.4
const MOUSE_SENSITIVITY := 0.003
## Ограничения наклона: камера не уходит под героя и не встаёт над ним вертикально.
const MIN_PITCH := deg_to_rad(-70.0)
const MAX_PITCH := deg_to_rad(10.0)
const DEFAULT_PITCH := deg_to_rad(-8.0)

var yaw := 0.0
var pitch := DEFAULT_PITCH
## Игра держит курсор захваченным. Флаг, а не Input.mouse_mode: без окна ОС не захватывает курсор,
## а камера должна слушаться мышь так же.
var _cursor_captured := false

@onready var _hero: Node3D = get_parent()
@onready var _pitch_pivot: Node3D = $Pitch
@onready var _camera: Camera3D = $Pitch/SpringArm/Camera


func _ready() -> void:
	_capture_cursor(true)
	_apply()


func _process(_delta: float) -> void:
	var hero_origin := _hero.get_global_transform_interpolated().origin
	global_position = hero_origin + Vector3.UP * PIVOT_HEIGHT
	_camera.look_at(hero_origin + Vector3.UP * LOOK_HEIGHT)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_cancel"):
		_capture_cursor(false)
	elif event is InputEventMouseButton and event.pressed:
		_capture_cursor(true)
	elif event is InputEventMouseMotion and _cursor_captured:
		look((event as InputEventMouseMotion).screen_relative)


func look(mouse_delta: Vector2) -> void:
	yaw = wrapf(yaw - mouse_delta.x * MOUSE_SENSITIVITY, -PI, PI)
	pitch = clampf(pitch - mouse_delta.y * MOUSE_SENSITIVITY, MIN_PITCH, MAX_PITCH)
	_apply()


func reset_view() -> void:
	yaw = 0.0
	pitch = DEFAULT_PITCH
	_apply()


func _capture_cursor(captured: bool) -> void:
	_cursor_captured = captured
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _apply() -> void:
	rotation = Vector3(0.0, yaw, 0.0)
	_pitch_pivot.rotation = Vector3(pitch, 0.0, 0.0)
