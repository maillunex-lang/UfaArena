extends Node
## UI walk (dev only): URALIA_E2E_UI=<dir>. Opens every main section and key screens, saves screenshots,
## reports script errors through the log.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_UI")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func wait(s: float) -> void:
	await get_tree().create_timer(s, true, false, true).timeout


func shot(n: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + n + ".png")
	print("UI: shot ", n)


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(2.5)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and String(d.get_script().resource_path).ends_with("StoryDialog.gd"):
			d.skip_all()
		elif d.get_script() and String(d.get_script().resource_path).ends_with("UpdateDialog.gd"):
			d.queue_free()
	var main: Node = get_tree().current_scene
	var t0 := Time.get_ticks_msec()
	for s in ["home", "heroes", "campaign", "guild", "world", "more", "profile", "inventory", "quests", "events", "shop", "settings", "mail", "summon", "friends", "chat", "rankings", "arena", "raids", "fortress"]:
		var st := Time.get_ticks_msec()
		main.open(s)
		await wait(3.0)
		print("UI: open %s %d ms (incl. 3 s wait)" % [s, Time.get_ticks_msec() - st])
		await shot("u_" + s)
	main.open("home")
	await wait(2.0)
	main._open_notifications()
	await wait(2.0)
	await shot("u_notifications")
	print("UI: memory static=%d MB" % int(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576))
	print("UI: fps=%d objects=%d nodes=%d" % [int(Performance.get_monitor(Performance.TIME_FPS)), int(Performance.get_monitor(Performance.OBJECT_COUNT)), int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))])
	print("UI: total %d ms" % (Time.get_ticks_msec() - t0))
	print("UI: DONE")
	get_tree().quit()
