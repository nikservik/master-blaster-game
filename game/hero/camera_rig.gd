class_name CameraRig
extends Node3D

## Камера от третьего лица из-за правого плеча. Следует за героем, вращается мышью при захваченном
## курсоре. Центр вращения выше головы, камера сдвинута вправо и смотрит на точку правее груди героя.
## Поэтому луч прицела из центра экрана всегда идёт правее героя и не задевает его.
## У стен камеру придвигают два SpringArm3D: вбок от центра вращения к плечу, затем назад от плеча.
## Так путь от героя к камере всегда свободен и камера не выглядывает из-за угла.

## Центр вращения выше макушки героя (капсула 1,8 м).
const PIVOT_HEIGHT := 2.2
## Высота точки, на которую смотрит камера, — уровень груди.
const LOOK_HEIGHT := 1.4
## Сдвиг вправо: больше радиуса капсулы (0,4 м), чтобы луч прицела проходил мимо героя.
const SHOULDER := 0.6
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
@onready var _camera: Camera3D = $Pitch/Shoulder/Arm/Camera


func _ready() -> void:
	_capture_cursor(true)
	_apply()


func _process(_delta: float) -> void:
	var hero_origin := _hero.get_global_transform_interpolated().origin
	global_position = hero_origin + Vector3.UP * PIVOT_HEIGHT
	var target := hero_origin + Vector3.UP * LOOK_HEIGHT + global_basis.x * SHOULDER
	# Прижатая к центру вращения камера стоит ровно над целью: смотреть некуда.
	if Vector2(_camera.global_position.x - target.x, _camera.global_position.z - target.z).length() > 0.001:
		_camera.look_at(target)


## Щелчок, который возвращает захват курсора, дальше не идёт: иначе он же копал бы или строил.
func _input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and not _cursor_captured:
		_capture_cursor(true)
		get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_cancel"):
		_capture_cursor(false)
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


## Луч прицела: из камеры через центр экрана (MOV-2.5). Возвращает [from: Vector3, dir: Vector3],
## dir — единичный. С этой точкой работают строительство и копание.
func aim_ray() -> Array:
	var center := _camera.get_viewport().get_visible_rect().size / 2.0
	return [_camera.project_ray_origin(center), _camera.project_ray_normal(center)]


func _capture_cursor(captured: bool) -> void:
	_cursor_captured = captured
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _apply() -> void:
	rotation = Vector3(0.0, yaw, 0.0)
	_pitch_pivot.rotation = Vector3(pitch, 0.0, 0.0)
