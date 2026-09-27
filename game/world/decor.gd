extends Node3D

## Руины над бухтой: у каждого модуля — коллизия по его сетке на слое 1, как у площадки.
## Сквозь стены и арки не пройти, на обломки можно запрыгнуть. Растения коллизий не получают.


func _ready() -> void:
	for module in get_children():
		if module.scene_file_path.contains("/ruins/"):
			for view: MeshInstance3D in module.find_children("*", "MeshInstance3D", true, false):
				view.create_trimesh_collision()
