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
	"fortress": preload("res://src/screens/FortressScreen.gd"),
	"modes": preload("res://src/screens/ModesScreen.gd"),
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
const UpdateDialog := preload("res://src/ui/UpdateDialog.gd")
## Fixed order of the six main sections (design brief §4).
const NAV := [["home", "Главная"], ["heroes", "Герои"], ["campaign", "Поход"], ["guild", "Гильдия"], ["world", "Мир"],
	["more", "Ещё"]]
## Which section stays highlighted for a secondary screen.
const NAV_OF := {"formation": "heroes", "summon": "more", "quests": "more", "mail": "more", "shop": "more", "friends": "more",
	"chat": "more", "settings": "more", "profile": "more", "inventory": "more", "rankings": "more", "fortress": "home",
	"raids": "world", "arena": "world", "tournaments": "world", "events": "world"}

var world: Node3D
var world_kind := ""
var ui: Control
var content: Control
var current := ""
var screen: Control
var _chips := {}
var _nav_buttons := {}
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
	_build_nav()
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
	var section: String = NAV_OF.get(screen_name, screen_name)
	for k in _nav_buttons:
		_style_nav(k, k == section)
	_check_onboarding()


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
	bar_bg.add_theme_stylebox_override("panel", UI._flat(Color(UI.BG, 0.88), Color.TRANSPARENT, 0, 0))
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
	prof.custom_minimum_size = Vector2(330, 120)
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
	summary = s
	var soc: Dictionary = s.get("social", {})
	var afk: Dictionary = s.get("afk", {})
	badges = {"quests": int(s.get("quests", {}).get("claimable", 0)), "mail": int(s.get("mail_unclaimed", 0)),
		"friends": int(soc.get("friend_requests", 0)) + int(soc.get("gifts", 0)), "chat": int(soc.get("chat_unread", 0)),
		"guild": int(soc.get("guild_apps", 0)), "afk": 1 if afk.get("full", false) else 0}
	var total: int = badges.quests + badges.mail + badges.friends + badges.guild + badges.afk + (1 if badges.chat > 0 else 0)
	if is_instance_valid(_bell_badge):
		_bell_badge.visible = total > 0
		(_bell_badge.get_child(0) as Label).text = str(total) if total < 100 else "99+"
	_nav_badge("home", badges.quests + badges.afk)
	_nav_badge("guild", badges.guild)
	_nav_badge("more", badges.mail + badges.friends)


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
	var icons := {"home": "home", "heroes": "heroes", "campaign": "campaign", "guild": "guild", "world": "world", "more": "more"}
	for item in NAV:
		var b := UI.icon_button(icons[item[0]], item[1], true)
		b.get_node("Badge").visible = false
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var key: String = item[0]
		b.pressed.connect(func(): open(key))
		h.add_child(b)
		_nav_buttons[key] = b


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
	_guide.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_guide.offset_left = -330
	_guide.offset_right = 330
	_guide.offset_top = 236
	_guide.offset_bottom = 330
	_guide.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_guide_label = UI.label("", 28, UI.TEXT, true)
	_guide_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_guide_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_guide.add_child(_guide_label)
	_guide.visible = false
	ui.add_child(_guide)
	var tw := _guide.create_tween().set_loops()
	tw.tween_property(_guide, "modulate", Color(1.15, 1.1, 0.95), 0.8)
	tw.tween_property(_guide, "modulate", Color.WHITE, 0.8)


## Onboarding steps (server-persisted, monotonic):
## 0 intro story -> 1 fight 1-1 -> 2 claim mail -> 3 summon -> 4 formation -> 5 AFK -> 6 done
func _check_onboarding() -> void:
	if not Game.loaded or _guide == null:
		return
	var step := int(Game.profile.get("onboarding_step", 0))
	var cleared: Array = Game.campaign.get("cleared", [])
	if step == 0 and current == "home":
		var dlg: Control = preload("res://src/ui/StoryDialog.gd").new()
		ui.add_child(dlg)
		await dlg.play([
			{"speaker": "narrator", "text": "Когда-то семь ветров хранили Уралию. Но в ночь Раскола из недр под шиханами пробудились тени Шульгана."},
			{"speaker": "azamat", "text": "Хранитель, ты вовремя! Крепость держится, но на берегу Агидели уже поднимаются мертвецы."},
			{"speaker": "yurek", "text": "Я Юрек, следопыт. Сафарий читает руны, Тан-Чечек лечит. Возьми нас — вместе отбросим их к Торатау."},
		])
		await Game.advance_onboarding(1)
		step = 1
	if step == 1 and "1-1" in cleared:
		await Game.advance_onboarding(2)
		step = 2
	var text := ""
	var nav_hint := ""
	match step:
		1:
			text = "Откройте «Поход» и пройдите бой «Берег Агидели»"
			nav_hint = "campaign"
		2: text = "На главной откройте «Почту» — там ждут дары предков"
		3:
			text = "«Ещё» → «Призыв»: призовите нового героя"
			nav_hint = "more"
		4:
			text = "Герои → «Формация»: поставьте нового героя в отряд"
			nav_hint = "heroes"
		5: text = "На главной в блоке «Дозор» нажмите «Забрать»"
	_guide.visible = text != "" and current == "home"
	_guide_label.text = text
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
