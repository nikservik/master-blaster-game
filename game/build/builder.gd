class_name Builder
extends Node3D

## Режим строительства: выбор детали или предмета, призрак под прицелом, установка и уборка.
## Постройки и предметы — дочерние узлы строителя.

enum Slot { FOUNDATION, FLOOR, WALL, DOOR_WALL, STAIRS, BOX, TABLE }

const SLOT_PARTS := {
	Slot.FOUNDATION: BuildPart.Kind.FOUNDATION,
	Slot.FLOOR: BuildPart.Kind.FLOOR,
	Slot.WALL: BuildPart.Kind.WALL,
	Slot.DOOR_WALL: BuildPart.Kind.DOOR_WALL,
	Slot.STAIRS: BuildPart.Kind.STAIRS,
}
const SLOT_ITEMS := {Slot.BOX: BuildItem.Kind.BOX, Slot.TABLE: BuildItem.Kind.TABLE}
const SLOT_NAMES := ["Фундамент", "Перекрытие", "Стена", "Стена с проёмом", "Лестница", "Ящик", "Стол"]

## Слой 1 — мир, по нему ходит герой и упирается камера; слой 3 — постройки и предметы.
const CONSTRUCTION_LAYERS := 1 | 4
## Пересечения ищутся с героем (слой 2) и постройками с предметами (слой 3).
const OVERLAP_MASK := 2 | 4
## Проверяемая форма сжимается с каждой стороны: по горизонтали больше половины толщины стены,
## чтобы угол двух стен не считался пересечением, по вертикали — чуть-чуть, чтобы не считалось касание пола.
const OVERLAP_SHRINK := Vector3(0.11, 0.02, 0.11)
## Прицел ставит не дальше этого расстояния от героя (BLD-3.2).
const REACH := 8.0
## Грунт под углами нового фундамента ищется в пределах этой высоты выше и ниже точки прицела.
const GROUND_PROBE := 3.0
const ITEM_TURN_STEP := deg_to_rad(15.0)
const GHOST_GREEN := Color(0.2, 1.0, 0.35, 0.45)
const GHOST_RED := Color(1.0, 0.2, 0.2, 0.45)

@export var hero: Hero

var active := false
var slot := Slot.FOUNDATION
var size_index := 0
var quarter_turns := 0
var item_turn := 0.0

## Последнее попадание луча прицела: пусто, если луч ни во что не попал.
var _aim := {}
## Что и куда поставится сейчас: пусто, если прицел вне досягаемости.
var _plan := {}
var _ghost: Node3D
var _ghost_key := ""
var _ghost_material: StandardMaterial3D
var _hud: Label


func _ready() -> void:
	_ghost_material = StandardMaterial3D.new()
	_ghost_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_ghost_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var layer := CanvasLayer.new()
	add_child(layer)
	_hud = Label.new()
	_hud.position = Vector2(16, 16)
	layer.add_child(_hud)
	_update_hud()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"build_toggle"):
		active = not active
		_update_hud()
		return
	if not active:
		return
	for i in 7:
		if event.is_action_pressed(StringName("build_slot_%d" % (i + 1))):
			slot = i as Slot
			size_index = 0
	if event.is_action_pressed(&"build_size") and SLOT_PARTS.has(slot):
		size_index = (size_index + 1) % BuildPart.SIZES[SLOT_PARTS[slot]].size()
	elif event.is_action_pressed(&"build_rotate"):
		quarter_turns = (quarter_turns + 1) % 4
	elif event.is_action_pressed(&"build_turn_left"):
		item_turn += ITEM_TURN_STEP
	elif event.is_action_pressed(&"build_turn_right"):
		item_turn -= ITEM_TURN_STEP
	elif event.is_action_pressed(&"build_place"):
		_place()
	elif event.is_action_pressed(&"build_remove"):
		_remove()
	_update_hud()


func _physics_process(_delta: float) -> void:
	_aim = _cast_aim()
	_plan = {}
	if active and not _aim.is_empty() and hero.global_position.distance_to(_aim.position) <= REACH:
		_plan = _plan_part() if SLOT_PARTS.has(slot) else _plan_item()
	_show_ghost()


# --- Наблюдаемое состояние -----------------------------------------------

## Точка под прицелом, куда бы она ни попала; null, если луч ни во что не попал.
func aim_point() -> Variant:
	return null if _aim.is_empty() else _aim.position


func is_ghost_visible() -> bool:
	return _ghost != null and _ghost.visible


func is_ghost_green() -> bool:
	return is_ghost_visible() and bool(_plan.get("valid", false))


func ghost_transform() -> Transform3D:
	return _ghost.global_transform if _ghost else Transform3D()


func buildings() -> Array[Building]:
	var result: Array[Building] = []
	for child in get_children():
		if child is Building and not child.is_queued_for_deletion():
			result.append(child)
	return result


func items() -> Array[BuildItem]:
	var result: Array[BuildItem] = []
	for child in get_children():
		if child is BuildItem and child != _ghost and not child.is_queued_for_deletion():
			result.append(child)
	return result


# --- Прицел и план установки ---------------------------------------------

func _cast_aim() -> Dictionary:
	var ray := hero.camera_rig.aim_ray()
	var from: Vector3 = ray[0]
	var query := PhysicsRayQueryParameters3D.create(from, from + (ray[1] as Vector3) * (REACH * 3.0), 1)
	return get_world_3d().direct_space_state.intersect_ray(query)


func _camera_yaw() -> float:
	var forward := -get_viewport().get_camera_3d().global_basis.z
	return atan2(-forward.x, -forward.z)


func _nearest_building(point: Vector3) -> Building:
	var best: Building = null
	var best_distance := Building.NEAR
	for building in buildings():
		var d := building.distance_to(building.to_local(point))
		if d <= best_distance:
			best = building
			best_distance = d
	return best


func _plan_part() -> Dictionary:
	var kind: BuildPart.Kind = SLOT_PARTS[slot]
	var hit: Vector3 = _aim.position
	var building := _nearest_building(hit)
	if building == null:
		# Вдали от построек сетки нет: фундамент начинает новую постройку под углом камеры.
		var grid := Transform3D(Basis(Vector3.UP, _camera_yaw()), Vector3.ZERO)
		var r := Building.rotated_footprint(BuildPart.footprint(kind, size_index), quarter_turns)
		grid.origin = hit - grid.basis * Vector3(r.x / 2.0, 0.0, r.y / 2.0)
		# На неровном рельефе сетка горизонтальна и встаёт на самую высокую точку грунта под площадкой (BLD-1.5).
		grid.origin.y = _highest_ground(grid, r, hit.y)
		var center := Vector2(r.x / 2.0, r.y / 2.0)
		var valid := kind == BuildPart.Kind.FOUNDATION and _surface_is_ground()
		var world := grid * Building.part_transform(center, 0, quarter_turns)
		valid = valid and not _overlaps(BuildPart.solids(kind, size_index, OVERLAP_SHRINK), world)
		return {"valid": valid, "kind": kind, "world": world, "grid": grid, "center": center, "level": 0}

	var local := building.to_local(hit)
	var level := Building.level_at(local.y)
	if kind == BuildPart.Kind.FLOOR:
		level += 1
	var center := Building.snap(kind, size_index, quarter_turns, local)
	var world := building.global_transform * Building.part_transform(center, level, quarter_turns)
	var bounds := Building.part_bounds(kind, size_index, quarter_turns, center, level)
	var valid := building.touches(bounds)
	if kind == BuildPart.Kind.FOUNDATION and level != 0:
		valid = false
	valid = valid and not _overlaps(BuildPart.solids(kind, size_index, OVERLAP_SHRINK), world)
	return {"valid": valid, "kind": kind, "world": world, "building": building, "center": center, "level": level}


func _plan_item() -> Dictionary:
	var kind: BuildItem.Kind = SLOT_ITEMS[slot]
	var world := Transform3D(Basis(Vector3.UP, _camera_yaw() + item_turn), _aim.position)
	var collider: Object = _aim.collider
	var on_floor: bool = _aim.normal.y > 0.9 and not collider is BuildItem
	if collider is BuildPart:
		var part := collider as BuildPart
		on_floor = on_floor and (part.kind == BuildPart.Kind.FOUNDATION or part.kind == BuildPart.Kind.FLOOR)
	var valid := on_floor and not _overlaps([BuildItem.solid(kind, OVERLAP_SHRINK)], world)
	return {"valid": valid, "item": kind, "world": world}


## Самая высокая точка грунта под углами площадки размером r в сетке grid, но не ниже точки прицела.
func _highest_ground(grid: Transform3D, r: Vector2, aim_y: float) -> float:
	var space := get_world_3d().direct_space_state
	var highest := aim_y
	for corner in [Vector3.ZERO, Vector3(r.x, 0, 0), Vector3(0, 0, r.y), Vector3(r.x, 0, r.y)]:
		var p: Vector3 = grid * corner
		var ground: Variant = Building.ground_height(space, Vector3(p.x, aim_y + GROUND_PROBE, p.z), GROUND_PROBE * 2.0)
		if ground != null:
			highest = maxf(highest, ground)
	return highest


## Пол площадки — всё, что не постройка и не предмет.
func _surface_is_ground() -> bool:
	return _aim.normal.y > 0.9 and not _aim.collider is BuildPart and not _aim.collider is BuildItem


func _overlaps(shapes: Array, world: Transform3D) -> bool:
	var space := get_world_3d().direct_space_state
	for solid in shapes:
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = solid[0]
		query.transform = world * (solid[1] as Transform3D)
		query.collision_mask = OVERLAP_MASK
		if not space.intersect_shape(query, 1).is_empty():
			return true
	return false


# --- Действия ------------------------------------------------------------

func _place() -> void:
	if not bool(_plan.get("valid", false)):
		return
	if _plan.has("item"):
		var item := BuildItem.new()
		item.setup(_plan.item, false)
		add_child(item)
		item.global_transform = _plan.world
		return
	var building: Building = _plan.get("building")
	if building == null:
		building = Building.new()
		add_child(building)
		building.global_transform = _plan.grid
	var part := building.add_part(_plan.kind, size_index, quarter_turns, _plan.center, _plan.level)
	if part.kind == BuildPart.Kind.FOUNDATION:
		part.grow_supports()


func _remove() -> void:
	if _aim.is_empty() or hero.global_position.distance_to(_aim.position) > REACH:
		return
	var target: Object = _aim.collider
	if target is BuildItem:
		(target as Node).queue_free()
	elif target is BuildPart:
		var part := target as BuildPart
		var building := part.get_parent() as Building
		part.queue_free()
		if building.parts().is_empty():
			building.queue_free()


# --- Призрак и подсказка -------------------------------------------------

func _show_ghost() -> void:
	if _plan.is_empty():
		if _ghost:
			_ghost.visible = false
		return
	var key := "item%d" % _plan.item if _plan.has("item") else "part%d_%d" % [_plan.kind, size_index]
	if key != _ghost_key:
		if _ghost:
			_ghost.queue_free()
		_ghost = _make_ghost()
		_ghost_key = key
	_ghost.visible = true
	_ghost.global_transform = _plan.world
	_ghost_material.albedo_color = GHOST_GREEN if _plan.valid else GHOST_RED


func _make_ghost() -> Node3D:
	var ghost: Node3D
	if _plan.has("item"):
		var item := BuildItem.new()
		item.setup(_plan.item, true)
		ghost = item
	else:
		var part := BuildPart.new()
		part.setup(_plan.kind, size_index, true)
		ghost = part
	(ghost as CollisionObject3D).collision_layer = 0
	for child in ghost.get_children():
		if child is MeshInstance3D:
			(child as MeshInstance3D).material_override = _ghost_material
	add_child(ghost)
	return ghost


func _update_hud() -> void:
	if not active:
		_hud.text = ""
		return
	var text: String = "Строительство: " + SLOT_NAMES[slot]
	if SLOT_PARTS.has(slot):
		var f := BuildPart.footprint(SLOT_PARTS[slot], size_index)
		text += " %s × %s м" % [f.x, f.y] if slot != Slot.WALL and slot != Slot.DOOR_WALL else " %s м" % f.x
	_hud.text = text + "   [1–7] выбор  [Tab] размер  [R] поворот  [ЛКМ] поставить  [ПКМ] убрать  [B] выход"
