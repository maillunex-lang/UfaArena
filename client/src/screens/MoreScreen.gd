extends Control
## «Ещё»: grouped cards for secondary features. Every tile opens a working screen; systems not in the game
## yet (equipment, artifacts) are clearly locked.

var main: Node

const KNOWN := ["inventory", "equipment", "artifacts", "summon", "quests", "achievements", "mail", "shop", "rankings", "friends",
	"chat", "caravan", "profile", "settings", "events", "raids", "arena", "tournaments", "heroes", "campaign", "guild", "world",
	"formation", "search", "home", "battle", "afk"]
const DEFAULT_GROUPS := [
	{"title": "Предметы", "items": [{"id": "inventory", "label": "Инвентарь", "icon": "quests"},
		{"id": "equipment", "label": "Экипировка", "icon": "lock"}, {"id": "artifacts", "label": "Артефакты", "icon": "lock"}]},
	{"title": "Прогресс", "items": [{"id": "summon", "label": "Призыв", "icon": "summon"}, {"id": "quests", "label": "Задания", "icon": "quests"},
		{"id": "achievements", "label": "Достижения", "icon": "ranks"}]},
	{"title": "Социальное и сервисы", "items": [{"id": "mail", "label": "Почта", "icon": "mail"}, {"id": "shop", "label": "Магазин", "icon": "shop"},
		{"id": "rankings", "label": "Рейтинг", "icon": "ranks"}, {"id": "friends", "label": "Друзья", "icon": "friends"},
		{"id": "chat", "label": "Чат", "icon": "chat"}, {"id": "caravan", "label": "Караван", "icon": "caravan"}]},
	{"title": "Управление", "items": [{"id": "profile", "label": "Профиль", "icon": "profile"},
		{"id": "settings", "label": "Настройки", "icon": "settings"}]},
]


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("none")
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", UI.SP.l)
	var sc := UI.scroll(body)
	sc.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	sc.offset_left = UI.SP.m
	sc.offset_right = -UI.SP.m
	sc.offset_top = UI.SP.s
	add_child(sc)
	var b: Dictionary = main.badges
	var badge := {"quests": int(b.get("quests", 0)), "mail": int(b.get("mail", 0)), "friends": int(b.get("friends", 0)),
		"chat": int(b.get("chat", 0))}
	var cols := int(Game.ui_part("more.columns", 3.0))
	# groups and tiles from the admin layout (Редактор игры → Интерфейс); the built-in set otherwise
	for g in Game.ui_part("more.groups", DEFAULT_GROUPS):
		if not (g is Dictionary):
			continue
		var items: Array = Game.visible_items(g.get("items", []), func(k): return k in KNOWN)
		if items.is_empty():
			continue
		body.add_child(UI.section(String(g.get("title", ""))))
		var grid := GridContainer.new()
		grid.columns = clampi(cols, 2, 4)
		grid.add_theme_constant_override("h_separation", UI.SP.m)
		grid.add_theme_constant_override("v_separation", UI.SP.m)
		for it in items:
			var id := String(it.id)
			var locked: bool = id in ["equipment", "artifacts"]
			var t := UI.tile(String(it.get("icon", id)), String(it.get("label", id)), "скоро" if locked else "", locked,
				int(badge.get(id, 0)))
			t.pressed.connect(func(): main.do_action(id))
			grid.add_child(t)
		body.add_child(grid)
	body.add_child(UI.spacer(UI.SP.l))
