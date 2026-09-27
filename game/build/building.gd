class_name Building
extends Node3D

## Постройка: своя сетка, выровненная по первому фундаменту. Начало координат — на земле
## в углу сетки; ячейка 2 × 2 м, четверть 1 × 1 м, этаж 3 м. Детали — дочерние узлы.

const CELL := 2.0
const FLOOR_HEIGHT := 3.0
## Пол нулевого этажа — верх фундамента над землёй. Выше капсула героя на ступень не заходит.
const BASE := 0.1
## Насколько далеко от деталей постройки прицел ещё привязывается к её сетке.
const NEAR := 2.0
## Зазор, в пределах которого детали считаются касающимися.
const TOUCH := 0.05


## Высота грунта под точкой: первое попадание луча вниз в слой 1 мимо построек и предметов.
## Грунт — любое тело, кроме построек: площадка, рельеф. null, если в пределах depth грунта нет.
static func ground_height(space: PhysicsDirectSpaceState3D, from: Vector3, depth: float) -> Variant:
	var query := PhysicsRayQueryParameters3D.create(from, from + Vector3.DOWN * depth, 1)
	while true:
		var hit := space.intersect_ray(query)
		if hit.is_empty():
			return null
		if not (hit.collider is BuildPart or hit.collider is BuildItem):
			return (hit.position as Vector3).y
		query.exclude += [hit.rid]
	return null


static func level_y(level: int) -> float:
	return BASE + level * FLOOR_HEIGHT


## Этаж, на полу которого лежит точка с высотой y в координатах постройки.
static func level_at(y: float) -> int:
	return maxi(0, roundi((y - BASE) / FLOOR_HEIGHT))


## Размер детали по осям постройки с учётом поворота на четверти оборота.
static func rotated_footprint(footprint: Vector2, quarter_turns: int) -> Vector2:
	return Vector2(footprint.y, footprint.x) if quarter_turns % 2 == 1 else footprint


## Привязка по одной оси: размер 2 и 4 м — к чётным линиям ячеек, 1 м — к линиям четвертей.
static func snap_axis(h: float, extent: float) -> float:
	if extent >= CELL:
		return CELL * roundf((h - extent / 2.0) / CELL) + extent / 2.0
	return floorf(h) + extent / 2.0


## Центр детали в сетке (x, z) по точке прицела в координатах постройки.
## Стена встаёт на ближайшую линию сетки, её длина привязывается как размер детали.
static func snap(kind: BuildPart.Kind, size_index: int, quarter_turns: int, aim: Vector3) -> Vector2:
	var f := BuildPart.footprint(kind, size_index)
	if kind == BuildPart.Kind.WALL or kind == BuildPart.Kind.DOOR_WALL:
		if quarter_turns % 2 == 0:
			return Vector2(snap_axis(aim.x, f.x), roundf(aim.z))
		return Vector2(roundf(aim.x), snap_axis(aim.z, f.x))
	var r := rotated_footprint(f, quarter_turns)
	return Vector2(snap_axis(aim.x, r.x), snap_axis(aim.z, r.y))


static func part_transform(center: Vector2, level: int, quarter_turns: int) -> Transform3D:
	return Transform3D(Basis(Vector3.UP, quarter_turns * PI / 2.0), Vector3(center.x, level_y(level), center.y))


## Габарит детали в координатах постройки.
static func part_bounds(kind: BuildPart.Kind, size_index: int, quarter_turns: int, center: Vector2, level: int) -> AABB:
	return part_transform(center, level, quarter_turns) * BuildPart.local_bounds(kind, size_index)


func parts() -> Array[BuildPart]:
	var result: Array[BuildPart] = []
	for child in get_children():
		if child is BuildPart and not child.is_queued_for_deletion():
			result.append(child)
	return result


func add_part(kind: BuildPart.Kind, size_index: int, quarter_turns: int, center: Vector2, level: int) -> BuildPart:
	var part := BuildPart.new()
	part.setup(kind, size_index, false)
	part.level = level
	part.quarter_turns = quarter_turns
	part.transform = part_transform(center, level, quarter_turns)
	add_child(part)
	return part


func bounds_of(part: BuildPart) -> AABB:
	return part.transform * BuildPart.local_bounds(part.kind, part.size_index)


## Касается ли габарит хотя бы одной детали постройки (BLD-2.3).
func touches(bounds: AABB) -> bool:
	var grown := bounds.grow(TOUCH)
	for part in parts():
		if grown.intersects(bounds_of(part)):
			return true
	return false


## Расстояние по горизонтали от точки (координаты постройки) до ближайшей детали; INF, если деталей нет.
func distance_to(point: Vector3) -> float:
	var best := INF
	for part in parts():
		var b := bounds_of(part)
		var dx := maxf(maxf(b.position.x - point.x, point.x - b.end.x), 0.0)
		var dz := maxf(maxf(b.position.z - point.z, point.z - b.end.z), 0.0)
		best = minf(best, Vector2(dx, dz).length())
	return best
