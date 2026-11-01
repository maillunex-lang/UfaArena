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
	"dragon": "res://assets/third_party/quaternius_monsters/Dragon.fbx",
	"tree": "res://assets/third_party/kaykit_hexagon/decoration/nature/tree_single_B.gltf",
}
const DRAGON_ANIMS := {"idle": "DragonArmature|Dragon_Flying", "run": "DragonArmature|Dragon_Flying",
	"attack": "DragonArmature|Dragon_Attack", "skill": "DragonArmature|Dragon_Attack2",
	"skill2": "DragonArmature|Dragon_Attack2", "ultimate": "DragonArmature|Dragon_Attack2",
	"hit": "DragonArmature|Dragon_Hit", "death": "DragonArmature|Dragon_Death", "cheer": "DragonArmature|Dragon_Flying"}

## HERO FORGE roster (temporary looks built from CC0 rigs; each hero has its own weapon set,
## faction palette and 8-animation set: idle, run, attack, skill, skill2, ultimate, hit, death, cheer).
## Replace with Meshy models via a content package: looks/<code>.json {"rig": "content:models/<code>.glb"}.
const FORGE_LOOKS := {
	"arslan_kara": {"rig": "knight", "keep": ["1H_Sword", "Knight_Cape"], "tint": Color(0.62, 0.7, 0.74),
		"glow": Color(0.2, 0.75, 0.7), "anim": "1h", "scale": 1.04, "anims": {"attack": "1H_Melee_Attack_Chop",
		"skill": "Block", "skill2": "1H_Melee_Attack_Slice_Horizontal", "ultimate": "1H_Melee_Attack_Stab",
		"hit": "Block_Hit", "death": "Death_B", "cheer": "Interact"}},
	"bai_tash": {"rig": "barbarian", "keep": ["Barbarian_Round_Shield"], "tint": Color(0.42, 0.45, 0.5),
		"glow": Color(0.25, 0.85, 0.8), "anim": "1h", "scale": 1.45, "anims": {"idle": "Idle",
		"attack": "Unarmed_Melee_Attack_Punch_A", "skill": "Block", "skill2": "2H_Melee_Attack_Slice",
		"ultimate": "Spellcast_Long", "hit": "Hit_B", "death": "Death_B", "cheer": "Cheer"}},
	"safariy": {"rig": "mage", "keep": ["2H_Staff", "Mage_Cape"], "tint": Color(0.62, 0.7, 1.0), "anim": "mage",
		"anims": {"attack": "Spellcast_Shoot", "skill": "Spellcast_Raise", "skill2": "Spellcast_Long",
		"ultimate": "Spellcasting", "hit": "Block", "death": "Death_A", "cheer": "Interact"}},
	"ai_tulgan": {"rig": "mage", "keep": ["2H_Staff"], "tint": Color(1.12, 1.08, 0.98), "glow": Color(0.4, 0.9, 0.85),
		"anim": "mage", "anims": {"attack": "Spellcast_Shoot", "skill": "Spellcast_Raise", "skill2": "Spellcasting",
		"ultimate": "Spellcast_Long", "hit": "Hit_A", "death": "Death_B", "cheer": "Cheer"}},
	"yurek": {"rig": "rogue", "keep": ["1H_Crossbow", "Rogue_Cape"], "tint": Color(0.82, 0.98, 0.74), "anim": "bow1",
		"anims": {"attack": "1H_Ranged_Shoot", "skill": "1H_Ranged_Aiming", "skill2": "Throw",
		"ultimate": "1H_Ranged_Shooting", "hit": "Dodge_Backward", "death": "Death_A", "cheer": "Cheer"}},
	"sumbel": {"rig": "mage", "keep": ["2H_Staff", "Mage_Cape"], "tint": Color(0.62, 0.92, 0.58),
		"glow": Color(0.5, 0.95, 0.4), "anim": "mage", "anims": {"attack": "Spellcast_Shoot", "skill": "PickUp",
		"skill2": "Spellcast_Long", "ultimate": "Spellcast_Raise", "hit": "Block", "death": "Death_B", "cheer": "Use_Item"}},
	"ak_bure": {"rig": "rogue_hooded", "keep": ["Knife", "Knife_Offhand"], "tint": Color(1.3, 1.3, 1.36),
		"glow": Color(1.0, 0.75, 0.3), "anim": "dual", "scale": 1.08, "anims": {"attack": "Dualwield_Melee_Attack_Slice",
		"skill": "Dualwield_Melee_Attack_Chop", "skill2": "Spellcast_Raise", "ultimate": "Dualwield_Melee_Attack_Stab",
		"hit": "Dodge_Left", "death": "Death_A", "cheer": "Idle"}},
	"tan_chechek": {"rig": "mage", "keep": ["1H_Wand"], "tint": Color(1.28, 0.96, 1.06), "glow": Color(0.6, 1.0, 0.55),
		"anim": "mage", "anims": {"attack": "Spellcast_Shoot", "skill": "Use_Item", "skill2": "Spellcast_Raise",
		"ultimate": "Spellcasting", "hit": "Block", "death": "Death_B", "cheer": "Cheer"}},
	"vargat": {"rig": "knight", "keep": ["2H_Sword"], "tint": Color(0.68, 0.52, 0.56), "anim": "2h",
		"anims": {"idle": "2H_Melee_Idle", "attack": "2H_Melee_Attack_Chop", "skill": "2H_Melee_Attack_Slice",
		"skill2": "2H_Melee_Attack_Stab", "ultimate": "2H_Melee_Attack_Spin", "hit": "Block_Hit", "death": "Death_B",
		"cheer": "Cheer"}},
	"morai": {"rig": "mage", "keep": ["Mage_Cape"], "tint": Color(0.72, 0.64, 0.95), "glow": Color(0.65, 0.35, 1.0),
		"anim": "mage", "scale": 1.08, "anims": {"attack": "Spellcast_Shoot", "skill": "Spellcast_Raise",
		"skill2": "Spellcasting", "ultimate": "Spellcast_Long", "hit": "Hit_B", "death": "Death_A", "cheer": "Idle"}},
	"zarkhan": {"rig": "rogue", "keep": ["1H_Crossbow", "Rogue_Cape"], "tint": Color(0.74, 0.74, 0.8),
		"glow": Color(1.0, 0.65, 0.2), "anim": "bow1", "anims": {"attack": "1H_Ranged_Shoot", "skill": "1H_Ranged_Aiming",
		"skill2": "1H_Ranged_Reload", "ultimate": "1H_Ranged_Shooting", "hit": "Dodge_Right", "death": "Death_B",
		"cheer": "Interact"}},
	"ur_kaan": {"rig": "dragon", "keep": [], "tint": Color(0.5, 0.46, 0.52), "glow": Color(1.0, 0.6, 0.2),
		"anim": "1h", "scale": 0.62, "anims": DRAGON_ANIMS},
	"root_guardian": {"rig": "tree", "keep": [], "tint": Color(0.7, 1.0, 0.6), "glow": Color(0.45, 1.0, 0.4),
		"anim": "1h", "scale": 1.7, "static": true},
	"dragon_echo_small": {"rig": "dragon", "keep": [], "tint": Color(1.2, 0.8, 0.45), "glow": Color(1.0, 0.6, 0.15),
		"anim": "1h", "scale": 0.22, "alpha": 0.7, "anims": DRAGON_ANIMS},
	"dragon_echo": {"rig": "dragon", "keep": [], "tint": Color(1.25, 0.85, 0.5), "glow": Color(1.0, 0.65, 0.2),
		"anim": "1h", "scale": 0.4, "alpha": 0.72, "anims": DRAGON_ANIMS},
	# raid & world bosses (temporary looks on licensed rigs; final models can arrive via content packages)
	"rb_kurgan_colossus": {"rig": "skeleton_warrior", "keep": ["Skeleton_Warrior_Helmet"],
		"weapons": {"r": "Skeleton_Axe", "l": "Skeleton_Shield_Large_A"}, "anim": "1h", "scale": 2.1,
		"tint": Color(0.72, 0.68, 0.6), "glow": Color(1.0, 0.55, 0.2)},
	"rb_azhdaha": {"rig": "dragon", "keep": [], "tint": Color(0.55, 0.32, 0.3), "glow": Color(1.0, 0.35, 0.1),
		"anim": "1h", "scale": 1.05, "anims": DRAGON_ANIMS},
	"rb_ancient_root": {"rig": "tree", "keep": [], "tint": Color(0.55, 0.45, 0.6), "glow": Color(0.7, 0.3, 1.0),
		"anim": "1h", "scale": 2.6, "static": true},
	"rb_shulgan_shade": {"rig": "skeleton_mage", "keep": ["Skeleton_Mage_Hat"], "weapons": {"r": "Skeleton_Staff"},
		"anim": "mage", "scale": 2.0, "tint": Color(0.45, 0.35, 0.7), "glow": Color(0.6, 0.2, 1.0)},
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
	var lk: Dictionary = (LOOKS.get(code, FORGE_LOOKS.get(code, {})) as Dictionary).duplicate()
	var ov: Variant = Content.json("looks/%s.json" % code)
	if ov is Dictionary:
		for k in ov:
			lk[k] = ov[k]
	if lk.is_empty():
		lk = LOOKS["azamat"].duplicate()
	var skins: Variant = Game.cosmetics.get("hero_skins", {})
	if skins is Dictionary and skins.has(code) and skins[code] is Dictionary:
		var sd: Dictionary = skins[code].get("data", {})
		for k in ["tint", "glow"]:
			if sd.has(k):
				lk[k] = sd[k]
	for ck in ["tint", "glow"]:
		if lk.get(ck) is Array and (lk[ck] as Array).size() >= 3:
			lk[ck] = Color(float(lk[ck][0]), float(lk[ck][1]), float(lk[ck][2]))
	if not ANIMS.has(String(lk.get("anim", "1h"))):
		lk["anim"] = "1h"
	return lk


## Also used by Settings → «Очистить кэш»; returns how many portraits were dropped.
func clear_cache() -> int:
	var n := _portraits.size()
	_portraits.clear()
	return n


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
		_tint(inst, lk.tint, lk.get("glow", Color.BLACK), float(lk.get("alpha", 1.0)))
	var s: float = lk.get("scale", 1.0)
	root.scale = Vector3.ONE * s
	var ap: AnimationPlayer = inst.find_child("AnimationPlayer", true, false)
	if ap:
		for a in LOOPING:
			if ap.has_animation(a):
				ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
	root.set_meta("ap", ap)
	var aset: Dictionary = (ANIMS[lk.anim] as Dictionary).duplicate()
	var over: Variant = lk.get("anims", {})
	if over is Dictionary:
		for k in over:
			aset[k] = over[k]
	if ap:
		for k in ["idle", "run"]:
			var nm: String = aset.get(k, COMMON_ANIMS.get(k, ""))
			if ap.has_animation(nm):
				ap.get_animation(nm).loop_mode = Animation.LOOP_LINEAR
	root.set_meta("anim_set", aset)
	if lk.get("static", false):
		root.set_meta("static", true)
	play(root, "idle")
	if lk.has("glow"):
		var l := OmniLight3D.new()
		l.light_color = lk.glow
		l.light_energy = 1.4
		l.omni_range = 3.0
		l.position = Vector3(0, 1.6, 0.6)
		root.add_child(l)
	return root


func _tint(n: Node, tint: Color, glow: Color, alpha := 1.0) -> void:
	for m in n.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		for i in mi.get_surface_override_material_count():
			var base: Material = mi.get_active_material(i)
			if base is StandardMaterial3D:
				var mat := (base as StandardMaterial3D).duplicate() as StandardMaterial3D
				mat.albedo_color = mat.albedo_color * tint
				if alpha < 1.0:
					mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
					mat.albedo_color.a = alpha
				if glow != Color.BLACK:
					mat.emission_enabled = true
					mat.emission = glow
					mat.emission_energy_multiplier = 0.12
				mi.set_surface_override_material(i, mat)


func anim_name(actor: Node3D, key: String) -> String:
	var set_: Dictionary = actor.get_meta("anim_set", {})
	if set_.has(key):
		return set_[key]
	if key in ["skill2", "ultimate"]:
		return set_.get("skill", "Idle")
	if key == "victory":
		return set_.get("cheer", COMMON_ANIMS["cheer"])
	return COMMON_ANIMS.get(key, "Idle")


## Plays a logical animation (idle/attack/skill/hit/death/cheer/walk/run). Returns its length.
func play(actor: Node3D, key: String, blend := 0.15, speed := 1.0) -> float:
	var ap: AnimationPlayer = actor.get_meta("ap", null)
	if ap == null:
		return 0.0
	var a := anim_name(actor, key)
	if not ap.has_animation(a):
		a = anim_name(actor, "idle") if ap.has_animation(anim_name(actor, "idle")) else "Idle"
	if not ap.has_animation(a):
		return 0.0
	ap.play(a, blend, speed)
	return ap.get_animation(a).length / max(speed, 0.01)


func queue_idle(actor: Node3D) -> void:
	var ap: AnimationPlayer = actor.get_meta("ap", null)
	if ap:
		ap.queue(anim_name(actor, "idle"))


# ------------------------------------------------------------------ portraits (3D -> 2D)
func portrait(code: String, size := 256) -> Texture2D:
	var art := UI.art("heroes/%s.png" % code)  # painted portrait from the admin panel wins over the 3D render
	if art:
		return art
	var key := "%s@%d" % [code, size]
	if _portraits.has(key):
		return _portraits[key]
	var vp := SubViewport.new()
	vp.size = Vector2i(size, size)
	vp.transparent_bg = true
	vp.own_world_3d = true
	# render only after camera, lights and the posed actor are all in place (a frame hitch between add_child and
	# setup used to capture an empty/garbage frame with UPDATE_ONCE)
	vp.render_target_update_mode = SubViewport.UPDATE_DISABLED
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
	await get_tree().process_frame  # animation pose and transforms applied
	if not is_instance_valid(vp):
		return null
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var img := vp.get_texture().get_image()
	var tex := ImageTexture.create_from_image(img)
	_portraits[key] = tex
	vp.queue_free()
	return tex


func cached_portrait(code: String, size := 256) -> Texture2D:
	return _portraits.get("%s@%d" % [code, size], null)

