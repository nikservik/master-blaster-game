class_name Shallows
extends Node

## Открытое море (Sea.is_open_water) глубже пояса героя не пускает (TER-1.6): если герой встал на дно глубже WADE_DEPTH под водой,
## он возвращается туда, где стоял последний раз мельче, — как упёрся в стену.
## Узел стоит в сцене после героя: проверка идёт после его шага физики.

## Глубина по пояс, м.
const WADE_DEPTH := 1.0

@export var hero: Hero

var _last_shallow: Vector3


func _ready() -> void:
	_last_shallow = hero.global_position


func _physics_process(_delta: float) -> void:
	var feet := hero.global_position
	if not hero.is_on_floor():
		return
	if Sea.is_open_water(feet.x, feet.z) and WorldTerrain.SEA_Y - feet.y > WADE_DEPTH:
		hero.global_position = _last_shallow
		hero.velocity.x = 0.0
		hero.velocity.z = 0.0
	else:
		_last_shallow = feet


