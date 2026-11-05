extends RefCounted
## Conservative rest-pose bounds for runtime glTF skins. Some exporters store the
## mesh and skeleton at different scales; raw mesh AABBs then cause GPU culling.

static func _relative_transform(ancestor: Node3D, node: Node3D) -> Transform3D:
	var result := Transform3D.IDENTITY
	var current: Node = node
	while current is Node3D and current != ancestor:
		result = (current as Node3D).transform * result
		current = current.get_parent()
	return result

static func fix_mesh(model: Node3D, mesh: MeshInstance3D) -> bool:
	if mesh.mesh == null or mesh.skin == null or mesh.skin.get_bind_count() == 0:
		return false
	var skeleton := mesh.get_node_or_null(mesh.skeleton) as Skeleton3D
	if skeleton == null or not model.is_ancestor_of(skeleton) or not model.is_ancestor_of(mesh):
		return false
	var mesh_to_model := _relative_transform(model, mesh)
	if absf(mesh_to_model.basis.determinant()) < 0.000000000001:
		return false
	var skeleton_to_mesh := mesh_to_model.affine_inverse() * _relative_transform(model, skeleton)
	var source := mesh.mesh.get_aabb()
	var expanded := source
	var valid := false
	for i in mesh.skin.get_bind_count():
		var bone := mesh.skin.get_bind_bone(i)
		if bone < 0:
			bone = skeleton.find_bone(mesh.skin.get_bind_name(i))
		if bone < 0 or bone >= skeleton.get_bone_count():
			continue
		var skin_transform := skeleton_to_mesh * skeleton.get_bone_global_rest(bone) * mesh.skin.get_bind_pose(i)
		var bounds: AABB = skin_transform * source
		if not bounds.position.is_finite() or not bounds.size.is_finite():
			continue
		expanded = expanded.merge(bounds)
		valid = true
	if not valid:
		return false
	# Allow ordinary arm and leg movement beyond the rest pose, while preserving
	# the original mesh bounds and any larger authored custom bounds.
	var margin := maxf(expanded.size.x, maxf(expanded.size.y, expanded.size.z)) * 0.5
	expanded = expanded.grow(margin)
	if mesh.custom_aabb.size != Vector3.ZERO:
		expanded = expanded.merge(mesh.custom_aabb)
	mesh.custom_aabb = expanded
	return true
