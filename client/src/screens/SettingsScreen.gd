extends Control
## Settings, grouped: Аккаунт · Графика и производительность · Звук · Интерфейс и доступность · Уведомления ·
## ИИ-жители · Данные и обновления · О игре. Every control changes a real setting (Config.settings, saved to
## user://settings.cfg) or calls a real server endpoint.

var main: Node
var _v: VBoxContainer


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("none")
	_v = VBoxContainer.new()
	_v.add_theme_constant_override("separation", UI.SP.m)
	var sc := UI.scroll(_v)
	sc.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	sc.offset_left = UI.SP.m
	sc.offset_right = -UI.SP.m
	sc.offset_top = UI.SP.s
	add_child(sc)
	UI.keep_wrapped(_v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Настройки", UI.FS.h1))
	head.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 180, 80)
	back.pressed.connect(func(): main.open("more"))
	head.add_child(back)
	_v.add_child(head)
	_account()
	_graphics()
	_sound()
	_interface()
	_notifications()
	_ai()
	_data()
	_about()
	_v.add_child(UI.spacer(UI.SP.xl))


# ------------------------------------------------------------------ helpers
func _group(title: String) -> VBoxContainer:
	_v.add_child(UI.section(title))
	var c := UI.card(UI.LINE)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", UI.SP.s)
	c.add_child(box)
	_v.add_child(c)
	return box


func _note(box: Container, text: String) -> void:
	var l := UI.label(text, UI.FS.caption, UI.MUTED)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(l)


func _toggle(box: Container, text: String, key: String, after := Callable()) -> CheckButton:
	var cb := CheckButton.new()
	cb.text = text
	cb.button_pressed = bool(Config.settings.get(key, false))
	cb.add_theme_font_size_override("font_size", UI.FS.body)
	cb.add_theme_color_override("font_color", UI.TEXT)
	cb.add_theme_color_override("font_pressed_color", UI.TEXT)
	cb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cb.custom_minimum_size.y = 72
	cb.toggled.connect(func(on: bool):
		_save(key, on)
		if after.is_valid():
			after.call())
	box.add_child(cb)
	return cb


## Segmented choice: [[value, caption], ...]
func _choice(box: Container, items: Array, key: String, after := Callable()) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UI.SP.s)
	var cur = Config.settings.get(key)
	for it in items:
		var b := UI.button(String(it[1]), "primary" if str(cur) == str(it[0]) else "glass", 0, 80)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.add_theme_font_size_override("font_size", UI.FS.caption + 2)
		var val = it[0]
		b.pressed.connect(func():
			_save(key, val)
			if after.is_valid():
				after.call()
			main.open("settings"))
		row.add_child(b)
	box.add_child(row)


func _field(box: Container, placeholder: String, secret := false) -> LineEdit:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.secret = secret
	e.custom_minimum_size = Vector2(0, 88)
	e.add_theme_font_size_override("font_size", UI.FS.body)
	box.add_child(e)
	return e


func _save(key: String, val: Variant) -> void:
	Config.settings[key] = val
	Config.save()


# ------------------------------------------------------------------ account
func _account() -> void:
	var box := _group("Аккаунт")
	var p := Game.profile
	box.add_child(UI.label("%s · уровень %d" % [p.get("nickname", ""), int(p.get("level", 1))], UI.FS.body_l, UI.GOLD, true))
	box.add_child(UI.label("URALIA ID: %s" % p.get("uralia_id", "—"), UI.FS.body, UI.TEXT))
	var nick_row := HBoxContainer.new()
	nick_row.add_theme_constant_override("separation", UI.SP.s)
	var nick := LineEdit.new()
	nick.text = p.get("nickname", "")
	nick.max_length = 20
	nick.custom_minimum_size = Vector2(0, 88)
	nick.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nick.add_theme_font_size_override("font_size", UI.FS.body)
	nick_row.add_child(nick)
	var nb := UI.button("Сменить имя", "glass", 0, 88)
	nb.pressed.connect(func(): _nick(nick.text))
	nick_row.add_child(nb)
	box.add_child(nick_row)
	var linked := String(p.get("account_kind", "guest")) == "linked"
	if linked:
		box.add_child(UI.label("Вход по email: %s" % p.get("email_masked", ""), UI.FS.body, UI.TEXT))
		_note(box, "Прогресс хранится на сервере: войдите с этим email на любом устройстве — данные синхронизируются автоматически.")
		var rc := UI.button("Получить новый код восстановления", "glass", 0, 84)
		rc.pressed.connect(func(): _new_code(rc))
		box.add_child(rc)
		box.add_child(UI.label("Смена пароля", UI.FS.body, UI.ACCENT, true))
		var old := _field(box, "текущий пароль", true)
		var npw := _field(box, "новый пароль (от 8 символов)", true)
		var cp := UI.button("Сменить пароль", "glass", 0, 84)
		cp.pressed.connect(func(): _change_pw(old, npw, cp))
		box.add_child(cp)
	else:
		_note(box, "Гостевой аккаунт привязан к этому устройству. Привяжите email, чтобы не потерять прогресс и играть на нескольких устройствах.")
		var email := _field(box, "email")
		email.virtual_keyboard_type = LineEdit.KEYBOARD_TYPE_EMAIL_ADDRESS
		var pw := _field(box, "пароль (от 8 символов)", true)
		var lb := UI.button("Привязать email", "primary", 0, 88)
		lb.pressed.connect(func(): _link(email.text, pw.text, lb))
		box.add_child(lb)
	var sw := UI.button("Войти в другой аккаунт", "glass", 0, 84)
	sw.pressed.connect(func(): _logout())
	box.add_child(sw)


func _nick(n: String) -> void:
	var r := await Api.post_json("/player/nickname", {"nickname": n})
	if not r.ok:
		Router.error(r)
		return
	Game.profile["nickname"] = r.data.nickname
	Game.profile_changed.emit()
	Router.toast("Имя изменено")


func _show_code(code: String, title: String) -> void:
	UI.confirm(main.ui, title, "Ваш код восстановления:\n\n%s\n\nЗапишите его и храните в надёжном месте. Код нужен, чтобы восстановить доступ, если вы забудете пароль. Новый код отменяет предыдущий." % code,
		"Я записал", func(): pass)


func _link(email: String, pw: String, b: Button) -> void:
	UI.set_loading(b, true)
	var r := await Api.post_json("/auth/link", {"email": email.strip_edges(), "password": pw})
	UI.set_loading(b, false)
	if not r.ok:
		Router.error(r)
		return
	Game.profile["account_kind"] = "linked"
	var e := email.strip_edges()
	Game.profile["email_masked"] = e.substr(0, 2) + "***" + e.substr(e.find("@"))
	main.open("settings")
	_show_code(String(r.data.get("recovery_code", "")), "Email привязан")


func _new_code(b: Button) -> void:
	UI.confirm(main.ui, "Новый код восстановления", "Текущий код перестанет действовать. Продолжить?", "Получить", func():
		UI.set_loading(b, true)
		var r := await Api.post_json("/auth/recovery-code", {})
		UI.set_loading(b, false)
		if not r.ok:
			Router.error(r)
			return
		_show_code(String(r.data.recovery_code), "Новый код"))


func _change_pw(old: LineEdit, npw: LineEdit, b: Button) -> void:
	if npw.text.length() < 8:
		Router.toast("Новый пароль — от 8 символов", true)
		return
	UI.set_loading(b, true)
	var r := await Api.post_json("/auth/password", {"old_password": old.text, "new_password": npw.text})
	UI.set_loading(b, false)
	if not r.ok:
		Router.error(r)
		return
	old.text = ""
	npw.text = ""
	Router.toast("Пароль изменён. Другие устройства вышли из аккаунта")


func _logout() -> void:
	var guest := String(Game.profile.get("account_kind", "guest")) != "linked"
	var body := "Без привязанного email вернуться в этот гостевой аккаунт будет нельзя." if guest else "Вы сможете снова войти по email."
	UI.confirm(main.ui, "Выйти из аккаунта?", body, "Выйти", func():
		await Api.post_json("/auth/logout", {})
		Api.clear_session()
		Game.loaded = false
		Router.goto(Router.BOOT), guest)


# ------------------------------------------------------------------ graphics & performance
func _graphics() -> void:
	var box := _group("Графика и производительность")
	var q := String(Config.settings.graphics_quality)
	box.add_child(UI.label("Качество" + (" (авто: сейчас «%s»)" % _tier_name(Gfx.tier) if q == "auto" else ""), UI.FS.body, UI.TEXT, true))
	_choice(box, [["auto", "Авто"], ["low", "Низкое"], ["medium", "Среднее"], ["high", "Высокое"]], "graphics_quality", Gfx.apply)
	box.add_child(UI.label("Ограничение FPS", UI.FS.body, UI.TEXT, true))
	_choice(box, [[0, "По качеству"], [30, "30"], [60, "60"]], "fps_limit", Gfx.apply)
	_toggle(box, "Экономия батареи (30 FPS, низкое качество)", "battery_saver", Gfx.apply)
	_note(box, "Сейчас: %s · лимит %d FPS. Размытие стекла включается только на высоком качестве." % [_tier_name(Gfx.tier), Engine.max_fps])


func _tier_name(t: String) -> String:
	return {"low": "низкое", "medium": "среднее", "high": "высокое"}.get(t, t)


# ------------------------------------------------------------------ sound
func _sound() -> void:
	var box := _group("Звук")
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UI.SP.m)
	row.add_child(UI.label("Громкость", UI.FS.body, UI.TEXT, true))
	var sl := HSlider.new()
	sl.min_value = 0
	sl.max_value = 1
	sl.step = 0.05
	sl.value = float(Config.settings.get("master_volume", 0.8))
	sl.custom_minimum_size = Vector2(0, 72)
	sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var pct := UI.label("%d%%" % int(sl.value * 100), UI.FS.body, UI.MUTED)
	pct.custom_minimum_size.x = 90
	sl.value_changed.connect(func(val: float):
		_save("master_volume", val)
		pct.text = "%d%%" % int(val * 100)
		Sfx.apply_volume())
	row.add_child(sl)
	row.add_child(pct)
	box.add_child(row)
	_toggle(box, "Музыка", "music_on", Sfx.apply_volume)
	_toggle(box, "Звуковые эффекты", "sfx_on", Sfx.apply_volume)


# ------------------------------------------------------------------ interface & accessibility
func _interface() -> void:
	var box := _group("Интерфейс и доступность")
	box.add_child(UI.label("Масштаб интерфейса", UI.FS.body, UI.TEXT, true))
	_choice(box, [[0.9, "Компактный"], [1.0, "Обычный"], [1.1, "Крупный"]], "ui_scale", Gfx.apply)
	_toggle(box, "Меньше анимаций", "reduce_motion")
	_toggle(box, "Высокая контрастность", "high_contrast", func(): main.open("settings"))
	_toggle(box, "Альтернативная цветовая кодировка (для дальтонизма)", "colorblind", func(): main.open("settings"))
	_toggle(box, "Вибрация при нажатиях", "vibration")
	box.add_child(UI.label("Скорость боя по умолчанию", UI.FS.body, UI.TEXT, true))
	var speeds: Array = Game.profile.get("battle_speeds", [1, 2])
	var items: Array = []
	for s in speeds:
		items.append([int(s), "x%d" % int(s)])
	_choice(box, items, "battle_speed")
	_note(box, "Скорости выше x2 открываются с уровнем VIP (VIP %d сейчас)." % int(Game.profile.get("vip_level", 0)))


# ------------------------------------------------------------------ notifications
func _notifications() -> void:
	var box := _group("Уведомления")
	_note(box, "Какие события показывать в центре уведомлений и на колокольчике.")
	var upd := func(): main.set_badges(main.summary)
	_toggle(box, "Награды: дозор, задания, почта", "notify_rewards", upd)
	_toggle(box, "Друзья, подарки и чат", "notify_social", upd)
	_toggle(box, "Гильдия: заявки", "notify_guild", upd)
	_toggle(box, "Мировые события", "notify_events", upd)


# ------------------------------------------------------------------ AI residents
func _ai() -> void:
	var box := _group("ИИ-жители")
	_note(box, "ИИ-персонажи всегда помечены значком «ИИ» и не выдаются за реальных игроков.")
	var r := await Api.get_json("/social/ai-prefs")
	if not r.ok or not is_instance_valid(box):
		if is_instance_valid(box):
			_note(box, "Настройки ИИ недоступны без соединения.")
		return
	for k in r.data.names:
		var cb := CheckButton.new()
		cb.text = String(r.data.names[k])
		cb.button_pressed = bool(r.data.prefs.get(k, true))
		cb.add_theme_font_size_override("font_size", UI.FS.body)
		cb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var key: String = k
		cb.toggled.connect(func(on: bool): Api.post_json("/social/ai-prefs", {key: on}))
		box.add_child(cb)
	var off: Array = []
	for k in r.data.global:
		if k != "arena_rated" and not r.data.global[k]:
			off.append(String(r.data.global_names.get(k, k)))
	if off.size() > 0:
		_note(box, "Отключено владельцем сервера: " + ", ".join(off))


# ------------------------------------------------------------------ data & updates
func _data() -> void:
	var box := _group("Данные и обновления")
	_note(box, Content.summary())
	var crow := HBoxContainer.new()
	crow.add_theme_constant_override("separation", UI.SP.s)
	var chk := UI.button("Проверить контент", "glass", 0, 84)
	chk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chk.pressed.connect(_check_content)
	crow.add_child(chk)
	var rb := UI.button("Откатить", "glass", 0, 84)
	rb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rb.disabled = Content.previous.is_empty()
	rb.pressed.connect(func():
		UI.confirm(main.ui, "Откатить контент?", "Будет восстановлена предыдущая версия пакетов контента.", "Откатить", func():
			if await Content.rollback():
				Router.toast("Контент откатан к предыдущей версии")
				main.open("settings")))
	crow.add_child(rb)
	box.add_child(crow)
	var bg := CheckButton.new()
	bg.text = "Загружать обновления контента в фоне"
	bg.button_pressed = Content.background_enabled
	bg.add_theme_font_size_override("font_size", UI.FS.body)
	bg.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	bg.toggled.connect(func(on: bool): Content.set_background(on))
	box.add_child(bg)
	var cache := UI.button("Очистить кэш изображений", "glass", 0, 84)
	cache.pressed.connect(func():
		var n := Models.clear_cache() + Content.clear_texture_cache()
		Router.toast("Кэш очищен: освобождено изображений — %d" % n))
	box.add_child(cache)
	_note(box, "Кэш портретов и картинок собирается заново по мере надобности. Прогресс хранится на сервере и не затрагивается.")
	var upd := UI.button("Проверить обновление приложения", "glass", 0, 84)
	upd.pressed.connect(func(): load("res://src/ui/UpdateDialog.gd").check(main.ui, true))
	box.add_child(upd)
	# server address: only for test builds (dev channel) — players never need it
	if Config.CHANNEL == "dev":
		box.add_child(UI.label("Адрес сервера (тестовая сборка)", UI.FS.body, UI.TEXT, true))
		var srv_row := HBoxContainer.new()
		srv_row.add_theme_constant_override("separation", UI.SP.s)
		var srv := LineEdit.new()
		srv.text = Config.server_url
		srv.custom_minimum_size = Vector2(0, 84)
		srv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		srv.add_theme_font_size_override("font_size", UI.FS.caption + 2)
		srv_row.add_child(srv)
		var sb := UI.button("Применить", "glass", 0, 84)
		sb.pressed.connect(func(): Config.server_url = srv.text.strip_edges(); Config.save(); Router.toast("Адрес сервера сохранён"))
		srv_row.add_child(sb)
		box.add_child(srv_row)


func _check_content() -> void:
	Router.busy(true)
	var c := await Content.check()
	if c.ok and c.status == "ok":
		var s := await Content.sync(false)
		Router.busy(false)
		if not s.ok:
			Router.toast(s.get("message", "Ошибка загрузки"), true)
			return
		if Content.has_pending():
			await Content.apply_pending()
		else:
			Router.toast("Контент актуален")
	else:
		Router.busy(false)
		Router.toast(c.get("message", "Обновления недоступны: " + String(c.status)), true)
	main.open("settings")


# ------------------------------------------------------------------ about
func _about() -> void:
	var box := _group("О игре")
	_note(box, "УРАЛИЯ: Дыхание предков · версия %s · канал %s" % [Config.CLIENT_VERSION, Config.CHANNEL])
	_note(box, "Ассеты: KayKit (CC0), Poly Haven (CC0), RPG Sound Pack (CC0); шрифты Philosopher и Manrope (SIL OFL). Музыка — оригинальная.")
	var lo := UI.button("Выйти из аккаунта", "danger", 0, 88)
	lo.pressed.connect(_logout)
	box.add_child(lo)
