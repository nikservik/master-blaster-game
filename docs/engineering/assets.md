# Ассеты

Модели и текстуры игры лежат в `game/assets/<категория>/`. Стиль задаёт [арт-направление](../world/art-direction.md): стилизованный реализм. Модели, растения, руины и детали строительства — в одной рисованной манере Quaternius MegaKit. Текстуры рельефа и небо — фото-PBR Poly Haven.

Все источники — CC0, указание автора не требуется. Скачанные архивы, `.blend` и неиспользуемые варианты в git не попадают. Они лежат вне репозитория, в `C:\Dev\asset-cache\`.

## Пакеты

| Пакет, URL | Автор | Что взято | Куда |
|---|---|---|---|
| Universal Base Characters [Standard], https://quaternius.itch.io/universal-base-characters | Quaternius | Голова, глаза и брови `Superhero_Male` | `character/hero.glb` |
| Modular Character Outfits – Fantasy [Standard], https://quaternius.itch.io/modular-character-outfits-fantasy | Quaternius | Одежда `Male_Ranger` с руками и капюшоном | `character/hero.glb` |
| Universal Animation Library [Standard], https://quaternius.itch.io/universal-animation-library | Quaternius | `Idle_Loop`, `Jog_Fwd_Loop`, `Jump_Start`, `Jump_Loop`, `Jump_Land` | `character/hero.glb` |
| Universal Animation Library 2 [Standard], https://quaternius.itch.io/universal-animation-library-2 | Quaternius | `TreeChopping_Loop` | `character/hero.glb` |
| Stylized Nature MegaKit [Standard], https://quaternius.itch.io/stylized-nature-megakit | Quaternius | Кусты, папоротник, растения, клевер и трава. Камни `Rock_Medium_1–3`, гальки. Текстуры листьев и коры для пальм | `vegetation/`, `rocks/` |
| Medieval Village MegaKit [Standard], https://quaternius.itch.io/medieval-village-megakit | Quaternius | Лианы `Prop_Vine1/2/4/5/6/9`. Текстуры кирпича, бутового камня и досок — основа песчаника и досок | `vegetation/vine_*`, `ruins/`, `building/` |
| Fantasy Props MegaKit [Standard], https://quaternius.itch.io/fantasy-props-megakit | Quaternius | `Crate_Wooden`, `Table_Large`, подогнаны под размеры BLD | `props/` |
| Poly Haven, https://polyhaven.com/a/aerial_beach_01 | Rob Tuytel | Песок, 1K | `terrain/sand/` |
| Poly Haven, https://polyhaven.com/a/aerial_grass_rock | Rob Tuytel | Трава, 1K | `terrain/grass/` |
| Poly Haven, https://polyhaven.com/a/sandstone_cracks | Rob Tuytel | Камень, охристый песчаник, 1K | `terrain/rock/` |
| Poly Haven, https://polyhaven.com/a/dirt | Charlotte Baglioni | Земля, 1K | `terrain/dirt/` |
| Poly Haven, https://polyhaven.com/a/wasteland_clouds_puresky | Sergej Majboroda, Jarod Guest | HDRI 2K: низкое тёплое солнце, бирюзовое небо, кучевые облака, без земли | `sky/` |

Quaternius скачивается с itch.io без входа в аккаунт: у бесплатных версий [Standard] кнопка Download. Лицензия CC0 указана в `License*.txt` каждого архива.

## Что сделано в Blender

Готовых деталей нужного вида не нашлось, поэтому в Blender сделаны:
- пальмы;
- модульные руины из песчаника с магико-технологическими деталями;
- детали строительства по размерам BLD.

Эти модели используют текстуры Quaternius, перекрашенные в палитру. Скрипты сборки лежат в `game/assets/_blender/`, Godot их не импортирует (`.gdignore`). Они читают архивы из `C:\Dev\asset-cache\`, а `build_parts.py` удаляет все объекты текущей сцены. Поэтому запускать их нужно в отдельной сцене Blender, по порядку:
1. `make_textures.py` — перекрашенные текстуры в `C:\Dev\asset-cache\work\tex`;
2. `build_parts.py`, `ruins.py`, `nature.py` — экспорт в `game/assets`.

`blib.py` — общие функции: материалы, развёртка по граням, экспорт.

## Формат и координаты

- Метры, +Y вверх — это glTF. Начало модели — на земле, в центре основания, если ниже не сказано иное.
- Перед модели — +Z glTF. Герой смотрит лицом в +Z. В Godot «вперёд» — −Z, поэтому модель героя внутри узла `Model` разворачивают на 180° вокруг Y.
- Кроме героя, все модели — `.gltf` + `.bin`. Текстуры категории общие и лежат в её `textures/`. Герой — один `character/hero.glb`: Godot при импорте извлекает из него текстуры в `character/hero_T_*.png`.
- Карты нормалей — OpenGL (+Y), как требует glTF. Нормали MegaKit в папках `glTF` — DirectX, поэтому взяты из `Normals Godot-Unity`.
- Листва — `alphaMode MASK`, отсечение 0,5.
- Магическое свечение — материал `M_Magitech`: цвет `#5FF2E6`, эмиссия с силой 4 (`KHR_materials_emissive_strength`). Нужен glow в окружении.

## Герой

`character/hero.glb` — скелет UE-манекена Quaternius (65 костей, корень `root`). Его разделяют Base Characters, Outfits и обе Animation Library, поэтому клипы подходят без ретаргетинга. Проигрывание на выбранном персонаже проверено в Blender.

- Рост — 1,84 м с капюшоном, ступни на 0. Ширина по разведённым рукам T-позы — 1,8 м.
- Клипы без перемещения корня (in place). Петля включена в `hero.glb.import` для `idle`, `run`, `fall`, `dig`.

| Клип | Источник | Длина, с | Петля |
|---|---|---|---|
| `idle` | `Idle_Loop` | 2,5 | да |
| `run` | `Jog_Fwd_Loop` | 0,92 | да |
| `jump` | `Jump_Start` — отталкивание | 1,33 | нет |
| `fall` | `Jump_Loop` — в воздухе | 2,5 | да |
| `land` | `Jump_Land` — приземление, дополнительно | 1,25 | нет |
| `dig` | `TreeChopping_Loop` — замах и удар двумя руками | 0,96 | да |

Шаг `run` рассчитан примерно на 5,4 м/с: столько проходит корень в версии с root motion. При скорости бега героя 6 м/с ставь `speed_scale` ≈ 1,1.

## Каталог

**Строительство** (`building/`). Начало координат совпадает с `BuildPart`: центр основания на уровне пола этажа. Материалы — блоки песчаника и доски.

| Файл | Размер, м | Особенности |
|---|---|---|
| `foundation_2x2`, `foundation_2x1`, `foundation_1x1` | 2 × 2, 2 × 1, 1 × 1; толщина 0,2 | Песчаник; от 0 вниз до −0,2 |
| `floor_2x2`, `floor_2x1`, `floor_1x1` | То же | Доски; от 0 вниз до −0,2 |
| `wall_2m`, `wall_1m` | Длина 2 или 1 по X, высота 2,8, толщина 0,2 по Z | — |
| `wall_door_2m` | 2 × 2,8 × 0,2 | Проём 1 × 2,2 по центру, деревянная перемычка над ним |
| `stairs_2x4` | 2 по X × 4 по Z | 10 ступеней, подъём 3 м к −Z, низ у +Z |
| `post_1m` | 0,3 × 0,3, высота 1 | Опора под фундамент: от 0 вниз до −1. Длину задаёт масштаб по Y, текстура при этом растягивается |

**Руины** (`ruins/`). Песчаник — блоки и бут. Светятся `column_magitech`, `obelisk_magitech`, `magitech_panel` и замковый камень `arch`.

| Файл | Размер, м | Особенности |
|---|---|---|
| `column` | Высота 4 | — |
| `column_broken` | Высота 2,4 | Сломанный верх |
| `column_magitech` | Высота 4 | Два светящихся кольца |
| `wall` | 4 × 3,2 × 0,8 | — |
| `wall_broken` | 4 × 0,8, высота ступеньками от 3 до 0,9 | — |
| `wall_stepped` | 4 × 3 × 3 | Три террасы, выше к −Z |
| `arch` | 4 × 5,3 × 1 | Акведук; пролёт 2,4 м, до замка 3,8 м |
| `floor_slab` | 4 × 4 × 0,3 | Верх на 0 |
| `stairs` | 3 × 2,5 | 5 ступеней по 0,3 м, подъём к −Z |
| `debris_block`, `debris_slab`, `debris_pile`, `debris_drum` | — | Обломки |
| `obelisk_magitech` | Высота 5,6 | Светящиеся полосы на гранях |
| `magitech_panel` | 1 × 1 × 0,1 | Светящееся кольцо-руна. Задняя грань на z = 0, лицо к +Z: ставится на стену |

**Растительность** (`vegetation/`):
- `palm_1`, `palm_2`, `palm_3` — стволы 6,5, 8 и 4,5 м, крона добавляет около 1,4 м. Ствол наклонён к +X;
- `bush`, `bush_flowers`, `fern`, `plant_small`, `plant_big`, `clover`;
- трава: `grass_short`, `grass_tall`, `grass_wispy_short`, `grass_wispy_tall`;
- лианы `vine_1` … `vine_6` — плоские плети длиной 1–2,6 м. Верх примерно на 0,5 м выше начала координат, плеть свисает вниз, толщина — по Z: вешаются на стену.

**Камни** (`rocks/`):
- `rock_1` … `rock_3` — серо-зелёные, около 3 м в поперечнике и 2 м в высоту; низ немного уходит под 0;
- `rock_desert_1` … `rock_desert_3` — те же формы в охре;
- `plateau_desert` — плато из трёх увеличенных охристых камней, около 12 × 8 м в плане и 5,7 м в высоту;
- `pebble_round_1/2`, `pebble_square_1/2`.

**Предметы** (`props/`): `crate` 0,8 × 0,8 × 0,8, `table` 1,4 (X) × 0,75 (высота) × 0,8 (Z) — по размерам `BuildItem`.

**Рельеф** (`terrain/<sand|grass|rock|dirt>/`): карты Poly Haven 1K — `*_diff_1k.jpg` (цвет), `*_nor_gl_1k.jpg` (нормали OpenGL), `*_arm_1k.jpg` (AO, шероховатость, металличность по каналам R, G, B).

**Небо** (`sky/wasteland_clouds_puresky_2k.hdr`) — для `PanoramaSkyMaterial`. Солнце в HDRI ниже, чем 25–35° из арт-направления: высоту и цвет солнца задаёт `DirectionalLight3D`.

`preview.tscn` — пробная сцена: все модели рядами по категориям, образцы рельефа, небо и солнце. В игре она не используется.
