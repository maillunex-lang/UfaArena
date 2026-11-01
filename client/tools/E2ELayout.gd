extends Node
## Interface layout check (dev only): URALIA_E2E_LAYOUT=<dir>. The client builds the bottom bar, the main screen and
## «Ещё» from the admin layout sent by the server (Редактор игры → Интерфейс). Screenshots of both screens.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_LAYOUT")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func wait(s: float) -> void:
	await get_tree().create_timer(s, true, false, true).timeout


func shot(n: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + n + ".png")
	print("LAYOUT: shot ", n)


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(2.0)
	for d in get_tree().root.find_children("*", "Control", true, false):  # close the hero setup window if shown
		if d.get_script() and String(d.get_script().resource_path).ends_with("HeroSetupDialog.gd"):
			d._nick.text = "Макет_Тест"
			d._adult.button_pressed = true
			d._submit()
			await wait(2.0)
	var main: Node = get_tree().current_scene
	print("LAYOUT: version = ", Game.layout_version, " nav = ", main._nav_buttons.keys())
	main.open("home")
	await wait(2.5)
	await shot("layout_home")
	main.open("more")
	await wait(1.5)
	await shot("layout_more")
	get_tree().quit(0 if Game.layout_version > 0 else 1)
