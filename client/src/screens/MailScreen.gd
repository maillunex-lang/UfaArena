extends Control
## Mail with attachments; claiming is idempotent and server-validated.

var main: Node
var _list: VBoxContainer


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
	v.add_theme_constant_override("separation", 12)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Почта", 52))
	head.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 200, 90)
	back.pressed.connect(func(): main.open("home"))
	head.add_child(back)
	v.add_child(head)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_list))
	_load()


func _load() -> void:
	var r := await Api.get_json("/mail")
	if not r.ok or not is_inside_tree():
		return
	for c in _list.get_children():
		c.queue_free()
	if r.data.mail.is_empty():
		_list.add_child(UI.label("Писем нет", 30, UI.MUTED))
	for msg in r.data.mail:
		var card := PanelContainer.new()
		card.add_theme_stylebox_override("panel", UI._flat(Color(0.02, 0.03, 0.07, 0.5), Color(1, 1, 1, 0.22), 22, 2))
		var vv := VBoxContainer.new()
		vv.add_theme_constant_override("separation", 8)
		vv.add_child(UI.label(msg.title, 34, UI.GOLD, true))
		vv.add_child(UI.label("от: " + msg.sender, 24, UI.MUTED))
		var body := UI.label(msg.body, 28)
		body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		vv.add_child(body)
		var row := HBoxContainer.new()
		row.add_child(UI.rewards_row(msg.attachments, 28))
		row.add_child(UI.expand())
		var btn := UI.button("Получено" if msg.claimed else "Забрать", "dim" if msg.claimed else "primary", 230, 90)
		btn.disabled = msg.claimed
		var id: String = msg.id
		btn.pressed.connect(func(): _claim(id))
		row.add_child(btn)
		vv.add_child(row)
		card.add_child(vv)
		_list.add_child(card)


func _claim(id: String) -> void:
	var r := await Api.post_json("/mail/%s/claim" % id, {}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Получено: " + Game.rewards_text(r.data.rewards))
	main.onboarding_event("mail")
	_load()
