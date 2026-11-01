extends Control
## Player profile: header card + statistics + tabs (Обзор, Герои, Достижения, История). Own profile; other players
## open the same data through PlayerPopup.

var main: Node
var tab := "overview"
var _d := {}
var _prog := {}
var _body: VBoxContainer
var _tabs_row: Control


func setup(m: Node, p: Dictionary) -> void:
	main = m
	main.use_world("none")
	tab = String(p.get("tab", tab))
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.offset_left = UI.SP.m
	root.offset_right = -UI.SP.m
	root.offset_top = UI.SP.s
	root.add_theme_constant_override("separation", UI.SP.m)
	add_child(root)
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", UI.SP.m)
	_tabs_row = HBoxContainer.new()
	var head := VBoxContainer.new()
	root.add_child(head)
	root.add_child(_tabs_row)
	root.add_child(UI.scroll(_body))
	UI.keep_wrapped(_body)
	_body.add_child(UI.skeleton(3, 140))
	var a := await Api.get_json("/social/profile/" + Api.user_id)
	var b := await Api.get_json("/progression")
	if not is_inside_tree():
		return
	if not a.ok:
		for c in _body.get_children():
			c.queue_free()
		_body.add_child(UI.state("error", "Профиль не загрузился.", "Повторить", func(): main.open("profile")))
		return
	_d = a.data
	_prog = b.data if b.ok else {}
	head.add_child(_header())
	if not b.ok:  # partial data: the profile is shown, progression could not be loaded
		var pl := UI.label("Достижения и история временно недоступны — показана основная информация.", 22, UI.WARNING)
		pl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		head.add_child(pl)
	_render()


func _header() -> Control:
	var c: Dictionary = _d.card
	var card := UI.card(UI.GOLD_DARK)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", UI.SP.l)
	var av := TextureRect.new()
	av.custom_minimum_size = Vector2(150, 150)
	av.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	av.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://src/ui/circle.gdshader")
	av.material = mat
	h.add_child(av)
	var code := String(_d.squad[0].hero_code) if _d.squad.size() > 0 else "azamat"
	_portrait(av, code)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_child(UI.title(String(c.nickname), UI.FS.h1))
	var t: Variant = Game.cosmetics.get("title")
	if t is Dictionary:
		v.add_child(UI.label("«%s»" % String(t.get("data", {}).get("text", "")), UI.FS.body, UI.GOLD))
	v.add_child(UI.label("%s · уровень %d%s" % [c.uralia_id, int(c.level), ("  · VIP %d" % int(c.vip_level)) if int(c.vip_level) > 0 else ""], UI.FS.body, UI.MUTED))
	v.add_child(UI.label("Боевой рейтинг: %s" % Game.exact(int(c.power)), UI.FS.body_l, UI.TEXT, true))
	if c.guild:
		v.add_child(UI.label("Гильдия: [%s] %s" % [c.guild.tag, c.guild.name], UI.FS.body, UI.TEAL))
	h.add_child(v)
	card.add_child(h)
	return card


func _portrait(tr: TextureRect, code: String) -> void:
	var tex: Texture2D = await Models.portrait(code, 200)
	if is_instance_valid(tr):
		tr.texture = tex


func _render() -> void:
	for c in _tabs_row.get_children():
		c.queue_free()
	_tabs_row.add_child(UI.tabs([["overview", "Обзор"], ["heroes", "Герои"], ["achievements", "Достижения"], ["history", "История"]], tab,
		func(k: String): tab = k; _render()))
	for c in _body.get_children():
		c.queue_free()
	match tab:
		"overview": _overview()
		"heroes": _heroes()
		"achievements": _achievements()
		"history": _history()


func _stat(grid: GridContainer, name: String, value: String) -> void:
	var c := UI.card()
	var v := VBoxContainer.new()
	v.add_child(UI.label(name, UI.FS.caption, UI.MUTED))
	v.add_child(UI.label(value, UI.FS.h3, UI.GOLD, true))
	c.add_child(v)
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(c)


func _overview() -> void:
	var st: Dictionary = _prog.get("stats", {})
	var rec: Dictionary = _prog.get("records", {})
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", UI.SP.m)
	grid.add_theme_constant_override("v_separation", UI.SP.m)
	_stat(grid, "Пройдено этапов", str((Game.campaign.get("cleared", []) as Array).size()))
	_stat(grid, "Героев в коллекции", str(_d.heroes.size()))
	_stat(grid, "Достижений", str(int(_d.achievements)))
	_stat(grid, "Репутация", "%d — %s" % [int(_prog.get("reputation", 0)), _prog.get("title", "")])
	_stat(grid, "Победы на арене", str(int(st.get("arena_wins", 0))))
	_stat(grid, "Лучший рейтинг арены", str(rec.get("best_arena_rating", "—")) if rec.get("best_arena_rating") != null else "—")
	_stat(grid, "Урон по боссам", Game.exact(int(st.get("raid_damage", 0))))
	_stat(grid, "Друзей", str(int(st.get("friends", 0))))
	_body.add_child(grid)
	var cos := UI.button("Гардероб: рамки и титулы", "glass", 0, 84)
	cos.pressed.connect(func(): main.open("shop", {"tab": "cosmetics"}))
	_body.add_child(cos)


func _heroes() -> void:
	for h in _d.heroes:
		var c := UI.card()
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", UI.SP.m)
		var n := UI.label(String(h.name), UI.FS.body_l, UI.RARITY.get(int(h.rarity), UI.TEXT), true)
		n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(n)
		row.add_child(UI.label("ур.%d %s" % [int(h.level), "★".repeat(int(h.stars))], UI.FS.body, UI.GOLD))
		c.add_child(row)
		_body.add_child(c)


func _achievements() -> void:
	for a in _prog.get("achievements", []):
		var c := UI.card(UI.GOLD_DARK if a.done else Color(0, 0, 0, 0))
		var v := VBoxContainer.new()
		v.add_child(UI.label(("✓ " if a.done else "") + String(a.name), UI.FS.body_l, UI.GOLD if a.done else UI.TEXT, true))
		v.add_child(UI.label(String(a.desc), UI.FS.caption, UI.MUTED))
		if not a.done:
			v.add_child(UI.progress(int(a.progress), max(1, int(a.goal)), "%s / %s" % [Game.exact(int(a.progress)), Game.exact(int(a.goal))], UI.TEAL, 20))
		c.add_child(v)
		_body.add_child(c)


func _history() -> void:
	var items: Array = _d.activity
	if items.is_empty() and _prog.get("legacy", []).is_empty():
		_body.add_child(UI.state("empty", "История появится после боёв на арене, рейдов, турниров и событий."))
	for a in items:
		var c := UI.card()
		var l := UI.label("%s  %s" % [UI.local_time(String(a.at)), a.text], UI.FS.body, UI.TEXT)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		c.add_child(l)
		_body.add_child(c)
	for h in _prog.get("legacy", []):
		var c := UI.card(UI.GOLD_DARK)
		var r: Dictionary = h.result
		var l := UI.label("%s · %s" % [{"arena": "Сезон арены", "tournament": "Турнир", "raid": "Рейд", "event": "Событие"}.get(h.category, h.category),
			String(r.get("name", r.get("league", r.get("boss", ""))))], UI.FS.body, UI.GOLD)
		c.add_child(l)
		_body.add_child(c)
