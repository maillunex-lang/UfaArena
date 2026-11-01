extends Control
## Notification centre: one place for everything that waits for the player, grouped by category and merged
## (one row per category, not one per item). Data: /player/summary (server truth).

var main: Node
var data := {}


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.gui_input.connect(func(e: InputEvent):
		if e is InputEventMouseButton and e.pressed:
			queue_free())
	add_child(dim)
	var p := UI.solid_panel()
	p.set_anchors_preset(Control.PRESET_TOP_WIDE)
	p.offset_left = UI.SP.m
	p.offset_right = -UI.SP.m
	p.offset_top = 210
	p.offset_bottom = 1400
	add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.m)
	p.add_child(v)
	var h := HBoxContainer.new()
	var t := UI.title("Уведомления", UI.FS.h2)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(t)
	var x := UI.button("✕", "glass", 84, 84)
	x.pressed.connect(queue_free)
	h.add_child(x)
	v.add_child(h)
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", UI.SP.s)
	v.add_child(UI.scroll(list))
	var items := _items()
	if items.is_empty():
		list.add_child(UI.state("empty", "Всё под контролем: новых уведомлений нет."))
	for it in items:
		var c := UI.card(it[4])
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", UI.SP.m)
		var ic := GameIcon.new()
		ic.kind = it[0]
		ic.custom_minimum_size = Vector2(60, 60)
		row.add_child(ic)
		var l := UI.label(String(it[1]), UI.FS.body, UI.TEXT)
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		row.add_child(l)
		var go := UI.button("Перейти", "accent", 0, 76)
		var target: String = it[2]
		var params: Dictionary = it[3]
		go.pressed.connect(func(): queue_free(); main.open(target, params))
		row.add_child(go)
		c.add_child(row)
		list.add_child(c)
	UI.pop_in(p)


## [icon, text, screen, params, border]
func _items() -> Array:
	var out: Array = []
	if data.is_empty():
		return out
	var s: Dictionary = data.get("social", {})
	var q: Dictionary = data.get("quests", {})
	var afk: Dictionary = data.get("afk", {})
	if afk.get("full", false):
		out.append(["afk", "Дозор заполнен (%d ч) — заберите награды, иначе накопление остановится" % int(afk.cap_hours), "home", {}, UI.WARNING])
	elif float(afk.get("hours", 0)) >= 1.0:
		out.append(["afk", "Дозор накопил награды за %.1f ч" % float(afk.hours), "home", {}, UI.GOLD_DARK])
	if int(q.get("claimable", 0)) > 0:
		out.append(["quests", "Задания выполнены: %d — заберите награды" % int(q.claimable), "quests", {}, UI.GOLD_DARK])
	if int(data.get("mail_unclaimed", 0)) > 0:
		out.append(["mail", "Почта: %d писем с наградами" % int(data.mail_unclaimed), "mail", {}, UI.GOLD_DARK])
	if int(s.get("friend_requests", 0)) > 0:
		out.append(["friends", "Заявки в друзья: %d" % int(s.friend_requests), "friends", {"tab": "requests"}, Color(0, 0, 0, 0)])
	if int(s.get("gifts", 0)) > 0:
		out.append(["shop", "Подарки от друзей: %d" % int(s.gifts), "friends", {"tab": "gifts"}, Color(0, 0, 0, 0)])
	if int(s.get("guild_apps", 0)) > 0:
		out.append(["guild", "Заявки в гильдию: %d" % int(s.guild_apps), "guild", {"tab": "apps"}, Color(0, 0, 0, 0)])
	if int(s.get("chat_unread", 0)) > 0:
		out.append(["chat", "Новые сообщения в чате: %d" % int(s.chat_unread), "chat", {}, Color(0, 0, 0, 0)])
	for e in data.get("events", []):
		out.append(["events", "Идёт событие «%s»: %s / %s" % [e.name, Game.fmt(int(e.progress)), Game.fmt(int(e.goal))], "events", {}, UI.TEAL_DEEP])
	# categories switched off in Settings → Уведомления are hidden
	var cat := {"afk": "rewards", "quests": "rewards", "mail": "rewards", "friends": "social", "shop": "social",
		"chat": "social", "guild": "guild", "events": "events"}
	return out.filter(func(it): return bool(Config.settings.get("notify_" + String(cat.get(it[0], "rewards")), true)))
