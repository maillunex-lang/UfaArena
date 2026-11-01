extends Control
## Зал призыва: server-side summon with transparent rates + pity, reveal animation.

const HeroCard := preload("res://src/ui/HeroCard.gd")

var main: Node
var pools := {}
var pity := 0
var _list: VBoxContainer
var _pity_lbl: Label


## Functional summon panel (brief §13.2): every active pool from the server with cost, odds, guarantee and limits;
## a confirmation window shows the full price, balance after, odds and consequences before anything is spent (§13.3).
func setup(m: Node, _p: Dictionary) -> void:
	main = m
	var w: Node3D = main.use_world("hub")
	w.show_hero("humai")
	var panel := UI.glass_panel(Color("#d7c6ff"))
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 16
	panel.offset_right = -16
	panel.offset_top = -900
	panel.offset_bottom = -10
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	panel.add_child(v)
	var head := HBoxContainer.new()
	head.add_child(UI.title("Призыв", 52))
	head.add_child(UI.expand())
	_pity_lbl = UI.label("", 26, UI.GOLD, true)
	head.add_child(_pity_lbl)
	v.add_child(head)
	var d := UI.label("Шансы открыты. Гарантия: героя высокой редкости вы получите не позже порога призывов. Любого героя можно получить игровым путём.", 24, UI.MUTED)
	d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(d)
	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 12)
	v.add_child(UI.scroll(_list))
	_list.add_child(UI.skeleton(2, 220))
	var r := await Api.get_json("/summon/pools")
	if not is_inside_tree():
		return
	for c in _list.get_children():
		c.queue_free()
	if not r.ok:
		_list.add_child(UI.state("offline" if int(r.get("status", 0)) == 0 else "error", "Не удалось загрузить призыв.", "Повторить", func(): main.open("summon")))
		return
	pity = int(r.data.pity)
	for p in r.data.pools:
		pools[p.code] = p
		_list.add_child(_pool_card(p))
	if r.data.pools.is_empty():
		_list.add_child(UI.state("empty", "Сейчас нет доступных призывов."))
	_update_pity()


func _rates_text(p: Dictionary) -> String:
	var txt := []
	var rt: Dictionary = p.rates
	for k in rt:
		txt.append("%s %s%%" % [Game.rarities.get(k, k), String.num(float(rt[k]) * 100.0, 1)])
	return ", ".join(txt)


func _pool_card(p: Dictionary) -> Control:
	var c := UI.card(UI.GOLD_DARK)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	v.add_child(UI.label(String(p.name), 32, UI.GOLD, true))
	var cost_row := HBoxContainer.new()
	cost_row.add_child(UI.label("Цена одного призыва:", 24, UI.TEXT))
	cost_row.add_child(UI.rewards_row(p.cost, 26))
	v.add_child(cost_row)
	var rl := UI.label("Шансы: " + _rates_text(p), 22, UI.MUTED)
	rl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(rl)
	var g := UI.label("Гарантия: %s или выше не позже %d-го призыва (общий счётчик)" % [Game.rarities.get(str(int(p.pity_min_rarity)), ""),
		int(p.pity_threshold)], 22, UI.TEXT)
	g.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(g)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	for n in [1, 10]:
		var b := UI.button("×%d" % n, "primary" if n == 10 else "glass", 0, 96)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var code: String = p.code
		var cnt: int = n
		b.pressed.connect(func(): _confirm(code, cnt))
		row.add_child(b)
	v.add_child(row)
	c.add_child(v)
	return c


func _update_pity() -> void:
	var th := 60
	for p in pools.values():
		th = int(p.pity_threshold)
	_pity_lbl.text = "До гарантии: %d" % max(0, th - pity)


## Transparency window: full cost, balance after, odds, guarantee, consequences.
func _confirm(code: String, count: int) -> void:
	var p: Dictionary = pools[code]
	var total := {}
	var enough := true
	for k in p.cost:
		total[k] = int(p.cost[k]) * count
		if int(Game.wallet.get(k, 0)) < int(total[k]):
			enough = false
	var lines := []
	for k in total:
		lines.append("%s: %s (у вас %s → останется %s)" % [Game.CURRENCY_NAMES.get(k, k),
			Game.exact(total[k]), Game.exact(int(Game.wallet.get(k, 0))), Game.exact(maxi(0, int(Game.wallet.get(k, 0)) - int(total[k])))])
	var left := maxi(0, int(p.pity_threshold) - pity)
	var body := "Стоимость: %s\n\nШансы на каждый призыв: %s\n\nГарантия: %s" % ["\n".join(lines), _rates_text(p),
		("сработает в этом призыве" if left <= count else "через %d призывов" % left)]
	body += "\n\nПовторный герой превращается в осколки для вознесения. Ресурсы списываются сразу, отменить призыв нельзя."
	if not enough:
		body += "\n\nНе хватает ресурсов."
	UI.confirm(main.ui, "%s ×%d" % [p.name, count], body, "Призвать" if enough else "Понятно", func():
		if enough:
			_summon(code, count))


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
			UI.celebrate(card, Game.RARITY_COLORS.get(int(res.rarity), UI.GOLD))  # rarity effect for epic+ heroes
		elif int(res.rarity) == 4:
			UI.celebrate(card, Game.RARITY_COLORS.get(4, UI.GOLD), false)
		await get_tree().create_timer(0.12 if results.size() > 1 else 0.3).timeout
	var ok := UI.button("Отлично", "primary", 420)
	ok.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	ok.pressed.connect(overlay.queue_free)
	v.add_child(ok)
