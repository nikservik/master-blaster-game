extends GdUnitTestSuite

## Технические тесты сетки постройки: привязка ячеек и четвертей, поворот, этажи,
## касание, ближайшая постройка и проверка пересечений.

const K := BuildPart.Kind


func test_snap_axis_cells_go_to_even_lines_quarters_to_whole_lines() -> void:
	assert_float(Building.snap_axis(0.2, 2.0)).is_equal(1.0)
	assert_float(Building.snap_axis(2.9, 2.0)).is_equal(3.0)
	assert_float(Building.snap_axis(-0.4, 2.0)).is_equal(-1.0)
	assert_float(Building.snap_axis(2.9, 1.0)).is_equal(2.5)
	assert_float(Building.snap_axis(-0.4, 1.0)).is_equal(-0.5)
	assert_float(Building.snap_axis(1.2, 4.0)).is_equal(2.0)


func test_half_foundation_rotates_within_cell() -> void:
	var aim := Vector3(2.5, 0, 1.0)
	assert_vector(Building.snap(K.FOUNDATION, 1, 0, aim)).is_equal(Vector2(3, 1.5))
	assert_vector(Building.snap(K.FOUNDATION, 1, 1, aim)).is_equal(Vector2(2.5, 1))
	var turned := Building.part_bounds(K.FOUNDATION, 1, 1, Vector2(2.5, 1), 0)
	assert_vector(turned.size).is_equal_approx(Vector3(1, 0.2, 2), Vector3.ONE * 0.001)


func test_wall_goes_to_nearest_grid_line() -> void:
	assert_vector(Building.snap(K.WALL, 0, 0, Vector3(1.3, 0, 0.3))).is_equal(Vector2(1, 0))
	assert_vector(Building.snap(K.WALL, 1, 0, Vector3(1.3, 0, 0.7))).is_equal(Vector2(1.5, 1))
	assert_vector(Building.snap(K.WALL, 0, 1, Vector3(1.6, 0, 0.3))).is_equal(Vector2(2, 1))


func test_levels_are_3_m_apart_above_foundation_top() -> void:
	assert_int(Building.level_at(0.0)).is_equal(0)
	assert_int(Building.level_at(0.1)).is_equal(0)
	assert_int(Building.level_at(3.1)).is_equal(1)
	assert_int(Building.level_at(-2.0)).is_equal(0)
	assert_float(Building.level_y(2)).is_equal_approx(6.1, 0.0001)


func test_stairs_rise_one_storey_over_two_cells() -> void:
	var bounds := Building.part_bounds(K.STAIRS, 0, 2, Vector2(1, 2), 0)
	assert_vector(bounds.size).is_equal_approx(Vector3(2, 3, 4), Vector3.ONE * 0.001)
	assert_float(bounds.end.y).is_equal_approx(Building.level_y(1), 0.0001)


func test_touching_needs_contact_not_just_proximity() -> void:
	var building := auto_free(Building.new()) as Building
	building.add_part(K.FOUNDATION, 0, 0, Vector2(1, 1), 0)
	var wall_on_edge := Building.part_bounds(K.WALL, 0, 0, Vector2(1, 2), 0)
	var wall_apart := Building.part_bounds(K.WALL, 0, 0, Vector2(1, 3), 0)
	var slab_above := Building.part_bounds(K.FLOOR, 0, 0, Vector2(1, 1), 1)
	assert_bool(building.touches(wall_on_edge)).is_true()
	assert_bool(building.touches(wall_apart)).is_false()
	assert_bool(building.touches(slab_above)).is_false()


func test_distance_to_building_is_measured_from_nearest_part() -> void:
	var building := auto_free(Building.new()) as Building
	building.add_part(K.FOUNDATION, 0, 0, Vector2(1, 1), 0)
	assert_float(building.distance_to(Vector3(1, 0, 1))).is_equal(0.0)
	assert_float(building.distance_to(Vector3(5, 0, 1))).is_equal_approx(3.0, 0.0001)
	assert_float(building.distance_to(Vector3(4, 0, 6))).is_equal_approx(sqrt(4.0 + 16.0), 0.0001)


func test_overlap_ignores_touching_and_wall_corners_but_finds_real_overlap() -> void:
	var builder := auto_free(Builder.new()) as Builder
	add_child(builder)
	builder.set_physics_process(false)
	var building := Building.new()
	builder.add_child(building)
	building.add_part(K.FOUNDATION, 0, 0, Vector2(1, 1), 0)
	building.add_part(K.WALL, 0, 0, Vector2(1, 0), 0)
	await get_tree().physics_frame
	await get_tree().physics_frame
	var shrink := Builder.OVERLAP_SHRINK
	var corner_wall := Building.part_transform(Vector2(0, 1), 0, 1)
	var same_wall := Building.part_transform(Vector2(1, 0), 0, 0)
	var next_foundation := Building.part_transform(Vector2(3, 1), 0, 0)
	assert_bool(builder._overlaps(BuildPart.solids(K.WALL, 0, shrink), corner_wall)).is_false()
	assert_bool(builder._overlaps(BuildPart.solids(K.FOUNDATION, 0, shrink), next_foundation)).is_false()
	assert_bool(builder._overlaps(BuildPart.solids(K.WALL, 0, shrink), same_wall)).is_true()
