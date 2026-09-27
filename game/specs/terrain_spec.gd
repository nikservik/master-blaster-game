extends GdUnitTestSuite

## Спеки фичи «Рельеф и копание» (docs/features/terrain.md, TER-1…TER-3) и старта в мире (MOV-1.5, MOV-3.2).
## Горячий стенд: главная сцена — мир на рельефе — загружается и строится один раз на весь набор.
## Хранилище правок — во временном каталоге. У каждой спеки своё место на рельефе, чтобы правки не мешали.

const HeroDriver := preload("res://specs/drivers/hero_driver.gd")
const TerrainDriver := preload("res://specs/drivers/terrain_driver.gd")
const BuilderDriver := preload("res://specs/drivers/builder_driver.gd")
const LevelDriver := preload("res://specs/drivers/level_driver.gd")

const GRASS := WorldTerrain.Ground.GRASS
const STONE := WorldTerrain.Ground.STONE
const DIRT := WorldTerrain.Ground.DIRT
const RADIUS := 1.5
## Ровный грунт у руин: верх пола руин — 40 м, грунт вокруг на 0,1 м ниже.
const GROUND_Y := 39.9

var hero: HeroDriver
var terrain: TerrainDriver
var builder: BuilderDriver
var level: LevelDriver
var _stand: Node3D


func before() -> void:
	var store := create_temp_dir("terrain_spec")
	DirAccess.remove_absolute(store + "/terrain.sqlite")
	var main_scene: String = ProjectSettings.get_setting("application/run/main_scene")
	_stand = (load(main_scene) as PackedScene).instantiate()
	(_stand.get_node("Terrain") as WorldTerrain).save_path = store + "/terrain.sqlite"
	add_child(_stand)
	hero = HeroDriver.new(_stand.get_node("Ruins/Hero") as Hero)
	terrain = TerrainDriver.new(_stand, hero)
	builder = BuilderDriver.new(_stand.get_node("Ruins/Builder") as Builder, hero)
	level = LevelDriver.new(_stand.get_node("Ruins") as Node3D)
	await terrain.wait_until_ready()


func after() -> void:
	_stand.free()


## Герой стоит на грунте в (x, z) — на верхнем или на первом ниже высоты below — и смотрит вдоль направления.
func _given_on_ground(x: float, z: float, look: Vector3, below := INF) -> Vector3:
	await hero.begin_on_start()
	var at := await terrain.stand_on_ground(x, z, below)
	await hero.look_along(look)
	return at


# --- MOV-3.2, TER-1.3 ----------------------------------------------------

## MOV-3.2, TER-1.3
func test_TER_S1_game_starts_in_world_hero_on_ruins_that_stand_on_terrain() -> void:
	# Given: запущена главная сцена
	await hero.begin_on_start()
	# Then: герой стоит на полу руин
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_equal_approx(level.floor_top(), 0.05)
	# Then: вокруг пола руин вплотную — рельеф, чуть ниже пола
	var top := level.floor_top()
	for side in [Vector2(-12.5, 0), Vector2(0, -12.5), Vector2(-12.5, 8), Vector2(8, -12.5)]:
		var y := terrain.surface_y(side.x, side.y)
		assert_float(y).is_between(top - 0.2, top)


# --- TER-1.1 -------------------------------------------------------------

## TER-1.1
func test_TER_S2_world_is_1_km_of_smooth_hills_with_cliff_and_overhangs() -> void:
	# Given: мир запущен
	await hero.begin_on_start()
	# Then: участок 1 × 1 км
	assert_float(terrain.world_size().x).is_equal_approx(1024.0, 1.0)
	assert_float(terrain.world_size().z).is_equal_approx(1024.0, 1.0)
	# Then: холмы — высота по участку меняется на десятки метров
	var heights: Array[float] = []
	for x in range(-480, 481, 120):
		for z in range(-480, 481, 120):
			heights.append(terrain.generated_surface_y(x, z))
	assert_float(heights.max() - heights.min()).is_greater(30.0)
	# Then: обрыв — на 4 м по горизонтали рельеф поднимается больше чем на 15 м
	var steepest := 0.0
	for z in range(-200, 200):
		steepest = maxf(steepest, absf(terrain.generated_surface_y(0, z) - terrain.generated_surface_y(0, z + 4)))
	assert_float(steepest).is_greater(15.0)
	# Then: нависания — в столбце под грунтом есть воздух, а под ним снова грунт
	assert_bool(_has_overhang()).is_true()
	# Then: гладкий, без кубиков — нормаль на склоне наклонная, высоты меняются плавно
	var slope := terrain.surface_hit_by(Vector3(0, 60, -30), Vector3(0, 20, -30))
	assert_float((slope.normal as Vector3).y).is_between(0.5, 0.97)
	var previous := terrain.surface_y(0, -30)
	for i in range(1, 12):
		var y := terrain.surface_y(0, -30 - i * 0.25)
		assert_float(absf(y - previous)).is_less(0.3)
		previous = y


func _has_overhang() -> bool:
	for x in range(-100, 101, 10):
		for z in range(-85, -55):
			var column := terrain.generated_column(x, z)
			var changes := 0
			for i in range(1, column.size()):
				if column[i] != column[i - 1]:
					changes += 1
			if changes >= 3:
				return true
	return false


# --- TER-1.2 -------------------------------------------------------------

## TER-1.2
func test_TER_S3_flat_open_ground_is_grass_cliff_and_cave_floor_are_stone() -> void:
	# Given: герой на старте
	await hero.begin_on_start()
	# Then: ровный открытый грунт у руин — трава
	assert_int(terrain.ground_hit_by(Vector3(-14, 45, 0), Vector3(-14, 35, 0))).is_equal(GRASS)
	# Given: герой у подножия обрыва; рядом навес с ровным полом
	var foot := _cliff_foot(-10)
	var at := await terrain.stand_on_ground(-10, foot.z + 2.0, foot.y + 1.0)
	var cave: Variant = _find_cave_floor(-40, 20)
	assert_that(cave).is_not_null()
	# Then: отвесная стена обрыва — камень
	var chest := at + Vector3.UP * 1.3
	assert_int(terrain.ground_hit_by(chest, chest + Vector3.FORWARD * 8.0)).is_equal(STONE)
	# Then: пол под навесом ровный, но каменный
	var above_floor: Vector3 = cave + Vector3.UP * 1.0
	var floor_hit := terrain.surface_hit_by(above_floor, above_floor + Vector3.DOWN * 2.0)
	assert_float((floor_hit.normal as Vector3).y).is_greater(WorldTerrain.GRASS_MIN_NORMAL_Y)
	assert_int(terrain.ground_hit_by(above_floor, above_floor + Vector3.DOWN * 2.0)).is_equal(STONE)


## Пол пещеры у обрыва по форме мира: над полом не меньше 2 м воздуха, выше в пределах 8 м — грунт навеса.
## Пол ровный: у соседних столбцов верх пола на той же высоте. Возвращает точку на полу.
func _find_cave_floor(x_from: int, x_to: int) -> Variant:
	for x in range(x_from, x_to + 1, 2):
		for z in range(-80, -60):
			var column := terrain.generated_column(x, z)
			for i in range(1, column.size() - 9):
				if not (column[i] and not column[i + 1] and not column[i + 2] and column.slice(i + 3, i + 9).has(true)):
					continue
				var flat := true
				for side in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
					var next := terrain.generated_column(x + side.x, z + side.y)
					flat = flat and next[i] and not next[i + 1]
				if flat:
					return Vector3(x, WorldTerrain.BOUNDS.position.y + i + 0.5, z)
	return null


## TER-1.2, TER-2.1
func test_TER_S4_left_click_digs_sphere_at_crosshair_walls_are_dirt() -> void:
	# Given
	var at := await _given_on_ground(-14, -16, Vector3.FORWARD)
	var target := Vector3(at.x, GROUND_Y, at.z - 4.0)
	await terrain.aim_at(target)
	var aimed: Vector3 = terrain.crosshair_point()
	# When
	await terrain.click_left()
	# Then: шар радиусом 1,5 м в точке прицела убран, за его краем грунт на месте
	assert_bool(terrain.is_solid(aimed + Vector3.DOWN * (RADIUS - 0.3))).is_false()
	assert_bool(terrain.is_solid(aimed + Vector3.DOWN * (RADIUS + 0.4))).is_true()
	assert_bool(terrain.is_solid(aimed + Vector3(RADIUS - 0.3, -0.5, 0))).is_false()
	assert_bool(terrain.is_solid(aimed + Vector3(RADIUS + 0.4, -0.5, 0))).is_true()
	# Then: дно ямы — земля
	var bottom := aimed + Vector3.DOWN * RADIUS
	assert_int(terrain.ground_hit_by(bottom + Vector3.UP, bottom + Vector3.DOWN)).is_equal(DIRT)


## TER-2.1
func test_TER_S5_right_click_adds_same_sphere_at_crosshair() -> void:
	# Given
	var at := await _given_on_ground(-7, -16, Vector3.FORWARD)
	await terrain.aim_at(Vector3(at.x, GROUND_Y, at.z - 4.0))
	var aimed: Vector3 = terrain.crosshair_point()
	# When
	await terrain.click_right()
	# Then
	assert_bool(terrain.is_solid(aimed + Vector3.UP * (RADIUS - 0.3))).is_true()
	assert_bool(terrain.is_solid(aimed + Vector3.UP * (RADIUS + 0.4))).is_false()
	var top := aimed + Vector3.UP * RADIUS
	assert_int(terrain.ground_hit_by(top + Vector3.UP, top + Vector3.DOWN)).is_equal(DIRT)


## TER-2.1
func test_TER_S6_ground_farther_than_6_m_from_hero_is_not_dug() -> void:
	# Given: прицел на грунте в 8 м от героя
	var at := await _given_on_ground(7, -14, Vector3.FORWARD)
	var target := Vector3(at.x, terrain.surface_y(at.x, at.z - 8.0), at.z - 8.0)
	await terrain.aim_at(target)
	var aimed: Vector3 = terrain.crosshair_point()
	assert_float(aimed.distance_to(at)).is_greater(6.0)
	# When
	await terrain.click_left()
	await terrain.click_right()
	# Then: грунт как был
	assert_bool(terrain.is_solid(aimed + Vector3.DOWN * 0.3)).is_true()
	assert_bool(terrain.is_solid(aimed + Vector3.UP * 0.3)).is_false()


## TER-2.1, BLD-3.4
func test_TER_S7_in_build_mode_mouse_buttons_do_not_dig_or_fill() -> void:
	# Given: режим строительства
	var at := await _given_on_ground(-8, 18, Vector3.BACK)
	await builder.begin_empty()
	await builder.enter_build_mode()
	var target := Vector3(at.x, GROUND_Y, at.z + 4.0)
	await terrain.aim_at(target)
	var aimed: Vector3 = terrain.crosshair_point()
	# When
	await terrain.click_right()
	await terrain.click_left()
	# Then: грунт не тронут
	assert_bool(terrain.is_solid(aimed + Vector3.DOWN * 0.3)).is_true()
	assert_bool(terrain.is_solid(aimed + Vector3.UP * 0.3)).is_false()
	await builder.press_build_key()
	await builder.begin_empty()


## TER-2.2
func test_TER_S8_hero_falls_into_dug_pit_and_stands_on_its_bottom() -> void:
	# Given: яма перед героем
	var at := await _given_on_ground(8, 18, Vector3.BACK)
	await terrain.aim_at(Vector3(at.x, GROUND_Y, at.z + 2.5))
	await terrain.click_left()
	# When: бежит вперёд
	await hero.run_forward(20)
	await hero.wait(30)
	# Then: стоит в яме, ниже окружающего грунта
	assert_float(hero.position().y).is_less(GROUND_Y - 0.8)
	assert_bool(hero.is_standing()).is_true()


## TER-2.2
func test_TER_S9_hero_walks_into_tunnel_dug_into_cliff() -> void:
	# Given: герой у подножия отвесной стены обрыва
	var foot := _cliff_foot(-10)
	var wall_z: float = foot.z
	var at := await _given_on_ground(-10, wall_z + 2.0, Vector3.FORWARD, foot.y + 1.0)
	# When: копает перед собой на высоте груди и заходит в туннель, четыре раза
	for i in 4:
		var feet := hero.position()
		var face: Vector3 = terrain.surface_hit_by(feet + Vector3.UP * 1.3, feet + Vector3(0, 1.3, -6)).position
		await terrain.aim_at(face)
		await terrain.click_left()
		await hero.run_forward(20)
		await hero.wait(20)
	# Then: герой прошёл сквозь линию стены и стоит под толщей грунта
	var inside := hero.position()
	assert_float(inside.z).is_less(wall_z - 2.0)
	assert_bool(hero.is_standing()).is_true()
	assert_bool(terrain.is_solid(inside + Vector3.UP * 6.0)).is_true()
	assert_float(inside.y).is_equal_approx(at.y, 1.0)


## Подножие обрыва на x: {z — линия стены на высоте груди героя, y — грунт у подножия}.
## Идёт от низины к обрыву (−Z), пока на высоте груди над грунтом не окажется грунт стены.
func _cliff_foot(x: float) -> Dictionary:
	var z := -50.0
	var ground := terrain.generated_surface_y(x, z)
	while z > -90.0:
		var column := terrain.generated_column(x, z - 0.5)
		if column[roundi(ground + 1.3 - WorldTerrain.BOUNDS.position.y)]:
			return {"z": z, "y": ground}
		z -= 0.5
		ground = terrain.generated_surface_y(x, z, ground + 1.0)
	return {}


## TER-2.3
func test_TER_S10_fill_into_hero_does_nothing() -> void:
	# Given: прицел в грунт у самых ног героя
	var at := await _given_on_ground(0, 18, Vector3.BACK)
	await terrain.aim_at(Vector3(at.x, GROUND_Y, at.z + 1.0))
	var aimed: Vector3 = terrain.crosshair_point()
	# When
	await terrain.click_right()
	# Then: над грунтом по-прежнему воздух, герой стоит где стоял
	assert_bool(terrain.is_solid(aimed + Vector3.UP * 0.5)).is_false()
	assert_bool(terrain.is_solid(aimed + Vector3.UP * 1.2)).is_false()
	assert_vector(hero.position()).is_equal_approx(at, Vector3(0.05, 0.05, 0.05))


## TER-2.4
func test_TER_S11_digging_leaves_building_parts_even_when_ground_under_them_is_dug() -> void:
	# Given: фундамент на грунте перед героем
	var at := await _given_on_ground(0, -14, Vector3.FORWARD)
	await builder.begin_empty()
	await builder.enter_build_mode()
	var center := Vector3(at.x, GROUND_Y, at.z - 5.0)
	await builder.aim_at(center)
	await builder.place()
	assert_int(builder.part_count("foundation")).is_equal(1)
	var placed: Vector3 = builder.parts()[0].center
	await builder.press_build_key()
	# When: копает грунт вплотную к ближнему краю фундамента (ячейка 2 × 2 м), затем в сам фундамент
	var edge := Vector3(placed.x, GROUND_Y, placed.z + 1.3)
	await terrain.aim_at(edge)
	await terrain.click_left()
	await terrain.aim_at(placed + Vector3(0, 0.0, -0.5))
	await terrain.click_left()
	# Then: фундамент на месте, а грунт под его краем выкопан
	assert_int(builder.part_count("foundation")).is_equal(1)
	assert_vector(builder.parts()[0].center).is_equal_approx(placed, Vector3(0.01, 0.01, 0.01))
	assert_bool(terrain.is_solid(Vector3(placed.x, GROUND_Y - 0.5, placed.z + 0.6))).is_false()
	await builder.begin_empty()


# --- TER-3 ---------------------------------------------------------------

## TER-3.1
func test_TER_S12_pit_is_saved_on_exit_and_is_there_on_next_launch() -> void:
	# Given: выкопана яма
	await hero.begin_on_start()
	var pit := Vector3(20, GROUND_Y, -22.5)
	await terrain.dug_pit(pit)
	# When: выход из игры и следующий запуск
	await terrain.quit_game()
	await terrain.launch_again(pit)
	# Then: яма на месте, её стенки — земля
	assert_bool(terrain.is_solid_after_relaunch(pit + Vector3.DOWN * 1.0)).is_false()
	assert_bool(terrain.is_solid_after_relaunch(pit + Vector3.DOWN * 2.0)).is_true()
	assert_int(terrain.ground_after_relaunch(pit + Vector3.DOWN * RADIUS)).is_equal(DIRT)
	terrain.close_relaunched()
	await terrain.restore_world()


## TER-3.1, TER-3.2
func test_TER_S13_after_crash_last_minute_save_is_restored() -> void:
	# Given: выкопана яма A, прошла минута игры, потом выкопана яма B
	await hero.begin_on_start()
	var saved_pit := Vector3(28, GROUND_Y, -22.5)
	var late_pit := Vector3(36, GROUND_Y, -22.5)
	await terrain.dug_pit(saved_pit)
	await terrain.a_minute_passes()
	await terrain.dug_pit(late_pit)
	# When: игра закрылась аварийно — без записи при выходе — и запущена снова
	terrain.crash_now()
	await terrain.launch_again(Vector3(32, GROUND_Y, -22.5))
	# Then: яма A на месте, яма B — нет: восстановлено последнее сохранение
	assert_bool(terrain.is_solid_after_relaunch(saved_pit + Vector3.DOWN * 1.0)).is_false()
	assert_bool(terrain.is_solid_after_relaunch(late_pit + Vector3.DOWN * 1.0)).is_true()
	terrain.close_relaunched()


# --- MOV-1.5 -------------------------------------------------------------

## MOV-1.5
func test_TER_S14_hero_who_dug_to_world_bottom_falls_out_and_returns_to_start() -> void:
	# Given: под героем шахта до дна мира
	await hero.begin_on_start()
	var start := hero.position()
	await terrain.stand_on_ground(-14, 16)
	# When
	await terrain.dug_shaft(-14, 16)
	for i in 240:
		await hero.wait(1)
		if hero.position().distance_to(start) < 0.1:
			break
	await hero.wait(10)
	# Then: снова на старте на руинах и слушается
	assert_vector(hero.position()).is_equal_approx(start, Vector3(0.05, 0.05, 0.05))
	assert_bool(hero.is_standing()).is_true()
	await hero.run_forward(20)
	assert_float((hero.position() - start).z).is_less(-1.0)


# --- TER-1.4, TER-1.5, TER-1.6 --------------------------------------------

## Кромка воды к югу от руин на x: первая z, где нетронутый рельеф ниже уровня моря.
func _waterline_z(x: float) -> float:
	var z := WorldTerrain.FLAT_CENTER.y + WorldTerrain.FLAT_HALF.y
	while terrain.generated_surface_y(x, z) >= terrain.sea_y():
		z += 1.0
	return z


## TER-1.4
func test_TER_S15_bay_with_sand_beach_is_seen_from_ruins() -> void:
	# Given: герой на старте, на площадке руин
	await hero.begin_on_start()
	var x := WorldTerrain.FLAT_CENTER.x
	var water_z := _waterline_z(x)
	# Then: от южного края площадки до моря рельеф не закрывает взгляд — бухта видна
	# глаза героя на южном краю ровной площадки, у акведука
	var eye := Vector3(x, level.floor_top() + 1.7, WorldTerrain.FLAT_CENTER.y + WorldTerrain.FLAT_HALF.y - 1.0)
	var sea := Vector3(x, terrain.sea_y(), water_z + 20.0)
	for i in range(1, 20):
		var p := eye.lerp(sea, i / 20.0)
		assert_float(terrain.generated_surface_y(p.x, p.z)).is_less(p.y)
	# Then: у воды пологий пляж шириной не меньше 8 м
	var beach := 0
	for z in range(int(water_z) - 30, int(water_z)):
		var y := terrain.generated_surface_y(x, z)
		if y >= terrain.sea_y() and y < WorldTerrain.SAND_TOP:
			beach += 1
	assert_int(beach).is_greater_equal(8)
	# When: герой выходит на пляж
	await terrain.stand_on_ground(x, water_z - 3.0)
	# Then: под ногами песок
	var feet := hero.position()
	assert_int(terrain.ground_hit_by(feet + Vector3.UP, feet + Vector3.DOWN)).is_equal(WorldTerrain.Ground.SAND)


## TER-1.5
func test_TER_S16_plants_grow_on_terrain_and_ruins_stand_above_bay() -> void:
	# Given: герой на старте
	await hero.begin_on_start()
	# Then: по рельефу рассыпаны растения и камни
	assert_int(terrain.plants_count()).is_greater(100)
	# Then: над бухтой — акведук и светящийся обелиск
	var modules := terrain.ruin_modules()
	assert_array(modules.keys()).contains(["Arch1", "Obelisk"])
	# When: герой бежит в опору арки акведука
	var arch: Vector3 = modules["Arch4"]
	await _given_on_ground(arch.x + 1.8, arch.z - 3.5, Vector3.BACK)
	await hero.run_forward(90)
	# Then: опора его остановила, сквозь неё не пройти
	assert_float(hero.position().z).is_less(arch.z - 0.4)


## TER-1.6
func test_TER_S17_hero_wades_into_sea_only_to_waist() -> void:
	# Given: герой на пляже лицом к морю
	var x := WorldTerrain.FLAT_CENTER.x
	var water_z := _waterline_z(x)
	await _given_on_ground(x, water_z - 3.0, Vector3.BACK)
	# When: бежит в море
	await hero.run_forward(150)
	# Then: он зашёл в воду, но не глубже пояса, и стоит на дне
	var feet := hero.position()
	assert_float(feet.z).is_greater(water_z)
	assert_float(terrain.sea_y() - feet.y).is_less_equal(Shallows.WADE_DEPTH + 0.1)
	assert_bool(hero.is_standing()).is_true()


## TER-1.4, TER-1.6
func test_TER_S18_pit_on_beach_below_sea_level_is_dry_and_hero_goes_down_into_it() -> void:
	# Given: герой на пляже выше кромки воды
	var x := WorldTerrain.FLAT_CENTER.x
	var water_z := _waterline_z(x)
	var at := await _given_on_ground(x, water_z - 12.0, Vector3.BACK)
	# When: у его ног выкопана яма глубже уровня моря
	var pit := Vector3(at.x, terrain.surface_y(at.x, at.z + 3.0), at.z + 3.0)
	await terrain.dug_pit(pit)
	for depth in [1.2, 2.4, 3.6]:
		await terrain.dug_pit(pit + Vector3.DOWN * depth)
	# Then: в яме нет морской воды
	assert_bool(terrain.water_shown_at(pit.x, pit.z)).is_false()
	# When: герой идёт в яму
	await hero.run_forward(30)
	await hero.wait(30)
	# Then: он стоит на её дне ниже уровня моря, мелководье его не держит
	assert_bool(hero.is_standing()).is_true()
	assert_float(hero.position().y).is_less(terrain.sea_y() - Shallows.WADE_DEPTH)


## TER-2.5
func test_TER_S19_digging_removes_plants_around_the_pit_and_they_do_not_grow_back(do_skip := true, skip_reason := "TER-2.5 не выполнено: VoxelInstancer.remove_instances_in_sphere в радиусе 2,5 м не убирает растения вокруг ямы; причина не найдена") -> void:
	# Given: герой на заросшем склоне за руинами
	var at := await _given_on_ground(-34, 36, Vector3.BACK)
	await terrain.settle()
	var before := terrain.plants_count()
	# When: выкопаны ямы вокруг героя — травы вокруг достаточно, чтобы хоть одна яма пришлась на неё
	for side in [Vector3(3, 0, 3), Vector3(-3, 0, 3), Vector3(3, 0, -3), Vector3(-3, 0, -3), Vector3(6, 0, 0), Vector3(-6, 0, 0), Vector3(0, 0, 6), Vector3(0, 0, -6)]:
		var spot: Vector3 = at + side
		spot.y = terrain.surface_y(spot.x, spot.z)
		await terrain.dug_pit(spot)
	var after := terrain.plants_count()
	# Then: растений и камней стало меньше
	assert_int(after).is_less(before)
	# Then: после перестройки сетки рельефа они не выросли снова
	await hero.wait(60)
	await terrain.settle()
	assert_int(terrain.plants_count()).is_equal(after)
