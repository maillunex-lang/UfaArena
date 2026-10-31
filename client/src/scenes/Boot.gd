extends Node
## Boot: content manifest check -> login (refresh token or new guest) -> bootstrap -> Main.

const HubWorld := preload("res://src/world/HubWorld.gd")

var _status: Label
var _retry: Button
var _url_row: HBoxContainer
var _url_edit: LineEdit
var _ui: Control


func _ready() -> void:
	var w: Node3D = HubWorld.new()
	add_child(w)
	w.show_hero("aigul")
	var layer := CanvasLayer.new()
	add_child(layer)
	_ui = Control.new()
	_ui.theme = UI.theme()
	_ui.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(_ui)
	var v := VBoxContainer.new()
	v.set_anchors_preset(Control.PRESET_FULL_RECT)
	v.offset_top = 260
	v.offset_bottom = -200
	v.add_theme_constant_override("separation", 10)
	_ui.add_child(v)
	var t := UI.title("УРАЛИЯ", 132)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
	var st := UI.label("ДЫХАНИЕ ПРЕДКОВ", 50, Color("#e6f2ff"), true)
	st.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(st)
	v.add_child(UI.expand())
	var panel := UI.glass_panel()
	panel.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	panel.custom_minimum_size = Vector2(860, 0)
	var pv := VBoxContainer.new()
	pv.add_theme_constant_override("separation", 14)
	_status = UI.label("Пробуждаем духов предков…", 32)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	pv.add_child(_status)
	_retry = UI.button("Повторить", "primary")
	_retry.visible = false
	_retry.pressed.connect(_run)
	pv.add_child(_retry)
	_url_row = HBoxContainer.new()
	_url_row.add_theme_constant_override("separation", 10)
	_url_edit = LineEdit.new()
	_url_edit.text = Config.server_url
	_url_edit.custom_minimum_size = Vector2(0, 90)
	_url_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_url_edit.add_theme_font_size_override("font_size", 28)
	_url_row.add_child(_url_edit)
	var save := UI.button("Сохранить", "glass", 240, 90)
	save.pressed.connect(func():
		Config.server_url = _url_edit.text.strip_edges().trim_suffix("/")
		Config.save()
		_run())
	_url_row.add_child(save)
	_url_row.visible = false
	pv.add_child(_url_row)
	panel.add_child(pv)
	v.add_child(panel)
	Sfx.music("hub")
	_run()


func _run() -> void:
	_retry.visible = false
	_url_row.visible = false
	_status.text = "Проверяем обновления контента…"
	var c := await ContentUpdater.run()
	if not c.ok and c.status in ["signature_invalid", "hash_mismatch", "client_update_required"]:
		_fail(c.message)
		return
	if not c.ok:
		_fail("Нет связи с сервером %s\nПроверьте сеть или адрес сервера." % Config.server_url)
		return
	_status.text = "Вход в Крепость хранителей…"
	var r := await Api.login()
	if not r.ok:
		_fail("Не удалось войти: %s" % r.message)
		return
	_status.text = "Загружаем прогресс с сервера…"
	var b := await Game.bootstrap()
	if not b.ok:
		_fail("Не удалось загрузить профиль: %s" % b.message)
		return
	Router.goto(Router.MAIN, {"screen": "home"})


func _fail(msg: String) -> void:
	_status.text = msg
	_retry.visible = true
	_url_edit.text = Config.server_url
	_url_row.visible = true
