extends "res://src/screens/TabScreen.gd"
## Guild: search / create / invites when not in a guild; otherwise overview, members & management,
## guild fortress (buildings, specialization, research), activities (tasks, expeditions, war) and the log.

const ROLES := ["leader", "deputy", "officer", "veteran", "member", "novice"]
const LOG_NAMES := {"create": "создал гильдию", "join": "вступил", "leave": "покинул гильдию", "kick": "исключил",
	"role": "изменил должность", "transfer": "передал руководство", "invite": "пригласил", "apply": "подал заявку",
	"decline": "отклонил заявку", "edit": "изменил настройки", "building": "улучшил постройку",
	"research": "провёл исследование", "specialize": "выбрал путь", "expedition": "отправил экспедицию",
	"expedition_done": "экспедиция вернулась", "war_start": "объявил войну", "war_declared": "гильдии объявлена война",
	"war_end": "война завершена", "warn": "предупредил", "auto_warn": "автопредупреждение за неактивность"}

var g := {}


func _init() -> void:
	title_text = "Гильдия"


func _extra_setup(_p: Dictionary) -> void:
	head_button("Рейды", func(): main.open("raids"))


func render() -> void:
	var d := await get_data("/guilds/mine")
	if not is_inside_tree():
		return
	g = d
	if d.get("guild") == null:
		tabs = [["find", "Найти"], ["create", "Создать"]]
		if tab not in ["find", "create"]:
			tab = "find"
	else:
		tabs = [["overview", "Обзор"], ["members", "Участники"], ["fortress", "Крепость"], ["activities", "Активности"],
			["log", "Журнал"]]
		if tab not in ["overview", "members", "fortress", "activities", "log"]:
			tab = "overview"
	super.render()


func perm(p: String) -> bool:
	return p in g.get("permissions", [])


func _render_tab(t: String) -> void:
	match t:
		"find": _find()
		"create": _create()
		"overview": _overview()
		"members": _members()
		"fortress": _fortress()
		"activities": _activities()
		"log": _log()


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
	var c := card(UI.GOLD)
	var nr := HBoxContainer.new()
	nr.add_child(UI.label("[%s] %s" % [gd.tag, gd.name], 36, UI.GOLD, true))
	c.info.add_child(nr)
	line_to(c.info, "Уровень %d · опыт %d%s" % [int(gd.level), int(gd.exp), (" / %d" % int(gd.exp_next)) if gd.exp_next != null else ""], 26)
	if gd.exp_next != null:
		c.info.add_child(UI.bar(int(gd.exp), int(gd.exp_next), UI.GOLD, 14))
	line_to(c.info, "Ваша должность: %s · участников %d/%d" % [g.my_role_name, int(gd.members), int(gd.max_members)], 26)
	line_to(c.info, "Казна: %d · очки недели: %d" % [int(gd.treasury), int(gd.week_points)], 26, UI.ACCENT)
	if String(gd.description) != "":
		line_to(c.info, String(gd.description), 24, UI.MUTED)
	var don: Dictionary = g.donate
	h1("Пожертвование в казну")
	txt("%d золота → +%d в казну, +%d очков вклада. Сегодня: %d/%d" % [int(don.per), int(don.treasury), int(don.points),
		int(g.donated_today), int(don.daily_max)], 24, UI.MUTED)
	var b := btn(_body, "Пожертвовать %d золота" % int(don.per), "primary" if int(g.donated_today) < int(don.daily_max) else "dim",
		func(): if not (await act("/guilds/donate", {}, "Спасибо за вклад!")).is_empty(): render())
	b.disabled = int(g.donated_today) >= int(don.daily_max)
	h1("Бонусы гильдии")
	var names := {"atk_pct": "атака (PvE)", "hp_pct": "здоровье (PvE)", "boss_dmg_pct": "урон по боссам",
		"war_atk_pct": "урон в войнах", "war_def_pct": "оборона в войнах", "expedition_pct": "награды экспедиций",
		"afk_gold_pct": "золото AFK"}
	var parts: Array = []
	for k in g.bonuses:
		parts.append("+%d%% %s" % [int(round(float(g.bonuses[k]) * 100)), names.get(k, k)])
	txt(", ".join(parts) if parts.size() > 0 else "Пока нет: улучшайте постройки и исследования.", 26)
	var wr: Dictionary = g.week_rewards
	h1("Недельная награда")
	txt("Каждый активный участник (от %d очков) получает базовую награду %s плюс личный бонус: 1 метка за очко, максимум %d. Так награду получают все активные, а не только сильнейшие." % [
		int(wr.min_points_active), Game.rewards_text(wr.base), int(wr.max_bonus_marks)], 24, UI.MUTED)
	if perm("edit"):
		h1("Настройки")
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		for m in [["open", "Свободно"], ["approval", "По заявке"], ["invite", "Приглашения"]]:
			var mm: String = m[0]
			btn(row, m[1], "primary" if gd.join_mode == mm else "glass", func():
				if not (await act("/guilds/edit", {"join_mode": mm}, "Сохранено")).is_empty(): render())
		add(row)
	if g.has("ai_policy"):
		h1("ИИ-жители в гильдии")
		var pol: Dictionary = g.ai_policy
		for k in pol.names:
			var cb := CheckButton.new()
			cb.text = String(pol.names[k])
			cb.button_pressed = bool(pol.values.get(k, false))
			cb.disabled = not perm("edit")
			cb.add_theme_font_size_override("font_size", 26)
			cb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			var key: String = k
			cb.toggled.connect(func(on: bool): await act("/guilds/ai-policy", {key: on}, "Сохранено"))
			add(cb)
		if not perm("edit"):
			txt("Меняет глава или заместитель.", 22, UI.MUTED)
	var leave := btn(_body, "Покинуть гильдию", "danger", func():
		if not (await act("/guilds/leave", {}, "Вы покинули гильдию")).is_empty():
			render())
	leave.custom_minimum_size.y = 80


# ------------------------------------------------------------------ members
func _members() -> void:
	var my_rank := ROLES.find(String(g.my_role))
	if g.applications.size() > 0:
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
func _activities() -> void:
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
					play_battle(r.simulation, "Война гильдий: " + tn, "guild", ["+%d очков гильдии" % int(r.points)], {}, false, {"tab": "activities"}))
	else:
		if w:
			txt("Прошлая война: %s (%d : %d)" % [{"mine": "победа", "opponent": "поражение"}.get(w.winner, "ничья"), int(w.score), int(w.opponent_score)], 24, UI.MUTED)
		if perm("war"):
			btn(_body, "Объявить войну (подбор по уровню)", "primary", func():
				if not (await act("/guilds/war/start", {}, "Война объявлена!")).is_empty(): render())
		else:
			txt("Войну объявляет глава или заместитель.", 24, UI.MUTED)


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
