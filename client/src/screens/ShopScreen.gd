extends Control
## Shop: 8 sections from the server catalog (RUB prices, discounts, limits, expiry), crystal lavka,
## VIP + subscriptions, battle pass, wardrobe (equip cosmetics), order history and promo codes.
## Real-money purchases: create order -> confirm with provider -> server grants. In TEST mode the
## server accepts only the test provider and never charges anything.

var main: Node
var tab := "crystals"
var data := {}
var _body: VBoxContainer
var _rail: VBoxContainer
static var _seen := {}  # offer impressions sent once per session
var _pending_views: Array = []
const EXTRA_TABS := [["lavka", "Лавка"], ["wardrobe", "Гардероб"], ["history", "Заказы"]]
## Rail: server section → short caption + icon (order follows the mockup: donation first).
const RAIL := {"crystals": ["Кристаллы", "crystals"], "starter": ["Наборы", "afk"], "vip": ["Подписка", "crown"],
	"battlepass": ["Пропуск", "campaign"], "resources": ["Ресурсы", "nature_essence"], "heroes": ["Герои", "heroes"],
	"cosmetics": ["Облики", "profile"], "seasonal": ["Сезон", "events"], "lavka": ["Лавка", "gold"],
	"wardrobe": ["Гардероб", "settings"], "history": ["Заказы", "quests"]}
const RAIL_ORDER := ["crystals", "starter", "vip", "battlepass", "resources", "heroes", "cosmetics", "seasonal", "lavka", "wardrobe", "history"]
const CUR := {"gold": "Золото", "crystals": "Кристаллы", "summon_essence": "Эссенция призыва",
	"ancient_seals": "Печатные знаки", "guild_marks": "Знаки гильдии", "nature_essence": "Эссенция природы"}
const GOLD_C := Color("#e6b452")


func setup(m: Node, p: Dictionary) -> void:
	main = m
	tab = p.get("tab", "crystals")
	main.use_world("none")
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.offset_left = 10
	root.offset_right = -10
	root.offset_top = 4
	root.add_theme_constant_override("separation", 8)
	add_child(root)
	root.add_child(_plaque())
	if Game.test_mode:
		var t := UI.label("ТЕСТОВЫЙ РЕЖИМ · покупки без списаний", 23, Color("#7fe39a"), true)
		t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		root.add_child(t)
	var h := HBoxContainer.new()
	h.size_flags_vertical = Control.SIZE_EXPAND_FILL
	h.add_theme_constant_override("separation", 10)
	root.add_child(h)
	var rs := ScrollContainer.new()
	rs.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	rs.custom_minimum_size = Vector2(176, 0)
	_rail = VBoxContainer.new()
	_rail.add_theme_constant_override("separation", 8)
	_rail.custom_minimum_size = Vector2(168, 0)
	rs.add_child(_rail)
	h.add_child(rs)
	var frame := PanelContainer.new()
	frame.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var fsb := UI._flat(Color(0.03, 0.09, 0.11, 0.92), Color(GOLD_C, 0.55), 16, 2)
	fsb.content_margin_left = 10
	fsb.content_margin_right = 10
	fsb.content_margin_top = 10
	fsb.content_margin_bottom = 10
	frame.add_theme_stylebox_override("panel", UI.skin(fsb, "ui/panels/glass.png", 512, 64))
	h.add_child(frame)
	_body = VBoxContainer.new()
	_body.add_theme_constant_override("separation", 14)
	frame.add_child(UI.scroll(_body))
	UI.keep_wrapped(_body)
	_body.add_child(UI.skeleton(3, 220))
	_load()


## Ornate title plaque «Магазин» (admin slot ui/shop/title_plaque.png, otherwise drawn).
func _plaque() -> Control:
	var c := CenterContainer.new()
	var p := PanelContainer.new()
	p.custom_minimum_size = Vector2(560, 96)
	var sb := UI._flat(Color("#0d2a2c"), GOLD_C, 18, 3)
	sb.shadow_color = Color(1.0, 0.75, 0.3, 0.35)
	sb.shadow_size = 10
	p.add_theme_stylebox_override("panel", UI.skin(sb, "ui/shop/title_plaque.png", 880, 60))
	var t := UI.title("Магазин", 56)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	p.add_child(t)
	c.add_child(p)
	return c


func _load() -> void:
	var r := await Api.get_json("/shop")
	if not is_inside_tree():
		return
	if not r.ok:
		for c in _body.get_children():
			c.queue_free()
		_body.add_child(UI.state("offline" if int(r.get("status", 0)) == 0 else "error", "Магазин не загрузился.", "Повторить", _load))
		return
	data = r.data
	Game.test_mode = data.get("test_mode", true)
	_render_tabs()
	_render()


func _render_tabs() -> void:
	for c in _rail.get_children():
		c.queue_free()
	var have := {}
	for s in data.get("sections", []) + EXTRA_TABS:
		have[s[0]] = s[1]
	for key in RAIL_ORDER:
		if not have.has(key):
			continue
		_rail.add_child(_rail_button(key, String(RAIL[key][0]), String(RAIL[key][1])))


func _rail_button(key: String, caption: String, icon: String) -> Button:
	var active := key == tab
	var b := Button.new()
	b.custom_minimum_size = Vector2(164, 140)
	b.focus_mode = Control.FOCUS_NONE
	var sb := UI._flat(Color("#4a3210") if active else Color(0.03, 0.1, 0.12, 0.95), GOLD_C if active else Color(GOLD_C, 0.45), 14, 3 if active else 2)
	if active:
		sb.shadow_color = Color(1.0, 0.75, 0.3, 0.45)
		sb.shadow_size = 12
	var path := "ui/shop/rail_active.png" if active else "ui/shop/rail.png"
	for st in ["normal", "hover", "pressed"]:
		b.add_theme_stylebox_override(st, UI.skin(sb, path, 256, 48))
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ic := GameIcon.new()
	ic.kind = icon
	ic.custom_minimum_size = Vector2(62, 62)
	ic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(ic)
	var l := UI.label(caption, 22, Color("#fff1c9") if active else Color("#e8efe9"), true)
	l.custom_minimum_size.x = 150
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(l)
	b.add_child(v)
	b.pressed.connect(func(): Sfx.play("click"); tab = key; _render_tabs(); _render())
	return b


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
			_banner()
			_render_products("vip")
			await _render_vip()
			await _render_subscriptions()
		"battlepass":
			_banner()
			_render_products("battlepass")
			await _render_battlepass()
		_:
			_banner()
			_render_products(tab)


func _section_title(text: String) -> Control:
	var h := HBoxContainer.new()
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_theme_constant_override("separation", 12)
	for side in [0, 1]:
		var line := ColorRect.new()
		line.color = Color(GOLD_C, 0.5)
		line.custom_minimum_size = Vector2(90, 2)
		line.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		if side == 1:
			h.add_child(UI.label("◆", 22, UI.TEAL))
			var t := UI.title(text, 40)
			h.add_child(t)
			h.add_child(UI.label("◆", 22, UI.TEAL))
		h.add_child(line)
	return h


# ------------------------------------------------------------------ banner (real offers only)
## Featured real offer: discounted / seasonal / starter item that is available now. No invented promotions.
func _banner() -> void:
	var pick = null
	var score := -1
	for it in data.get("items", []):
		if not it.available:
			continue
		var sc := int(it.discount_pct) * 10 + (40 if it.section == "seasonal" else 0) + (30 if it.section == "starter" else 0) + int(it.get("featured", 0)) * 5
		if it.section == tab:
			sc += 100
		if sc > score:
			score = sc
			pick = it
	if pick == null:
		return
	var it: Dictionary = pick
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(0, 300)
	card.add_theme_stylebox_override("panel", UI._flat(Color("#102a33"), GOLD_C, 16, 3))
	card.clip_contents = true
	var tex := UI.art("ui/shop/banner_%s.png" % String(it.section))
	var bg := TextureRect.new()
	bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if tex:
		bg.texture = tex
	else:
		var g := Gradient.new()
		g.set_color(0, Color("#1d4a55"))
		g.set_color(1, Color("#2a1840"))
		var gt := GradientTexture2D.new()
		gt.gradient = g
		gt.width = 64
		gt.height = 16
		bg.texture = gt
	card.add_child(bg)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var pic := _product_art(it, Vector2(260, 260))
	if tex == null:
		h.add_child(pic)
	else:
		h.add_child(UI.expand())
	var v := VBoxContainer.new()
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var t := UI.title(String(it.name), 36)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	t.add_theme_constant_override("line_spacing", -8)
	v.add_child(t)
	var sub := UI.label(_short(it), 25, UI.TEXT, true)
	sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(sub)
	var tags := []
	if int(it.discount_pct) > 0:
		tags.append("Скидка −%d%%" % int(it.discount_pct))
	if it.expires_at:
		tags.append("до " + UI.local_time(String(it.expires_at)))
	if tags.size() > 0:
		var tl := UI.label(" · ".join(tags), 24, UI.WARNING, true)
		tl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(tl)
	var b := _price_button(it)
	b.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	v.add_child(b)
	h.add_child(v)
	card.add_child(h)
	_body.add_child(card)


# ------------------------------------------------------------------ products (real money)
func _render_products(section: String) -> void:
	var list: Array = []
	for it in data.get("items", []):
		if it.section == section:
			list.append(it)
	var cap := ""
	for s in data.get("sections", []):
		if s[0] == section:
			cap = String(s[1])
	_body.add_child(_section_title(cap if cap != "" else "Предложения"))
	if list.is_empty():
		_body.add_child(UI.state("empty", "Сейчас здесь нет предложений."))
		return
	# «Выгодно»: the largest real bonus share among crystal packs
	var best_sku := ""
	var best := 0.0
	for it in list:
		var d: Dictionary = it.get("display", {})
		if float(d.get("base", 0)) > 0 and float(d.get("bonus", 0)) / float(d.base) > best:
			best = float(d.bonus) / float(d.base)
			best_sku = String(it.sku)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 14)
	for it in list:
		grid.add_child(_card(it, String(it.sku) == best_sku))
	_body.add_child(grid)
	if _pending_views.size() > 0:
		Api.post_json("/shop/offer-view", {"skus": _pending_views.duplicate()})
		_pending_views.clear()


## Product picture: admin slot ui/shop/items/<sku>.png, otherwise a large icon of what the pack gives.
func _product_art(it: Dictionary, sz: Vector2) -> Control:
	var tex := UI.art("ui/shop/items/%s.png" % String(it.sku))
	if tex:
		var r := TextureRect.new()
		r.texture = tex
		r.custom_minimum_size = sz
		r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		r.mouse_filter = Control.MOUSE_FILTER_IGNORE
		return r
	var kind: String = {"crystals": "crystals", "starter": "afk", "resources": "afk", "vip": "crown", "battlepass": "campaign",
		"heroes": "heroes", "cosmetics": "profile", "seasonal": "events"}.get(String(it.section), "shop")
	var cur: Dictionary = it.contents.get("currencies", {})
	if it.section != "crystals" and cur.size() == 1:
		kind = String(cur.keys()[0])
	var ic := GameIcon.new()
	ic.kind = kind
	ic.custom_minimum_size = sz * 0.62
	ic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var c := CenterContainer.new()
	c.custom_minimum_size = sz
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.add_child(ic)
	return c


func _short(it: Dictionary) -> String:
	var d: Dictionary = it.get("display", {})
	if int(d.get("base", 0)) > 0:
		return "%s кристаллов" % Game.exact(int(d.base) + int(d.get("bonus", 0))) + (" (бонус +%d)" % int(d.bonus) if int(d.get("bonus", 0)) > 0 else "")
	var t := _contents_text(it.contents)
	return t if t.length() <= 70 else t.substr(0, 68) + "…"


func _price_button(it: Dictionary) -> Button:
	var b := UI.button(Game.rub(it.price_rub), "primary" if it.available else "dim", 230, 80)
	b.add_theme_font_size_override("font_size", 32)
	var gold := UI._flat(Color("#e2b34e"), Color("#fbe3a2"), 40, 3)
	gold.shadow_color = Color(1.0, 0.7, 0.2, 0.35)
	gold.shadow_size = 6
	if it.available:
		for st in ["normal", "hover", "pressed"]:
			b.add_theme_stylebox_override(st, UI.skin(gold, "ui/shop/price_button.png", 400, 50, Color(1.1, 1.1, 1.1) if st == "hover" else (Color(0.85, 0.85, 0.85) if st == "pressed" else Color.WHITE)))
	else:
		b.disabled = true
		b.text = {"limit_reached": "Куплено", "owned": "Активно", "locked_until": "Скоро", "ended": "Завершено"}.get(it.unavailable_reason, "Недоступно")
	b.pressed.connect(func(): _details(it))
	return b


func _card(it: Dictionary, best_value := false) -> Control:
	var card := Button.new()
	card.custom_minimum_size = Vector2(0, 360 if int(it.get("display", {}).get("base", 0)) > 0 else 430)
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.focus_mode = Control.FOCUS_NONE
	var sb := UI._flat(Color(0.04, 0.12, 0.15, 0.95), GOLD_C if int(it.discount_pct) > 0 or best_value else Color(GOLD_C, 0.5), 16, 2)
	for st in ["normal", "hover", "pressed"]:
		card.add_theme_stylebox_override(st, UI.skin(sb, "ui/shop/item_card.png", 384, 48, Color(1.1, 1.1, 1.1) if st == "hover" else Color.WHITE))
	card.pressed.connect(func(): _details(it))
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.offset_left = 8
	v.offset_right = -8
	v.offset_top = 10
	v.offset_bottom = -10
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 4)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var d: Dictionary = it.get("display", {})
	if int(d.get("base", 0)) == 0:
		var nm := UI.label(String(it.name), 23, UI.GOLD, true)
		nm.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		nm.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		nm.max_lines_visible = 2
		nm.custom_minimum_size.y = 62
		nm.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(nm)
	var pic := _product_art(it, Vector2(220, 150))
	pic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	v.add_child(pic)
	if int(d.get("base", 0)) > 0:
		var amt := HBoxContainer.new()
		amt.alignment = BoxContainer.ALIGNMENT_CENTER
		amt.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ci := GameIcon.new()
		ci.kind = "crystals"
		ci.custom_minimum_size = Vector2(40, 40)
		ci.mouse_filter = Control.MOUSE_FILTER_IGNORE
		amt.add_child(ci)
		amt.add_child(UI.label(Game.exact(int(d.base) + int(d.get("bonus", 0))), 34, UI.TEXT, true))
		v.add_child(amt)
		if int(d.get("bonus", 0)) > 0:
			var bl := UI.label("включая бонус +%d" % int(d.bonus), 21, Color("#9fe0ff"))
			bl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			v.add_child(bl)
	else:
		var sl := UI.label(_short(it), 20, UI.MUTED)
		sl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		sl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		sl.max_lines_visible = 2
		v.add_child(sl)
	if int(it.discount_pct) > 0:
		var ol := UI.label("было %s" % Game.rub(it.base_price_rub), 20, Color("#ffb3a8"))
		ol.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(ol)
	var pb := _price_button(it)
	pb.custom_minimum_size = Vector2(0, 70)
	v.add_child(pb)
	card.add_child(v)
	# ribbon from real data
	var rib := ""
	if int(it.discount_pct) > 0:
		rib = "−%d%%" % int(it.discount_pct)
	elif best_value:
		rib = "Выгодно"
	elif int(it.get("featured", 0)) > 0:
		rib = "Популярно"
	elif it.limit and it.available:
		rib = "Ограничено"
	if rib != "":
		var r := PanelContainer.new()
		var rsb := UI._flat(Color("#b3261e"), Color("#ffcf7a"), 8, 2)
		rsb.content_margin_left = 10
		rsb.content_margin_right = 10
		r.add_theme_stylebox_override("panel", UI.skin(rsb, "ui/shop/ribbon.png", 256, 24))
		r.add_child(UI.label(rib, 21, Color.WHITE, true))
		r.set_anchors_preset(Control.PRESET_TOP_RIGHT)
		r.position = Vector2(-10, -12)
		r.grow_horizontal = Control.GROW_DIRECTION_BEGIN
		r.mouse_filter = Control.MOUSE_FILTER_IGNORE
		card.add_child(r)
	if not _seen.has(it.sku):
		_seen[it.sku] = true
		_pending_views.append(it.sku)
	return card


## Purchase transparency: full contents, limits, expiry and price before paying.
func _details(it: Dictionary) -> void:
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.gui_input.connect(func(e: InputEvent):
		if e is InputEventMouseButton and e.pressed:
			root.queue_free())
	root.add_child(dim)
	var p := UI.solid_panel(Color("#ffe1a0"))
	p.set_anchors_preset(Control.PRESET_CENTER)
	p.custom_minimum_size = Vector2(900, 0)
	p.position = Vector2(-450, -560)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	var t := UI.title(String(it.name), 44)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
	var pic := _product_art(it, Vector2(360, 260))
	pic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	v.add_child(pic)
	if String(it.get("desc", "")) != "":
		var d := UI.label(String(it.desc), 26, UI.MUTED)
		d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(d)
	v.add_child(UI.label("Состав:", 28, UI.ACCENT, true))
	var ct := UI.label(_contents_text(it.contents).replace(" · ", "\n"), 27, UI.TEXT)
	ct.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(ct)
	var meta := []
	if it.limit:
		meta.append("Лимит: %d из %d (%s)" % [int(it.bought), int(it.limit.count), {"once": "навсегда", "week": "в неделю",
			"month": "за 30 дней", "season": "за сезон", "event": "за событие", "day": "в день"}.get(it.limit.period, it.limit.period)])
	if it.expires_at:
		meta.append("Доступно до " + UI.local_time(String(it.expires_at)))
	if int(it.discount_pct) > 0:
		meta.append("Скидка −%d%%, обычная цена %s" % [int(it.discount_pct), Game.rub(it.base_price_rub)])
	if String(it.get("personal_reason", "")) != "":
		meta.append("Для вас: " + String(it.personal_reason))
	if Game.test_mode:
		meta.append("Тестовый режим: деньги не списываются")
	if meta.size() > 0:
		var ml := UI.label("\n".join(meta), 24, UI.MUTED)
		ml.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(ml)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	var cancel := UI.button("Закрыть", "glass", 0, 92)
	cancel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cancel.pressed.connect(root.queue_free)
	row.add_child(cancel)
	var buy := UI.button("Купить за " + Game.rub(it.price_rub), "primary" if it.available else "dim", 0, 92)
	buy.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	buy.disabled = not it.available
	buy.pressed.connect(func(): root.queue_free(); _purchase(it))
	row.add_child(buy)
	v.add_child(row)
	p.add_child(v)
	root.add_child(p)
	main.ui.add_child(root)
	UI.pop_in(p)


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
	var p := UI.solid_panel()
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
		card.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.5), Color(1, 1, 1, 0.2), 22, 2))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 10)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.custom_minimum_size.x = 200
		info.add_child(UI.label("%s  ·  %s" % [it.name, "день" if it.kind == "daily" else "неделя"], 28, UI.GOLD, true))
		info.add_child(UI.label(_contents_text(it.contents) + "   (%d/%d)" % [int(it.bought), int(it.limit)], 23))
		h.add_child(info)
		var cost := HBoxContainer.new()
		cost.add_child(UI.rewards_row(it.cost, 26))
		h.add_child(cost)
		var b := UI.button("Купить", "primary" if int(it.bought) < int(it.limit) else "dim", 170, 84)
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
			hist.append("%+d %s" % [int(hrow.delta), {"purchase": "покупка", "purchase_test": "тест-покупка",
				"daily": "активность", "achievement": "достижение"}.get(String(hrow.source), String(hrow.source))])
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
	var lv_l := UI.label("Уровень %d · опыт %d (уровень = %d опыта) · до %s" % [int(bp.level), int(bp.xp), int(bp.xp_per_level),
		String(bp.ends).substr(0, 10)], 24)
	lv_l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	head.add_child(lv_l)
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
		row.add_theme_constant_override("separation", 14)
		row.add_child(UI.label("%2d" % n, 30, UI.GOLD if n <= int(bp.level) else UI.MUTED, true))
		for track in ["free", "premium"]:
			var col := VBoxContainer.new()
			col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var tl := UI.label(("Бесплатно: " if track == "free" else "Premium: ") + _contents_text(lvl[track]), 24,
				UI.TEXT if track == "free" or bp.premium else UI.MUTED)
			tl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			tl.custom_minimum_size.x = 120
			col.add_child(tl)
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
		"ability_effect": "Эффекты способностей", "emote": "Эмоции", "fortress": "Оформление каравана"}
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
		main.use_world("none").show_hero(code if code != "" else "azamat")
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
