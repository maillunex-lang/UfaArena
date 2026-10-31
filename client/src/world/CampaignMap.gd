extends Node3D
## Campaign region map: stylised hex map of the Shikhany around the Agidel (Belaya) river.
## Progress runs bottom -> top in portrait. Node world positions derive from server map_pos.

signal node_selected(code: String)

const SHIKHAN := {"1-4": "Юрактау", "1-5": "Куштау", "1-6": "Шахтау", "1-8": "Торатау"}

var camera: Camera3D
var nodes: Array = []
var _markers := {}
var _rng := RandomNumberGenerator.new()
var _cam_z := 0.0
var _cam_min := -20.0
var _cam_max := 2.0
var _drag_from := Vector2.ZERO
var _dragging := false
var _drag_dist := 0.0
var _pulse: Array[Node3D] = []
var _t := 0.0


func node_pos(n: Dictionary) -> Vector3:
	var mp: Array = n.get("map_pos", [0, 0])
	var w := Hex.to_world(int(mp[0]) * 2, int(mp[1]) * 2)
	return Vector3(w.z * 1.6 + 2.6, 0.0, -w.x)


func setup(region: Dictionary) -> void:
	nodes = region.get("nodes", [])
	_rng.seed = 42
	Hex.environment(self)
	Hex.sun(self, 0.95, Color(1, 0.95, 0.88), Vector3(-55, -25, 0))
	var occupied: Array[Vector3] = []
	for n in nodes:
		occupied.append(node_pos(n))
	_build_terrain(occupied)
	_build_path()
	for n in nodes:
		_build_marker(n)
	camera = Camera3D.new()
	camera.fov = 46
	add_child(camera)
	camera.current = true
	_cam_max = 2.0
	_cam_min = node_pos(nodes[-1]).z + 3.0 if nodes.size() > 0 else -20.0
	var focus := _focus_node()
	_cam_z = clampf(node_pos(focus).z + 3.0, _cam_min, _cam_max) if not focus.is_empty() else 0.0
	_update_camera()


func _focus_node() -> Dictionary:
	for n in nodes:
		if n.unlocked and not n.cleared:
			return n
	return nodes[-1] if nodes.size() > 0 else {}


func _river_x(z: float) -> float:
	return -6.5 + sin(z * 0.18) * 1.6


func _build_terrain(occupied: Array[Vector3]) -> void:
	for r in range(-20, 6):
		for q in range(-16, 22):
			var p := Hex.to_world(q, r)
			if p.x < -11.5 or p.x > 12.5:
				continue
			var near_river: bool = abs(p.x - _river_x(p.z)) < 1.2
			if near_river:
				Hex.tile(self, "base/hex_water", q, r)
				continue
			Hex.tile(self, "base/hex_grass", q, r)
			var free := true
			for o in occupied:
				if p.distance_to(o) < 2.6:
					free = false
					break
			if free and _rng.randf() < 0.42:
				var deco: String = Hex.NATURE[_rng.randi() % Hex.NATURE.size()]
				Hex.put(self, deco, p, _rng.randf() * TAU)
	# Sterlitamak: a cluster of houses near the 1-3 outpost
	for n in nodes:
		var pos := node_pos(n)
		match n.code:
			"1-3":
				for off in [Vector3(-2.2, 0, -1.2), Vector3(2.1, 0, -1.6), Vector3(-1.6, 0, 1.6), Vector3(2.4, 0, 1.2)]:
					Hex.put(self, "buildings/blue/building_home_A_blue.gltf", pos + off, _rng.randf() * TAU, 1.2)
				Hex.put(self, "buildings/blue/building_tower_A_blue.gltf", pos + Vector3(0, 0, -2.4), 0.0, 1.0)
			"1-4", "1-5", "1-8":
				var m: String = "decoration/nature/mountain_A_grass_trees.gltf" if n.code != "1-8" else "decoration/nature/mountain_B_grass_trees.gltf"
				Hex.put(self, m, pos + Vector3(0, 0, -2.6), 0.4, 2.6 if n.code == "1-8" else 2.0)
			"1-6":
				Hex.put(self, "decoration/nature/mountain_C.gltf", pos + Vector3(0.4, -0.3, -2.4), 1.2, 1.7)
				Hex.put(self, "buildings/neutral/building_destroyed.gltf", pos + Vector3(-1.8, 0, -0.8), 0.6, 1.1)
				Hex.put(self, "decoration/props/resource_stone.gltf", pos + Vector3(1.8, 0, 0.6), 0.0, 1.2)
			"1-7":
				Hex.put(self, "decoration/nature/hills_C_trees.gltf", pos + Vector3(0, 0, -2.2), 0.0, 1.8)
	# distant Ural ridge on the far edge
	for i in 9:
		Hex.put(self, Hex.MOUNTAINS[i % Hex.MOUNTAINS.size()], Vector3(-12 + i * 3.2, -0.4, -40 - _rng.randf() * 4), _rng.randf() * TAU, 3.0)


func _build_path() -> void:
	var mat_done := StandardMaterial3D.new()
	mat_done.albedo_color = Color(1.0, 0.82, 0.4)
	mat_done.emission_enabled = true
	mat_done.emission = Color(1.0, 0.7, 0.25)
	mat_done.emission_energy_multiplier = 0.8
	var mat_todo := StandardMaterial3D.new()
	mat_todo.albedo_color = Color(0.92, 0.9, 0.85)
	var dot := SphereMesh.new()
	dot.radius = 0.13
	dot.height = 0.18
	for i in range(nodes.size() - 1):
		var a := node_pos(nodes[i])
		var b := node_pos(nodes[i + 1])
		var steps := int(a.distance_to(b) / 0.7)
		for s in range(1, steps):
			var mi := MeshInstance3D.new()
			mi.mesh = dot
			mi.material_override = mat_done if nodes[i + 1].cleared or nodes[i].cleared else mat_todo
			mi.position = a.lerp(b, float(s) / steps) + Vector3(0, 0.08, 0)
			add_child(mi)


func _build_marker(n: Dictionary) -> void:
	var root := Node3D.new()
	root.position = node_pos(n)
	add_child(root)
	var stage := Hex.put(root, "buildings/neutral/building_stage_A.gltf", Vector3.ZERO, 0.0, 0.9)
	stage.position.y = 0.0
	var flag := "decoration/props/flag_blue.gltf" if n.cleared else ("decoration/props/flag_yellow.gltf" if n.unlocked else "decoration/props/flag_red.gltf")
	Hex.put(root, flag, Vector3(0.7, 0.3, 0.2), 0.0, 1.6)
	if n.is_boss:
		var boss := Models.spawn("e_boss_toratau")
		boss.scale *= 0.55
		boss.position = Vector3(-0.3, 0.3, 0)
		root.add_child(boss)
	var lbl := Label3D.new()
	lbl.text = "%s  %s" % [n.code, n.name]
	lbl.font = UI.FONT_BOLD
	lbl.font_size = 64
	lbl.pixel_size = 0.006
	lbl.outline_size = 14
	lbl.modulate = Color(1, 0.95, 0.8) if n.unlocked else Color(0.75, 0.75, 0.8)
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.position = Vector3(0, 2.6, 0)
	lbl.no_depth_test = true
	root.add_child(lbl)
	if SHIKHAN.has(n.code):
		var sub := Label3D.new()
		sub.text = "шихан " + SHIKHAN[n.code]
		sub.font = UI.FONT_REG
		sub.font_size = 48
		sub.pixel_size = 0.006
		sub.outline_size = 10
		sub.modulate = Color(0.8, 0.92, 1.0)
		sub.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		sub.position = Vector3(0, 2.15, 0)
		sub.no_depth_test = true
		root.add_child(sub)
	if n.unlocked and not n.cleared:
		var ring := MeshInstance3D.new()
		var torus := TorusMesh.new()
		torus.inner_radius = 1.25
		torus.outer_radius = 1.45
		ring.mesh = torus
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(1, 0.85, 0.4)
		m.emission_enabled = true
		m.emission = Color(1, 0.7, 0.2)
		m.emission_energy_multiplier = 2.5
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		ring.material_override = m
		ring.position.y = 0.35
		root.add_child(ring)
		_pulse.append(ring)
		var arrow := Label3D.new()
		arrow.text = "▼"
		arrow.font_size = 96
		arrow.pixel_size = 0.008
		arrow.modulate = Color(1, 0.85, 0.35)
		arrow.outline_size = 12
		arrow.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		arrow.position = Vector3(0, 3.4, 0)
		arrow.no_depth_test = true
		root.add_child(arrow)
		_pulse.append(arrow)
	_markers[n.code] = root


func _update_camera() -> void:
	camera.position = Vector3(0.5, 15.0, _cam_z + 11.0)
	camera.look_at(Vector3(0.5, 0, _cam_z - 1.5))


func _process(delta: float) -> void:
	_t += delta
	for p in _pulse:
		if p is Label3D:
			p.position.y = 3.4 + sin(_t * 4.0) * 0.18
		else:
			var s := 1.0 + sin(_t * 3.0) * 0.06
			p.scale = Vector3(s, 1, s)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch or (event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT):
		if event.pressed:
			_dragging = true
			_drag_dist = 0.0
			_drag_from = event.position
		else:
			_dragging = false
			if _drag_dist < 24.0:
				_tap(event.position)
	elif (event is InputEventScreenDrag or event is InputEventMouseMotion) and _dragging:
		var d: Vector2 = event.position - _drag_from
		_drag_from = event.position
		_drag_dist += d.length()
		_cam_z = clampf(_cam_z - d.y * 0.03, _cam_min, _cam_max)
		_update_camera()


func _tap(screen_pos: Vector2) -> void:
	var from := camera.project_ray_origin(screen_pos)
	var dir := camera.project_ray_normal(screen_pos)
	if abs(dir.y) < 0.001:
		return
	var hit := from + dir * (-from.y / dir.y)
	var best := ""
	var best_d := 2.2
	for n in nodes:
		var d := node_pos(n).distance_to(hit)
		# also accept taps on the floating label above the node
		var lbl_d := (node_pos(n) + Vector3(0, 2.6, 0)).distance_to(from + dir * from.distance_to(node_pos(n) + Vector3(0, 2.6, 0)))
		d = min(d, lbl_d)
		if d < best_d:
			best_d = d
			best = n.code
	if best != "":
		node_selected.emit(best)
