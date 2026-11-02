extends Node
## Dev only: URALIA_E2E_UIMAP=<dir> — builds the bundled interface map (all screens: elements + screenshots) and,
## with URALIA_E2E_UIRULES=1, checks that admin screen rules are applied (rename / hide / where a button leads).
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_UIMAP")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func wait(s: float) -> void:
	await get_tree().create_timer(s, true, false, true).timeout


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(2.0)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if not is_instance_valid(d):
			continue
		if d.get_script() and String(d.get_script().resource_path).ends_with("HeroSetupDialog.gd"):
			d._nick.text = "Картограф"
			d._adult.button_pressed = true
			d._submit()
			await wait(2.0)
			break
	var main: Node = get_tree().current_scene
	for i in 12:  # close the prologue / guide overlays of a fresh account
		var hit := false
		for b in get_tree().root.find_children("*", "Button", true, false):
			if is_instance_valid(b) and b.is_visible_in_tree() and b.text in ["Пропустить", "Закрыть", "Понятно"]:
				b.pressed.emit()
				hit = true
				break
		for d in get_tree().root.find_children("*", "Control", true, false):
			if is_instance_valid(d) and d.get_script() and String(d.get_script().resource_path).ends_with("StoryDialog.gd"):
				d.queue_free()
				hit = true
		if not hit:
			break
		await wait(0.8)
	if OS.get_environment("URALIA_E2E_UIRULES") != "":
		main.open("more")
		await wait(2.0)
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(out + "/rules_more.png")
		var names := []
		for b in main.screen.find_children("*", "Button", true, false):
			if b.is_visible_in_tree():
				names.append(preload("res://src/ui/UIOverrides.gd").first_label(b).text if preload("res://src/ui/UIOverrides.gd").first_label(b) else b.text)
		print("UIRULES: more buttons = ", names)
		for b in main.screen.find_children("*", "Button", true, false):
			var l = preload("res://src/ui/UIOverrides.gd").first_label(b)
			if l and l.text == "Рейтинг":
				b.pressed.emit()
				break
		await wait(1.5)
		print("UIRULES: after tap current = ", main.current)
		get_tree().quit(0)
		return
	var m: Node = preload("res://src/ui/UIMapper.gd").new()
	m.main = main
	m.out_dir = out
	main.add_child(m)
	await m.run()
	print("UIMAP: done")
	get_tree().quit(0)
