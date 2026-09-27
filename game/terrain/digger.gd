class_name Digger
extends Node

## Копание и насыпание ([TER-2]): вне режима строительства ЛКМ убирает шар грунта в точке прицела,
## ПКМ насыпает такой же. В режиме строительства мышь принадлежит строителю.

## Досягаемость: точка прицела не дальше этого расстояния от героя (TER-2.1).
const REACH := 6.0
## Длина луча прицела: от камеры за героем до точки в REACH от героя.
const RAY_LENGTH := 20.0
## Луч прицела видит слой 1: рельеф, руины, постройки и предметы.
const AIM_MASK := 1
## Насыпь не может задеть героя (слой 2).
const HERO_MASK := 2

@export var terrain: WorldTerrain
@export var hero: Hero
@export var builder: Builder


func _unhandled_input(event: InputEvent) -> void:
	if builder.active:
		return
	if event.is_action_pressed(&"dig"):
		var point: Variant = aim_point()
		if point != null:
			terrain.dig(point)
			hero.play_dig()
	elif event.is_action_pressed(&"fill"):
		var point: Variant = aim_point()
		if point != null and not _touches_hero(point):
			terrain.fill(point)
			hero.play_dig()


## Точка под прицелом в пределах досягаемости; null, если луч никуда не попал или точка далеко.
func aim_point() -> Variant:
	var ray := aim_ray()
	var from: Vector3 = ray[0]
	var query := PhysicsRayQueryParameters3D.create(from, from + (ray[1] as Vector3) * RAY_LENGTH, AIM_MASK)
	var hit := hero.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty() or hero.global_position.distance_to(hit.position) > REACH:
		return null
	return hit.position


## Луч прицела [начало, направление] — из камеры через центр экрана.
func aim_ray() -> Array:
	return hero.camera_rig.aim_ray()


func _touches_hero(center: Vector3) -> bool:
	var sphere := SphereShape3D.new()
	sphere.radius = WorldTerrain.BRUSH_RADIUS
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = sphere
	query.transform = Transform3D(Basis(), center)
	query.collision_mask = HERO_MASK
	return not hero.get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()
