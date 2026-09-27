class_name BuildPart
extends StaticBody3D

## Деталь постройки. Координаты детали: начало — центр основания на уровне пола этажа,
## длина — вдоль X, лестница поднимается в сторону −Z. Поворот задаётся постройкой четвертями оборота.

enum Kind { FOUNDATION, FLOOR, WALL, DOOR_WALL, STAIRS }

## Размеры по X и Z для каждого вида; Tab перебирает их по порядку.
const SIZES := {
	Kind.FOUNDATION: [Vector2(2, 2), Vector2(2, 1), Vector2(1, 1)],
	Kind.FLOOR: [Vector2(2, 2), Vector2(2, 1), Vector2(1, 1)],
	Kind.WALL: [Vector2(2, 0.2), Vector2(1, 0.2)],
	Kind.DOOR_WALL: [Vector2(2, 0.2)],
	Kind.STAIRS: [Vector2(2, 4)],
}
const SLAB := 0.2
const WALL_THICKNESS := 0.2
## Стена от пола этажа до низа перекрытия следующего: 3 м этажа минус толщина плиты.
const WALL_HEIGHT := 2.8
const DOOR_WIDTH := 1.0
const DOOR_HEIGHT := 2.2
const STAIRS_RISE := 3.0
const STAIRS_STEPS := 10

const COLORS := {
	Kind.FOUNDATION: Color(0.55, 0.53, 0.5),
	Kind.FLOOR: Color(0.6, 0.45, 0.3),
	Kind.WALL: Color(0.78, 0.72, 0.6),
	Kind.DOOR_WALL: Color(0.78, 0.72, 0.6),
	Kind.STAIRS: Color(0.5, 0.36, 0.24),
}

var kind: Kind
var size_index: int
var level: int
var quarter_turns: int


static func footprint(part_kind: Kind, part_size: int) -> Vector2:
	return SIZES[part_kind][part_size]


## Габарит детали в её координатах — для проверки касания соседей.
static func local_bounds(part_kind: Kind, part_size: int) -> AABB:
	var f := footprint(part_kind, part_size)
	match part_kind:
		Kind.FOUNDATION, Kind.FLOOR:
			return AABB(Vector3(-f.x / 2.0, -SLAB, -f.y / 2.0), Vector3(f.x, SLAB, f.y))
		Kind.STAIRS:
			return AABB(Vector3(-f.x / 2.0, 0.0, -f.y / 2.0), Vector3(f.x, STAIRS_RISE, f.y))
		_:
			return AABB(Vector3(-f.x / 2.0, 0.0, -WALL_THICKNESS / 2.0), Vector3(f.x, WALL_HEIGHT, WALL_THICKNESS))


## Твёрдые формы детали в её координатах: пары [Shape3D, Transform3D].
## shrink уменьшает каждую форму со всех сторон — так касание не считается пересечением.
static func solids(part_kind: Kind, part_size: int, shrink := Vector3.ZERO) -> Array:
	var f := footprint(part_kind, part_size)
	match part_kind:
		Kind.FOUNDATION, Kind.FLOOR:
			return [_box(Vector3(0, -SLAB / 2.0, 0), Vector3(f.x, SLAB, f.y), shrink)]
		Kind.WALL:
			return [_box(Vector3(0, WALL_HEIGHT / 2.0, 0), Vector3(f.x, WALL_HEIGHT, WALL_THICKNESS), shrink)]
		Kind.DOOR_WALL:
			var side := (f.x - DOOR_WIDTH) / 2.0
			var lintel := WALL_HEIGHT - DOOR_HEIGHT
			return [
				_box(Vector3(-(DOOR_WIDTH + side) / 2.0, WALL_HEIGHT / 2.0, 0), Vector3(side, WALL_HEIGHT, WALL_THICKNESS), shrink),
				_box(Vector3((DOOR_WIDTH + side) / 2.0, WALL_HEIGHT / 2.0, 0), Vector3(side, WALL_HEIGHT, WALL_THICKNESS), shrink),
				_box(Vector3(0, DOOR_HEIGHT + lintel / 2.0, 0), Vector3(DOOR_WIDTH, lintel, WALL_THICKNESS), shrink),
			]
		_:
			# Лестница — сплошной клин: низ у +Z на полу этажа, верх у −Z на полу следующего.
			var hx := f.x / 2.0 - shrink.x
			var hz := f.y / 2.0 - shrink.z
			var wedge := ConvexPolygonShape3D.new()
			wedge.points = PackedVector3Array([
				Vector3(-hx, shrink.y, hz), Vector3(hx, shrink.y, hz),
				Vector3(-hx, shrink.y, -hz), Vector3(hx, shrink.y, -hz),
				Vector3(-hx, STAIRS_RISE - shrink.y, -hz), Vector3(hx, STAIRS_RISE - shrink.y, -hz),
			])
			return [[wedge, Transform3D.IDENTITY]]


static func _box(center: Vector3, size: Vector3, shrink: Vector3) -> Array:
	var shape := BoxShape3D.new()
	shape.size = (size - shrink * 2.0).max(Vector3.ONE * 0.01)
	return [shape, Transform3D(Basis.IDENTITY, center)]


## Собирает деталь: видимые формы и, если это не призрак, коллизию.
func setup(part_kind: Kind, part_size: int, ghost: bool) -> void:
	kind = part_kind
	size_index = part_size
	collision_layer = Builder.CONSTRUCTION_LAYERS
	collision_mask = 0
	var material := StandardMaterial3D.new()
	material.albedo_color = COLORS[kind]
	if not ghost:
		for solid in solids(kind, size_index):
			var collision := CollisionShape3D.new()
			collision.shape = solid[0]
			collision.transform = solid[1]
			add_child(collision)
	if kind == Kind.STAIRS:
		_add_steps(material)
	else:
		for solid in solids(kind, size_index):
			var mesh := BoxMesh.new()
			mesh.size = (solid[0] as BoxShape3D).size
			mesh.material = material
			var view := MeshInstance3D.new()
			view.mesh = mesh
			view.transform = solid[1]
			add_child(view)


func _add_steps(material: StandardMaterial3D) -> void:
	var f := footprint(kind, size_index)
	var depth := f.y / STAIRS_STEPS
	var rise := STAIRS_RISE / STAIRS_STEPS
	for i in STAIRS_STEPS:
		var mesh := BoxMesh.new()
		mesh.size = Vector3(f.x, rise * (i + 1), depth)
		mesh.material = material
		var view := MeshInstance3D.new()
		view.mesh = mesh
		view.position = Vector3(0, rise * (i + 1) / 2.0, f.y / 2.0 - depth * (i + 0.5))
		add_child(view)
