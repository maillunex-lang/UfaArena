extends Node
## Guild screen E2E (dev only): URALIA_E2E_GUILD=<dir>. Becomes a guild leader and screenshots every section.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_GUILD")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func wait(s: float) -> void:
	await get_tree().create_timer(s, true, false, true).timeout


func shot(n: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + n + ".png")
	print("GUILD: shot ", n)


func _run() -> void:
	while get_tree().current_scene == null or get_tree().current_scene.name != "Main":
		await wait(0.25)
	await wait(2.0)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and (String(d.get_script().resource_path).ends_with("StoryDialog.gd") or String(d.get_script().resource_path).ends_with("UpdateDialog.gd")):
			d.queue_free()
	print("GUILD_UID ", Api.user_id)
	while not FileAccess.file_exists(out + "/ready.flag"):
		await wait(0.5)
	var r := await Api.post_json("/guilds/create", {"name": "Бурзяне", "tag": "БРЗ", "description": "Активная гильдия Уралии. Рейды, события, развитие. Вместе к вершинам!", "join_mode": "approval"}, true)
	print("GUILD: create ", r.ok, " ", r.get("message", ""))
	await Api.post_json("/guilds/edit", {"emblem": "wolf", "min_level": 30, "min_power": 500000, "notify_chat": true})
	var main: Node = get_tree().current_scene
	main.open("guild", {"tab": "manage"})
	await wait(3.0)
	await shot("g01_manage_form")
	for t in ["overview", "members", "apps", "ranks", "tech", "events", "wars", "treasury", "settings"]:
		main.screen.tab = t
		main.screen.render()
		await wait(2.5)
		await shot("g_" + t)
	main.screen.tab = "manage"
	main.screen.sub = "rights"
	main.screen.render()
	await wait(2.5)
	await shot("g02_rights")
	print("GUILD: DONE")
	get_tree().quit()
