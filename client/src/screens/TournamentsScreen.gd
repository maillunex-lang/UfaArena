extends "res://src/screens/TabScreen.gd"
## Tournaments: current (registration / running) and past; details with rules, standings, matches and replays.

const KIND := {"individual": "одиночный", "team": "командный (3 игрока)", "guild": "гильдейский"}
const FORMAT := {"points": "по очкам (швейцарская система)", "groups": "группы → финальная сетка", "bracket": "сетка на выбывание"}
const STATUS := {"registration": "регистрация", "running": "идёт", "finished": "завершён"}

var detail_id := ""


func _init() -> void:
	title_text = "Турниры"
	tabs = [["current", "Текущие"], ["past", "Прошедшие"]]


func _extra_setup(p: Dictionary) -> void:
	detail_id = String(p.get("detail", ""))


func _render_tab(t: String) -> void:
	if detail_id != "":
		_detail(detail_id)
		return
	_list(t)


func _list(t: String) -> void:
	var gen := _gen
	var d := await get_data("/tournaments")
	if not alive(gen) or d.is_empty():
		return
	txt("Бои турниров рассчитывает сервер по расписанию. Отряд фиксируется при регистрации. Награды: ресурсы, титулы, рамки — без боевых преимуществ.", 23, UI.MUTED)
	var items: Array = d.current if t == "current" else d.past
	if items.is_empty():
		txt("Здесь пока пусто.", 26, UI.MUTED)
	for x in items:
		var c := card(UI.GOLD if x.mine else Color(1, 1, 1, 0.18))
		line_to(c.info, String(x.name), 29, UI.GOLD, true)
		line_to(c.info, "%s · %s · %s" % [KIND.get(x.kind, x.kind), FORMAT.get(x.format, x.format), "еженедельный" if x.scale == "weekly" else "ежемесячный"], 23, UI.MUTED)
		var rules: Dictionary = x.rules
		if rules.has("note"):
			line_to(c.info, "Правило: " + String(rules.note), 23, Color("#ffd28a"))
		if rules.has("condition"):
			line_to(c.info, "Условие боя: %s — %s" % [rules.condition.name, rules.condition.desc], 23, Color("#ffd28a"))
		var when := ""
		if x.status == "registration":
			when = "регистрация ещё %s" % countdown(String(x.reg_ends_at))
		elif x.status == "running":
			when = "раунд %d/%d · до конца %s" % [int(x.round), int(x.rounds), countdown(String(x.ends_at))]
		else:
			when = "завершён"
		line_to(c.info, "%s · участников %d · %s" % [STATUS.get(x.status, x.status), int(x.entries), when], 24)
		if x.mine:
			line_to(c.info, "Вы участвуете: %d очков, %d побед" % [int(x.mine.points), int(x.mine.wins)], 24, UI.ACCENT)
		var tid: String = x.id
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		btn(row, "Подробнее", "glass", func(): detail_id = tid; render())
		if x.status == "registration" and not x.mine:
			if x.kind == "team":
				btn(row, "Собрать команду", "primary", func(): _team_pick(tid))
			else:
				btn(row, "Участвовать", "primary", func(): _register(tid, []))
		elif x.status == "registration" and x.mine:
			btn(row, "Сняться", "dim", func(): if not (await act("/tournaments/%s/withdraw" % tid, {}, "Регистрация отменена")).is_empty(): render())
		c.info.add_child(row)


func _register(tid: String, mates: Array) -> void:
	if not (await act("/tournaments/%s/register" % tid, {"teammates": mates}, "Вы зарегистрированы! Отряд зафиксирован")).is_empty():
		render()


func _team_pick(tid: String) -> void:
	var fr := await get_data("/social/friends")
	if fr.is_empty():
		return
	for c in _body.get_children():
		c.queue_free()
	h1("Выберите двух друзей")
	var chosen: Array = []
	var status := txt("Выбрано: 0/2", 26, UI.ACCENT)
	for f in fr.friends:
		if f.is_ai:
			continue
		var c := card()
		name_button(c.info, String(f.nickname), String(f.user_id), false)
		var uid: String = f.user_id
		var b := btn(c.row, "Выбрать", "glass", func(): pass)
		b.pressed.connect(func():
			if uid in chosen:
				chosen.erase(uid)
				b.text = "Выбрать"
			elif chosen.size() < 2:
				chosen.append(uid)
				b.text = "✓"
			status.text = "Выбрано: %d/2" % chosen.size())
	if fr.friends.filter(func(f): return not f.is_ai).size() < 2:
		txt("Нужно минимум два друга-игрока (ИИ-персонажи не участвуют в командных турнирах игроков).", 24, UI.MUTED)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	btn(row, "Зарегистрировать команду", "primary", func(): _register(tid, chosen))
	btn(row, "Назад", "glass", func(): render())
	add(row)


func _detail(tid: String) -> void:
	var gen := _gen
	var x := await get_data("/tournaments/" + tid)
	if not alive(gen) or x.is_empty():
		return
	var row := HBoxContainer.new()
	btn(row, "◀ К списку", "glass", func(): detail_id = ""; render())
	add(row)
	h1(String(x.name))
	txt("%s · %s · %s · раунд %d/%d" % [KIND.get(x.kind, x.kind), FORMAT.get(x.format, x.format), STATUS.get(x.status, x.status),
		int(x.round), int(x.rounds)], 24, UI.MUTED)
	var rw: Dictionary = x.rewards
	txt("Награды: 1 место — %s; 2 — %s; 3 — %s; топ-10 — %s; участие — %s" % [_rw(rw["1"]), _rw(rw["2"]), _rw(rw["3"]),
		_rw(rw.top10), _rw(rw.participant)], 23, UI.MUTED)
	if x.results.get("cancelled", false):
		txt("Турнир отменён: " + String(x.results.get("reason", "")), 26, Color("#ffb3a8"))
	h1("Таблица")
	var place := 0
	for e in x.standings:
		place += 1
		txt("%d. %s%s — %d очк. (%d/%d)%s" % [place, e.name, " (ИИ)" if e.is_ai else "", int(e.points), int(e.wins), int(e.losses),
			" · выбыл" if e.eliminated else ""], 24, UI.GOLD if x.mine and e.id == x.mine.id else UI.TEXT)
	if x.matches.size() > 0:
		h1("Бои")
		for m in x.matches:
			var c := card()
			var sc = m.get("score")
			line_to(c.info, "Раунд %d: %s — %s" % [int(m.round), m.a, m.b], 24, UI.TEXT, true)
			line_to(c.info, "Победитель: %s%s" % [m.winner, (" (%d:%d)" % [int(sc[0]), int(sc[1])]) if sc else ""], 22, UI.MUTED)
			if not m.bye:
				var mid: String = m.id
				var title := "%s — %s" % [m.a, m.b]
				btn(c.row, "Повтор", "glass", func():
					var r := await get_data("/tournaments/match/%s/replay" % mid)
					if not r.is_empty():
						play_battle(r.simulation, title, "tournaments", ["Повтор турнирного боя"], {}, false, {"detail": tid}, "ПОВТОР"))


func _rw(r: Dictionary) -> String:
	var x := r.duplicate()
	var cos = x.get("cosmetic")
	x.erase("cosmetic")
	return Game.rewards_text(x) + (" + косметика" if cos else "")
