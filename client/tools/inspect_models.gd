extends SceneTree
func _init():
	for f in ["pillar_decorated","banner_triple_red","barrel_large_decorated","chest_gold","torch_lit"]:
		var doc := GLTFDocument.new(); var st := GLTFState.new()
		doc.append_from_file("res://../content_src/fortress_autumn_fair/models/%s.glb" % f, st)
		var n: Node = doc.generate_scene(st)
		var a := AABB(); var first := true
		for m in n.find_children("*", "MeshInstance3D", true, false):
			var b: AABB = (m as MeshInstance3D).get_aabb()
			if first: a = b; first = false
			else: a = a.merge(b)
		print(f, " ", a.size)
	quit()
