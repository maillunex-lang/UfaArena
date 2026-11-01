extends Control
## Mini chat over the game (brief §16): compact panel with world / guild channels, the latest messages and an input
## line, opened from the top bar on any screen; «Развернуть» opens the full chat screen. AI residents keep their «ИИ» badge.

var main: Node
var channel := "global"
var _guild := ""
var _list: VBoxContainer
var _scroll: ScrollContainer
var _entry: LineEdit
var _tabs: HBoxContainer
var _last := 0
var _t := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.35)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.gui_input.connect(func(e: InputEvent):
		if e is InputEventMouseButton and e.pressed:
			queue_free())
	add_child(dim)
	var p := UI.solid_panel(Color("#bfe3ff"))
	p.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	p.offset_left = 16
	p.offset_right = -16
	p.offset_top = -1060
	p.offset_bottom = -240
	add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	p.add_child(v)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	_tabs = HBoxContainer.new()
	_tabs.add_theme_constant_override("separation", 8)
	_tabs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(_tabs)
	var full := UI.button("Развернуть", "glass", 0, 72)
	full.add_theme_font_size_override("font_size", 24)
	full.pressed.connect(func(): queue_free(); main.open("chat", {"channel": channel}))
	h.add_child(full)
	var x := UI.button("✕", "glass", 72, 72)
	x.pressed.connect(queue_free)
	h.add_child(x)
	v.add_child(h)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 6)
	_scroll = UI.scroll(_list)
	v.add_child(_scroll)
	UI.keep_wrapped(_list)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	_entry = LineEdit.new()
	_entry.placeholder_text = "Сообщение…"
	_entry.max_length = 300
	_entry.custom_minimum_size = Vector2(0, 80)
	_entry.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_entry.add_theme_font_size_override("font_size", 28)
	_entry.text_submitted.connect(func(_t2: String): _send())
	row.add_child(_entry)
	var send := UI.button("➤", "primary", 96, 80)
	send.pressed.connect(_send)
	row.add_child(send)
	v.add_child(row)
	UI.pop_in(p)
	_load_channels()


func _load_channels() -> void:
	var r := await Api.get_json("/chat/channels")
	if not is_inside_tree():
		return
	if r.ok:
		for c in r.data.channels:
			if String(c.channel).begins_with("guild:"):
				_guild = String(c.channel)
	_render_tabs()
	_reload()


func _render_tabs() -> void:
	for c in _tabs.get_children():
		c.queue_free()
	var items := [["global", "Мир"]]
	if _guild != "":
		items.append([_guild, "Гильдия"])
	for it in items:
		var key: String = it[0]
		var b := UI.button(String(it[1]), "primary" if key == channel else "glass", 0, 72)
		b.add_theme_font_size_override("font_size", 24)
		b.pressed.connect(func(): channel = key; _render_tabs(); _reload())
		_tabs.add_child(b)


func _reload() -> void:
	_last = 0
	for c in _list.get_children():
		c.queue_free()
	await _poll()


func _poll() -> void:
	var path := "/chat/messages?channel=%s" % channel.uri_encode()
	if _last > 0:
		path += "&after=%d" % _last
	var r := await Api.get_json(path)
	if not r.ok or not is_inside_tree():
		if not r.ok and _last == 0 and is_inside_tree():
			_list.add_child(UI.state("offline" if int(r.get("status", 0)) == 0 else "error", "Чат недоступен."))
		return
	var msgs: Array = r.data.messages
	if _last == 0 and msgs.size() > 30:
		msgs = msgs.slice(msgs.size() - 30)
	for m in msgs:
		if String(m.channel) != channel:
			continue
		_add(m)
		_last = maxi(_last, int(m.id))
	if msgs.size() > 0:
		await get_tree().process_frame
		await get_tree().process_frame
		if is_instance_valid(_scroll):
			_scroll.scroll_vertical = int(_scroll.get_v_scroll_bar().max_value)


func _add(m: Dictionary) -> void:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 6)
	if m.get("system", false) or m.get("author") == null:
		var s := UI.label(String(m.text), 23, UI.WARNING)
		s.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(s)
	else:
		var a: Dictionary = m.author
		h.add_child(UI.label(String(a.nickname) + ":", 24, UI.GOLD, true))
		if a.get("is_ai", false):
			h.add_child(UI.ai_badge())
		var t := UI.label(String(m.text), 24, UI.TEXT)
		t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(t)
	_list.add_child(h)


func _process(d: float) -> void:
	_t += d
	if _t >= 4.0:
		_t = 0.0
		_poll()


func _send() -> void:
	var text := _entry.text.strip_edges()
	if text == "":
		return
	var r := await Api.post_json("/chat/send", {"text": text, "channel": channel})
	if not r.ok:
		Router.error(r)
		return
	_entry.text = ""
	Sfx.play("click")
	await _poll()
