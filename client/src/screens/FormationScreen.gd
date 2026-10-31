extends Control
## Formation: 2 front + 3 back slots (provisional «формация C»), saved on the server.

const HeroCard := preload("res://src/ui/HeroCard.gd")

var main: Node
var back_to := "heroes"
var slots: Array = []
var _slot_box: VBoxContainer
var _list: GridContainer
var _power: Label


func setup(m: Node, p: Dictionary) -> void:
	main = m
	back_to = p.get("back", "heroes")
	slots = Game.formation.duplicate()
	var panel := UI.glass_panel()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 24
	panel.offset_right = -24
	panel.offset_top = 10
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Формация", 52))
	head.add_child(UI.expand())
	_power = UI.label("", 34, UI.GOLD, true)
	head.add_child(_power)
	v.add_child(head)
	v.add_child(UI.label("Передний ряд принимает удары, задний — наносит урон и лечит.", 26, UI.MUTED))
	_slot_box = VBoxContainer.new()
	_slot_box.add_theme_constant_override("separation", 12)
	v.add_child(_slot_box)
	v.add_child(UI.label("Ваши герои (коснитесь, чтобы добавить/убрать):", 28, UI.TEXT, true))
	_list = GridContainer.new()
	_list.columns = 5
	_list.add_theme_constant_override("h_separation", 12)
	_list.add_theme_constant_override("v_separation", 12)
	v.add_child(UI.scroll(_list))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 16)
	var cancel := UI.button("Назад", "glass", 260)
	cancel.pressed.connect(func(): main.open(back_to))
	row.add_child(cancel)
	var save := UI.button("Сохранить отряд", "primary")
	save.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	save.pressed.connect(_save)
	row.add_child(save)
	v.add_child(row)
	_render()


func _render() -> void:
	for c in _slot_box.get_children():
		c.queue_free()
	for c in _list.get_children():
		c.queue_free()
	for row_def in [["Задний ряд", [2, 3, 4]], ["Передний ряд", [0, 1]]]:
		var h := HBoxContainer.new()
		h.alignment = BoxContainer.ALIGNMENT_CENTER
		h.add_theme_constant_override("separation", 16)
		for s in row_def[1]:
			h.add_child(_slot(s))
		_slot_box.add_child(UI.label(row_def[0], 24, UI.MUTED))
		_slot_box.add_child(h)
	var power := 0
	for id in slots:
		if id:
			power += int(Game.hero_by_id(id).get("power", 0))
	_power.text = "Сила отряда: %s" % Game.fmt(power)
	for h in Game.heroes:
		var card := HeroCard.new()
		card.setup(h, h.id in slots, true)
		var hid: String = h.id
		card.pressed.connect(func(): _toggle(hid))
		_list.add_child(card)


func _slot(i: int) -> Control:
	var id = slots[i]
	if id:
		var card := HeroCard.new()
		card.setup(Game.hero_by_id(id), true, true)
		card.pressed.connect(func(): slots[i] = null; _render())
		return card
	var b := UI.button("+", "dim", 180, 230)
	b.add_theme_font_size_override("font_size", 64)
	return b


func _toggle(hid: String) -> void:
	var idx := slots.find(hid)
	if idx >= 0:
		slots[idx] = null
	else:
		var free := slots.find(null)
		if free < 0:
			Router.toast("Все 5 мест заняты — уберите героя из отряда")
			return
		slots[free] = hid
	Sfx.play("click")
	_render()


func _save() -> void:
	var r := await Game.save_formation(slots)
	if not r.ok:
		Router.error(r)
		return
	Router.toast("Отряд сохранён")
	main.onboarding_event("formation")
	main.open(back_to)
