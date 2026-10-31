extends Control
## Profile & settings: graphics tier, audio, battle speed, server, URALIA ID linking, logout.

var main: Node


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("hub")
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 24
	panel.offset_right = -24
	panel.offset_top = 10
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 16)
	panel.add_child(UI.scroll(v))
	var head := HBoxContainer.new()
	head.add_child(UI.title("Профиль и настройки", 46))
	head.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 200, 90)
	back.pressed.connect(func(): main.open("home"))
	head.add_child(back)
	v.add_child(head)
	var p := Game.profile
	v.add_child(UI.label("URALIA ID: %s" % p.get("uralia_id", "—"), 32, UI.GOLD, true))
	v.add_child(UI.label("%s · уровень %d" % [p.get("nickname", ""), int(p.get("level", 1))], 30))
	var speeds: Array = p.get("battle_speeds", [1, 2])
	var vip_txt := "VIP %d · ускорение боя: %s" % [int(p.get("vip_level", 0)), ", ".join(speeds.map(func(s): return "x%d" % int(s)))]
	for row in p.get("vip_speed_table", []):
		if int(row.vip) > int(p.get("vip_level", 0)):
			vip_txt += "  (x%d — с VIP %d)" % [int(row.speeds[-1]), int(row.vip)]
			break
	v.add_child(UI.label(vip_txt, 26, UI.GOLD))
	var nick_row := HBoxContainer.new()
	var nick := LineEdit.new()
	nick.text = p.get("nickname", "")
	nick.max_length = 20
	nick.custom_minimum_size = Vector2(0, 90)
	nick.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nick.add_theme_font_size_override("font_size", 32)
	nick_row.add_child(nick)
	var nb := UI.button("Сменить имя", "glass", 300, 90)
	nb.pressed.connect(func(): _nick(nick.text))
	nick_row.add_child(nb)
	v.add_child(nick_row)
	v.add_child(UI.spacer(8))
	v.add_child(UI.label("Графика (адаптивная, сейчас: %s)" % Gfx.tier, 32, UI.ACCENT, true))
	var q_row := HBoxContainer.new()
	q_row.add_theme_constant_override("separation", 10)
	for q in [["auto", "Авто"], ["low", "Низкая"], ["medium", "Средняя"], ["high", "Высокая"]]:
		var b := UI.button(q[1], "primary" if Config.settings.graphics_quality == q[0] else "glass", 0, 90)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var val: String = q[0]
		b.pressed.connect(func(): _save_setting("graphics_quality", val); Gfx.apply(); main.open("settings"))
		q_row.add_child(b)
	v.add_child(q_row)
	for s in [["music_volume", "Музыка"], ["sfx_volume", "Звуки"]]:
		var row := HBoxContainer.new()
		row.add_child(UI.label(s[1], 30))
		var sl := HSlider.new()
		sl.min_value = 0
		sl.max_value = 1
		sl.step = 0.05
		sl.value = float(Config.settings[s[0]])
		sl.custom_minimum_size = Vector2(0, 70)
		sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var key: String = s[0]
		sl.value_changed.connect(func(val: float): _save_setting(key, val); Sfx.apply_volume())
		row.add_child(sl)
		v.add_child(row)
	v.add_child(UI.spacer(8))
	v.add_child(UI.label("Сервер", 32, UI.ACCENT, true))
	var srv_row := HBoxContainer.new()
	var srv := LineEdit.new()
	srv.text = Config.server_url
	srv.custom_minimum_size = Vector2(0, 90)
	srv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	srv.add_theme_font_size_override("font_size", 28)
	srv_row.add_child(srv)
	var sb := UI.button("Применить", "glass", 260, 90)
	sb.pressed.connect(func(): Config.server_url = srv.text.strip_edges(); Config.save(); Router.toast("Адрес сервера сохранён"))
	srv_row.add_child(sb)
	v.add_child(srv_row)
	v.add_child(UI.spacer(8))
	v.add_child(UI.label("Привязка аккаунта (URALIA ID по email)", 32, UI.ACCENT, true))
	var hint := UI.label("Гостевой прогресс хранится на сервере. Привяжите email, чтобы войти на другом устройстве.", 26, UI.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(hint)
	var email := LineEdit.new()
	email.placeholder_text = "email"
	email.custom_minimum_size = Vector2(0, 90)
	email.add_theme_font_size_override("font_size", 30)
	v.add_child(email)
	var pw := LineEdit.new()
	pw.placeholder_text = "пароль (от 8 символов)"
	pw.secret = true
	pw.custom_minimum_size = Vector2(0, 90)
	pw.add_theme_font_size_override("font_size", 30)
	v.add_child(pw)
	var lb := UI.button("Привязать email", "primary")
	lb.pressed.connect(func(): _link(email.text, pw.text))
	v.add_child(lb)
	v.add_child(UI.spacer(8))
	v.add_child(UI.spacer(8))
	v.add_child(UI.label("Обновления контента", 32, UI.ACCENT, true))
	var cs := UI.label(Content.summary(), 24, UI.MUTED)
	cs.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(cs)
	var crow := HBoxContainer.new()
	crow.add_theme_constant_override("separation", 10)
	var chk := UI.button("Проверить", "glass", 0, 90)
	chk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chk.pressed.connect(_check_content)
	crow.add_child(chk)
	var rb := UI.button("Откатить", "glass", 0, 90)
	rb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rb.disabled = Content.previous.is_empty()
	rb.pressed.connect(func():
		if await Content.rollback():
			Router.toast("Контент откатан к предыдущей версии")
			main.open("settings"))
	crow.add_child(rb)
	v.add_child(crow)
	var bg := CheckButton.new()
	bg.text = "Загружать обновления в фоне"
	bg.button_pressed = Content.background_enabled
	bg.add_theme_font_size_override("font_size", 28)
	bg.toggled.connect(func(on: bool): Content.set_background(on))
	v.add_child(bg)
	var about := UI.label("УРАЛИЯ: Дыхание предков · клиент %s · канал %s\nАссеты: KayKit (CC0), Poly Haven (CC0), RPG Sound Pack (CC0), шрифт Philosopher (OFL). Музыка — оригинальная." % [Config.CLIENT_VERSION, Config.CHANNEL], 22, UI.MUTED)
	about.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(about)
	var lo := UI.button("Выйти из аккаунта", "danger")
	lo.pressed.connect(_logout)
	v.add_child(lo)


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


func _save_setting(key: String, val: Variant) -> void:
	Config.settings[key] = val
	Config.save()


func _nick(n: String) -> void:
	var r := await Api.post_json("/player/nickname", {"nickname": n})
	if not r.ok:
		Router.error(r)
		return
	Game.profile["nickname"] = r.data.nickname
	Game.profile_changed.emit()
	Router.toast("Имя изменено")


func _link(email: String, pw: String) -> void:
	var r := await Api.post_json("/auth/link", {"email": email.strip_edges(), "password": pw})
	if not r.ok:
		Router.error(r)
		return
	Router.toast("Email привязан к аккаунту")


func _logout() -> void:
	await Api.post_json("/auth/logout", {})
	Api.clear_session()
	Game.loaded = false
	Router.goto(Router.BOOT)
