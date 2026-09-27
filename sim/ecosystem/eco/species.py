"""Виды, паттерны и связи «хищник — добыча» — таблицы параметров.

Время жизни, взросление и беременность заданы в годах; в игровые дни их переводит Sim (year_days).
Суточная потребность в пище — кг/сутки; масса — кг туши для падали.
"""
import numpy as np

# Паттерны — общий список; каждому виду доступно подмножество.
PATTERNS = ["rest", "graze", "drink", "follow", "flee", "hide", "explore", "hunt", "scavenge", "patrol", "investigate", "ambush"]
P = {name: i for i, name in enumerate(PATTERNS)}
PATTERN_DESC = {
    "rest": "lie down in cover or den and rest",
    "graze": "look for food here and eat",
    "drink": "walk to known water and drink",
    "follow": "stay close to the group leader or mother",
    "flee": "run away from danger",
    "hide": "freeze or hide in dense cover",
    "explore": "wander and explore the area",
    "hunt": "stalk and chase prey",
    "scavenge": "search for carrion and eat it",
    "patrol": "walk around the pack territory",
    "investigate": "carefully go closer to look at the disturbance",
    "ambush": "wait hidden in cover for prey to come close",
}
# Реакции на событие: у добычи и у хищника свои варианты.
REACTIONS_PREY = {"continue": "keep doing the current activity", "freeze": "freeze and watch",
                  "flee": "run away now", "investigate": "go closer to look"}
REACTIONS_PRED = {"continue": "ignore it and keep doing the current activity", "stalk": "start stalking the prey",
                  "investigate": "go closer to look"}
REACTION_TO_PATTERN = {"freeze": P["hide"], "flee": P["flee"], "investigate": P["investigate"], "stalk": P["hunt"]}

FOODS = ["grass", "shrub", "mast", "berries", "carrion"]
SEASONS = ["spring", "summer", "autumn", "winter"]

_ALL = ["rest", "graze", "drink", "follow", "flee", "hide", "explore", "investigate"]
_PRED = ["rest", "drink", "follow", "explore", "hunt", "scavenge", "investigate"]

# name, mass, walk, run, stamina_s, strength, vision, hearing, smell, night, flying, silent,
# diet{food: вес}, need кг/сутки, eat_frac (доля суток на суточную норму), thirst/сутки,
# social, group_max, mate сезоны, gestation лет, litter, maturity лет, lifespan лет, den, patterns
SPECIES = [
    dict(key="roe", name="roe deer", mass=22, walk=1.3, run=12.5, stamina=25, strength=0.25, vision=80, hearing=60, smell=40,
         night=0.6, flying=False, silent=False, diet={"grass": .5, "shrub": .5}, need=2.5, eat_frac=0.1, thirst=0.4,
         social="herd", group_max=6, mate=[1], gestation=0.72, litter=(1, 2), maturity=1.0, lifespan=10, den=False,
         patterns=_ALL, forage="browse grass and shrubs here"),
    dict(key="hare", name="brown hare", mass=3.5, walk=1.0, run=15, stamina=30, strength=0.1, vision=40, hearing=70, smell=30,
         night=0.9, flying=False, silent=False, diet={"grass": .7, "shrub": .3}, need=0.5, eat_frac=0.1, thirst=0.3,
         social="solitary", group_max=1, mate=[0, 1], gestation=0.115, litter=(1, 3), maturity=0.6, lifespan=5, den=True,
         patterns=["rest", "graze", "drink", "follow", "flee", "hide", "explore"], forage="nibble grass and shoots"),
    dict(key="wolf", name="wolf", mass=38, walk=1.5, run=13.5, stamina=70, strength=0.6, vision=70, hearing=90, smell=100,
         night=0.9, flying=False, silent=False, diet={"carrion": 1.0}, need=2.5, eat_frac=0.02, thirst=0.8,
         social="pack", group_max=8, mate=[3], gestation=0.17, litter=(2, 5), maturity=2.0, lifespan=10, den=True,
         patterns=_PRED + ["patrol"], forage="eat from a carcass"),
    dict(key="jay", name="jay", mass=0.17, walk=3.0, run=9, stamina=60, strength=0.05, vision=60, hearing=50, smell=0,
         night=0.2, flying=True, silent=False, diet={"mast": .6, "berries": .3, "grass": .1}, need=0.04, eat_frac=0.3, thirst=0.4,
         social="solitary", group_max=1, mate=[0], gestation=0.07, litter=(3, 5), maturity=1.0, lifespan=6, den=False,
         patterns=["rest", "graze", "drink", "flee", "hide", "explore", "investigate"], forage="gather acorns, seeds and berries"),
    dict(key="boar", name="wild boar", mass=80, walk=1.2, run=11, stamina=40, strength=0.9, vision=30, hearing=60, smell=90,
         night=0.8, flying=False, silent=False, diet={"grass": .3, "mast": .4, "berries": .1, "shrub": .1, "carrion": .1},
         need=4.0, eat_frac=0.12, thirst=0.8, social="herd", group_max=12, mate=[3], gestation=0.32, litter=(3, 6),
         maturity=1.5, lifespan=10, den=False, patterns=_ALL, forage="root for acorns, roots and grass"),
    dict(key="lynx", name="lynx", mass=20, walk=1.2, run=15, stamina=10, strength=0.7, vision=90, hearing=90, smell=40,
         night=1.0, flying=False, silent=True, diet={"carrion": 1.0}, need=1.5, eat_frac=0.02, thirst=0.6,
         social="solitary", group_max=1, mate=[3], gestation=0.19, litter=(1, 3), maturity=2.0, lifespan=15, den=True,
         patterns=_PRED + ["ambush"], forage="eat from a carcass"),
    dict(key="fox", name="red fox", mass=7, walk=1.3, run=12, stamina=25, strength=0.3, vision=50, hearing=80, smell=90,
         night=1.0, flying=False, silent=False, diet={"carrion": .7, "berries": .2, "mast": .1}, need=0.5, eat_frac=0.03,
         thirst=0.5, social="solitary", group_max=1, mate=[3], gestation=0.14, litter=(3, 6), maturity=1.0, lifespan=6,
         den=True, patterns=_PRED + ["graze"], forage="pick berries and fallen fruit"),
    dict(key="raven", name="raven", mass=1.2, walk=2.0, run=12, stamina=200, strength=0.1, vision=150, hearing=60, smell=0,
         night=0.2, flying=True, silent=False, diet={"carrion": .6, "mast": .2, "berries": .2}, need=0.12, eat_frac=0.1,
         thirst=0.4, social="pair", group_max=2, mate=[0], gestation=0.12, litter=(2, 4), maturity=2.0, lifespan=15,
         den=False, patterns=["rest", "graze", "drink", "follow", "flee", "explore", "scavenge"],
         forage="pick acorns and berries", follow="follow wolves to find their kills"),
    dict(key="mouse", name="wood mouse", mass=0.025, walk=0.5, run=3, stamina=15, strength=0.01, vision=10, hearing=20, smell=15,
         night=1.0, flying=False, silent=True, diet={"grass": .5, "mast": .3, "berries": .2}, need=0.004, eat_frac=0.3,
         thirst=0.0, social="solitary", group_max=1, mate=[0, 1, 2], gestation=0.06, litter=(3, 6), maturity=0.15,
         lifespan=1.5, den=True, patterns=["rest", "graze", "follow", "flee", "hide", "explore"], forage="gather seeds and nuts"),
    dict(key="owl", name="tawny owl", mass=0.5, walk=2.0, run=10, stamina=60, strength=0.2, vision=40, hearing=60, smell=0,
         night=1.0, flying=True, silent=True, diet={"carrion": 1.0}, need=0.1, eat_frac=0.1, thirst=0.2,
         social="solitary", group_max=1, mate=[3], gestation=0.08, litter=(2, 3), maturity=1.0, lifespan=10, den=True,
         patterns=["rest", "drink", "follow", "explore", "hunt", "scavenge"], forage="eat the catch"),
    dict(key="badger", name="badger", mass=12, walk=0.9, run=6, stamina=20, strength=0.5, vision=20, hearing=50, smell=90,
         night=1.0, flying=False, silent=False, diet={"grass": .4, "berries": .2, "mast": .2, "carrion": .2}, need=0.6,
         eat_frac=0.25, thirst=0.5, social="solitary", group_max=1, mate=[0], gestation=0.8, litter=(1, 3), maturity=1.5,
         lifespan=12, den=True, patterns=["rest", "graze", "drink", "follow", "flee", "explore", "hunt", "scavenge"],
         forage="dig for worms and roots"),
]
KEYS = [s["key"] for s in SPECIES]
K = {k: i for i, k in enumerate(KEYS)}
NS = len(SPECIES)
BASE = ["roe", "hare", "wolf", "jay"]

# Кого ест хищник (охота).
PREY = {"wolf": ["roe", "hare", "boar"], "lynx": ["roe", "hare", "fox", "jay"], "fox": ["hare", "mouse", "jay"],
        "owl": ["mouse"], "badger": ["mouse"]}
# Кого боится вид (угрозы); сойка ещё и кричит на всех хищников, включая сову.
THREATS = {"roe": ["wolf", "lynx"], "hare": ["wolf", "lynx", "fox"], "boar": ["wolf"], "fox": ["lynx", "wolf"],
           "jay": ["fox", "lynx", "wolf", "owl"], "mouse": ["fox", "owl", "badger"], "raven": [], "wolf": [], "lynx": ["wolf"],
           "owl": [], "badger": ["wolf"]}
CHASE_DIST = {"wolf": 45.0, "lynx": 20.0, "fox": 15.0, "owl": 15.0, "badger": 5.0}
# Доли вида в начальной численности.
SHARE_BASE = {"roe": .47, "hare": .30, "wolf": .02, "jay": .21}
SHARE_ALL = {"roe": .20, "boar": .07, "hare": .15, "mouse": .35, "wolf": .01, "lynx": .005, "fox": .02,
             "jay": .10, "raven": .03, "owl": .005, "badger": .02}


def arr(field: str, dtype=float) -> np.ndarray:
    return np.array([s[field] for s in SPECIES], dtype=dtype)


MASS, WALK, RUN, STAMINA, STRENGTH = arr("mass"), arr("walk"), arr("run"), arr("stamina"), arr("strength")
VISION, HEARING, SMELL, NIGHT = arr("vision"), arr("hearing"), arr("smell"), arr("night")
FLYING, SILENT, DEN = arr("flying", bool), arr("silent", bool), arr("den", bool)
NEED, EAT_FRAC, THIRST = arr("need"), arr("eat_frac"), arr("thirst")
GROUP_MAX = arr("group_max", int)
SOCIAL = np.array([s["social"] != "solitary" for s in SPECIES])
TERRITORIAL = np.array([s["social"] == "pack" for s in SPECIES])
GESTATION, MATURITY, LIFESPAN = arr("gestation"), arr("maturity"), arr("lifespan")
LITTER_LO = np.array([s["litter"][0] for s in SPECIES]); LITTER_HI = np.array([s["litter"][1] for s in SPECIES])
DIET = np.array([[s["diet"].get(f, 0.0) for f in FOODS] for s in SPECIES])            # (NS, 5)
MATE = np.array([[q in s["mate"] for q in range(4)] for s in SPECIES])                 # (NS, 4)
ALLOWED = np.array([[p in s["patterns"] for p in PATTERNS] for s in SPECIES])           # (NS, NP)
IS_PRED = np.array([k in PREY for k in KEYS])
EATS = np.zeros((NS, NS), bool)          # EATS[хищник, добыча]
for pk, qs in PREY.items():
    for q in qs:
        EATS[K[pk], K[q]] = True
FEARS = np.zeros((NS, NS), bool)         # FEARS[вид, угроза]
for sk, ts in THREATS.items():
    for t in ts:
        FEARS[K[sk], K[t]] = True
CHASE = np.array([CHASE_DIST.get(k, 0.0) for k in KEYS])
# Выводков в год; смертность от неучтённых причин (болезни, погода, мелкие хищники), доля в год: детёныши, взрослые.
_EXTRA = {"roe": (1, 0.4, 0.1), "hare": (3, 1.0, 0.3), "wolf": (1, 0.3, 0.1), "jay": (1, 1.2, 0.3), "boar": (1, 0.5, 0.1),
          "lynx": (1, 0.3, 0.05), "fox": (1, 0.8, 0.2), "raven": (1, 0.8, 0.1), "mouse": (4, 2.0, 0.8), "owl": (1, 0.8, 0.1),
          "badger": (1, 0.4, 0.1)}
BROODS = np.array([_EXTRA[k][0] for k in KEYS])
# Предел плотности для размножения, особей своего вида на гектар (0 — без предела): при нём зачатий нет.
CAP_HA = np.array([{"mouse": 60, "hare": 20, "jay": 15, "raven": 5}.get(k, 0) for k in KEYS], float)
JUV_MORT = np.array([_EXTRA[k][1] for k in KEYS])
ADULT_MORT = np.array([_EXTRA[k][2] for k in KEYS])


def pattern_choices(s: int) -> dict[str, str]:
    """Варианты вопроса «паттерн» для вида: имя -> короткое английское описание."""
    sp = SPECIES[s]
    out = {}
    for p in sp["patterns"]:
        if p == "investigate":      # только реакция на событие: ей нужен источник
            continue
        out[p] = sp.get("forage") if p == "graze" else sp.get("follow") if (p == "follow" and "follow" in sp) else PATTERN_DESC[p]
    return out


def reaction_choices(s: int) -> dict[str, str]:
    return REACTIONS_PRED if IS_PRED[s] else REACTIONS_PREY
