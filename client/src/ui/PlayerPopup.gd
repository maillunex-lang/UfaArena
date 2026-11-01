extends Control
## Player profile overlay (friends, chat authors, recommendations). AI personas carry the "ИИ" badge.

var user_id := ""
var main: Node
var _box: VBoxContainer


static func open(parent: Node, uid: String, m: Node) -> void:
	var p: Control = load("res://src/ui/PlayerPopup.gd").new()
	p.user_id = uid
	p.main = m
	parent.add_child(p)


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.gui_input.connect(func(e: InputEvent):
		if e is InputEventMouseButton and e.pressed:
			queue_free())
	add_child(dim)
	var panel := UI.solid_panel(Color("#c9a0ff"))
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 30
	panel.offset_right = -30
	panel.offset_top = 260
	panel.offset_bottom = -260
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Профиль", 44))
	head.add_child(UI.expand())
	var close := UI.button("✕", "glass", 90, 80)
	close.pressed.connect(queue_free)
	head.add_child(close)
	v.add_child(head)
	_box = VBoxContainer.new()
	_box.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_box))
	UI.keep_wrapped(_box)
	_load()


func _load() -> void:
	var r := await Api.get_json("/social/profile/" + user_id)
	if not is_inside_tree():
		return
	if not r.ok:
		Router.error(r)
		queue_free()
		return
	var d: Dictionary = r.data
	var c: Dictionary = d.card
	var name_row := HBoxContainer.new()
	name_row.add_theme_constant_override("separation", 12)
	name_row.add_child(UI.label(String(c.nickname), 40, UI.GOLD, true))
	if c.is_ai:
		name_row.add_child(UI.ai_badge())
	_box.add_child(name_row)
	var pres := UI.label("● " + UI.presence_text(String(c.presence)), 26, UI.presence_color(String(c.presence)))
	_box.add_child(pres)
	var info := "%s · уровень %d · сила %s" % [c.uralia_id, int(c.level), Game.fmt(int(c.power))]
	if c.guild:
		info += "\nГильдия: [%s] %s%s" % [c.guild.tag, c.guild.name, " (ИИ-гильдия)" if c.guild.is_ai else ""]
	if c.arena:
		info += "\nАрена: %d (%s)" % [int(c.arena.rating), c.arena.league]
	if String(c.rep_title) != "":
		info += "\nРепутация: %d — %s" % [int(c.reputation), c.rep_title]
	info += "\nДостижений: %d" % int(d.achievements)
	_box.add_child(UI.label(info, 28, UI.TEXT))
	if c.is_ai:
		_box.add_child(UI.label("Это виртуальный житель Уралии (ИИ). Он не участвует в рейтингах игроков и не совершает покупок.", 24, Color("#d6b8ff")))
	var acts := HBoxContainer.new()
	acts.add_theme_constant_override("separation", 10)
	if user_id != Api.user_id:
		if not d.friend:
			var add := UI.button("В друзья", "primary", 0, 92)
			add.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			add.pressed.connect(_add_friend)
			acts.add_child(add)
		var dm := UI.button("Написать", "glass", 0, 92)
		dm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		dm.pressed.connect(func():
			queue_free()
			main.open("chat", {"to_user": user_id, "name": String(c.nickname), "is_ai": bool(c.is_ai)}))
		acts.add_child(dm)
		_box.add_child(acts)
		var acts2 := HBoxContainer.new()
		acts2.add_theme_constant_override("separation", 10)
		var rep := UI.button("Пожаловаться", "dim", 0, 80)
		rep.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		rep.pressed.connect(_report)
		acts2.add_child(rep)
		var blk := UI.button("Заблокировать", "dim", 0, 80)
		blk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		blk.pressed.connect(_block)
		acts2.add_child(blk)
		_box.add_child(acts2)
	if d.squad.size() > 0:
		_box.add_child(UI.label("Отряд · сила %s" % Game.fmt(int(d.squad_power)), 30, UI.ACCENT, true))
		var names: Array = []
		for u in d.squad:
			names.append("%s ур.%d" % [Game.hero_name(String(u.hero_code)), int(u.level)])
		_box.add_child(UI.label(", ".join(names), 26, UI.TEXT))
	_box.add_child(UI.label("Коллекция: %d героев" % d.heroes.size(), 30, UI.ACCENT, true))
	var top: Array = []
	for h in d.heroes.slice(0, 12):
		top.append("%s%s ур.%d" % [h.name, " ★%d" % int(h.stars) if int(h.stars) > 0 else "", int(h.level)])
	_box.add_child(UI.label(", ".join(top), 24, UI.MUTED))
	if not d.fortress.is_empty():
		var parts: Array = []
		for k in d.fortress:
			parts.append("%s %d" % [Game.building_name(String(k)), int(d.fortress[k])])
		_box.add_child(UI.label("Караван: " + ", ".join(parts), 24, UI.MUTED))
	if d.activity.size() > 0:
		_box.add_child(UI.label("Активность", 30, UI.ACCENT, true))
		for a in d.activity.slice(0, 8):
			_box.add_child(UI.label("%s  %s" % [UI.local_time(String(a.at)), a.text], 24, UI.TEXT))


func _add_friend() -> void:
	var r := await Api.post_json("/social/friends/request", {"user_id": user_id, "source": "id"})
	if not r.ok:
		Router.error(r)
		return
	Router.toast("Вы теперь друзья!" if r.data.status == "friends" else "Заявка отправлена")
	queue_free()


func _report() -> void:
	var r := await Api.post_json("/chat/report", {"user_id": user_id, "reason": "abuse"})
	if r.ok:
		Router.toast("Жалоба отправлена модераторам")
	else:
		Router.error(r)


func _block() -> void:
	var r := await Api.post_json("/social/block/" + user_id, {})
	if r.ok:
		Router.toast("Игрок заблокирован: его сообщения скрыты")
		queue_free()
	else:
		Router.error(r)
