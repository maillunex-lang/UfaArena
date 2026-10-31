extends SceneTree
func _init():
	var s: Node = load("res://assets/third_party/quaternius_monsters/Dragon.fbx").instantiate()
	var ap: AnimationPlayer = s.find_child("AnimationPlayer", true, false)
	print("anims: ", ap.get_animation_list() if ap else "none")
	var a := AABB(); var first := true
	for m in s.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = (m as MeshInstance3D).get_aabb()
		if first: a = b; first = false
		else: a = a.merge(b)
	print("aabb ", a, " root scale ", (s as Node3D).scale)
	quit()
