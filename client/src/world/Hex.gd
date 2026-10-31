class_name Hex
extends RefCounted
## KayKit hexagon pack helpers (pointy-top tiles, 2 m flat-to-flat, top face at y=0).

const ROOT := "res://assets/third_party/kaykit_hexagon/"
const SQ3 := 1.7320508

static var _cache := {}


static func scene(rel: String) -> PackedScene:
	if not _cache.has(rel):
		_cache[rel] = load(ROOT + rel)
	return _cache[rel]


static func to_world(q: int, r: int) -> Vector3:
	return Vector3(2.0 * (q + r * 0.5), 0.0, SQ3 * r)


static func dist(q: int, r: int) -> int:
	return int((abs(q) + abs(r) + abs(q + r)) / 2)


static func put(parent: Node3D, rel: String, pos: Vector3, rot_y := 0.0, scl := 1.0) -> Node3D:
	var n: Node3D = scene(rel).instantiate()
	n.position = pos
	n.rotation.y = rot_y
	n.scale = Vector3.ONE * scl
	parent.add_child(n)
	return n


static var _tile_mats := {}


## Tiles share one atlas; tint grass towards a deeper meadow green (cached, so batching is kept).
static func tile(parent: Node3D, kind: String, q: int, r: int, rot_steps := 0, tint := Color(0.7, 0.9, 0.62)) -> Node3D:
	var n := put(parent, "tiles/" + kind + ".gltf", to_world(q, r), rot_steps * PI / 3.0)
	if kind.contains("grass") or kind.contains("road"):
		for m in n.find_children("*", "MeshInstance3D", true, false):
			var mi := m as MeshInstance3D
			var key := str(tint)
			if not _tile_mats.has(key):
				var mat := (mi.get_active_material(0) as StandardMaterial3D).duplicate() as StandardMaterial3D
				mat.albedo_color = tint
				_tile_mats[key] = mat
			mi.material_override = _tile_mats[key]
	return n


static func environment(parent: Node3D, mood := "day") -> WorldEnvironment:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	var sky := Sky.new()
	var mat := PanoramaSkyMaterial.new()
	mat.panorama = load("res://assets/third_party/polyhaven/kloofendal_48d_partly_cloudy_puresky_1k.hdr")
	sky.sky_material = mat
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 0.7
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.0
	env.glow_enabled = true
	env.glow_intensity = 0.55
	env.glow_bloom = 0.08
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.0
	env.adjustment_contrast = 1.06
	env.fog_enabled = true
	env.fog_light_color = Color(0.72, 0.8, 0.92)
	env.fog_density = 0.006
	env.fog_sky_affect = 0.0
	match mood:
		"dusk":
			env.background_energy_multiplier = 0.55
			env.ambient_light_energy = 0.55
			env.adjustment_saturation = 1.0
			env.fog_light_color = Color(0.45, 0.35, 0.6)
			env.fog_density = 0.012
		"dungeon":
			env.background_energy_multiplier = 0.25
			env.ambient_light_energy = 0.35
			env.fog_light_color = Color(0.25, 0.18, 0.4)
			env.fog_density = 0.02
	we.environment = env
	parent.add_child(we)
	return we


static func sun(parent: Node3D, energy := 0.95, color := Color(1.0, 0.96, 0.9), rot := Vector3(-48, -35, 0)) -> DirectionalLight3D:
	var l := DirectionalLight3D.new()
	l.rotation_degrees = rot
	l.light_energy = energy
	l.light_color = color
	l.shadow_enabled = Gfx.setting("shadows")
	l.shadow_bias = 0.04
	l.directional_shadow_max_distance = 60.0
	parent.add_child(l)
	return l


const NATURE := ["decoration/nature/trees_A_large.gltf", "decoration/nature/trees_A_medium.gltf",
	"decoration/nature/trees_B_large.gltf", "decoration/nature/trees_B_medium.gltf",
	"decoration/nature/tree_single_A.gltf", "decoration/nature/tree_single_B.gltf",
	"decoration/nature/hills_A_trees.gltf", "decoration/nature/rock_single_A.gltf"]
const MOUNTAINS := ["decoration/nature/mountain_A_grass_trees.gltf", "decoration/nature/mountain_B_grass_trees.gltf",
	"decoration/nature/mountain_C_grass_trees.gltf", "decoration/nature/mountain_A_grass.gltf",
	"decoration/nature/mountain_B_grass.gltf"]
