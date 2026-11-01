extends Control
## World: map of regions (campaign chapters with world-event status) + activity catalogue.
## Activities that the game does not have yet are shown as locked, never as fake screens.

var main: Node
var _body: VBoxContainer


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("none")
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", UI.SP.l)
	var sc := UI.scroll(_body)
	sc.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	sc.offset_left = UI.SP.m
	sc.offset_right = -UI.SP.m
	sc.offset_top = UI.SP.s
	add_child(sc)
	UI.keep_wrapped(_body)
	_body.add_child(UI.title("Мир Уралии", UI.FS.h1))
	_catalog()
	_body.add_child(UI.skeleton(3, 120))
	_regions()


func _catalog() -> void:
	_body.add_child(UI.section("Активности"))
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", UI.SP.m)
	grid.add_theme_constant_override("v_separation", UI.SP.m)
	var items := [
		["campaign", "Регионы", "Главы похода", "campaign", false],
		["events", "События", "Общая цель сервера", "events", false],
		["arena", "Боссы", "Рейды и мировые боссы", "raids", false],
		["arena", "Испытания", "Арена и турниры", "arena", false],
		["guild", "Экспедиции", "Гильдейские походы", "guild:events", false],
		["summon", "Турниры", "Недельные и месячные", "tournaments", false],
		["lock", "Подземелья", "Скоро", "", true],
		["lock", "Башня", "Скоро", "", true],
		["lock", "Тайны", "Скоро", "", true],
	]
	for it in items:
		var t := UI.tile(it[0], it[1], it[2], it[4])
		var target: String = it[3]
		if it[4]:
			var nm: String = it[1]
			t.pressed.connect(func(): Router.toast("«%s» появятся в одном из следующих обновлений" % nm))
		elif target.begins_with("guild:"):
			t.pressed.connect(func(): main.open("guild", {"tab": target.substr(6)}))
		else:
			t.pressed.connect(func(): main.open(target))
		grid.add_child(t)
	_body.add_child(grid)


func _regions() -> void:
	var r := await Game.refresh_campaign()
	var w := await Api.get_json("/events/world")
	if not is_inside_tree():
		return
	_body.get_child(_body.get_child_count() - 1).queue_free()
	_body.add_child(UI.section("Регионы", "Открыть поход", func(): main.open("campaign")))
	if not r.ok:
		_body.add_child(UI.state("error", "Регионы не загрузились.", "Повторить", func(): main.open("world")))
		return
	var unlocked: Array = w.data.get("unlocked", []) if w.ok else []
	for i in Game.campaign.regions.size():
		var reg: Dictionary = Game.campaign.regions[i]
		var open: bool = reg.nodes.size() > 0 and bool(reg.nodes[0].unlocked)
		var done := 0
		for n in reg.nodes:
			done += int(n.cleared)
		var card := UI.card(UI.GOLD_DARK if open else Color(0, 0, 0, 0))
		# admin-panel region banner (regions/<code>.png, 1024×320) as the card background
		var ban := UI.art("regions/%s.png" % String(reg.get("code", "")))
		if ban:
			var bg := TextureRect.new()
			bg.texture = ban
			bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
			bg.modulate = Color(1, 1, 1, 0.55) if open else Color(0.5, 0.5, 0.5, 0.4)
			bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
			bg.clip_contents = true
			card.add_child(bg)
			card.custom_minimum_size.y = 200
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", UI.SP.xs)
		var h := HBoxContainer.new()
		var t := UI.label("Глава %d. %s" % [i + 1, reg.name], UI.FS.body_l, UI.TEXT if open else UI.MUTED, true)
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(t)
		var status = reg.get("world_status")
		if status:
			h.add_child(UI.rarity_tag(2 if status == "liberated" else 6, "освобождён" if status == "liberated" else "опалён Тьмой"))
		elif not open:
			h.add_child(UI.label("закрыто", UI.FS.caption, UI.MUTED))
		v.add_child(h)
		v.add_child(UI.label(String(reg.real_place), UI.FS.caption, UI.MUTED))
		v.add_child(UI.progress(done, reg.nodes.size(), "%d / %d этапов" % [done, reg.nodes.size()], UI.TEAL, 20))
		card.add_child(v)
		if open:
			var b := Button.new()
			b.flat = true
			b.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			var idx: int = i
			b.pressed.connect(func(): main.open("campaign", {"chapter": idx}))
			card.add_child(b)
		_body.add_child(card)
	if unlocked.size() > 0:
		_body.add_child(UI.section("Открытые территории"))
		var c := UI.card()
		var l := UI.label(", ".join(unlocked), UI.FS.body, UI.TEXT)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		c.add_child(l)
		_body.add_child(c)
