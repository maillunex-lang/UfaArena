extends Node
## Dev tool: renders a scene (or a world script) and saves a PNG.
## godot --path client res://tools/Shot.tscn -- <res://scene_or_script> <out.png> [frames] [setup]
func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var target: String = args[0]
	var out: String = args[1]
	var frames := int(args[2]) if args.size() > 2 else 90
	var node: Node
	if target.ends_with(".gd"):
		node = (load(target) as GDScript).new()
	else:
		node = (load(target) as PackedScene).instantiate()
	if args.size() > 3:
		node.set_meta("shot_setup", args[3])
	get_tree().root.add_child.call_deferred(node)
	for i in frames:
		await get_tree().process_frame
	if node.has_method("shot_hook"):
		await node.shot_hook()
		for i in 30:
			await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(out)
	print("SHOT_SAVED ", out)
	get_tree().quit()
