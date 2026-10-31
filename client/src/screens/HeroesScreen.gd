extends Control
## Hero collection + hero detail (stats, skill, lore, level up via server).

const HeroCard := preload("res://src/ui/HeroCard.gd")

var main: Node
var _grid: GridContainer
var _detail: Control


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("hub")
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 24
	panel.offset_right = -24
	panel.offset_top = 10
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 16)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Герои", 52))
	head.add_child(UI.expand())
	var form := UI.button("Формация", "primary", 300)
	form.pressed.connect(func(): main.open("formation", {"back": "heroes"}))
	head.add_child(form)
	v.add_child(head)
	v.add_child(UI.label("Коллекция: %d / %d" % [Game.heroes.size(), _summonable_count()], 28, UI.MUTED))
	_grid = GridContainer.new()
	_grid.columns = 4
	_grid.add_theme_constant_override("h_separation", 16)
	_grid.add_theme_constant_override("v_separation", 16)
	v.add_child(UI.scroll(_grid))
	_fill()
	Game.heroes_changed.connect(_fill)


func _summonable_count() -> int:
	var c := 0
	for h in Game.catalog.get("heroes", []):
		if not h.is_enemy:
			c += 1
	return c


func _fill() -> void:
	if not is_inside_tree():
		return
	for c in _grid.get_children():
		c.queue_free()
	for h in Game.heroes:
		var card := HeroCard.new()
		card.setup(h, h.id in Game.formation)
		var hid: String = h.id
		card.pressed.connect(func(): _open_detail(hid))
		_grid.add_child(card)
	# silhouettes of heroes not yet collected
	var owned := {}
	for h in Game.heroes:
		owned[h.hero_code] = true
	for ch in Game.catalog.get("heroes", []):
		if ch.is_enemy or owned.has(ch.code):
			continue
		var p := PanelContainer.new()
		p.custom_minimum_size = Vector2(230, 300)
		p.add_theme_stylebox_override("panel", UI._flat(Color(0, 0, 0, 0.35), Color(1, 1, 1, 0.15), 24, 2))
		var l := UI.label("?\n%s\n%s" % [ch.name, Game.rarities.get(str(int(ch.rarity)), "")], 24, UI.MUTED)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		p.add_child(l)
		_grid.add_child(p)


func _open_detail(hero_id: String) -> void:
	if _detail:
		_detail.queue_free()
	var h := Game.hero_by_id(hero_id)
	main.world.show_hero(h.hero_code)
	_detail = UI.glass_panel(Game.RARITY_COLORS.get(int(h.rarity), Color.WHITE))
	_detail.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_detail.offset_left = 24
	_detail.offset_right = -24
	_detail.offset_top = -900
	_detail.offset_bottom = -10
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	var head := HBoxContainer.new()
	var title := UI.title(h.name, 54)
	head.add_child(title)
	head.add_child(UI.expand())
	var close := UI.button("✕", "dim", 96, 90)
	close.pressed.connect(func(): _detail.queue_free(); _detail = null)
	head.add_child(close)
	v.add_child(head)
	var cat := Game.catalog_hero(h.hero_code)
	v.add_child(UI.label("%s · %s · %s · %s" % [h.title, h.rarity_name, Game.CLASS_NAMES.get(h["class"], ""),
		Game.FACTION_NAMES.get(h.faction, "")], 28, Game.RARITY_COLORS.get(int(h.rarity), Color.WHITE), true))
	var stats := GridContainer.new()
	stats.columns = 4
	stats.add_theme_constant_override("h_separation", 40)
	for pair in [["Уровень", h.level], ["Звёзды", "★".repeat(int(h.stars)) if int(h.stars) > 0 else "—"],
			["Здоровье", h.stats.hp], ["Атака", h.stats.atk], ["Защита", h.stats["def"]], ["Скорость", h.stats.spd],
			["Сила", h.power], ["Осколки", "%d/10" % int(h.shards)]]:
		stats.add_child(UI.label(pair[0], 28, UI.MUTED))
		stats.add_child(UI.label(str(int(pair[1])) if (pair[1] is float or pair[1] is int) else str(pair[1]), 32, UI.TEXT, true))
	v.add_child(stats)
	var sk: Dictionary = h.skill
	v.add_child(UI.label("Умение: " + String(sk.get("name", "")), 32, UI.GOLD, true))
	var sd := UI.label(String(sk.get("desc", "")), 28)
	sd.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(sd)
	var lore := UI.label("«%s»" % String(cat.get("lore", "")), 26, UI.MUTED)
	lore.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(lore)
	v.add_child(UI.expand())
	var cost = h.get("level_up_cost")
	if cost:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 16)
		row.add_child(UI.rewards_row(cost, 30))
		var up := UI.button("Повысить уровень", "primary", 0, 112)
		up.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		up.pressed.connect(func(): _level_up(hero_id))
		row.add_child(up)
		v.add_child(row)
	_detail.add_child(v)
	add_child(_detail)


func _level_up(hero_id: String) -> void:
	var r := await Api.post_json("/player/heroes/%s/level-up" % hero_id, {}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coin")
	Game.set_wallet(r.data.wallet)
	for i in Game.heroes.size():
		if Game.heroes[i].id == hero_id:
			Game.heroes[i] = r.data.hero
	Game.heroes_changed.emit()
	var hero_node: Node3D = main.world.hero
	if hero_node:
		Models.play(hero_node, "cheer")
		Models.queue_idle(hero_node)
	_open_detail(hero_id)
