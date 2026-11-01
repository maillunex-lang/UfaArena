extends Control
## «Ещё»: grouped cards for secondary features. Every tile opens a working screen; systems not in the game
## yet (equipment, artifacts) are clearly locked.

var main: Node


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
	var groups := [
		["Предметы", [["quests", "Инвентарь", "inventory", false, 0], ["lock", "Экипировка", "", true, 0], ["lock", "Артефакты", "", true, 0]]],
		["Прогресс", [["summon", "Призыв", "summon", false, 0], ["quests", "Задания", "quests", false, int(b.get("quests", 0))],
			["ranks", "Достижения", "rankings:achievements", false, 0]]],
		["Социальное и сервисы", [["mail", "Почта", "mail", false, int(b.get("mail", 0))], ["shop", "Магазин", "shop", false, 0],
			["ranks", "Рейтинг", "rankings", false, 0], ["friends", "Друзья", "friends", false, int(b.get("friends", 0))],
			["chat", "Чат", "chat", false, int(b.get("chat", 0))], ["fortress", "Крепость", "fortress", false, 0]]],
		["Управление", [["profile", "Профиль", "profile", false, 0], ["settings", "Настройки", "settings", false, 0]]],
	]
	for g in groups:
		body.add_child(UI.section(String(g[0])))
		var grid := GridContainer.new()
		grid.columns = 3
		grid.add_theme_constant_override("h_separation", UI.SP.m)
		grid.add_theme_constant_override("v_separation", UI.SP.m)
		for it in g[1]:
			var t := UI.tile(it[0], it[1], "скоро" if it[3] else "", it[3], it[4])
			var target: String = it[2]
			var nm: String = it[1]
			if it[3]:
				t.pressed.connect(func(): Router.toast("«%s» появится вместе с системой предметов в следующих обновлениях" % nm))
			elif ":" in target:
				t.pressed.connect(func(): main.open(target.split(":")[0], {"tab": target.split(":")[1]}))
			else:
				t.pressed.connect(func(): main.open(target))
			grid.add_child(t)
		body.add_child(grid)
	body.add_child(UI.spacer(UI.SP.l))
