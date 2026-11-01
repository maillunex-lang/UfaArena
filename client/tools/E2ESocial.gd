extends Node
## Social E2E (dev only): URALIA_E2E_SOCIAL=<dir>. Update prompt, chat with AI residents, friends flows.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_SOCIAL")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func _log(s: String) -> void:
	print("SOCIAL: ", s)


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


func press(text: String, timeout := 6.0) -> bool:
	var t := 0.0
	while t < timeout:
		for n in _all(get_tree().root, []):
			if n is Button and n.is_visible_in_tree() and not n.disabled and (n.text.contains(text) or n.find_children("*", "Label", true, false).any(func(l): return l.text == text)):
				n.pressed.emit()
				_log("press '%s'" % text)
				return true
		await wait(0.25)
		t += 0.25
	_log("MISSING '%s'" % text)
	return false


func main() -> Node:
	return get_tree().current_scene


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(3.0)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and String(d.get_script().resource_path).ends_with("StoryDialog.gd"):
			d.queue_free()
	for i in 40:
		if get_tree().root.find_children("*", "Control", true, false).any(func(c): return c.get_script() != null and String(c.get_script().resource_path).ends_with("UpdateDialog.gd")):
			break
		await wait(0.25)
	await wait(0.5)
	await shot("u01_update_dialog")
	await press("Позже")
	await wait(0.5)
	await shot("u02_home_chat_button")
	main().open("chat")
	await wait(3.0)
	var scr: Node = main().screen
	scr._entry.text = "Привет всем! Кто идёт на босса гильдии сегодня?"
	await scr._send()
	await wait(1.0)
	await shot("c01_chat_global")
	main().open("friends", {"tab": "find"})
	await wait(4.0)
	await shot("f01_find")
	var rec: Dictionary = (await Api.get_json("/social/recommendations")).data
	for c in rec.items:
		if c.is_ai:
			var rr := await Api.post_json("/social/friends/request", {"user_id": c.user_id, "source": "recommend"})
			_log("ADD_AI %s -> %s" % [c.nickname, str(rr.data.get("status", rr.get("message", "")))])
			if rr.ok and rr.data.status == "friends":
				break
	await wait(1.0)
	main().open("friends")
	await wait(3.0)
	await shot("f02_friends")
	var fr: Dictionary = (await Api.get_json("/social/friends")).data
	_log("FRIENDS %d first_ai=%s" % [fr.friends.size(), str(fr.friends[0].is_ai) if fr.friends.size() > 0 else "-"])
	if fr.friends.size() > 0:
		var f: Dictionary = fr.friends[0]
		load("res://src/ui/PlayerPopup.gd").open(main().screen, String(f.user_id), main())
		await wait(3.0)
		await shot("f03_profile_popup")
		for p in get_tree().root.find_children("*", "Control", true, false):
			if p.get_script() and String(p.get_script().resource_path).ends_with("PlayerPopup.gd"):
				p.queue_free()
		main().open("chat", {"to_user": String(f.user_id), "name": String(f.nickname), "is_ai": bool(f.is_ai)})
		await wait(2.0)
		scr = main().screen
		scr._entry.text = "Привет! Ты бот? Подскажи совет по арене"
		await scr._send()
		_log("waiting for AI reply")
		await wait(40.0)
		await scr._poll()
		await wait(1.0)
		await shot("c02_dm_ai_reply")
	main().open("chat")
	await wait(3.0)
	await shot("c03_chat_after")
	main().open("world")
	await wait(1.5)
	await shot("m01_world")
	_log("SOCIAL_E2E_DONE")
	get_tree().quit()
