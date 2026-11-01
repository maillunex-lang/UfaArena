extends Node
## Art pipeline E2E (dev only): URALIA_E2E_ART=<dir>. Waits for the ui.art package and screenshots the home screen.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_ART")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await get_tree().create_timer(0.25).timeout
	for i in 120:
		if Content.has("art/icons/gold.png"):
			break
		if Content.has_pending():
			await Content.apply_pending()
		await get_tree().create_timer(0.5).timeout
	print("ART: has_gold_icon=", Content.has("art/icons/gold.png"))
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and (String(d.get_script().resource_path).ends_with("StoryDialog.gd") or String(d.get_script().resource_path).ends_with("UpdateDialog.gd")):
			d.queue_free()
	get_tree().current_scene.open("home")
	await get_tree().create_timer(2.0).timeout
	for c in get_tree().root.find_children("*", "Control", true, false):
		if c is GameIcon:
			c.queue_redraw()
	await get_tree().create_timer(0.5).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/art_home.png")
	print("ART: DONE")
	get_tree().quit()
