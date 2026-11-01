extends "res://src/screens/TabScreen.gd"
## Guild screen (dark-fantasy layout): left section rail, header with the guild banner, level and stats,
## management form with inner tabs (Управление / Ранги / Права / Журнал) and the rest of the guild systems.

const ROLES := ["leader", "deputy", "officer", "veteran", "member", "novice"]
const LOG_NAMES := {"create": "создал гильдию", "join": "вступил", "leave": "покинул гильдию", "kick": "исключил",
	"role": "изменил должность", "transfer": "передал руководство", "invite": "пригласил", "apply": "подал заявку",
	"decline": "отклонил заявку", "edit": "изменил настройки", "building": "улучшил постройку",
	"research": "провёл исследование", "specialize": "выбрал путь", "expedition": "отправил экспедицию",
	"expedition_done": "экспедиция вернулась", "war_start": "объявил войну", "war_declared": "гильдии объявлена война",
	"war_end": "война завершена", "warn": "предупредил", "auto_warn": "автопредупреждение за неактивность",
	"ai_policy": "изменил правила ИИ"}
## Guild Center: Обзор · Участники · Босс · Магазин · Задания · Рейтинг · Война, then development and management.
const SECTIONS := [["overview", "fortress", "Обзор"], ["members", "friends", "Участники"], ["boss", "shulgan", "Босс"],
	["shop", "shop", "Магазин"], ["events", "quests", "Задания"], ["rating", "ranks", "Рейтинг"], ["wars", "arena", "Война"],
	["tech", "settings", "Технологии"], ["treasury", "afk", "Казна"], ["apps", "friends", "Заявки"],
	["manage", "crown", "Управление"], ["settings", "settings", "Настройки"]]
const NO_GUILD := [["find", "guild", "Найти"], ["create", "crown", "Создать"]]
const SUBTABS := [["form", "Управление"], ["ranks", "Ранги"], ["rights", "Права"], ["log", "Журнал"]]
const OrnateFrame := preload("res://src/ui/OrnateFrame.gd")
const GuildBanner := preload("res://src/ui/GuildBanner.gd")
const GOLD_C := Color("#e6b452")
const TEAL := Color("#3fd6c8")

var g := {}
var sub := "form"
var _rail: VBoxContainer
var _right: VBoxContainer
var _header: Control
var _subrow: HBoxContainer
var _plaque_label: Label
var _form := {}


func _init() -> void:
	title_text = "Гильдия"
	tab = "overview"


func setup(m: Node, p: Dictionary) -> void:
	main = m
	main.use_world("none")
	tab = String(p.get("tab", tab))
	if tab == "activities":
		tab = "events"
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.offset_left = 8
	root.offset_right = -8
	root.offset_top = 4
	root.offset_bottom = -6
	add_child(root)
	var bg: Control = OrnateFrame.new()
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bg.crest = true
	root.add_child(bg)
	var h := HBoxContainer.new()
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.offset_left = 14
	h.offset_right = -16
	h.offset_top = 16
	h.offset_bottom = -16
	h.add_theme_constant_override("separation", 12)
	root.add_child(h)
	var rail_scroll := ScrollContainer.new()
	rail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	rail_scroll.custom_minimum_size = Vector2(176, 0)
	_rail = VBoxContainer.new()
	_rail.add_theme_constant_override("separation", 8)
	_rail.custom_minimum_size = Vector2(168, 0)
	rail_scroll.add_child(_rail)
	h.add_child(rail_scroll)
	_right = VBoxContainer.new()
	_right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_right.add_theme_constant_override("separation", 10)
	h.add_child(_right)
	_right.add_child(_plaque())
	_header = VBoxContainer.new()
	_right.add_child(_header)
	_subrow = HBoxContainer.new()
	_subrow.add_theme_constant_override("separation", 6)
	_right.add_child(_subrow)
	var body_bg := PanelContainer.new()
	var sb := UI._flat(Color(0.02, 0.07, 0.08, 0.8), Color(GOLD_C, 0.55), 14, 2)
	sb.content_margin_left = 14
	sb.content_margin_right = 14
	sb.content_margin_top = 12
	sb.content_margin_bottom = 12
	body_bg.add_theme_stylebox_override("panel", sb)
	body_bg.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 12)
	body_bg.add_child(UI.scroll(_body))
	UI.keep_wrapped(_body)
	_right.add_child(body_bg)
	render()


func _plaque() -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(0, 92)
	var f: Control = OrnateFrame.new()
	f.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	f.offset_left = 40
	f.offset_right = -40
	f.radius = 10
	f.fill = Color(0.03, 0.12, 0.13, 0.98)
	c.add_child(f)
	_plaque_label = UI.title("Гильдия", 46)
	_plaque_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_plaque_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_plaque_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	c.add_child(_plaque_label)
	return c


func render() -> void:
	var d := await get_data("/guilds/mine")
	if not is_inside_tree():
		return
	g = d
	_gen += 1
	var in_guild: bool = d.get("guild") != null
	var secs: Array = SECTIONS if in_guild else NO_GUILD
	if not secs.any(func(x): return x[0] == tab):
		tab = secs[0][0]
	_plaque_label.text = {"manage": "Управление гильдией", "members": "Участники", "apps": "Заявки", "ranks": "Ранги",
		"tech": "Технологии", "events": "Задания гильдии", "wars": "Войны гильдий", "boss": "Босс гильдии",
		"shop": "Магазин гильдии", "rating": "Рейтинг гильдий", "treasury": "Казна",
		"settings": "Настройки", "find": "Найти гильдию", "create": "Создать гильдию"}.get(tab, "Гильдия")
	_render_rail(secs)
	_render_header(in_guild)
	_render_subtabs()
	for c in _body.get_children():
		c.queue_free()
	_render_tab(tab)


func _render_rail(secs: Array) -> void:
	for c in _rail.get_children():
		c.queue_free()
	for s in secs:
		var key: String = s[0]
		var active := key == tab
		var b := Button.new()
		b.custom_minimum_size = Vector2(164, 124)
		b.focus_mode = Control.FOCUS_NONE
		var sb := UI._flat(Color("#4a3210") if active else Color(0.03, 0.1, 0.12, 0.95), GOLD_C if active else Color(GOLD_C, 0.45), 14, 3 if active else 2)
		if active:
			sb.shadow_color = Color(1.0, 0.75, 0.3, 0.4)
			sb.shadow_size = 12
		for st in ["normal", "hover", "pressed"]:
			b.add_theme_stylebox_override(st, sb)
		var v := VBoxContainer.new()
		v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		v.alignment = BoxContainer.ALIGNMENT_CENTER
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ic := GameIcon.new()
		ic.kind = s[1]
		ic.custom_minimum_size = Vector2(58, 58)
		ic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(ic)
		var l := UI.label(String(s[2]), 25, Color("#fff1c9") if active else Color("#e8efe9"), true)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(l)
		b.add_child(v)
		if key == "apps" and g.get("applications", []).size() > 0:
			var dot := Panel.new()
			dot.add_theme_stylebox_override("panel", UI._flat(Color("#e53b2f"), Color.WHITE, 14, 2))
			dot.size = Vector2(26, 26)
			dot.position = Vector2(130, 8)
			dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
			b.add_child(dot)
		b.pressed.connect(func(): Sfx.play("click"); tab = key; sub = "form"; render())
		_rail.add_child(b)


func _render_header(in_guild: bool) -> void:
	for c in _header.get_children():
		c.queue_free()
	if not in_guild or tab in ["settings"]:
		return
	var gd: Dictionary = g.guild
	var card_c := PanelContainer.new()
	var sb := UI._flat(Color(0.04, 0.12, 0.13, 0.96), Color(GOLD_C, 0.7), 14, 2)
	sb.content_margin_left = 12
	sb.content_margin_right = 16
	sb.content_margin_top = 10
	sb.content_margin_bottom = 10
	card_c.add_theme_stylebox_override("panel", sb)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 16)
	var banner: Control = GuildBanner.new()
	banner.emblem = String(gd.get("emblem", "wolf"))
	banner.custom_minimum_size = Vector2(150, 230)
	h.add_child(banner)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", 6)
	var nr := HBoxContainer.new()
	var nm := UI.title(String(gd.name), 44)
	nm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nm.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	nr.add_child(nm)
	if perm("edit"):
		var ed := UI.button("✎ Изменить", "glass", 0, 70)
		ed.add_theme_font_size_override("font_size", 24)
		ed.pressed.connect(func(): tab = "manage"; sub = "form"; render())
		nr.add_child(ed)
	v.add_child(nr)
	v.add_child(UI.label("ID: %s · [%s]%s" % [gd.get("public_id", ""), gd.tag, "  · ИИ-гильдия" if gd.is_ai else ""], 24, Color("#9fb7b4")))
	var lv := HBoxContainer.new()
	lv.add_theme_constant_override("separation", 12)
	lv.add_child(UI.label("Ур. %d" % int(gd.level), 36, GOLD_C, true))
	var bar_box := Control.new()
	bar_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar_box.custom_minimum_size = Vector2(0, 34)
	var nxt = gd.exp_next
	var bar := UI.bar(int(gd.exp), int(nxt) if nxt != null else max(1, int(gd.exp)), TEAL, 34)
	bar.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bar_box.add_child(bar)
	var bl := UI.label("%s / %s" % [Game.fmt(int(gd.exp)), Game.fmt(int(nxt)) if nxt != null else "макс."], 22, Color.WHITE, true)
	bl.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	bar_box.add_child(bl)
	lv.add_child(bar_box)
	v.add_child(lv)
	var chips := HBoxContainer.new()
	chips.add_theme_constant_override("separation", 8)
	for ch in [["friends", "%d/%d" % [int(gd.members), int(gd.max_members)]], ["arena", Game.fmt(int(gd.get("power", 0)))],
			["ranks", "Топ %d" % int(gd.get("rank", 0))]]:
		var pc := PanelContainer.new()
		var csb := UI._flat(Color(0.02, 0.06, 0.07, 0.95), Color(GOLD_C, 0.7), 18, 2)
		csb.content_margin_left = 12
		csb.content_margin_right = 14
		pc.add_theme_stylebox_override("panel", csb)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 6)
		var ic := GameIcon.new()
		ic.kind = ch[0]
		ic.custom_minimum_size = Vector2(36, 36)
		row.add_child(ic)
		row.add_child(UI.label(String(ch[1]), 26, Color.WHITE, true))
		pc.add_child(row)
		chips.add_child(pc)
	v.add_child(chips)
	h.add_child(v)
	card_c.add_child(h)
	_header.add_child(card_c)


func _render_subtabs() -> void:
	for c in _subrow.get_children():
		c.queue_free()
	_subrow.visible = tab == "manage"
	if tab != "manage":
		return
	for t in SUBTABS:
		var key: String = t[0]
		var b := UI.button(String(t[1]), "primary" if key == sub else "glass", 0, 80)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.add_theme_font_size_override("font_size", 27)
		b.pressed.connect(func(): sub = key; render())
		_subrow.add_child(b)


func perm(p: String) -> bool:
	return p in g.get("permissions", [])


func _render_tab(t: String) -> void:
	match t:
		"find": _find()
		"create": _create()
		"overview": _overview()
		"members": _members(false)
		"manage":
			match sub:
				"form": _settings_form()
				"ranks": _ranks()
				"rights": _rights()
				"log": _log()
		"apps": _apps()
		"boss": _boss()
		"shop": _shop()
		"rating": _rating()
		"ranks": _ranks()
		"tech": _fortress()
		"events": _activities(true, false)
		"wars": _activities(false, true)
		"treasury": _treasury()
		"settings": _guild_settings()


# ------------------------------------------------------------------ boss / shop / rating
func _boss() -> void:
	var gen := _gen
	var d := await get_data("/raids")
	if not alive(gen) or d.is_empty():
		return
	var r = null
	for x in d.raids:
		if String(x.kind) == "guild":
			r = x
	if r == null or r.has("locked"):
		add(UI.state("locked", String(r.locked) if r else "Босс гильдии недоступен."))
		return
	var c := card(GOLD_C)
	line_to(c.info, "%s · ур. %d · этап %d/%d" % [r.name, int(r.level), int(r.stage), int(r.stages)], 30, UI.GOLD, true)
	line_to(c.info, String(r.desc), 24, UI.MUTED)
	c.info.add_child(UI.progress(int(r.hp_left), int(r.hp_max), "Здоровье %s / %s" % [Game.fmt(int(r.hp_left)), Game.fmt(int(r.hp_max))], UI.bad_color(), 26))
	line_to(c.info, "Фаза: %s — %s" % [r.phase_name, r.phase_note], 24, UI.TEXT)
	line_to(c.info, "Ваш урон: %s · участников: %d · попытки %d/%d · до конца: %s" % [Game.exact(int(r.my_damage)),
		int(r.participants), int(r.attempts), int(r.max_attempts), countdown(String(r.ends_at))], 24, UI.MUTED)
	var go := btn(c.info, "К бою с боссом", "primary", func(): main.open("raids", {"tab": "bosses"}))
	go.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	h1("Лучший урон")
	if r.top.is_empty():
		txt("Пока никто не атаковал — станьте первым.", 26, UI.MUTED)
	var i := 0
	for t in r.top:
		i += 1
		var row := card()
		var nm := "%d. %s" % [i, t.nickname]
		line_to(row.info, nm, 27, UI.GOLD if i <= 3 else UI.TEXT, true)
		if t.is_ai:
			row.row.add_child(UI.ai_badge())
		row.row.add_child(UI.label(Game.exact(int(t.damage)), 27, UI.TEXT, true))


func _shop() -> void:
	var gen := _gen
	var d := await get_data("/guilds/shop")
	if not alive(gen) or d.is_empty():
		return
	var head := card(GOLD_C)
	line_to(head.info, "Гильдейские знаки: %s" % Game.exact(int(d.marks)), 30, UI.GOLD, true)
	line_to(head.info, String(d.note), 24, UI.MUTED)
	for it in d.items:
		var c := card()
		line_to(c.info, String(it.name), 28, UI.TEXT, true)
		c.info.add_child(UI.rewards_row(it.reward, 26))
		var left: int = int(it.weekly_limit) - int(it.bought)
		line_to(c.info, "Осталось на неделе: %d из %d" % [left, int(it.weekly_limit)], 23, UI.MUTED)
		var code: String = it.code
		var price := "%d знаков" % int(it.cost)
		var b := btn(c.row, price if left > 0 else "Лимит", "primary" if left > 0 and int(d.marks) >= int(it.cost) else "dim",
			func(): if not (await act("/guilds/shop/%s/buy" % code, {}, "Покупка совершена")).is_empty(): render())
		b.disabled = left <= 0 or int(d.marks) < int(it.cost)


func _rating() -> void:
	var gen := _gen
	var d := await get_data("/rankings/guilds")
	if not alive(gen) or d.is_empty():
		return
	if d.get("me"):
		var me := card(GOLD_C)
		line_to(me.info, "Ваша гильдия: %s" % d.me.name, 28, UI.GOLD, true)
		line_to(me.info, "Уровень %d · %s" % [int(d.me.value), d.me.extra], 24, UI.TEXT)
	txt("Рейтинг по уровню и опыту гильдии. Виртуальные ИИ-гильдии отмечены и показаны после реальных.", 23, UI.MUTED)
	var i := 0
	for r in d.items:
		i += 1
		var c := card(GOLD_C if g.guild and r.get("guild_id") == g.guild.id else Color(1, 1, 1, 0.12))
		line_to(c.info, "%d. %s" % [i, r.name], 27, UI.GOLD if i <= 3 else UI.TEXT, true)
		line_to(c.info, "Уровень %d · %s" % [int(r.value), r.extra], 23, UI.MUTED)
		if r.get("is_ai", false):
			c.row.add_child(UI.ai_badge())


# ------------------------------------------------------------------ no guild
func _find() -> void:
	for inv in g.get("invites", []):
		var c := card(UI.GOLD)
		line_to(c.info, "Приглашение: [%s] %s" % [inv.guild.tag, inv.guild.name], 28, UI.GOLD, true)
		var iid: String = inv.id
		btn(c.row, "Принять", "primary", func():
			if not (await act("/guilds/applications/%s/accept" % iid)).is_empty():
				Router.toast("Добро пожаловать в гильдию!")
				render())
		btn(c.row, "✕", "dim", func(): await act("/guilds/applications/%s/decline" % iid); render(), 84)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var q := LineEdit.new()
	q.placeholder_text = "Название или тег"
	q.custom_minimum_size = Vector2(0, 90)
	q.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	q.add_theme_font_size_override("font_size", 30)
	row.add_child(q)
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 10)
	var search := func(): _list_guilds(list, q.text.strip_edges())
	btn(row, "Найти", "primary", search, 180)
	add(row)
	add(list)
	_list_guilds(list, "")


func _list_guilds(list: VBoxContainer, query: String) -> void:
	var d := await get_data("/guilds/list?q=" + query.uri_encode())
	if not is_instance_valid(list):
		return
	for c in list.get_children():
		c.queue_free()
	var mode_names := {"open": "свободный вход", "approval": "по заявке", "invite": "по приглашению"}
	for x in d.get("items", []):
		var pc := PanelContainer.new()
		pc.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.55), Color(1, 1, 1, 0.18), 22, 2))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 10)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.custom_minimum_size.x = 200
		var nr := HBoxContainer.new()
		nr.add_theme_constant_override("separation", 8)
		nr.add_child(UI.label("[%s] %s" % [x.tag, x.name], 29, UI.GOLD, true))
		if x.is_ai:
			nr.add_child(UI.ai_badge())
		info.add_child(nr)
		line_to(info, "Ур. %d · %d/%d участников · %s · с %d ур." % [int(x.level), int(x.members), int(x.max_members),
			mode_names.get(x.join_mode, x.join_mode), int(x.min_level)], 24, UI.MUTED)
		if String(x.description) != "":
			line_to(info, String(x.description), 24, UI.TEXT)
		h.add_child(info)
		var gid: String = x.id
		if x.applied:
			h.add_child(UI.label("Заявка\nотправлена", 22, UI.MUTED))
		elif x.join_mode != "invite":
			btn(h, "Вступить" if x.join_mode == "open" else "Заявка", "primary", func():
				var r := await act("/guilds/%s/join" % gid)
				if not r.is_empty():
					Router.toast("Вы вступили в гильдию!" if r.status == "joined" else "Заявка отправлена")
					render())
		pc.add_child(h)
		list.add_child(pc)
	if d.get("items", []).is_empty():
		list.add_child(UI.label("Гильдии не найдены", 26, UI.MUTED))


func _create() -> void:
	txt("Создание гильдии стоит 50 000 золота, нужен 5 уровень. В гильдии до 20 участников и 6 должностей.", 26, UI.MUTED)
	var fields := {}
	for f in [["name", "Название (3–24 символа)"], ["tag", "Тег (2–5 символов)"], ["description", "Описание"]]:
		var e := LineEdit.new()
		e.placeholder_text = f[1]
		e.custom_minimum_size = Vector2(0, 90)
		e.add_theme_font_size_override("font_size", 30)
		add(e)
		fields[f[0]] = e
	var mode := OptionButton.new()
	for m in [["open", "Свободный вход"], ["approval", "Вступление по заявке"], ["invite", "Только по приглашению"]]:
		mode.add_item(m[1])
		mode.set_item_metadata(mode.item_count - 1, m[0])
	mode.custom_minimum_size = Vector2(0, 86)
	mode.add_theme_font_size_override("font_size", 28)
	add(mode)
	btn(_body, "Создать гильдию", "primary", func():
		var r := await act("/guilds/create", {"name": fields.name.text.strip_edges(), "tag": fields.tag.text.strip_edges(),
			"description": fields.description.text.strip_edges(), "join_mode": mode.get_item_metadata(mode.selected)},
			"Гильдия создана!")
		if not r.is_empty():
			tab = "overview"
			render())


# ------------------------------------------------------------------ overview
func _overview() -> void:
	var gd: Dictionary = g.guild
	var c := card(GOLD_C)
	line_to(c.info, "Ваша должность: %s" % g.my_role_name, 28, GOLD_C, true)
	if String(gd.description) != "":
		line_to(c.info, String(gd.description), 26, UI.TEXT)
	line_to(c.info, "Казна: %s · очки недели: %s · путь: %s" % [Game.fmt(int(gd.treasury)), Game.fmt(int(gd.week_points)),
		g.specializations.get(gd.specialization, {}).get("name", "не выбран") if gd.specialization else "не выбран"], 24, UI.ACCENT)
	h1("Бонусы гильдии")
	var names := {"atk_pct": "атака (PvE)", "hp_pct": "здоровье (PvE)", "boss_dmg_pct": "урон по боссам",
		"war_atk_pct": "урон в войнах", "war_def_pct": "оборона в войнах", "expedition_pct": "награды экспедиций",
		"afk_gold_pct": "золото AFK"}
	var parts: Array = []
	for k in g.bonuses:
		parts.append("+%d%% %s" % [int(round(float(g.bonuses[k]) * 100)), names.get(k, k)])
	txt(", ".join(parts) if parts.size() > 0 else "Пока нет: улучшайте постройки и исследования.", 26)
	h1("Лучшие за неделю")
	var top: Array = g.members.duplicate()
	top.sort_custom(func(x, y): return int(x.week) > int(y.week))
	for m in top.slice(0, 5):
		txt("%s%s — %d очков" % [m.nickname, " (ИИ)" if m.is_ai else "", int(m.week)], 25)
	var wr: Dictionary = g.week_rewards
	h1("Недельная награда")
	txt("Каждый активный участник (от %d очков) получает базовую награду %s плюс личный бонус: 1 метка за очко, максимум %d." % [
		int(wr.min_points_active), Game.rewards_text(wr.base), int(wr.max_bonus_marks)], 24, UI.MUTED)


# ------------------------------------------------------------------ management form
func _settings_form() -> void:
	var gd: Dictionary = g.guild
	var st: Dictionary = gd.get("settings", {})
	var can_edit := perm("edit")
	_form = {"name": String(gd.name), "description": String(gd.description), "emblem": String(gd.emblem),
		"join_mode": String(gd.join_mode), "min_level": int(gd.min_level), "min_power": int(st.get("min_power", 0)),
		"auto_accept": bool(st.get("auto_accept", false)), "notify_chat": bool(st.get("notify_chat", true))}
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 10)
	var gi := GameIcon.new()
	gi.kind = "settings"
	gi.custom_minimum_size = Vector2(48, 48)
	head.add_child(gi)
	head.add_child(UI.label("Основные настройки", 34, GOLD_C, true))
	add(head)
	if not can_edit:
		txt("Изменять настройки могут глава и заместитель.", 24, UI.MUTED)
	var name_e := _field_row("Название гильдии", String(gd.name), can_edit and g.my_role == "leader")
	name_e.text_changed.connect(func(t: String): _form.name = t)
	var desc_e := _field_row("Описание гильдии", String(gd.description), can_edit)
	desc_e.text_changed.connect(func(t: String): _form.description = t)
	# banner picker
	var emblems: Array = gd.get("emblems", ["wolf", "bear", "eagle", "tree", "horse", "stone"])
	var br := _row_label("Флаг (знамя)")
	var banner: Control = GuildBanner.new()
	banner.emblem = _form.emblem
	banner.custom_minimum_size = Vector2(96, 140)
	var prev := UI.button("◀", "glass", 70, 90)
	var nxt := UI.button("▶", "glass", 70, 90)
	var shift := func(d: int):
		var i: int = emblems.find(_form.emblem)
		_form.emblem = emblems[(i + d + emblems.size()) % emblems.size()]
		banner.emblem = _form.emblem
	prev.pressed.connect(func(): shift.call(-1))
	nxt.pressed.connect(func(): shift.call(1))
	prev.disabled = not can_edit
	nxt.disabled = not can_edit
	br.add_child(prev)
	br.add_child(banner)
	br.add_child(nxt)
	# join mode segmented control
	var jr := _row_label("Тип вступления")
	var seg := HBoxContainer.new()
	seg.add_theme_constant_override("separation", 0)
	seg.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var seg_buttons := {}
	for m in [["open", "Открытая"], ["approval", "По заявке"], ["invite", "Закрытая"]]:
		var key: String = m[0]
		var b := UI.button(String(m[1]), "primary" if _form.join_mode == key else "glass", 0, 76)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.add_theme_font_size_override("font_size", 25)
		b.disabled = not can_edit
		seg_buttons[key] = b
		b.pressed.connect(func():
			_form.join_mode = key
			for k in seg_buttons:
				var on: bool = k == key
				var nb := UI.button("", "primary" if on else "glass")
				for stn in ["normal", "hover", "pressed"]:
					seg_buttons[k].add_theme_stylebox_override(stn, nb.get_theme_stylebox(stn))
				seg_buttons[k].add_theme_color_override("font_color", nb.get_theme_color("font_color"))
				nb.free())
		seg.add_child(b)
	jr.add_child(seg)
	_stepper("Мин. уровень", "min_level", 1, 80, 1, can_edit)
	_stepper("Требуемая сила", "min_power", 0, 10000000, 50000, can_edit)
	_toggle("Автопринятие заявок (если условия выполнены)", "auto_accept", can_edit)
	_toggle("Уведомления в чат о вступлениях и выходах", "notify_chat", can_edit)
	if can_edit:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 12)
		var save := UI.button("✔ Сохранить изменения", "primary", 0, 100)
		save.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		save.pressed.connect(_save_form)
		row.add_child(save)
		var reset := UI.button("↺ Сбросить", "glass", 260, 100)
		reset.pressed.connect(func(): render())
		row.add_child(reset)
		add(row)


func _row_label(text: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var l := UI.label(text, 26, UI.TEXT)
	l.custom_minimum_size = Vector2(220, 0)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	row.add_child(l)
	add(row)
	add(_divider())
	return row


func _divider() -> Control:
	var d := ColorRect.new()
	d.color = Color(GOLD_C, 0.18)
	d.custom_minimum_size = Vector2(0, 1)
	return d


func _field_row(label: String, value: String, editable: bool) -> LineEdit:
	var row := _row_label(label)
	var e := LineEdit.new()
	e.text = value
	e.editable = editable
	e.custom_minimum_size = Vector2(0, 80)
	e.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	e.add_theme_font_size_override("font_size", 27)
	e.right_icon = null
	row.add_child(e)
	if editable:
		row.add_child(UI.label("✎", 30, GOLD_C, true))
	return e


func _stepper(label: String, key: String, lo: int, hi: int, step: int, editable: bool) -> void:
	var row := _row_label(label)
	var val := UI.label(Game.fmt(int(_form[key])), 30, Color.WHITE, true)
	val.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	val.custom_minimum_size = Vector2(170, 0)
	var minus := UI.button("−", "glass", 76, 76)
	var plus := UI.button("+", "glass", 76, 76)
	minus.disabled = not editable
	plus.disabled = not editable
	minus.pressed.connect(func(): _form[key] = clampi(int(_form[key]) - step, lo, hi); val.text = Game.fmt(int(_form[key])))
	plus.pressed.connect(func(): _form[key] = clampi(int(_form[key]) + step, lo, hi); val.text = Game.fmt(int(_form[key])))
	row.add_child(minus)
	row.add_child(val)
	row.add_child(plus)


func _toggle(label: String, key: String, editable: bool) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	var l := UI.label(label, 26, UI.TEXT)
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	row.add_child(l)
	row.add_child(switch(bool(_form[key]), editable, func(on: bool): _form[key] = on))
	add(row)
	add(_divider())


## Pill switch (teal when on, graphite when off) with a round knob — like the guild UI mockup.
func switch(on: bool, editable: bool, cb: Callable) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(118, 60)
	b.focus_mode = Control.FOCUS_NONE
	b.disabled = not editable
	b.toggle_mode = true
	b.button_pressed = on
	var knob := Panel.new()
	knob.add_theme_stylebox_override("panel", UI._flat(Color("#f4f1e8"), Color(0, 0, 0, 0.25), 24, 1))
	knob.size = Vector2(48, 48)
	knob.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(knob)
	var paint := func(state: bool):
		var sb := UI._flat(Color("#1f8f86") if state else Color(0.16, 0.19, 0.21), Color(GOLD_C, 0.7) if state else Color(1, 1, 1, 0.25), 30, 2)
		for st in ["normal", "hover", "pressed", "disabled", "hover_pressed"]:
			b.add_theme_stylebox_override(st, sb)
		knob.position = Vector2(64 if state else 6, 6)
	paint.call(on)
	b.toggled.connect(func(state: bool): paint.call(state); cb.call(state))
	return b


func _save_form() -> void:
	var gd: Dictionary = g.guild
	var body := {"description": _form.description.strip_edges(), "emblem": _form.emblem, "join_mode": _form.join_mode,
		"min_level": int(_form.min_level), "min_power": int(_form.min_power), "auto_accept": _form.auto_accept,
		"notify_chat": _form.notify_chat}
	if _form.name.strip_edges() != String(gd.name):
		body["name"] = _form.name.strip_edges()
	if not (await act("/guilds/edit", body, "Настройки гильдии сохранены")).is_empty():
		render()


# ------------------------------------------------------------------ ranks & rights
func _ranks() -> void:
	var by := {}
	for m in g.members:
		if not by.has(String(m.role)):
			by[String(m.role)] = []
		by[String(m.role)].append(m)
	for r in ROLES:
		var lst: Array = by.get(r, [])
		var c := card(GOLD_C if r == "leader" else Color(1, 1, 1, 0.18))
		var hr := HBoxContainer.new()
		var ic := GameIcon.new()
		ic.kind = "crown" if r == "leader" else "ranks"
		ic.custom_minimum_size = Vector2(44, 44)
		hr.add_child(ic)
		hr.add_child(UI.label("%s — %d" % [g.role_names.get(r, r), lst.size()], 29, GOLD_C, true))
		c.info.add_child(hr)
		var names: Array = []
		for m in lst:
			names.append(String(m.nickname) + (" (ИИ)" if m.is_ai else ""))
		line_to(c.info, ", ".join(names) if names.size() > 0 else "—", 24, UI.TEXT)
	txt("Повышение и понижение — в разделе «Участники» (кнопки ▲ ▼ рядом с игроком). Новички становятся участниками автоматически через 3 дня.", 23, UI.MUTED)


func _rights() -> void:
	var perm_names := {"edit": "Настройки гильдии", "accept": "Принимать заявки", "invite": "Приглашать",
		"kick": "Исключать", "promote": "Менять должности", "transfer": "Передать руководство", "build": "Постройки",
		"research": "Исследования", "specialize": "Путь гильдии", "expedition": "Экспедиции", "war": "Объявлять войну",
		"warn": "Предупреждать", "disband": "Распустить гильдию"}
	var table := GridContainer.new()
	table.columns = ROLES.size() + 1
	table.add_theme_constant_override("h_separation", 10)
	table.add_theme_constant_override("v_separation", 8)
	table.add_child(UI.label("Право", 22, GOLD_C, true))
	for r in ROLES:
		var l := UI.label(String(g.role_names.get(r, r)).substr(0, 5), 20, GOLD_C, true)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		table.add_child(l)
	var leader_perms: Array = []
	for r in ["leader"]:
		leader_perms = ["edit", "accept", "invite", "kick", "promote", "transfer", "build", "research", "specialize", "expedition", "war", "warn"]
	for pkey in leader_perms:
		table.add_child(UI.label(String(perm_names.get(pkey, pkey)), 22, UI.TEXT))
		for r in ROLES:
			var has := _role_has(r, pkey)
			var l := UI.label("✔" if has else "—", 24, TEAL if has else Color(1, 1, 1, 0.3), true)
			l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			table.add_child(l)
	add(table)
	txt("Права должностей задаются правилами сервера. Ваши права: " + ", ".join(g.permissions.map(func(x): return perm_names.get(x, x))), 22, UI.MUTED)


func _role_has(role: String, p: String) -> bool:
	var table := {"leader": ["edit", "accept", "invite", "kick", "promote", "transfer", "build", "research", "specialize", "expedition", "war", "warn"],
		"deputy": ["edit", "accept", "invite", "kick", "promote", "build", "research", "expedition", "war", "warn"],
		"officer": ["accept", "invite", "kick", "build", "expedition", "warn"], "veteran": ["invite", "expedition"],
		"member": [], "novice": []}
	return p in table.get(role, [])


# ------------------------------------------------------------------ applications
func _apps() -> void:
	if perm("invite"):
		btn(_body, "Пригласить друга в гильдию", "primary", _invite_dialog)
	if not perm("accept"):
		txt("Заявки рассматривают глава, заместитель и офицеры.", 24, UI.MUTED)
		return
	if g.applications.is_empty():
		txt("Новых заявок нет.", 26, UI.MUTED)
	for a in g.applications:
		var c := card(GOLD_C)
		name_button(c.info, String(a.player.nickname), String(a.player.user_id), bool(a.player.is_ai))
		line_to(c.info, "ур.%d · сила %s · %s" % [int(a.player.level), Game.fmt(int(a.player.power)), UI.local_time(String(a.at))], 24, UI.MUTED)
		var aid: String = a.id
		btn(c.row, "Принять", "primary", func(): if not (await act("/guilds/applications/%s/accept" % aid)).is_empty(): render())
		btn(c.row, "✕", "dim", func(): await act("/guilds/applications/%s/decline" % aid); render(), 84)


# ------------------------------------------------------------------ treasury
func _treasury() -> void:
	var gd: Dictionary = g.guild
	var c := card(GOLD_C)
	line_to(c.info, "В казне: %s" % Game.fmt(int(gd.treasury)), 34, GOLD_C, true)
	line_to(c.info, "Казна оплачивает постройки и исследования. Пополняется пожертвованиями, заданиями и экспедициями.", 23, UI.MUTED)
	var don: Dictionary = g.donate
	h1("Пожертвование")
	txt("%s золота → +%d в казну, +%d очков вклада. Сегодня: %d/%d" % [Game.fmt(int(don.per)), int(don.treasury), int(don.points),
		int(g.donated_today), int(don.daily_max)], 24, UI.MUTED)
	var b := btn(_body, "Пожертвовать %s золота" % Game.fmt(int(don.per)), "primary" if int(g.donated_today) < int(don.daily_max) else "dim",
		func(): if not (await act("/guilds/donate", {}, "Спасибо за вклад!")).is_empty(): render())
	b.disabled = int(g.donated_today) >= int(don.daily_max)
	h1("Вклад участников")
	var top: Array = g.members.duplicate()
	top.sort_custom(func(x, y): return int(x.total) > int(y.total))
	for m in top:
		txt("%s%s — неделя %d · всего %s" % [m.nickname, " (ИИ)" if m.is_ai else "", int(m.week), Game.fmt(int(m.total))], 24)


# ------------------------------------------------------------------ settings
func _guild_settings() -> void:
	if g.has("ai_policy"):
		h1("ИИ-жители в гильдии")
		var pol: Dictionary = g.ai_policy
		for k in pol.names:
			var row := HBoxContainer.new()
			row.add_theme_constant_override("separation", 12)
			var l := UI.label(String(pol.names[k]), 26, UI.TEXT)
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			row.add_child(l)
			var key: String = k
			row.add_child(switch(bool(pol.values.get(k, false)), perm("edit"), func(on: bool): await act("/guilds/ai-policy", {key: on}, "Сохранено")))
			add(row)
			add(_divider())
		if not perm("edit"):
			txt("Меняет глава или заместитель.", 22, UI.MUTED)
	h1("Чат гильдии")
	btn(_body, "Открыть чат гильдии", "glass", func(): main.open("chat", {"channel": "guild:" + String(g.guild.id)}))
	h1("Участие")
	var leave := btn(_body, "Покинуть гильдию", "danger", func():
		if not (await act("/guilds/leave", {}, "Вы покинули гильдию")).is_empty():
			render())
	leave.custom_minimum_size.y = 84
	if g.my_role == "leader" and int(g.guild.members) > 1:
		txt("Главе нужно сначала передать руководство (раздел «Участники»).", 22, UI.MUTED)


# ------------------------------------------------------------------ members
func _members(show_apps := true) -> void:
	var my_rank := ROLES.find(String(g.my_role))
	if show_apps and g.applications.size() > 0:
		h1("Заявки на вступление")
		for a in g.applications:
			var c := card(UI.GOLD)
			name_button(c.info, String(a.player.nickname), String(a.player.user_id), bool(a.player.is_ai))
			line_to(c.info, "ур.%d · сила %s" % [int(a.player.level), Game.fmt(int(a.player.power))], 24, UI.MUTED)
			var aid: String = a.id
			btn(c.row, "Принять", "primary", func(): if not (await act("/guilds/applications/%s/accept" % aid)).is_empty(): render())
			btn(c.row, "✕", "dim", func(): await act("/guilds/applications/%s/decline" % aid); render(), 84)
	if perm("invite"):
		btn(_body, "Пригласить друга", "glass", _invite_dialog)
	h1("Участники (%d)" % g.members.size())
	for m in g.members:
		var c := card(UI.GOLD if m.user_id == Api.user_id else Color(1, 1, 1, 0.18))
		name_button(c.info, String(m.nickname), String(m.user_id), bool(m.is_ai))
		var sub := "%s · ур.%d · вклад за неделю %d (всего %d)" % [m.role_name, int(m.level), int(m.week), int(m.total)]
		if int(m.inactive_days) >= 1:
			sub += " · не заходил %d дн." % int(m.inactive_days)
		line_to(c.info, sub, 24, Color("#ffb3a8") if m.warned else UI.MUTED)
		var r := ROLES.find(String(m.role))
		if m.user_id == Api.user_id or r <= my_rank:
			continue
		var uid: String = m.user_id
		if perm("promote"):
			var actions := HBoxContainer.new()
			actions.add_theme_constant_override("separation", 6)
			if r - 1 > my_rank:
				var up_role: String = ROLES[r - 1]
				btn(actions, "▲", "glass", func(): if not (await act("/guilds/members/%s/role" % uid, {"role": up_role})).is_empty(): render(), 76)
			if r + 1 < ROLES.size():
				var down_role: String = ROLES[r + 1]
				btn(actions, "▼", "glass", func(): if not (await act("/guilds/members/%s/role" % uid, {"role": down_role})).is_empty(): render(), 76)
			c.info.add_child(actions)
		var more := HBoxContainer.new()
		more.add_theme_constant_override("separation", 6)
		if perm("warn"):
			btn(more, "Предупредить", "dim", func(): if not (await act("/guilds/members/%s/warn" % uid, {}, "Предупреждение отправлено")).is_empty(): render())
		if perm("kick"):
			btn(more, "Исключить", "danger", func(): if not (await act("/guilds/members/%s/kick" % uid, {}, "Участник исключён")).is_empty(): render())
		if perm("transfer"):
			btn(more, "Передать главу", "dim", func(): if not (await act("/guilds/transfer", {"user_id": uid}, "Руководство передано")).is_empty(): render())
		c.info.add_child(more)
	txt("Права: глава — всё; заместитель — без передачи руководства; офицер — заявки, приглашения, исключение младших, постройки, экспедиции; ветеран — приглашения и экспедиции.", 22, UI.MUTED)


func _invite_dialog() -> void:
	var fr := await get_data("/social/friends")
	if fr.is_empty():
		return
	h1("Кого пригласить")
	for f in fr.friends:
		if f.get("guild"):
			continue
		var c := card()
		name_button(c.info, String(f.nickname), String(f.user_id), bool(f.is_ai))
		var uid: String = f.user_id
		btn(c.row, "Пригласить", "primary", func():
			var r := await act("/guilds/invite", {"user_id": uid})
			if not r.is_empty():
				Router.toast("Принял приглашение!" if r.status == "accepted" else "Приглашение отправлено")
				render())


# ------------------------------------------------------------------ fortress
func _fortress() -> void:
	txt("Казна: %d. Постройки и исследования оплачиваются из казны (пожертвования, задания, экспедиции)." % int(g.guild.treasury), 26, UI.ACCENT)
	h1("Постройки")
	for b in g.buildings:
		var c := card()
		line_to(c.info, "%s — ур. %d/%d" % [b.name, int(b.level), int(b.max)], 28, UI.GOLD, true)
		line_to(c.info, String(b.effect), 24, UI.MUTED)
		if b.get("requires"):
			var req: Array = []
			for k in b.requires:
				req.append("Зал Совета %d" % int(b.requires[k]) if k == "hall" else "%s %d" % [k, int(b.requires[k])])
			line_to(c.info, "Требуется: " + ", ".join(req), 22, UI.MUTED)
		if b.next_cost != null and perm("build"):
			var code: String = b.code
			btn(c.row, "%d" % int(b.next_cost), "primary" if int(g.guild.treasury) >= int(b.next_cost) else "dim",
				func(): if not (await act("/guilds/build/" + code, {}, "Постройка улучшена")).is_empty(): render())
	h1("Путь гильдии")
	var spec = g.guild.specialization
	for code in g.specializations:
		var s: Dictionary = g.specializations[code]
		var c := card(UI.GOLD if spec == code else Color(1, 1, 1, 0.18))
		line_to(c.info, String(s.name) + ("  ✓" if spec == code else ""), 28, UI.GOLD, true)
		line_to(c.info, String(s.desc), 24, UI.MUTED)
		if spec != code and perm("specialize"):
			var cc: String = code
			btn(c.row, "Выбрать" if spec == null else "Сменить (3000)", "glass",
				func(): if not (await act("/guilds/specialize", {"code": cc}, "Путь выбран")).is_empty(): render())
	h1("Исследования")
	for r in g.research:
		var c := card()
		line_to(c.info, "%s — ур. %d/%d%s" % [r.name, int(r.level), int(r.max), "" if r.active else " (неактивно: другой путь)"], 28,
			UI.GOLD if r.active else UI.MUTED, true)
		line_to(c.info, String(r.effect), 24, UI.MUTED)
		if r.next_cost != null and perm("research") and (r.branch == null or r.branch == spec):
			var code: String = r.code
			btn(c.row, "%d" % int(r.next_cost), "primary" if int(g.guild.treasury) >= int(r.next_cost) else "dim",
				func(): if not (await act("/guilds/research/" + code, {}, "Исследование завершено")).is_empty(): render())


# ------------------------------------------------------------------ activities
func _activities(show_events := true, show_wars := true) -> void:
	if show_events:
		_events_part()
	if show_wars:
		_wars_part()


func _events_part() -> void:
	h1("Задания дня")
	for t in g.tasks:
		var c := card()
		line_to(c.info, String(t.name), 28, UI.TEXT, true)
		line_to(c.info, "%d/%d · %s · +%d очков" % [int(t.progress), int(t.target), Game.rewards_text(t.reward), int(t.points)], 24, UI.MUTED)
		var code: String = t.code
		if t.claimed:
			c.row.add_child(UI.label("✓", 34, UI.GOLD, true))
		else:
			var done: bool = int(t.progress) >= int(t.target)
			var b := btn(c.row, "Забрать" if done else "В пути", "primary" if done else "dim",
				func(): if not (await act("/guilds/tasks/%s/claim" % code, {}, "Награда получена")).is_empty(): render())
			b.disabled = not done
	h1("Экспедиции")
	var active = null
	for e in g.expeditions:
		if e.status == "active":
			active = e
	if active:
		var c := card(UI.GOLD)
		line_to(c.info, "%s — в пути" % active.name, 28, UI.GOLD, true)
		line_to(c.info, "Участников %d · сила %s / цель %s · вернётся через %s" % [int(active.participants), Game.fmt(int(active.power)),
			Game.fmt(int(active.power_goal)), countdown(String(active.ends_at))], 24, UI.TEXT)
		if not Api.user_id in active.joined_ids:
			var eid: String = active.id
			btn(c.row, "Присоединиться", "primary", func(): if not (await act("/guilds/expeditions/%s/join" % eid, {}, "Вы в экспедиции")).is_empty(): render())
	else:
		for code in g.expedition_types:
			var x: Dictionary = g.expedition_types[code]
			var c := card()
			line_to(c.info, String(x.name), 28, UI.TEXT, true)
			line_to(c.info, "%d ч · %d–%d участников · цель силы %s · %s" % [int(x.hours), int(x.min_participants), int(x.max_participants),
				Game.fmt(int(x.power_goal)), Game.rewards_text(x.reward)], 24, UI.MUTED)
			if perm("expedition"):
				var cc: String = code
				btn(c.row, "Отправить", "primary", func(): if not (await act("/guilds/expeditions/start", {"code": cc}, "Экспедиция отправлена")).is_empty(): render())
	for e in g.expeditions:
		if e.status == "done" and e.result:
			txt("%s: %s (%d%%)" % [e.name, "успех" if e.result.success else "частично", int(float(e.result.ratio) * 100)], 22, UI.MUTED)


func _wars_part() -> void:
	h1("Война гильдий")
	var w = g.get("war")
	if w and w.status == "active":
		txt("Противник: [%s] %s%s · счёт %d : %d · до конца %s" % [w.opponent.tag, w.opponent.name, " (ИИ)" if w.opponent.is_ai else "",
			int(w.score), int(w.opponent_score), countdown(String(w.ends_at))], 26, UI.GOLD)
		txt("У каждого участника %d атаки. Победа +3 очка, поражение +1. Бой против защитного отряда соперника." % int(w.attacks_per_member), 22, UI.MUTED)
		for t in w.targets:
			var c := card()
			name_button(c.info, String(t.nickname), String(t.user_id), bool(t.is_ai))
			line_to(c.info, "сила защиты %s · побеждён %d раз" % [Game.fmt(int(t.power)), int(t.defeated_times)], 24, UI.MUTED)
			var tid: String = t.user_id
			var tn: String = t.nickname
			btn(c.row, "Атаковать", "primary", func():
				var r := await act("/guilds/war/attack", {"user_id": tid})
				if not r.is_empty():
					play_battle(r.simulation, "Война гильдий: " + tn, "guild", ["+%d очков гильдии" % int(r.points)], {}, false, {"tab": "wars"}))
	else:
		if w:
			txt("Прошлая война: %s (%d : %d)" % [{"mine": "победа", "opponent": "поражение"}.get(w.winner, "ничья"), int(w.score), int(w.opponent_score)], 24, UI.MUTED)
		if perm("war"):
			btn(_body, "Объявить войну (подбор по уровню)", "primary", func():
				if not (await act("/guilds/war/start", {}, "Война объявлена!")).is_empty(): render())
		else:
			txt("Войну объявляет глава или заместитель.", 24, UI.MUTED)
	_alliance_part()


# ------------------------------------------------------------------ alliances (up to 3 guilds, shared chat, never at war)
func _alliance_part() -> void:
	var gen := _gen
	var d := await get_data("/alliances/mine")
	if not is_inside_tree() or gen != _gen or d.is_empty():
		return
	h1("Союз гильдий")
	var manage: bool = d.get("can_manage", false)
	var a = d.get("alliance")
	if a:
		txt("«%s»" % a.name, 28, UI.GOLD)
		for x in a.guilds:
			txt("[%s] %s%s — ур. %d, участников %d" % [x.tag, x.name, " (ИИ)" if x.is_ai else "", int(x.level), int(x.members)], 24, UI.TEXT)
		txt("Союзники не воюют друг с другом. До %d гильдий в союзе." % int(d.max_guilds), 22, UI.MUTED)
		var ch: String = a.channel
		btn(_body, "Чат союза", "glass", func(): main.open("chat", {"channel": ch}))
		if manage:
			btn(_body, "Выйти из союза", "danger", func():
				if not (await act("/alliances/leave", {}, "Гильдия вышла из союза")).is_empty(): render())
	else:
		txt("Гильдия пока не в союзе. Союз — до %d гильдий: общий чат и мир между союзниками." % int(d.max_guilds), 24, UI.MUTED)
	for p in d.get("incoming", []):
		if p.guild == null:
			continue
		var c := card()
		line_to(c.info, "Предложение союза от [%s] %s%s" % [p.guild.tag, p.guild.name, " (ИИ)" if p.guild.is_ai else ""], 26, UI.GOLD)
		var pid: String = p.id
		if manage:
			btn(c.row, "Принять", "primary", func():
				if not (await act("/alliances/proposals/%s/accept" % pid, {}, "Союз заключён!")).is_empty(): render())
			btn(c.row, "Отклонить", "glass", func():
				if not (await act("/alliances/proposals/%s/decline" % pid, {}, "Отклонено")).is_empty(): render())
	for p in d.get("outgoing", []):
		if p.guild != null:
			txt("Ждём ответа: [%s] %s" % [p.guild.tag, p.guild.name], 22, UI.MUTED)
	if not manage:
		txt("Союзы заключает глава или заместитель.", 22, UI.MUTED)
		return
	if a and a.guilds.size() >= int(d.max_guilds):
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var q := LineEdit.new()
	q.placeholder_text = "Название гильдии"
	q.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	q.add_theme_font_size_override("font_size", 26)
	row.add_child(q)
	var found := VBoxContainer.new()
	found.add_theme_constant_override("separation", 8)
	btn(row, "Найти", "glass", func(): _alliance_search(found, q.text))
	add(row)
	add(found)


func _alliance_search(list: VBoxContainer, query: String) -> void:
	var d := await get_data("/guilds/list?q=" + query.uri_encode())
	if not is_instance_valid(list):
		return
	for c in list.get_children():
		c.queue_free()
	var mine := String(g.guild.id) if g.get("guild") else ""
	for x in d.get("items", []):
		if String(x.id) == mine:
			continue
		var c := card()
		line_to(c.info, "[%s] %s%s · ур. %d" % [x.tag, x.name, " (ИИ)" if x.is_ai else "", int(x.level)], 26, UI.TEXT)
		var gid: String = x.id
		btn(c.row, "Предложить союз", "primary", func():
			var r := await act("/alliances/propose", {"guild_id": gid})
			if not r.is_empty():
				Router.toast({"accepted": "Союз заключён!", "declined": "Гильдия отказалась от союза"}.get(String(r.get("status", "")), "Предложение отправлено"))
				render())
		_body.remove_child(c.card)  # card() appends to the body; the results live in their own list
		list.add_child(c.card)
	if d.get("items", []).is_empty():
		list.add_child(UI.label("Гильдии не найдены", 26, UI.MUTED))


# ------------------------------------------------------------------ log
func _log() -> void:
	for e in g.log:
		var t := "%s  %s %s" % [UI.local_time(String(e.at)), e.actor, LOG_NAMES.get(e.action, e.action)]
		if e.target:
			t += " → " + String(e.target)
		var p: Dictionary = e.get("payload", {})
		if p.has("code"):
			t += " (%s%s)" % [p.code, (" ур.%d" % int(p.level)) if p.has("level") else ""]
		if p.has("new"):
			t += " (%s)" % g.role_names.get(p.new, p.new)
		txt(t, 24, UI.TEXT)
