extends Control
## Home dashboard: player card, rewards (patrol AFK + mail), campaign progress, daily quests, events, activities.
## Everything shown comes from the server (/player/summary + bootstrap state); no decorative numbers.

var main: Node
var _body: VBoxContainer
var _afk_lbl: Label
var _afk_bar: Control
var _s := {}


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("none")
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", UI.SP.l)
	var sc := UI.scroll(_body)
	sc.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	sc.offset_left = UI.SP.m
	sc.offset_right = -UI.SP.m
	sc.offset_top = UI.SP.s
	add_child(sc)
	UI.keep_wrapped(_body)
	_body.add_child(UI.skeleton(4, 160))
	Game.afk_changed.connect(_tick_afk)
	_load()


func _load() -> void:
	var r := await Api.get_json("/player/summary")
	if not is_inside_tree():
		return
	for c in _body.get_children():
		c.queue_free()
	if not r.ok:
		_body.add_child(UI.state("offline" if r.get("status", 0) == 0 else "error",
			"Не удалось загрузить данные. Проверьте соединение.", "Повторить", func(): main.open("home")))
		return
	_s = r.data
	main.set_badges(_s)
	_rewards()
	_campaign()
	_daily()
	_events()
	_activities()


# ------------------------------------------------------------------ rewards
func _rewards() -> void:
	_body.add_child(UI.section("Награды"))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UI.SP.m)
	var afk := UI.card(UI.GOLD_DARK)
	afk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	afk.size_flags_stretch_ratio = 1.5
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.s)
	var hh := HBoxContainer.new()
	var ic := GameIcon.new()
	ic.kind = "afk"
	ic.custom_minimum_size = Vector2(64, 64)
	hh.add_child(ic)
	var t := VBoxContainer.new()
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.add_child(UI.label("Дозор", UI.FS.h3, UI.GOLD, true))
	_afk_lbl = UI.label("", UI.FS.caption, UI.MUTED)
	t.add_child(_afk_lbl)
	hh.add_child(t)
	v.add_child(hh)
	_afk_bar = UI.progress(0, 1, "", UI.TEAL, 18)
	v.add_child(_afk_bar)
	v.add_child(UI.rewards_row(_s.afk.rewards, 26))
	var claim := UI.button("Забрать", "primary", 0, 84)
	claim.pressed.connect(func(): _claim_afk(claim))
	v.add_child(claim)
	afk.add_child(v)
	row.add_child(afk)
	var mail := UI.card()
	mail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var mv := VBoxContainer.new()
	mv.add_theme_constant_override("separation", UI.SP.s)
	var mh := HBoxContainer.new()
	var mic := GameIcon.new()
	mic.kind = "mail"
	mic.custom_minimum_size = Vector2(64, 64)
	mh.add_child(mic)
	var mt := VBoxContainer.new()
	mt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mt.add_child(UI.label("Почта", UI.FS.h3, UI.GOLD, true))
	var n := int(_s.mail_unclaimed)
	mt.add_child(UI.label("%d с наградами" % n if n > 0 else "Наград нет", UI.FS.caption, UI.MUTED))
	mh.add_child(mt)
	mv.add_child(mh)
	mv.add_child(UI.expand())
	var open := UI.button("Открыть", "glass" if n == 0 else "accent", 0, 84)
	open.pressed.connect(func(): main.open("mail"))
	mv.add_child(open)
	mail.add_child(mv)
	row.add_child(mail)
	_body.add_child(row)
	_tick_afk()


func _process(_d: float) -> void:
	if Engine.get_process_frames() % 30 == 0:
		_tick_afk()


func _tick_afk() -> void:
	if Game.afk.is_empty() or _afk_lbl == null or not is_instance_valid(_afk_lbl):
		return
	var since := Time.get_unix_time_from_datetime_string(String(Game.afk.since).substr(0, 19))
	var now := Time.get_unix_time_from_system() + Game.server_time_offset
	var cap: float = Game.afk.get("cap_s", 28800)
	var el: float = clampf(now - since, 0, cap)
	_afk_lbl.text = "%02d:%02d из %d ч" % [int(el / 3600), int(el / 60) % 60, int(cap / 3600)]
	if is_instance_valid(_afk_bar):
		var pb: ProgressBar = _afk_bar.get_child(0)
		pb.max_value = cap
		pb.value = el


func _claim_afk(b: Button) -> void:
	UI.set_loading(b, true)
	var r := await Api.post_json("/rewards/afk/claim", {}, true)
	UI.set_loading(b, false)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Дозор принёс: " + Game.rewards_text(r.data.rewards))
	await Game.refresh_afk()
	main.onboarding_event("afk")
	_load()


# ------------------------------------------------------------------ campaign
func _campaign() -> void:
	var c: Dictionary = _s.campaign
	_body.add_child(UI.section("Поход", "Карта", func(): main.open("campaign")))
	var card := UI.card(UI.GOLD_DARK)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.s)
	var nx = c.get("next")
	v.add_child(UI.label(("Следующий этап: %s «%s»" % [nx.code, nx.name]) if nx else "Все этапы пройдены!", UI.FS.body_l, UI.TEXT, true))
	v.add_child(UI.progress(int(c.cleared), int(c.total), "Пройдено %d из %d" % [int(c.cleared), int(c.total)], UI.GOLD_DARK, 30))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UI.SP.s)
	row.add_child(UI.label("Сила отряда: %s" % Game.exact(Game.team_power()), UI.FS.body, UI.MUTED))
	row.add_child(UI.expand())
	if nx:
		var go := UI.button("В бой", "primary", 260, 84)
		var code: String = nx.code
		go.pressed.connect(func(): main.open("campaign", {"select": code}))
		row.add_child(go)
	v.add_child(row)
	card.add_child(v)
	_body.add_child(card)


# ------------------------------------------------------------------ daily quests
func _daily() -> void:
	var q: Dictionary = _s.quests
	_body.add_child(UI.section("Ежедневные задания %d/%d" % [int(q.daily_done), int(q.daily_total)], "Все задания",
		func(): main.open("quests")))
	var card := UI.card()
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.m)
	if q.daily.is_empty():
		v.add_child(UI.label("Сегодня заданий нет.", UI.FS.body, UI.MUTED))
	for x in q.daily:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", UI.SP.m)
		var col := VBoxContainer.new()
		col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		col.add_child(UI.label(String(x.title), UI.FS.body, UI.TEXT, true))
		col.add_child(UI.progress(int(x.progress), int(x.target), "%d/%d" % [int(x.progress), int(x.target)], UI.TEAL, 22))
		row.add_child(col)
		if x.claimable:
			var b := UI.button("Забрать", "primary", 200, 76)
			b.pressed.connect(func(): main.open("quests"))
			row.add_child(b)
		elif x.claimed:
			row.add_child(UI.label("✓", UI.FS.h2, UI.ok_color(), true))
		v.add_child(row)
	if int(q.claimable) > 0:
		v.add_child(UI.label("Готово к получению наград: %d" % int(q.claimable), UI.FS.caption, UI.GOLD))
	card.add_child(v)
	_body.add_child(card)


# ------------------------------------------------------------------ events
func _events() -> void:
	_body.add_child(UI.section("События", "Центр событий", func(): main.open("events")))
	if _s.events.is_empty():
		var c := UI.card()
		c.add_child(UI.label("Сейчас нет активных событий.", UI.FS.body, UI.MUTED))
		_body.add_child(c)
	for e in _s.events:
		var card := UI.card(UI.TEAL_DEEP)
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", UI.SP.xs)
		var h := HBoxContainer.new()
		var t := UI.label(String(e.name), UI.FS.body_l, UI.TEXT, true)
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(t)
		h.add_child(UI.label(_left(String(e.ends_at)), UI.FS.caption, UI.WARNING, true))
		v.add_child(h)
		v.add_child(UI.progress(int(e.progress), int(e.goal), "%s / %s" % [Game.fmt(int(e.progress)), Game.fmt(int(e.goal))], UI.TEAL, 22))
		var b := Button.new()
		b.flat = true
		b.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		b.pressed.connect(func(): main.open("events"))
		card.add_child(v)
		card.add_child(b)
		_body.add_child(card)


func _left(iso: String) -> String:
	var t := Time.get_unix_time_from_datetime_string(iso.substr(0, 19)) - Time.get_unix_time_from_system()
	if t <= 0:
		return "завершается"
	var d := int(t / 86400)
	return ("%d д %d ч" % [d, int(fmod(t, 86400) / 3600)]) if d > 0 else ("%d ч %d мин" % [int(t / 3600), int(fmod(t, 3600) / 60)])


# ------------------------------------------------------------------ activities
func _activities() -> void:
	_body.add_child(UI.section("Активности"))
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", UI.SP.m)
	grid.add_theme_constant_override("v_separation", UI.SP.m)
	var soc: Dictionary = _s.social
	for it in [["arena", "Арена", "arena"], ["events", "Рейды", "raids"], ["summon", "Призыв", "summon"],
			["fortress", "Крепость", "fortress"], ["shop", "Магазин", "shop"], ["chat", "Чат", "chat"]]:
		var key: String = it[2]
		var t := UI.tile(it[0], it[1], "", false, int(soc.chat_unread) if key == "chat" else 0)
		t.pressed.connect(func(): main.open(key))
		grid.add_child(t)
	_body.add_child(grid)
	_body.add_child(UI.spacer(UI.SP.l))
