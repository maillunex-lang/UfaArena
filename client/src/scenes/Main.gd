extends Node
## Main shell: 3D world (fortress / campaign map) + Liquid Glass UI:
## top resources bar, bottom navigation, context buttons, screen container.

const HubWorld := preload("res://src/world/HubWorld.gd")
const CampaignMap := preload("res://src/world/CampaignMap.gd")
const SCREENS := {
	"home": preload("res://src/screens/HomeScreen.gd"),
	"campaign": preload("res://src/screens/CampaignScreen.gd"),
	"heroes": preload("res://src/screens/HeroesScreen.gd"),
	"summon": preload("res://src/screens/SummonScreen.gd"),
	"fortress": preload("res://src/screens/CaravanScreen.gd"),  # old key kept: links and saved params still work
	"caravan": preload("res://src/screens/CaravanScreen.gd"),
	"quests": preload("res://src/screens/QuestsScreen.gd"),
	"mail": preload("res://src/screens/MailScreen.gd"),
	"settings": preload("res://src/screens/SettingsScreen.gd"),
	"formation": preload("res://src/screens/FormationScreen.gd"),
	"shop": preload("res://src/screens/ShopScreen.gd"),
	"chat": preload("res://src/screens/ChatScreen.gd"),
	"friends": preload("res://src/screens/FriendsScreen.gd"),
	"guild": preload("res://src/screens/GuildScreen.gd"),
	"raids": preload("res://src/screens/RaidsScreen.gd"),
	"arena": preload("res://src/screens/ArenaScreen.gd"),
	"tournaments": preload("res://src/screens/TournamentsScreen.gd"),
	"events": preload("res://src/screens/EventsScreen.gd"),
	"rankings": preload("res://src/screens/RankingsScreen.gd"),
	"world": preload("res://src/screens/WorldScreen.gd"),
	"more": preload("res://src/screens/MoreScreen.gd"),
	"profile": preload("res://src/screens/ProfileScreen.gd"),
	"inventory": preload("res://src/screens/InventoryScreen.gd"),
}
const Notifications := preload("res://src/ui/Notifications.gd")
const Tips := preload("res://src/ui/Tips.gd")
const UpdateDialog := preload("res://src/ui/UpdateDialog.gd")
const UIOverrides := preload("res://src/ui/UIOverrides.gd")
## Fixed order of the six main sections (design brief §4).
const NAV := [["home", "Главная"], ["heroes", "Герои"], ["campaign", "Поход"], ["guild", "Гильдия"], ["world", "Мир"],
	["more", "Ещё"]]
## Which section stays highlighted for a secondary screen.
const NAV_OF := {"formation": "heroes", "summon": "more", "quests": "more", "mail": "more", "shop": "more", "friends": "more",
	"chat": "more", "settings": "more", "profile": "more", "inventory": "more", "rankings": "more", "fortress": "home", "caravan": "home",
	"raids": "world", "arena": "world", "tournaments": "world", "events": "world"}

var world: Node3D
var world_kind := ""
var ui: Control
var content: Control
var current := ""
var screen: Control
var _chips := {}
var _nav_buttons := {}
var _nav_panel: Control
var _uo_pending := false
var _guide: PanelContainer
var _guide_label: Label
var _profile_lbl: Label
var _avatar: PanelContainer


func _ready() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 10
	add_child(layer)
	ui = Control.new()
	ui.theme = UI.theme()
	ui.set_anchors_preset(Control.PRESET_FULL_RECT)
	ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(ui)
	content = Control.new()
	content.set_anchors_preset(Control.PRESET_FULL_RECT)
	content.offset_top = 230
	content.offset_bottom = -230
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(content)
	_build_top()
	Game.load_cached_layout()
	_build_nav()
	Game.layout_changed.connect(_on_layout_changed)
	get_tree().node_added.connect(_on_node_added)
	_build_guide()
	Game.wallet_changed.connect(_update_chips)
	Game.profile_changed.connect(_update_profile)
	_update_chips()
	_update_profile()
	Sfx.music("hub")
	if not Game.loaded:
		Router.busy(true)
		var r := await Game.bootstrap()
		Router.busy(false)
		if not r.ok:
			Router.error(r)
	Content.activated.connect(_on_content_activated)
	Content.pending_ready.connect(func(_v): if current == "home": Content.apply_pending())
	_build_download_chip()
	open(Router.params.get("screen", "home"), Router.params.get("params", {}))
	UpdateDialog.check(ui)
	_check_onboarding()
	Content.start_background()


# ------------------------------------------------------------------ worlds
func use_world(kind: String) -> Node3D:
	if world_kind == kind and (world or kind == "none"):
		return world
	if world:
		world.queue_free()
		world = null
	world_kind = kind
	if _bg:
		_bg.visible = kind == "none"
	if kind == "none":  # dashboards and menus: no 3D scene behind (saves GPU/battery)
		return null
	if kind == "campaign":
		world = CampaignMap.new()
	else:
		world = HubWorld.new()
	add_child(world)
	move_child(world, 0)
	return world


# ------------------------------------------------------------------ screens
func open(screen_name: String, params := {}) -> void:
	if screen_name == "home" and Content.has_pending():
		await Content.apply_pending()
	if screen:
		screen.queue_free()
	current = screen_name
	screen = SCREENS[screen_name].new()
	screen.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(screen)
	if screen.has_method("setup"):
		screen.setup(self, params)
	_enter_anim(screen, screen_name)
	var section: String = screen_name if _nav_buttons.has(screen_name) else NAV_OF.get(screen_name, screen_name)
	if not _nav_buttons.has(section):
		section = "more"
	for k in _nav_buttons:
		_style_nav(k, k == section)
	for tip in get_tree().get_nodes_in_group("tip_card"):
		tip.queue_free()
	_check_onboarding()
	Tips.maybe_show(self, screen_name)


## Contextual entrance per section (brief §24): heroes slide in from the side, maps fade with a slight zoom,
## the shop rises from below, everything else fades. Short (≤0.2 s); off with reduced motion.
func _enter_anim(c: Control, name: String) -> void:
	if UI.reduce_motion():
		return
	c.modulate.a = 0.0
	var tw := c.create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(c, "modulate:a", 1.0, 0.18)
	match name:
		"heroes", "formation", "profile":
			c.position.x = 60
			tw.tween_property(c, "position:x", 0.0, 0.2)
		"shop", "summon":
			c.position.y = 50
			tw.tween_property(c, "position:y", 0.0, 0.2)
		"campaign", "world":
			c.pivot_offset = content.size / 2
			c.scale = Vector2(1.03, 1.03)
			tw.tween_property(c, "scale", Vector2.ONE, 0.22)


## Modal overlay above content (full screen within bars).
func modal(node: Control) -> void:
	node.set_anchors_preset(Control.PRESET_FULL_RECT)
	content.add_child(node)


var _bg: TextureRect
var _bell: Button
var _bell_badge: PanelContainer
var badges := {}
var summary := {}
var _sum_t := 0.0


func _build_background() -> void:
	_bg = TextureRect.new()
	var art := UI.art("ui/app_bg.png")
	if art:
		_bg.texture = art
	else:
		var g := Gradient.new()
		g.set_color(0, Color("#13232a"))
		g.set_color(1, UI.BG)
		var gt := GradientTexture2D.new()
		gt.gradient = g
		gt.fill_from = Vector2(0.5, 0)
		gt.fill_to = Vector2(0.5, 1)
		gt.width = 8
		gt.height = 256
		_bg.texture = gt
	_bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_bg.stretch_mode = TextureRect.STRETCH_SCALE
	_bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_bg.visible = false
	var layer := CanvasLayer.new()
	layer.layer = -1
	add_child(layer)
	layer.add_child(_bg)


func _build_top() -> void:
	_build_background()
	var bar_bg := Panel.new()
	bar_bg.set_anchors_preset(Control.PRESET_TOP_WIDE)
	bar_bg.offset_bottom = 214
	bar_bg.add_theme_stylebox_override("panel", UI.skin(UI._flat(Color(UI.BG, 0.88), Color.TRANSPARENT, 0, 0), "ui/topbar.png", 1080, 0))
	bar_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(bar_bg)
	var line := ColorRect.new()
	line.color = Color(UI.GOLD_DARK, 0.6)
	line.set_anchors_preset(Control.PRESET_TOP_WIDE)
	line.offset_top = 212
	line.offset_bottom = 214
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(line)
	var bar := HBoxContainer.new()
	bar.set_anchors_preset(Control.PRESET_TOP_WIDE)
	bar.offset_top = 60
	bar.offset_left = UI.SP.m
	bar.offset_right = -UI.SP.m
	bar.offset_bottom = 200
	bar.add_theme_constant_override("separation", UI.SP.s)
	ui.add_child(bar)
	var prof := Button.new()
	prof.flat = true
	prof.focus_mode = Control.FOCUS_NONE
	prof.custom_minimum_size = Vector2(280, 120)
	for st in ["normal", "hover", "pressed"]:
		prof.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	var ph := HBoxContainer.new()
	ph.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ph.add_theme_constant_override("separation", UI.SP.s)
	var av := PanelContainer.new()
	_avatar = av
	av.add_theme_stylebox_override("panel", UI._round_glass())
	av.custom_minimum_size = Vector2(104, 104)
	av.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var avi := GameIcon.new()
	avi.kind = "profile"
	avi.mouse_filter = Control.MOUSE_FILTER_IGNORE
	av.add_child(avi)
	ph.add_child(av)
	_profile_lbl = UI.label("", 26, UI.TEXT, true)
	_profile_lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ph.add_child(_profile_lbl)
	prof.add_child(ph)
	prof.pressed.connect(func(): open("profile"))
	bar.add_child(prof)
	bar.add_child(UI.expand())
	var chips := GridContainer.new()
	chips.columns = 2
	chips.add_theme_constant_override("h_separation", UI.SP.xs)
	chips.add_theme_constant_override("v_separation", UI.SP.xs)
	for k in ["gold", "crystals", "summon_essence", "nature_essence"]:
		var chip := UI.chip(k, "0")
		chip.custom_minimum_size = Vector2(196, 0)
		var hit := Button.new()
		hit.flat = true
		hit.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		hit.focus_mode = Control.FOCUS_NONE
		hit.pressed.connect(func(): open("inventory"))
		chip.add_child(hit)
		_chips[k] = chip
		chips.add_child(chip)
	bar.add_child(chips)
	# global search (brief §22)
	var find_b := UI.button("", "glass", 92, 92)
	find_b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var fi := GameIcon.new()
	fi.kind = "search"
	fi.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	fi.offset_left = 14
	fi.offset_right = -14
	fi.offset_top = 14
	fi.offset_bottom = -14
	fi.mouse_filter = Control.MOUSE_FILTER_IGNORE
	find_b.add_child(fi)
	find_b.tooltip_text = "Поиск"
	find_b.pressed.connect(func():
		var gs: Control = preload("res://src/ui/GlobalSearch.gd").new()
		gs.main = self
		ui.add_child(gs))
	bar.add_child(find_b)
	# mini chat over any screen (brief §16)
	var chat_b := UI.button("", "glass", 92, 92)
	chat_b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var ci := GameIcon.new()
	ci.kind = "chat"
	ci.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ci.offset_left = 14
	ci.offset_right = -14
	ci.offset_top = 14
	ci.offset_bottom = -14
	ci.mouse_filter = Control.MOUSE_FILTER_IGNORE
	chat_b.add_child(ci)
	chat_b.tooltip_text = "Чат"
	chat_b.pressed.connect(open_mini_chat)
	bar.add_child(chat_b)
	_bell = UI.button("", "glass", 92, 92)
	_bell.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var bi := GameIcon.new()
	bi.kind = "bell"
	bi.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bi.offset_left = 14
	bi.offset_right = -14
	bi.offset_top = 14
	bi.offset_bottom = -14
	bi.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_bell.add_child(bi)
	_bell_badge = UI.badge(0)
	_bell_badge.position = Vector2(56, -8)
	_bell.add_child(_bell_badge)
	_bell.pressed.connect(_open_notifications)
	bar.add_child(_bell)


func open_mini_chat() -> void:
	var c: Control = preload("res://src/ui/MiniChat.gd").new()
	c.main = self
	ui.add_child(c)


func _open_notifications() -> void:
	var n: Control = Notifications.new()
	n.main = self
	n.data = summary
	ui.add_child(n)
	_refresh_summary()


func _refresh_summary() -> void:
	var r := await Api.get_json("/player/summary")
	if r.ok:
		set_badges(r.data)


## Badges on the bell and nav from the server summary (merged per category).
func set_badges(s: Dictionary) -> void:
	if not summary.is_empty() and summary != s:
		_live_toasts(summary, s)
	summary = s
	var soc: Dictionary = s.get("social", {})
	var afk: Dictionary = s.get("afk", {})
	badges = {"quests": int(s.get("quests", {}).get("claimable", 0)), "mail": int(s.get("mail_unclaimed", 0)),
		"friends": int(soc.get("friend_requests", 0)) + int(soc.get("gifts", 0)), "chat": int(soc.get("chat_unread", 0)),
		"guild": int(soc.get("guild_apps", 0)), "afk": 1 if afk.get("full", false) else 0}
	# the bell only counts categories the player kept enabled in Settings → Уведомления
	var on := func(k: String) -> int: return 1 if bool(Config.settings.get("notify_" + k, true)) else 0
	var total: int = (badges.quests + badges.mail + badges.afk) * on.call("rewards") \
		+ (badges.friends + (1 if badges.chat > 0 else 0)) * on.call("social") + badges.guild * on.call("guild")
	if is_instance_valid(_bell_badge):
		_bell_badge.visible = total > 0
		(_bell_badge.get_child(0) as Label).text = str(total) if total < 100 else "99+"
	_nav_badge("home", badges.quests + badges.afk)
	_nav_badge("guild", badges.guild)
	_nav_badge("more", badges.mail + badges.friends)


var _toasted_events := {}


## Live notifications (brief §18): compares the previous and the new server summary and shows ONE merged toast for
## what appeared since the last check; categories switched off in Settings are skipped; event deadlines once per event.
func _live_toasts(a: Dictionary, b: Dictionary) -> void:
	var on := func(k: String) -> bool: return bool(Config.settings.get("notify_" + k, true))
	var parts: Array = []
	var sa: Dictionary = a.get("social", {})
	var sb: Dictionary = b.get("social", {})
	if on.call("rewards"):
		if b.get("afk", {}).get("full", false) and not a.get("afk", {}).get("full", false):
			parts.append("сундук «Дозор» полон")
		var dq := int(b.get("quests", {}).get("claimable", 0)) - int(a.get("quests", {}).get("claimable", 0))
		if dq > 0:
			parts.append("выполнено заданий: %d" % dq)
		var dm := int(b.get("mail_unclaimed", 0)) - int(a.get("mail_unclaimed", 0))
		if dm > 0:
			parts.append("новых писем с наградами: %d" % dm)
	if on.call("social"):
		var df := int(sb.get("friend_requests", 0)) - int(sa.get("friend_requests", 0))
		if df > 0:
			parts.append("заявок в друзья: %d" % df)
		var dg := int(sb.get("gifts", 0)) - int(sa.get("gifts", 0))
		if dg > 0:
			parts.append("подарков: %d" % dg)
	if on.call("guild"):
		var da := int(sb.get("guild_apps", 0)) - int(sa.get("guild_apps", 0))
		if da > 0:
			parts.append("заявок в гильдию: %d" % da)
	if on.call("events"):
		var old_ids := {}
		for e in a.get("events", []):
			old_ids[String(e.id)] = true
		for e in b.get("events", []):
			var id := String(e.id)
			if not old_ids.has(id) and not _toasted_events.has(id + ":start"):
				_toasted_events[id + ":start"] = true
				parts.append("началось событие «%s»" % e.name)
			var left := Time.get_unix_time_from_datetime_string(String(e.ends_at).substr(0, 19)) - Time.get_unix_time_from_system()
			if left > 0 and left < 3600 and not _toasted_events.has(id + ":end"):
				_toasted_events[id + ":end"] = true
				parts.append("событие «%s» заканчивается меньше чем через час" % e.name)
	if parts.size() > 0 and current != "" and screen != null:
		Router.toast("Новое: " + ", ".join(parts))


func _nav_badge(key: String, n: int) -> void:
	if not _nav_buttons.has(key):
		return
	var b: Button = _nav_buttons[key]
	var dot := b.get_node_or_null("Badge")
	if dot:
		dot.visible = n > 0


func _process(delta: float) -> void:
	_sum_t += delta
	if _sum_t > 45.0 and Game.loaded:
		_sum_t = 0.0
		_refresh_summary()


func _update_chips() -> void:
	for k in _chips:
		var lbl: Label = _chips[k].find_child("Value", true, false)
		var nv := Game.fmt(Game.wallet.get(k, 0))
		if lbl.text != nv and lbl.text != "0":
			var c: Control = _chips[k]
			c.pivot_offset = c.size / 2
			var tw := c.create_tween()
			tw.tween_property(c, "scale", Vector2(1.12, 1.12), 0.08)
			tw.tween_property(c, "scale", Vector2.ONE, 0.12)
		lbl.text = nv


func _update_profile() -> void:
	var p := Game.profile
	var title := ""
	var t: Variant = Game.cosmetics.get("title")
	if t is Dictionary:
		title = "\n«%s»" % String(t.get("data", {}).get("text", ""))
	var vipl := int(p.get("vip_level", 0))
	_profile_lbl.text = "%s\nУр. %d%s\n⚔ %s" % [p.get("nickname", "Хранитель"), int(p.get("level", 1)),
		("  · VIP %d" % vipl) if vipl > 0 else "", Game.fmt(Game.team_power())]
	if _avatar:
		var sb := UI._round_glass()
		var fr: Variant = Game.cosmetics.get("frame")
		if fr is Dictionary:
			sb.border_color = Color(String(fr.get("data", {}).get("color", "#ffffff")))
			sb.set_border_width_all(6)
		var fx: Variant = Game.cosmetics.get("profile_effect")
		if fx is Dictionary:
			sb.shadow_color = Color(String(fx.get("data", {}).get("color", "#ffffff")), 0.8)
			sb.shadow_size = 22
		_avatar.add_theme_stylebox_override("panel", sb)


func _build_nav() -> void:
	var panel := UI.glass_panel(Color("#a9c9ff"), 44)
	var nav_skin := UI.skin(UI.glass_style(Color("#a9c9ff"), 44), "ui/navbar.png", 1040, 72)
	if nav_skin is StyleBoxTexture:
		panel.add_theme_stylebox_override("panel", nav_skin)
		panel.material = null
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 20
	panel.offset_right = -20
	panel.offset_top = -220
	panel.offset_bottom = -40
	ui.add_child(panel)
	var h := HBoxContainer.new()
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_theme_constant_override("separation", 6)
	panel.add_child(h)
	_nav_panel = panel
	_nav_buttons.clear()
	for item in nav_items():
		var b := UI.icon_button(String(item.icon), String(item.label), true)
		b.get_node("Badge").visible = false
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var key: String = item.id
		b.pressed.connect(func(): open(key))
		h.add_child(b)
		_nav_buttons[key] = b


## Bottom bar items: the admin layout (Редактор игры → Интерфейс) or the built-in six sections.
func nav_items() -> Array:
	var def := []
	var icons := {"home": "home", "heroes": "heroes", "campaign": "campaign", "guild": "guild", "world": "world", "more": "more"}
	for n in NAV:
		def.append({"id": n[0], "label": n[1], "icon": icons[n[0]]})
	var items: Array = Game.visible_items(Game.ui_part("nav", def), func(k): return SCREENS.has(k))
	if not items.any(func(x): return x.id == "home") or not items.any(func(x): return x.id == "more"):
		return def  # never lock the player out
	return items


## One place that knows what a layout button does (main screen columns, big buttons, «Ещё» tiles).
func do_action(id: String, from := "") -> void:
	match id:
		"achievements": open("quests", {"tab": "ach"})
		"chat":
			if from == "home":
				open_mini_chat()
			else:
				open("chat")
		"search":
			var gs: Control = preload("res://src/ui/GlobalSearch.gd").new()
			gs.main = self
			ui.add_child(gs)
		"battle":
			var nx = Game.campaign.get("next") if Game.campaign is Dictionary else null
			var code: String = String(nx.code) if nx is Dictionary else ""
			open("campaign", {"select": code} if code != "" else {})
		"equipment", "artifacts":
			Router.toast("Появится вместе с системой предметов в следующих обновлениях")
		"afk":  # patrol (AFK) rewards can be claimed from any button the admin placed
			var r := await Api.post_json("/rewards/afk/claim", {}, true)
			if not r.ok:
				Router.error(r)
				return
			Sfx.play("coins")
			Game.set_wallet(r.data.wallet)
			Router.toast("Дозор принёс: " + Game.rewards_text(r.data.rewards))
			await Game.refresh_afk()
			onboarding_event("afk")
		_:
			if SCREENS.has(id):
				open(id)


## Admin rules over the real interface (any screen + the shell): applied once per frame after nodes appear.
func _on_node_added(n: Node) -> void:
	if (n is Button or n is Label) and not _uo_pending:
		_uo_pending = true
		_apply_overrides.call_deferred()


func _apply_overrides() -> void:
	_uo_pending = false
	if is_instance_valid(screen):
		UIOverrides.apply(screen, current, self)
	if is_instance_valid(ui):
		UIOverrides.apply(ui, "main", self, content)


func _on_layout_changed() -> void:
	if _nav_panel:
		_nav_panel.queue_free()
		_nav_panel = null
	_build_nav()
	var section: String = current if _nav_buttons.has(current) else NAV_OF.get(current, current)
	for k in _nav_buttons:
		_style_nav(k, k == section)
	if current != "":
		open(current)  # rebuild with the new menu and screen rules
	_apply_overrides.call_deferred()


func _style_nav(key: String, active: bool) -> void:
	var b: Button = _nav_buttons[key]
	b.modulate = Color(1, 1, 1) if active else Color(0.82, 0.86, 0.95)
	b.pivot_offset = b.size / 2
	b.scale = Vector2(1.08, 1.08) if active else Vector2.ONE


# ------------------------------------------------------------------ content updates
var _dl_chip: PanelContainer
var _dl_label: Label


func _build_download_chip() -> void:
	_dl_chip = UI.glass_panel(Color("#bfe3ff"), 24)
	_dl_chip.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_dl_chip.offset_left = -200
	_dl_chip.offset_right = 200
	_dl_chip.offset_top = 196
	_dl_chip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_dl_label = UI.label("", 24, UI.TEXT, true)
	_dl_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_dl_chip.add_child(_dl_label)
	_dl_chip.visible = false
	ui.add_child(_dl_chip)
	Content.progress.connect(func(done: int, total: int):
		_dl_chip.visible = done < total
		_dl_label.text = "Загрузка обновления %d%%" % int(100.0 * done / max(total, 1)))
	Content.state_changed.connect(func(s: String, _i: String):
		if s != "downloading":
			_dl_chip.visible = false)


func _on_content_activated(v: int) -> void:
	Router.toast("Обновление контента применено (манифест v%d)" % v if v > 0 else "Контент-обновления отключены сервером")
	Models.clear_cache()
	Sfx.reload_music()
	if world_kind == "hub" and world:
		var code: String = world.hero_code
		world.queue_free()
		world = null
		world_kind = ""
		var w := use_world("hub")
		if code != "":
			w.show_hero(code)


# ------------------------------------------------------------------ onboarding guide
func _build_guide() -> void:
	_guide = UI.glass_panel(Color("#ffe1a0"))
	# sits just above the bottom navigation so it never covers dashboard content
	# sits under the campaign strip of the game panel, above the squad — never over buttons
	_guide.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_guide.offset_left = -360
	_guide.offset_right = 360
	_guide.offset_top = 352
	_guide.offset_bottom = 446
	# tap the hint to skip the whole tutorial (brief §21: it can be skipped entirely and replayed from Settings)
	_guide.mouse_filter = Control.MOUSE_FILTER_STOP
	_guide.gui_input.connect(func(e: InputEvent):
		if (e is InputEventMouseButton and e.pressed) or (e is InputEventScreenTouch and e.pressed):
			UI.confirm(ui, "Пропустить обучение?", "Подсказки шагов больше не появятся. Вернуть их можно в «Настройки» → «Обучение».",
				"Пропустить", func():
					await Game.advance_onboarding(6)
					_check_onboarding()))
	_guide_label = UI.label("", 28, UI.TEXT, true)
	_guide_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_guide_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_guide.add_child(_guide_label)
	_guide.visible = false
	ui.add_child(_guide)
	var tw := _guide.create_tween().set_loops()
	tw.tween_property(_guide, "modulate", Color(1.15, 1.1, 0.95), 0.8)
	tw.tween_property(_guide, "modulate", Color.WHITE, 0.8)


var _story_open := false
## Prologue «Ночь Раскола», scenes 1-2 (docs/lore/URALIA_MAIN_STORY.md §3); the next scenes play before stages 1-1…1-4.
const INTRO_STORY := [
	{"speaker": "narrator", "text": "Когда-то семь ветров хранили Уралию, а под горами спал Древний, скованный семью печатями. Об этом помнили только сказки."},
	{"speaker": "narrator", "text": "Таулар, край Одиноких Гор. Тихий вечер в речном селе у подножия Белой горы."},
	{"speaker": "aisylu", "text": "Опять слушаешь, как гора гудит? Кроме тебя её никто не слышит, знаешь?"},
	{"speaker": "bayras", "text": "Не приставай, Айсылу. А тебе пора на Заставу — Тимер ждёт в дозор. Вернись до рассвета."},
	{"speaker": "narrator", "text": "В полночь земля вздрогнула. Над вершиной ударили белые вспышки, а гул под горой стал голосом."},
	{"speaker": "azamat", "text": "Хранитель! Из реки поднимаются мертвецы! К переправе — люди ещё спят!"},
]


## Onboarding steps (server-persisted, monotonic):
## 0 intro story -> 1 fight 1-1 -> 2 claim mail -> 3 summon -> 4 formation -> 5 AFK -> 6 done
var _setup_open := false


func _check_onboarding() -> void:
	if not Game.loaded or _guide == null:
		return
	if bool(Game.profile.get("needs_setup", false)):  # hero creation: nickname + age (decision D-C1), once
		if not _setup_open:
			_setup_open = true
			var dlg: Control = preload("res://src/ui/HeroSetupDialog.gd").open(ui, true)
			await dlg.finished
			_setup_open = false
			_check_onboarding()
		return
	var step := int(Game.profile.get("onboarding_step", 0))
	var cleared: Array = Game.campaign.get("cleared", [])
	if step == 0 and current == "home" and not _story_open:
		_story_open = true
		var dlg: Control = preload("res://src/ui/StoryDialog.gd").new()
		ui.add_child(dlg)
		await dlg.play(INTRO_STORY)
		_story_open = false
		await Game.advance_onboarding(1)
		step = 1
	if step == 1 and "1-1" in cleared:
		await Game.advance_onboarding(2)
		step = 2
	var text := ""
	var nav_hint := ""
	match step:
		1:
			text = "Откройте «Поход» и пройдите бой «Ночная переправа»"
			nav_hint = "campaign"
		2: text = "На главной слева нажмите «Почта» — там ждут дары предков"
		3:
			text = "«Ещё» → «Призыв»: призовите нового героя"
			nav_hint = "more"
		4:
			text = "Герои → «Формация»: поставьте нового героя в отряд"
			nav_hint = "heroes"
		5: text = "На главной справа нажмите сундук «Дозор»"
	_guide.visible = text != "" and current == "home"
	_guide_label.text = (text + "\n(коснитесь, чтобы пропустить обучение)") if text != "" else ""
	_pulse_nav(nav_hint if nav_hint != current else "")


var _pulse_tw: Tween


func _pulse_nav(key: String) -> void:
	if _pulse_tw:
		_pulse_tw.kill()
		_pulse_tw = null
	for k in _nav_buttons:
		_style_nav(k, k == current)
	if key == "" or not _nav_buttons.has(key):
		return
	var b: Button = _nav_buttons[key]
	b.pivot_offset = b.size / 2
	_pulse_tw = b.create_tween().set_loops()
	_pulse_tw.tween_property(b, "scale", Vector2(1.16, 1.16), 0.45)
	_pulse_tw.parallel().tween_property(b, "modulate", Color(1.4, 1.25, 0.8), 0.45)
	_pulse_tw.tween_property(b, "scale", Vector2.ONE, 0.45)
	_pulse_tw.parallel().tween_property(b, "modulate", Color.WHITE, 0.45)


func onboarding_event(ev: String) -> void:
	var step := int(Game.profile.get("onboarding_step", 0))
	var advance := {"mail": 2, "summon": 3, "formation": 4, "afk": 5}
	if advance.has(ev) and step == advance[ev]:
		await Game.advance_onboarding(step + 1)
		if step + 1 == 6 or (ev == "afk"):
			await Game.advance_onboarding(6)
	_check_onboarding()
