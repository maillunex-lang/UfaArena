extends Control
## Chat (dark-fantasy layout): title plaque, tabs Общий / Гильдии / Личный, message rows with round hero avatars,
## level badges and guild tags, event cards with a "Перейти" button, emoji picker and a bottom input that rises above
## the on-screen keyboard. Polls the server every few seconds; at most MAX_ROWS messages stay on screen
## (the server also keeps only the newest 100 per channel).

const POLL_S := 4.0
const MAX_ROWS := 100
const PlayerPopup := preload("res://src/ui/PlayerPopup.gd")
const OrnateFrame := preload("res://src/ui/OrnateFrame.gd")
const CIRCLE := preload("res://src/ui/circle.gdshader")
const UI_DIR := "res://assets/ui/chat/"
const EMOJI := ["😀", "😂", "🤣", "😎", "😏", "😉", "😊", "😍", "🥰", "😘", "😳", "😅", "🙃", "🤔", "😤", "😭", "😡", "🤡",
	"👍", "👎", "👏", "🙏", "💪", "🤝", "🔥", "❤️", "💔", "⭐", "✨", "⚔️", "🛡️", "🏹", "🏔️", "🐺", "🦅", "🍪", "🥛", "🎉", "💎", "👑"]
const TEXT_C := Color("#eef3f2")
const NAME_C := Color("#f6e7c1")
const TEAL := Color("#3fd6c8")
const GOLD_C := Color("#e6b452")

var main: Node
var mode := "global"  # global | guild | dm_list | dm | channels | chan (region / event / alliance / group / news)
var channel := "global"
var _guild_channel := ""
var _dm_user := ""
var _dm_name := ""
var _channels: Array = []
var _reactions: Array = ["👍", "❤️", "😂", "🔥", "⚔️", "🏔️"]
var _frame: Control
var _tabs := {}
var _list: VBoxContainer
var _scroll: ScrollContainer
var _entry: LineEdit
var _input_row: HBoxContainer
var _emoji_panel: PanelContainer
var _status: Label
var _last_id := 0
var _rows := {}
var _poll_t := 0.0
var _busy := false
var _base_bottom := -6.0


func setup(m: Node, p: Dictionary) -> void:
	main = m
	main.use_world("none")
	if p.has("to_user"):
		_open_dm_target(String(p.to_user), String(p.get("name", "Игрок")))
	elif String(p.get("channel", "")).begins_with("guild:"):
		mode = "guild"
		channel = String(p.channel)
	elif String(p.get("channel", "")) != "" and String(p.channel) != "global":
		mode = "chan"
		channel = String(p.channel)
	_build()
	_load_channels()


# ------------------------------------------------------------------ optional artist textures (drop-in, see docs)
func _tex(name: String) -> Texture2D:
	var art := UI.art("ui/chat/" + name)  # uploaded in the admin panel
	if art:
		return art
	var path := UI_DIR + name
	return load(path) if ResourceLoader.exists(path) else null


func _tex_style(name: String, margin: int) -> StyleBoxTexture:
	var t := _tex(name)
	if t == null:
		return null
	var sb := StyleBoxTexture.new()
	sb.texture = t
	sb.texture_margin_left = margin
	sb.texture_margin_right = margin
	sb.texture_margin_top = margin
	sb.texture_margin_bottom = margin
	sb.content_margin_left = margin * 0.7
	sb.content_margin_right = margin * 0.7
	sb.content_margin_top = margin * 0.45
	sb.content_margin_bottom = margin * 0.45
	return sb


# ------------------------------------------------------------------ layout
func _build() -> void:
	_frame = Control.new()
	_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_frame.offset_left = 10
	_frame.offset_right = -10
	_frame.offset_top = 4
	_frame.offset_bottom = _base_bottom
	add_child(_frame)
	var bg: Control = OrnateFrame.new()
	bg.texture_path = UI_DIR + "panel.png"
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bg.crest = true
	_frame.add_child(bg)
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.offset_left = 22
	v.offset_right = -22
	v.offset_top = 18
	v.offset_bottom = -18
	v.add_theme_constant_override("separation", 12)
	_frame.add_child(v)
	v.add_child(_title_plaque())
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 10)
	for t in [["global", "chat", "Общий"], ["guild", "guild", "Гильдия"], ["dm_list", "mail", "Личные"], ["channels", "world", "Каналы"]]:
		var b := _tab_button(t[1], t[2])
		var key: String = t[0]
		b.pressed.connect(func(): _switch(key))
		tabs.add_child(b)
		_tabs[key] = b
	v.add_child(tabs)
	_status = UI.label("", 22, Color("#9fb7b4"))
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(_status)
	var list_bg := PanelContainer.new()
	var lsb := UI._flat(Color(0.01, 0.04, 0.05, 0.55), Color(GOLD_C, 0.35), 12, 1)
	lsb.content_margin_left = 6
	lsb.content_margin_right = 6
	lsb.content_margin_top = 6
	lsb.content_margin_bottom = 6
	list_bg.add_theme_stylebox_override("panel", lsb)
	list_bg.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var bgt := _tex("background.png")
	if bgt:
		var bgr := TextureRect.new()
		bgr.texture = bgt
		bgr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		bgr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		bgr.modulate = Color(1, 1, 1, 0.55)
		bgr.mouse_filter = Control.MOUSE_FILTER_IGNORE
		list_bg.add_child(bgr)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 14)
	_scroll = UI.scroll(_list)
	list_bg.add_child(_scroll)
	v.add_child(list_bg)
	_emoji_panel = _build_emoji_panel()
	_emoji_panel.visible = false
	v.add_child(_emoji_panel)
	_input_row = HBoxContainer.new()
	_input_row.add_theme_constant_override("separation", 10)
	var emo := _square_button("😊", func(): _emoji_panel.visible = not _emoji_panel.visible)
	_input_row.add_child(emo)
	_entry = LineEdit.new()
	_entry.placeholder_text = "Написать сообщение…"
	_entry.max_length = 300
	_entry.custom_minimum_size = Vector2(0, 96)
	_entry.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_entry.add_theme_font_size_override("font_size", 32)
	var esb := UI._flat(Color(0.02, 0.06, 0.07, 0.9), Color(GOLD_C, 0.6), 46, 2)
	esb.content_margin_left = 28
	esb.content_margin_right = 28
	_entry.add_theme_stylebox_override("normal", esb)
	var efs := esb.duplicate() as StyleBoxFlat
	efs.border_color = GOLD_C
	_entry.add_theme_stylebox_override("focus", efs)
	_entry.text_submitted.connect(func(_t: String): _send())
	_input_row.add_child(_entry)
	var send := UI.button("➤", "primary", 116, 96)
	send.add_theme_font_size_override("font_size", 42)
	send.pressed.connect(_send)
	_input_row.add_child(send)
	v.add_child(_input_row)


func _title_plaque() -> Control:
	var h := HBoxContainer.new()
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_theme_constant_override("separation", 0)
	var left := UI.expand()
	h.add_child(left)
	var plaque := Control.new()
	plaque.custom_minimum_size = Vector2(440, 100)
	var pf: Control = OrnateFrame.new()
	pf.texture_path = UI_DIR + "title_plaque.png"
	pf.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pf.radius = 10
	pf.fill = Color(0.03, 0.12, 0.13, 0.98)
	plaque.add_child(pf)
	var t := UI.title("Чат", 56)
	t.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	t.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	plaque.add_child(t)
	h.add_child(plaque)
	var right := HBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.alignment = BoxContainer.ALIGNMENT_END
	var info := _square_button("i", func(): _show_rules())
	info.custom_minimum_size = Vector2(80, 80)
	right.add_child(info)
	h.add_child(right)
	return h


func _tab_button(icon: String, caption: String) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(0, 100)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.focus_mode = Control.FOCUS_NONE
	var h := HBoxContainer.new()
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_theme_constant_override("separation", 10)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ic := GameIcon.new()
	ic.kind = icon
	ic.custom_minimum_size = Vector2(54, 54)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(ic)
	var l := UI.label(caption, 28, NAME_C, true)
	l.name = "Caption"
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(l)
	b.add_child(h)
	var badge := PanelContainer.new()
	var bsb := UI._flat(Color("#e53b2f"), Color.WHITE, 16, 2)
	bsb.content_margin_left = 8
	bsb.content_margin_right = 8
	badge.add_theme_stylebox_override("panel", bsb)
	badge.add_child(UI.label("0", 20, Color.WHITE, true))
	badge.name = "Badge"
	badge.visible = false
	badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
	badge.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	badge.position = Vector2(-34, -10)
	b.add_child(badge)
	b.pressed.connect(func(): Sfx.play("click"))
	return b


func _style_tabs() -> void:
	for key in _tabs:
		var b: Button = _tabs[key]
		var active: bool = key == mode or (key == "dm_list" and mode == "dm") or (key == "channels" and mode == "chan")
		var sb: StyleBox = _tex_style("tab_active.png" if active else "tab.png", 30)
		if sb == null:
			var flat := UI._flat(Color("#5a3b10") if active else Color(0.03, 0.1, 0.12, 0.95), GOLD_C if active else Color(GOLD_C, 0.5), 14, 3 if active else 2)
			if active:
				flat.shadow_color = Color(1.0, 0.75, 0.3, 0.35)
				flat.shadow_size = 12
			sb = flat
		for st in ["normal", "hover", "pressed"]:
			b.add_theme_stylebox_override(st, sb)


func _square_button(text: String, cb: Callable) -> Button:
	var b := UI.button(text, "glass", 96, 96)
	b.add_theme_font_size_override("font_size", 40)
	var sb := UI._flat(Color(0.03, 0.1, 0.12, 0.95), GOLD_C, 18, 2)
	for st in ["normal", "hover", "pressed"]:
		b.add_theme_stylebox_override(st, sb)
	b.pressed.connect(cb)
	return b


func _build_emoji_panel() -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.07, 0.08, 0.97), Color(GOLD_C, 0.6), 16, 2))
	var g := GridContainer.new()
	g.columns = 10
	g.add_theme_constant_override("h_separation", 6)
	g.add_theme_constant_override("v_separation", 6)
	for e in EMOJI:
		var b := Button.new()
		b.text = e
		b.flat = true
		b.focus_mode = Control.FOCUS_NONE
		b.custom_minimum_size = Vector2(84, 70)
		b.add_theme_font_size_override("font_size", 38)
		var emo: String = e
		b.pressed.connect(func(): _entry.text += emo; _entry.caret_column = _entry.text.length())
		g.add_child(b)
	p.add_child(g)
	return p


func _show_rules() -> void:
	Router.toast("Будьте вежливы: ругань, ссылки и телефоны скрываются. Жалоба — кнопка «…» у сообщения. Метка «ИИ» — виртуальные жители. В чате видны последние %d сообщений." % MAX_ROWS)


# ------------------------------------------------------------------ keyboard: lift the frame above it
func _process(delta: float) -> void:
	_poll_t += delta
	if _poll_t >= POLL_S and not _busy and mode != "dm_list":
		_poll_t = 0.0
		_poll()
	var kb := DisplayServer.virtual_keyboard_get_height()
	var lift := 0.0
	if kb > 0:
		var win := DisplayServer.window_get_size()
		var vis := get_viewport_rect().size
		lift = float(kb) * vis.y / max(1.0, float(win.y))
		lift = max(0.0, lift - 230.0)  # the bottom nav bar (230 px) is already below the content area
	var target := _base_bottom - lift
	if abs(_frame.offset_bottom - target) > 1.0:
		_frame.offset_bottom = target


# ------------------------------------------------------------------ channels & tabs
func _load_channels() -> void:
	var r := await Api.get_json("/chat/channels")
	if not r.ok or not is_inside_tree():
		return
	_channels = r.data.channels
	_reactions = r.data.get("reactions", _reactions)
	for c in _channels:
		if String(c.channel).begins_with("guild:"):
			_guild_channel = c.channel
	var dm_unread := 0
	for c in _channels:
		if String(c.channel).begins_with("dm:"):
			dm_unread += int(c.get("unread", 0))
	_set_badge("dm_list", dm_unread)
	var ch_unread := 0
	for c in _channels:
		if c.has("kind"):
			ch_unread += int(c.get("unread", 0))
	_set_badge("channels", ch_unread)
	_set_badge("guild", int(_find_channel(_guild_channel).get("unread", 0)) if _guild_channel != "" else 0)
	if r.data.get("muted_until"):
		_status.text = "Чат ограничен до %s" % (UI.local_time(String(r.data.muted_until)) if String(r.data.muted_until) != "forever" else "решения модератора")
	_switch(mode, true)


func _find_channel(ch: String) -> Dictionary:
	for c in _channels:
		if c.channel == ch:
			return c
	return {}


func _set_badge(key: String, n: int) -> void:
	var badge: PanelContainer = _tabs[key].get_node("Badge")
	badge.visible = n > 0
	(badge.get_child(0) as Label).text = str(n) if n < 100 else "99+"


func _switch(key: String, initial := false) -> void:
	if key == "guild" and _guild_channel == "":
		mode = "guild"
		_style_tabs()
		_clear()
		_status.text = "Вы пока не в гильдии."
		var b := UI.button("Найти гильдию", "primary", 0, 90)
		b.pressed.connect(func(): main.open("guild"))
		_list.add_child(b)
		_input_row.visible = false
		return
	_input_row.visible = true
	if key == "dm_list":
		mode = "dm_list"
		_style_tabs()
		_render_dm_list()
		return
	if key == "channels":
		mode = "channels"
		_style_tabs()
		_render_chan_list()
		return
	if key == "chan" or (initial and mode == "chan"):
		mode = "chan"
		_style_tabs()
		_open_channel(channel)
		return
	if key == "dm" or (initial and mode == "dm"):
		mode = "dm"
	else:
		mode = key
		channel = "global" if key == "global" else _guild_channel
	_style_tabs()
	_open_channel(channel)


func _open_dm_target(uid: String, name: String) -> void:
	_dm_user = uid
	_dm_name = name
	var ids := [Api.user_id, uid]
	ids.sort()
	channel = "dm:%s:%s" % [ids[0], ids[1]]
	mode = "dm"


func _render_chan_list() -> void:
	_clear()
	_input_row.visible = false
	_status.text = "Каналы: объявления, ваш регион (где стоит караван), текущее событие, союз гильдий и круг друзей."
	var any := false
	for c in _channels:
		if not c.has("kind"):
			continue
		any = true
		var row := Button.new()
		row.custom_minimum_size = Vector2(0, 100)
		row.focus_mode = Control.FOCUS_NONE
		var sb := UI._flat(Color(0.03, 0.1, 0.12, 0.9), Color(TEAL, 0.5), 18, 2)
		for st in ["normal", "hover", "pressed"]:
			row.add_theme_stylebox_override(st, sb)
		var h := HBoxContainer.new()
		h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		h.offset_left = 20
		h.offset_right = -20
		h.add_theme_constant_override("separation", 14)
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ic := GameIcon.new()
		ic.kind = {"news": "bell", "region": "world", "event": "chat", "alliance": "guild", "group": "chat"}.get(String(c.kind), "chat")
		ic.custom_minimum_size = Vector2(60, 60)
		ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(ic)
		var nm := UI.label(String(c.name), 30, NAME_C, true)
		nm.mouse_filter = Control.MOUSE_FILTER_IGNORE
		nm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		nm.clip_text = true
		h.add_child(nm)
		if int(c.get("unread", 0)) > 0:
			h.add_child(UI.label("%d новых" % int(c.unread), 24, Color("#ff8a7a"), true))
		row.add_child(h)
		var ch: String = c.channel
		row.pressed.connect(func():
			channel = ch
			_switch("chan"))
		_list.add_child(row)
	if not any:
		_list.add_child(UI.label("Дополнительных каналов пока нет.", 28, Color("#9fb7b4")))


func _render_dm_list() -> void:
	_clear()
	_input_row.visible = false
	_status.text = "Личные сообщения. Начать разговор можно из профиля игрока или из списка друзей."
	var any := false
	for c in _channels:
		if not String(c.channel).begins_with("dm:"):
			continue
		any = true
		var row := Button.new()
		row.custom_minimum_size = Vector2(0, 110)
		row.focus_mode = Control.FOCUS_NONE
		var sb := UI._flat(Color(0.03, 0.1, 0.12, 0.9), Color(TEAL, 0.5), 18, 2)
		for st in ["normal", "hover", "pressed"]:
			row.add_theme_stylebox_override(st, sb)
		var h := HBoxContainer.new()
		h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		h.offset_left = 20
		h.offset_right = -20
		h.add_theme_constant_override("separation", 14)
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ic := GameIcon.new()
		ic.kind = "mail"
		ic.custom_minimum_size = Vector2(64, 64)
		ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(ic)
		var nm := UI.label(String(c.name), 32, NAME_C, true)
		nm.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(nm)
		if c.get("is_ai", false):
			var b := UI.ai_badge()
			b.mouse_filter = Control.MOUSE_FILTER_IGNORE
			h.add_child(b)
		h.add_child(UI.expand())
		if int(c.get("unread", 0)) > 0:
			h.add_child(UI.label("%d новых" % int(c.unread), 24, Color("#ff8a7a"), true))
		row.add_child(h)
		var ch: String = c.channel
		var uid: String = c.get("user_id", "")
		var name: String = c.name
		row.pressed.connect(func():
			_open_dm_target(uid, name)
			_switch("dm"))
		_list.add_child(row)
	if not any:
		_list.add_child(UI.label("Пока нет личных переписок.", 28, Color("#9fb7b4")))


func _clear() -> void:
	_last_id = 0
	_rows.clear()
	for c in _list.get_children():
		c.queue_free()


func _open_channel(ch: String) -> void:
	channel = ch
	_clear()
	_input_row.visible = ch != "news"
	if ch == "global":
		_status.text = ""
	elif ch.begins_with("guild:"):
		_status.text = "Чат вашей гильдии"
	elif ch.begins_with("dm:"):
		_status.text = "Личная переписка: " + _dm_name
	else:
		var info := _find_channel(ch)
		_status.text = String(info.get("name", "Канал")) + (" · пишет только администрация" if ch == "news" else "")
	await _poll()
	_to_bottom()


func _poll() -> void:
	if not is_inside_tree() or mode == "dm_list" or mode == "channels" or (mode == "guild" and _guild_channel == ""):
		return
	_busy = true
	var path := "/chat/messages?channel=%s" % channel.uri_encode()
	if _last_id > 0:
		path += "&after=%d" % _last_id
	var r := await Api.get_json(path)
	_busy = false
	if not r.ok or not is_inside_tree():
		return
	var at_bottom := _scroll.scroll_vertical >= int(_scroll.get_v_scroll_bar().max_value - _scroll.size.y - 80)
	for m in r.data.messages:
		if String(m.channel) != channel:
			continue
		_add(m)
		_last_id = max(_last_id, int(m.id))
	if r.data.messages.size() > 0 and at_bottom:
		_to_bottom()


func _to_bottom() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	if is_instance_valid(_scroll):
		_scroll.scroll_vertical = int(_scroll.get_v_scroll_bar().max_value)


# ------------------------------------------------------------------ message rows
func _add(m: Dictionary) -> void:
	if _rows.has(int(m.id)):
		return
	var row: Control = _event_card(m) if m.get("system", false) else _message_row(m)
	_list.add_child(row)
	_rows[int(m.id)] = row
	while _list.get_child_count() > MAX_ROWS:  # keep the screen light: drop the oldest rows
		var old := _list.get_child(0)
		_list.remove_child(old)
		old.queue_free()


func _avatar(m: Dictionary) -> Control:
	var a: Dictionary = m.author
	var box := Control.new()
	box.custom_minimum_size = Vector2(128, 128)
	var ring := Panel.new()
	var rsb := UI._flat(Color(0.05, 0.12, 0.13), GOLD_C, 64, 4)
	rsb.shadow_color = Color(0, 0, 0, 0.5)
	rsb.shadow_size = 6
	ring.add_theme_stylebox_override("panel", rsb)
	ring.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(ring)
	var tr := TextureRect.new()
	tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	tr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	tr.offset_left = 6
	tr.offset_top = 6
	tr.offset_right = -6
	tr.offset_bottom = -6
	var mat := ShaderMaterial.new()
	mat.shader = CIRCLE
	tr.material = mat
	tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(tr)
	_load_portrait(tr, String(a.get("avatar_hero", "azamat")))
	var ring_t := _tex("avatar_ring.png")
	if ring_t:
		ring.visible = false
		var rt := TextureRect.new()
		rt.texture = ring_t
		rt.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		rt.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		rt.mouse_filter = Control.MOUSE_FILTER_IGNORE
		box.add_child(rt)
	var lv := PanelContainer.new()
	var lsb := UI._flat(Color("#2a1d08"), GOLD_C, 22, 3)
	lsb.content_margin_left = 8
	lsb.content_margin_right = 8
	lv.add_theme_stylebox_override("panel", lsb)
	lv.add_child(UI.label(str(int(a.get("level", 1))), 24, Color("#fff1c9"), true))
	lv.position = Vector2(2, 86)
	lv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(lv)
	var btn := Button.new()
	btn.flat = true
	btn.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	btn.focus_mode = Control.FOCUS_NONE
	var uid: String = a.user_id
	btn.pressed.connect(func(): PlayerPopup.open(self, uid, main))
	box.add_child(btn)
	return box


func _load_portrait(tr: TextureRect, code: String) -> void:
	var tex: Texture2D = await Models.portrait(code, 160)
	if is_instance_valid(tr):
		tr.texture = tex


func _message_row(m: Dictionary) -> Control:
	var a: Dictionary = m.author
	var mine: bool = m.get("mine", false)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	row.add_child(_avatar(m))
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.custom_minimum_size.x = 200
	col.add_theme_constant_override("separation", 6)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 10)
	var nb := Button.new()
	nb.text = String(a.nickname)
	nb.flat = true
	nb.focus_mode = Control.FOCUS_NONE
	nb.add_theme_font_override("font", UI.FONT_BOLD)
	nb.add_theme_font_size_override("font_size", 32)
	nb.add_theme_color_override("font_color", GOLD_C if mine else NAME_C)
	nb.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	nb.add_theme_constant_override("outline_size", 6)
	var uid: String = a.user_id
	nb.pressed.connect(func(): PlayerPopup.open(self, uid, main))
	head.add_child(nb)
	if a.get("is_ai", false):
		head.add_child(UI.ai_badge())
	if String(a.get("guild_tag", "")) != "":
		var gi := GameIcon.new()
		gi.kind = "guild"
		gi.custom_minimum_size = Vector2(34, 34)
		gi.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		head.add_child(gi)
		head.add_child(UI.label(String(a.get("guild_name", a.guild_tag)), 26, Color("#bcd2d0")))
	col.add_child(head)
	var bubble_row := HBoxContainer.new()
	bubble_row.add_theme_constant_override("separation", 10)
	var bubble := PanelContainer.new()
	var bsb := UI._flat(Color(0.05, 0.13, 0.15, 0.94) if not mine else Color(0.2, 0.15, 0.06, 0.94),
		Color(TEAL, 0.55) if not mine else Color(GOLD_C, 0.8), 22, 2)
	bsb.content_margin_left = 22
	bsb.content_margin_right = 22
	bsb.content_margin_top = 14
	bsb.content_margin_bottom = 14
	bsb.corner_radius_top_left = 6
	var tex_b := _tex_style("bubble_mine.png" if mine else "bubble.png", 28)
	bubble.add_theme_stylebox_override("panel", tex_b if tex_b else bsb)
	bubble.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var bv := VBoxContainer.new()
	bv.add_theme_constant_override("separation", 8)
	var t := UI.label(String(m.text), 31, TEXT_C)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bv.add_child(t)
	var rr := HBoxContainer.new()
	rr.add_theme_constant_override("separation", 6)
	_fill_reactions(rr, m)
	bv.add_child(rr)
	bubble.add_child(bv)
	bubble_row.add_child(bubble)
	var time_l := UI.label(UI.local_time(String(m.at)), 24, Color("#9fb7b4"))
	time_l.size_flags_vertical = Control.SIZE_SHRINK_END
	bubble_row.add_child(time_l)
	col.add_child(bubble_row)
	row.add_child(col)
	return row


func _event_card(m: Dictionary) -> Control:
	var text := String(m.text)
	var target := ""
	var low := text.to_lower()
	if "босс" in low or "рейд" in low:
		target = "raids"
	elif "турнир" in low:
		target = "tournaments"
	elif "событие" in low:
		target = "events"
	elif "гильди" in low:
		target = "guild"
	var card := PanelContainer.new()
	var sb := UI._flat(Color(0.04, 0.14, 0.15, 0.97), Color(TEAL, 0.8), 14, 2)
	sb.content_margin_left = 20
	sb.content_margin_right = 20
	sb.content_margin_top = 16
	sb.content_margin_bottom = 16
	sb.shadow_color = Color(0.2, 0.9, 0.85, 0.18)
	sb.shadow_size = 10
	card.add_theme_stylebox_override("panel", sb)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 16)
	var ic := GameIcon.new()
	ic.kind = "arena"
	ic.custom_minimum_size = Vector2(80, 80)
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	h.add_child(ic)
	var art := _tex("event_" + target + ".png") if target != "" else null
	if art:
		var at := TextureRect.new()
		at.texture = art
		at.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		at.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		at.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		at.modulate = Color(1, 1, 1, 0.45)
		at.mouse_filter = Control.MOUSE_FILTER_IGNORE
		card.add_child(at)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.custom_minimum_size.x = 200
	col.add_child(UI.label("[Событие]", 28, GOLD_C, true))
	var l := UI.label(text, 30, TEXT_C)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(l)
	h.add_child(col)
	var right := VBoxContainer.new()
	right.alignment = BoxContainer.ALIGNMENT_CENTER
	right.add_child(UI.label(UI.local_time(String(m.at)), 22, Color("#9fb7b4")))
	if target != "":
		var go := UI.button("Перейти »", "primary", 0, 80)
		go.add_theme_font_size_override("font_size", 28)
		go.pressed.connect(func(): main.open(target))
		right.add_child(go)
	h.add_child(right)
	card.add_child(h)
	return card


func _fill_reactions(rr: HBoxContainer, m: Dictionary) -> void:
	for c in rr.get_children():
		c.queue_free()
	var reacts: Dictionary = m.get("reactions", {})
	for e in reacts:
		var b := UI.button("%s %d" % [e, int(reacts[e].count)], "primary" if reacts[e].mine else "dim", 0, 56)
		b.add_theme_font_size_override("font_size", 24)
		var emo: String = e
		b.pressed.connect(func(): _react(int(m.id), emo, rr, m))
		rr.add_child(b)
	var more := UI.button("…", "dim", 64, 56)
	more.add_theme_font_size_override("font_size", 26)
	more.pressed.connect(func(): _menu(rr, m))
	rr.add_child(more)


func _menu(rr: HBoxContainer, m: Dictionary) -> void:
	for c in rr.get_children():
		c.queue_free()
	for e in _reactions:
		var b := UI.button(String(e), "glass", 68, 56)
		b.add_theme_font_size_override("font_size", 26)
		var emo: String = e
		b.pressed.connect(func(): _react(int(m.id), emo, rr, m))
		rr.add_child(b)
	if not m.get("mine", false):
		var rep := UI.button("Жалоба", "dim", 0, 56)
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
	if text == "" or mode == "dm_list" or mode == "channels" or channel == "news":
		return
	var body := {"text": text}
	if mode == "dm" and _dm_user != "":
		body["to_user"] = _dm_user
	else:
		body["channel"] = channel
	var r := await Api.post_json("/chat/send", body)
	if not r.ok:
		Router.error(r)
		return
	_entry.text = ""
	_emoji_panel.visible = false
	_add(r.data.message)  # the poll cursor is not moved: earlier messages from others still arrive
	_to_bottom()
	Sfx.play("click")
