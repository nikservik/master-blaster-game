class_name Hero
extends CharacterBody3D

## Нога-Нога: бег относительно камеры, прыжок с опоры, возврат на старт после падения.

const RUN_SPEED := 6.0
const GROUND_ACCELERATION := 50.0
const AIR_ACCELERATION := 15.0
## Высота прыжка v²/2g ≈ 1,6 м: хватает на уступ 1 м, не хватает на 2,5 м.
const JUMP_VELOCITY := 8.8
const GRAVITY := 24.0
const TURN_SPEED := 12.0
## Ниже этой высоты герой считается упавшим с площадки.
const FALL_LIMIT_Y := -10.0
## Скорость, под которую нарисован клип бега.
const RUN_CLIP_SPEED := 5.4
## Время перехода между клипами, с.
const BLEND := 0.15

@onready var camera_rig: CameraRig = $CameraRig
@onready var _model: Node3D = $Model
@onready var _animation: AnimationPlayer = $Model/Body.find_child("AnimationPlayer") as AnimationPlayer

var _start: Vector3
var _dig_left := 0.0


func _ready() -> void:
	_start = global_position


func _process(delta: float) -> void:
	_dig_left = maxf(_dig_left - delta, 0.0)
	var speed := Vector2(velocity.x, velocity.z).length()
	var clip := &"idle"
	var scale := 1.0
	if _dig_left > 0.0:
		clip = &"dig"
	elif not is_on_floor():
		clip = &"jump" if velocity.y > 0.0 else &"fall"
	elif speed > 0.5:
		clip = &"run"
		scale = speed / RUN_CLIP_SPEED
	if _animation.current_animation != clip:
		_animation.play(clip, BLEND)
	_animation.speed_scale = scale


## Проигрывает взмах копания поверх бега и ожидания.
func play_dig() -> void:
	_dig_left = _animation.get_animation(&"dig").length


func _physics_process(delta: float) -> void:
	var input := Input.get_vector(&"move_left", &"move_right", &"move_forward", &"move_back")
	var direction := move_direction(input, camera_rig.yaw)
	var acceleration := GROUND_ACCELERATION if is_on_floor() else AIR_ACCELERATION
	var horizontal := Vector3(velocity.x, 0.0, velocity.z).move_toward(direction * RUN_SPEED, acceleration * delta)
	velocity.x = horizontal.x
	velocity.z = horizontal.z
	if is_on_floor():
		if Input.is_action_just_pressed(&"jump"):
			velocity.y = JUMP_VELOCITY
	else:
		velocity.y -= GRAVITY * delta
	move_and_slide()

	if direction != Vector3.ZERO:
		var target_angle := atan2(-direction.x, -direction.z)
		_model.rotation.y = lerp_angle(_model.rotation.y, target_angle, minf(TURN_SPEED * delta, 1.0))
	if global_position.y < FALL_LIMIT_Y:
		respawn()


## Направление, куда смотрит герой, в мировых координатах.
func facing() -> Vector3:
	return -_model.global_basis.z


func respawn() -> void:
	global_position = _start
	velocity = Vector3.ZERO
	reset_physics_interpolation()


## Направление бега по вводу WASD и повороту камеры: вперёд — от камеры.
static func move_direction(input: Vector2, camera_yaw: float) -> Vector3:
	return Vector3(input.x, 0.0, input.y).limit_length(1.0).rotated(Vector3.UP, camera_yaw)
