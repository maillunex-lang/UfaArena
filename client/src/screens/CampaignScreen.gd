extends Control
## Campaign: 3D region map + node card with enemies, rewards and the battle button.

var main: Node
var map: Node3D
var region := {}
var _card: PanelContainer


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	Router.busy(true)
	var r := await Game.refresh_campaign()
	Router.busy(false)
	if not r.ok:
		Router.error(r)
		return
	region = Game.campaign.regions[0]
	main.world_kind = ""
	map = main.use_world("campaign")
	map.setup(region)
	map.node_selected.connect(_show_node)
	var head := UI.glass_panel()
	head.set_anchors_preset(Control.PRESET_TOP_WIDE)
	head.offset_left = 30
	head.offset_right = -30
	var hv := VBoxContainer.new()
	hv.add_child(UI.title("Глава 1. " + region.name, 44))
	var sub := UI.label(region.real_place, 26, UI.MUTED)
	sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hv.add_child(sub)
	var cleared := 0
	for n in region.nodes:
		if n.cleared:
			cleared += 1
	hv.add_child(UI.bar(cleared, region.nodes.size(), UI.GOLD, 16))
	head.add_child(hv)
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(head)
	for n in region.nodes:
		if n.unlocked and not n.cleared:
			_show_node(n.code)
			break


func _show_node(code: String) -> void:
	var n := {}
	for x in region.nodes:
		if x.code == code:
			n = x
	if n.is_empty():
		return
	Sfx.play("open")
	if _card:
		_card.queue_free()
	_card = UI.glass_panel(Color("#ffe1a0") if n.is_boss else Color("#bfe3ff"))
	_card.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_card.offset_left = 30
	_card.offset_right = -30
	_card.offset_top = -470
	_card.offset_bottom = -10
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	var title := UI.title("%s  %s%s" % [n.code, n.name, "  · БОСС" if n.is_boss else ""], 42)
	v.add_child(title)
	var place := UI.label(n.real_place + "   ·   " + _territory(n.territory), 26, UI.MUTED)
	place.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(place)
	var foes := HBoxContainer.new()
	foes.add_theme_constant_override("separation", 10)
	for e in n.enemies:
		var tr := TextureRect.new()
		tr.custom_minimum_size = Vector2(110, 110)
		tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		foes.add_child(tr)
		_load_portrait(tr, e.hero_code)
		var lv := UI.label("ур.%d" % int(e.level), 22, Color("#ffb3a8"), true)
		lv.position = Vector2(4, 80)
		tr.add_child(lv)
	v.add_child(foes)
	var rw := HBoxContainer.new()
	rw.add_theme_constant_override("separation", 14)
	rw.add_child(UI.label("Награда:", 28, UI.MUTED))
	rw.add_child(UI.rewards_row(n.rewards, 28))
	if not n.cleared:
		rw.add_child(UI.label("  Первое:", 28, UI.GOLD))
		rw.add_child(UI.rewards_row(n.first_clear_rewards, 28))
	v.add_child(rw)
	var btn := UI.button("Сражаться" if n.unlocked else "Закрыто", "primary" if n.unlocked else "dim", 0, 112)
	btn.disabled = not n.unlocked
	btn.pressed.connect(func(): Router.goto(Router.BATTLE, {"node_code": n.code, "node": n}))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 16)
	var form := UI.button("Отряд · сила %s" % Game.fmt(Game.team_power()), "glass", 380, 112)
	form.pressed.connect(func(): main.open("formation", {"back": "campaign"}))
	row.add_child(form)
	btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(btn)
	v.add_child(row)
	_card.add_child(v)
	add_child(_card)


func _load_portrait(tr: TextureRect, code: String) -> void:
	tr.texture = await Models.portrait(code, 160)


func _territory(t: String) -> String:
	return {"nature": "природа", "cities": "города", "settlements": "поселения", "dungeons": "подземелья",
		"complexes": "комплексы", "resources": "ресурсы", "dimensions": "измерения"}.get(t, t)
