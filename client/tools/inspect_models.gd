extends SceneTree
func _aabb(n: Node) -> AABB:
	var a := AABB()
	var first := true
	for m in n.find_children("*", "MeshInstance3D", true, false):
		var b: AABB = (m as MeshInstance3D).get_aabb()
		if first: a = b; first = false
		else: a = a.merge(b)
	return a
func _init():
	for p in ["kaykit_hexagon/tiles/base/hex_grass.gltf","kaykit_hexagon/buildings/blue/building_castle_blue.gltf","kaykit_hexagon/buildings/blue/building_home_A_blue.gltf","kaykit_hexagon/decoration/nature/mountain_A_grass_trees.gltf","kaykit_adventurers/Knight.glb","kaykit_dungeon/chest_gold.glb"]:
		print(p, " ", _aabb(load("res://assets/third_party/" + p).instantiate()))
	quit()
