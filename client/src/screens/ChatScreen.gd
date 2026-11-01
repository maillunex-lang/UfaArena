extends Control
## Chat: global, guild and private channels. Polling every few seconds (server: /chat/messages?after=).
## The input row sits at the top so the Android keyboard never covers it; newest messages are shown first.

const POLL_S := 4.0
const PlayerPopup := preload("res://src/ui/PlayerPopup.gd")

var main: Node
var channel := "global"
var _dm_user := ""
var _dm_name := ""
var _channels: Array = []
var _reactions: Array = ["👍", "❤️", "😂", "🔥", "⚔️", "🏔️"]
var _tabs: HBoxContainer
var _list: VBoxContainer
var _entry: LineEdit
var _status: Label
var _last_id := 0
var _rows := {}
var _poll_t := 0.0
var _busy := false


func setup(m: Node, p: Dictionary) -> void:
	main = m
	main.use_world("hub")
	if p.has("to_user"):
		_dm_user = String(p.to_user)
		_dm_name = String(p.get("name", "Игрок"))
		var ids := [Api.user_id, _dm_user]
		ids.sort()
		channel = "dm:%s:%s" % [ids[0], ids[1]]
	elif p.has("channel"):
		channel = String(p.channel)
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 16
	panel.offset_right = -16
	panel.offset_top = 6
	panel.offset_bottom = -6
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Чат", 48))
	head.add_child(UI.expand())
	var fr := UI.button("Друзья", "glass", 0, 80)
	fr.pressed.connect(func(): main.open("friends"))
	head.add_child(fr)
	v.add_child(head)
	var sc := ScrollContainer.new()
	sc.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sc.custom_minimum_size = Vector2(0, 88)
	_tabs = HBoxContainer.new()
	_tabs.add_theme_constant_override("separation", 8)
	sc.add_child(_tabs)
	v.add_child(sc)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	_entry = LineEdit.new()
	_entry.placeholder_text = "Сообщение…"
	_entry.max_length = 300
	_entry.custom_minimum_size = Vector2(0, 96)
	_entry.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_entry.add_theme_font_size_override("font_size", 32)
	_entry.text_submitted.connect(func(_t: String): _send())
	row.add_child(_entry)
	var send := UI.button("➤", "primary", 120, 96)
	send.pressed.connect(_send)
	row.add_child(send)
	v.add_child(row)
	_status = UI.label("", 24, UI.MUTED)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(_status)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 10)
	v.add_child(UI.scroll(_list))
	_load_channels()
	_open_channel(channel)


func _process(delta: float) -> void:
	_poll_t += delta
	if _poll_t >= POLL_S and not _busy:
		_poll_t = 0.0
		_poll()


func _load_channels() -> void:
	var r := await Api.get_json("/chat/channels")
	if not r.ok or not is_inside_tree():
		return
	_channels = r.data.channels
	_reactions = r.data.get("reactions", _reactions)
	if r.data.get("muted_until"):
		_status.text = "Чат ограничен до %s" % (UI.local_time(String(r.data.muted_until)) if String(r.data.muted_until) != "forever" else "решения модератора")
	if _dm_user != "" and not _channels.any(func(c): return c.channel == channel):
		_channels.append({"channel": channel, "name": _dm_name, "unread": 0, "user_id": _dm_user})
	_render_tabs()


func _render_tabs() -> void:
	for c in _tabs.get_children():
		c.queue_free()
	for c in _channels:
		var cap := String(c.name)
		if int(c.get("unread", 0)) > 0 and c.channel != channel:
			cap += " (%d)" % int(c.unread)
		if c.get("is_ai", false):
			cap += " · ИИ"
		var b := UI.button(cap, "primary" if c.channel == channel else "glass", 0, 80)
		b.add_theme_font_size_override("font_size", 28)
		var ch: String = c.channel
		b.pressed.connect(func(): _open_channel(ch))
		_tabs.add_child(b)


func _open_channel(ch: String) -> void:
	channel = ch
	_last_id = 0
	_rows.clear()
	for c in _list.get_children():
		c.queue_free()
	for c in _channels:
		if c.channel == ch:
			c["unread"] = 0
			_dm_user = String(c.get("user_id", "")) if ch.begins_with("dm:") else ""
	_render_tabs()
	if ch == "global":
		_status.text = "Общий чат. Будьте вежливы: ругань и ссылки скрываются, за нарушения — ограничения. Метка «ИИ» — виртуальные жители."
	elif ch.begins_with("guild:"):
		_status.text = "Чат гильдии"
	else:
		_status.text = "Личные сообщения"
	await _poll()


func _poll() -> void:
	if not is_inside_tree():
		return
	_busy = true
	var path := "/chat/messages?channel=%s" % channel.uri_encode()
	if _last_id > 0:
		path += "&after=%d" % _last_id
	var r := await Api.get_json(path)
	_busy = false
	if not r.ok or not is_inside_tree():
		if r.get("status", 0) == 403 and channel.begins_with("dm:"):
			return  # a DM channel exists only after the first message
		return
	for m in r.data.messages:
		_add(m)
		_last_id = max(_last_id, int(m.id))


func _add(m: Dictionary) -> void:
	if _rows.has(int(m.id)):
		return
	var card := PanelContainer.new()
	var mine: bool = m.get("mine", false)
	var bg := Color(0.16, 0.12, 0.05, 0.6) if mine else (Color(0.12, 0.07, 0.2, 0.6) if m.get("is_ai", false) else Color(0.02, 0.03, 0.07, 0.55))
	var sb := UI._flat(bg, UI.GOLD if mine else Color(1, 1, 1, 0.15), 18, 2)
	sb.content_margin_left = 18
	sb.content_margin_right = 18
	sb.content_margin_top = 10
	sb.content_margin_bottom = 10
	card.add_theme_stylebox_override("panel", sb)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	if m.get("system", false):
		var sl := UI.label("⚑ " + String(m.text), 26, Color("#9fe0ff"))
		sl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(sl)
	else:
		var a: Dictionary = m.author
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 10)
		var nb := Button.new()
		nb.text = String(a.nickname)
		nb.flat = true
		nb.focus_mode = Control.FOCUS_NONE
		nb.add_theme_font_override("font", UI.FONT_BOLD)
		nb.add_theme_font_size_override("font_size", 28)
		nb.add_theme_color_override("font_color", UI.GOLD if mine else UI.ACCENT)
		var auid: String = a.user_id
		nb.pressed.connect(func(): PlayerPopup.open(self, auid, main))
		h.add_child(nb)
		if a.get("is_ai", false):
			h.add_child(UI.ai_badge())
		h.add_child(UI.label("ур.%d" % int(a.get("level", 1)), 22, UI.MUTED))
		h.add_child(UI.expand())
		h.add_child(UI.label(UI.local_time(String(m.at)), 22, UI.MUTED))
		v.add_child(h)
		var t := UI.label(String(m.text), 30, UI.TEXT)
		t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(t)
		var rr := HBoxContainer.new()
		rr.add_theme_constant_override("separation", 6)
		_fill_reactions(rr, m)
		v.add_child(rr)
	card.add_child(v)
	_list.add_child(card)
	_list.move_child(card, 0)  # newest first
	_rows[int(m.id)] = card
	while _list.get_child_count() > 120:
		_list.get_child(_list.get_child_count() - 1).queue_free()


func _fill_reactions(rr: HBoxContainer, m: Dictionary) -> void:
	for c in rr.get_children():
		c.queue_free()
	var reacts: Dictionary = m.get("reactions", {})
	for e in reacts:
		var b := UI.button("%s %d" % [e, int(reacts[e].count)], "primary" if reacts[e].mine else "dim", 0, 60)
		b.add_theme_font_size_override("font_size", 24)
		var emo: String = e
		b.pressed.connect(func(): _react(int(m.id), emo, rr, m))
		rr.add_child(b)
	var plus := UI.button("☺+", "dim", 0, 60)
	plus.add_theme_font_size_override("font_size", 24)
	plus.pressed.connect(func(): _menu(rr, m))
	rr.add_child(plus)


func _menu(rr: HBoxContainer, m: Dictionary) -> void:
	for c in rr.get_children():
		c.queue_free()
	for e in _reactions:
		var b := UI.button(String(e), "glass", 70, 60)
		b.add_theme_font_size_override("font_size", 26)
		var emo: String = e
		b.pressed.connect(func(): _react(int(m.id), emo, rr, m))
		rr.add_child(b)
	if not m.get("mine", false):
		var rep := UI.button("Жалоба", "dim", 0, 60)
		rep.add_theme_font_size_override("font_size", 22)
		rep.pressed.connect(func(): _report(int(m.id)))
		rr.add_child(rep)


func _react(mid: int, emo: String, rr: HBoxContainer, m: Dictionary) -> void:
	var r := await Api.post_json("/chat/messages/%d/react" % mid, {"emoji": emo})
	if not r.ok:
		Router.error(r)
		return
	m["reactions"] = r.data.reactions
	if is_instance_valid(rr):
		_fill_reactions(rr, m)


func _report(mid: int) -> void:
	var r := await Api.post_json("/chat/report", {"message_id": mid, "reason": "abuse"})
	if r.ok:
		Router.toast("Жалоба отправлена. Спасибо!")
	else:
		Router.error(r)


func _send() -> void:
	var text := _entry.text.strip_edges()
	if text == "":
		return
	var body := {"text": text}
	if channel.begins_with("dm:") and _dm_user != "":
		body["to_user"] = _dm_user
	else:
		body["channel"] = channel
	var r := await Api.post_json("/chat/send", body)
	if not r.ok:
		Router.error(r)
		return
	_entry.text = ""
	_add(r.data.message)  # cursor is not moved: earlier messages from others still arrive on the next poll
	Sfx.play("click")
