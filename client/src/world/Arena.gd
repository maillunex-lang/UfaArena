extends Node3D
## Side-view 3D battle arena (player's team on the left, enemies on the right, camera slightly
## above — AFK-style). Unit positions come straight from the server's real-time simulation.

const UNIT_SCALE := 1.0
const SIM_X := 0.78  # portrait screen: compress the battle line horizontally
const SIM_Z := 1.5   # ...and stretch formation depth so rows read vertically
const FACE_BIAS := 0.55  # turn models 3/4 towards the camera
const BAR_SHADER := preload("res://src/world/bar.gdshader")

var camera: Camera3D
var units := {}  # uid -> {node, bar, data, hp, max_hp, shield, energy, alive, home}
var _rng := RandomNumberGenerator.new()
var _shake := 0.0
var _cam_base := Vector3(0, 10.5, 15.5)
var _look := Vector3(0, 0.6, -0.2)


func build(territory: String, is_boss: bool) -> void:
	_rng.seed = hash(territory)
	var mood := "day"
	var tint := Color(0.7, 0.9, 0.62)
	match territory:
		"dungeons":
			mood = "dungeon"
			tint = Color(0.45, 0.45, 0.55)
		"resources", "complexes":
			mood = "dusk"
			tint = Color(0.75, 0.78, 0.6)
		"dimensions":
			mood = "dusk"
			tint = Color(0.6, 0.55, 0.75)
	Hex.environment(self, mood)
	var sun := Hex.sun(self, 0.95 if mood == "day" else 0.55, Color(1, 0.95, 0.88) if mood == "day" else Color(0.85, 0.7, 1.0))
	sun.rotation_degrees = Vector3(-55, -30, 0)
	for q in range(-8, 9):
		for r in range(-8, 9):
			var d := Hex.dist(q, r)
			var p := Hex.to_world(q, r)
			if abs(p.x) > 14.0 or p.z > 16.0 or p.z < -16.0:
				continue
			Hex.tile(self, "base/hex_grass", q, r, 0, tint if abs(p.z) < 4.5 and abs(p.x) < 9.0 else tint.darkened(0.08))
			# backdrop: decoration behind the battle line and at the far sides, never in front of the camera
			if (p.z < -4.5 or (abs(p.x) > 8.5 and p.z < 2.0)) and _rng.randf() < 0.6:
				_decorate(territory, p)
	if mood != "day":
		for p in [Vector3(-6.5, 0, -3.2), Vector3(6.5, 0, -3.2), Vector3(-2.5, 0, -3.6), Vector3(2.5, 0, -3.6)]:
			var torch: Node3D = load("res://assets/third_party/kaykit_dungeon/torch_lit.gltf.glb").instantiate()
			torch.position = p
			torch.scale = Vector3.ONE * 1.6
			add_child(torch)
			var l := OmniLight3D.new()
			l.light_color = Color(1.0, 0.65, 0.3)
			l.light_energy = 2.2
			l.omni_range = 6.0
			l.position = p + Vector3(0, 2.0, 0)
			add_child(l)
	if is_boss:
		var portal := _ring_mesh(Color(0.7, 0.25, 1.0), 2.4, 2.75)
		portal.position = Vector3(6.0, 0.05, -2.6)
		add_child(portal)
	camera = Camera3D.new()
	camera.fov = 44
	add_child(camera)
	camera.current = true
	_update_camera()


func _decorate(territory: String, p: Vector3) -> void:
	var pool: Array = Hex.NATURE
	match territory:
		"settlements":
			pool = ["buildings/red/building_home_A_red.gltf", "buildings/red/building_home_B_red.gltf",
				"decoration/props/crate_A_big.gltf", "decoration/props/barrel.gltf"] + Hex.NATURE
		"dungeons", "resources":
			pool = ["decoration/nature/rock_single_A.gltf", "decoration/nature/rock_single_C.gltf",
				"decoration/nature/rock_single_E.gltf", "decoration/nature/mountain_C.gltf", "decoration/props/resource_stone.gltf"]
		"dimensions", "complexes":
			pool = ["decoration/nature/rock_single_B.gltf", "decoration/nature/tree_single_A_cut.gltf",
				"decoration/nature/mountain_B.gltf", "buildings/neutral/building_destroyed.gltf"]
	Hex.put(self, pool[_rng.randi() % pool.size()], p, _rng.randf() * TAU, 0.9 + _rng.randf() * 0.4)


func _update_camera() -> void:
	var shake := Vector3(_rng.randf_range(-1, 1), _rng.randf_range(-1, 1), 0) * _shake
	camera.position = _cam_base + shake
	camera.look_at(_look + shake * 0.5)


func _process(delta: float) -> void:
	if _shake > 0.0:
		_shake = max(0.0, _shake - delta * 1.6)
	_update_camera()
	for uid in units:
		var u: Dictionary = units[uid]
		var m: ShaderMaterial = u.bar.material_override
		var trail: float = float(m.get_shader_parameter("hp_trail")) if m.get_shader_parameter("hp_trail") != null else 1.0
		var hp_n: float = float(u.hp) / float(u.max_hp)
		if trail > hp_n:
			m.set_shader_parameter("hp_trail", max(hp_n, trail - delta * 0.6))


func shake(amount := 0.35) -> void:
	_shake = max(_shake, amount)


func sim_pos(x: float, z: float) -> Vector3:
	return Vector3(x * SIM_X, 0, z * SIM_Z)


func rest_yaw(side: int) -> float:
	return (PI / 2 - FACE_BIAS) if side == 0 else -(PI / 2 - FACE_BIAS)


## Yaw to face a point, biased 3/4 towards the camera so faces stay visible.
func yaw_to(from: Vector3, to: Vector3) -> float:
	var d := to - from
	if d.length() < 0.01:
		return 0.0
	var y := atan2(d.x, d.z)
	return y - FACE_BIAS * signf(y) * 0.6


func add_unit(data: Dictionary) -> void:
	var node := Models.spawn(data.code)
	var side: int = data.side
	node.position = sim_pos(float(data.x), float(data.z))
	node.rotation.y = rest_yaw(side)
	node.scale *= UNIT_SCALE
	add_child(node)
	var bar := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2(1.5, 0.24)
	bar.mesh = quad
	var mat := ShaderMaterial.new()
	mat.shader = BAR_SHADER
	mat.set_shader_parameter("hp_color", Color(0.36, 0.86, 0.45) if side == 0 else Color(0.92, 0.32, 0.3))
	mat.set_shader_parameter("hp_trail", 1.0)
	bar.material_override = mat
	var lk_scale: float = Models.look(data.code).get("scale", 1.0)
	bar.position = Vector3(0, 3.2 * lk_scale, 0)
	bar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(bar)
	bar.scale = Vector3.ONE / node.scale.x
	var lv := Label3D.new()
	lv.text = str(int(data.level))
	lv.font = UI.FONT_BOLD
	lv.font_size = 44
	lv.pixel_size = 0.006
	lv.outline_size = 10
	lv.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lv.no_depth_test = true
	lv.position = Vector3(-0.92, 0, 0.01)
	lv.modulate = Color(1, 0.9, 0.6)
	bar.add_child(lv)
	var ring := _ring_mesh(Game.RARITY_COLORS.get(int(data.rarity), Color.WHITE) if side == 0 else Color(0.9, 0.3, 0.3), 0.55, 0.65)
	ring.position = Vector3(0, 0.04, 0)
	ring.scale = Vector3(1, 0.15, 1) / node.scale.x
	node.add_child(ring)
	units[data.uid] = {"node": node, "bar": bar, "ring": ring, "data": data, "hp": int(data.hp),
		"max_hp": int(data.max_hp), "shield": 0, "energy": 0, "alive": true, "home": node.position,
		"side": side, "target_pos": node.position, "busy_until": 0.0, "moving": false}
	set_bar(data.uid)


func set_bar(uid: String) -> void:
	var u: Dictionary = units[uid]
	var m: ShaderMaterial = u.bar.material_override
	m.set_shader_parameter("hp", float(u.hp) / float(u.max_hp))
	m.set_shader_parameter("shield", clampf(float(u.shield) / float(u.max_hp), 0.0, 1.0))
	m.set_shader_parameter("energy", clampf(float(u.energy) / 100.0, 0.0, 1.0))


func chest(uid: String) -> Vector3:
	var u: Dictionary = units[uid]
	return u.node.position + Vector3(0, 1.3 * UNIT_SCALE * u.node.scale.y / UNIT_SCALE, 0)


# ------------------------------------------------------------------ VFX
func _ring_mesh(color: Color, inner: float, outer: float) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var t := TorusMesh.new()
	t.inner_radius = inner
	t.outer_radius = outer
	t.rings = 32
	mi.mesh = t
	mi.scale = Vector3(1, 0.15, 1)
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = color
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.emission_enabled = true
	m.emission = color
	m.emission_energy_multiplier = 2.0
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi


func burst(pos: Vector3, color: Color, amount := 24, speed := 4.0, up := false) -> void:
	var p := CPUParticles3D.new()
	p.amount = max(4, int(amount * float(Gfx.setting("particles"))))
	p.one_shot = true
	p.explosiveness = 0.95 if not up else 0.4
	p.lifetime = 0.7 if not up else 1.1
	p.direction = Vector3.UP
	p.spread = 180.0 if not up else 25.0
	p.initial_velocity_min = speed * 0.5
	p.initial_velocity_max = speed
	p.gravity = Vector3(0, -6, 0) if not up else Vector3(0, 1.5, 0)
	p.scale_amount_min = 0.06
	p.scale_amount_max = 0.14
	var mesh := SphereMesh.new()
	mesh.radius = 0.5
	mesh.height = 1.0
	mesh.radial_segments = 6
	mesh.rings = 3
	p.mesh = mesh
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = color
	m.emission_enabled = true
	m.emission = color
	m.emission_energy_multiplier = 3.0
	p.material_override = m
	var grad := Gradient.new()
	grad.set_color(0, Color(1, 1, 1, 1))
	grad.set_color(1, Color(1, 1, 1, 0))
	p.color_ramp = grad
	p.position = pos
	add_child(p)
	p.emitting = true
	get_tree().create_timer(p.lifetime + 0.3).timeout.connect(p.queue_free)


func shockwave(pos: Vector3, color: Color, radius := 4.0) -> void:
	var r := _ring_mesh(color, 0.2, 0.45)
	r.position = pos + Vector3(0, 0.1, 0)
	add_child(r)
	var tw := r.create_tween().set_parallel(true)
	tw.tween_property(r, "scale", Vector3(radius, 0.2, radius), 0.55).set_ease(Tween.EASE_OUT).set_trans(Tween.TRANS_CUBIC)
	tw.tween_property(r.material_override, "albedo_color:a", 0.0, 0.55)
	tw.chain().tween_callback(r.queue_free)


func projectile(from: Vector3, to: Vector3, color: Color, size := 0.18, time := 0.35) -> void:
	var mi := MeshInstance3D.new()
	var s := SphereMesh.new()
	s.radius = size
	s.height = size * 2
	mi.mesh = s
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = color.lightened(0.4)
	m.emission_enabled = true
	m.emission = color
	m.emission_energy_multiplier = 4.0
	mi.material_override = m
	mi.position = from
	add_child(mi)
	var trail := CPUParticles3D.new()
	trail.amount = max(4, int(18 * float(Gfx.setting("particles"))))
	trail.lifetime = 0.3
	trail.local_coords = false
	trail.gravity = Vector3.ZERO
	trail.initial_velocity_max = 0.3
	trail.scale_amount_min = size * 0.6
	trail.scale_amount_max = size
	trail.mesh = s
	trail.material_override = m
	var grad := Gradient.new()
	grad.set_color(0, Color(1, 1, 1, 0.9))
	grad.set_color(1, Color(1, 1, 1, 0))
	trail.color_ramp = grad
	mi.add_child(trail)
	var mid := from.lerp(to, 0.5) + Vector3(0, 1.2, 0)
	var tw := mi.create_tween()
	tw.tween_method(func(t: float):
		var a := from.lerp(mid, t)
		var b := mid.lerp(to, t)
		mi.position = a.lerp(b, t), 0.0, 1.0, time)
	tw.tween_callback(mi.queue_free)


func float_text(pos: Vector3, text: String, color: Color, big := false) -> void:
	var l := Label3D.new()
	l.text = text
	l.font = UI.FONT_BOLD
	l.font_size = 96 if big else 72
	l.pixel_size = 0.008
	l.outline_size = 18
	l.outline_modulate = Color(0.05, 0.02, 0.0, 0.9)
	l.modulate = color
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	l.position = pos + Vector3(_rng.randf_range(-0.3, 0.3), 0.6, 0)
	add_child(l)
	l.scale = Vector3.ONE * (0.6 if not big else 0.8)
	var tw := l.create_tween().set_parallel(true)
	tw.tween_property(l, "scale", Vector3.ONE * (1.0 if not big else 1.35), 0.12)
	tw.tween_property(l, "position:y", l.position.y + 1.4, 0.9).set_ease(Tween.EASE_OUT)
	tw.tween_property(l, "modulate:a", 0.0, 0.35).set_delay(0.6)
	tw.chain().tween_callback(l.queue_free)


func shield_bubble(uid: String, on: bool) -> void:
	var u: Dictionary = units[uid]
	var existing: Node = u.node.get_node_or_null("Shield")
	if on and existing == null:
		var mi := MeshInstance3D.new()
		mi.name = "Shield"
		var s := SphereMesh.new()
		s.radius = 1.3
		s.height = 2.8
		mi.mesh = s
		mi.position = Vector3(0, 1.3, 0)
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.albedo_color = Color(0.5, 0.85, 1.0, 0.22)
		m.emission_enabled = true
		m.emission = Color(0.4, 0.75, 1.0)
		m.rim_enabled = true
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
		mi.material_override = m
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		u.node.add_child(mi)
		mi.scale = Vector3.ONE * 0.2
		mi.create_tween().tween_property(mi, "scale", Vector3.ONE, 0.25).set_trans(Tween.TRANS_BACK)
	elif not on and existing:
		existing.queue_free()


func stun_mark(uid: String, on: bool) -> void:
	var u: Dictionary = units[uid]
	var existing: Node = u.node.get_node_or_null("Stun")
	if on and existing == null:
		var l := Label3D.new()
		l.name = "Stun"
		l.text = "✦ ✦ ✦"
		l.font_size = 64
		l.pixel_size = 0.007
		l.modulate = Color(1, 0.9, 0.3)
		l.outline_size = 10
		l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		l.position = Vector3(0, 3.0, 0)
		u.node.add_child(l)
	elif not on and existing:
		existing.queue_free()
