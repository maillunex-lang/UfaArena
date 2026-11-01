extends Control
## Inventory: currencies and materials that exist in the game (exact values), with what each is for.
## Tapping a card opens a context panel over the grid (no separate screen).

const INFO := {
	"gold": ["Золото", "Улучшение героев и построек, пожертвования в казну гильдии.", "Дозор, бои, задания"],
	"crystals": ["Кристаллы", "Призыв героев, лавка, магазин.", "Задания, достижения, события"],
	"summon_essence": ["Эссенция призыва", "Бесплатный призыв героя.", "Зал призыва, рейды, события"],
	"nature_essence": ["Эссенция природы", "Повышение уровня героев.", "Дозор, этапы похода, помощь друзей"],
	"ancient_seals": ["Древние печати", "Особые обмены и сюжетные рейды.", "Сюжетный рейд, события"],
	"guild_marks": ["Знаки гильдии", "Магазин гильдии.", "Задания и войны гильдии, рейды"],
	"friend_tokens": ["Жетоны дружбы", "Лавка дружбы.", "Подарки от друзей"],
	"raid_tickets": ["Билеты рейда", "Дополнительная попытка атаки босса.", "Лавка дружбы, награды"],
}

var main: Node
var _panel: Control


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	main.use_world("none")
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", UI.SP.l)
	var sc := UI.scroll(body)
	sc.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	sc.offset_left = UI.SP.m
	sc.offset_right = -UI.SP.m
	sc.offset_top = UI.SP.s
	add_child(sc)
	body.add_child(UI.title("Инвентарь", UI.FS.h1))
	body.add_child(UI.section("Ресурсы и материалы"))
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", UI.SP.m)
	grid.add_theme_constant_override("v_separation", UI.SP.m)
	for k in INFO:
		var card := Button.new()
		card.custom_minimum_size = Vector2(0, 140)
		card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		card.focus_mode = Control.FOCUS_NONE
		var sb := UI._flat(Color(UI.SURFACE, 0.95), Color(UI.LINE, 0.9), UI.R.m, 1)
		for st in ["normal", "hover", "pressed"]:
			card.add_theme_stylebox_override(st, sb)
		var h := HBoxContainer.new()
		h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		h.offset_left = UI.SP.m
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_theme_constant_override("separation", UI.SP.m)
		var ic := GameIcon.new()
		ic.kind = k
		ic.custom_minimum_size = Vector2(76, 76)
		ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(ic)
		var v := VBoxContainer.new()
		v.alignment = BoxContainer.ALIGNMENT_CENTER
		v.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(UI.label(String(INFO[k][0]), UI.FS.body, UI.MUTED))
		v.add_child(UI.label(Game.exact(Game.wallet.get(k, 0)), UI.FS.h3, UI.GOLD, true))
		h.add_child(v)
		card.add_child(h)
		var key: String = k
		card.pressed.connect(func(): _details(key))
		grid.add_child(card)
	body.add_child(grid)
	body.add_child(UI.section("Предметы и экипировка"))
	body.add_child(UI.state("locked", "Экипировка и артефакты появятся вместе с системой предметов. Сейчас развитие героев — уровни и звёзды."))


func _details(k: String) -> void:
	if is_instance_valid(_panel):
		_panel.queue_free()
	var p := UI.solid_panel()
	p.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	p.offset_left = UI.SP.m
	p.offset_right = -UI.SP.m
	p.offset_top = -420
	p.offset_bottom = -UI.SP.m
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", UI.SP.s)
	var h := HBoxContainer.new()
	var ic := GameIcon.new()
	ic.kind = k
	ic.custom_minimum_size = Vector2(80, 80)
	h.add_child(ic)
	var t := UI.title(String(INFO[k][0]), UI.FS.h2)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(t)
	var x := UI.button("✕", "glass", 80, 80)
	x.pressed.connect(func(): p.queue_free())
	h.add_child(x)
	v.add_child(h)
	v.add_child(UI.label("Количество: %s" % Game.exact(Game.wallet.get(k, 0)), UI.FS.body_l, UI.GOLD, true))
	for line in ["Для чего: " + String(INFO[k][1]), "Где получить: " + String(INFO[k][2])]:
		var l := UI.label(line, UI.FS.body, UI.TEXT)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		v.add_child(l)
	p.add_child(v)
	add_child(p)
	_panel = p
	UI.pop_in(p)
