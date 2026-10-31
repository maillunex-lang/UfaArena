extends Control
## Hero collection: faction / rarity / class filters, name search, sorting; hero detail with the
## full kit (basic, 2 skills, ultimate, passive, unique mechanic), stats, lore and level up.

const HeroCard := preload("res://src/ui/HeroCard.gd")
const SORTS := [["power", "Сила"], ["level", "Уровень"], ["rarity", "Редкость"]]

var main: Node
var _grid: GridContainer
var _detail: Control
var _count: Label
var f_faction := ""
var f_rarity := 0
var f_class := ""
var query := ""
var sort_by := "power"
var _filter_row: HBoxContainer


func setup(m: Node, p: Dictionary) -> void:
	main = m
	f_faction = p.get("faction", "")
	f_rarity = int(p.get("rarity", 0))
	f_class = p.get("class", "")
	sort_by = p.get("sort", "power")
	main.use_world("hub")
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 20
	panel.offset_right = -20
	panel.offset_top = 10
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Герои", 50))
	head.add_child(UI.expand())
	var form := UI.button("Формация", "primary", 280, 92)
	form.pressed.connect(func(): main.open("formation", {"back": "heroes"}))
	head.add_child(form)
	v.add_child(head)
	# faction tabs
	var fac := HBoxContainer.new()
	fac.add_theme_constant_override("separation", 8)
	fac.add_child(_tab("Все", "", f_faction == "", func(): _set_faction("")))
	for f in Game.playable_factions():
		var code: String = f.code
		fac.add_child(_tab(f.name, code, f_faction == code, func(): _set_faction(code)))
	v.add_child(fac)
	_filter_row = HBoxContainer.new()
	_filter_row.add_theme_constant_override("separation", 8)
	v.add_child(_filter_row)
	var search_row := HBoxContainer.new()
	search_row.add_theme_constant_override("separation", 8)
	var search := LineEdit.new()
	search.placeholder_text = "Поиск по имени"
	search.custom_minimum_size = Vector2(0, 80)
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.add_theme_font_size_override("font_size", 28)
	search.text_changed.connect(func(t: String): query = t.strip_edges().to_lower(); _fill())
	search_row.add_child(search)
	for s in SORTS:
		var key: String = s[0]
		var sb := UI.button(s[1], "primary" if sort_by == key else "dim", 0, 80)
		sb.add_theme_font_size_override("font_size", 26)
		sb.pressed.connect(func(): main.open("heroes", {"faction": f_faction, "rarity": f_rarity, "class": f_class, "sort": key}))
		search_row.add_child(sb)
	v.add_child(search_row)
	_count = UI.label("", 26, UI.MUTED)
	v.add_child(_count)
	_grid = GridContainer.new()
	_grid.columns = 4
	_grid.add_theme_constant_override("h_separation", 14)
	_grid.add_theme_constant_override("v_separation", 14)
	v.add_child(UI.scroll(_grid))
	_refresh_filters()
	Game.heroes_changed.connect(_fill)


func _set_faction(code: String) -> void:
	f_faction = code
	main.open("heroes", {"faction": code, "rarity": f_rarity, "class": f_class, "sort": sort_by})


func _tab(text: String, emblem: String, active: bool, cb: Callable) -> Button:
	var b := UI.button(text, "primary" if active else "glass", 0, 78)
	b.add_theme_font_size_override("font_size", 25)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if emblem != "":
		var ic := GameIcon.new()
		ic.kind = emblem
		ic.size = Vector2(46, 46)
		ic.position = Vector2(8, 16)
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		b.add_child(ic)
		b.add_theme_constant_override("h_separation", 40)
	b.pressed.connect(cb)
	return b


func _refresh_filters() -> void:
	for c in _filter_row.get_children():
		c.queue_free()
	var rar := OptionButton.new()
	rar.add_item("Любая редкость", 0)
	for i in range(1, 7):
		rar.add_item(String(Game.rarities.get(str(i), str(i))), i)
	rar.select(f_rarity)
	rar.custom_minimum_size = Vector2(0, 72)
	rar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rar.add_theme_font_size_override("font_size", 26)
	rar.item_selected.connect(func(i: int): f_rarity = i; _fill())
	_filter_row.add_child(rar)
	var cls := OptionButton.new()
	cls.add_item("Любой класс")
	var codes := [""]
	for c in Game.catalog.get("classes", []):
		cls.add_item(String(c.name))
		codes.append(String(c.code))
	cls.select(maxi(0, codes.find(f_class)))
	cls.custom_minimum_size = Vector2(0, 72)
	cls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cls.add_theme_font_size_override("font_size", 26)
	cls.item_selected.connect(func(i: int): f_class = codes[i]; _fill())
	_filter_row.add_child(cls)
	_fill()


func _summonable_count() -> int:
	var c := 0
	for h in Game.catalog.get("heroes", []):
		if not h.is_enemy:
			c += 1
	return c


func _match(code: String, name: String, faction: String, rarity: int, cls: String) -> bool:
	if f_faction != "" and faction != f_faction:
		return false
	if f_rarity > 0 and rarity != f_rarity:
		return false
	if f_class != "" and cls != f_class:
		return false
	if query != "" and not name.to_lower().contains(query) and not code.contains(query):
		return false
	return true


func _fill() -> void:
	if not is_inside_tree() or _grid == null:
		return
	for c in _grid.get_children():
		c.queue_free()
	var owned := {}
	var list := []
	for h in Game.heroes:
		owned[h.hero_code] = true
		if _match(h.hero_code, h.name, h.faction, int(h.rarity), h["class"]):
			list.append(h)
	list.sort_custom(func(a, b):
		match sort_by:
			"level": return int(a.level) > int(b.level) if a.level != b.level else int(a.power) > int(b.power)
			"rarity": return int(a.rarity) > int(b.rarity) if a.rarity != b.rarity else int(a.power) > int(b.power)
		return int(a.power) > int(b.power))
	for h in list:
		var card := HeroCard.new()
		card.setup(h, h.id in Game.formation)
		var hid: String = h.id
		card.pressed.connect(func(): _open_detail(hid))
		_grid.add_child(card)
	var missing := 0
	for ch in Game.catalog.get("heroes", []):
		if ch.is_enemy or owned.has(ch.code) or not _match(ch.code, ch.name, ch.faction, int(ch.rarity), ch["class"]):
			continue
		missing += 1
		var p := Button.new()
		p.custom_minimum_size = Vector2(230, 300)
		p.focus_mode = Control.FOCUS_NONE
		for st in ["normal", "hover", "pressed"]:
			p.add_theme_stylebox_override(st, UI._flat(Color(0, 0, 0, 0.35), Color(Game.faction_color(ch.faction), 0.4), 24, 2))
		var l := UI.label("?\n%s\n%s\n%s" % [ch.name, Game.rarities.get(str(int(ch.rarity)), ""),
			Game.CLASS_NAMES.get(ch["class"], "")], 24, UI.MUTED)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.set_anchors_preset(Control.PRESET_FULL_RECT)
		l.mouse_filter = Control.MOUSE_FILTER_IGNORE
		p.add_child(l)
		var em := GameIcon.new()
		em.kind = String(ch.faction)
		em.size = Vector2(46, 46)
		em.position = Vector2(176, 6)
		em.modulate.a = 0.6
		em.mouse_filter = Control.MOUSE_FILTER_IGNORE
		p.add_child(em)
		var code: String = ch.code
		p.pressed.connect(func(): _open_catalog(code))
		_grid.add_child(p)
	_count.text = "Коллекция: %d / %d · показано %d" % [Game.heroes.size(), _summonable_count(), list.size() + missing]


# ------------------------------------------------------------------ detail
func _open_detail(hero_id: String) -> void:
	var h := Game.hero_by_id(hero_id)
	main.world.show_hero(h.hero_code)
	_show_detail(h, Game.catalog_hero(h.hero_code), true)


func _open_catalog(code: String) -> void:
	main.world.show_hero(code)
	_show_detail({}, Game.catalog_hero(code), false)


func _show_detail(h: Dictionary, cat: Dictionary, owned: bool) -> void:
	if _detail:
		_detail.queue_free()
	var rarity := int(cat.get("rarity", 1))
	_detail = UI.solid_panel(Game.RARITY_COLORS.get(rarity, Color.WHITE))
	_detail.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_detail.offset_left = 20
	_detail.offset_right = -20
	_detail.offset_top = -1180
	_detail.offset_bottom = -10
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 12)
	var em := GameIcon.new()
	em.kind = String(cat.get("faction", ""))
	em.custom_minimum_size = Vector2(84, 84)
	head.add_child(em)
	var tv := VBoxContainer.new()
	tv.add_child(UI.title(String(cat.get("name", "")), 50))
	tv.add_child(UI.label(String(cat.get("title", "")), 26, UI.MUTED))
	head.add_child(tv)
	head.add_child(UI.expand())
	var close := UI.button("✕", "dim", 90, 86)
	close.pressed.connect(func(): _detail.queue_free(); _detail = null)
	head.add_child(close)
	v.add_child(head)
	var fac: String = cat.get("faction", "")
	var tags := UI.label("%s · %s · %s · %s" % [Game.rarities.get(str(rarity), ""), Game.CLASS_NAMES.get(cat.get("class", ""), ""),
		cat.get("role_name", ""), Game.faction_name(fac)], 27, Game.faction_color(fac), true)
	tags.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(tags)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 10)
	var stats := GridContainer.new()
	stats.columns = 4
	stats.add_theme_constant_override("h_separation", 34)
	var st: Dictionary = h.get("stats", cat.get("base", {}))
	var pairs := [["Здоровье", st.get("hp", 0)], ["Атака", st.get("atk", 0)], ["Защита", st.get("def", 0)],
		["Скорость", st.get("spd", 0)], ["Крит. шанс", "%d%%" % int(float(cat.get("crit", 0.1)) * 100)],
		["Крит. урон", "×%.2f" % float(cat.get("crit_dmg", 1.5))]]
	if owned:
		pairs = [["Уровень", h.level], ["Звёзды", "★".repeat(int(h.stars)) if int(h.stars) > 0 else "—"],
			["Сила", h.power], ["Осколки", "%d/10" % int(h.shards)]] + pairs
	for pair in pairs:
		stats.add_child(UI.label(pair[0], 25, UI.MUTED))
		stats.add_child(UI.label(str(int(pair[1])) if (pair[1] is float or pair[1] is int) else str(pair[1]), 28, UI.TEXT, true))
	body.add_child(stats)
	var kit: Dictionary = cat.get("kit", {})
	_ability(body, "Базовая атака", kit.get("basic"), "")
	var i := 1
	for sk in kit.get("skills", []):
		_ability(body, "Навык %d" % i, sk, "перезарядка %d с" % int(sk.get("cooldown", 0)))
		i += 1
	_ability(body, "Ультимейт", kit.get("ultimate"), "при 100 энергии")
	_ability(body, "Пассивное", kit.get("passive"), "")
	_ability(body, "Уникальная механика", kit.get("mechanic"), "")
	for f in Game.catalog.get("factions", []):
		if f.code == fac and f.get("strong_against"):
			var adv := UI.label("Фракция: %s. Преимущество над «%s» (+20%% урона). Бонус отряда при 3/4/5 героях фракции." % [
				f.description, Game.faction_name(f.strong_against)], 23, UI.MUTED)
			adv.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			body.add_child(adv)
	for sec in [["Внешность", "appearance"], ["История", "lore"], ["Характер", "personality"]]:
		var txt := String(cat.get(sec[1], ""))
		if txt == "":
			continue
		body.add_child(UI.label(sec[0], 28, UI.ACCENT, true))
		var t := UI.label(txt, 24, UI.TEXT)
		t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		body.add_child(t)
	v.add_child(UI.scroll(body))
	if owned:
		var cost = h.get("level_up_cost")
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 14)
		if cost:
			row.add_child(UI.rewards_row(cost, 28))
			var up := UI.button("Повысить уровень", "primary", 0, 104)
			up.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var hid: String = h.id
			up.pressed.connect(func(): _level_up(hid))
			row.add_child(up)
		else:
			row.add_child(UI.label("Максимальный уровень MVP", 28, UI.GOLD, true))
		v.add_child(row)
		var rank := UI.label("Ранг: ★ из осколков дубликатов (10 осколков = +1 звезда, +8%% характеристик, уровень навыков %d)." % int(h.get("skill_level", 1)), 22, UI.MUTED)
		rank.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(rank)
	else:
		v.add_child(UI.label("Герой ещё не получен — доступен в Зале призыва.", 28, UI.GOLD, true))
	_detail.add_child(v)
	add_child(_detail)


func _ability(parent: Control, kind: String, ab: Variant, note: String) -> void:
	if not (ab is Dictionary) or String(ab.get("name", "")) == "":
		return
	var box := PanelContainer.new()
	box.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.5), Color(1, 1, 1, 0.16), 18, 2))
	var vv := VBoxContainer.new()
	var h := HBoxContainer.new()
	h.add_child(UI.label(kind + ":", 24, UI.MUTED))
	h.add_child(UI.label(" " + String(ab.name), 28, UI.GOLD, true))
	h.add_child(UI.expand())
	if note != "":
		h.add_child(UI.label(note, 22, UI.MUTED))
	vv.add_child(h)
	var d := UI.label(String(ab.get("desc", "")), 24, UI.TEXT)
	d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vv.add_child(d)
	box.add_child(vv)
	parent.add_child(box)


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
