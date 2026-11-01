extends "res://src/screens/TabScreen.gd"
## World events: server goal, personal / guild / server progress, event battles, votes, consequences,
## and the world chronicle (versioned world state).

var d := {}
var tour := {}
var bp := {}
var quests: Array = []
var arena := {}
var shop := {}
var _open_event := ""


func _init() -> void:
	title_text = "Центр событий"
	tabs = [["all", "Все"], ["daily", "Ежедневные"], ["weekly", "Недельные"], ["seasonal", "Сезонные"], ["special", "Особые"],
		["competitive", "Соревнования"], ["rewards", "Награды"], ["calendar", "Календарь"], ["chronicle", "Летопись"]]


## One centre for everything time-limited (brief §15): world events, tournaments, arena season, battle pass,
## daily quests and seasonal offers. Archive of finished events is intentionally not shown.
func render() -> void:
	var r := await Api.get_json("/events")
	if not is_inside_tree():
		return
	if not r.ok:
		super.render()
		add(UI.state("offline" if int(r.get("status", 0)) == 0 else "error", "События не загрузились.", "Повторить", render))
		return
	d = r.data
	var parts := 0
	for pair in [["/tournaments", "tour"], ["/battlepass", "bp"], ["/arena", "arena"], ["/shop", "shop"]]:
		var x := await Api.get_json(String(pair[0]))
		if not is_inside_tree():
			return
		if x.ok:
			set(String(pair[1]), x.data)
		else:
			parts += 1
	var q := await Api.get_json("/quests")
	if q.ok:
		quests = q.data.quests
	else:
		parts += 1
	if not is_inside_tree():
		return
	super.render()
	if parts > 0:  # partial data: show what loaded and say what didn't
		_body.move_child(add(UI.label("Часть данных не загрузилась (%d из 6 источников). Показано то, что доступно." % parts, 22, UI.WARNING)), 0)


func _render_tab(t: String) -> void:
	match t:
		"all":
			for k in ["daily", "weekly", "seasonal", "special", "competitive"]:
				_category(k, true)
		"chronicle": _chronicle()
		"rewards": _rewards()
		"calendar": _calendar()
		_: _category(t, false)


# ------------------------------------------------------------------ unified card
## Card: name, short description, deadline, progress, rewards, availability status (+ optional action).
func ev_card(title: String, desc: String, ends_iso: String, prog: Array, rewards: Variant, status: String, color: Color,
		action := "", cb := Callable()) -> Dictionary:
	var c := card(color)
	var top := HBoxContainer.new()
	var tl := UI.label(title, 29, UI.GOLD, true)
	tl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	top.add_child(tl)
	if ends_iso != "":
		top.add_child(UI.label("⏳ " + countdown(ends_iso), 23, UI.WARNING, true))
	c.info.add_child(top)
	if desc != "":
		line_to(c.info, desc, 23, UI.TEXT)
	if prog.size() == 3:
		c.info.add_child(UI.progress(float(prog[0]), maxf(1, float(prog[1])), String(prog[2]), UI.TEAL, 22))
	if rewards is Dictionary and not (rewards as Dictionary).is_empty():
		var rr := HBoxContainer.new()
		rr.add_child(UI.label("Награды:", 22, UI.MUTED))
		rr.add_child(UI.rewards_row(rewards, 24))
		c.info.add_child(rr)
	elif rewards is String and rewards != "":
		line_to(c.info, "Награды: " + String(rewards), 22, UI.MUTED)
	line_to(c.info, status, 22, UI.ok_color() if status.begins_with("Доступно") or status.begins_with("Идёт") else UI.MUTED, true)
	if action != "" and cb.is_valid():
		btn(c.row, action, "accent", cb)
	return c


func _event_rewards(e: Dictionary) -> String:
	var rw: Dictionary = e.get("rewards", {})
	var parts := []
	if rw.has("participant"):
		parts.append("участнику " + Game.rewards_text(rw.participant))
	if rw.has("success_bonus"):
		parts.append("при успехе ещё " + Game.rewards_text(rw.success_bonus))
	if rw.has("per_1000"):
		parts.append("за каждые 1000 очков " + Game.rewards_text(rw.per_1000))
	return "; ".join(parts)


func _world_event(e: Dictionary) -> void:
	var eid := String(e.id)
	var st := "Идёт · ваш вклад %s · боёв события сегодня: %d" % [Game.fmt(int(e.my_points)), int(e.battles_left)]
	var ai_pts := int(e.get("ai_progress", 0))
	var total := int(e.progress) + ai_pts
	var goal_text := "Общая цель сервера %s / %s" % [Game.fmt(total), Game.fmt(int(e.goal))]
	if ai_pts > 0:  # decision D-05: the AI residents' contribution is a separate, capped line
		goal_text += " · из них вклад ИИ-жителей %s" % Game.fmt(ai_pts)
	var c := ev_card(String(e.name), String(e.desc), String(e.ends_at),
		[total, int(e.goal), goal_text],
		_event_rewards(e), st, UI.GOLD, "Подробнее" if _open_event != eid else "Свернуть",
		func(): _open_event = "" if _open_event == eid else eid; render())
	if _open_event == eid:
		_event_details(c.info, e)


func _category(k: String, compact: bool) -> void:
	var items := 0
	var head: String = {"daily": "Ежедневные", "weekly": "Недельные", "seasonal": "Сезонные", "special": "Особые", "competitive": "Соревнования"}[k]
	if compact:
		h1(head)
	match k:
		"daily":
			var daily := quests.filter(func(q): return q.kind == "daily")
			var done := daily.filter(func(q): return q.claimed or q.claimable).size()
			var claim := daily.filter(func(q): return q.claimable).size()
			ev_card("Ежедневные задания", "Обновляются каждый день в 00:00 по серверу.", _next_midnight(),
				[done, daily.size(), "Выполнено %d из %d" % [done, daily.size()]], "",
				("Доступно: %d наград к получению" % claim) if claim > 0 else "Идёт", UI.TEAL_DEEP, "Открыть", func(): main.open("quests"))
			items += 1
			for e in d.active:
				items += 1
				ev_card("Бои события «%s»" % e.name, "Каждый день доступны бои события, они приносят очки вклада.", _next_midnight(),
					[], "", ("Доступно боёв сегодня: %d" % int(e.battles_left)) if int(e.battles_left) > 0 else "На сегодня всё — завтра снова",
					UI.TEAL_DEEP, "К событию", func(): tab = "weekly" if e.scale == "weekly" else "seasonal"; _open_event = String(e.id); render())
		"weekly":
			for e in d.active:
				if e.scale == "weekly":
					items += 1
					_world_event(e)
			for t in tour.get("current", []):
				if String(t.scale) == "weekly":
					items += 1
					_tour_card(t)
		"seasonal":
			for e in d.active:
				if e.scale == "monthly":
					items += 1
					_world_event(e)
			if not bp.is_empty():
				items += 1
				var per := int(bp.xp_per_level)
				ev_card("Боевой пропуск: %s" % bp.name, "Сезон %d. Опыт пропуска дают бои, задания и события." % int(bp.season),
					String(bp.ends), [int(bp.xp) % maxi(1, per), per, "Уровень %d · опыт %d / %d" % [int(bp.level), int(bp.xp) % maxi(1, per), per]],
					"награды на каждом уровне (бесплатная и Premium-линии)", "Идёт" + (" · Premium активен" if bp.premium else ""),
					UI.GOLD_DARK, "Открыть", func(): main.open("shop", {"tab": "battlepass"}))
			for it in shop.get("items", []):
				if it.section == "seasonal" and it.available:
					items += 1
					ev_card(String(it.name), "Сезонное предложение магазина.", String(it.expires_at) if it.expires_at else "", [],
						"", "Доступно · " + Game.rub(it.price_rub), UI.GOLD_DARK, "В магазин", func(): main.open("shop", {"tab": "seasonal"}))
		"special":
			for e in d.active:
				if e.scale != "weekly" and e.scale != "monthly":
					items += 1
					_world_event(e)
		"competitive":
			if not arena.is_empty() and arena.has("season"):
				items += 1
				ev_card("Сезон арены", "Рейтинговые бои с отрядами других игроков. Награды по лиге в конце сезона.",
					String(arena.season.ends_at), [], "по лиге в конце сезона", "Доступно", UI.TEAL_DEEP, "На арену", func(): main.open("arena"))
			for t in tour.get("current", []):
				items += 1
				_tour_card(t)
	if items == 0:
		var msg: String = {"daily": "Ежедневных активностей нет.", "weekly": "Сейчас нет недельных событий. Они начинаются по понедельникам.",
			"seasonal": "Сейчас нет сезонных событий.", "special": "Особых событий сейчас нет — их объявляет администрация.",
			"competitive": "Сейчас нет соревнований."}[k]
		if compact:
			txt(msg, 22, UI.MUTED)
		else:
			add(UI.state("empty", msg))


func _tour_card(t: Dictionary) -> void:
	var reg := String(t.status) == "registration"
	var st := ("Идёт регистрация · участников %d" % int(t.entries)) if reg else ("Идёт раунд %d из %d" % [int(t.round), int(t.rounds)])
	if t.mine:
		st += " · вы участвуете"
	ev_card(String(t.name), "Турнир (%s)." % ("недельный" if String(t.scale) == "weekly" else "месячный"),
		String(t.reg_ends_at) if reg else String(t.ends_at), [], "за места в итоговой таблице", st, UI.GOLD,
		"Открыть", func(): main.open("tournaments"))


func _next_midnight() -> String:
	var now := int(Time.get_unix_time_from_system())
	var mid := (now / 86400 + 1) * 86400
	return Time.get_datetime_string_from_unix_time(mid)


# ------------------------------------------------------------------ rewards & calendar
func _rewards() -> void:
	var any := false
	var claim := quests.filter(func(q): return q.claimable)
	if claim.size() > 0:
		any = true
		ev_card("Задания: награды готовы", "Выполненные задания ждут получения.", "", [], "", "Доступно: %d" % claim.size(), UI.GOLD,
			"Забрать", func(): main.open("quests"))
	if not bp.is_empty():
		var lv := int(bp.level)
		var free_left := 0
		for i in range(1, lv + 1):
			if not (i in bp.claimed_free):
				free_left += 1
		var prem_left := 0
		if bp.premium:
			for i in range(1, lv + 1):
				if not (i in bp.claimed_premium):
					prem_left += 1
		if free_left + prem_left > 0:
			any = true
			ev_card("Боевой пропуск: награды уровней", "", String(bp.ends), [], "",
				"Доступно: %d наград" % (free_left + prem_left), UI.GOLD, "Забрать", func(): main.open("shop", {"tab": "battlepass"}))
	for e in d.active:
		any = true
		ev_card("Награды события «%s»" % e.name, "Начисляются автоматически в конце события.", String(e.ends_at), [],
			_event_rewards(e), "Ваш вклад: %s очков" % Game.fmt(int(e.my_points)), UI.TEAL_DEEP)
	if not any:
		add(UI.state("empty", "Сейчас нет наград к получению."))


func _calendar() -> void:
	var rows := []
	for e in d.active:
		rows.append([String(e.starts_at), String(e.ends_at), "Событие: " + String(e.name)])
	for t in tour.get("current", []):
		rows.append([String(t.reg_ends_at), String(t.ends_at), "Турнир: " + String(t.name)])
	if not bp.is_empty():
		rows.append([String(bp.starts), String(bp.ends), "Сезон пропуска: " + String(bp.name)])
	if arena.has("season"):
		rows.append(["", String(arena.season.ends_at), "Сезон арены"])
	rows.sort_custom(func(x, y): return String(x[1]) < String(y[1]))
	txt("Ближайшие сроки — сначала то, что заканчивается раньше.", 22, UI.MUTED)
	if rows.is_empty():
		add(UI.state("empty", "Календарь пуст."))
	for r in rows:
		var c := card()
		line_to(c.info, String(r[2]), 27, UI.TEXT, true)
		line_to(c.info, ("%s — %s" % [UI.local_time(String(r[0])), UI.local_time(String(r[1]))]) if String(r[0]) != "" else ("до " + UI.local_time(String(r[1]))), 23, UI.MUTED)
		c.row.add_child(UI.label("⏳ " + countdown(String(r[1])), 23, UI.WARNING, true))


# ------------------------------------------------------------------ event details (inside the event)
func _event_details(box: VBoxContainer, e: Dictionary) -> void:
	line_to(box, "Ваш вклад: %s · вклад вашей гильдии: %s · участников %d" % [Game.fmt(int(e.my_points)), Game.fmt(int(e.guild_points)),
		int(e.participants)], 24)
	line_to(box, "Если цель достигнута: %s" % e.consequences.success, 23, UI.ok_color())
	if e.consequences.failure:
		line_to(box, "Если нет: %s" % e.consequences.failure, 23, UI.bad_color())
	var pts: Dictionary = e.points_table
	line_to(box, "Очки: победа в бою %d, бой %d, дозор %d, задание %d, помощь другу %d, арена %d, урон по боссам 1 за %d." % [
		int(pts.battle_win), int(pts.battle), int(pts.afk_claim), int(pts.quest), int(pts.help), int(pts.arena), int(pts.raid_damage_per)], 22, UI.MUTED)
	var eid: String = e.id
	var nm: String = e.name
	var b := btn(box, "Бой события (осталось %d)" % int(e.battles_left), "primary" if int(e.battles_left) > 0 else "dim", func(): _battle(eid, nm))
	b.disabled = int(e.battles_left) <= 0
	if e.choices:
		line_to(box, "Голосование (вес голоса = ваш вклад)%s:" % ((" · ваш выбор: " + String(e.choices.get(e.my_choice, ""))) if e.my_choice else ""), 24, UI.ACCENT, true)
		for k in e.choices:
			var kk: String = k
			var votes := int(e.votes.get(k, 0)) if e.votes else 0
			btn(box, "%s%s" % [e.choices[k], (" · %s" % Game.fmt(votes)) if votes > 0 else ""], "primary" if e.my_choice == k else "glass",
				func(): if not (await act("/events/%s/vote" % eid, {"choice": kk}, "Голос учтён")).is_empty(): render())
	if e.top.size() > 0:
		var tops: Array = []
		for x in e.top.slice(0, 5):
			tops.append("%s %s" % [x.nickname, Game.fmt(int(x.points))])
		line_to(box, "Лучшие игроки: " + ", ".join(tops), 22, UI.MUTED)
	if e.top_guilds.size() > 0:
		var tg: Array = []
		for x in e.top_guilds:
			tg.append("%s %s" % [x.name, Game.fmt(int(x.points))])
		line_to(box, "Лучшие гильдии: " + ", ".join(tg), 22, UI.MUTED)


func _battle(eid: String, nm: String) -> void:
	var r := await act("/events/%s/battle" % eid)
	if r.is_empty():
		return
	play_battle(r.simulation, nm, "events", ["+%d очков события" % int(r.points)], r.reward)


func _chronicle() -> void:
	var w: Dictionary = d.world
	txt("Летопись Уралии (версия мира %d). Итоги событий навсегда меняют регионы, открывают территории и сюжет." % int(w.version), 24, UI.MUTED)
	var regions: Dictionary = w.get("regions", {})
	if not regions.is_empty():
		h1("Состояние регионов")
		for k in regions:
			txt("%s: %s" % [k, {"liberated": "освобождён", "scorched": "опалён Тьмой (враги сильнее)"}.get(regions[k], regions[k])], 26)
	var unl: Array = w.get("unlocked", [])
	if unl.size() > 0:
		h1("Открытые территории")
		txt(", ".join(unl), 24)
	h1("События")
	var chron: Array = w.get("chronicle", [])
	if chron.is_empty():
		txt("Летопись ещё не начата: первое событие впишет сюда свою страницу.", 26, UI.MUTED)
	for i in range(chron.size() - 1, -1, -1):
		var x: Dictionary = chron[i]
		txt("%s — %s (%s)" % [UI.local_time(String(x.at)), x.text, "успех" if x.outcome == "success" else "неудача"], 25,
			Color("#9fe0a0") if x.outcome == "success" else Color("#ffb3a8"))
	for s in w.get("story", []):
		txt("«%s»: %s" % [s.event, s.text], 24, UI.TEXT)
