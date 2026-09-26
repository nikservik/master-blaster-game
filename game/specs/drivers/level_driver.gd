extends RefCounted

## Драйвер спек: места площадки руин, нужные сценариям. Размеры читаются из самой сцены.

## Уступ; ближняя грань обращена к старту (+Z).
class Ledge:
	var top: float
	var center_x: float
	var near_face_z: float


var _level: Node3D


func _init(level: Node3D) -> void:
	_level = level


func low_ledge() -> Ledge:
	return _ledge(&"LowLedge")


func high_ledge() -> Ledge:
	return _ledge(&"HighLedge")


func floor_top() -> float:
	var floor_box := _box(&"Floor")
	return floor_box.global_position.y + floor_box.size.y / 2.0


## Точка на полу перед уступом, на заданном расстоянии от ближней грани.
func spot_before_ledge(ledge: Ledge, distance: float) -> Vector3:
	return Vector3(ledge.center_x, floor_top(), ledge.near_face_z + distance)


## Грань задней стены, обращённая к площадке.
func back_wall_face_z() -> float:
	var wall := _box(&"BackWall")
	return wall.global_position.z - wall.size.z / 2.0


## Точка на полу спиной к задней стене: камера по умолчанию оказывается за стеной.
func spot_with_back_to_wall(distance: float) -> Vector3:
	return Vector3(0.0, floor_top(), back_wall_face_z() - distance)


## Край пола в сторону -Z, за ним обрыв.
func edge_z() -> float:
	var floor_box := _box(&"Floor")
	return floor_box.global_position.z - floor_box.size.z / 2.0


func spot_before_edge(distance: float) -> Vector3:
	return Vector3(0.0, floor_top(), edge_z() + distance)


func _ledge(node_name: StringName) -> Ledge:
	var box := _box(node_name)
	var ledge := Ledge.new()
	ledge.top = box.global_position.y + box.size.y / 2.0
	ledge.center_x = box.global_position.x
	ledge.near_face_z = box.global_position.z + box.size.z / 2.0
	return ledge


func _box(node_name: StringName) -> CSGBox3D:
	return _level.get_node(NodePath(node_name)) as CSGBox3D
