extends Control
## Global search (brief §22): one field over the whole game — heroes (owned and catalogue), game sections, players
## (/social/search) and guilds (/guilds/list). Relevance by default (prefix matches first). No search history,
## favourites or saved filters are kept. Equipment/artifacts/items appear here once those systems exist on the server.

var main: Node
var _q: LineEdit
var _list: VBoxContainer
var _gen := 0

const SECTIONS := [["home", "Главная", "home"], ["heroes", "Герои", "heroes"], ["formation", "Формация отряда", "heroes"],
	["campaign", "Поход", "campaign"], ["guild", "Гильдия", "guild"], ["world", "Мир", "world"], ["more", "Ещё", "more"],
	["summon", "Призыв", "summon"], ["shop", "Магазин", "shop"], ["quests", "Задания и достижения", "quests"],
	["events", "Центр событий", "events"], ["mail", "Почта", "mail"], ["friends", "Друзья", "friends"], ["chat", "Чат", "chat"],
	["rankings", "Рейтинг", "ranks"], ["arena", "Арена", "arena"], ["raids", "Рейды и боссы", "shulgan"],
	["tournaments", "Турниры", "crown"], ["fortress", "Крепость", "fortress"], ["inventory", "Инвентарь", "afk"],
	["profile", "Профиль", "profile"], ["settings", "Настройки", "settings"]]


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.gui_input.connect(func(e: InputEvent):
		if e is InputEventMouseButton and e.pressed:
			queue_free())
	add_child(dim)
	var p := UI.solid_panel()
	p.set_anchors_preset(Control.PRESET_TOP_WIDE)
	p.offset_left = 16
	p.offset_right = -16
	p.offset_top = 210
	p.offset_bottom = 1500
	add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	p.add_child(v)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	_q = LineEdit.new()
	_q.placeholder_text = "Поиск: герой, раздел, игрок, гильдия"
	_q.custom_minimum_size = Vector2(0, 88)
	_q.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_q.add_theme_font_size_override("font_size", 30)
	_q.clear_button_enabled = true
	_q.text_changed.connect(func(_t: String): _search())
	h.add_child(_q)
	var x := UI.button("✕", "glass", 88, 88)
	x.pressed.connect(queue_free)
	h.add_child(x)
	v.add_child(h)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 8)
	v.add_child(UI.scroll(_list))
	UI.keep_wrapped(_list)
	_list.add_child(UI.label("Введите хотя бы 2 буквы. История поиска не сохраняется.", 24, UI.MUTED))
	UI.pop_in(p)
	_q.grab_focus.call_deferred()


func _score(name: String, q: String) -> int:
	var n := name.to_lower()
	if n == q:
		return 3
	if n.begins_with(q):
		return 2
	for w in n.split(" "):
		if w.begins_with(q):
			return 2
	return 1 if n.contains(q) else 0


func _search() -> void:
	_gen += 1
	var gen := _gen
	var q := _q.text.strip_edges().to_lower()
	for c in _list.get_children():
		c.queue_free()
	if q.length() < 2:
		_list.add_child(UI.label("Введите хотя бы 2 буквы. История поиска не сохраняется.", 24, UI.MUTED))
		return
	# local: sections and heroes (instant)
	var secs := []
	for s in SECTIONS:
		var sc := _score(String(s[1]), q)
		if sc > 0:
			secs.append([sc, s])
	secs.sort_custom(func(a, b): return a[0] > b[0])
	if secs.size() > 0:
		_list.add_child(UI.section("Разделы"))
		for it in secs.slice(0, 6):
			var s: Array = it[1]
			var key: String = s[0]
			_list.add_child(_row(String(s[2]), String(s[1]), "", func(): queue_free(); main.open(key)))
	var owned := {}
	for hh in Game.heroes:
		owned[String(hh.hero_code)] = hh
	var heroes := []
	for ch in Game.catalog.get("heroes", []):
		if ch.is_enemy:
			continue
		var sc := _score(String(ch.name), q)
		if sc > 0:
			heroes.append([sc + (1 if owned.has(String(ch.code)) else 0), ch])
	heroes.sort_custom(func(a, b): return a[0] > b[0])
	if heroes.size() > 0:
		_list.add_child(UI.section("Герои"))
		for it in heroes.slice(0, 8):
			var ch: Dictionary = it[1]
			var own: Dictionary = owned.get(String(ch.code), {})
			var sub := ("Уровень %d · ⚔ %s" % [int(own.level), Game.fmt(int(own.power))]) if not own.is_empty() else "Нет в коллекции · можно получить призывом"
			var hid: String = String(own.get("id", ""))
			_list.add_child(_row(String(ch.faction), String(ch.name), sub, func():
				queue_free()
				main.open("heroes", {"open": hid} if hid != "" else {})))
	# server: players and guilds (debounced by generation)
	await get_tree().create_timer(0.35).timeout
	if gen != _gen or not is_inside_tree():
		return
	var pr := await Api.get_json("/social/search?q=" + q.uri_encode())
	if gen != _gen or not is_inside_tree():
		return
	if pr.ok and pr.data.items.size() > 0:
		_list.add_child(UI.section("Игроки"))
		for pl in pr.data.items.slice(0, 8):
			var uid: String = pl.user_id
			var r := _row("profile", String(pl.nickname), "Уровень %d" % int(pl.get("level", 1)), func():
				preload("res://src/ui/PlayerPopup.gd").open(main.ui, uid, main))
			if pl.get("is_ai", false):
				r.get_child(0).get_child(1).get_child(0).add_child(UI.ai_badge())
			_list.add_child(r)
	var gr := await Api.get_json("/guilds/list?q=" + q.uri_encode())
	if gen != _gen or not is_inside_tree():
		return
	if gr.ok and gr.data.items.size() > 0:
		_list.add_child(UI.section("Гильдии"))
		for g in gr.data.items.slice(0, 6):
			var gr_row := _row("guild", "[%s] %s" % [g.tag, g.name], "Ур. %d · %d/%d участников" % [int(g.level), int(g.members), int(g.max_members)],
				func(): queue_free(); main.open("guild"))
			if g.get("is_ai", false):
				gr_row.get_child(0).get_child(1).get_child(0).add_child(UI.ai_badge())
			_list.add_child(gr_row)
	if _list.get_child_count() == 0 or (not pr.ok and not gr.ok and secs.is_empty() and heroes.is_empty()):
		_list.add_child(UI.state("empty", "Ничего не найдено по запросу «%s»." % q))


func _row(icon: String, title: String, sub: String, cb: Callable) -> Button:
	var b := Button.new()
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(0, 96)
	var sb := UI._flat(Color(UI.SURFACE, 0.95), Color(UI.LINE, 0.9), UI.R.m, 1)
	b.add_theme_stylebox_override("normal", sb)
	b.add_theme_stylebox_override("hover", sb)
	b.add_theme_stylebox_override("pressed", sb)
	var h := HBoxContainer.new()
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.offset_left = 12
	h.add_theme_constant_override("separation", 12)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ic := GameIcon.new()
	ic.kind = icon
	ic.custom_minimum_size = Vector2(60, 60)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(ic)
	var v := VBoxContainer.new()
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var th := HBoxContainer.new()
	th.add_theme_constant_override("separation", 8)
	th.mouse_filter = Control.MOUSE_FILTER_IGNORE
	th.add_child(UI.label(title, 28, UI.TEXT, true))
	var inner := HBoxContainer.new()  # slot for badges (AI)
	inner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	th.add_child(inner)
	v.add_child(th)
	if sub != "":
		v.add_child(UI.label(sub, 22, UI.MUTED))
	h.add_child(v)
	b.add_child(h)
	b.pressed.connect(cb)
	return b
