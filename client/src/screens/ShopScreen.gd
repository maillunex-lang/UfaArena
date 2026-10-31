extends Control
## Shop: 8 sections from the server catalog (RUB prices, discounts, limits, expiry), crystal lavka,
## VIP + subscriptions, battle pass, wardrobe (equip cosmetics), order history and promo codes.
## Real-money purchases: create order -> confirm with provider -> server grants. In TEST mode the
## server accepts only the test provider and never charges anything.

var main: Node
var tab := "crystals"
var data := {}
var _body: VBoxContainer
var _tabs: HBoxContainer
static var _seen := {}  # offer impressions sent once per session
var _pending_views: Array = []
const EXTRA_TABS := [["lavka", "Лавка"], ["wardrobe", "Гардероб"], ["history", "Заказы"]]
const CUR := {"gold": "Золото", "crystals": "Кристаллы", "summon_essence": "Эссенция призыва",
	"ancient_seals": "Древние печати", "guild_marks": "Знаки гильдии", "nature_essence": "Эссенция природы"}


func setup(m: Node, p: Dictionary) -> void:
	main = m
	tab = p.get("tab", "crystals")
	main.use_world("hub")
	var panel := UI.glass_panel(Color("#ffe1a0"))
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
	head.add_child(UI.title("Магазин", 48))
	head.add_child(UI.expand())
	if Game.test_mode:
		var t := UI.label("ТЕСТОВЫЙ РЕЖИМ · без списаний", 24, Color("#7fe39a"), true)
		head.add_child(t)
	v.add_child(head)
	var sc := ScrollContainer.new()
	sc.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sc.custom_minimum_size = Vector2(0, 92)
	_tabs = HBoxContainer.new()
	_tabs.add_theme_constant_override("separation", 8)
	sc.add_child(_tabs)
	v.add_child(sc)
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_body))
	_load()


func _load() -> void:
	var r := await Api.get_json("/shop")
	if not r.ok or not is_inside_tree():
		Router.error(r)
		return
	data = r.data
	Game.test_mode = data.get("test_mode", true)
	_render_tabs()
	_render()


func _render_tabs() -> void:
	for c in _tabs.get_children():
		c.queue_free()
	for s in data.get("sections", []) + EXTRA_TABS:
		var key: String = s[0]
		var b := UI.button(s[1], "primary" if key == tab else "glass", 0, 84)
		b.add_theme_font_size_override("font_size", 26)
		b.pressed.connect(func(): tab = key; _render_tabs(); _render())
		_tabs.add_child(b)


func _clear() -> void:
	for c in _body.get_children():
		c.queue_free()


func _render() -> void:
	_clear()
	match tab:
		"lavka": await _render_lavka()
		"wardrobe": await _render_wardrobe()
		"history": await _render_history()
		"vip":
			await _render_vip()
			_render_products("vip")
			await _render_subscriptions()
		"battlepass":
			_render_products("battlepass")
			await _render_battlepass()
		_: _render_products(tab)


# ------------------------------------------------------------------ products (real money)
func _render_products(section: String) -> void:
	var any := false
	for it in data.get("items", []):
		if it.section != section:
			continue
		any = true
		_body.add_child(_card(it))
	if not any:
		_body.add_child(UI.label("Сейчас здесь нет предложений.", 28, UI.MUTED))
	if _pending_views.size() > 0:
		Api.post_json("/shop/offer-view", {"skus": _pending_views.duplicate()})
		_pending_views.clear()


func _contents_text(c: Dictionary) -> String:
	var parts := []
	for k in c.get("currencies", {}):
		parts.append("%s ×%s" % [CUR.get(k, k), Game.fmt(c.currencies[k])])
	for code in c.get("heroes", []):
		parts.append("Герой: " + String(Game.catalog_hero(code).get("name", code)))
	for code in c.get("shards", {}):
		parts.append("Осколки %s ×%d" % [Game.catalog_hero(code).get("name", code), int(c.shards[code])])
	if c.get("shards_choice"):
		parts.append("Осколки героя на выбор ×%d" % int(c.shards_choice))
	if c.get("hero_choice"):
		parts.append("Герой на выбор (до «%s»)" % Game.rarities.get(str(int(c.hero_choice.rarity_max)), ""))
	for cid in c.get("cosmetics", []):
		parts.append("Косметика: " + String(cid))
	if c.get("entitlement"):
		parts.append("Подписка на %d дней" % int(c.entitlement.get("days", 30)))
	if c.get("bp_premium"):
		parts.append("Premium-линия боевого пропуска")
	return " · ".join(parts)


func _card(it: Dictionary) -> Control:
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", UI._flat(Color(0, 0, 0, 0.32), UI.GOLD if it.discount_pct > 0 else Color(1, 1, 1, 0.22), 22, 2))
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(UI.label(it.name, 30, UI.GOLD, true))
	var disp: Dictionary = it.get("display", {})
	if disp.get("bonus", 0) > 0:
		info.add_child(UI.label("%d + бонус %d кристаллов" % [int(disp.base), int(disp.bonus)], 24, Color("#9fe0ff"), true))
	if String(it.get("desc", "")) != "":
		var d := UI.label(it.desc, 22, UI.MUTED)
		d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		info.add_child(d)
	var ct := UI.label(_contents_text(it.contents), 23, UI.TEXT)
	ct.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	info.add_child(ct)
	var meta := []
	if it.limit:
		meta.append("Лимит: %d/%d (%s)" % [int(it.bought), int(it.limit.count), {"once": "навсегда", "week": "неделя",
			"month": "30 дней", "season": "сезон", "event": "событие", "day": "день"}.get(it.limit.period, it.limit.period)])
	if it.expires_at:
		meta.append("До " + String(it.expires_at).substr(0, 16).replace("T", " "))
	if String(it.get("personal_reason", "")) != "":
		meta.append("Для вас: " + it.personal_reason)
	if meta.size() > 0:
		var ml := UI.label(" · ".join(meta), 21, UI.MUTED)
		ml.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		info.add_child(ml)
	h.add_child(info)
	var buy := VBoxContainer.new()
	buy.alignment = BoxContainer.ALIGNMENT_CENTER
	if it.discount_pct > 0:
		buy.add_child(UI.label("−%d%%  было %s" % [int(it.discount_pct), Game.rub(it.base_price_rub)], 21, Color("#ffb3a8")))
	var b := UI.button(Game.rub(it.price_rub), "primary" if it.available else "dim", 220, 92)
	b.disabled = not it.available
	if not it.available:
		b.text = {"limit_reached": "Куплено", "owned": "Активно", "locked_until": "Скоро", "ended": "Завершено"}.get(it.unavailable_reason, "Недоступно")
	b.pressed.connect(func(): _purchase(it))
	buy.add_child(b)
	if Game.test_mode and it.available:
		buy.add_child(UI.label("ТЕСТ: без списания", 18, Color("#7fe39a")))
	h.add_child(buy)
	card.add_child(h)
	if not _seen.has(it.sku):
		_seen[it.sku] = true
		_pending_views.append(it.sku)
	return card


func _purchase(it: Dictionary) -> void:
	var hero := ""
	if it.needs_hero_choice:
		hero = await _pick_hero(it)
		if hero == "":
			return
	Router.busy(true)
	var o := await Api.post_json("/shop/orders", {"sku": it.sku, "hero_code": hero if hero != "" else null}, true)
	if not o.ok:
		Router.busy(false)
		Router.error(o)
		return
	# TEST mode: the server only accepts the test provider. Real providers are wired server-side later.
	var c := await Api.post_json("/shop/orders/%s/confirm" % o.data.order.id, {"provider": "test", "payload": {}}, true)
	Router.busy(false)
	if not c.ok:
		Router.error(c)
		return
	Sfx.play("coins")
	Game.set_wallet(c.data.get("wallet", {}))
	Router.toast("Получено: " + _grant_text(c.data.order.grant))
	await Game.refresh_heroes()
	var me := await Api.get_json("/player/me")
	if me.ok:
		Game.profile = me.data.profile
		Game.profile_changed.emit()
	_load()


func _grant_text(g: Dictionary) -> String:
	var parts := []
	for k in g.get("currencies", {}):
		parts.append("%s +%s" % [CUR.get(k, k), Game.fmt(g.currencies[k])])
	for code in g.get("heroes", []):
		parts.append("герой " + String(Game.catalog_hero(code).get("name", code)))
	for code in g.get("shards", {}):
		parts.append("осколки +%d" % int(g.shards[code]))
	if g.get("cosmetics"):
		parts.append("косметика")
	if g.get("entitlements") and not g.get("cosmetics"):
		parts.append("подписка активирована")
	if g.has("bp_premium"):
		parts.append("Premium пропуска")
	if g.get("vip_xp"):
		parts.append("VIP-опыт +%d" % int(g.vip_xp))
	return ", ".join(parts) if parts.size() > 0 else "готово"


func _pick_hero(it: Dictionary) -> String:
	var choices := []
	if it.contents.get("shards_choice") or it.get("needs_hero_choice") and not it.get("hero_choice"):
		for h in Game.heroes:
			choices.append({"code": h.hero_code, "name": h.name, "rarity": int(h.rarity)})
	if it.get("hero_choice"):
		choices = []
		var owned := {}
		for h in Game.heroes:
			owned[h.hero_code] = true
		for h in Game.catalog.get("heroes", []):
			if not h.is_enemy and h.get("summonable", true) and int(h.rarity) <= int(it.hero_choice.rarity_max):
				choices.append({"code": h.code, "name": h.name + (" (есть)" if owned.has(h.code) else ""), "rarity": int(h.rarity)})
	choices.sort_custom(func(a, b): return a.rarity > b.rarity)
	var dlg := ColorRect.new()
	dlg.color = Color(0, 0, 0, 0.7)
	dlg.set_anchors_preset(Control.PRESET_FULL_RECT)
	main.modal(dlg)
	var p := UI.glass_panel()
	p.set_anchors_preset(Control.PRESET_FULL_RECT)
	p.offset_left = 40
	p.offset_right = -40
	p.offset_top = 120
	p.offset_bottom = -120
	dlg.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	p.add_child(v)
	v.add_child(UI.title("Выберите героя", 44))
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 8)
	v.add_child(UI.scroll(list))
	var picked := [""]
	var done := [false]
	for ch in choices:
		var b := UI.button("%s · %s" % [ch.name, Game.rarities.get(str(ch.rarity), "")], "glass", 0, 84)
		b.add_theme_color_override("font_color", Game.RARITY_COLORS.get(ch.rarity, Color.WHITE))
		var code: String = ch.code
		b.pressed.connect(func(): picked[0] = code; done[0] = true)
		list.add_child(b)
	var cancel := UI.button("Отмена", "dim", 0, 84)
	cancel.pressed.connect(func(): done[0] = true)
	v.add_child(cancel)
	while not done[0] and is_instance_valid(dlg):
		await get_tree().process_frame
	if is_instance_valid(dlg):
		dlg.queue_free()
	return picked[0]


# ------------------------------------------------------------------ lavka (in-game currency)
func _render_lavka() -> void:
	var r := await Api.get_json("/shop/lavka")
	if not r.ok or not is_inside_tree():
		return
	_body.add_child(UI.label("Покупки за кристаллы и печати · ежедневное обновление " + String(r.data.daily_refresh).substr(11, 5) +
		" UTC, еженедельное — по понедельникам", 24, UI.MUTED))
	for it in r.data.items:
		var card := PanelContainer.new()
		card.add_theme_stylebox_override("panel", UI._flat(Color(0, 0, 0, 0.3), Color(1, 1, 1, 0.2), 22, 2))
		var h := HBoxContainer.new()
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.add_child(UI.label("%s  ·  %s" % [it.name, "день" if it.kind == "daily" else "неделя"], 28, UI.GOLD, true))
		info.add_child(UI.label(_contents_text(it.contents) + "   (%d/%d)" % [int(it.bought), int(it.limit)], 23))
		h.add_child(info)
		var cost := HBoxContainer.new()
		cost.add_child(UI.rewards_row(it.cost, 26))
		h.add_child(cost)
		var b := UI.button("Купить", "primary" if int(it.bought) < int(it.limit) else "dim", 180, 84)
		b.disabled = int(it.bought) >= int(it.limit)
		var item: Dictionary = it
		b.pressed.connect(func(): _buy_lavka(item))
		h.add_child(b)
		card.add_child(h)
		_body.add_child(card)


func _buy_lavka(it: Dictionary) -> void:
	var hero := ""
	if it.needs_hero_choice:
		hero = await _pick_hero({"contents": it.contents, "needs_hero_choice": true})
		if hero == "":
			return
	var r := await Api.post_json("/shop/lavka/%s/buy" % it.id, {"hero_code": hero if hero != "" else null}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coin")
	Game.set_wallet(r.data.wallet)
	Router.toast("Получено: " + _grant_text(r.data.granted))
	_render()


# ------------------------------------------------------------------ VIP & subscriptions
func _render_vip() -> void:
	var r := await Api.get_json("/vip")
	if not r.ok or not is_inside_tree():
		return
	var v: Dictionary = r.data
	v["claimable"] = _ints(v.claimable)  # JSON numbers arrive as floats; `in` is type-strict in GDScript
	v["claimed"] = _ints(v.claimed)
	var box := PanelContainer.new()
	box.add_theme_stylebox_override("panel", UI._flat(Color(0.2, 0.12, 0.3, 0.5), Color("#c9a0ff"), 22, 3))
	var vv := VBoxContainer.new()
	vv.add_child(UI.title("VIP %d" % int(v.level), 46))
	if v.next_xp != null:
		vv.add_child(UI.label("Опыт: %d / %d" % [int(v.xp), int(v.next_xp)], 26))
		vv.add_child(UI.bar(int(v.xp), int(v.next_xp), Color("#c9a0ff"), 18))
	else:
		vv.add_child(UI.label("Максимальный уровень · %d опыта" % int(v.xp), 26))
	var src := UI.label("VIP-опыт: %d за каждый рубль покупки, %d за ежедневную активность, %d за достижения. Уровень не сгорает." % [
		int(v.sources.purchase_per_rub), int(v.sources.daily), int(v.sources.achievement)], 22, UI.MUTED)
	src.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vv.add_child(src)
	vv.add_child(UI.label("Бонус AFK: +%.1f%% · скорость боя до x%d" % [float(v.afk_bonus) * 100, int(v.battle_speeds[-1])], 24, UI.GOLD))
	for lvs in range(1, 8):
		var row := HBoxContainer.new()
		var perk := UI.label("VIP %d (%d): %s" % [lvs, int(v.levels[lvs]), String(v.perks.get(str(lvs), ""))], 22,
			UI.TEXT if lvs <= int(v.level) else UI.MUTED)
		perk.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		perk.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		row.add_child(perk)
		if lvs in v.claimable:
			var b := UI.button("Награда", "primary", 170, 72)
			var lvn := lvs
			b.pressed.connect(func(): _claim("/vip/rewards/%d/claim" % lvn))
			row.add_child(b)
		elif lvs in v.claimed:
			row.add_child(UI.label("получено", 20, UI.MUTED))
		vv.add_child(row)
	if v.history.size() > 0:
		var hist := []
		for hrow in v.history.slice(0, 6):
			hist.append("%+d %s" % [int(hrow.delta), hrow.source])
		vv.add_child(UI.label("История: " + ", ".join(hist), 20, UI.MUTED))
	box.add_child(vv)
	_body.add_child(box)


func _render_subscriptions() -> void:
	var r := await Api.get_json("/subscriptions")
	if not r.ok or not is_inside_tree():
		return
	for s in r.data.subscriptions:
		if not s.active:
			continue
		var row := HBoxContainer.new()
		var l := UI.label("%s активна до %s" % [s.name, String(s.expires_at).substr(0, 10)], 26, Color("#7fe39a"), true)
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(l)
		var b := UI.button("Получено сегодня" if s.claimed_today else "Ежедневная награда", "dim" if s.claimed_today else "primary", 300, 80)
		b.disabled = s.claimed_today
		var code: String = s.code
		b.pressed.connect(func(): _claim("/subscriptions/%s/claim" % code))
		row.add_child(b)
		_body.add_child(row)


func _claim(path: String) -> void:
	var r := await Api.post_json(path, {}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Получено: " + _grant_text(r.data.granted))
	_render()


# ------------------------------------------------------------------ battle pass
func _render_battlepass() -> void:
	var r := await Api.get_json("/battlepass")
	if not r.ok or not is_inside_tree():
		return
	var bp: Dictionary = r.data
	bp["claimed_free"] = _ints(bp.claimed_free)
	bp["claimed_premium"] = _ints(bp.claimed_premium)
	var head := VBoxContainer.new()
	head.add_child(UI.title("Сезон «%s»" % bp.name, 40))
	head.add_child(UI.label("Уровень %d · опыт %d (уровень = %d опыта) · до %s" % [int(bp.level), int(bp.xp), int(bp.xp_per_level),
		String(bp.ends).substr(0, 10)], 24))
	var lvl_xp := int(bp.xp) - int(bp.level) * int(bp.xp_per_level)
	head.add_child(UI.bar(lvl_xp, int(bp.xp_per_level), UI.GOLD, 16))
	var src := UI.label("Опыт: бой +%d, прохождение +%d, задание +%d, дозор +%d, призыв +%d, ежедневный вход +%d" % [
		int(bp.xp_sources.battle_fought), int(bp.xp_sources.campaign_clear), int(bp.xp_sources.quest_claim),
		int(bp.xp_sources.afk_claim), int(bp.xp_sources.summon), int(bp.xp_sources.daily_login)], 21, UI.MUTED)
	src.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	head.add_child(src)
	_body.add_child(head)
	for lvl in bp.levels:
		var n := int(lvl.level)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		row.add_child(UI.label("%2d" % n, 30, UI.GOLD if n <= int(bp.level) else UI.MUTED, true))
		for track in ["free", "premium"]:
			var col := VBoxContainer.new()
			col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			col.add_child(UI.label(("Бесплатно: " if track == "free" else "Premium: ") + _contents_text(lvl[track]), 21,
				UI.TEXT if track == "free" or bp.premium else UI.MUTED))
			var claimed: bool = n in (bp.claimed_free if track == "free" else bp.claimed_premium)
			var can: bool = n <= int(bp.level) and not claimed and (track == "free" or bp.premium)
			if claimed:
				col.add_child(UI.label("получено", 19, UI.MUTED))
			elif can:
				var b := UI.button("Забрать", "primary", 0, 64)
				b.add_theme_font_size_override("font_size", 24)
				var tr: String = track
				b.pressed.connect(func(): _claim_bp(n, tr))
				col.add_child(b)
			row.add_child(col)
		_body.add_child(row)


func _claim_bp(level: int, track: String) -> void:
	var r := await Api.post_json("/battlepass/claim", {"level": level, "track": track}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Получено: " + _grant_text(r.data.granted))
	_render()


# ------------------------------------------------------------------ wardrobe
func _render_wardrobe() -> void:
	var r := await Api.get_json("/cosmetics")
	if not r.ok or not is_inside_tree():
		return
	var owned: Array = r.data.owned
	if owned.is_empty():
		_body.add_child(UI.label("Косметики пока нет. Её можно получить в разделе «Косметика», за VIP, подписки и боевой пропуск.", 26, UI.MUTED))
	var raw: Dictionary = r.data.raw
	var types := {"frame": "Рамки", "title": "Титулы", "profile_effect": "Эффекты профиля", "hero_skin": "Облики героев",
		"ability_effect": "Эффекты способностей", "emote": "Эмоции", "fortress": "Оформление крепости"}
	for t in types:
		var items := owned.filter(func(c): return c.type == t)
		if items.is_empty():
			continue
		_body.add_child(UI.label(types[t], 30, UI.ACCENT, true))
		for c in items:
			var row := HBoxContainer.new()
			var l := UI.label(c.name, 26, Game.RARITY_COLORS.get(int(c.rarity), Color.WHITE), true)
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(l)
			var key: String = {"hero_skin": "hero_skins", "ability_effect": "ability_effects"}.get(t, t)
			var on := false
			if raw.get(key) is Dictionary:
				on = c.id in (raw[key] as Dictionary).values()
			else:
				on = raw.get(key) == c.id
			var b := UI.button("Снять" if on else "Надеть", "glass" if on else "primary", 180, 76)
			var cid: String = c.id
			var ctype: String = t
			b.pressed.connect(func(): _equip(ctype, cid, on, c))
			row.add_child(b)
			_body.add_child(row)


func _equip(slot: String, cid: String, on: bool, c: Dictionary) -> void:
	var body := {"slot": slot, "cosmetic_id": null if on else cid}
	var hero := String(c.get("data", {}).get("hero", ""))
	if slot == "ability_effect":
		hero = await _pick_hero({"contents": {"shards_choice": 1}, "needs_hero_choice": true})
		if hero == "":
			return
	if hero != "":
		body["hero"] = hero
	var r := await Api.post_json("/cosmetics/equip", body)
	if not r.ok:
		Router.error(r)
		return
	Game.set_cosmetics(r.data.equipped)
	if main.world and main.world.has_method("show_hero"):
		var code: String = main.world.hero_code
		main.world_kind = ""
		main.use_world("hub").show_hero(code if code != "" else "azamat")
	_render()


# ------------------------------------------------------------------ history & promo
func _render_history() -> void:
	var promo_row := HBoxContainer.new()
	var inp := LineEdit.new()
	inp.placeholder_text = "Промокод"
	inp.custom_minimum_size = Vector2(0, 84)
	inp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inp.add_theme_font_size_override("font_size", 28)
	promo_row.add_child(inp)
	var pb := UI.button("Активировать", "primary", 280, 84)
	pb.pressed.connect(func(): _promo(inp.text))
	promo_row.add_child(pb)
	_body.add_child(promo_row)
	var r := await Api.get_json("/shop/orders")
	if not r.ok or not is_inside_tree():
		return
	if r.data.orders.is_empty():
		_body.add_child(UI.label("Заказов пока нет.", 26, UI.MUTED))
	for o in r.data.orders:
		var st: String = {"fulfilled": "выдан", "refunded": "возврат", "created": "создан", "failed": "ошибка"}.get(o.status, o.status)
		_body.add_child(UI.label("%s · %s · %s · %s%s" % [String(o.created_at).substr(0, 16).replace("T", " "), o.sku,
			Game.rub(o.price_rub), st, "  (тест)" if o.is_test else ""], 23, UI.TEXT if o.status == "fulfilled" else UI.MUTED))


func _promo(code: String) -> void:
	var r := await Api.post_json("/promo/redeem", {"code": code.strip_edges()}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Промокод: " + _grant_text(r.data.granted))


static func _ints(a: Array) -> Array:
	var out := []
	for x in a:
		out.append(int(x))
	return out
