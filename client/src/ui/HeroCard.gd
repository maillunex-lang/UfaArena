extends Button
## Collection card: rendered portrait, rarity frame, level, stars, faction stripe.

var hero := {}
var _tex: TextureRect


func setup(h: Dictionary, selected := false, compact := false) -> void:
	hero = h
	custom_minimum_size = Vector2(230, 300) if not compact else Vector2(180, 230)
	focus_mode = Control.FOCUS_NONE
	var rc: Color = Game.RARITY_COLORS.get(int(h.rarity), Color.WHITE)
	var sb := UI._flat(Color(rc.r * 0.25, rc.g * 0.25, rc.b * 0.3, 0.75), rc if not selected else UI.GOLD, 24, 4 if not selected else 7)
	sb.shadow_color = Color(rc, 0.35)
	sb.shadow_size = 10 if int(h.rarity) >= 5 else 4
	for st in ["normal", "hover", "pressed", "focus"]:
		add_theme_stylebox_override(st, sb)
	_tex = TextureRect.new()
	_tex.set_anchors_preset(Control.PRESET_FULL_RECT)
	_tex.offset_left = 6
	_tex.offset_right = -6
	_tex.offset_top = 6
	_tex.offset_bottom = -40
	_tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	_tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_tex)
	var stripe := ColorRect.new()
	stripe.color = Game.faction_color(h.get("faction", ""))
	stripe.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	stripe.offset_top = -44
	stripe.offset_bottom = -38
	stripe.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(stripe)
	var name_l := UI.label(h.name, 26 if not compact else 22, UI.TEXT, true)
	name_l.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	name_l.offset_top = -40
	name_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	name_l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(name_l)
	var lv := UI.label("%d" % int(h.get("level", 1)), 30, UI.GOLD, true)
	lv.position = Vector2(14, 6)
	lv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(lv)
	var em := GameIcon.new()
	em.kind = String(h.get("faction", ""))
	em.size = Vector2(52, 52) if not compact else Vector2(42, 42)
	em.position = Vector2(custom_minimum_size.x - em.size.x - 6, 6)
	em.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(em)
	# admin-panel rarity frame (transparent centre) drawn over the portrait
	var fr := UI.art("ui/cards/frame_r%d.png" % int(h.rarity))
	if fr:
		var frame := TextureRect.new()
		frame.texture = fr
		frame.set_anchors_preset(Control.PRESET_FULL_RECT)
		frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		frame.stretch_mode = TextureRect.STRETCH_SCALE
		frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(frame)
		move_child(frame, _tex.get_index() + 1)
	# combat rating (server-computed hero power) — required on every card by the brief
	if h.has("power"):
		var pw := PanelContainer.new()
		var psb := UI._flat(Color(0, 0, 0, 0.62), Color(UI.GOLD_DARK, 0.8), 10, 1)
		psb.content_margin_left = 6
		psb.content_margin_right = 6
		pw.add_theme_stylebox_override("panel", psb)
		pw.add_child(UI.label("⚔ " + Game.fmt(int(h.power)), 22 if not compact else 20, UI.GOLD, true))
		pw.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
		pw.position = Vector2(8, custom_minimum_size.y - 84)
		pw.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(pw)
	var st_l := UI.stars(int(h.get("stars", 0)), 22)
	st_l.position = Vector2(14, 40)
	st_l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(st_l)
	_load()


func _load() -> void:
	_tex.texture = await Models.portrait(hero.hero_code)
