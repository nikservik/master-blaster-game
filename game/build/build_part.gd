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
## Опора фундамента — столб 0,2 × 0,2 м в углу плиты; грунт ищется не глубже SUPPORT_DEPTH под плитой.
## Вид столба — модель 0,3 × 0,3 м на той же оси: она выступает за край плиты на 5 см.
const SUPPORT := 0.2
const SUPPORT_DEPTH := 20.0

## Вид детали — модели assets/building/ в порядке размеров SIZES. Начало и оси моделей
## совпадают с координатами детали, поэтому модель встаёт без смещения и поворота.
const MODELS := {
	Kind.FOUNDATION: [
		preload("res://assets/building/foundation_2x2.gltf"),
		preload("res://assets/building/foundation_2x1.gltf"),
		preload("res://assets/building/foundation_1x1.gltf"),
	],
	Kind.FLOOR: [
		preload("res://assets/building/floor_2x2.gltf"),
		preload("res://assets/building/floor_2x1.gltf"),
		preload("res://assets/building/floor_1x1.gltf"),
	],
	Kind.WALL: [preload("res://assets/building/wall_2m.gltf"), preload("res://assets/building/wall_1m.gltf")],
	Kind.DOOR_WALL: [preload("res://assets/building/wall_door_2m.gltf")],
	Kind.STAIRS: [preload("res://assets/building/stairs_2x4.gltf")],
}
## Опора: от 0 вниз до −1 м; длину до грунта задаёт масштаб по Y.
const POST := preload("res://assets/building/post_1m.gltf")

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


## Собирает деталь: вид из модели и, если это не призрак, коллизию.
func setup(part_kind: Kind, part_size: int, ghost: bool) -> void:
	kind = part_kind
	size_index = part_size
	collision_layer = Builder.CONSTRUCTION_LAYERS
	collision_mask = 0
	if not ghost:
		for solid in solids(kind, size_index):
			var collision := CollisionShape3D.new()
			collision.shape = solid[0]
			collision.transform = solid[1]
			add_child(collision)
	var view := (MODELS[kind][size_index] as PackedScene).instantiate()
	view.name = "View"
	add_child(view)


## Опоры фундамента (BLD-1.5): столбы в углах плиты от её низа вниз до грунта. Где грунт не ниже
## низа плиты, опоры нет. Деталь уже стоит в мире; рельеф не меняется.
## Призрак зовёт это после каждого сдвига, без коллизии (solid = false): прежние столбы заменяются.
## Поставленная деталь зовёт один раз, с коллизией.
func grow_supports(solid := true) -> void:
	for child in get_children():
		if String(child.name).begins_with("Support"):
			remove_child(child)
			child.free()
	var f := footprint(kind, size_index)
	var space := get_world_3d().direct_space_state
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var top := Vector3(sx * (f.x - SUPPORT) / 2.0, -SLAB, sz * (f.y - SUPPORT) / 2.0)
			# Луч сверху: изнутри рельефа луч его поверхность не видит.
			var probe := to_global(top) + Vector3.UP * Building.FLOOR_HEIGHT
			var ground: Variant = Building.ground_height(space, probe, Building.FLOOR_HEIGHT + SUPPORT_DEPTH)
			if ground == null:
				continue
			var length: float = to_global(top).y - float(ground)
			if length <= 0.0:
				continue
			if solid:
				var s := _box(top + Vector3.DOWN * length / 2.0, Vector3(SUPPORT, length, SUPPORT), Vector3.ZERO)
				var collision := CollisionShape3D.new()
				collision.shape = s[0]
				collision.transform = s[1]
				add_child(collision)
			var post := POST.instantiate() as Node3D
			post.name = "Support"
			post.transform = Transform3D(Basis.from_scale(Vector3(1.0, length, 1.0)), top)
			add_child(post, true)
