extends Node3D
## Крепость хранителей: diorama on a hex island in the waters of Agidel, Ural ridges behind.
## The selected hero stands in the centre (GDD: «герой в центре на фоне крепости»).

const BUILDING_MODELS := {
	"summon_hall": "buildings/blue/building_church_blue.gltf",
	"forge": "buildings/blue/building_blacksmith_blue.gltf",
	"training": "buildings/blue/building_barracks_blue.gltf",
	"alchemy": "buildings/blue/building_tower_B_blue.gltf",
	"storage": "buildings/blue/building_market_blue.gltf",
	"guild_house": "buildings/blue/building_tavern_blue.gltf",
}
const BUILDING_POS := {
	"summon_hall": Vector3(-5.2, 0, -2.2), "forge": Vector3(5.4, 0, -3.0), "training": Vector3(-6.0, 0, 2.2),
	"alchemy": Vector3(6.2, 0, 1.4), "storage": Vector3(-3.2, 0, -6.4), "guild_house": Vector3(3.4, 0, -6.8),
}
const BUILDING_SCALE := 1.7

var camera: Camera3D
var hero: Node3D
var hero_code := ""
var _t := 0.0
var _rng := RandomNumberGenerator.new()
var _cam_base := Vector3(0, 5.2, 12.5)
var _look := Vector3(0, 0.9, -2.0)


func _ready() -> void:
	_rng.seed = 7
	Hex.environment(self)
	Hex.sun(self)
	_build_island()
	camera = Camera3D.new()
	camera.fov = 50
	camera.position = _cam_base
	add_child(camera)
	camera.look_at(_look)
	camera.current = true


func _build_island() -> void:
	for q in range(-9, 10):
		for r in range(-9, 10):
			var d := Hex.dist(q, r)
			if d > 9:
				continue
			if d <= 6:
				var road: bool = abs(q + r / 2.0) < 0.6 and r >= -3 and r <= 3
				Hex.tile(self, "base/hex_grass", q, r, 0, Color(0.82, 0.86, 0.7) if road else Color(0.7, 0.9, 0.62))
				if d >= 5 and not road and r < 3 and _free(Hex.to_world(q, r)):
					var deco: String = Hex.NATURE[_rng.randi() % Hex.NATURE.size()]
					Hex.put(self, deco, Hex.to_world(q, r), _rng.randf() * TAU)
			else:
				Hex.tile(self, "base/hex_water", q, r)
				# Ural ridge across the water behind the fortress
				if r <= -8 and _rng.randf() < 0.9:
					var m: String = Hex.MOUNTAINS[_rng.randi() % Hex.MOUNTAINS.size()]
					Hex.put(self, m, Hex.to_world(q, r) + Vector3(0, -0.5, -9.0), _rng.randf() * TAU, 2.6 + _rng.randf() * 1.6)
	for code in BUILDING_POS:
		var bp: Vector3 = BUILDING_POS[code]
		var b := Hex.put(self, BUILDING_MODELS[code], bp, atan2(-bp.x, -bp.z) + PI, BUILDING_SCALE)
		b.name = code
	# castle keep behind the plaza, towers and banners
	Hex.put(self, "buildings/blue/building_castle_blue.gltf", Vector3(0, 0, -9.0), 0.0, 1.8)
	Hex.put(self, "buildings/blue/building_tower_A_blue.gltf", Vector3(-8.5, 0, -5.0), 0.0, 1.5)
	Hex.put(self, "buildings/blue/building_tower_A_blue.gltf", Vector3(8.5, 0, -6.0), 0.0, 1.5)
	Hex.put(self, "buildings/blue/building_well_blue.gltf", Hex.to_world(2, 1), 0.4, 1.3)
	for p in [Vector3(-1.5, 0, 3.0), Vector3(1.5, 0, 3.0), Vector3(-1.2, 0, -4.0), Vector3(1.2, 0, -4.0)]:
		Hex.put(self, "decoration/props/flag_blue.gltf", p, 0.0, 1.6)
	Hex.put(self, "decoration/props/weaponrack.gltf", Vector3(-3.2, 0, 2.6), 0.6, 1.4)
	Hex.put(self, "decoration/props/barrel.gltf", Vector3(3.3, 0, 3.0), 0.0, 1.3)
	Hex.put(self, "decoration/props/crate_A_big.gltf", Vector3(3.9, 0, 2.3), 0.3, 1.3)
	Hex.put(self, "decoration/props/tent.gltf", Hex.to_world(-5, 4), 0.8, 1.4)
	for i in 6:
		var c := Hex.put(self, "decoration/nature/cloud_big.gltf" if i % 2 == 0 else "decoration/nature/cloud_small.gltf",
			Vector3(_rng.randf_range(-22, 22), _rng.randf_range(12, 16), _rng.randf_range(-40, -26)), 0.0, 3.5)
		c.set_meta("drift", _rng.randf_range(0.2, 0.5))
		c.add_to_group("clouds")
	# hero pedestal: a raised grass hex with a golden ring
	var ring := MeshInstance3D.new()
	var torus := TorusMesh.new()
	torus.inner_radius = 0.95
	torus.outer_radius = 1.08
	ring.mesh = torus
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(1.0, 0.85, 0.45)
	mat.emission_enabled = true
	mat.emission = Color(1.0, 0.75, 0.3)
	mat.emission_energy_multiplier = 1.6
	ring.material_override = mat
	ring.position = Vector3(0, 0.03, 3.2)
	add_child(ring)


func _free(p: Vector3) -> bool:
	for code in BUILDING_POS:
		if p.distance_to(BUILDING_POS[code]) < 2.6:
			return false
	return p.distance_to(Vector3(0, 0, -9)) > 3.5


func show_hero(code: String) -> void:
	if code == hero_code and hero:
		return
	hero_code = code
	if hero:
		hero.queue_free()
	hero = Models.spawn(code)
	hero.position = Vector3(0, 0, 3.2)
	hero.rotation.y = 0.0
	add_child(hero)
	Models.play(hero, "cheer")
	Models.queue_idle(hero)


func building_node(code: String) -> Node3D:
	return get_node_or_null(code)


func _process(delta: float) -> void:
	_t += delta
	camera.position = _cam_base + Vector3(sin(_t * 0.15) * 0.5, sin(_t * 0.23) * 0.12, 0)
	camera.look_at(_look)
	for c in get_tree().get_nodes_in_group("clouds"):
		c.position.x += delta * float(c.get_meta("drift"))
		if c.position.x > 20:
			c.position.x = -20
