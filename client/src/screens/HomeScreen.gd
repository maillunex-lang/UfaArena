extends Control
## Крепость хранителей (home): hero in the centre, context buttons, AFK chest, battle CTA.

var main: Node
var _afk_lbl: Label
var _afk_btn: Button
var _hero_idx := 0
var _hero_lbl: Label
var _battle_btn: Button
var _mail_btn: Button
var _quest_btn: Button


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	var w: Node3D = main.use_world("hub")
	if Game.heroes.size() > 0:
		w.show_hero(Game.heroes[0].hero_code)
	# left column
	var left := VBoxContainer.new()
	left.position = Vector2(14, 40)
	left.add_theme_constant_override("separation", 6)
	add_child(left)
	_afk_btn = UI.icon_button("afk", "Дозор")
	_afk_btn.pressed.connect(_claim_afk)
	left.add_child(_afk_btn)
	_afk_lbl = UI.label("", 24, UI.GOLD, true)
	_afk_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_afk_lbl.custom_minimum_size = Vector2(150, 0)
	left.add_child(_afk_lbl)
	_quest_btn = UI.icon_button("quests", "Задания", false)
	_quest_btn.pressed.connect(func(): main.open("quests"))
	left.add_child(_quest_btn)
	_mail_btn = UI.icon_button("mail", "Почта", false)
	_mail_btn.pressed.connect(func(): main.open("mail"))
	left.add_child(_mail_btn)
	# right column (phased release: locked until their functional block)
	var right := VBoxContainer.new()
	right.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	right.position = Vector2(-164, 40)
	right.add_theme_constant_override("separation", 6)
	add_child(right)
	for it in [["fortress", "Здания", "fortress"], ["shop", "Магазин", "shop"], ["events", "Пропуск", "shop:battlepass"],
			["guild", "Гильдия", ""], ["friends", "Друзья", ""]]:
		var b := UI.icon_button(it[0], it[1])
		var target: String = it[2]
		if target == "":
			b.modulate = Color(0.75, 0.75, 0.8)
			b.pressed.connect(func(): Router.toast("«%s» откроется в следующем функциональном блоке" % it[1]))
		elif target.begins_with("shop:"):
			var tab := target.substr(5)
			b.pressed.connect(func(): main.open("shop", {"tab": tab}))
		else:
			b.pressed.connect(func(): main.open(target))
		right.add_child(b)
	# bottom: hero plate + battle CTA
	var bottom := VBoxContainer.new()
	bottom.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_top = -290
	bottom.offset_left = 60
	bottom.offset_right = -60
	bottom.add_theme_constant_override("separation", 16)
	add_child(bottom)
	var plate := HBoxContainer.new()
	plate.alignment = BoxContainer.ALIGNMENT_CENTER
	var prev := UI.button("◀", "dim", 90, 84)
	prev.pressed.connect(func(): _cycle(-1))
	plate.add_child(prev)
	var pp := UI.glass_panel()
	pp.custom_minimum_size = Vector2(560, 0)
	_hero_lbl = UI.label("", 32, UI.TEXT, true)
	_hero_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	pp.add_child(_hero_lbl)
	plate.add_child(pp)
	var nxt := UI.button("▶", "dim", 90, 84)
	nxt.pressed.connect(func(): _cycle(1))
	plate.add_child(nxt)
	var emo: Variant = Game.cosmetics.get("emote")
	if emo is Dictionary:
		var eb := UI.button("Эмоция", "glass", 170, 84)
		eb.add_theme_font_size_override("font_size", 26)
		var anim := String(emo.get("data", {}).get("anim", "cheer"))
		eb.pressed.connect(func():
			var hn: Node3D = main.world.hero
			if hn:
				var ap: AnimationPlayer = hn.get_meta("ap", null)
				if ap and ap.has_animation(anim):
					ap.play(anim)
				else:
					Models.play(hn, anim)
				Models.queue_idle(hn))
		plate.add_child(eb)
	bottom.add_child(plate)
	_battle_btn = UI.button("", "primary", 0, 124)
	_battle_btn.add_theme_font_size_override("font_size", 40)
	_battle_btn.pressed.connect(_go_battle)
	bottom.add_child(_battle_btn)
	_refresh()
	Game.afk_changed.connect(_refresh)
	Game.heroes_changed.connect(_refresh)
	_poll_badges()


func _refresh() -> void:
	if not is_inside_tree():
		return
	var nxt = Game.campaign.get("next_node")
	_battle_btn.text = ("В бой: этап %s" % nxt) if nxt else "Глава пройдена — повторить бои"
	_battle_btn.text += "  ·  сила %s" % Game.fmt(Game.team_power())
	_update_hero_label()
	_tick_afk()


func _update_hero_label() -> void:
	if Game.heroes.is_empty():
		return
	var h: Dictionary = Game.heroes[_hero_idx % Game.heroes.size()]
	_hero_lbl.text = "%s · %s  ур.%d  %s" % [h.name, h.rarity_name, int(h.level), "★".repeat(int(h.stars))]
	_hero_lbl.add_theme_color_override("font_color", Game.RARITY_COLORS.get(int(h.rarity), Color.WHITE))


func _cycle(d: int) -> void:
	if Game.heroes.is_empty():
		return
	_hero_idx = posmod(_hero_idx + d, Game.heroes.size())
	main.world.show_hero(Game.heroes[_hero_idx].hero_code)
	_update_hero_label()


func _process(_d: float) -> void:
	_tick_afk()


func _tick_afk() -> void:
	if Game.afk.is_empty() or _afk_lbl == null:
		return
	var since := Time.get_unix_time_from_datetime_string(String(Game.afk.since).substr(0, 19))
	var now := Time.get_unix_time_from_system() + Game.server_time_offset
	var cap: float = Game.afk.get("cap_s", 28800)
	var el: float = clampf(now - since, 0, cap)
	var gold_h: float = Game.afk.rates_per_hour.get("gold", 0)
	_afk_lbl.text = "%02d:%02d  +%s" % [int(el / 3600), int(el / 60) % 60, Game.fmt(int(gold_h * el / 3600.0))]


func _claim_afk() -> void:
	Router.busy(true)
	var r := await Api.post_json("/rewards/afk/claim", {}, true)
	Router.busy(false)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Дозор принёс: " + Game.rewards_text(r.data.rewards))
	await Game.refresh_afk()
	main.onboarding_event("afk")


func _go_battle() -> void:
	main.open("campaign")


func _poll_badges() -> void:
	var m := await Api.get_json("/mail")
	if m.ok and is_inside_tree():
		for x in m.data.mail:
			if not x.claimed:
				_add_badge(_mail_btn)
				break
	var q := await Api.get_json("/quests")
	if q.ok and is_inside_tree():
		for x in q.data.quests:
			if x.claimable:
				_add_badge(_quest_btn)
				break


func _add_badge(b: Button) -> void:
	if b.get_node_or_null("Badge"):
		return
	var dot := Panel.new()
	dot.name = "Badge"
	dot.add_theme_stylebox_override("panel", UI._flat(Color("#ff5a4f"), Color.WHITE, 16, 3))
	dot.size = Vector2(32, 32)
	dot.position = Vector2(108, 6)
	dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(dot)
