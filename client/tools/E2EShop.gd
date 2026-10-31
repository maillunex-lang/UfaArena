extends Node
## Shop E2E (dev only): URALIA_E2E_SHOP=<dir>. Presses real buttons through the monetization UI in TEST mode.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_SHOP")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func _log(s: String) -> void:
	print("SHOP: ", s)


func wait(sec: float) -> void:
	await get_tree().create_timer(sec, true, false, true).timeout


func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + name + ".png")


func _all(n: Node, acc: Array) -> Array:
	acc.append(n)
	for c in n.get_children():
		_all(c, acc)
	return acc


func find_button(text: String) -> Button:
	for n in _all(get_tree().root, []):
		if n is Button and n.is_visible_in_tree() and not n.disabled:
			if n.text.contains(text):
				return n
			for l in n.find_children("*", "Label", true, false):
				if (l as Label).text == text:
					return n
	return null


func press(text: String, timeout := 6.0) -> bool:
	var t := 0.0
	while t < timeout:
		var b := find_button(text)
		if b:
			b.pressed.emit()
			_log("press '%s'" % text)
			return true
		await wait(0.25)
		t += 0.25
	_log("MISSING '%s'" % text)
	return false


func shop() -> Node:
	return get_tree().current_scene.screen


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(2.0)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and String(d.get_script().resource_path).ends_with("StoryDialog.gd"):
			d.queue_free()
	var w0: Dictionary = (await Api.get_json("/player/me")).data.wallet
	await press("Магазин")
	await wait(2.5)
	await shot("s01_crystals")
	await press("99 ₽")  # smallest crystal pack: test purchase through the UI
	await wait(2.5)
	var w1: Dictionary = (await Api.get_json("/player/me")).data.wallet
	_log("CRYSTALS before=%d after=%d" % [int(w0.crystals), int(w1.crystals)])
	for t in ["Наборы ресурсов", "Стартовые наборы", "VIP и подписки", "Герои и фрагменты", "Косметика", "Боевой пропуск",
			"Сезонные предложения", "Лавка"]:
		shop().tab = {"Наборы ресурсов": "resources", "Стартовые наборы": "starter", "VIP и подписки": "vip",
			"Герои и фрагменты": "heroes", "Косметика": "cosmetics", "Боевой пропуск": "battlepass",
			"Сезонные предложения": "seasonal", "Лавка": "lavka"}[t]
		shop()._render_tabs()
		await shop()._render()
		await wait(1.5)
		await shot("s_" + shop().tab)
	# starter pack 1
	shop().tab = "starter"; shop()._render_tabs(); await shop()._render(); await wait(1.0)
	var starter := _item("starter_1")
	await shop()._purchase(starter)
	await wait(1.5)
	# shards with hero choice: picker opens, choose first hero
	shop().tab = "heroes"; shop()._render_tabs(); await shop()._render(); await wait(1.0)
	shop()._purchase.call_deferred(_item("shards_small"))
	await wait(1.5)
	await shot("s10_hero_picker")
	await press("Юрек")
	await wait(3.0)
	# battle pass premium + claim
	shop().tab = "battlepass"; shop()._render_tabs(); await shop()._render(); await wait(1.0)
	await shop()._purchase(_item("battlepass_premium"))
	await wait(2.0)
	await shot("s11_battlepass_premium")
	var uid := Api.user_id
	OS.set_environment("URALIA_E2E_BP_USER", uid)
	_log("BP_NEEDS_XP user=%s" % uid)
	var f := FileAccess.open(out + "/bp_xp.request", FileAccess.WRITE)
	f.store_string(uid)
	f.close()
	var t := 0.0
	while not FileAccess.file_exists(out + "/bp_xp.done") and t < 30.0:
		await wait(0.3)
		t += 0.3
	await shop()._render()
	await wait(1.5)
	await press("Забрать", 3.0)
	await wait(1.5)
	await press("Забрать", 3.0)
	await wait(1.5)
	# cosmetic frame -> wardrobe equip
	shop().tab = "cosmetics"; shop()._render_tabs(); await shop()._render(); await wait(1.0)
	await shop()._purchase(_item("cos_frame_rift"))
	await wait(1.5)
	shop().tab = "wardrobe"; shop()._render_tabs(); await shop()._render(); await wait(1.0)
	await press("Надеть")
	await wait(2.0)
	await shot("s12_wardrobe")
	# VIP rewards
	shop().tab = "vip"; shop()._render_tabs(); await shop()._render(); await wait(1.5)
	await shot("s13_vip")
	await press("Награда", 3.0)
	await wait(1.5)
	shop().tab = "history"; shop()._render_tabs(); await shop()._render(); await wait(1.5)
	await shot("s14_history")
	var orders: Array = (await Api.get_json("/shop/orders")).data.orders
	var cos: Dictionary = (await Api.get_json("/cosmetics")).data
	var heroes: Array = (await Api.get_json("/player/heroes")).data.heroes
	var bp: Dictionary = (await Api.get_json("/battlepass")).data
	var vip: Dictionary = (await Api.get_json("/vip")).data
	var yur := heroes.filter(func(h): return h.hero_code == "yurek")
	_log("ORDERS %s" % str(orders.map(func(o): return "%s:%s:%s" % [o.sku, o.status, "test" if o.is_test else "REAL"])))
	_log("FRAME equipped=%s" % str(cos.equipped.get("frame", {}).get("id", "none")))
	_log("YUREK shards=%s stars=%s" % [str(yur[0].shards) if yur.size() else "-", str(yur[0].stars) if yur.size() else "-"])
	_log("BP premium=%s claimed_free=%s claimed_premium=%s" % [str(bp.premium), str(bp.claimed_free), str(bp.claimed_premium)])
	_log("VIP level=%d xp=%d claimed=%s" % [int(vip.level), int(vip.xp), str(vip.claimed)])
	await press("Крепость", 2.0)
	await wait(2.0)
	await shot("s15_home_frame")
	_log("SHOP_E2E_DONE")
	get_tree().quit()


func _item(sku: String) -> Dictionary:
	for it in shop().data.get("items", []):
		if it.sku == sku:
			return it
	_log("NO ITEM " + sku)
	return {}
