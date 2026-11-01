extends Node
## Boot: content manifest check -> login (stored session, or choice: new guest / email) -> bootstrap -> Main.

const HubWorld := preload("res://src/world/HubWorld.gd")

var _status: Label
var _retry: Button
var _bar: ProgressBar
var _url_row: HBoxContainer
var _url_edit: LineEdit
var _ui: Control
var _pv: VBoxContainer
var _login_box: VBoxContainer
var _email: LineEdit
var _pw: LineEdit


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
	var bg_art := UI.art("ui/boot_bg.png")
	if bg_art:
		var bgr := TextureRect.new()
		bgr.texture = bg_art
		bgr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		bgr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		bgr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_ui.add_child(bgr)
		_ui.move_child(bgr, 0)
	var logo_art := UI.art("ui/logo.png")
	if logo_art:
		var lt := TextureRect.new()
		lt.texture = logo_art
		lt.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		lt.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		lt.custom_minimum_size = Vector2(0, 300)
		v.add_child(lt)
	else:
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
	_bar = UI.bar(0, 1, UI.GOLD, 22)
	_bar.visible = false
	pv.add_child(_bar)
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
	_build_login(pv)
	panel.add_child(pv)
	v.add_child(panel)
	Sfx.music("hub")
	_run()


func _run() -> void:
	_retry.visible = false
	_url_row.visible = false
	_status.text = "Проверяем обновления контента…"
	var c := await Content.check()
	if not c.ok and c.status == "client_update_required":
		_fail(c.message)
		var shown: bool = await load("res://src/ui/UpdateDialog.gd").check(_ui)
		if not shown:
			_status.text = "Требуется новая версия приложения. Скачайте её: %s/download" % Config.server_url
		return
	if not c.ok and c.status == "signature_invalid":
		_fail(c.message)
		return
	if not c.ok:
		_fail("Нет связи с сервером %s\nПроверьте сеть или адрес сервера." % Config.server_url)
		return
	if c.status == "ok" and c.missing_required.size() > 0:
		# required packages block entry; optional ones are downloaded in the background later
		var total := Content.bytes_to_download(c.missing_required)
		_bar.visible = true
		var cb := func(done: int, t: int):
			_bar.max_value = max(t, 1)
			_bar.value = done
			_status.text = "Загрузка ресурсов: %.1f / %.1f МБ" % [done / 1048576.0, t / 1048576.0]
		Content.progress.connect(cb)
		_status.text = "Загрузка ресурсов: 0 / %.1f МБ" % (total / 1048576.0)
		var s := await Content.sync(true)
		Content.progress.disconnect(cb)
		_bar.visible = false
		if not s.ok:
			_fail(s.get("message", "Не удалось загрузить ресурсы"))
			return
	if Content.missing(false).is_empty() and not Content.up_to_date():
		Content.pending = Content._set_from_manifest()
	_status.text = "Вход в Крепость хранителей…"
	var r := await Api.login()
	if not r.ok and r.code == "need_login":
		if _auto_guest():
			r = await Api.login_guest()
		else:
			_show_login()
			return
	if not r.ok:
		_fail("Не удалось войти: %s" % r.message)
		return
	await _enter()


func _enter() -> void:
	_login_box.visible = false
	_status.text = "Загружаем прогресс с сервера…"
	var b := await Game.bootstrap()
	if not b.ok:
		_fail("Не удалось загрузить профиль: %s" % b.message)
		return
	await Content.apply_pending()  # safe point: nothing from packages is on screen yet
	Router.goto(Router.MAIN, {"screen": "home"})


func _fail(msg: String) -> void:
	_login_box.visible = false
	_status.text = msg
	_retry.visible = true
	_url_edit.text = Config.server_url
	_url_row.visible = true


## Dev E2E runs start from a fresh guest without the login choice.
func _auto_guest() -> bool:
	for k in ["URALIA_E2E", "URALIA_E2E_SHOP", "URALIA_E2E_UPDATE", "URALIA_E2E_SOCIAL", "URALIA_E2E_ONLINE", "URALIA_E2E_ART"]:
		if OS.get_environment(k) != "":
			return true
	return false


func _build_login(pv: VBoxContainer) -> void:
	_login_box = VBoxContainer.new()
	_login_box.add_theme_constant_override("separation", 14)
	_login_box.visible = false
	var guest := UI.button("Начать новую игру", "primary", 0, 110)
	guest.pressed.connect(_guest)
	_login_box.add_child(guest)
	var or_l := UI.label("или войдите в аккаунт с привязанным email", 28, UI.TEXT)
	or_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	or_l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_login_box.add_child(or_l)
	_email = LineEdit.new()
	_email.placeholder_text = "email"
	_email.virtual_keyboard_type = LineEdit.KEYBOARD_TYPE_EMAIL_ADDRESS
	_email.custom_minimum_size = Vector2(0, 96)
	_email.add_theme_font_size_override("font_size", 32)
	_login_box.add_child(_email)
	_pw = LineEdit.new()
	_pw.placeholder_text = "пароль"
	_pw.secret = true
	_pw.virtual_keyboard_type = LineEdit.KEYBOARD_TYPE_PASSWORD
	_pw.custom_minimum_size = Vector2(0, 96)
	_pw.add_theme_font_size_override("font_size", 32)
	_pw.text_submitted.connect(func(_t: String): _email_login())
	_login_box.add_child(_pw)
	var lb := UI.button("Войти по email", "glass", 0, 110)
	lb.pressed.connect(_email_login)
	_login_box.add_child(lb)
	pv.add_child(_login_box)


func _show_login() -> void:
	_status.text = "Добро пожаловать, хранитель!"
	_login_box.visible = true


func _guest() -> void:
	_login_box.visible = false
	_status.text = "Создаём нового хранителя…"
	var r := await Api.login_guest()
	if not r.ok:
		_fail("Не удалось войти: %s" % r.message)
		return
	await _enter()


func _email_login() -> void:
	if _email.text.strip_edges() == "" or _pw.text == "":
		_status.text = "Введите email и пароль"
		return
	_status.text = "Входим…"
	var r := await Api.login_email(_email.text, _pw.text)
	if not r.ok:
		_status.text = r.message if r.status == 401 else "Не удалось войти: %s" % r.message
		return
	_pw.text = ""
	await _enter()
