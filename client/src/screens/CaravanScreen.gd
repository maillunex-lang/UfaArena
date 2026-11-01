extends Control
## Caravan — the player's moving base (lore stage S4): modules (former fortress buildings, same levels), the council
## without a single captain (hidden influence shown only as moods and words, C17) and the route along the Roads of Breath.
## Data: GET /caravan, POST /fortress/buildings/{code}/upgrade, POST /caravan/travel.

const WorldMap := preload("res://src/ui/WorldMap.gd")
const TABS := [["modules", "Модули"], ["council", "Совет"], ["route", "Маршрут"]]
const MODULE_ICONS := {"summon_hall": "summon", "forge": "arena", "training": "heroes", "alchemy": "afk", "storage": "shop",
	"guild_house": "home", "library": "quests", "research": "settings", "towers": "guild"}

var main: Node
var tab := "modules"
var d := {}
var _head: VBoxContainer
var _tabs: HBoxContainer
var _body: VBoxContainer
var _travel_lbl: Label


func setup(m: Node, p: Dictionary) -> void:
	main = m
	main.use_world("none")
	tab = String(p.get("tab", tab))
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.offset_left = UI.SP.m
	v.offset_right = -UI.SP.m
	v.offset_top = UI.SP.s
	v.add_theme_constant_override("separation", UI.SP.s)
	add_child(v)
	var h := HBoxContainer.new()
	h.add_child(UI.title("Караван", UI.FS.h1))
	h.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 180, 80)
	back.pressed.connect(func(): main.open("home"))
	h.add_child(back)
	v.add_child(h)
	_head = VBoxContainer.new()
	v.add_child(_head)
	_tabs = HBoxContainer.new()
	_tabs.add_theme_constant_override("separation", UI.SP.s)
	v.add_child(_tabs)
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", UI.SP.m)
	v.add_child(UI.scroll(_body))
	UI.keep_wrapped(_body)
	_body.add_child(UI.skeleton(3, 160))
	_load()


func _load() -> void:
	var r := await Api.get_json("/caravan")
	if not is_inside_tree():
		return
	if not r.ok:
		for c in _body.get_children():
			c.queue_free()
		_body.add_child(UI.state("offline" if int(r.get("status", 0)) == 0 else "error", "Караван не отвечает.", "Повторить", _load))
		return
	d = r.data
	_render()


func _render() -> void:
	for c in _head.get_children():
		c.queue_free()
	var card := UI.card(UI.GOLD_DARK)
	var hv := VBoxContainer.new()
	hv.add_theme_constant_override("separation", UI.SP.xs)
	if d.traveling:
		hv.add_child(UI.label("В пути: %s → %s" % [d.location_name, d.destination_name], UI.FS.body_l, UI.TEXT, true))
		_travel_lbl = UI.label("", UI.FS.caption, UI.WARNING, true)
		hv.add_child(_travel_lbl)
		hv.add_child(UI.label("На дороге местных припасов нет.", UI.FS.caption, UI.MUTED))
	else:
		hv.add_child(UI.label("Стоянка: %s" % d.location_name, UI.FS.body_l, UI.TEXT, true))
		hv.add_child(UI.label("Местные припасы в дозоре: %s" % d.location_bonus, UI.FS.caption, UI.ok_color()))
	var lead_line := String(d.leader_text)
	if d.leader != null:
		lead_line = "Ближайший советник — %s: %s" % [_council_name(String(d.leader)), d.leader_text]
	hv.add_child(UI.label(lead_line, UI.FS.caption, UI.GOLD))
	card.add_child(hv)
	_head.add_child(card)
	for c in _tabs.get_children():
		c.queue_free()
	for t in TABS:
		var key: String = t[0]
		var b := UI.button(String(t[1]), "primary" if key == tab else "glass", 0, 76)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.pressed.connect(func(): tab = key; _render())
		_tabs.add_child(b)
	for c in _body.get_children():
		c.queue_free()
	match tab:
		"modules": _modules()
		"council": _council()
		"route": _route()
	_tick()


func _process(_dt: float) -> void:
	if Engine.get_process_frames() % 30 == 0:
		_tick()


func _tick() -> void:
	if not d.get("traveling", false) or not is_instance_valid(_travel_lbl):
		return
	var left := Time.get_unix_time_from_datetime_string(String(d.arrive_at).substr(0, 19)) - Time.get_unix_time_from_system()
	if left <= 0:
		_travel_lbl.text = "Караван прибывает…"
		d["traveling"] = false
		_load()
		return
	_travel_lbl.text = "Прибытие через %d ч %02d мин" % [int(left / 3600), int(fmod(left, 3600) / 60)]


# ------------------------------------------------------------------ modules
func _council_name(code: String) -> String:
	for c in d.get("council", []):
		if String(c.code) == code:
			return String(c.name)
	return ""


func _overseer(module_code: String) -> String:
	for c in d.get("council", []):
		if module_code in c.modules:
			return String(c.name)
	return ""


func _modules() -> void:
	_body.add_child(UI.label("Модули дают постоянные бонусы. Каждым руководит член совета — улучшения укрепляют его голос.", UI.FS.caption, UI.MUTED))
	for b in d.modules:
		var card := UI.card()
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", UI.SP.m)
		var mod_art := UI.art("caravan/modules/%s.png" % String(b.code))  # admin-panel art (section «Караван»)
		if mod_art:
			var tr := TextureRect.new()
			tr.texture = mod_art
			tr.custom_minimum_size = Vector2(96, 96)
			tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			tr.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			h.add_child(tr)
		else:
			var ic := GameIcon.new()
			ic.kind = String(MODULE_ICONS.get(String(b.code), "fortress"))
			ic.custom_minimum_size = Vector2(80, 80)
			ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
			h.add_child(ic)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.add_child(UI.label("%s · ур. %d/%d" % [b.name, int(b.level), int(b.max_level)], UI.FS.body_l, UI.GOLD, true))
		info.add_child(UI.label(String(b.effect), UI.FS.caption, UI.TEXT))
		var ov := _overseer(String(b.code))
		if ov != "":
			info.add_child(UI.label("Руководит: " + ov, UI.FS.caption, UI.MUTED))
		if b.upgrade_cost:
			info.add_child(UI.rewards_row(b.upgrade_cost, 24))
		h.add_child(info)
		if b.upgrade_cost and not b.locked:
			var up := UI.button("Улучшить", "primary", 200, 88)
			var code: String = b.code
			up.pressed.connect(func(): _upgrade(code, up))
			h.add_child(up)
		elif not b.upgrade_cost:
			h.add_child(UI.label("Макс.", UI.FS.body, UI.ok_color(), true))
		card.add_child(h)
		_body.add_child(card)


func _upgrade(code: String, b: Button) -> void:
	UI.set_loading(b, true)
	var r := await Api.post_json("/fortress/buildings/%s/upgrade" % code, {}, true)
	if not is_inside_tree():
		return
	UI.set_loading(b, false)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("door")
	Game.set_wallet(r.data.wallet)
	Router.toast("Модуль улучшен")
	Game.refresh_heroes()
	Game.refresh_afk()
	_load()


# ------------------------------------------------------------------ council
func _council() -> void:
	_body.add_child(UI.label("У каравана нет одного капитана. Решения в пути и улучшения модулей меняют, к кому прислушиваются люди. Ближайший советник даёт каравану свой бонус.", UI.FS.caption, UI.MUTED))
	for c in d.council:
		var card := UI.card(UI.GOLD if c.mood == "lead" else (UI.bad_color() if c.mood == "doubt" else Color(0, 0, 0, 0)))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", UI.SP.m)
		var face := TextureRect.new()
		face.custom_minimum_size = Vector2(110, 110)
		face.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		face.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		var mat := ShaderMaterial.new()
		mat.shader = preload("res://src/ui/circle.gdshader")
		face.material = mat
		h.add_child(face)
		_face(face, c)
		var v := VBoxContainer.new()
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		v.add_theme_constant_override("separation", UI.SP.xs)
		var top := HBoxContainer.new()
		var nm := UI.label("%s — %s" % [c.name, c.area], UI.FS.body, UI.GOLD, true)
		nm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		top.add_child(nm)
		top.add_child(UI.label(String(c.mood_text), UI.FS.caption,
			UI.GOLD if c.mood == "lead" else (UI.ok_color() if c.mood == "support" else (UI.bad_color() if c.mood == "doubt" else UI.MUTED)), true))
		v.add_child(top)
		var line := UI.label("«%s»" % c.line, UI.FS.caption, UI.TEXT)
		line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(line)
		v.add_child(UI.label("Если станет ближайшим советником: " + String(c.lead_text), 22, UI.MUTED))
		h.add_child(v)
		card.add_child(h)
		_body.add_child(card)


func _face(tex: TextureRect, c: Dictionary) -> void:
	var art := UI.art("ui/story/%s.png" % String(c.code))  # admin-panel portrait (Ильсур, Гаухар-апа…)
	if art:
		tex.texture = art
		return
	if c.hero != null and String(c.hero) != "":
		var t := await Models.portrait(String(c.hero))
		if is_instance_valid(tex):
			tex.texture = t
		return
	# no collectible hero and no uploaded portrait yet: a neutral emblem instead of an empty circle
	tex.material = null
	var ic := GameIcon.new()
	ic.kind = "profile"
	ic.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ic.offset_left = 14
	ic.offset_right = -14
	ic.offset_top = 14
	ic.offset_bottom = -14
	tex.add_child(ic)


# ------------------------------------------------------------------ route
func _route() -> void:
	if Game.campaign.get("regions", []).is_empty():
		await Game.refresh_campaign()
		if not is_inside_tree() or tab != "route":
			return
	var map := WorldMap.new()
	map.route_mode = true
	map.roads = d.all_roads
	map.caravan_at = String(d.location)
	map.caravan_to = String(d.destination) if d.traveling else ""
	var reach := {}
	for r in d.roads:
		reach[String(r.to)] = bool(r.open)
	map.reachable = reach
	map.set_regions(Game.campaign.get("regions", []))
	map.region_pressed.connect(func(i: int): _pick(String(Game.campaign.regions[i].get("code", ""))))
	_body.add_child(map)
	if d.traveling:
		_body.add_child(UI.label("Караван в пути. Новое направление можно выбрать после прибытия.", UI.FS.caption, UI.MUTED))
		return
	_body.add_child(UI.section("Дороги со стоянки «%s»" % d.location_name))
	for r in d.roads:
		var card := UI.card(UI.GOLD_DARK if r.open else Color(0, 0, 0, 0))
		var h := HBoxContainer.new()
		var v := VBoxContainer.new()
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		v.add_child(UI.label(String(r.name), UI.FS.body_l, UI.TEXT if r.open else UI.MUTED, true))
		v.add_child(UI.label(("В пути: %s ч · припасы: %s" % [String.num(float(r.hours), 1), r.bonus]) if r.open else String(r.reason), UI.FS.caption, UI.MUTED))
		h.add_child(v)
		if r.open:
			var to: String = r.to
			var b := UI.button("В путь", "primary", 180, 80)
			b.pressed.connect(func(): _pick(to))
			h.add_child(b)
		else:
			var ic := GameIcon.new()
			ic.kind = "lock"
			ic.custom_minimum_size = Vector2(56, 56)
			h.add_child(ic)
		card.add_child(h)
		_body.add_child(card)


func _pick(code: String) -> void:
	if d.traveling:
		Router.toast("Караван уже в пути")
		return
	var road = null
	for r in d.roads:
		if String(r.to) == code:
			road = r
	if code == String(d.location):
		Router.toast("Караван уже стоит здесь")
		return
	if road == null:
		Router.toast("Отсюда туда нет прямой дороги — выберите соседнюю землю")
		return
	if not road.open:
		Router.toast(String(road.reason))
		return
	UI.confirm(main.ui, "В путь: %s" % road.name,
		"Дорога займёт %s ч. Пока караван в пути, местных припасов нет. По прибытии: %s.\nДозор и бои продолжаются как обычно." % [
			String.num(float(road.hours), 1), road.bonus], "В путь", func(): _travel(code))


func _travel(code: String) -> void:
	var r := await Api.post_json("/caravan/travel", {"to": code}, true)
	if not is_inside_tree():
		return
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("door")
	Router.toast("Караван отправился в путь")
	d = r.data
	Game.refresh_afk()
	_render()
