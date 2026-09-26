extends GdUnitTestSuite

## Технические тесты расчёта направления бега и ограничений камеры.

const EPS := Vector3(0.0001, 0.0001, 0.0001)


func test_move_direction_forward_is_away_from_camera() -> void:
	assert_vector(Hero.move_direction(Vector2(0, -1), 0.0)).is_equal_approx(Vector3(0, 0, -1), EPS)


func test_move_direction_follows_camera_yaw() -> void:
	assert_vector(Hero.move_direction(Vector2(0, -1), -PI / 2.0)).is_equal_approx(Vector3(1, 0, 0), EPS)
	assert_vector(Hero.move_direction(Vector2(1, 0), -PI / 2.0)).is_equal_approx(Vector3(0, 0, 1), EPS)


func test_diagonal_is_not_faster_than_straight() -> void:
	assert_float(Hero.move_direction(Vector2(1, -1), 0.3).length()).is_less_equal(1.0001)


func test_no_input_gives_no_direction() -> void:
	assert_vector(Hero.move_direction(Vector2.ZERO, 1.0)).is_equal(Vector3.ZERO)


func test_camera_pitch_is_clamped_and_yaw_wraps() -> void:
	var rig := auto_free(CameraRig.new()) as CameraRig
	var pivot := Node3D.new()
	pivot.name = "Pitch"
	rig.add_child(pivot)
	rig._pitch_pivot = pivot
	rig.look(Vector2(0, 100000))
	assert_float(rig.pitch).is_equal_approx(CameraRig.MIN_PITCH, 0.0001)
	rig.look(Vector2(0, -100000))
	assert_float(rig.pitch).is_equal_approx(CameraRig.MAX_PITCH, 0.0001)
	rig.look(Vector2(-TAU * 3.0 / CameraRig.MOUSE_SENSITIVITY, 0))
	assert_float(rig.yaw).is_between(-PI, PI)
