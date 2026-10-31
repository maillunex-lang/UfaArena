extends Control
## Зал призыва: server-side summon with transparent rates + pity, reveal animation.

const HeroCard := preload("res://src/ui/HeroCard.gd")

var main: Node
var pools := {}
var pity := 0
var _pity_lbl: Label


func setup(m: Node, _p: Dictionary) -> void:
	main = m
	var w: Node3D = main.use_world("hub")
	w.show_hero("humai")
	var panel := UI.glass_panel(Color("#d7c6ff"))
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 24
	panel.offset_right = -24
	panel.offset_top = -760
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	panel.add_child(v)
	v.add_child(UI.title("Зов предков", 56))
	var d := UI.label("Призовите героев Уралии. Шансы открыты, гарантия легендарного героя не позже 60 призывов. Любого героя можно получить игровым путём.", 27, UI.TEXT)
	d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(d)
	_pity_lbl = UI.label("", 28, UI.GOLD, true)
	v.add_child(_pity_lbl)
	var rates := UI.label("", 24, UI.MUTED)
	rates.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(rates)
	v.add_child(UI.expand())
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	var b1 := UI.button("×1", "glass", 0, 120)
	b1.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b1.pressed.connect(func(): _summon("standard", 1))
	var b10 := UI.button("×10", "primary", 0, 120)
	b10.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b10.pressed.connect(func(): _summon("standard", 10))
	row.add_child(_with_cost(b1, {"summon_essence": 1}))
	row.add_child(_with_cost(b10, {"summon_essence": 10}))
	v.add_child(row)
	var bc := UI.button("×1 за кристаллы", "glass", 0, 100)
	bc.pressed.connect(func(): _summon("standard_crystals", 1))
	v.add_child(_with_cost(bc, {"crystals": 300}))
	var r := await Api.get_json("/summon/pools")
	if r.ok and is_inside_tree():
		pity = int(r.data.pity)
		var txt := []
		for p in r.data.pools:
			pools[p.code] = p
		var rt: Dictionary = r.data.pools[0].rates
		for k in rt:
			txt.append("%s %.1f%%" % [Game.rarities.get(k, k), float(rt[k]) * 100.0])
		rates.text = "Шансы: " + ", ".join(txt)
		_update_pity()


func _with_cost(b: Button, cost: Dictionary) -> Control:
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_child(b)
	var c := UI.rewards_row(cost, 26)
	c.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_child(c)
	return v


func _update_pity() -> void:
	_pity_lbl.text = "До гарантии: %d призывов" % max(0, 60 - pity)


func _summon(pool: String, count: int) -> void:
	Router.busy(true)
	var r := await Api.post_json("/summon", {"pool": pool, "count": count}, true)
	Router.busy(false)
	if not r.ok:
		Router.error(r)
		return
	Game.set_wallet(r.data.wallet)
	pity = int(r.data.pity)
	_update_pity()
	await Game.refresh_heroes()
	main.onboarding_event("summon")
	_reveal(r.data.results, r.data.heroes)


func _reveal(results: Array, heroes: Dictionary) -> void:
	var overlay := ColorRect.new()
	overlay.color = Color(0.03, 0.02, 0.08, 0.82)
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	main.modal(overlay)
	var v := VBoxContainer.new()
	v.set_anchors_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 26)
	overlay.add_child(v)
	var t := UI.title("Предки откликнулись!", 60)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
	var grid := GridContainer.new()
	grid.columns = 5 if results.size() > 1 else 1
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 12)
	var center := CenterContainer.new()
	center.add_child(grid)
	v.add_child(center)
	var best: Dictionary = results[0]
	for res in results:
		if int(res.rarity) > int(best.rarity):
			best = res
	main.world.show_hero(best.hero_code)
	Sfx.play("magic")
	for res in results:
		var h: Dictionary = heroes.get(res.player_hero_id, {})
		var card := HeroCard.new()
		card.setup(h, false, results.size() > 1)
		card.modulate.a = 0.0
		card.pivot_offset = card.custom_minimum_size / 2
		card.scale = Vector2(0.4, 0.4)
		grid.add_child(card)
		var tw := card.create_tween().set_parallel(true)
		tw.tween_property(card, "modulate:a", 1.0, 0.2)
		tw.tween_property(card, "scale", Vector2.ONE, 0.3).set_trans(Tween.TRANS_BACK)
		if res.duplicate:
			var dl := UI.label("дубликат → осколки", 18, UI.GOLD, true)
			dl.position = Vector2(8, 70)
			card.add_child(dl)
		if int(res.rarity) >= 5:
			Sfx.play("spell")
		await get_tree().create_timer(0.12 if results.size() > 1 else 0.3).timeout
	var ok := UI.button("Отлично", "primary", 420)
	ok.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	ok.pressed.connect(overlay.queue_free)
	v.add_child(ok)
