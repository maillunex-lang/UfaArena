extends Node
## Online screens E2E (dev only): URALIA_E2E_ONLINE=<dir>. Guild, raids, arena, tournaments, events, rankings.
var out := ""


func _ready() -> void:
	out = OS.get_environment("URALIA_E2E_ONLINE")
	process_mode = Node.PROCESS_MODE_ALWAYS
	_run.call_deferred()


func _log(s: String) -> void:
	print("ONLINE: ", s)


func wait(sec: float) -> void:
	await get_tree().create_timer(sec, true, false, true).timeout


func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out + "/" + name + ".png")
	_log("shot " + name)


func scene_name() -> String:
	return String(get_tree().current_scene.name) if get_tree().current_scene else ""


func main() -> Node:
	return get_tree().current_scene


func wait_scene(n: String, timeout := 30.0) -> bool:
	var t := 0.0
	while scene_name() != n and t < timeout:
		await wait(0.25)
		t += 0.25
	return scene_name() == n


func screen() -> Node:
	return main().screen


func tab(t: String) -> void:
	screen().tab = t
	screen().render()
	await wait(2.5)


## Waits for the battle result panel, screenshots it and presses "Назад".
func finish_battle(name: String) -> void:
	if not await wait_scene("Battle", 10.0):
		_log("NO_BATTLE " + name)
		return
	Engine.time_scale = 1.0
	var b = get_tree().current_scene
	var t := 0.0
	while not b._finished and t < 120.0:
		b._speed = 8
		Engine.time_scale = 8.0
		await wait(0.5)
		t += 0.5
	Engine.time_scale = 1.0
	await wait(1.0)
	await shot(name)
	for n in b.find_children("*", "Button", true, false):
		if n.text == "Назад":
			n.pressed.emit()
	await wait_scene("Main", 20.0)
	await wait(2.0)


func _run() -> void:
	await wait_scene("Main", 60.0)
	await wait(3.0)
	for d in get_tree().root.find_children("*", "Control", true, false):
		if d.get_script() and (String(d.get_script().resource_path).ends_with("StoryDialog.gd") or String(d.get_script().resource_path).ends_with("UpdateDialog.gd")):
			d.queue_free()
	main().open("world")
	await wait(1.5)
	await shot("o00_world")
	# guild: join an AI guild that accepts level 1
	main().open("guild")
	await wait(3.0)
	await shot("o01_guild_find")
	var gl: Dictionary = (await Api.get_json("/guilds/list")).data
	for g in gl.items:
		if g.is_ai and int(g.min_level) <= 1:
			var r := await Api.post_json("/guilds/%s/join" % g.id, {})
			_log("JOIN %s -> %s" % [g.name, str(r.data)])
			break
	main().open("guild")
	await wait(3.0)
	for t in ["overview", "members", "fortress", "activities", "log"]:
		await tab(t)
		await shot("o02_guild_" + t)
	# raids
	main().open("raids")
	await wait(3.5)
	await shot("o03_raids")
	screen()._attack("guild", "Курганный Колосс", false)
	await finish_battle("o04_raid_result")
	main().open("raids", {"tab": "coop"})
	await wait(3.0)
	await shot("o05_raids_coop")
	# arena
	main().open("arena")
	await wait(3.5)
	await shot("o06_arena")
	var ad: Dictionary = (await Api.get_json("/arena")).data
	if ad.candidates.training.size() > 0:
		screen()._go(String(ad.candidates.training[0].user_id), String(ad.candidates.training[0].nickname), "training")
		await finish_battle("o07_arena_result")
	main().open("arena", {"tab": "history"})
	await wait(3.0)
	await shot("o08_arena_history")
	main().open("arena", {"tab": "season"})
	await wait(3.0)
	await shot("o09_arena_season")
	# tournaments
	main().open("tournaments")
	await wait(3.5)
	await shot("o10_tournaments")
	var td: Dictionary = (await Api.get_json("/tournaments")).data
	for t in td.current:
		if t.kind == "individual" and t.status == "registration" and t.mine == null:
			var r := await Api.post_json("/tournaments/%s/register" % t.id, {"teammates": []})
			_log("REGISTER %s -> %s" % [t.name, "ok" if r.ok else r.message])
			screen().detail_id = String(t.id)
			screen().render()
			await wait(3.0)
			await shot("o11_tournament_detail")
			break
	# events
	main().open("events")
	await wait(3.5)
	await shot("o12_events")
	var ed: Dictionary = (await Api.get_json("/events")).data
	if ed.active.size() > 0:
		screen()._battle(String(ed.active[0].id), String(ed.active[0].name))
		await finish_battle("o13_event_result")
	main().open("events", {"tab": "chronicle"})
	await wait(3.0)
	await shot("o14_chronicle")
	# rankings
	main().open("rankings")
	await wait(3.5)
	await shot("o15_rankings")
	main().open("rankings", {"tab": "achievements"})
	await wait(3.0)
	await shot("o16_achievements")
	main().open("rankings", {"tab": "legacy"})
	await wait(3.0)
	await shot("o17_legacy")
	_log("ONLINE_E2E_DONE")
	get_tree().quit()
