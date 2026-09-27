extends GdUnitTestSuite

## Технические тесты сетки постройки: привязка ячеек и четвертей, поворот, этажи,
## касание, ближайшая постройка, проверка пересечений, грунт и опоры.

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


func _support_count(part: BuildPart) -> int:
	return part.get_children().filter(func(c): return String(c.name).begins_with("Support")).size()


func test_ground_skips_buildings_and_supports_stop_at_ground() -> void:
	var world := auto_free(Node3D.new()) as Node3D
	add_child(world)
	var ground := StaticBody3D.new()
	var box := CollisionShape3D.new()
	box.shape = BoxShape3D.new()
	(box.shape as BoxShape3D).size = Vector3(20, 1, 20)
	box.position = Vector3(0, -0.5, 0)
	ground.add_child(box)
	world.add_child(ground)
	var floating := Building.new()
	world.add_child(floating)
	floating.position = Vector3(0, 1.0, 0)
	var on_ground := Building.new()
	world.add_child(on_ground)
	on_ground.position = Vector3(5, 0, 0)
	await get_tree().physics_frame
	# Фундамент в метре над землёй: четыре столба от низа плиты (0,9 м) до земли
	var high := floating.add_part(K.FOUNDATION, 0, 0, Vector2(1, 1), 0)
	high.grow_supports()
	assert_int(_support_count(high)).is_equal(4)
	# Фундамент на земле: низ плиты под землёй, столбов нет
	var low := on_ground.add_part(K.FOUNDATION, 0, 0, Vector2(1, 1), 0)
	low.grow_supports()
	assert_int(_support_count(low)).is_equal(0)
	await get_tree().physics_frame
	await get_tree().physics_frame
	# Грунт под постройкой — земля, а не плита и не столбы
	var space := world.get_world_3d().direct_space_state
	assert_float(Building.ground_height(space, Vector3(1, 5, 1), 10.0)).is_equal_approx(0.0, 0.001)
	assert_float(Building.ground_height(space, Vector3(0.1, 5, 0.1), 10.0)).is_equal_approx(0.0, 0.001)
	assert_object(Building.ground_height(space, Vector3(1, 5, 1), 2.0)).is_null()


## Габарит всех мешей узла в его координатах.
func _view_bounds(node: Node3D) -> AABB:
	var total := AABB()
	var first := true
	for mesh in node.find_children("*", "MeshInstance3D", true, false):
		var box: AABB = node.global_transform.affine_inverse() * (mesh as MeshInstance3D).global_transform * (mesh as MeshInstance3D).get_aabb()
		total = box if first else total.merge(box)
		first = false
	return total


func test_models_fit_part_and_item_bounds_and_ghost_paints_every_mesh() -> void:
	var builder := auto_free(Builder.new()) as Builder
	add_child(builder)
	builder.set_physics_process(false)
	for kind in BuildPart.SIZES:
		for size in BuildPart.SIZES[kind].size():
			var part := BuildPart.new()
			part.setup(kind, size, true)
			builder.add_child(part)
			# Модель стоит в координатах детали: её габарит — габарит детали; перемычка проёма выступает на 2 см
			var bounds := BuildPart.local_bounds(kind, size)
			var view := _view_bounds(part)
			assert_vector(view.position).is_equal_approx(bounds.position, Vector3.ONE * 0.03)
			assert_vector(view.end).is_equal_approx(bounds.end, Vector3.ONE * 0.03)
			if kind == K.STAIRS:
				# Лестница модели поднимается к −Z, как клин коллизии: верхние вершины — у −Z
				var mesh := part.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D
				for v: Vector3 in mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]:
					if v.y > BuildPart.STAIRS_RISE - 0.1:
						assert_float(v.z).is_less(-1.5)
			# Призрак красит все меши glTF, включая вложенные, полупрозрачным материалом
			builder._paint_ghost(part)
			for mesh in part.find_children("*", "MeshInstance3D", true, false):
				var material := (mesh as MeshInstance3D).material_override as BaseMaterial3D
				assert_object(material).is_not_null()
				assert_int(material.transparency).is_equal(BaseMaterial3D.TRANSPARENCY_ALPHA)
			part.free()
	for kind in [BuildItem.Kind.BOX, BuildItem.Kind.TABLE]:
		var item := BuildItem.new()
		item.setup(kind, true)
		builder.add_child(item)
		var view := _view_bounds(item)
		var size := BuildItem.size_of(kind)
		assert_vector(view.position).is_equal_approx(Vector3(-size.x / 2.0, 0, -size.z / 2.0), Vector3.ONE * 0.01)
		assert_vector(view.end).is_equal_approx(Vector3(size.x / 2.0, size.y, size.z / 2.0), Vector3.ONE * 0.01)
		item.free()
