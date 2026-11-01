extends Control
## Game modes hub. Phased release (GDD stage 11): modes open with their functional blocks.

var main: Node
const MODES := [
	["campaign", "Кампания: 7 глав Башкортостана", "Доступно", true],
	["chat", "Чат Курултая", "Общий, гильдейский и личный чат", true],
	["friends", "Друзья", "Поиск, подарки, помощь, жители Уралии", true],
	["arena", "Арена хранителей (PvP)", "Сервер готов, экран — в следующем обновлении", false],
	["quests", "Башня испытаний", "Блок «Режимы» — закрытая бета", false],
	["guild", "Гильдии и рейды", "Сервер готов, экраны — в следующем обновлении", false],
	["events", "Сезонные события", "LiveOps — после релиза", false],
]


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("hub")
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 24
	panel.offset_right = -24
	panel.offset_top = -1180
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	panel.add_child(v)
	v.add_child(UI.title("Режимы", 52))
	for md in MODES:
		var b := Button.new()
		b.custom_minimum_size = Vector2(0, 140)
		b.focus_mode = Control.FOCUS_NONE
		var sb := UI._flat(Color(0.02, 0.03, 0.07, 0.5), UI.GOLD if md[3] else Color(1, 1, 1, 0.2), 24, 3 if md[3] else 2)
		for st in ["normal", "hover", "pressed"]:
			b.add_theme_stylebox_override(st, sb)
		var h := HBoxContainer.new()
		h.set_anchors_preset(Control.PRESET_FULL_RECT)
		h.offset_left = 20
		h.add_theme_constant_override("separation", 20)
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var ic := GameIcon.new()
		ic.kind = md[0] if md[3] else "lock"
		ic.custom_minimum_size = Vector2(96, 96)
		ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(ic)
		var info := VBoxContainer.new()
		info.alignment = BoxContainer.ALIGNMENT_CENTER
		info.mouse_filter = Control.MOUSE_FILTER_IGNORE
		info.add_child(UI.label(md[1], 34, UI.TEXT if md[3] else UI.MUTED, true))
		info.add_child(UI.label(md[2], 24, UI.MUTED))
		h.add_child(info)
		b.add_child(h)
		if md[3]:
			var key: String = md[0]
			b.pressed.connect(func(): main.open(key))
		else:
			b.pressed.connect(func(): Router.toast(md[1] + ": " + md[2]))
		v.add_child(b)
