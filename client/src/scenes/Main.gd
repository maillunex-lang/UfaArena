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
}
const NAV := [["campaign", "Кампания"], ["heroes", "Герои"], ["home", "Крепость"], ["summon", "Призыв"],
	["modes", "Режимы"]]

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
	open(Router.params.get("screen", "home"))
	_check_onboarding()
	Content.start_background()


# ------------------------------------------------------------------ worlds
func use_world(kind: String) -> Node3D:
	if world_kind == kind and world:
		return world
	if world:
		world.queue_free()
	world_kind = kind
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
	for k in _nav_buttons:
		_style_nav(k, k == screen_name)
	_check_onboarding()


## Modal overlay above content (full screen within bars).
func modal(node: Control) -> void:
	node.set_anchors_preset(Control.PRESET_FULL_RECT)
	content.add_child(node)


func _build_top() -> void:
	var bar := HBoxContainer.new()
	bar.set_anchors_preset(Control.PRESET_TOP_WIDE)
	bar.offset_top = 64
	bar.offset_left = 28
	bar.offset_right = -28
	bar.offset_bottom = 200
	bar.add_theme_constant_override("separation", 14)
	ui.add_child(bar)
	var prof := Button.new()
	prof.flat = true
	prof.focus_mode = Control.FOCUS_NONE
	prof.custom_minimum_size = Vector2(300, 120)
	for st in ["normal", "hover", "pressed"]:
		prof.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	var ph := HBoxContainer.new()
	ph.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ph.add_theme_constant_override("separation", 12)
	var av := PanelContainer.new()
	av.add_theme_stylebox_override("panel", UI._round_glass())
	av.custom_minimum_size = Vector2(108, 108)
	av.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var avi := GameIcon.new()
	avi.kind = "profile"
	avi.mouse_filter = Control.MOUSE_FILTER_IGNORE
	av.add_child(avi)
	ph.add_child(av)
	_profile_lbl = UI.label("", 28, UI.TEXT, true)
	_profile_lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ph.add_child(_profile_lbl)
	prof.add_child(ph)
	prof.pressed.connect(func(): open("settings"))
	bar.add_child(prof)
	bar.add_child(UI.expand())
	var chips := VBoxContainer.new()
	chips.add_theme_constant_override("separation", 6)
	var row1 := HBoxContainer.new()
	row1.alignment = BoxContainer.ALIGNMENT_END
	row1.add_theme_constant_override("separation", 10)
	var row2 := HBoxContainer.new()
	row2.alignment = BoxContainer.ALIGNMENT_END
	row2.add_theme_constant_override("separation", 10)
	for k in ["gold", "crystals"]:
		_chips[k] = UI.chip(k, "0")
		row1.add_child(_chips[k])
	for k in ["summon_essence", "nature_essence"]:
		_chips[k] = UI.chip(k, "0")
		row2.add_child(_chips[k])
	chips.add_child(row1)
	chips.add_child(row2)
	bar.add_child(chips)


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
	_profile_lbl.text = "%s\nУр. %d" % [p.get("nickname", "Хранитель"), int(p.get("level", 1))]


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
	var icons := {"campaign": "campaign", "heroes": "heroes", "home": "fortress", "summon": "summon", "modes": "modes"}
	for item in NAV:
		var b := UI.icon_button(icons[item[0]], item[1])
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
			{"speaker": "gulnaz", "text": "Возьми нас в отряд. Вместе мы отбросим их к Торатау."},
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
			text = "Откройте «Кампанию» и пройдите бой «Берег Агидели»"
			nav_hint = "campaign"
		2: text = "В «Почте» ждут дары предков — заберите их"
		3:
			text = "Откройте «Призыв» и призовите нового героя"
			nav_hint = "summon"
		4:
			text = "Герои → «Формация»: поставьте нового героя в отряд"
			nav_hint = "heroes"
		5: text = "Нажмите на сундук «Дозор» и заберите AFK-награды"
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
