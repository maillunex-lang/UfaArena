extends Node3D
## Preview of a content package's fortress decor without a server: mounts a local zip directly.
func _ready() -> void:
	var zip := OS.get_environment("URALIA_PREVIEW_ZIP")
	Content._mount({"packages": []})
	var z := ZIPReader.new()
	z.open(zip)
	Content._readers["preview"] = z
	for f in z.get_files():
		Content._index[f] = "preview"
	var w: Node3D = load("res://src/world/HubWorld.gd").new()
	add_child(w)
	w.show_hero("gulnaz")
