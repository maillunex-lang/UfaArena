extends Control
## Main screen — modern game panel (brief §5, hybrid structure): top info strip (campaign progress), side columns of
## quick-access icons with badges and live timers, the player's real squad in the centre, daily quests strip and big
## action buttons (Магазин · Призыв · В бой) at the bottom. Every number comes from the server
## (/player/summary, bootstrap state); background and big buttons can be replaced from the admin panel.

var main: Node
var _s := {}
var _root: VBoxContainer
var _afk_sub: Label
var _event_sub: Label
var _event_end := ""
var _caravan_sub: Label
var _caravan_arrive := ""

const DEFAULT_BLOCKS := [{"id": "campaign"}, {"id": "middle"}, {"id": "daily"}, {"id": "actions"}]
const DEFAULT_LEFT := [{"id": "quests", "label": "Задания", "icon": "quests"}, {"id": "mail", "label": "Почта", "icon": "mail"},
	{"id": "friends", "label": "Друзья", "icon": "friends"}, {"id": "chat", "label": "Чат", "icon": "chat"},
	{"id": "caravan", "label": "Караван", "icon": "caravan"}]
const DEFAULT_RIGHT := [{"id": "events", "label": "События", "icon": "events"}, {"id": "afk", "label": "Дозор", "icon": "afk"},
	{"id": "raids", "label": "Рейды", "icon": "shulgan"}, {"id": "arena", "label": "Арена", "icon": "arena"},
	{"id": "tournaments", "label": "Турниры", "icon": "crown"}]
const DEFAULT_ACTIONS := [{"id": "shop", "label": "Магазин", "icon": "shop", "color": "#1d4f8a", "ratio": 1.0},
	{"id": "summon", "label": "Призыв", "icon": "summon", "color": "#4b2a7a", "ratio": 1.0},
	{"id": "battle", "label": "В бой", "icon": "arena", "color": "#8e1b1b", "ratio": 1.5}]
const SIDE_IDS := ["quests", "mail", "friends", "chat", "caravan", "events", "afk", "raids", "arena", "tournaments", "shop",
	"summon", "battle", "rankings", "inventory", "formation", "profile", "settings", "search", "achievements", "heroes",
	"campaign", "guild", "world", "more", "home"]


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("none")
	var art := UI.art("ui/home_bg.png")
	if art:
		var bg := TextureRect.new()
		bg.texture = art
		bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(bg)
	_root = VBoxContainer.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.offset_left = UI.SP.s
	_root.offset_right = -UI.SP.s
	_root.offset_top = UI.SP.s
	_root.offset_bottom = -UI.SP.s
	_root.add_theme_constant_override("separation", UI.SP.s)
	add_child(_root)
	_root.add_child(UI.skeleton(5, 160))
	Game.afk_changed.connect(_tick)
	_load()


func _load() -> void:
	var r := await Api.get_json("/player/summary")
	if not is_inside_tree():
		return
	for c in _root.get_children():
		c.queue_free()
	if not r.ok:
		_root.add_child(UI.state("offline" if r.get("status", 0) == 0 else "error",
			"Не удалось загрузить данные. Проверьте соединение.", "Повторить", func(): main.open("home")))
		return
	_s = r.data
	main.set_badges(_s)
	# block order and visibility come from the admin layout (Редактор игры → Интерфейс)
	var blocks: Array = Game.visible_items(Game.ui_part("home.blocks", DEFAULT_BLOCKS),
		func(k): return k in ["campaign", "middle", "daily", "actions"])
	if blocks.is_empty():
		blocks = DEFAULT_BLOCKS
	for b in blocks:
		match String(b.id):
			"campaign": _root.add_child(_campaign_strip())
			"middle":
				var mid := HBoxContainer.new()
				mid.size_flags_vertical = Control.SIZE_EXPAND_FILL
				mid.add_theme_constant_override("separation", UI.SP.xs)
				mid.add_child(_left_column())
				mid.add_child(_squad())
				mid.add_child(_right_column())
				_root.add_child(mid)
			"daily": _root.add_child(_daily_strip())
			"actions": _root.add_child(_actions())
	if not blocks.any(func(x): return x.id == "middle"):
		_root.add_child(UI.spacer(0))  # the squad block is hidden: keep the rest at the top
	Game.refresh_layout()
	_tick()


# ------------------------------------------------------------------ top strip: campaign progress
func _campaign_strip() -> Control:
	var c: Dictionary = _s.campaign
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(0, 104)
	var sb := UI._flat(Color(UI.SURFACE, 0.9), UI.GOLD_DARK, UI.R.m, 2)
	for st in ["normal", "hover", "pressed"]:
		b.add_theme_stylebox_override(st, UI.skin(sb, "ui/panels/card.png", 512, 48))
	b.pressed.connect(func(): main.open("campaign"))
	var h := HBoxContainer.new()
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.offset_left = UI.SP.m
	h.offset_right = -UI.SP.m
	h.add_theme_constant_override("separation", UI.SP.m)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ic := GameIcon.new()
	ic.kind = "campaign"
	ic.custom_minimum_size = Vector2(64, 64)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(ic)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var nx = c.get("next")
	var t := UI.label(("Поход · %s «%s»" % [nx.code, nx.name]) if nx else "Поход · все этапы пройдены", UI.FS.body, UI.TEXT, true)
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	t.clip_text = true
	v.add_child(t)
	var pr := UI.progress(int(c.cleared), int(c.total), "Пройдено %d из %d" % [int(c.cleared), int(c.total)], UI.GOLD_DARK, 22)
	pr.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(pr)
	h.add_child(v)
	h.add_child(UI.label("›", UI.FS.h2, UI.GOLD, true))
	b.add_child(h)
	return b


# ------------------------------------------------------------------ side columns
func _side(icon: String, caption: String, sub: String, badge_n: int, cb: Callable, glow := false) -> Button:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(150, 156)
	for st in ["normal", "hover", "pressed", "focus"]:
		b.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 0)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var bubble := PanelContainer.new()
	var rs := UI._round_glass()
	if glow:
		rs.border_color = UI.GOLD
		rs.shadow_color = Color(1.0, 0.78, 0.3, 0.6)
		rs.shadow_size = 16
	bubble.add_theme_stylebox_override("panel", UI.skin(rs, "ui/nav/bubble.png", 256, 100))
	bubble.custom_minimum_size = Vector2(100, 100)
	bubble.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	bubble.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ic := GameIcon.new()
	ic.kind = icon
	ic.custom_minimum_size = Vector2(66, 66)
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bubble.add_child(ic)
	v.add_child(bubble)
	var l := UI.label(caption, UI.FS.caption, UI.TEXT, true)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(l)
	var sl := UI.label(sub, 22, UI.WARNING, true)
	sl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	sl.visible = sub != ""
	sl.name = "Sub"
	v.add_child(sl)
	b.add_child(v)
	if badge_n > 0:
		var bd := UI.badge(badge_n)
		bd.position = Vector2(104, 0)
		b.add_child(bd)
	b.pressed.connect(func(): Sfx.play("open"); cb.call())
	return b


func _column() -> VBoxContainer:
	var v := VBoxContainer.new()
	v.custom_minimum_size = Vector2(150, 0)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", UI.SP.xs)
	return v


func _left_column() -> Control:
	var col := _column()
	for it in Game.visible_items(Game.ui_part("home.left", DEFAULT_LEFT), func(k): return k in SIDE_IDS):
		col.add_child(_side_item(it))
	return col


func _right_column() -> Control:
	var col := _column()
	for it in Game.visible_items(Game.ui_part("home.right", DEFAULT_RIGHT), func(k): return k in SIDE_IDS):
		col.add_child(_side_item(it))
	return col


## A side button by its layout id: live counters / timers for the known ones, a plain shortcut for the rest.
func _side_item(it: Dictionary) -> Control:
	var id := String(it.id)
	var lbl := String(it.get("label", id))
	var ic := String(it.get("icon", id))
	var q: Dictionary = _s.quests
	var soc: Dictionary = _s.social
	match id:
		"quests":
			return _side(ic, lbl, "%d/%d" % [int(q.daily_done), int(q.daily_total)], int(q.claimable), func(): main.open("quests"))
		"mail":
			return _side(ic, lbl, "", int(_s.mail_unclaimed), func(): main.open("mail"))
		"friends":
			return _side(ic, lbl, "", int(soc.friend_requests) + int(soc.gifts), func(): main.open("friends"))
		"chat":
			return _side(ic, lbl, "", int(soc.chat_unread), func(): main.open_mini_chat())
		"caravan":
			var cv := _side(ic, lbl, "", 0, func(): main.open("caravan"))
			_caravan_sub = cv.find_child("Sub", true, false)
			_load_caravan()
			return cv
		"events":  # nearest-ending world event with a live countdown
			var ev = null
			for e in _s.events:
				if ev == null or String(e.ends_at) < String(ev.ends_at):
					ev = e
			var eb := _side(ic, lbl, "", 0, func(): main.open("events"), ev != null)
			_event_sub = eb.find_child("Sub", true, false)
			_event_end = String(ev.ends_at) if ev else ""
			return eb
		"afk":  # patrol (AFK) chest: one tap claims, the timer shows time left until the cap
			var afk := _side(ic, lbl, "", 0, _claim_afk, bool(_s.afk.full))
			_afk_sub = afk.find_child("Sub", true, false)
			return afk
	return _side(ic, lbl, "", 0, func(): main.do_action(id, "home"))


func _process(_d: float) -> void:
	if Engine.get_process_frames() % 30 == 0:
		_tick()


func _tick() -> void:
	if is_instance_valid(_afk_sub) and not Game.afk.is_empty():
		var since := Time.get_unix_time_from_datetime_string(String(Game.afk.since).substr(0, 19))
		var now := Time.get_unix_time_from_system() + Game.server_time_offset
		var cap: float = Game.afk.get("cap_s", 28800)
		var el: float = clampf(now - since, 0, cap)
		_afk_sub.visible = true
		_afk_sub.text = "Полон!" if el >= cap else _dur(cap - el)
		_afk_sub.add_theme_color_override("font_color", UI.bad_color() if el >= cap else UI.WARNING)
	if is_instance_valid(_caravan_sub) and _caravan_arrive != "":
		var ct := Time.get_unix_time_from_datetime_string(_caravan_arrive.substr(0, 19)) - Time.get_unix_time_from_system()
		_caravan_sub.text = ("в пути " + _dur(ct)) if ct > 0 else "прибыл"
	if is_instance_valid(_event_sub) and _event_end != "":
		var t := Time.get_unix_time_from_datetime_string(_event_end.substr(0, 19)) - Time.get_unix_time_from_system()
		_event_sub.visible = true
		_event_sub.text = _dur(t) if t > 0 else "итоги"


## Caravan status under its icon: travel countdown or the current land.
func _load_caravan() -> void:
	var r := await Api.get_json("/caravan")
	if not r.ok or not is_instance_valid(_caravan_sub):
		return
	_caravan_sub.visible = true
	if r.data.traveling:
		_caravan_arrive = String(r.data.arrive_at)
	else:
		_caravan_arrive = ""
		_caravan_sub.text = String(r.data.location_name)
		_caravan_sub.add_theme_color_override("font_color", UI.TEAL)


func _dur(t: float) -> String:
	var d := int(t / 86400)
	if d > 0:
		return "%dд %dч" % [d, int(fmod(t, 86400) / 3600)]
	return "%dч %02dм" % [int(t / 3600), int(fmod(t, 3600) / 60)]


func _claim_afk() -> void:
	var r := await Api.post_json("/rewards/afk/claim", {}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Дозор принёс: " + Game.rewards_text(r.data.rewards))
	await Game.refresh_afk()
	main.onboarding_event("afk")
	if is_inside_tree():
		_load()


# ------------------------------------------------------------------ centre: the real squad
func _squad() -> Control:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for st in ["normal", "hover", "pressed", "focus"]:
		b.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	b.pressed.connect(func(): main.open("formation", {"back": "home"}))
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", UI.SP.s)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var t := UI.title("Ваш отряд", UI.FS.h2)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
	# formation: slots 0-2 back row, 3-4 front row (front drawn larger, closer to the viewer)
	var back := HBoxContainer.new()
	back.alignment = BoxContainer.ALIGNMENT_CENTER
	back.add_theme_constant_override("separation", UI.SP.s)
	back.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var front := HBoxContainer.new()
	front.alignment = BoxContainer.ALIGNMENT_CENTER
	front.add_theme_constant_override("separation", UI.SP.l)
	front.mouse_filter = Control.MOUSE_FILTER_IGNORE
	for i in Game.formation.size():
		(back if i < 3 else front).add_child(_hero_face(Game.formation[i], 172 if i < 3 else 214))
	v.add_child(back)
	v.add_child(front)
	var pw := UI.label("Сила отряда  ⚔ %s" % Game.exact(Game.team_power()), UI.FS.body_l, UI.GOLD, true)
	pw.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(pw)
	# player level and experience (server rule: 100 × level experience per level)
	var lvl := int(Game.profile.get("level", 1))
	var xp := int(Game.profile.get("exp", 0))
	var bar := UI.progress(xp, 100 * lvl, "Уровень %d · опыт %d / %d" % [lvl, xp, 100 * lvl], UI.TEAL, 24)
	bar.custom_minimum_size.x = 520
	bar.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(bar)
	var hint := UI.label("Нажмите, чтобы изменить отряд", UI.FS.caption, UI.MUTED)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(hint)
	b.add_child(v)
	return b


func _hero_face(id: Variant, sz: int) -> Control:
	var box := VBoxContainer.new()
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_theme_constant_override("separation", 0)
	var ring := PanelContainer.new()
	ring.custom_minimum_size = Vector2(sz, sz)
	ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var h: Dictionary = Game.hero_by_id(id) if id else {}
	var rc: Color = Game.RARITY_COLORS.get(int(h.get("rarity", 1)), UI.LINE) if not h.is_empty() else Color(UI.LINE, 0.6)
	var sb := UI._flat(Color(UI.SURFACE_2, 0.9), rc, sz / 2, 4)
	ring.add_theme_stylebox_override("panel", UI.skin(sb, "ui/home/hero_ring.png", 256, 100))
	box.add_child(ring)
	if h.is_empty():
		var e := UI.label("+", UI.FS.h1, UI.MUTED, true)
		e.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		e.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		ring.add_child(e)
		return box
	var tex := TextureRect.new()
	tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://src/ui/circle.gdshader")
	tex.material = mat
	ring.add_child(tex)
	_load_face(tex, String(h.hero_code))
	var l := UI.label("%s · %d" % [h.name, int(h.level)], 22, UI.TEXT, true)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.custom_minimum_size.x = sz
	l.clip_text = true
	box.add_child(l)
	return box


func _load_face(tex: TextureRect, code: String) -> void:
	var t := await Models.portrait(code)
	if is_instance_valid(tex):
		tex.texture = t


# ------------------------------------------------------------------ bottom: daily quests + big actions
func _daily_strip() -> Control:
	var q: Dictionary = _s.quests
	var c := UI.card(UI.GOLD_DARK if int(q.claimable) > 0 else Color(0, 0, 0, 0), UI.SP.s)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", UI.SP.m)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_child(UI.label("Ежедневные задания %d/%d" % [int(q.daily_done), int(q.daily_total)], UI.FS.body, UI.TEXT, true))
	var line := []
	for x in q.daily:
		line.append("%s %d/%d" % [x.title, mini(int(x.progress), int(x.target)), int(x.target)])
	var l := UI.label(" · ".join(line) if line.size() > 0 else "Сегодня заданий нет", UI.FS.caption, UI.MUTED)
	l.clip_text = true
	v.add_child(l)
	h.add_child(v)
	var b := UI.button("Забрать" if int(q.claimable) > 0 else "Все задания", "primary" if int(q.claimable) > 0 else "glass", 230, 84)
	b.pressed.connect(func(): main.open("quests"))
	h.add_child(b)
	c.add_child(h)
	return c


func _big(text: String, sub: String, icon: String, base: StyleBoxFlat, art_path: String, cb: Callable, ratio := 1.0) -> Button:
	var b := Button.new()
	b.text = text  # real caption (accessibility/tests); drawn by the custom layout below
	b.add_theme_color_override("font_color", Color.TRANSPARENT)
	b.add_theme_color_override("font_hover_color", Color.TRANSPARENT)
	b.add_theme_color_override("font_pressed_color", Color.TRANSPARENT)
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(0, 150)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.size_flags_stretch_ratio = ratio
	b.add_theme_stylebox_override("normal", UI.skin(base, art_path, 420, 56))
	b.add_theme_stylebox_override("hover", UI.skin(base, art_path, 420, 56, Color(1.12, 1.12, 1.12)))
	b.add_theme_stylebox_override("pressed", UI.skin(base, art_path, 420, 56, Color(0.85, 0.85, 0.85)))
	var h := HBoxContainer.new()
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_theme_constant_override("separation", 6)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ic := GameIcon.new()
	ic.kind = icon
	ic.custom_minimum_size = Vector2(54, 54)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(ic)
	var v := VBoxContainer.new()
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var t := UI.title(text, 40 if ratio > 1.0 else 32)
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(t)
	if sub != "":
		var s := UI.label(sub, 22, Color(1, 1, 1, 0.85), true)
		s.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(s)
	h.add_child(v)
	b.add_child(h)
	b.pressed.connect(func(): Sfx.play("open"); cb.call())
	return b


func _actions() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UI.SP.s)
	var art := {"shop": "ui/home/shop_button.png", "summon": "ui/home/summon_button.png", "battle": "ui/home/battle_button.png"}
	for it in Game.visible_items(Game.ui_part("home.actions", DEFAULT_ACTIONS), func(k): return k in SIDE_IDS):
		var id := String(it.id)
		var col := Color(String(it.get("color", "#1d4f8a")))
		var edge := {"#1d4f8a": Color("#9fd3ff"), "#4b2a7a": Color("#d6b8ff")}  # the built-in look stays identical
		var base := UI._flat(col, UI.GOLD if id == "battle" else edge.get(String(it.get("color", "")).to_lower(), col.lightened(0.55)), UI.R.m, 3)
		var sub := ""
		var cb := func(): main.do_action(id, "home")
		if id == "battle":
			base.shadow_color = Color(1.0, 0.4, 0.2, 0.45)
			base.shadow_size = 12
			var nx = _s.campaign.get("next")
			var code: String = nx.code if nx else ""
			sub = ("Этап " + code) if nx else "Карта похода"
			cb = func(): main.open("campaign", {"select": code} if code != "" else {})
		row.add_child(_big(String(it.get("label", id)), sub, String(it.get("icon", id)), base,
			String(art.get(id, "ui/home/%s_button.png" % id)), cb, float(it.get("ratio", 1.0))))
	return row
