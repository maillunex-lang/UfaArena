extends "res://src/screens/TabScreen.gd"
## World events: server goal, personal / guild / server progress, event battles, votes, consequences,
## and the world chronicle (versioned world state).

var d := {}


func _init() -> void:
	title_text = "События мира"
	tabs = [["active", "Сейчас"], ["chronicle", "Летопись"], ["past", "Прошедшие"]]


func render() -> void:
	d = await get_data("/events")
	if not is_inside_tree() or d.is_empty():
		return
	super.render()


func _render_tab(t: String) -> void:
	match t:
		"active": _active()
		"chronicle": _chronicle()
		"past": _past()


func _active() -> void:
	if d.active.is_empty():
		txt("Сейчас активных событий нет. Еженедельные события начинаются по понедельникам, крупные — в начале месяца.", 26, UI.MUTED)
	for e in d.active:
		var c := card(UI.GOLD)
		line_to(c.info, String(e.name), 32, UI.GOLD, true)
		line_to(c.info, "%s · до конца %s · участников %d" % ["Крупное (месяц)" if e.scale == "monthly" else "Недельное", countdown(String(e.ends_at)),
			int(e.participants)], 24, UI.MUTED)
		line_to(c.info, String(e.desc), 24)
		line_to(c.info, "Общий прогресс сервера: %s / %s" % [Game.fmt(int(e.progress)), Game.fmt(int(e.goal))], 26, UI.ACCENT, true)
		c.info.add_child(UI.bar(int(e.progress), max(1, int(e.goal)), UI.GOLD, 18))
		line_to(c.info, "Ваш вклад: %s · вклад вашей гильдии: %s" % [Game.fmt(int(e.my_points)), Game.fmt(int(e.guild_points))], 25)
		line_to(c.info, "Если цель достигнута: %s" % e.consequences.success, 23, Color("#9fe0a0"))
		if e.consequences.failure:
			line_to(c.info, "Если нет: %s" % e.consequences.failure, 23, Color("#ffb3a8"))
		var pts: Dictionary = e.points_table
		line_to(c.info, "Очки: победа в бою %d, бой %d, дозор %d, задание %d, помощь другу %d, арена %d, урон по боссам 1 за %d." % [
			int(pts.battle_win), int(pts.battle), int(pts.afk_claim), int(pts.quest), int(pts.help), int(pts.arena), int(pts.raid_damage_per)], 22, UI.MUTED)
		var eid: String = e.id
		var nm: String = e.name
		var b := btn(c.info, "Бой события (осталось %d)" % int(e.battles_left), "primary" if int(e.battles_left) > 0 else "dim", func(): _battle(eid, nm))
		b.disabled = int(e.battles_left) <= 0
		if e.choices:
			line_to(c.info, "Голосование (вес голоса = ваш вклад)%s:" % ((" · ваш выбор: " + String(e.choices.get(e.my_choice, ""))) if e.my_choice else ""), 24, UI.ACCENT, true)
			for k in e.choices:
				var kk: String = k
				var votes := int(e.votes.get(k, 0)) if e.votes else 0
				btn(c.info, "%s%s" % [e.choices[k], (" · %s" % Game.fmt(votes)) if votes > 0 else ""], "primary" if e.my_choice == k else "glass",
					func(): if not (await act("/events/%s/vote" % eid, {"choice": kk}, "Голос учтён")).is_empty(): render())
		if e.top.size() > 0:
			var tops: Array = []
			for x in e.top.slice(0, 5):
				tops.append("%s %s" % [x.nickname, Game.fmt(int(x.points))])
			line_to(c.info, "Лучшие игроки: " + ", ".join(tops), 22, UI.MUTED)
		if e.top_guilds.size() > 0:
			var tg: Array = []
			for x in e.top_guilds:
				tg.append("%s %s" % [x.name, Game.fmt(int(x.points))])
			line_to(c.info, "Лучшие гильдии: " + ", ".join(tg), 22, UI.MUTED)


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


func _past() -> void:
	if d.past.is_empty():
		txt("Завершённых событий пока нет.", 26, UI.MUTED)
	for e in d.past:
		var c := card()
		line_to(c.info, "%s — %s" % [e.name, "успех" if e.outcome == "success" else "неудача"], 28, UI.GOLD, true)
		line_to(c.info, "Прогресс %s / %s · ваш вклад %s" % [Game.fmt(int(e.progress)), Game.fmt(int(e.goal)), Game.fmt(int(e.my_points))], 24)
