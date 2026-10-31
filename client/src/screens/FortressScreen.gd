extends Control
## Крепость хранителей: buildings, effects and upgrades (server-validated costs).

var main: Node
var _list: VBoxContainer


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("hub")
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 24
	panel.offset_right = -24
	panel.offset_top = -1000
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Крепость хранителей", 48))
	head.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 200, 90)
	back.pressed.connect(func(): main.open("home"))
	head.add_child(back)
	v.add_child(head)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_list))
	_load()


func _load() -> void:
	var r := await Api.get_json("/fortress")
	if r.ok and is_inside_tree():
		_render(r.data.buildings)


func _render(buildings: Array) -> void:
	for c in _list.get_children():
		c.queue_free()
	for b in buildings:
		var card := PanelContainer.new()
		card.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.5), Color(1, 1, 1, 0.25), 24, 2))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 16)
		var ic := GameIcon.new()
		ic.kind = "fortress" if not b.locked else "lock"
		ic.custom_minimum_size = Vector2(90, 90)
		h.add_child(ic)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.add_child(UI.label("%s  ·  ур. %d/%d" % [b.name, int(b.level), int(b.max_level)], 32, UI.GOLD, true))
		var eff := UI.label(b.effect, 25, UI.TEXT)
		eff.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		info.add_child(eff)
		if b.upgrade_cost:
			info.add_child(UI.rewards_row(b.upgrade_cost, 24))
		h.add_child(info)
		if b.upgrade_cost and not b.locked:
			var up := UI.button("Улучшить", "primary", 230, 96)
			var code: String = b.code
			up.pressed.connect(func(): _upgrade(code))
			h.add_child(up)
		card.add_child(h)
		_list.add_child(card)


func _upgrade(code: String) -> void:
	var r := await Api.post_json("/fortress/buildings/%s/upgrade" % code, {}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("door")
	Game.set_wallet(r.data.wallet)
	_render(r.data.buildings)
	Router.toast("Здание улучшено")
	var node: Node3D = main.world.building_node(code)
	if node:
		node.create_tween().tween_property(node, "scale", node.scale * 1.06, 0.25).set_trans(Tween.TRANS_BACK)
	Game.refresh_heroes()
	Game.refresh_afk()
