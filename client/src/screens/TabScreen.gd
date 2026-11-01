extends Control
## Base for social screens: glass panel, title, optional header buttons, tab row and a scrolled body.
## Subclasses set `title_text`, `tabs` and implement `_render_tab(tab)`.

const PlayerPopup := preload("res://src/ui/PlayerPopup.gd")

var main: Node
var tab := ""
var title_text := ""
var tabs: Array = []  # [[key, caption], ...]
var _tab_row: HBoxContainer
var _body: VBoxContainer
var _head: HBoxContainer
var _gen := 0  # render generation: async renders that finish late are dropped


func setup(m: Node, p: Dictionary) -> void:
	main = m
	main.use_world("none")
	if tab == "" and tabs.size() > 0:
		tab = tabs[0][0]
	tab = String(p.get("tab", tab))
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
	_head = HBoxContainer.new()
	_head.add_theme_constant_override("separation", 10)
	_head.add_child(UI.title(title_text, 46))
	_head.add_child(UI.expand())
	v.add_child(_head)
	if tabs.size() > 0:
		var sc := ScrollContainer.new()
		sc.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		sc.custom_minimum_size = Vector2(0, 86)
		_tab_row = HBoxContainer.new()
		_tab_row.add_theme_constant_override("separation", 8)
		sc.add_child(_tab_row)
		v.add_child(sc)
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_body))
	UI.keep_wrapped(_body)
	_extra_setup(p)
	render()


func _extra_setup(_p: Dictionary) -> void:
	pass


func head_button(text: String, cb: Callable) -> void:
	var b := UI.button(text, "glass", 0, 80)
	b.add_theme_font_size_override("font_size", 28)
	b.pressed.connect(cb)
	_head.add_child(b)


func render() -> void:
	_gen += 1
	if _tab_row:
		for c in _tab_row.get_children():
			c.queue_free()
		for t in tabs:
			var b := UI.button(String(t[1]), "primary" if t[0] == tab else "glass", 0, 78)
			b.add_theme_font_size_override("font_size", 27)
			var key: String = t[0]
			b.pressed.connect(func(): tab = key; render())
			_tab_row.add_child(b)
	for c in _body.get_children():
		c.queue_free()
	_render_tab(tab)


func alive(gen: int) -> bool:
	return is_inside_tree() and gen == _gen


func _render_tab(_t: String) -> void:
	pass


# ------------------------------------------------------------------ small widgets
func add(c: Control) -> Control:
	_body.add_child(c)
	return c


func h1(text: String) -> Label:
	return add(UI.label(text, 32, UI.ACCENT, true))


func txt(text: String, size := 26, color := UI.TEXT) -> Label:
	var l := UI.label(text, size, color)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return add(l)


func card(border := Color(1, 1, 1, 0.18)) -> Dictionary:
	var pc := PanelContainer.new()
	var sb := UI._flat(Color(0.02, 0.03, 0.07, 0.55), border, 22, 2)
	sb.content_margin_left = 18
	sb.content_margin_right = 18
	sb.content_margin_top = 12
	sb.content_margin_bottom = 12
	pc.add_theme_stylebox_override("panel", sb)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.custom_minimum_size.x = 200
	h.add_child(info)
	pc.add_child(h)
	_body.add_child(pc)
	return {"card": pc, "row": h, "info": info}


func line_to(box: VBoxContainer, text: String, size := 26, color := UI.TEXT, bold := false) -> Label:
	var l := UI.label(text, size, color, bold)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(l)
	return l


func btn(box: Container, text: String, style: String, cb: Callable, w := 0) -> Button:
	var b := UI.button(text, style, w, 80)
	b.add_theme_font_size_override("font_size", 28)
	b.pressed.connect(cb)
	box.add_child(b)
	return b


func name_button(box: Container, nick: String, user_id: String, is_ai: bool, color := UI.GOLD) -> void:
	var nr := HBoxContainer.new()
	nr.add_theme_constant_override("separation", 8)
	var nb := Button.new()
	nb.text = nick
	nb.flat = true
	nb.focus_mode = Control.FOCUS_NONE
	nb.add_theme_font_override("font", UI.FONT_BOLD)
	nb.add_theme_font_size_override("font_size", 29)
	nb.add_theme_color_override("font_color", color)
	nb.pressed.connect(func(): PlayerPopup.open(self, user_id, main))
	nr.add_child(nb)
	if is_ai:
		nr.add_child(UI.ai_badge())
	box.add_child(nr)


## POST with an idempotency key; toasts the error and returns {} on failure.
func act(path: String, body := {}, ok_text := "") -> Dictionary:
	var r := await Api.post_json(path, body, true)
	if not r.ok:
		Router.error(r)
		return {}
	if r.data.has("wallet"):
		Game.set_wallet(r.data.wallet)
	if ok_text != "":
		Router.toast(ok_text)
	return r.data


func get_data(path: String) -> Dictionary:
	var r := await Api.get_json(path)
	if not r.ok:
		Router.error(r)
		return {}
	return r.data


## Plays a server-computed battle in the battle scene and returns here afterwards.
func play_battle(sim: Dictionary, title: String, back: String, lines: Array, rewards := {}, is_boss := false,
		back_params := {}, result_title := "") -> void:
	var p := {"sim": sim, "title": title, "back": back, "lines": lines, "rewards": rewards, "is_boss": is_boss,
		"territory": "dungeons", "back_params": back_params}
	if result_title != "":
		p["result_title"] = result_title
	Router.goto(Router.BATTLE, p)


func countdown(iso: String) -> String:
	if iso.length() < 19:
		return ""
	var t := Time.get_unix_time_from_datetime_string(iso.substr(0, 19)) - Time.get_unix_time_from_system()
	if t <= 0:
		return "завершено"
	var d := int(t / 86400)
	var h := int(fmod(t, 86400) / 3600)
	var m := int(fmod(t, 3600) / 60)
	return ("%d д %d ч" % [d, h]) if d > 0 else ("%d ч %d мин" % [h, m])
