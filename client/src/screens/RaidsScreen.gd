extends "res://src/screens/TabScreen.gd"
## Raids & bosses: guild / world / seasonal / story bosses (phases, vulnerabilities, attempts, tickets, loot odds),
## co-op hunts up to 5 players and the loot history.

const KIND_NAMES := {"guild": "Гильдейский босс", "world": "Мировой босс", "seasonal": "Сезонный босс", "story": "Сюжетный рейд"}


func _init() -> void:
	title_text = "Рейды"
	tabs = [["bosses", "Боссы"], ["coop", "Совместная охота"], ["loot", "Добыча"]]


func _extra_setup(_p: Dictionary) -> void:
	head_button("Гильдия", func(): main.open("guild"))


func _render_tab(t: String) -> void:
	match t:
		"bosses": _bosses()
		"coop": _coop()
		"loot": _loot()


func _bosses() -> void:
	var gen := _gen
	var d := await get_data("/raids")
	if not alive(gen) or d.is_empty():
		return
	txt("Билеты рейда: %d (дают попытку, когда обычные закончились). Урон всех участников по боссу суммируется." % int(d.tickets), 24, UI.MUTED)
	for r in d.raids:
		if r.has("locked"):
			var lc := card()
			line_to(lc.info, KIND_NAMES.get(r.kind, r.kind), 30, UI.MUTED, true)
			line_to(lc.info, String(r.locked), 24, UI.MUTED)
			btn(lc.row, "В гильдию", "glass", func(): main.open("guild"))
			continue
		var c := card(UI.GOLD if r.kind == "world" else Color(1, 1, 1, 0.2))
		line_to(c.info, "%s · %s" % [KIND_NAMES.get(r.kind, r.kind), r.name], 30, UI.GOLD, true)
		if int(r.stages) > 1:
			line_to(c.info, "Этап %d из %d" % [int(r.stage), int(r.stages)], 24, UI.ACCENT)
		line_to(c.info, String(r.desc), 23, UI.MUTED)
		line_to(c.info, "Здоровье: %s / %s · до конца %s" % [Game.fmt(int(r.hp_left)), Game.fmt(int(r.hp_max)), countdown(String(r.ends_at))], 24)
		c.info.add_child(UI.bar(int(r.hp_left), max(1, int(r.hp_max)), Color("#ff6a5c"), 18))
		line_to(c.info, "Фаза %d «%s»: %s" % [int(r.phase), r.phase_name, r.phase_note], 24, Color("#ffd28a"))
		line_to(c.info, "Ваш урон: %s · участников: %d" % [Game.fmt(int(r.my_damage)), int(r.participants)], 24)
		var odds: Array = []
		for l in r.loot:
			odds.append("%s%s %d%%" % ["★" if l.rare else "", l.name, int(round(float(l.chance) * 100))])
		line_to(c.info, "За участие: %s. Добыча при победе (шанс каждому): %s" % [Game.rewards_text(r.base_reward), ", ".join(odds)], 22, UI.MUTED)
		if r.top.size() > 0:
			var tops: Array = []
			for x in r.top.slice(0, 5):
				tops.append("%s%s %s" % [x.nickname, " (ИИ)" if x.is_ai else "", Game.fmt(int(x.damage))])
			line_to(c.info, "Лучшие: " + ", ".join(tops), 22, UI.MUTED)
		var att := "Попытки %d/%d" % [int(r.attempts), int(r.max_attempts)]
		if r.next_attempt_s != null:
			att += " · следующая через %d мин" % int(int(r.next_attempt_s) / 60)
		line_to(c.info, att, 24, UI.ACCENT)
		var kind: String = r.kind
		var nm: String = r.name
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		if r.status == "active":
			btn(row, "Атаковать", "primary" if int(r.attempts) > 0 else "dim", func(): _attack(kind, nm, false))
			if int(r.attempts) <= 0 and int(d.tickets) > 0:
				btn(row, "Билетом", "glass", func(): _attack(kind, nm, true))
		else:
			row.add_child(UI.label("Повержен — ждите нового босса" if r.status == "defeated" else "Рейд завершён", 24, UI.MUTED))
		c.info.add_child(row)


func _attack(kind: String, nm: String, ticket: bool) -> void:
	var r := await act("/raids/attack", {"kind": kind, "use_ticket": ticket})
	if r.is_empty():
		return
	var lines := ["Урон по боссу: %s" % Game.fmt(int(r.damage))]
	for n in r.simulation.get("phase_notes", []):
		lines.append(String(n))
	if r.killed:
		lines.append("Босс повержен! Добыча разослана по почте.")
	play_battle(r.simulation, nm, "raids", lines, r.reward, true, {}, "БОСС ПОВЕРЖЕН" if r.killed else "УРОН НАНЕСЁН")


func _coop() -> void:
	var gen := _gen
	var d := await get_data("/raids/coop")
	if not alive(gen) or d.is_empty():
		return
	txt("До 5 игроков в одном бою: отряды входят волнами, здоровье босса общее. Попытки: %d/%d. Свободные места можно занять ИИ-союзниками (только PvE)." % [
		int(d.attempts), int(d.max_attempts)], 24, UI.MUTED)
	var mine = null
	for lb in d.open:
		if lb.leader_id == Api.user_id:
			mine = lb
	if mine == null:
		h1("Собрать отряд")
		for b in d.bosses:
			var code: String = b.code
			btn(_body, "Сбор на «%s»" % b.name, "primary", func():
				if not (await act("/raids/coop/create", {"boss_code": code}, "Сбор создан")).is_empty(): render())
	h1("Открытые сборы")
	if d.open.is_empty():
		txt("Сейчас сборов нет — создайте свой.", 24, UI.MUTED)
	for lb in d.open:
		var c := card(UI.GOLD if lb.leader_id == Api.user_id else Color(1, 1, 1, 0.18))
		line_to(c.info, "%s · %d/%d · общее здоровье %s" % [lb.boss_name, lb.members.size(), int(lb.max), Game.fmt(int(lb.hp))], 28, UI.GOLD, true)
		var names: Array = []
		var joined := false
		for m in lb.members:
			names.append(String(m.nickname) + (" (ИИ)" if m.is_ai else ""))
			joined = joined or m.user_id == Api.user_id
		line_to(c.info, ", ".join(names), 24)
		var lid: String = lb.id
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		if lb.leader_id == Api.user_id:
			if lb.members.size() < int(lb.max):
				btn(row, "+ ИИ-союзник", "glass", func(): if not (await act("/raids/coop/%s/add-ai" % lid)).is_empty(): render())
			btn(row, "В бой!", "primary", func(): _coop_start(lid, String(lb.boss_name)))
		elif not joined and lb.members.size() < int(lb.max):
			btn(row, "Присоединиться", "primary", func(): if not (await act("/raids/coop/%s/join" % lid, {}, "Вы в отряде")).is_empty(): render())
		elif joined:
			row.add_child(UI.label("Вы в отряде, ждём лидера", 24, UI.MUTED))
		c.info.add_child(row)
	if d.recent.size() > 0:
		h1("Ваши недавние охоты")
		for lb in d.recent:
			var res: Dictionary = lb.result
			txt("%s: %s" % [lb.boss_name, "победа" if res.get("victory", false) else "босс выстоял"], 24)


func _coop_start(lid: String, boss: String) -> void:
	var r := await act("/raids/coop/%s/start" % lid)
	if r.is_empty():
		return
	var res: Dictionary = r.lobby.result
	var lines := []
	for w in res.waves:
		lines.append("%s%s: %s урона" % [w.nickname, " (ИИ)" if w.is_ai else "", Game.fmt(int(w.damage))])
	lines.append("Победа! Добыча выдана." if res.victory else "Босс выстоял. Награда за участие выдана.")
	if r.simulation:
		play_battle(r.simulation, "Совместная охота: " + boss, "raids", lines, {}, true, {"tab": "coop"},
			"ПОБЕДА ОТРЯДА" if res.victory else "БОСС ВЫСТОЯЛ")
	else:
		Router.toast(" · ".join(lines))
		render()


func _loot() -> void:
	var gen := _gen
	var d := await get_data("/raids/loot")
	if not alive(gen) or d.is_empty():
		return
	txt("Каждая добыча — отдельный бросок на сервере с указанным шансом. Повторная выдача исключена.", 24, UI.MUTED)
	if d.items.is_empty():
		txt("Пока пусто. Победите босса, чтобы получить добычу.", 26, UI.MUTED)
	for it in d.items:
		txt("%s  %s%s: %s (шанс %d%%)" % [UI.local_time(String(it.at)), "★ " if it.rare else "", it.name, Game.rewards_text(it.item),
			int(round(float(it.chance) * 100))], 24, UI.GOLD if it.rare else UI.TEXT)
