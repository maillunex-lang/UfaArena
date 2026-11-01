extends Node
## Hero setup check (dev only): URALIA_E2E_SETUP=<dir>. A new player sees the hero creation window (nickname + 18+),
## fills it in, and the server stores the age group. Screenshots before/after.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_SETUP")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func wait(s: float) -> void:
	await get_tree().create_timer(s, true, false, true).timeout


func shot(n: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + n + ".png")
	print("SETUP: shot ", n)


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	var dlg: Node = null
	for i in 40:
		await wait(0.25)
		for d in get_tree().root.find_children("*", "Control", true, false):
			if d.get_script() and String(d.get_script().resource_path).ends_with("HeroSetupDialog.gd"):
				dlg = d
		if dlg:
			break
	print("SETUP: dialog shown = ", dlg != null)
	if dlg == null:
		get_tree().quit(1)
		return
	await wait(0.6)
	await shot("setup_1_window")
	dlg._nick.text = "Батыр_Тест"
	dlg._adult.button_pressed = true
	dlg._submit()
	await wait(2.0)
	print("SETUP: age_group = ", Game.profile.get("age_group"), " nickname = ", Game.profile.get("nickname"),
		" needs_setup = ", Game.profile.get("needs_setup"))
	await shot("setup_2_after")
	get_tree().quit(0 if Game.profile.get("age_group") == "adult" else 1)
