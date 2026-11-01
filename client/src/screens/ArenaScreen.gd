extends "res://src/screens/TabScreen.gd"
## PvP arena 5v5: rating, league, season; ranked opponents (real players only) and AI training;
## defense squad; attack/defense history with replays.

var d := {}


func _init() -> void:
	title_text = "Арена"
	tabs = [["fight", "Бой"], ["defense", "Защита"], ["history", "История"], ["season", "Сезон"]]


func render() -> void:
	d = await get_data("/arena")
	if not is_inside_tree() or d.is_empty():
		return
	super.render()


func _render_tab(t: String) -> void:
	match t:
		"fight": _fight()
		"defense": _defense()
		"history": _history()
		"season": _season()


func _me_card() -> void:
	var me: Dictionary = d.me
	var c := card(UI.GOLD)
	line_to(c.info, "Рейтинг %d · лига «%s»%s" % [int(me.rating), me.league.name, (" · место %d" % int(me.rank)) if me.rank != null else ""], 30, UI.GOLD, true)
	line_to(c.info, "Победы %d / поражения %d · защита %d/%d · лучший %d" % [int(me.wins), int(me.losses), int(me.def_wins),
		int(me.def_losses), int(me.best)], 24)
	line_to(c.info, "Рейтинговые попытки: %d · тренировки: %d · сезон до %s" % [int(me.attempts_left), int(me.training_left),
		countdown(String(d.season.ends_at))], 24, UI.ACCENT)


func _fight() -> void:
	_me_card()
	txt("Атакует ваш текущий отряд кампании. Рейтинговые бои — только против реальных игроков, подбор по рейтингу и силе защиты.", 23, UI.MUTED)
	h1("Рейтинговые соперники")
	if d.candidates.ranked.is_empty():
		txt("Сейчас нет соперников в вашем диапазоне рейтинга. Попробуйте позже или потренируйтесь.", 24, UI.MUTED)
	for o in d.candidates.ranked:
		_opp(o, "ranked")
	h1("Тренировка с ИИ-жителями")
	txt("Не меняет рейтинг. ИИ-персонажи играют в отдельной лестнице.", 23, UI.MUTED)
	for o in d.candidates.training:
		_opp(o, "training")


func _opp(o: Dictionary, kind: String) -> void:
	var c := card()
	name_button(c.info, String(o.nickname), String(o.user_id), bool(o.is_ai))
	var heroes: Array = []
	for u in o.defense:
		heroes.append(Game.hero_name(String(u.hero_code)))
	line_to(c.info, "ур.%d · рейтинг %d (%s) · сила %s" % [int(o.level), int(o.rating), o.league, Game.fmt(int(o.power))], 24, UI.MUTED)
	line_to(c.info, ", ".join(heroes), 22, UI.TEXT)
	if kind == "ranked":
		line_to(c.info, "Победа: +%d" % int(o.win_delta), 22, UI.ACCENT)
	var oid: String = o.user_id
	var nick: String = o.nickname
	var left := int(d.me.attempts_left) if kind == "ranked" else int(d.me.training_left)
	var b := btn(c.row, "В бой" if kind == "ranked" else "Тренировка", "primary" if left > 0 else "dim", func(): _go(oid, nick, kind))
	b.disabled = left <= 0


func _go(oid: String, nick: String, kind: String) -> void:
	var r := await act("/arena/fight", {"opponent_id": oid, "kind": kind})
	if r.is_empty():
		return
	var lines := []
	if kind == "ranked":
		lines.append("Рейтинг: %d (%s%d) · лига «%s»" % [int(r.rating), "+" if int(r.delta) >= 0 else "", int(r.delta), r.league.name])
	else:
		lines.append("Тренировочный бой: рейтинг не меняется")
	play_battle(r.simulation, "Арена: " + nick, "arena", lines, r.reward)


func _defense() -> void:
	var me: Dictionary = d.me
	txt("Защитный отряд сражается за вас, пока вы не в игре. Сила защиты: %s" % Game.fmt(int(me.defense_power)), 26, UI.GOLD)
	for u in me.defense:
		txt("Слот %d: %s · ур.%d%s" % [int(u.slot) + 1, Game.hero_name(String(u.hero_code)), int(u.level),
			(" ★%d" % int(u.stars)) if int(u.stars) > 0 else ""], 26)
	btn(_body, "Поставить текущий отряд кампании в защиту", "primary", func():
		var r := await act("/arena/defense", {"slots": Game.formation}, "Защита обновлена")
		if not r.is_empty():
			render())
	btn(_body, "Изменить отряд кампании", "glass", func(): main.open("formation", {"back": "arena"}))
	var da: Dictionary = d.defense_analysis
	h1("Анализ защиты")
	txt("Недавних атак на вас: %d, отбито: %d." % [int(da.total), int(da.won)], 26)
	for m in d.history:
		if m.role == "defense":
			txt("%s  %s%s — %s (%s%d)" % [UI.local_time(String(m.at)), m.opponent, " (ИИ)" if m.opponent_is_ai else "",
				"отбита" if m.won else "прорвана", "+" if int(m.delta) >= 0 else "", int(m.delta)], 24, UI.GOLD if m.won else Color("#ffb3a8"))


func _history() -> void:
	if d.history.is_empty():
		txt("Боёв пока не было.", 26, UI.MUTED)
	for m in d.history:
		var c := card()
		line_to(c.info, "%s %s%s" % ["Атака на" if m.role == "attack" else "Защита от", m.opponent, " (ИИ)" if m.opponent_is_ai else ""], 26, UI.TEXT, true)
		line_to(c.info, "%s · %s%s · %s" % [UI.local_time(String(m.at)), "победа" if m.won else "поражение",
			(" · %s%d" % ["+" if int(m.delta) >= 0 else "", int(m.delta)]) if m.kind == "ranked" else " · тренировка", ""], 24,
			UI.GOLD if m.won else Color("#ffb3a8"))
		var mid: String = m.id
		btn(c.row, "Повтор", "glass", func():
			var r := await get_data("/arena/replay/" + mid)
			if not r.is_empty():
				play_battle(r.simulation, "Повтор: %s vs %s" % [r.attacker, r.defender], "arena", ["Повтор боя рассчитан сервером заново"], {}, false, {"tab": "history"}, "ПОВТОР"))


func _season() -> void:
	txt("Сезон %d длится 30 дней. В конце: награды по лиге (почтой), частичный сброс рейтинга, история сохраняется навсегда." % int(d.season.id), 25)
	for lg in d.season.leagues:
		var c := card(UI.GOLD if lg.code == d.me.league.code else Color(1, 1, 1, 0.18))
		line_to(c.info, "%s — от %d" % [lg.name, int(lg.min)], 28, UI.GOLD, true)
		var rw: Dictionary = lg.reward.duplicate()
		var cos = rw.get("cosmetic")
		rw.erase("cosmetic")
		line_to(c.info, Game.rewards_text(rw) + (" + косметика" if cos else ""), 24, UI.MUTED)
	txt("Победа: %s · поражение: %s · тренировка: %s" % [Game.rewards_text(d.rewards.win), Game.rewards_text(d.rewards.loss),
		Game.rewards_text(d.rewards.training)], 23, UI.MUTED)
