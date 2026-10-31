extends Node
## E2E for the Uralia Update System (dev only). Enabled with URALIA_E2E_UPDATE=<dir>.
## A shell orchestrator performs server-side actions (publish / rollback / corrupt / kill switch)
## when this driver writes <dir>/step_<n>.ready, and answers with <dir>/step_<n>.done.

var dir := ""


func _ready() -> void:
	dir = OS.get_environment("URALIA_E2E_UPDATE")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func _log(s: String) -> void:
	print("UPD: ", s)


func wait(sec: float) -> void:
	await get_tree().create_timer(sec, true, false, true).timeout


func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(dir + "/" + name + ".png")


func step(n: int) -> void:
	var f := FileAccess.open(dir + "/step_%d.ready" % n, FileAccess.WRITE)
	f.store_string("1")
	f.close()
	var t := 0.0
	while not FileAccess.file_exists(dir + "/step_%d.done" % n) and t < 60.0:
		await wait(0.25)
		t += 0.25


func active_ids() -> Array:
	var out := []
	for p in Content.active.get("packages", []):
		out.append("%s@%d" % [p.package_id, int(p.version)])
	return out


func decor_count() -> int:
	return get_tree().get_nodes_in_group("content_decor").size()


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(2.0)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and String(d.get_script().resource_path).ends_with("StoryDialog.gd"):
			d.queue_free()
	_log("BOOT active=%s decor=%d" % [active_ids(), decor_count()])
	await shot("u00_before")
	# 1) publish autumn fair -> background download -> applied on home without restart
	await step(1)
	var c := await Content.poll_now()
	await wait(3.0)
	_log("PUBLISH status=%s active=%s decor=%d music_override=%s" % [c.get("status"), active_ids(), decor_count(),
		str(Content.has("music/hub.ogg"))])
	await shot("u01_autumn_hub")
	get_tree().current_scene.open("heroes")
	await wait(3.0)
	await shot("u02_heroes_autumn_look")
	get_tree().current_scene.open("home")
	await wait(1.0)
	# 2) server rollback to the previous manifest
	await step(2)
	await Content.poll_now()
	await wait(2.0)
	_log("ROLLBACK active=%s decor=%d" % [active_ids(), decor_count()])
	# 3) resumable download: v2 of the package, interrupted after the first chunk, then resumed
	await step(3)
	var cut := func(done: int, total: int):
		if done > 0 and done < total and Content._dl:
			Content._dl.cancelled = true
	Content.progress.connect(cut)
	var c3 := await Content.check()
	var first := await Content.sync(false)
	Content.progress.disconnect(cut)
	var second := await Content.sync(false)
	await Content.apply_pending()
	await wait(1.5)
	_log("RESUME first=%s second_ok=%s resumed_bytes=%d active=%s" % [first.get("status"), str(second.ok),
		int(second.get("resumed_bytes", 0)), active_ids()])
	# 4) corrupted file on the server -> hash mismatch, nothing applied
	await step(4)
	var before := active_ids()
	var c4 := await Content.poll_now()
	await wait(1.0)
	_log("CORRUPT last_error=%s active_unchanged=%s" % [Content.last_error, str(before == active_ids())])
	# 5) kill switch
	await step(5)
	await Content.poll_now()
	await wait(2.0)
	_log("KILL active=%s decor=%d" % [active_ids(), decor_count()])
	await shot("u03_kill_switch")
	await step(6)
	await Content.poll_now()
	await wait(2.5)
	_log("RESTORE active=%s decor=%d" % [active_ids(), decor_count()])
	_log("UPDATE_E2E_DONE")
	get_tree().quit()
