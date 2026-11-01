extends "res://src/screens/TabScreen.gd"
## Leaderboards + social progression: reputation, achievements, records and the permanent season legacy.

const CATS := [["power", "Сила"], ["arena", "Арена"], ["guilds", "Гильдии"], ["raids", "Боссы"], ["events", "События"],
	["tournaments", "Турниры"], ["reputation", "Репутация"], ["ai", "ИИ"]]

var cat := "power"


func _init() -> void:
	title_text = "Рейтинги"
	tabs = [["boards", "Рейтинги"], ["achievements", "Достижения"], ["legacy", "Наследие"]]


func _render_tab(t: String) -> void:
	match t:
		"boards": _boards()
		"achievements": _achievements()
		"legacy": _legacy()


func _boards() -> void:
	var gen := _gen
	var flow := HFlowContainer.new()
	flow.add_theme_constant_override("h_separation", 8)
	flow.add_theme_constant_override("v_separation", 8)
	for c in CATS:
		var key: String = c[0]
		btn(flow, c[1], "primary" if key == cat else "glass", func(): cat = key; render())
	add(flow)
	var d := await get_data("/rankings/" + cat)
	if not alive(gen) or d.is_empty():
		return
	txt(String(d.note), 22, UI.MUTED)
	if d.me:
		add(UI.label("Ваше место: %d · %s" % [int(d.me.rank), Game.fmt(int(d.me.value))], 28, UI.GOLD, true))
	if d.items.is_empty():
		txt("Рейтинг пока пуст.", 26, UI.MUTED)
	for r in d.items:
		var mine: bool = r.get("user_id", "") == Api.user_id
		var c := card(UI.GOLD if mine else Color(1, 1, 1, 0.15))
		var ranked: bool = r.get("rank") != null  # AI residents may be listed with the label but without a place
		var medal: String = {1: "🥇 ", 2: "🥈 ", 3: "🥉 "}.get(int(r.rank), "") if ranked else ""
		if r.has("user_id"):
			var h := HBoxContainer.new()
			h.add_child(UI.label(("%s%d." % [medal, int(r.rank)]) if ranked else "—", 28, UI.MUTED, true))
			c.info.add_child(h)
			name_button(h, String(r.name), String(r.user_id), bool(r.get("is_ai", false)))
		else:
			line_to(c.info, "%s%d. %s%s" % [medal, int(r.rank), r.name, " (ИИ-гильдия)" if r.get("is_ai", false) else ""], 28, UI.TEXT, true)
		var extra := String(r.get("extra", ""))
		line_to(c.info, Game.fmt(int(r.value)) + ((" · " + extra) if extra != "" else ""), 24, UI.ACCENT)


func _achievements() -> void:
	var gen := _gen
	var d := await get_data("/progression")
	if not alive(gen) or d.is_empty():
		return
	var c := card(UI.GOLD)
	line_to(c.info, "Репутация %d — «%s»" % [int(d.reputation), d.title], 30, UI.GOLD, true)
	if d.next_title:
		line_to(c.info, "До «%s»: %d" % [d.next_title.name, int(d.next_title.min) - int(d.reputation)], 24)
		c.info.add_child(UI.bar(int(d.reputation), int(d.next_title.min), UI.GOLD, 14))
	line_to(c.info, "Репутация растёт за помощь друзьям, подарки, рейды, задания гильдии, турниры, события и содержательное общение (с дневными лимитами — накрутка не работает).", 22, UI.MUTED)
	var done := 0
	for a in d.achievements:
		done += int(a.done)
	h1("Достижения %d/%d" % [done, d.achievements.size()])
	for a in d.achievements:
		var ac := card(UI.GOLD if a.done else Color(1, 1, 1, 0.15))
		line_to(ac.info, ("✓ " if a.done else "") + String(a.name), 28, UI.GOLD if a.done else UI.TEXT, true)
		line_to(ac.info, "%s · %s/%s" % [a.desc, Game.fmt(int(a.progress)), Game.fmt(int(a.goal))], 24, UI.MUTED)
		if not a.done:
			ac.info.add_child(UI.bar(int(a.progress), max(1, int(a.goal)), UI.ACCENT, 12))
		var rw: Dictionary = a.reward.duplicate()
		var cos = rw.get("cosmetic")
		rw.erase("cosmetic")
		line_to(ac.info, "Награда: " + Game.rewards_text(rw) + (" + косметика" if cos else ""), 22, UI.MUTED)


func _legacy() -> void:
	var gen := _gen
	var d := await get_data("/progression")
	if not alive(gen) or d.is_empty():
		return
	txt(String(d.note), 23, UI.MUTED)
	var rec: Dictionary = d.records
	h1("Рекорды")
	txt("Лучший рейтинг арены: %s\nЛучший удар по боссу: %s\nПобед в турнирах: %d\nУчастий в мировых событиях: %d" % [
		str(int(rec.best_arena_rating)) if rec.best_arena_rating != null else "—", Game.fmt(int(rec.best_raid_hit)),
		int(rec.tournament_wins), int(rec.events_joined)], 26)
	if d.season:
		txt("Текущий сезон: %s · уровень пропуска %d" % [d.season.name, int(d.season.level)], 24, UI.ACCENT)
	h1("История сезонов")
	if d.legacy.is_empty():
		txt("История появится после первых сезонов арены, турниров, рейдов и событий.", 24, UI.MUTED)
	var cat_names := {"arena": "Арена", "tournament": "Турнир", "raid": "Рейд", "event": "Событие"}
	for h in d.legacy:
		var r: Dictionary = h.result
		var t := ""
		match String(h.category):
			"arena": t = "сезон %d: %s, место %d" % [int(h.season), r.get("league", ""), int(r.get("rank", 0))]
			"tournament": t = "%s: место %d из %d" % [r.get("name", ""), int(r.get("place", 0)), int(r.get("of", 0))]
			"raid": t = "%s повержен%s" % [r.get("boss", ""), (" · ★ " + ", ".join(r.get("rare", []))) if r.get("rare", []).size() > 0 else ""]
			"event": t = "%s: %s очков (%s)" % [r.get("name", ""), Game.fmt(int(r.get("points", 0))), "успех" if r.get("outcome") == "success" else "неудача"]
		txt("%s  %s — %s" % [UI.local_time(String(h.at)), cat_names.get(h.category, h.category), t], 24)
