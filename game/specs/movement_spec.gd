extends GdUnitTestSuite

## Спеки фичи «Передвижение и камера» (docs/features/movement.md, MOV-1…MOV-3).
## Горячий стенд: площадка руин с ровным полом загружается один раз на весь набор.

const HeroDriver := preload("res://specs/drivers/hero_driver.gd")
const LevelDriver := preload("res://specs/drivers/level_driver.gd")
## Спеки передвижения идут на площадке руин без рельефа: размеры пола и уступов в ней точные.
const RUINS := "res://levels/ruins.tscn"

var hero: HeroDriver
var level: LevelDriver
var _stand: Node3D
var _cursor_captured_on_launch := false


func before() -> void:
	_stand = (load(RUINS) as PackedScene).instantiate()
	add_child(_stand)
	_cursor_captured_on_launch = Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	hero = HeroDriver.new(_stand.get_node("Hero") as Hero)
	level = LevelDriver.new(_stand)


func after() -> void:
	_stand.free()


# --- MOV-1.1 -------------------------------------------------------------

## MOV-1.1
func test_MOV_S1_w_runs_away_from_camera_and_hero_faces_the_run() -> void:
	# Given
	await hero.begin_on_start()
	var start := hero.position()
	# When
	await hero.run_forward(30)
	# Then
	var run := hero.position() - start
	assert_float(run.z).is_less(-1.5)
	assert_float(absf(run.x)).is_less(0.05)
	assert_vector(hero.facing()).is_equal_approx(Vector3(0, 0, -1), Vector3(0.05, 0.05, 0.05))


## MOV-1.1
func test_MOV_S2_after_camera_turn_w_runs_where_camera_looks() -> void:
	# Given
	await hero.begin_on_start()
	# When: мышь вправо на четверть оборота, затем W
	await hero.turn_camera(HeroDriver.PIXELS_PER_TURN / 4.0)
	var start := hero.position()
	await hero.run_forward(30)
	# Then: камера смотрит вправо от старого направления (+X), герой бежит туда же
	assert_vector(hero.camera_forward_flat()).is_equal_approx(Vector3(1, 0, 0), Vector3(0.02, 0.02, 0.02))
	var run := (hero.position() - start)
	assert_float(run.x).is_greater(1.5)
	assert_float(absf(run.z)).is_less(0.05)
	assert_vector(hero.facing()).is_equal_approx(Vector3(1, 0, 0), Vector3(0.05, 0.05, 0.05))


## MOV-1.1
func test_MOV_S3_s_runs_toward_camera_a_and_d_run_left_and_right_on_screen() -> void:
	# Given: камера смотрит в -Z, правая сторона экрана — +X
	await hero.begin_on_start()
	# When / Then
	var start := hero.position()
	await hero.run_right(20)
	assert_float((hero.position() - start).x).is_greater(1.0)
	assert_vector(hero.facing()).is_equal_approx(Vector3(1, 0, 0), Vector3(0.05, 0.05, 0.05))

	start = hero.position()
	await hero.run_left(30)
	assert_float((hero.position() - start).x).is_less(-1.0)

	start = hero.position()
	await hero.run_back(20)
	assert_float((hero.position() - start).z).is_greater(1.0)
	assert_vector(hero.facing()).is_equal_approx(Vector3(0, 0, 1), Vector3(0.05, 0.05, 0.05))


# --- MOV-1.2 -------------------------------------------------------------

## MOV-1.2
func test_MOV_S4_space_jumps_from_floor_and_hero_lands() -> void:
	# Given
	await hero.begin_on_start()
	# When
	await hero.jump()
	var peak := await hero.wait_and_measure_peak(60)
	# Then
	assert_float(peak).is_greater(level.floor_top() + 1.0)
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(level.floor_top(), 0.05)


## MOV-1.2
func test_MOV_S5_second_jump_in_air_does_not_work() -> void:
	# Given: высота обычного прыжка
	await hero.begin_on_start()
	await hero.jump()
	var single_peak := await hero.wait_and_measure_peak(60)
	# When: прыжок и ещё раз пробел в воздухе
	await hero.jump()
	await hero.wait(10)
	assert_bool(hero.is_standing()).is_false()
	await hero.jump()
	var peak := await hero.wait_and_measure_peak(60)
	# Then
	assert_float(peak).is_equal_approx(single_peak, 0.05)
	assert_bool(hero.is_standing()).is_true()


# --- MOV-1.3 -------------------------------------------------------------

## MOV-1.3
func test_MOV_S6_hero_does_not_pass_through_wall() -> void:
	# Given
	await hero.begin_on_start()
	await hero.stand_at(level.spot_with_back_to_wall(3.0))
	# When: долго бежит к стене
	await hero.run_back(90)
	# Then
	assert_float(hero.position().z).is_less(level.back_wall_face_z())
	assert_bool(hero.is_standing()).is_true()


## MOV-1.3
func test_MOV_S7_hero_falls_after_stepping_off_edge() -> void:
	# Given
	await hero.begin_on_start()
	await hero.stand_at(level.spot_before_edge(1.0))
	# When
	await hero.run_forward(30)
	await hero.wait(10)
	# Then
	assert_float(hero.position().y).is_less(level.floor_top() - 0.5)
	assert_bool(hero.is_standing()).is_false()


## MOV-1.3, MOV-1.4
func test_MOV_S8_standing_jump_reaches_low_ledge() -> void:
	# Given
	await hero.begin_on_start()
	var ledge := level.low_ledge()
	await hero.stand_at(level.spot_before_ledge(ledge, 0.6))
	# When: W и пробел с места
	hero.start_running_forward()
	await hero.jump()
	await hero.wait(30)
	hero.stop_running()
	await hero.wait(30)
	# Then
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(ledge.top, 0.05)
	assert_float(hero.position().z).is_less(ledge.near_face_z)


## MOV-1.4
func test_MOV_S9_running_jump_reaches_low_ledge() -> void:
	# Given
	await hero.begin_on_start()
	var ledge := level.low_ledge()
	await hero.stand_at(level.spot_before_ledge(ledge, 4.0))
	# When: разбег и прыжок перед уступом
	hero.start_running_forward()
	await hero.wait(24)
	await hero.jump()
	await hero.wait(30)
	hero.stop_running()
	await hero.wait(30)
	# Then
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(ledge.top, 0.05)


## MOV-1.3, MOV-1.4
func test_MOV_S10_standing_jump_does_not_reach_high_ledge() -> void:
	# Given
	await hero.begin_on_start()
	var ledge := level.high_ledge()
	await hero.stand_at(level.spot_before_ledge(ledge, 0.6))
	# When
	hero.start_running_forward()
	await hero.jump()
	await hero.wait(30)
	hero.stop_running()
	await hero.wait(30)
	# Then: остался на полу перед уступом
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(level.floor_top(), 0.05)
	assert_float(hero.position().z).is_greater(ledge.near_face_z)


## MOV-1.4
func test_MOV_S11_running_jump_does_not_reach_high_ledge() -> void:
	# Given
	await hero.begin_on_start()
	var ledge := level.high_ledge()
	await hero.stand_at(level.spot_before_ledge(ledge, 4.0))
	# When
	hero.start_running_forward()
	await hero.wait(24)
	await hero.jump()
	await hero.wait(30)
	hero.stop_running()
	await hero.wait(30)
	# Then
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(level.floor_top(), 0.05)
	assert_float(hero.position().z).is_greater(ledge.near_face_z)


# --- MOV-1.5 -------------------------------------------------------------

## MOV-1.5
func test_MOV_S12_after_fall_hero_returns_to_start_and_keeps_control() -> void:
	# Given
	await hero.begin_on_start()
	var start := hero.position()
	await hero.stand_at(level.spot_before_edge(1.0))
	# When: сбегает с края и падает
	await hero.run_forward(40)
	await hero.wait(90)
	# Then: снова на старте и слушается
	assert_vector(hero.position()).is_equal_approx(start, Vector3(0.05, 0.05, 0.05))
	assert_bool(hero.is_standing()).is_true()
	await hero.run_forward(20)
	assert_float((hero.position() - start).z).is_less(-1.0)


# --- MOV-2 ---------------------------------------------------------------

## MOV-2.1
func test_MOV_S13_camera_stays_behind_and_above_and_follows() -> void:
	# Given
	await hero.begin_on_start()
	var offset := hero.camera_position() - hero.position()
	var right := hero.camera_forward_flat().cross(Vector3.UP)
	# Then: сзади, выше головы и правее — из-за правого плеча
	assert_float(offset.dot(hero.camera_forward_flat())).is_less(-2.0)
	assert_float(offset.y).is_greater(2.0)
	assert_float(offset.dot(right)).is_greater(0.4)
	assert_bool(hero.is_hero_visible()).is_true()
	# When
	await hero.run_forward(40)
	await hero.wait(10)
	# Then: следует за героем на том же месте относительно него
	var moved_offset := hero.camera_position() - hero.position()
	assert_vector(moved_offset).is_equal_approx(offset, Vector3(0.1, 0.1, 0.1))


## MOV-2.2
func test_MOV_S14_mouse_turns_camera_around_hero_without_limit() -> void:
	# Given
	await hero.begin_on_start()
	# When: мышь вправо на оборот с четвертью
	await hero.turn_camera(HeroDriver.PIXELS_PER_TURN * 1.25)
	# Then: камера повернулась на четверть вправо и по-прежнему позади героя
	assert_vector(hero.camera_forward_flat()).is_equal_approx(Vector3(1, 0, 0), Vector3(0.02, 0.02, 0.02))
	var offset := hero.camera_position() - hero.position()
	assert_float(offset.dot(hero.camera_forward_flat())).is_less(-2.0)


## MOV-2.2
func test_MOV_S15_camera_goes_neither_under_hero_nor_straight_above() -> void:
	# Given
	await hero.begin_on_start()
	# When: мышь далеко вниз — камера поднимается
	await hero.tilt_camera(5000.0)
	# Then: не встаёт над героем вертикально
	var offset := hero.camera_position() - hero.position()
	assert_float(Vector2(offset.x, offset.z).length()).is_greater(0.5)
	assert_float(offset.y).is_greater(0.0)
	assert_bool(hero.is_hero_visible()).is_true()
	# When: мышь далеко вверх — камера опускается
	await hero.tilt_camera(-10000.0)
	# Then: не уходит ниже ступней героя
	offset = hero.camera_position() - hero.position()
	assert_float(offset.y).is_greater(0.0)
	assert_bool(hero.is_hero_visible()).is_true()


## MOV-2.3
func test_MOV_S16_wall_behind_hero_pulls_camera_closer_and_hero_stays_visible() -> void:
	# Given: герой спиной к стене, камера по умолчанию оказалась бы за ней
	await hero.begin_on_start()
	await hero.stand_at(level.spot_with_back_to_wall(1.0))
	# Then
	assert_float(hero.camera_distance()).is_less(1.5)
	assert_float(hero.camera_position().z).is_less(level.back_wall_face_z())
	assert_bool(hero.is_hero_visible()).is_true()
	# When: пятится вплотную к стене
	await hero.run_back(30)
	# Then: камера всё ещё перед стеной и герой виден
	assert_float(hero.camera_position().z).is_less(level.back_wall_face_z())
	assert_bool(hero.is_hero_visible()).is_true()


## MOV-2.5
func test_MOV_S20_crosshair_is_in_screen_center_and_hero_never_covers_it() -> void:
	# Given: игра, режим строительства выключен
	await hero.begin_on_start()
	# Then: прицел в центре экрана, указывает на площадку, герой его не закрывает
	assert_vector(hero.crosshair_on_screen()).is_equal_approx(hero.screen_center(), Vector2(1, 1))
	assert_object(hero.crosshair_point()).is_not_null()
	assert_bool(hero.hero_covers_crosshair()).is_false()
	# When / Then: камера сверху, снизу, сбоку и у стены за спиной — герой прицел не закрывает
	await hero.tilt_camera(5000.0)
	assert_bool(hero.hero_covers_crosshair()).is_false()
	await hero.tilt_camera(-10000.0)
	assert_bool(hero.hero_covers_crosshair()).is_false()
	await hero.turn_camera(HeroDriver.PIXELS_PER_TURN / 3.0)
	assert_bool(hero.hero_covers_crosshair()).is_false()
	await hero.begin_on_start()
	await hero.stand_at(level.spot_with_back_to_wall(0.4))
	await hero.tilt_camera(3000.0)
	assert_bool(hero.hero_covers_crosshair()).is_false()
	assert_vector(hero.crosshair_on_screen()).is_equal_approx(hero.screen_center(), Vector2(1, 1))


## MOV-2.4. Курсор захватывает ОС, а без окна захвата нет: спека идёт только в прогоне с окном.
func test_MOV_S17_cursor_is_captured_esc_releases_click_captures(
	do_skip := DisplayServer.get_name() == "headless",
	skip_reason := "захват курсора виден только с окном"
) -> void:
	# Given: игра запущена
	assert_bool(_cursor_captured_on_launch).is_true()
	await hero.begin_on_start()
	# When / Then
	await hero.press_escape()
	assert_bool(hero.is_cursor_captured()).is_false()
	await hero.click_in_window()
	assert_bool(hero.is_cursor_captured()).is_true()


## MOV-2.4
func test_MOV_S19_after_esc_mouse_does_not_turn_camera_until_click() -> void:
	# Given
	await hero.begin_on_start()
	# When: Esc и движение мыши
	await hero.press_escape()
	await hero.turn_camera(HeroDriver.PIXELS_PER_TURN / 4.0)
	# Then: камера не повернулась
	assert_vector(hero.camera_forward_flat()).is_equal_approx(Vector3(0, 0, -1), Vector3(0.02, 0.02, 0.02))
	# When: щелчок в окне и движение мыши
	await hero.click_in_window()
	await hero.turn_camera(HeroDriver.PIXELS_PER_TURN / 4.0)
	# Then: камера снова слушается мышь
	assert_vector(hero.camera_forward_flat()).is_equal_approx(Vector3(1, 0, 0), Vector3(0.02, 0.02, 0.02))


# --- MOV-3 ---------------------------------------------------------------

## MOV-3.1, MOV-3.2
func test_MOV_S18_game_starts_on_ruins_with_low_and_high_ledges() -> void:
	# Given: запущена главная сцена
	await hero.begin_on_start()
	# Then: герой сразу стоит на площадке, на ней уступы 1 м и 2,5 м
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(level.floor_top(), 0.05)
	assert_float(level.low_ledge().top - level.floor_top()).is_equal_approx(1.0, 0.01)
	assert_float(level.high_ledge().top - level.floor_top()).is_equal_approx(2.5, 0.01)
