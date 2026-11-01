extends Control
## "A new APK is available" window: version, what's new, and a button that opens the download page.
## A required update (client below the server minimum) cannot be dismissed.

var info := {}


## Asks the server; shows the window when a newer APK exists (once per version unless required).
static func check(parent: Node, manual := false) -> bool:
	var r := await Api.get_json("/client/release?version=" + Config.CLIENT_VERSION)
	if not r.ok or not is_instance_valid(parent):
		if manual:
			Router.toast("Не удалось проверить обновления", true)
		return false
	var d: Dictionary = r.data
	if not d.get("update_available", false) and not d.get("required", false):
		if manual:
			Router.toast("У вас последняя версия %s" % Config.CLIENT_VERSION)
		return false
	if not manual and not d.get("required", false) and String(Config.settings.get("update_dismissed", "")) == String(d.latest):
		return false
	var w: Control = load("res://src/ui/UpdateDialog.gd").new()
	w.info = d
	parent.add_child(w)
	return true


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var required: bool = info.get("required", false)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.7)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var panel := UI.solid_panel(Color("#ffe1a0"))
	panel.anchor_left = 0.5
	panel.anchor_right = 0.5
	panel.anchor_top = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -470
	panel.offset_right = 470
	panel.offset_top = -340
	panel.offset_bottom = 340
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 18)
	panel.add_child(v)
	var t := UI.title("Вышло обновление %s" % String(info.get("latest", "")), 50)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(t)
	if String(info.get("title", "")) != "":
		var st := UI.label(String(info.title), 32, UI.ACCENT, true)
		st.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(st)
	for n in info.get("notes", []):
		var l := UI.label("• " + String(n), 30, UI.TEXT)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(l)
	var cur := UI.label("Ваша версия: %s%s" % [Config.CLIENT_VERSION,
		"\nЭта версия больше не поддерживается сервером — установите обновление." if required else ""], 26, UI.MUTED)
	cur.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(cur)
	var hint := UI.label("Прогресс хранится на сервере и не потеряется. Привяжите email в настройках, чтобы войти после переустановки.", 24, UI.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(hint)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 16)
	var dl := UI.button("Скачать", "primary", 0, 110)
	dl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	dl.disabled = info.get("url") == null
	dl.pressed.connect(func(): OS.shell_open(String(info.url)))
	row.add_child(dl)
	if not required:
		var later := UI.button("Позже", "glass", 280, 110)
		later.pressed.connect(func():
			Config.settings["update_dismissed"] = String(info.get("latest", ""))
			Config.save()
			queue_free())
		row.add_child(later)
	v.add_child(row)
