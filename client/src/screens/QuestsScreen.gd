extends Control
## Quests: main story chain, daily and side quests. Progress and claims are server-side.

const KIND_NAMES := {"main": "Основные", "daily": "Ежедневные", "side": "Побочные", "personal": "Личные",
	"secret": "Тайные", "seasonal": "Сезонные"}

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
	head.add_child(UI.title("Задания", 52))
	head.add_child(UI.expand())
	var back := UI.button("Назад", "dim", 200, 90)
	back.pressed.connect(func(): main.open("home"))
	head.add_child(back)
	v.add_child(head)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_list))
	var r := await Api.get_json("/quests")
	if r.ok and is_inside_tree():
		_render(r.data.quests)


func _render(quests: Array) -> void:
	for c in _list.get_children():
		c.queue_free()
	var last_kind := ""
	for q in quests:
		if q.kind != last_kind:
			last_kind = q.kind
			_list.add_child(UI.label(KIND_NAMES.get(q.kind, q.kind), 30, UI.ACCENT, true))
		var card := PanelContainer.new()
		card.add_theme_stylebox_override("panel", UI._flat(Color(0, 0, 0, 0.3), Color(1, 1, 1, 0.22), 22, 2))
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 16)
		var info := VBoxContainer.new()
		info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		info.add_child(UI.label(q.title, 32, UI.GOLD if not q.claimed else UI.MUTED, true))
		var d := UI.label(q.description, 25)
		d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		info.add_child(d)
		var pr := HBoxContainer.new()
		pr.add_theme_constant_override("separation", 12)
		var bar := UI.bar(int(q.progress), int(q.target), Color("#7fd48a"), 16, 260)
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		pr.add_child(bar)
		pr.add_child(UI.label("%d/%d" % [int(q.progress), int(q.target)], 24, UI.MUTED))
		pr.add_child(UI.rewards_row(q.rewards, 24))
		info.add_child(pr)
		h.add_child(info)
		var btn := UI.button("Получено" if q.claimed else ("Забрать" if q.claimable else "В пути"),
			"primary" if q.claimable else "dim", 210, 90)
		btn.disabled = not q.claimable
		var code: String = q.code
		btn.pressed.connect(func(): _claim(code))
		h.add_child(btn)
		card.add_child(h)
		_list.add_child(card)


func _claim(code: String) -> void:
	var r := await Api.post_json("/quests/%s/claim" % code, {}, true)
	if not r.ok:
		Router.error(r)
		return
	Sfx.play("coins")
	Game.set_wallet(r.data.wallet)
	Router.toast("Награда: " + Game.rewards_text(r.data.rewards))
	_render(r.data.quests)
