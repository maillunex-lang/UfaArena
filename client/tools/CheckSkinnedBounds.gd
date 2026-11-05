extends SceneTree

const Bounds = preload("res://src/autoload/SkinnedBounds.gd")

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var model := Node3D.new()
	root.add_child(model)
	var skeleton := Skeleton3D.new()
	skeleton.scale = Vector3.ONE * 0.01
	model.add_child(skeleton)
	skeleton.add_bone("root")
	skeleton.set_bone_rest(0, Transform3D.IDENTITY)
	var mesh := MeshInstance3D.new()
	mesh.mesh = BoxMesh.new()
	mesh.skeleton = NodePath("..")
	mesh.skin = Skin.new()
	mesh.skin.add_bind(0, Transform3D(Basis.from_scale(Vector3.ONE * 100.0), Vector3.ZERO))
	skeleton.add_child(mesh)
	await process_frame
	var before: AABB = mesh.global_transform * mesh.get_aabb()
	assert(Bounds.fix_mesh(model, mesh))
	var after: AABB = mesh.global_transform * mesh.custom_aabb
	assert(before.size.y < 0.02 and after.size.y >= 1.0)
	assert(after.has_point(Vector3(0, 0.5, 0)))
	var rigid := MeshInstance3D.new()
	rigid.mesh = BoxMesh.new()
	model.add_child(rigid)
	assert(not Bounds.fix_mesh(model, rigid))
	assert(rigid.custom_aabb.size == Vector3.ZERO)
	print("Skinned bounds: OK")
	quit()
