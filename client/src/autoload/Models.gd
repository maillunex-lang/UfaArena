extends Node
## Visual registry for heroes/enemies. Heroes are produced in 3D (KayKit CC0 rigs) and
## rendered to 2D portraits for cards/dialogues (GDD: «3D-производство, 2D-рендер»).

const ADV := "res://assets/third_party/kaykit_adventurers/"
const SKL := "res://assets/third_party/kaykit_skeletons/"

## base rigs
const RIGS := {
	"knight": ADV + "Knight.glb", "barbarian": ADV + "Barbarian.glb", "mage": ADV + "Mage.glb",
	"rogue": ADV + "Rogue.glb", "rogue_hooded": ADV + "Rogue_Hooded.glb",
	"skeleton_minion": SKL + "Skeleton_Minion.glb", "skeleton_warrior": SKL + "Skeleton_Warrior.glb",
	"skeleton_rogue": SKL + "Skeleton_Rogue.glb", "skeleton_mage": SKL + "Skeleton_Mage.glb",
}

## per-hero look: rig, attachments to keep visible, extra weapons, tint, scale, anim set
const LOOKS := {
	"azamat": {"rig": "knight", "keep": ["1H_Sword", "Badge_Shield", "Knight_Helmet", "Knight_Cape"], "anim": "1h"},
	"ilgiz": {"rig": "knight", "keep": ["2H_Sword", "Knight_Helmet"], "anim": "2h", "tint": Color(0.82, 0.9, 1.0)},
	"mirgali": {"rig": "barbarian", "keep": ["1H_Axe", "Barbarian_Round_Shield"], "anim": "1h",
		"tint": Color(0.92, 1.0, 0.9)},
	"burebai": {"rig": "barbarian", "keep": ["2H_Axe", "Barbarian_Hat", "Barbarian_Cape"], "anim": "2h"},
	"gulnaz": {"rig": "mage", "keep": ["1H_Wand", "Spellbook_open", "Mage_Cape"], "anim": "mage",
		"tint": Color(0.86, 1.0, 0.92)},
	"aigul": {"rig": "mage", "keep": ["2H_Staff", "Mage_Hat", "Mage_Cape"], "anim": "mage"},
	"humai": {"rig": "mage", "keep": ["2H_Staff", "Mage_Cape"], "anim": "mage", "tint": Color(1.25, 1.1, 0.75),
		"glow": Color(1.0, 0.85, 0.4), "scale": 1.05},
	"ramil": {"rig": "rogue", "keep": ["1H_Crossbow", "Knife_Offhand"], "anim": "bow1", "tint": Color(0.95, 0.95, 1.0)},
	"zulfiya": {"rig": "rogue", "keep": ["2H_Crossbow", "Rogue_Cape"], "anim": "bow2"},
	"tansulpan": {"rig": "rogue_hooded", "keep": ["Knife", "Knife_Offhand", "Rogue_Cape"], "anim": "dual"},
	"e_minion": {"rig": "skeleton_minion", "keep": [], "weapons": {"r": "Skeleton_Blade"}, "anim": "1h"},
	"e_warrior": {"rig": "skeleton_warrior", "keep": ["Skeleton_Warrior_Helmet"],
		"weapons": {"r": "Skeleton_Axe", "l": "Skeleton_Shield_Small_A"}, "anim": "1h"},
	"e_rogue": {"rig": "skeleton_rogue", "keep": ["Skeleton_Rogue_Hood", "Skeleton_Rogue_Cape"],
		"weapons": {"r": "Skeleton_Crossbow"}, "anim": "bow2"},
	"e_mage": {"rig": "skeleton_mage", "keep": ["Skeleton_Mage_Hat"], "weapons": {"r": "Skeleton_Staff"},
		"anim": "mage"},
	"e_boss_toratau": {"rig": "skeleton_warrior", "keep": ["Skeleton_Warrior_Helmet"],
		"weapons": {"r": "Skeleton_Axe", "l": "Skeleton_Shield_Large_A"}, "anim": "1h", "scale": 1.65,
		"tint": Color(1.0, 0.78, 0.78), "glow": Color(0.7, 0.2, 1.0)},
}

const ANIMS := {
	"1h": {"idle": "Idle", "attack": "1H_Melee_Attack_Slice_Diagonal", "skill": "1H_Melee_Attack_Chop"},
	"2h": {"idle": "2H_Melee_Idle", "attack": "2H_Melee_Attack_Slice", "skill": "2H_Melee_Attack_Spin"},
	"mage": {"idle": "Idle", "attack": "Spellcast_Shoot", "skill": "Spellcast_Long"},
	"bow1": {"idle": "Idle", "attack": "1H_Ranged_Shoot", "skill": "1H_Ranged_Shooting"},
	"bow2": {"idle": "Idle", "attack": "2H_Ranged_Shoot", "skill": "2H_Ranged_Shooting"},
	"dual": {"idle": "Idle", "attack": "Dualwield_Melee_Attack_Slice", "skill": "Dualwield_Melee_Attack_Chop"},
}
const COMMON_ANIMS := {"hit": "Hit_A", "death": "Death_A", "cheer": "Cheer", "walk": "Walking_A", "run": "Running_A",
	"block": "Block", "spawn": "Spawn_Ground"}
const LOOPING := ["Idle", "2H_Melee_Idle", "Walking_A", "Running_A", "Spellcasting", "Idle_Combat", "Blocking"]

var _portraits := {}
var _scene_cache := {}


func _scene(path: String) -> PackedScene:
	if not _scene_cache.has(path):
		_scene_cache[path] = load(path)
	return _scene_cache[path]


## Built-in look, overridden/extended by content packages (`looks/<code>.json`):
## {"rig": "knight" | "content:models/x.glb", "keep": [...], "weapons": {...}, "anim": "1h",
##  "tint": [r,g,b], "glow": [r,g,b], "scale": 1.0}. New heroes can ship purely as content.
func look(code: String) -> Dictionary:
	var lk: Dictionary = LOOKS.get(code, {}).duplicate()
	var ov: Variant = Content.json("looks/%s.json" % code)
	if ov is Dictionary:
		for k in ov:
			lk[k] = ov[k]
	if lk.is_empty():
		lk = LOOKS["azamat"].duplicate()
	for ck in ["tint", "glow"]:
		if lk.get(ck) is Array and (lk[ck] as Array).size() >= 3:
			lk[ck] = Color(float(lk[ck][0]), float(lk[ck][1]), float(lk[ck][2]))
	if not ANIMS.has(String(lk.get("anim", "1h"))):
		lk["anim"] = "1h"
	return lk


func clear_cache() -> void:
	_portraits.clear()


## Returns a Node3D "actor" with meta: anim_player, anim_set.
func spawn(code: String) -> Node3D:
	var lk := look(code)
	var root := Node3D.new()
	root.name = code
	var rig: String = lk.get("rig", "knight")
	var inst: Node3D = null
	if rig.begins_with("content:"):
		inst = Content.model(rig.substr(8))
	elif RIGS.has(rig):
		inst = _scene(RIGS[rig]).instantiate()
	if inst == null:
		inst = _scene(RIGS["knight"]).instantiate()
	root.add_child(inst)
	var keep: Array = lk.get("keep", [])
	for att in inst.find_children("*", "BoneAttachment3D", true, false):
		for m in att.get_children():
			if m is MeshInstance3D:
				m.visible = m.name in keep
	var skel: Skeleton3D = inst.find_child("Skeleton3D", true, false)
	var weapons: Dictionary = lk.get("weapons", {}) if skel else {}
	for side in weapons:
		var ba := BoneAttachment3D.new()
		ba.bone_name = "handslot." + side
		skel.add_child(ba)
		var w: Node3D = _scene(SKL + "weapons/" + weapons[side] + ".gltf").instantiate()
		ba.add_child(w)
	if lk.has("tint"):
		_tint(inst, lk.tint, lk.get("glow", Color.BLACK))
	var s: float = lk.get("scale", 1.0)
	root.scale = Vector3.ONE * s
	var ap: AnimationPlayer = inst.find_child("AnimationPlayer", true, false)
	if ap:
		for a in LOOPING:
			if ap.has_animation(a):
				ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
	root.set_meta("ap", ap)
	root.set_meta("anim_set", ANIMS[lk.anim])
	play(root, "idle")
	if lk.has("glow"):
		var l := OmniLight3D.new()
		l.light_color = lk.glow
		l.light_energy = 1.4
		l.omni_range = 3.0
		l.position = Vector3(0, 1.6, 0.6)
		root.add_child(l)
	return root


func _tint(n: Node, tint: Color, glow: Color) -> void:
	for m in n.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		for i in mi.get_surface_override_material_count():
			var base: Material = mi.get_active_material(i)
			if base is StandardMaterial3D:
				var mat := (base as StandardMaterial3D).duplicate() as StandardMaterial3D
				mat.albedo_color = mat.albedo_color * tint
				if glow != Color.BLACK:
					mat.emission_enabled = true
					mat.emission = glow
					mat.emission_energy_multiplier = 0.12
				mi.set_surface_override_material(i, mat)


func anim_name(actor: Node3D, key: String) -> String:
	var set_: Dictionary = actor.get_meta("anim_set", {})
	return set_.get(key, COMMON_ANIMS.get(key, "Idle"))


## Plays a logical animation (idle/attack/skill/hit/death/cheer/walk/run). Returns its length.
func play(actor: Node3D, key: String, blend := 0.15, speed := 1.0) -> float:
	var ap: AnimationPlayer = actor.get_meta("ap", null)
	if ap == null:
		return 0.0
	var a := anim_name(actor, key)
	if not ap.has_animation(a):
		a = "Idle"
	ap.play(a, blend, speed)
	return ap.get_animation(a).length / max(speed, 0.01)


func queue_idle(actor: Node3D) -> void:
	var ap: AnimationPlayer = actor.get_meta("ap", null)
	if ap:
		ap.queue(anim_name(actor, "idle"))


# ------------------------------------------------------------------ portraits (3D -> 2D)
func portrait(code: String, size := 256) -> Texture2D:
	var key := "%s@%d" % [code, size]
	if _portraits.has(key):
		return _portraits[key]
	var vp := SubViewport.new()
	vp.size = Vector2i(size, size)
	vp.transparent_bg = true
	vp.own_world_3d = true
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	vp.msaa_3d = Viewport.MSAA_4X
	add_child(vp)
	var actor := spawn(code)
	vp.add_child(actor)
	var ap: AnimationPlayer = actor.get_meta("ap", null)
	if ap:
		ap.play(anim_name(actor, "idle"))
		ap.seek(0.4, true)
		ap.pause()
	var cam := Camera3D.new()
	var s: float = look(code).get("scale", 1.0)
	cam.fov = 30
	cam.position = Vector3(0.55, 2.15, 3.2) * s
	vp.add_child(cam)
	cam.look_at(Vector3(0, 1.75 * s, 0))
	var key_l := DirectionalLight3D.new()
	key_l.rotation_degrees = Vector3(-35, 30, 0)
	key_l.light_energy = 1.3
	vp.add_child(key_l)
	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-10, 200, 0)
	rim.light_energy = 0.8
	rim.light_color = Color(0.7, 0.85, 1.0)
	vp.add_child(rim)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.55, 0.6, 0.7)
	env.environment.ambient_light_energy = 0.9
	env.environment.background_mode = Environment.BG_CLEAR_COLOR
	vp.add_child(env)
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var img := vp.get_texture().get_image()
	var tex := ImageTexture.create_from_image(img)
	_portraits[key] = tex
	vp.queue_free()
	return tex


func cached_portrait(code: String, size := 256) -> Texture2D:
	return _portraits.get("%s@%d" % [code, size], null)
