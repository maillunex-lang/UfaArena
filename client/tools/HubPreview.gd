extends Node3D
func _ready() -> void:
	var w: Node3D = load("res://src/world/HubWorld.gd").new()
	add_child(w)
	w.show_hero("azamat")
