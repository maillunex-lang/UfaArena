extends Control
## Campaign: 3D region map + node card with enemies, rewards and the battle button.

var main: Node
var map: Node3D
var region := {}
var _card: PanelContainer
var _select := ""
var _head: PanelContainer
var _chapter := 0


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	Router.busy(true)
	var r := await Game.refresh_campaign()
	Router.busy(false)
	if not r.ok:
		Router.error(r)
		return
	var regions: Array = Game.campaign.regions
	_chapter = 0
	_select = String(_p.get("select", ""))
	if _select != "":
		for i in regions.size():
			for n in regions[i].nodes:
				if n.code == _select:
					_p["chapter"] = i
	if _p.has("chapter"):
		_chapter = clampi(int(_p.chapter), 0, regions.size() - 1)
	else:
		for i in regions.size():
			if regions[i].nodes.size() > 0 and bool(regions[i].nodes[0].unlocked):
				_chapter = i
			if _has_open(regions[i]):
				break
	_open_chapter(_chapter)


func _has_open(r: Dictionary) -> bool:
	for n in r.nodes:
		if n.unlocked and not n.cleared:
			return true
	return false


func _open_chapter(i: int) -> void:
	var regions: Array = Game.campaign.regions
	_chapter = i
	region = regions[i]
	if _card:
		_card.queue_free()
		_card = null
	if _head:
		_head.queue_free()
	main.world_kind = ""
	map = main.use_world("campaign")
	map.setup(region)
	map.node_selected.connect(_show_node)
	_head = UI.glass_panel()
	_head.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_head.offset_left = 30
	_head.offset_right = -30
	var hv := VBoxContainer.new()
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 12)
	var prev := UI.button("◀", "glass" if i > 0 else "dim", 96, 84)
	prev.disabled = i <= 0
	prev.pressed.connect(func(): _open_chapter(i - 1))
	top.add_child(prev)
	var t := UI.title("Глава %d/%d. %s" % [i + 1, regions.size(), region.name], 40)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	top.add_child(t)
	var can_next := i < regions.size() - 1 and bool(regions[i + 1].nodes[0].unlocked)
	var nxt := UI.button("▶", "glass" if can_next else "dim", 96, 84)
	nxt.disabled = not can_next
	nxt.pressed.connect(func(): _open_chapter(i + 1))
	top.add_child(nxt)
	hv.add_child(top)
	var sub := UI.label(region.real_place, 26, UI.MUTED)
	sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hv.add_child(sub)
	var cleared := 0
	for n in region.nodes:
		if n.cleared:
			cleared += 1
	hv.add_child(UI.bar(cleared, region.nodes.size(), UI.GOLD, 16))
	_head.add_child(hv)
	add_child(_head)
	var shown := false
	for n in region.nodes:
		if n.unlocked and not n.cleared:
			_show_node(n.code)
			shown = true
			break
	if not shown and region.nodes.size() > 0:
		_show_node(region.nodes[-1].code)
	if _select != "":
		_show_node(_select)
		_select = ""


## Compact battle preparation: stage, enemies, your squad and power, rewards, start button.
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
	_card = UI.solid_panel(Color("#ffe1a0") if n.is_boss else Color("#bfe3ff"))
	_card.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_card.offset_left = UI.SP.m
	_card.offset_right = -UI.SP.m
	_card.offset_top = -560
	_card.offset_bottom = -UI.SP.s
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.s)
	var head := HBoxContainer.new()
	var title := UI.title("%s  %s" % [n.code, n.name], UI.FS.h2)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	head.add_child(title)
	if n.is_boss:
		head.add_child(UI.rarity_tag(6, "БОСС"))
	if n.cleared:
		head.add_child(UI.rarity_tag(2, "пройден"))
	v.add_child(head)
	var place := UI.label(n.real_place + "  ·  " + _territory(n.territory), UI.FS.caption, UI.MUTED)
	place.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(place)
	var teams := HBoxContainer.new()
	teams.add_theme_constant_override("separation", UI.SP.m)
	var mine := VBoxContainer.new()
	mine.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mine.add_child(UI.label("Ваш отряд · ⚔ %s" % Game.exact(Game.team_power()), UI.FS.caption, UI.TEAL, true))
	var row_m := HBoxContainer.new()
	row_m.add_theme_constant_override("separation", 4)
	for pid in Game.formation:
		if pid == null:
			continue
		var h := Game.hero_by_id(pid)
		if h.is_empty():
			continue
		row_m.add_child(_face(String(h.hero_code), int(h.level), UI.RARITY.get(int(h.rarity), UI.TEXT)))
	mine.add_child(row_m)
	teams.add_child(mine)
	var foes_box := VBoxContainer.new()
	foes_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	foes_box.add_child(UI.label("Противники · %d" % n.enemies.size(), UI.FS.caption, UI.DANGER, true))
	var foes := HBoxContainer.new()
	foes.add_theme_constant_override("separation", 4)
	for e in n.enemies:
		foes.add_child(_face(String(e.hero_code), int(e.level), UI.DANGER))
	foes_box.add_child(foes)
	teams.add_child(foes_box)
	v.add_child(teams)
	var rw := HBoxContainer.new()
	rw.add_theme_constant_override("separation", UI.SP.s)
	rw.add_child(UI.label("Награда:", UI.FS.caption, UI.MUTED))
	rw.add_child(UI.rewards_row(n.rewards, 24))
	if not n.cleared:
		rw.add_child(UI.label(" Впервые:", UI.FS.caption, UI.GOLD))
		rw.add_child(UI.rewards_row(n.first_clear_rewards, 24))
	v.add_child(rw)
	var btn := UI.button("В бой" if n.unlocked else "Закрыто: пройдите предыдущий этап", "primary" if n.unlocked else "dim", 0, 100)
	btn.disabled = not n.unlocked
	btn.pressed.connect(func(): Router.goto(Router.BATTLE, {"node_code": n.code, "node": n}))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UI.SP.m)
	var form := UI.button("Изменить отряд", "glass", 300, 100)
	form.pressed.connect(func(): main.open("formation", {"back": "campaign"}))
	row.add_child(form)
	btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(btn)
	v.add_child(row)
	_card.add_child(v)
	add_child(_card)
	UI.pop_in(_card)


func _face(code: String, level: int, ring: Color) -> Control:
	var box := Control.new()
	box.custom_minimum_size = Vector2(86, 96)
	var bg := Panel.new()
	bg.add_theme_stylebox_override("panel", UI._flat(Color(UI.SURFACE_2), ring, 14, 2))
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.add_child(bg)
	var tr := TextureRect.new()
	tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	tr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	tr.offset_left = 3
	tr.offset_top = 3
	tr.offset_right = -3
	tr.offset_bottom = -3
	box.add_child(tr)
	_load_portrait(tr, code)
	var lv := UI.label(str(level), 20, Color.WHITE, true)
	lv.position = Vector2(6, 62)
	box.add_child(lv)
	return box


func _load_portrait(tr: TextureRect, code: String) -> void:
	var tex: Texture2D = await Models.portrait(code, 128)
	if is_instance_valid(tr):
		tr.texture = tex


func _territory(t: String) -> String:
	return {"nature": "природа", "cities": "города", "settlements": "поселения", "dungeons": "подземелья",
		"complexes": "комплексы", "resources": "ресурсы", "dimensions": "измерения"}.get(t, t)
