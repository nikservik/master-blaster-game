class_name Sea
extends MeshInstance3D

## Море рисуется только над открытой водой бухты: где по форме берега грунт ниже уровня моря.
## Ямы на суше и низины у обрыва не заливаются, хотя плоскость моря проходит под ними.
## Правило продублировано в шейдере `sea.gdshader`; параметры берега берутся из WorldTerrain.

## Запас над уровнем моря: у кромки вода заходит под пляж, чтобы пена у берега не обрывалась.
const SHORE_MARGIN := 1.0


func _ready() -> void:
	var mat := (mesh as PrimitiveMesh).material as ShaderMaterial
	mat.set_shader_parameter("sea_y", WorldTerrain.SEA_Y)
	mat.set_shader_parameter("shore_margin", SHORE_MARGIN)
	mat.set_shader_parameter("coast", Vector4(WorldTerrain.COAST_START_Z, WorldTerrain.COAST_LENGTH, WorldTerrain.BAY_CURVE, WorldTerrain.SEABED_Y))
	mat.set_shader_parameter("hills_fade", WorldTerrain.HILLS_FADE)
	mat.set_shader_parameter("flat_area", Vector4(WorldTerrain.FLAT_CENTER.x, WorldTerrain.FLAT_CENTER.y, WorldTerrain.FLAT_HALF.x, WorldTerrain.FLAT_HALF.y))
	mat.set_shader_parameter("flat_y", Vector3(WorldTerrain.FLAT_Y, WorldTerrain.RUINS_FLOOR_Y, WorldTerrain.FLAT_BLEND))


## Открытая ли вода в (x, z): доля берега больше, чем там, где стихают холмы,
## и грунт нетронутого берега ниже уровня моря с запасом SHORE_MARGIN.
static func is_open_water(x: float, z: float) -> bool:
	var c := clampf((z - WorldTerrain.COAST_START_Z - pow(x - WorldTerrain.FLAT_CENTER.x, 2.0) * WorldTerrain.BAY_CURVE) / WorldTerrain.COAST_LENGTH, 0.0, 1.0)
	if c <= WorldTerrain.HILLS_FADE:
		return false
	return shore_height(x, z, c) < WorldTerrain.SEA_Y + SHORE_MARGIN


## Высота нетронутого берега там, где холмы уже стихли: спуск от уровня руин к дну и переход от ровной площадки.
static func shore_height(x: float, z: float, c: float) -> float:
	var natural := WorldTerrain.RUINS_FLOOR_Y + (WorldTerrain.SEABED_Y - WorldTerrain.RUINS_FLOOR_Y) * c * c * (3.0 - 2.0 * c)
	var dx := maxf(absf(x - WorldTerrain.FLAT_CENTER.x) - WorldTerrain.FLAT_HALF.x, 0.0)
	var dz := maxf(absf(z - WorldTerrain.FLAT_CENTER.y) - WorldTerrain.FLAT_HALF.y, 0.0)
	var w := clampf(sqrt(dx * dx + dz * dz) / WorldTerrain.FLAT_BLEND, 0.0, 1.0)
	return WorldTerrain.FLAT_Y + (natural - WorldTerrain.FLAT_Y) * w * w * (3.0 - 2.0 * w)
