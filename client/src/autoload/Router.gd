extends Node
## Scene routing + global overlays (toasts, offline banner, blocking loader).

const MAIN := "res://src/scenes/Main.tscn"
const BATTLE := "res://src/scenes/Battle.tscn"
const BOOT := "res://src/scenes/Boot.tscn"

var params := {}
var _layer: CanvasLayer
var _toast_box: VBoxContainer
var _offline: PanelContainer
var _loader: Control
var _loader_count := 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_layer = CanvasLayer.new()
	_layer.layer = 90
	add_child(_layer)
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_layer.add_child(root)
	_toast_box = VBoxContainer.new()
	_toast_box.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_toast_box.position = Vector2(-460, 230)
	_toast_box.custom_minimum_size = Vector2(920, 0)
	_toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_box.add_theme_constant_override("separation", 12)
	root.add_child(_toast_box)
	_build_offline(root)
	_build_loader(root)
	Api.offline_changed.connect(_on_offline)
	if OS.get_environment("URALIA_E2E") != "" and ResourceLoader.exists("res://tools/E2E.gd"):
		add_child(load("res://tools/E2E.gd").new())  # dev-only UI test driver
	if OS.get_environment("URALIA_E2E_SHOP") != "" and ResourceLoader.exists("res://tools/E2EShop.gd"):
		add_child(load("res://tools/E2EShop.gd").new())
	if OS.get_environment("URALIA_E2E_ART") != "" and ResourceLoader.exists("res://tools/E2EArt.gd"):
		add_child(load("res://tools/E2EArt.gd").new())
	if OS.get_environment("URALIA_E2E_ONLINE") != "" and ResourceLoader.exists("res://tools/E2EOnline.gd"):
		add_child(load("res://tools/E2EOnline.gd").new())
	if OS.get_environment("URALIA_E2E_SOCIAL") != "" and ResourceLoader.exists("res://tools/E2ESocial.gd"):
		add_child(load("res://tools/E2ESocial.gd").new())
	if OS.get_environment("URALIA_E2E_UPDATE") != "" and ResourceLoader.exists("res://tools/E2EUpdate.gd"):
		add_child(load("res://tools/E2EUpdate.gd").new())
	Api.session_lost.connect(func(): toast("Сессия завершена. Выполняем повторный вход…", true); goto(BOOT))


func goto(scene: String, p := {}) -> void:
	params = p
	get_tree().change_scene_to_file(scene)


func toast(text: String, warn := false) -> void:
	var p := UI.glass_panel(Color("#ff9b7a") if warn else Color("#bfe3ff"))
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var l := UI.label(text, 34, Color.WHITE)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	p.add_child(l)
	_toast_box.add_child(p)
	p.modulate.a = 0.0
	var tw := p.create_tween()
	tw.tween_property(p, "modulate:a", 1.0, 0.2)
	tw.tween_interval(2.4)
	tw.tween_property(p, "modulate:a", 0.0, 0.4)
	tw.tween_callback(p.queue_free)


func error(r: Dictionary) -> void:
	if r.get("status", 0) == 0:
		return  # offline banner already explains it
	toast(r.get("message", "Ошибка"), true)


func _build_offline(root: Control) -> void:
	_offline = UI.glass_panel(Color("#ff7a7a"))
	_offline.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_offline.position = Vector2(-470, -420)
	_offline.custom_minimum_size = Vector2(940, 0)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 24)
	var l := UI.label("Нет связи с Крепостью. Прогресс хранится на сервере — ничего не потеряно.", 30)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(l)
	var b := UI.button("Повторить", "primary", 200)
	b.pressed.connect(_retry)
	row.add_child(b)
	_offline.add_child(row)
	_offline.visible = false
	root.add_child(_offline)


func _retry() -> void:
	var r := await Api.get_json("/player/me")
	if r.ok:
		Game.set_wallet(r.data.wallet)
		toast("Соединение восстановлено")


func _on_offline(is_off: bool) -> void:
	_offline.visible = is_off


func _build_loader(root: Control) -> void:
	_loader = ColorRect.new()
	(_loader as ColorRect).color = Color(0, 0, 0, 0.35)
	_loader.set_anchors_preset(Control.PRESET_FULL_RECT)
	_loader.mouse_filter = Control.MOUSE_FILTER_STOP
	var l := UI.label("…", 72, Color("#ffe6a8"))
	l.set_anchors_preset(Control.PRESET_CENTER)
	l.position = Vector2(-40, -60)
	_loader.add_child(l)
	_loader.visible = false
	root.add_child(_loader)


func busy(on: bool) -> void:
	_loader_count = max(0, _loader_count + (1 if on else -1))
	_loader.visible = _loader_count > 0
