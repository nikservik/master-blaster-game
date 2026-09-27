extends GdUnitTestSuite

## Спеки фичи «Строительство» (docs/features/building.md, BLD-1…BLD-4).
## Горячий стенд: главная сцена загружается один раз; строят на ровном поле восточнее руин.

const HeroDriver := preload("res://specs/drivers/hero_driver.gd")
const BuilderDriver := preload("res://specs/drivers/builder_driver.gd")

## Где стоит герой на поле и куда смотрит камера по умолчанию (−Z).
const FIELD_SPOT := Vector3(28, 0, 6)
## Точка на земле в 4 м перед героем.
const AHEAD := Vector3(28, 0, 2)
const FOUNDATION_TOP := 0.1
const EPS := 0.05

var hero: HeroDriver
var builder: BuilderDriver
var _stand: Node3D


func before() -> void:
	var main_scene: String = ProjectSettings.get_setting("application/run/main_scene")
	_stand = (load(main_scene) as PackedScene).instantiate()
	add_child(_stand)
	hero = HeroDriver.new(_stand.get_node("Hero") as Hero)
	builder = BuilderDriver.new(_stand.get_node("Builder") as Builder, hero)


func after() -> void:
	_stand.free()


## Сценарий, в котором прицел не дошёл до цели, проверял не то место, что задумано.
func after_test() -> void:
	assert_array(builder.aim_misses()).is_empty()


## Герой на поле, камера смотрит вдоль −Z, построек нет, режим строительства включён.
func _given_on_field() -> void:
	await hero.begin_on_start()
	await builder.begin_empty()
	await hero.stand_at(FIELD_SPOT)
	await builder.enter_build_mode()


## Фундамент-ячейка с центром в точке AHEAD; сетка постройки совпадает с осями мира.
func _given_foundation_ahead() -> void:
	await _given_on_field()
	await builder.aim_at(AHEAD)
	await builder.place()


## Точка на земле перед героем и правее его. Прицел идёт из-за правого плеча: ближе 0,75 м
## к герою он землю не достаёт.
func _beside_hero(ahead: float) -> Vector3:
	var forward := hero.camera_forward_flat()
	return hero.position() + forward * ahead + forward.cross(Vector3.UP) * 0.6


func _yaw(v: Vector3) -> float:
	return atan2(-v.x, -v.z)


## Разница углов по модулю четверти оборота: для квадратных деталей поворот на 90° неразличим.
func _quarter_diff(a: float, b: float) -> float:
	return absf(wrapf(a - b, -PI / 4.0, PI / 4.0))


func _assert_grid(part: Dictionary, from: Vector2, to: Vector2) -> void:
	var grid: AABB = part.grid
	assert_vector(Vector2(grid.position.x, grid.position.z)).is_equal_approx(from, Vector2(EPS, EPS))
	assert_vector(Vector2(grid.end.x, grid.end.z)).is_equal_approx(to, Vector2(EPS, EPS))


# --- BLD-1 Сетка постройки -----------------------------------------------

## BLD-1.1, BLD-3.4
func test_BLD_S1_first_foundation_is_placed_freely_at_any_angle() -> void:
	# Given
	await _given_on_field()
	await hero.turn_camera(HeroDriver.PIXELS_PER_TURN / 12.0)
	var target := hero.position() + hero.camera_forward_flat() * 4.0
	# When
	await builder.aim_at(target)
	await builder.place()
	# Then: фундамент стоит в прицеле, под углом камеры, верхом над землёй
	assert_int(builder.building_count()).is_equal(1)
	var foundation: Dictionary = builder.parts()[0]
	assert_str(foundation.kind).is_equal("foundation")
	assert_float(Vector2(foundation.center.x - target.x, foundation.center.z - target.z).length()).is_less(0.1)
	assert_float(foundation.center.y).is_equal_approx(FOUNDATION_TOP, 0.01)
	assert_float(_quarter_diff(foundation.yaw, _yaw(hero.camera_forward_flat()))).is_less(0.02)
	assert_float(_quarter_diff(foundation.yaw, 0.0)).is_greater(0.3)


## BLD-1.2, BLD-2.1, BLD-3.1
func test_BLD_S2_foundation_sizes_cell_half_quarter_follow_grid() -> void:
	# Given: ячейка [0, 2] × [0, 2] в сетке постройки
	await _given_foundation_ahead()
	_assert_grid(builder.parts()[0], Vector2(0, 0), Vector2(2, 2))
	# When: Tab — половина рядом
	await builder.next_size()
	await builder.aim_at(builder.grid_point(Vector3(3.0, 0, 1.5)))
	await builder.place()
	# Then
	_assert_grid(builder.parts()[1], Vector2(2, 1), Vector2(4, 2))
	# When: Tab — четверть рядом с половиной
	await builder.next_size()
	await builder.aim_at(builder.grid_point(Vector3(4.5, 0, 1.5)))
	await builder.place()
	# Then
	_assert_grid(builder.parts()[2], Vector2(4, 1), Vector2(5, 2))
	# When: Tab ещё раз — снова ячейка
	await builder.next_size()
	# Then
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 0.2, 2), Vector3(EPS, EPS, EPS))


## BLD-1.3, BLD-2.1
func test_BLD_S3_floor_slab_is_one_storey_above_foundation() -> void:
	# Given: фундамент и стена на его краю
	await _given_foundation_ahead()
	await builder.choose_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 0.2)))
	await builder.place()
	# When: перекрытие, прицел — на фундамент
	await builder.choose_floor()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 1.2)))
	await builder.place()
	# Then: верх перекрытия на 3 м выше верха фундамента
	var foundation_top: float = builder.parts()[0].grid.end.y
	var slab: Dictionary = builder.parts()[2]
	assert_str(slab.kind).is_equal("floor")
	assert_float(slab.grid.end.y - foundation_top).is_equal_approx(3.0, 0.01)
	_assert_grid(slab, Vector2(0, 0), Vector2(2, 2))


## BLD-1.4
func test_BLD_S4_part_near_building_snaps_to_its_grid_and_turns_with_it() -> void:
	# Given: фундамент под углом 30°
	await _given_on_field()
	await hero.turn_camera(-HeroDriver.PIXELS_PER_TURN / 12.0)
	await builder.aim_at(hero.position() + hero.camera_forward_flat() * 4.0)
	await builder.place()
	var foundation: Dictionary = builder.parts()[0]
	# When: стена у ближнего к герою края
	await builder.choose_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 1.8)))
	await builder.place()
	# Then: стена ровно посередине края и повёрнута вместе с фундаментом
	var wall: Dictionary = builder.parts()[1]
	var edge_middle: Vector3 = foundation.center + Basis(Vector3.UP, foundation.yaw) * Vector3(0, 0, 1)
	assert_vector(wall.center).is_equal_approx(edge_middle, Vector3(EPS, EPS, EPS))
	assert_float(_quarter_diff(wall.yaw, foundation.yaw)).is_less(0.01)


## BLD-1.4
func test_BLD_S5_foundation_far_from_buildings_starts_new_building() -> void:
	# Given
	await _given_foundation_ahead()
	# When: фундамент в 4 м от первой постройки
	await builder.choose_foundation()
	await builder.aim_at(Vector3(33, 0, 4))
	await builder.place()
	# Then: вторая постройка со своей сеткой под углом камеры
	assert_int(builder.building_count()).is_equal(2)
	var camera_yaw := _yaw(hero.camera_forward_flat())
	assert_float(_quarter_diff(builder.building_yaw(1), camera_yaw)).is_less(0.02)
	assert_float(_quarter_diff(builder.building_yaw(1), builder.building_yaw(0))).is_greater(0.1)


# --- BLD-2 Детали --------------------------------------------------------

## BLD-2.2, BLD-3.1
func test_BLD_S6_walls_are_2_or_1_m_on_cell_or_quarter_edge_door_wall_only_2_m() -> void:
	# Given
	await _given_foundation_ahead()
	# When: стена 2 м на край ячейки
	await builder.choose_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 0.2)))
	await builder.place()
	# Then
	_assert_grid(builder.parts()[1], Vector2(0, -0.1), Vector2(2, 0.1))
	# When: Tab — стена 1 м на край четверти посреди ячейки
	await builder.next_size()
	await builder.aim_at(builder.grid_point(Vector3(0.5, FOUNDATION_TOP, 1.2)))
	await builder.place()
	# Then
	_assert_grid(builder.parts()[2], Vector2(0, 0.9), Vector2(1, 1.1))
	# When: стена с проёмом и Tab
	await builder.choose_door_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 1.7)))
	var before_tab := builder.ghost_size()
	await builder.next_size()
	# Then: длина по-прежнему 2 м
	assert_float(before_tab.x).is_equal_approx(2.0, EPS)
	assert_float(builder.ghost_size().x).is_equal_approx(2.0, EPS)


## BLD-2.2
func test_BLD_S7_hero_walks_through_door_opening_but_not_through_wall() -> void:
	# Given: проём на ближнем краю фундамента, глухая стена на дальнем
	await _given_foundation_ahead()
	await builder.choose_door_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 1.8)))
	await builder.place()
	await builder.choose_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 0.2)))
	await builder.place()
	await builder.press_build_key()
	await hero.stand_at(builder.grid_point(Vector3(1, 0, 4)))
	await hero.look_along(Vector3(0, 0, -1))
	# When: бежит в проём и дальше
	await hero.run_forward(90)
	# Then: внутри комнаты, между проёмом и глухой стеной
	var inside_z := hero.position().z - builder.grid_point(Vector3.ZERO).z
	assert_float(inside_z).is_between(0.3, 1.9)
	assert_bool(hero.is_standing()).is_true()


## BLD-2.3, BLD-3.4
func test_BLD_S8_part_not_touching_building_is_red_and_not_placed() -> void:
	# Given
	await _given_foundation_ahead()
	# When: стена рядом с постройкой, но в 2 м от фундамента
	await builder.choose_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, 0, 3.6)))
	# Then
	assert_bool(builder.ghost_visible()).is_true()
	assert_bool(builder.ghost_green()).is_false()
	# When
	await builder.place()
	# Then
	assert_int(builder.parts().size()).is_equal(1)


## BLD-2.4, BLD-3.4
func test_BLD_S9_part_overlapping_part_item_or_hero_is_red() -> void:
	# Given: фундамент и ящик рядом с ним на земле
	await _given_foundation_ahead()
	await builder.choose_box()
	await builder.aim_at(builder.grid_point(Vector3(3, 0, 1)))
	await builder.place()
	await builder.choose_foundation()
	# When / Then: поверх того же фундамента
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 1)))
	assert_bool(builder.ghost_green()).is_false()
	# When / Then: соседняя ячейка поверх ящика
	await builder.aim_at(builder.grid_point(Vector3(3, 0, 1.6)))
	assert_bool(builder.ghost_green()).is_false()
	await builder.place()
	# When / Then: там, где стоит герой
	await builder.aim_at(_beside_hero(1.0))
	assert_bool(builder.ghost_green()).is_false()
	await builder.place()
	# Then
	assert_int(builder.building_count()).is_equal(1)
	assert_int(builder.parts().size()).is_equal(1)


## BLD-2.5, BLD-2.1
func test_BLD_S10_hero_runs_up_stairs_to_upper_floor() -> void:
	# Given: два фундамента в полосу 2 × 4 м
	await _given_foundation_ahead()
	await builder.aim_at(builder.grid_point(Vector3(1, 0, 3)))
	await builder.place()
	# When: лестница вверх к герою (+Z) и перекрытие у её верха
	await builder.choose_stairs()
	await builder.rotate_part()
	await builder.rotate_part()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 2)))
	await builder.place()
	await hero.stand_at(builder.grid_point(Vector3(1, 0, 9)))
	await builder.choose_floor()
	await builder.aim_at(builder.grid_point(Vector3(1, 0, 5)))
	await builder.place()
	assert_int(builder.part_count("stairs")).is_equal(1)
	assert_int(builder.part_count("floor")).is_equal(1)
	# When: герой у низа лестницы бежит вверх
	await builder.press_build_key()
	await hero.stand_at(builder.grid_point(Vector3(1, 0, -1.5)))
	await hero.look_along(Vector3(0, 0, 1))
	await hero.run_forward(85)
	await hero.wait(10)
	# Then: стоит на перекрытии второго этажа
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(FOUNDATION_TOP + 3.0, EPS)


# --- BLD-3 Установка -----------------------------------------------------

## BLD-3.1
func test_BLD_S11_b_toggles_build_mode_keys_choose_tab_changes_size() -> void:
	# Given: режим строительства выключен
	await hero.begin_on_start()
	await builder.begin_empty()
	await hero.stand_at(FIELD_SPOT)
	# When / Then: без режима нет призрака, щелчок ничего не ставит
	await builder.place()
	assert_bool(builder.ghost_visible()).is_false()
	assert_int(builder.building_count()).is_equal(0)
	# When: B
	await builder.press_build_key()
	await builder.aim_at(AHEAD)
	# Then: призрак фундамента-ячейки
	assert_bool(builder.is_in_build_mode()).is_true()
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 0.2, 2), Vector3(EPS, EPS, EPS))
	# When / Then: клавиши 1–7
	await builder.choose_floor()
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 0.2, 2), Vector3(EPS, EPS, EPS))
	await builder.choose_wall()
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 2.8, 0.2), Vector3(EPS, EPS, EPS))
	await builder.choose_door_wall()
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 2.8, 0.2), Vector3(EPS, EPS, EPS))
	await builder.choose_stairs()
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 3, 4), Vector3(EPS, EPS, EPS))
	await builder.choose_box()
	assert_vector(builder.ghost_size()).is_equal_approx(BuildItem.BOX_SIZE, Vector3(EPS, EPS, EPS))
	await builder.choose_table()
	assert_vector(builder.ghost_size()).is_equal_approx(BuildItem.TABLE_SIZE, Vector3(EPS, EPS, EPS))
	# When / Then: фундамент и Tab
	await builder.choose_foundation()
	await builder.next_size()
	assert_vector(builder.ghost_size()).is_equal_approx(Vector3(2, 0.2, 1), Vector3(EPS, EPS, EPS))
	# When / Then: B ещё раз — режим выключен, призрака нет
	await builder.press_build_key()
	assert_bool(builder.is_in_build_mode()).is_false()
	assert_bool(builder.ghost_visible()).is_false()


## BLD-3.2, MOV-2.5
func test_BLD_S12_ghost_shows_at_crosshair_within_8_m_green_when_allowed() -> void:
	# Given
	await _given_on_field()
	# When: прицел на землю в 5 м
	var near := hero.position() + Vector3(0, 0, -5)
	await builder.aim_at(near)
	# Then: зелёный призрак там, куда указывает центр экрана
	assert_bool(builder.ghost_visible()).is_true()
	assert_bool(builder.ghost_green()).is_true()
	var crosshair: Vector3 = hero.crosshair_point()
	var ghost := builder.ghost_center()
	assert_float(Vector2(ghost.x - crosshair.x, ghost.z - crosshair.z).length()).is_less(0.01)
	# When: прицел дальше 8 м
	await builder.aim_at(hero.position() + Vector3(0, 0, -9.5))
	# Then: призрака нет
	assert_bool(builder.ghost_visible()).is_false()


## BLD-3.3
func test_BLD_S13_r_turns_part_90_degrees_within_grid() -> void:
	# Given: половина фундамента рядом с ячейкой
	await _given_foundation_ahead()
	await builder.next_size()
	await builder.aim_at(builder.grid_point(Vector3(2.5, 0, 1)))
	var yaw_before := builder.ghost_yaw()
	# When
	await builder.rotate_part()
	# Then: призрак повернулся на 90° относительно сетки
	assert_float(absf(wrapf(builder.ghost_yaw() - yaw_before, -PI, PI))).is_equal_approx(PI / 2.0, 0.02)
	# When
	await builder.place()
	# Then: половина стоит поперёк: 1 м по X сетки, 2 м по Z
	_assert_grid(builder.parts()[1], Vector2(2, 0), Vector2(3, 2))


## BLD-3.5
func test_BLD_S14_right_click_removes_part_or_item_others_stay() -> void:
	# Given: фундамент, стена на его краю, ящик на фундаменте
	await _given_foundation_ahead()
	await builder.choose_wall()
	await builder.aim_at(builder.grid_point(Vector3(1, FOUNDATION_TOP, 0.2)))
	await builder.place()
	var wall_center: Vector3 = builder.parts()[1].center
	await builder.choose_box()
	await builder.aim_at(builder.grid_point(Vector3(0.6, FOUNDATION_TOP, 1.3)))
	await builder.place()
	# When: ПКМ по фундаменту
	await builder.aim_at(builder.grid_point(Vector3(1.5, FOUNDATION_TOP, 1.6)))
	await builder.remove()
	# Then: фундамент убран, стена осталась на месте
	assert_int(builder.part_count("foundation")).is_equal(0)
	assert_int(builder.part_count("wall")).is_equal(1)
	assert_vector(builder.parts()[0].center).is_equal_approx(wall_center, Vector3(0.001, 0.001, 0.001))
	# When: ПКМ по ящику
	await builder.aim_at(builder.grid_point(Vector3(0.6, FOUNDATION_TOP + BuildItem.BOX_SIZE.y, 1.3)))
	await builder.remove()
	# Then
	assert_int(builder.items().size()).is_equal(0)


# --- BLD-4 Предметы ------------------------------------------------------

## BLD-4.1
func test_BLD_S15_items_stand_freely_on_ground_and_foundation_not_on_items() -> void:
	# Given
	await _given_foundation_ahead()
	# When: ящик на землю в стороне от сетки
	var on_ground := Vector3(25.3, 0, 3.7)
	await builder.choose_box()
	await builder.aim_at(on_ground)
	await builder.place()
	# When: стол на фундамент
	var on_foundation := builder.grid_point(Vector3(1.3, FOUNDATION_TOP, 0.9))
	await builder.choose_table()
	await builder.aim_at(on_foundation)
	await builder.place()
	# Then: предметы там, куда смотрел прицел
	var placed := builder.items()
	assert_int(placed.size()).is_equal(2)
	assert_vector(placed[0].position).is_equal_approx(on_ground, Vector3(0.06, 0.01, 0.06))
	assert_vector(placed[1].position).is_equal_approx(on_foundation, Vector3(0.06, 0.01, 0.06))
	# When / Then: на ящик ставить нельзя
	await builder.choose_box()
	await builder.aim_at(on_ground + Vector3(0, BuildItem.BOX_SIZE.y, 0))
	assert_bool(builder.ghost_green()).is_false()


## BLD-4.2
func test_BLD_S16_mouse_wheel_turns_item() -> void:
	# Given
	await _given_on_field()
	await builder.choose_box()
	await builder.aim_at(AHEAD)
	var yaw_before := builder.ghost_yaw()
	# When: три щелчка колеса
	await builder.turn_item(3)
	# Then: призрак повернулся на 45°
	assert_float(wrapf(builder.ghost_yaw() - yaw_before, -PI, PI)).is_equal_approx(deg_to_rad(45.0), 0.02)
	# When
	await builder.place()
	# Then
	assert_float(wrapf(builder.items()[0].yaw - yaw_before, -PI, PI)).is_equal_approx(deg_to_rad(45.0), 0.02)


## BLD-4.3
func test_BLD_S17_item_overlapping_item_part_or_hero_is_red() -> void:
	# Given: фундамент и ящик на земле
	await _given_foundation_ahead()
	var box_at := Vector3(25.3, 0, 3.7)
	await builder.choose_box()
	await builder.aim_at(box_at)
	await builder.place()
	# When / Then: второй ящик вплотную на первый
	await builder.aim_at(box_at + Vector3(0.5, 0, 0.3))
	assert_bool(builder.ghost_green()).is_false()
	# When / Then: ящик на землю, заходя на фундамент
	await builder.aim_at(builder.grid_point(Vector3(1, 0, 2.1)))
	assert_bool(builder.ghost_green()).is_false()
	# When / Then: стол, задевающий героя
	await builder.choose_table()
	await builder.aim_at(_beside_hero(0.6))
	assert_bool(builder.ghost_green()).is_false()
	await builder.place()
	# Then
	assert_int(builder.items().size()).is_equal(1)
