extends Node
## End-to-end UI driver (dev only, enabled with URALIA_E2E=<screenshot dir>).
## Presses real buttons through the whole MVP loop and saves screenshots.

var out := ""
var log_lines: Array[String] = []


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func _log(s: String) -> void:
	print("E2E: ", s)
	log_lines.append(s)


func wait(sec: float) -> void:
	await get_tree().create_timer(sec, true, false, true).timeout


func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + name + ".png")
	_log("shot " + name)


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


func press(text: String, timeout := 10.0) -> bool:
	var t := 0.0
	while t < timeout:
		var b := find_button(text)
		if b:
			b.pressed.emit()
			_log("press '%s'" % text)
			return true
		await wait(0.25)
		t += 0.25
	_log("MISSING button '%s'" % text)
	return false


func advance_dialogs() -> void:
	for i in 40:
		var dlg := _find_dialog()
		if dlg == null:
			return
		dlg.set("_typing", false)
		dlg.emit_signal("_advance")
		await wait(0.35)


func _find_dialog() -> Node:
	for n in _all(get_tree().root, []):
		if n.get_script() and String(n.get_script().resource_path).ends_with("StoryDialog.gd"):
			return n
	return null


func scene_name() -> String:
	return get_tree().current_scene.name if get_tree().current_scene else ""


func wait_scene(name: String, timeout := 30.0) -> bool:
	var t := 0.0
	while t < timeout:
		if scene_name() == name:
			return true
		await wait(0.25)
		t += 0.25
	_log("TIMEOUT scene " + name)
	return false


func _run() -> void:
	await wait_scene("Boot")
	await wait(1.0)
	await shot("00_boot")
	await wait_scene("Main")
	await wait(2.5)
	await shot("01_intro_dialog")
	await advance_dialogs()
	await wait(1.5)
	await shot("02_home")
	# new navigation: dashboard «В бой» opens the campaign with the next stage's preparation panel
	await press("В бой")
	await wait(3.0)
	await shot("03_campaign")
	await press("В бой")
	await wait_scene("Battle")
	await wait(2.5)
	await shot("04_battle_story")
	await advance_dialogs()
	await wait(1.6)
	await shot("05_battle")
	await wait(0.9)
	await shot("05b_battle")
	# battle speed x3 to finish faster
	await press("x1", 2.0)
	await press("x2", 2.0)
	var t := 0.0
	while find_button("На главную") == null and t < 120.0:
		await wait(0.5)
		t += 0.5
	await wait(1.0)
	await shot("06_battle_result")
	await press("На главную")
	await wait_scene("Main")
	await wait(2.0)
	get_tree().current_scene.open("mail")  # dashboard card «Почта» → «Открыть»
	await wait(1.5)
	await shot("07_mail")
	await press("Забрать")
	await wait(1.5)
	await press("Ещё")
	await wait(1.0)
	await press("Призыв")
	await wait(2.0)
	await shot("08_summon")
	await press("×1")
	await wait(3.0)
	await shot("09_summon_reveal")
	await press("Отлично")
	await press("Герои")
	await wait(3.0)
	await shot("10_heroes")
	var cards := []
	for n in _all(get_tree().root, []):
		if n.get_script() and String(n.get_script().resource_path).ends_with("HeroCard.gd") and n.is_visible_in_tree():
			cards.append(n)
	if cards.size() > 0:
		cards[0].pressed.emit()
		await wait(2.0)
		await shot("11_hero_detail")
		await press("Повысить уровень")
		await wait(1.5)
	await press("Формация")
	await wait(2.5)
	# put every unused hero into free slots
	var main: Node = get_tree().current_scene
	var form: Node = main.screen
	for h in Game.heroes:
		if not h.id in form.slots and form.slots.find(null) >= 0:
			form._toggle(h.id)
	await wait(1.0)
	await shot("12_formation")
	await press("Сохранить отряд")
	await wait(1.5)
	await press("Главная")
	await wait(2.5)
	await press("Дозор")  # patrol chest on the game panel claims in one tap
	await wait(2.0)
	await shot("13_home_after_afk")
	get_tree().current_scene.open("quests")
	await wait(2.0)
	await shot("14_quests")
	for i in 3:
		if not await press("Забрать", 1.0):
			break
		await wait(1.0)
	get_tree().current_scene.open("fortress")
	await wait(1.5)
	await shot("15_fortress")
	await press("Улучшить")
	await wait(1.5)
	await press("Главная")
	await wait(2.0)
	# second campaign battle: 1-2 from the dashboard campaign card
	await press("В бой")
	await wait(3.0)
	await shot("16_campaign_after")
	# real-time battle 1-2: all units fight at once (side view)
	await press("В бой")
	await wait_scene("Battle")
	await wait(2.5)
	await advance_dialogs()
	for i in 3:
		await wait(2.0)
		await shot("16b_battle_%d" % i)
	var t2 := 0.0
	while find_button("На главную") == null and t2 < 120.0:
		await wait(0.5)
		t2 += 0.5
	await shot("16c_battle_result")
	await press("На главную")
	await wait_scene("Main")
	await wait(1.5)
	var gold_before := int(Game.wallet.get("gold", 0))
	var cleared_before: Array = Game.campaign.get("cleared", []).duplicate()
	# ---- simulated app restart: drop in-memory state, keep only the stored refresh token
	Game.loaded = false
	Game.wallet = {}
	Game.campaign = {}
	Api.access_token = ""
	Router.goto(Router.BOOT)
	await wait_scene("Boot")
	await wait_scene("Main")
	await wait(2.0)
	var cleared_after: Array = Game.campaign.get("cleared", [])
	var ok := cleared_after.size() == cleared_before.size() and int(Game.wallet.get("gold", -1)) >= gold_before - 1
	_log("RESTART cleared_before=%s cleared_after=%s gold_before=%d gold_after=%d -> %s" % [cleared_before,
		cleared_after, gold_before, int(Game.wallet.get("gold", -1)), "OK" if ok else "FAIL"])
	await shot("17_after_restart")
	# ---- offline handling
	var url := Config.server_url
	Config.server_url = "http://127.0.0.1:9"
	await Api.get_json("/player/me")
	await wait(0.5)
	await shot("18_offline")
	_log("OFFLINE banner=%s" % str(Api.is_offline))
	Config.server_url = url
	await press("Повторить")
	await wait(1.5)
	_log("RECOVERED offline=%s" % str(Api.is_offline))
	await press("Настройки", 1.0)
	await get_tree().current_scene.open("settings")
	await wait(1.5)
	await shot("19_settings")
	_log("E2E_DONE")
	get_tree().quit()
