extends Node
## Loads every script under res://src and reports compile errors (run as main scene).
func _ready() -> void:
	var bad := 0
	for f in _files("res://src"):
		var s = ResourceLoader.load(f, "", ResourceLoader.CACHE_MODE_IGNORE)
		if s == null or (s is GDScript and not (s as GDScript).can_instantiate() and not f.ends_with("UI.gd") and not f.ends_with("Hex.gd") and not f.ends_with("ContentUpdater.gd")):
			print("BROKEN ", f)
			bad += 1
	print("CHECK_DONE broken=", bad)
	get_tree().quit(1 if bad else 0)
func _files(dir: String) -> Array:
	var out := []
	for d in DirAccess.get_directories_at(dir):
		out += _files(dir + "/" + d)
	for f in DirAccess.get_files_at(dir):
		if f.ends_with(".gd"):
			out.append(dir + "/" + f)
	return out
