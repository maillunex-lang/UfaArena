extends Control
## Quest centre: real server categories only.
##   Ежедневные / Основные / Побочные — GET /quests (claim POST /quests/{code}/claim)
##   Достижения — GET /progression (granted automatically by the server when the goal is reached)
##   Гильдия — GET /guilds/mine → tasks (claim POST /guilds/tasks/{code}/claim)
##   События — active world events from GET /player/summary (contributions happen in the event centre)

const TABS := [["daily", "Ежедневные"], ["main", "Основные"], ["side", "Побочные"], ["ach", "Достижения"],
	["guild", "Гильдия"], ["events", "События"]]

var main: Node
var tab := "daily"
var _tabs_box: HBoxContainer
var _list: VBoxContainer
var _quests: Array = []
var _gen := 0


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
	var head := HBoxContainer.new()
	head.add_child(UI.title("Задания", UI.FS.h1))
	head.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 180, 80)
	back.pressed.connect(func(): main.open("home"))
	head.add_child(back)
	v.add_child(head)
	var sc := ScrollContainer.new()
	sc.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sc.custom_minimum_size = Vector2(0, 84)
	_tabs_box = HBoxContainer.new()
	_tabs_box.add_theme_constant_override("separation", UI.SP.s)
	sc.add_child(_tabs_box)
	v.add_child(sc)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", UI.SP.m)
	v.add_child(UI.scroll(_list))
	UI.keep_wrapped(_list)
	_render()


func _render() -> void:
	_gen += 1
	var gen := _gen
	for c in _tabs_box.get_children():
		c.queue_free()
	for t in TABS:
		var key: String = t[0]
		var b := UI.button(String(t[1]), "primary" if key == tab else "glass", 0, 76)
		b.add_theme_font_size_override("font_size", UI.FS.caption + 2)
		b.pressed.connect(func(): tab = key; _render())
		_tabs_box.add_child(b)
	for c in _list.get_children():
		c.queue_free()
	_list.add_child(UI.skeleton(3, 150))
	match tab:
		"ach": await _render_ach(gen)
		"guild": await _render_guild(gen)
		"events": await _render_events(gen)
		_: await _render_quests(gen)


func _clear(gen: int) -> bool:
	if not is_inside_tree() or gen != _gen:
		return false
	for c in _list.get_children():
		c.queue_free()
	return true


func _fail(r: Dictionary) -> void:
	_list.add_child(UI.state("offline" if int(r.get("status", 0)) == 0 else "error", "Не удалось загрузить задания.",
		"Повторить", _render))


# ------------------------------------------------------------------ quests (daily / main / side)
func _render_quests(gen: int) -> void:
	var r := await Api.get_json("/quests")
	if not _clear(gen):
		return
	if not r.ok:
		_fail(r)
		return
	_quests = r.data.quests
	var shown := 0
	for q in _quests:
		if String(q.kind) != tab:
			continue
		shown += 1
		_quest_card(q)
	if shown == 0:
		var txt := {"daily": "Сегодня ежедневных заданий нет.", "main": "Основная цепочка пройдена — новые задания появятся с обновлениями.",
			"side": "Побочных заданий пока нет."}
		_list.add_child(UI.state("empty", String(txt.get(tab, "Заданий нет."))))
	if tab == "daily":
		_list.add_child(UI.label("Ежедневные задания обновляются в 00:00 по серверу.", UI.FS.caption, UI.MUTED))


func _quest_card(q: Dictionary) -> void:
	var card := UI.card(UI.GOLD_DARK if q.claimable else UI.LINE)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", UI.SP.m)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_theme_constant_override("separation", UI.SP.xs)
	info.add_child(UI.label(String(q.title), UI.FS.body_l, UI.MUTED if q.claimed else UI.GOLD, true))
	info.add_child(UI.label(String(q.description), UI.FS.caption, UI.TEXT))
	info.add_child(UI.progress(int(q.progress), int(q.target), "%d/%d" % [mini(int(q.progress), int(q.target)), int(q.target)], UI.TEAL, 22))
	info.add_child(UI.rewards_row(q.rewards, 24))
	h.add_child(info)
	if q.claimed:
		h.add_child(UI.label("✓ Получено", UI.FS.body, UI.ok_color(), true))
	elif q.claimable:
		var b := UI.button("Забрать", "primary", 200, 84)
		var code: String = q.code
		b.pressed.connect(func(): _claim(code, b))
		h.add_child(b)
	else:
		h.add_child(UI.label("В процессе", UI.FS.caption, UI.MUTED))
	card.add_child(h)
	_list.add_child(card)


func _claim(code: String, b: Button) -> void:
	UI.set_loading(b, true)
	var r := await Api.post_json("/quests/%s/claim" % code, {}, true)
	if not is_inside_tree():
		return
	UI.set_loading(b, false)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Награда: " + Game.rewards_text(r.data.rewards))
	_render()


# ------------------------------------------------------------------ achievements
func _render_ach(gen: int) -> void:
	var r := await Api.get_json("/progression")
	if not _clear(gen):
		return
	if not r.ok:
		_fail(r)
		return
	var items: Array = r.data.achievements
	var done := 0
	for a in items:
		if a.done:
			done += 1
	_list.add_child(UI.progress(done, maxi(1, items.size()), "Получено %d из %d" % [done, items.size()], UI.GOLD_DARK, 28))
	_list.add_child(UI.label("Награды за достижения начисляются автоматически, как только цель выполнена.", UI.FS.caption, UI.MUTED))
	# not yet achieved first, sorted by how close they are
	items = items.duplicate()
	items.sort_custom(func(x, y):
		if bool(x.done) != bool(y.done):
			return not x.done
		return float(x.progress) / maxf(1, float(x.goal)) > float(y.progress) / maxf(1, float(y.goal)))
	for a in items:
		var card := UI.card(UI.GOLD_DARK if a.done else UI.LINE)
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", UI.SP.xs)
		var h := HBoxContainer.new()
		var t := UI.label(String(a.name), UI.FS.body_l, UI.GOLD if a.done else UI.TEXT, true)
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(t)
		if a.done:
			h.add_child(UI.label("✓ " + UI.local_time(String(a.at)), UI.FS.caption, UI.ok_color(), true))
		v.add_child(h)
		v.add_child(UI.label(String(a.desc), UI.FS.caption, UI.MUTED))
		if not a.done:
			v.add_child(UI.progress(int(a.progress), int(a.goal), "%s / %s" % [Game.exact(int(a.progress)), Game.exact(int(a.goal))], UI.TEAL, 20))
		if not (a.reward as Dictionary).is_empty():
			v.add_child(UI.rewards_row(a.reward, 24))
		card.add_child(v)
		_list.add_child(card)


# ------------------------------------------------------------------ guild tasks
func _render_guild(gen: int) -> void:
	var r := await Api.get_json("/guilds/mine")
	if not _clear(gen):
		return
	if not r.ok:
		_fail(r)
		return
	if r.data.get("guild") == null:
		_list.add_child(UI.state("locked", "Задания гильдии доступны участникам гильдии.", "Найти гильдию", func(): main.open("guild")))
		return
	_list.add_child(UI.label("Задания дня приносят награды и очки вклада для гильдии.", UI.FS.caption, UI.MUTED))
	for t in r.data.tasks:
		var card := UI.card(UI.LINE)
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", UI.SP.m)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.add_child(UI.label(String(t.name), UI.FS.body_l, UI.TEXT, true))
		info.add_child(UI.progress(int(t.progress), int(t.target), "%d/%d · +%d очков гильдии" % [mini(int(t.progress), int(t.target)), int(t.target), int(t.points)], UI.TEAL, 22))
		info.add_child(UI.rewards_row(t.reward, 24))
		h.add_child(info)
		var done: bool = int(t.progress) >= int(t.target)
		if t.claimed:
			h.add_child(UI.label("✓ Получено", UI.FS.body, UI.ok_color(), true))
		elif done:
			var b := UI.button("Забрать", "primary", 200, 84)
			var code: String = t.code
			b.pressed.connect(func(): _claim_guild(code, b))
			h.add_child(b)
		else:
			h.add_child(UI.label("В процессе", UI.FS.caption, UI.MUTED))
		card.add_child(h)
		_list.add_child(card)


func _claim_guild(code: String, b: Button) -> void:
	UI.set_loading(b, true)
	var r := await Api.post_json("/guilds/tasks/%s/claim" % code, {}, true)
	if not is_inside_tree():
		return
	UI.set_loading(b, false)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Награда: " + Game.rewards_text(r.data.reward))
	_render()


# ------------------------------------------------------------------ events
func _render_events(gen: int) -> void:
	var r := await Api.get_json("/player/summary")
	if not _clear(gen):
		return
	if not r.ok:
		_fail(r)
		return
	if r.data.events.is_empty():
		_list.add_child(UI.state("empty", "Сейчас нет активных событий. Следите за уведомлениями."))
		return
	_list.add_child(UI.label("Вклад в события засчитывается за бои, дозоры, задания и помощь друзьям.", UI.FS.caption, UI.MUTED))
	for e in r.data.events:
		var card := UI.card(UI.TEAL_DEEP)
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", UI.SP.xs)
		v.add_child(UI.label(String(e.name), UI.FS.body_l, UI.TEXT, true))
		v.add_child(UI.progress(int(e.progress), int(e.goal), "Общий прогресс %s / %s" % [Game.fmt(int(e.progress)), Game.fmt(int(e.goal))], UI.TEAL, 22))
		var b := UI.button("Открыть событие", "glass", 0, 76)
		b.pressed.connect(func(): main.open("events"))
		v.add_child(b)
		card.add_child(v)
		_list.add_child(card)
