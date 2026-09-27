class_name BuildItem
extends StaticBody3D

## Свободный предмет: ящик или стол. Начало координат — в центре основания.

enum Kind { BOX, TABLE }

const BOX_SIZE := Vector3(0.8, 0.8, 0.8)
const TABLE_SIZE := Vector3(1.4, 0.75, 0.8)
## Вид — модели assets/props/ по размерам предметов; начало модели — в центре основания, как у предмета.
const MODELS := {
	Kind.BOX: preload("res://assets/props/crate.gltf"),
	Kind.TABLE: preload("res://assets/props/table.gltf"),
}

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
	var view := (MODELS[kind] as PackedScene).instantiate()
	view.name = "View"
	add_child(view)
