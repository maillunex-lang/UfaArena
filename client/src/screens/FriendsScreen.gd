extends Control
## Friends: list with presence, gifts and help; requests; search by ID / name, recommendations and
## invite codes; received gifts and the friendship-token shop. AI personas carry the "ИИ" badge.

const PlayerPopup := preload("res://src/ui/PlayerPopup.gd")
const TABS := [["friends", "Друзья"], ["requests", "Заявки"], ["find", "Найти"], ["gifts", "Подарки"], ["blocked", "Блок"]]

var main: Node
var tab := "friends"
var _tabs: HBoxContainer
var _body: VBoxContainer
var _data := {}


func setup(m: Node, p: Dictionary) -> void:
	main = m
	tab = String(p.get("tab", "friends"))
	main.use_world("none")
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
	head.add_child(UI.title("Друзья", 48))
	head.add_child(UI.expand())
	var chat := UI.button("Чат", "glass", 0, 80)
	chat.pressed.connect(func(): main.open("chat"))
	head.add_child(chat)
	v.add_child(head)
	_tabs = HBoxContainer.new()
	_tabs.add_theme_constant_override("separation", 8)
	v.add_child(_tabs)
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 10)
	v.add_child(UI.scroll(_body))
	UI.keep_wrapped(_body)
	_render()


func _render() -> void:
	for c in _tabs.get_children():
		c.queue_free()
	for t in TABS:
		var cap: String = t[1]
		if t[0] == "requests" and _data.get("incoming", []).size() > 0:
			cap += " (%d)" % _data.incoming.size()
		if t[0] == "gifts" and int(_data.get("gifts_waiting", 0)) > 0:
			cap += " (%d)" % int(_data.gifts_waiting)
		var b := UI.button(cap, "primary" if t[0] == tab else "glass", 0, 80)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.add_theme_font_size_override("font_size", 28)
		var key: String = t[0]
		b.pressed.connect(func(): tab = key; _render())
		_tabs.add_child(b)
	for c in _body.get_children():
		c.queue_free()
	match tab:
		"friends": _friends()
		"requests": _requests()
		"find": _find()
		"gifts": _gifts()
		"blocked": _blocked()


func _blocked() -> void:
	_body.add_child(UI.skeleton(2, 100))
	await _reload()
	if not is_inside_tree() or tab != "blocked":
		return
	for c in _body.get_children():
		c.queue_free()
	var list: Array = _data.get("blocked", [])
	var info := UI.label("Заблокированные игроки не могут писать вам, приглашать и отправлять заявки.", 24, UI.MUTED)
	info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.add_child(info)
	if list.is_empty():
		_body.add_child(UI.state("empty", "Вы никого не блокировали."))
	for c in list:
		var card := UI.card()
		var h := HBoxContainer.new()
		var l := UI.label("%s · ур. %d" % [c.nickname, int(c.get("level", 1))], 28, UI.TEXT, true)
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		h.add_child(l)
		var uid: String = c.user_id
		var b := UI.button("Разблокировать", "glass", 0, 80)
		b.pressed.connect(func():
			var r := await Api.post_json("/social/unblock/" + uid, {})
			if not r.ok:
				Router.error(r)
				return
			Router.toast("Игрок разблокирован")
			_render())
		h.add_child(b)
		card.add_child(h)
		_body.add_child(card)


func _reload() -> void:
	var r := await Api.get_json("/social/friends")
	if r.ok:
		_data = r.data


func _row(c: Dictionary) -> Dictionary:
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.5), Color(1, 1, 1, 0.18), 22, 2))
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	var dot := UI.label("●", 34, UI.presence_color(String(c.get("presence", "offline"))))
	h.add_child(dot)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.custom_minimum_size.x = 200
	var nr := HBoxContainer.new()
	nr.add_theme_constant_override("separation", 8)
	var nb := Button.new()
	nb.text = String(c.nickname)
	nb.flat = true
	nb.focus_mode = Control.FOCUS_NONE
	nb.add_theme_font_override("font", UI.FONT_BOLD)
	nb.add_theme_font_size_override("font_size", 30)
	nb.add_theme_color_override("font_color", UI.GOLD)
	var uid: String = c.user_id
	nb.pressed.connect(func(): PlayerPopup.open(self, uid, main))
	nr.add_child(nb)
	if c.get("is_ai", false):
		nr.add_child(UI.ai_badge())
	info.add_child(nr)
	var sub := "ур.%d · сила %s · %s" % [int(c.level), Game.fmt(int(c.power)), UI.presence_text(String(c.get("presence", "")))]
	if c.get("guild"):
		sub += " · [%s]" % c.guild.tag
	if c.has("reason"):
		sub += " · " + String(c.reason)
	info.add_child(UI.label(sub, 24, UI.MUTED))
	h.add_child(info)
	card.add_child(h)
	return {"card": card, "row": h}


# ------------------------------------------------------------------ friends
func _friends() -> void:
	_body.add_child(UI.label("Загрузка…", 26, UI.MUTED))
	await _reload()
	if not is_inside_tree() or tab != "friends":
		return
	for c in _body.get_children():
		c.queue_free()
	var lim: Dictionary = _data.get("limits", {})
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 10)
	top.add_child(UI.label("%d / %d" % [_data.friends.size(), int(_data.max)], 30, UI.TEXT, true))
	top.add_child(UI.expand())
	var all := UI.button("Подарить всем", "primary", 0, 80)
	all.add_theme_font_size_override("font_size", 28)
	all.pressed.connect(func():
		var r := await Api.post_json("/social/gifts/send-all", {}, true)
		if r.ok:
			Router.toast("Отправлено подарков: %d" % int(r.data.sent))
			_render()
		else:
			Router.error(r))
	top.add_child(all)
	_body.add_child(top)
	_body.add_child(UI.label("Подарки сегодня: %d/%d · помощь: %d/%d. Подарок: 5 жетонов дружбы и золото. Помощь: травы и «Благословение друга» (+8%% атаки на 3 боя кампании)." % [
		int(lim.get("sent_today", 0)), int(lim.get("gift_send_per_day", 20)), int(lim.get("helped_today", 0)),
		int(lim.get("help_per_day", 5))], 24, UI.MUTED))
	if int(_data.get("blessing_battles", 0)) > 0:
		_body.add_child(UI.label("У вас «Благословение друга» на %d боя" % int(_data.blessing_battles), 26, UI.GOLD, true))
	var hide := CheckButton.new()
	hide.text = "Скрыть мой статус «в сети»"
	hide.button_pressed = bool(_data.get("presence_hidden", false))
	hide.add_theme_font_size_override("font_size", 26)
	hide.toggled.connect(func(on: bool): Api.post_json("/social/presence", {"hidden": on}))
	_body.add_child(hide)
	if _data.friends.is_empty():
		var e := UI.label("Пока нет друзей. Откройте вкладку «Найти»: поиск по ID или имени, рекомендации и код приглашения.", 28, UI.TEXT)
		_body.add_child(e)
		return
	for c in _data.friends:
		var r := _row(c)
		var h: HBoxContainer = r.row
		var uid: String = c.user_id
		var g := _icon_btn("shop", "dim" if c.gift_sent else "primary")
		g.disabled = c.gift_sent
		g.pressed.connect(func(): _act("/social/gifts/send/" + uid, "Подарок отправлен"))
		h.add_child(g)
		var hp := _icon_btn("friends", "dim" if c.helped else "glass")
		hp.disabled = c.helped
		hp.pressed.connect(func(): _act("/social/help/" + uid, "Помощь отправлена"))
		h.add_child(hp)
		var dm := _icon_btn("chat", "glass")
		var nick: String = c.nickname
		var ai: bool = c.get("is_ai", false)
		dm.pressed.connect(func(): main.open("chat", {"to_user": uid, "name": nick, "is_ai": ai}))
		h.add_child(dm)
		_body.add_child(r.card)


func _icon_btn(kind: String, style: String) -> Button:
	var b := UI.button("", style, 88, 80)
	var ic := GameIcon.new()
	ic.kind = kind
	ic.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ic.offset_left = 16
	ic.offset_right = -16
	ic.offset_top = 10
	ic.offset_bottom = -10
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(ic)
	return b


func _act(path: String, ok_text: String) -> void:
	var r := await Api.post_json(path, {}, true)
	if r.ok:
		Router.toast(ok_text)
		Sfx.play("coin")
		_render()
	else:
		Router.error(r)


# ------------------------------------------------------------------ requests
func _requests() -> void:
	await _reload()
	if not is_inside_tree() or tab != "requests":
		return
	for c in _body.get_children():
		c.queue_free()
	_body.add_child(UI.label("Входящие", 32, UI.ACCENT, true))
	if _data.incoming.is_empty():
		_body.add_child(UI.label("Новых заявок нет", 26, UI.MUTED))
	for q in _data.incoming:
		var r := _row(q.from)
		var rid: String = q.id
		var ok := UI.button("Принять", "primary", 0, 80)
		ok.pressed.connect(func(): _respond(rid, "accept"))
		r.row.add_child(ok)
		var no := UI.button("✕", "dim", 84, 80)
		no.pressed.connect(func(): _respond(rid, "decline"))
		r.row.add_child(no)
		_body.add_child(r.card)
	_body.add_child(UI.label("Отправленные", 32, UI.ACCENT, true))
	if _data.outgoing.is_empty():
		_body.add_child(UI.label("Нет ожидающих заявок", 26, UI.MUTED))
	for q in _data.outgoing:
		var r := _row(q.to)
		var rid: String = q.id
		var no := UI.button("Отменить", "dim", 0, 80)
		no.pressed.connect(func(): _respond(rid, "cancel"))
		r.row.add_child(no)
		_body.add_child(r.card)


func _respond(rid: String, action: String) -> void:
	var r := await Api.post_json("/social/friends/requests/%s/%s" % [rid, action], {})
	if r.ok:
		Router.toast({"accept": "Теперь вы друзья!", "decline": "Заявка отклонена", "cancel": "Заявка отменена"}[action])
		_render()
	else:
		Router.error(r)


# ------------------------------------------------------------------ find
func _find() -> void:
	_body.add_child(UI.label("Поиск по ID (UR-…) или по имени", 30, UI.ACCENT, true))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var q := LineEdit.new()
	q.placeholder_text = "UR-XXXXXXXX или имя"
	q.custom_minimum_size = Vector2(0, 92)
	q.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	q.add_theme_font_size_override("font_size", 30)
	row.add_child(q)
	var go := UI.button("Найти", "primary", 200, 92)
	row.add_child(go)
	_body.add_child(row)
	var results := VBoxContainer.new()
	results.add_theme_constant_override("separation", 10)
	_body.add_child(results)
	var do_search := func():
		if q.text.strip_edges().length() < 2:
			Router.toast("Введите минимум 2 символа", true)
			return
		var r := await Api.get_json("/social/search?q=" + q.text.strip_edges().uri_encode())
		for c in results.get_children():
			c.queue_free()
		if not r.ok:
			Router.error(r)
			return
		if r.data.items.is_empty():
			results.add_child(UI.label("Никого не нашли", 26, UI.MUTED))
		for c in r.data.items:
			results.add_child(_add_row(c, "id"))
	go.pressed.connect(do_search)
	q.text_submitted.connect(func(_t: String): do_search.call())
	_body.add_child(UI.label("Код приглашения", 30, UI.ACCENT, true))
	var inv := HBoxContainer.new()
	inv.add_theme_constant_override("separation", 10)
	var mine := UI.label("…", 30, UI.GOLD, true)
	mine.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inv.add_child(mine)
	var copy := UI.button("Копировать", "glass", 0, 80)
	inv.add_child(copy)
	_body.add_child(inv)
	var code_row := HBoxContainer.new()
	code_row.add_theme_constant_override("separation", 10)
	var code := LineEdit.new()
	code.placeholder_text = "Код друга, например F1A2B3C4"
	code.custom_minimum_size = Vector2(0, 92)
	code.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	code.add_theme_font_size_override("font_size", 30)
	code_row.add_child(code)
	var use := UI.button("Применить", "primary", 0, 92)
	use.pressed.connect(func():
		var r := await Api.post_json("/social/invite/redeem", {"code": code.text.strip_edges()})
		if r.ok:
			Router.toast("Вы подружились с %s!" % r.data.friend.nickname)
			code.text = ""
		else:
			Router.error(r))
	code_row.add_child(use)
	_body.add_child(code_row)
	_body.add_child(UI.label("Рекомендации", 30, UI.ACCENT, true))
	var rec_box := VBoxContainer.new()
	rec_box.add_theme_constant_override("separation", 10)
	_body.add_child(rec_box)
	var ir := await Api.post_json("/social/invite", {})
	if ir.ok and is_instance_valid(mine):
		mine.text = "Ваш код: " + String(ir.data.code)
		var c2: String = ir.data.code
		copy.pressed.connect(func(): DisplayServer.clipboard_set(c2); Router.toast("Код скопирован"))
	var rr := await Api.get_json("/social/recommendations")
	if rr.ok and is_instance_valid(rec_box):
		if rr.data.items.is_empty():
			rec_box.add_child(UI.label("Пока некого предложить", 26, UI.MUTED))
		for c in rr.data.items:
			rec_box.add_child(_add_row(c, "recommend"))


func _add_row(c: Dictionary, source: String) -> Control:
	var r := _row(c)
	var uid: String = c.user_id
	var add := UI.button("Добавить", "primary", 0, 80)
	add.pressed.connect(func():
		var res := await Api.post_json("/social/friends/request", {"user_id": uid, "source": source})
		if res.ok:
			Router.toast("Вы теперь друзья!" if res.data.status == "friends" else "Заявка отправлена")
			add.disabled = true
			add.text = "✓"
		else:
			Router.error(res))
	r.row.add_child(add)
	return r.card


# ------------------------------------------------------------------ gifts & token shop
func _gifts() -> void:
	var r := await Api.get_json("/social/gifts")
	if not is_inside_tree() or tab != "gifts":
		return
	if not r.ok:
		Router.error(r)
		return
	var top := HBoxContainer.new()
	top.add_child(UI.label("Получено сегодня: %d/%d" % [int(r.data.claimed_today), int(r.data.claim_limit)], 28, UI.TEXT))
	top.add_child(UI.expand())
	var claim := UI.button("Забрать всё", "primary", 0, 80)
	claim.pressed.connect(func():
		var c := await Api.post_json("/social/gifts/claim-all", {}, true)
		if c.ok:
			Router.toast("Получено: " + Game.rewards_text(c.data.rewards) if not c.data.rewards.is_empty() else "Нечего забирать")
			var me := await Api.get_json("/player/me")
			if me.ok:
				Game.set_wallet(me.data.wallet)
			await _reload()
			_render()
		else:
			Router.error(c))
	top.add_child(claim)
	_body.add_child(top)
	var waiting := 0
	for g in r.data.items:
		if g.claimed:
			continue
		waiting += 1
		var l := UI.label("%s %s: %s" % ["Помощь от" if g.kind == "help" else "Подарок от", g.from + (" (ИИ)" if g.from_ai else ""), Game.rewards_text(g.contents)], 26, UI.TEXT)
		_body.add_child(l)
	if waiting == 0:
		_body.add_child(UI.label("Новых подарков нет", 26, UI.MUTED))
	_body.add_child(UI.label("Лавка дружбы (жетоны дружбы)", 32, UI.ACCENT, true))
	var s := await Api.get_json("/social/token-shop")
	if not s.ok or not is_inside_tree():
		return
	_body.add_child(UI.label("У вас жетонов: %d" % int(Game.wallet.get("friend_tokens", 0)), 26, UI.GOLD))
	for it in s.data.items:
		var card := PanelContainer.new()
		card.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.5), Color(1, 1, 1, 0.18), 22, 2))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 10)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.custom_minimum_size.x = 200
		info.add_child(UI.label(String(it.name), 28, UI.GOLD, true))
		info.add_child(UI.label("%s · за неделю %d/%d" % [Game.rewards_text(it.contents), int(it.bought), int(it.weekly_limit)], 24, UI.MUTED))
		h.add_child(info)
		var left: bool = int(it.bought) < int(it.weekly_limit)
		var b := UI.button("%d жет." % int(it.cost), "primary" if left else "dim", 0, 80)
		b.disabled = not left
		var iid: String = it.id
		b.pressed.connect(func():
			var res := await Api.post_json("/social/token-shop/%s/buy" % iid, {}, true)
			if res.ok:
				Game.set_wallet(res.data.wallet)
				Router.toast("Куплено!")
				_render()
			else:
				Router.error(res))
		h.add_child(b)
		card.add_child(h)
		_body.add_child(card)
