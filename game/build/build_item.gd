class_name BuildItem
extends StaticBody3D

## Свободный предмет: ящик или стол. Начало координат — в центре основания.

enum Kind { BOX, TABLE }

const BOX_SIZE := Vector3(0.8, 0.8, 0.8)
const TABLE_SIZE := Vector3(1.4, 0.75, 0.8)
const TABLE_TOP := 0.08
const TABLE_LEG := 0.08

var kind: Kind


static func size_of(item_kind: Kind) -> Vector3:
	return BOX_SIZE if item_kind == Kind.BOX else TABLE_SIZE


## Твёрдая форма предмета — один бокс по габариту: [Shape3D, Transform3D].
static func solid(item_kind: Kind, shrink := Vector3.ZERO) -> Array:
	var size := size_of(item_kind)
	var shape := BoxShape3D.new()
	shape.size = size - shrink * 2.0
	return [shape, Transform3D(Basis.IDENTITY, Vector3(0, size.y / 2.0, 0))]


func setup(item_kind: Kind, ghost: bool) -> void:
	kind = item_kind
	collision_layer = Builder.CONSTRUCTION_LAYERS
	collision_mask = 0
	if not ghost:
		var s := solid(kind)
		var collision := CollisionShape3D.new()
		collision.shape = s[0]
		collision.transform = s[1]
		add_child(collision)
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(0.55, 0.38, 0.2) if kind == Kind.BOX else Color(0.62, 0.46, 0.3)
	var size := size_of(kind)
	if kind == Kind.BOX:
		_add_box(Vector3(0, size.y / 2.0, 0), size, material)
	else:
		_add_box(Vector3(0, size.y - TABLE_TOP / 2.0, 0), Vector3(size.x, TABLE_TOP, size.z), material)
		var leg_height := size.y - TABLE_TOP
		for sx in [-1.0, 1.0]:
			for sz in [-1.0, 1.0]:
				var leg_at := Vector3(sx * (size.x / 2.0 - TABLE_LEG), leg_height / 2.0, sz * (size.z / 2.0 - TABLE_LEG))
				_add_box(leg_at, Vector3(TABLE_LEG, leg_height, TABLE_LEG), material)


func _add_box(center: Vector3, size: Vector3, material: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = material
	var view := MeshInstance3D.new()
	view.mesh = mesh
	view.position = center
	add_child(view)
