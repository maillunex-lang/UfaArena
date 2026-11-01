extends Node
## Battle: the server validates + simulates in real time; the client replays the time-stamped
## event log so that all heroes on both sides fight simultaneously (side view, AFK-style).
## Speed x1/x2/x4/x6 depends on the VIP level reported by the server.

const ArenaScript := preload("res://src/world/Arena.gd")
const DialogScript := preload("res://src/ui/StoryDialog.gd")
const MOVE_SPEED := 2.4 * 0.9  # sim speed scaled like the compressed battle line

var arena: Node3D
var node_code := ""
var node_info := {}
var battle_id := ""
var sim := {}
var claim_key := ""
var events: Array = []
var _ev_idx := 0
var _impacts: Array = []  # [{t, ev}]
var _clock := 0.0
var _playing := false
var _finished := false
var _speed := 1
var _speeds: Array = [1, 2]
var _ui: Control
var _timer_lbl: Label
var _speed_btn: Button
var _skill_banner: Label
var _cards := {}  # uid -> {hp: ProgressBar, en: ProgressBar, root: Control}


func _ready() -> void:
	node_code = Router.params.get("node_code", "1-1")
	node_info = Router.params.get("node", {})
	claim_key = Api.new_key()
	_speeds = []
	for s in Game.profile.get("battle_speeds", [1, 2]):  # JSON numbers arrive as floats
		_speeds.append(int(s))
	if _speeds.is_empty():
		_speeds = [1, 2]
	var saved := int(Config.settings.get("battle_speed", 1))
	_speed = saved if saved in _speeds else 1
	var layer := CanvasLayer.new()
	add_child(layer)
	_ui = Control.new()
	_ui.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui.theme = UI.theme()
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_ui)
	Sfx.music("battle")
	_start()


func _exit_tree() -> void:
	Engine.time_scale = 1.0


## External mode: arena / raid / tournament / event fights computed by the server elsewhere are only replayed.
func _external() -> bool:
	return Router.params.has("sim")


func _start() -> void:
	if _external():
		sim = Router.params.sim
		node_info = {"code": "", "name": String(Router.params.get("title", "Бой")), "story": [],
			"territory": String(Router.params.get("territory", "dungeons")), "is_boss": bool(Router.params.get("is_boss", false))}
	else:
		Router.busy(true)
		var r := await Api.post_json("/battles/validate", {"node_id": node_code})
		Router.busy(false)
		if not r.ok:
			Router.error(r)
			_back()
			return
		battle_id = r.data.battle_id
		sim = r.data.simulation
		node_info = r.data.node
	events = sim.events
	arena = ArenaScript.new()
	add_child(arena)
	arena.build(node_info.get("territory", "nature"), node_info.get("is_boss", false))
	for u in sim.units:
		arena.add_unit(u)
	_build_hud()
	var story: Array = node_info.get("story", [])
	if story.size() > 0 and not bool(Router.params.get("replay", false)):
		var dlg: Control = DialogScript.new()
		_ui.add_child(dlg)
		await dlg.play(story)
	Sfx.play("unsheathe")
	if node_info.get("is_boss", false):
		Sfx.play("boss")
		arena.shake(0.5)
	for uid in arena.units:
		var u: Dictionary = arena.units[uid]
		if u.side == 1 and String(u.data.code).begins_with("e_"):
			Models.play(u.node, "spawn")
			Models.queue_idle(u.node)
	await get_tree().create_timer(0.8).timeout
	Engine.time_scale = _speed
	_playing = true


# ------------------------------------------------------------------ HUD
func _build_hud() -> void:
	var top := HBoxContainer.new()
	top.set_anchors_preset(Control.PRESET_TOP_WIDE)
	top.offset_top = 70
	top.offset_left = 30
	top.offset_right = -30
	top.add_theme_constant_override("separation", 14)
	_ui.add_child(top)
	var title := UI.glass_panel()
	var tv := VBoxContainer.new()
	tv.add_child(UI.label("%s  %s" % [node_info.get("code", ""), node_info.get("name", "")], 32, UI.GOLD, true))
	var pw := [0, 0]
	for u in sim.units:
		pw[int(u.side)] += int(float(u.max_hp) * 0.25 + float(u.atk) * 2.2 + float(u.get("def", 0)) * 1.5)
	var pw_row := HBoxContainer.new()
	pw_row.add_theme_constant_override("separation", 14)
	pw_row.add_child(UI.label("⚔ %s" % Game.fmt(pw[0]), 30, Color("#9fe0ff"), true))
	pw_row.add_child(UI.label("VS", 30, UI.GOLD, true))
	pw_row.add_child(UI.label("%s ⚔" % Game.fmt(pw[1]), 30, Color("#ff9f9f"), true))
	pw_row.add_child(UI.expand())
	var syn: Dictionary = sim.get("synergy", {}).get("0", {})
	if float(syn.get("bonus", 0)) > 0:
		var sy := UI.label(" %s +%d%%" % [Game.faction_name(String(syn.faction)), int(float(syn.bonus) * 100)], 22,
			Game.faction_color(String(syn.faction)), true)
		sy.tooltip_text = "Бонус наследия: атака и здоровье"
		pw_row.add_child(sy)
	_timer_lbl = UI.label("1:30", 28, UI.MUTED)
	pw_row.add_child(_timer_lbl)
	tv.add_child(pw_row)
	title.add_child(tv)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(title)
	_speed_btn = UI.button("x%d" % _speed, "glass", 130)
	_speed_btn.pressed.connect(_toggle_speed)
	top.add_child(_speed_btn)
	var skip := UI.button("Пропуск", "glass", 190)
	skip.pressed.connect(_skip)
	top.add_child(skip)
	_skill_banner = UI.title("", 60)
	_skill_banner.set_anchors_preset(Control.PRESET_CENTER)
	_skill_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_skill_banner.custom_minimum_size = Vector2(1000, 100)
	_skill_banner.position = Vector2(-500, -640)
	_skill_banner.modulate.a = 0
	_ui.add_child(_skill_banner)
	# bottom: the player's heroes with HP / energy (AFK-style cards)
	var row := HBoxContainer.new()
	row.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	row.offset_top = -360
	row.offset_bottom = -90
	row.offset_left = 24
	row.offset_right = -24
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 12)
	_ui.add_child(row)
	for u in sim.units:
		if int(u.side) != 0:
			continue
		var card := PanelContainer.new()
		var rc: Color = Game.RARITY_COLORS.get(int(u.rarity), Color.WHITE)
		card.add_theme_stylebox_override("panel", UI._flat(Color(0.05, 0.07, 0.14, 0.7), rc, 20, 3))
		card.custom_minimum_size = Vector2(186, 250)
		var v := VBoxContainer.new()
		v.add_theme_constant_override("separation", 4)
		var tex := TextureRect.new()
		tex.custom_minimum_size = Vector2(170, 170)
		tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		v.add_child(tex)
		_load_portrait(tex, String(u.code))
		var hp := UI.bar(int(u.hp), int(u.max_hp), Color("#5fd36f"), 16)
		var en := UI.bar(0, 100, Color("#ffcf4a"), 10)
		v.add_child(hp)
		v.add_child(en)
		var emb := GameIcon.new()
		emb.kind = String(u.get("faction", ""))
		emb.size = Vector2(40, 40)
		emb.position = Vector2(136, 6)
		emb.mouse_filter = Control.MOUSE_FILTER_IGNORE
		tex.add_child(emb)
		var nm := UI.label(String(u.name), 22, UI.TEXT, true)
		nm.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(nm)
		card.add_child(v)
		row.add_child(card)
		_cards[u.uid] = {"hp": hp, "en": en, "root": card}


func _load_portrait(tr: TextureRect, code: String) -> void:
	tr.texture = await Models.portrait(code, 192)


func _toggle_speed() -> void:
	var i := maxi(0, _speeds.find(_speed))
	var nxt: int = _speeds[(i + 1) % _speeds.size()]
	var table: Array = Game.profile.get("vip_speed_table", [])
	if nxt == _speeds[0] and table.size() > 0:
		for row in table:  # tell the player what the next VIP tier unlocks
			var s: Array = row.speeds
			if int(s[-1]) > int(_speeds[-1]):
				Router.toast("Ускорение x%d — с VIP %d" % [int(s[-1]), int(row.vip)])
				break
	_speed = nxt
	_speed_btn.text = "x%d" % _speed
	if _playing:
		Engine.time_scale = _speed
	Config.settings.battle_speed = _speed
	Config.save()


func _sync_card(uid: String) -> void:
	if not _cards.has(uid):
		return
	var u: Dictionary = arena.units[uid]
	_cards[uid].hp.value = u.hp
	_cards[uid].en.value = u.energy
	if not u.alive:
		_cards[uid].root.modulate = Color(0.45, 0.45, 0.5)


# ------------------------------------------------------------------ playback
func _process(delta: float) -> void:
	if not _playing or arena == null:
		return
	_clock += delta  # delta already includes Engine.time_scale
	var left := maxf(0.0, 90.0 - _clock)
	_timer_lbl.text = "%d:%02d" % [int(left) / 60, int(left) % 60]
	while _ev_idx < events.size() and float(events[_ev_idx].t) <= _clock:
		_dispatch(events[_ev_idx])
		_ev_idx += 1
	var i := 0
	while i < _impacts.size():
		if float(_impacts[i].t) <= _clock:
			var imp: Dictionary = _impacts[i]
			_impacts.remove_at(i)
			if arena.units.has(imp.ev.actor):
				_apply_targets(arena.units[imp.ev.actor], imp.ev.targets, imp.ev.type in ["skill", "ultimate", "mechanic"])
		else:
			i += 1
	_move_units(delta)
	if _ev_idx >= events.size() and _impacts.is_empty() and _clock > float(sim.get("duration", 0.0)) + 0.6:
		_playing = false
		_finish()


func _move_units(delta: float) -> void:
	for uid in arena.units:
		var u: Dictionary = arena.units[uid]
		if not u.alive:
			continue
		var node: Node3D = u.node
		var tp: Vector3 = u.target_pos
		var d := tp - node.position
		if d.length() > 0.04:
			node.position += d.normalized() * minf(d.length(), MOVE_SPEED * delta)
			if _clock >= float(u.busy_until):
				node.rotation.y = arena.yaw_to(node.position, tp)
				if not u.moving:
					Models.play(node, "run", 0.12)
					u.moving = true
		elif u.moving:
			u.moving = false
			if _clock >= float(u.busy_until):
				node.rotation.y = arena.rest_yaw(u.side)
				Models.play(node, "idle", 0.15)


func _dispatch(ev: Dictionary) -> void:
	if ev.type == "summon":
		_spawn_summon(ev)
		return
	if ev.type == "despawn":
		if arena.units.has(ev.actor) and arena.units[ev.actor].alive:
			_kill(ev.actor)
		return
	var actor: Dictionary = arena.units.get(ev.actor, {})
	if actor.is_empty() or not actor.alive:
		return
	if ev.type == "pos":
		actor.target_pos = arena.sim_pos(float(ev.x), float(ev.z))
		if ev.get("leap", false):  # assassin leap: instant reposition with a dust burst
			arena.burst(actor.node.position + Vector3(0, 0.3, 0), Color(0.9, 0.9, 1.0), 16, 2.0, true)
			actor.node.position = actor.target_pos
		return
	if ev.type == "mechanic":
		_mechanic(ev, actor)
		return
	# attack / skill / ultimate
	var is_skill: bool = ev.type in ["skill", "ultimate"]
	var is_ult: bool = ev.type == "ultimate"
	var cls := String(actor.data.get("class", ""))
	var ranged := float(actor.data.get("range", 1.8)) > 3.0
	actor.energy = int(ev.get("energy", 0))
	arena.set_bar(ev.actor)
	_sync_card(ev.actor)
	var tgt_uid := String(ev.get("target", ""))
	var ally_target := false
	var targets: Array = ev.targets
	if targets.size() > 0 and (targets[0].has("heal") or (targets[0].has("shield") and not targets[0].has("dmg"))):
		ally_target = true
		tgt_uid = String(targets[0].uid)
	if arena.units.has(tgt_uid):
		actor.node.rotation.y = arena.yaw_to(actor.node.position, arena.units[tgt_uid].node.position)
	var windup := float(ev.impact) - float(ev.t)
	var alen := Models.play(actor.node, String(ev.get("anim", "attack")) if is_skill else "attack", 0.08)
	Models.queue_idle(actor.node)
	actor.busy_until = _clock + minf(alen, 1.2)
	actor.moving = false
	if is_ult:
		_banner(String(ev.get("name", "")), actor.side == 0, true)
	elif is_skill:
		arena.float_text(arena.chest(ev.actor) + Vector3(0, 1.1, 0), String(ev.get("name", "")),
			Color(1.0, 0.92, 0.6) if actor.side == 0 else Color(1.0, 0.7, 0.7))
	if is_skill:
		Sfx.play("spell" if ranged or is_ult else "swing3")
		var fc := Game.faction_color(String(actor.data.get("faction", "")))
		arena.burst(arena.chest(ev.actor), fc.lightened(0.3) if is_ult else Color(1, 0.9, 0.5), 44 if is_ult else 26, 2.8, true)
		if is_ult:
			arena.shockwave(actor.node.position, fc, 2.6)
			arena.shake(0.35)
		elif targets.size() > 1:
			arena.shake(0.2)
	else:
		Sfx.play(("magic" if cls == "mage" else "swing") if ranged else ("swing" if randi() % 2 == 0 else "swing2"), 0.1)
	if ranged and not ally_target and arena.units.has(tgt_uid) and targets.size() == 1:
		var col := _color_for(actor)
		var from: Vector3 = arena.chest(ev.actor)
		var to: Vector3 = arena.chest(tgt_uid)
		get_tree().create_timer(windup * 0.35).timeout.connect(func():
			if is_instance_valid(arena):
				arena.projectile(from, to, col, 0.16, windup * 0.6))
	_impacts.append({"t": float(ev.impact), "ev": ev})


func _color_for(actor: Dictionary) -> Color:
	var fx: Variant = Game.cosmetics.get("ability_effects", {})
	if actor.side == 0 and fx is Dictionary and fx.has(String(actor.data.code)) and fx[actor.data.code] is Dictionary:
		var c: Array = fx[actor.data.code].get("data", {}).get("color", [])
		if c.size() >= 3:
			return Color(float(c[0]), float(c[1]), float(c[2]))
	match String(actor.data.get("class", "")):
		"mage":
			return Color(0.65, 0.45, 1.0) if actor.side == 0 else Color(0.6, 0.2, 0.9)
		"healer":
			return Color(0.5, 1.0, 0.6)
		"ranger":
			return Color(1.0, 0.85, 0.45)
	return Color(1.0, 0.6, 0.3)


func _apply_targets(actor: Dictionary, targets: Array, is_skill: bool) -> void:
	if targets.size() > 1 and targets[0].has("dmg"):
		var center := Vector3.ZERO
		var n := 0
		for t in targets:
			if arena.units.has(t.uid):
				center += arena.units[t.uid].node.position
				n += 1
		if n > 0:
			arena.shockwave(center / n, _color_for(actor), 3.5)
	for t in targets:
		if not arena.units.has(t.uid):
			continue
		var u: Dictionary = arena.units[t.uid]
		var pos: Vector3 = arena.chest(t.uid)
		if t.get("miss", false):
			arena.float_text(pos, "Промах", Color(0.75, 0.8, 0.9))
			continue
		for rd in t.get("redirect", []):  # Bai-Tash / root guardian / Arslan take part of the hit
			if arena.units.has(rd.uid):
				var ru: Dictionary = arena.units[rd.uid]
				ru.hp = int(rd.hp)
				arena.float_text(arena.chest(rd.uid), "%d" % int(rd.dmg), Color(0.6, 0.9, 1.0))
				arena.set_bar(rd.uid)
				_sync_card(rd.uid)
				if ru.hp <= 0 and ru.alive:
					_kill(rd.uid)
		for tag in t.get("applied", []):
			_status_text(pos, String(tag))
		if t.get("removed", []).size() > 0:
			arena.float_text(pos + Vector3(0, 0.4, 0), "Снято: %d" % t.removed.size(), Color(1.0, 0.85, 0.6))
		if t.get("delayed", false):
			arena.float_text(pos + Vector3(0, 0.5, 0), "Задержка", Color(0.75, 0.6, 1.0))
		if t.has("dmg"):
			var crit: bool = t.get("crit", false)
			var txt := str(int(t.dmg))
			arena.float_text(pos, txt + ("!" if crit else ""), Color(1, 0.85, 0.3) if crit else Color(1, 1, 1), crit or is_skill)
			arena.burst(pos, Color(1, 0.55, 0.25) if actor.side == 0 else Color(0.75, 0.35, 1.0), 14 if not crit else 26, 4.0)
			u.hp = int(t.hp)
			u.shield = max(0, int(u.shield) - int(t.get("absorbed", 0)))
			u.energy = min(100, int(u.energy) + 6)
			if u.shield <= 0:
				arena.shield_bubble(t.uid, false)
			if t.get("stunned", false):
				arena.stun_mark(t.uid, true)
				var sid: String = t.uid
				get_tree().create_timer(2.2).timeout.connect(func():
					if is_instance_valid(arena) and arena.units.has(sid):
						arena.stun_mark(sid, false))
			if t.get("killed", false) and u.alive:
				_kill(t.uid)
			elif u.alive and _clock >= float(u.busy_until) and not u.moving:
				Models.play(u.node, "hit", 0.05)
				Models.queue_idle(u.node)
		if t.has("heal"):
			u.hp = int(t.hp)
			arena.float_text(pos, "+%d" % int(t.heal), Color(0.5, 1.0, 0.55), is_skill)
			arena.burst(u.node.position + Vector3(0, 0.2, 0), Color(0.45, 1.0, 0.55), 22, 2.2, true)
			Sfx.play("heal")
		if t.has("shield"):
			u.shield = int(t.shield)
			arena.shield_bubble(t.uid, true)
			if not t.has("dmg"):
				arena.float_text(pos, "Щит", Color(0.6, 0.85, 1.0))
		arena.set_bar(t.uid)
		_sync_card(t.uid)


func _status_text(pos: Vector3, tag: String) -> void:
	if tag.begins_with("mark:"):
		var parts := tag.split(":")
		var names := {"trail": "След", "wind": "Знак ветра", "prey": "Добыча", "rift": "Разлом", "ash": "Пепел"}
		arena.float_text(pos + Vector3(0, 0.7, 0), "%s ×%s" % [names.get(parts[1], parts[1]), parts[2] if parts.size() > 2 else "1"],
			Color(1.0, 0.75, 0.35))
		return
	var txt: String = Game.STATUS_NAMES.get(tag, "")
	if txt != "":
		var good := tag.ends_with("+") or tag == "guard"
		arena.float_text(pos + Vector3(0, 0.7, 0), txt, Color(0.55, 1.0, 0.7) if good else Color(1.0, 0.6, 0.55))


func _mechanic(ev: Dictionary, actor: Dictionary) -> void:
	var fc := Game.faction_color(String(actor.data.get("faction", "")))
	arena.burst(arena.chest(ev.actor), fc.lightened(0.4), 30, 2.4, true)
	arena.float_text(arena.chest(ev.actor) + Vector3(0, 1.0, 0), String(ev.get("name", "")), fc.lightened(0.5), true)
	_impacts.append({"t": float(ev.get("impact", ev.t)), "ev": ev})


func _spawn_summon(ev: Dictionary) -> void:
	var data: Dictionary = ev.unit
	if arena.units.has(data.uid):
		return
	arena.add_unit(data)
	var u: Dictionary = arena.units[data.uid]
	u.node.scale *= 0.2
	u.node.create_tween().tween_property(u.node, "scale", u.node.scale * 5.0, 0.35).set_trans(Tween.TRANS_BACK)
	arena.burst(u.node.position + Vector3(0, 0.4, 0), Game.faction_color(String(data.get("faction", ""))), 30, 2.6, true)
	arena.float_text(arena.chest(data.uid) + Vector3(0, 0.6, 0), String(data.get("name", "")), Color(1.0, 0.9, 0.6), true)
	Sfx.play("magic")


func _kill(uid: String) -> void:
	var u: Dictionary = arena.units[uid]
	u.alive = false
	Models.play(u.node, "death", 0.1)
	Sfx.play("enemy_die" if u.side == 1 else "back")
	arena.burst(arena.chest(uid), Color(0.7, 0.4, 1.0) if u.side == 1 else Color(0.8, 0.9, 1.0), 26, 2.0, true)
	for c in u.node.get_children():
		if c is MeshInstance3D and c.name != "Shield":
			c.visible = false  # hide bar + ring
	var tw: Tween = u.node.create_tween()
	tw.tween_interval(1.3)
	tw.tween_property(u.node, "position:y", -0.7, 0.6)
	_sync_card(uid)


func _skip() -> void:
	if not _playing:
		return
	_playing = false
	_impacts.clear()
	for ev in events:
		if ev.type in ["pos", "summon", "despawn"]:
			continue
		for t in ev.get("targets", []):
			if not arena.units.has(t.uid):
				continue
			var u: Dictionary = arena.units[t.uid]
			u.hp = int(t.hp)
			u.shield = int(t.get("shield", 0)) if t.has("shield") else 0
			if t.get("killed", false) and u.alive:
				_kill(t.uid)
			arena.set_bar(t.uid)
			_sync_card(t.uid)
	_finish()


func _banner(text: String, ally: bool, big := false) -> void:
	if text == "":
		return
	_skill_banner.text = text
	_skill_banner.add_theme_color_override("font_color", UI.GOLD if ally else Color("#ff8f8f"))
	_skill_banner.scale = Vector2(0.7, 0.7)
	_skill_banner.pivot_offset = _skill_banner.size / 2
	var tw := _skill_banner.create_tween().set_parallel(true)
	tw.tween_property(_skill_banner, "modulate:a", 1.0, 0.12)
	tw.tween_property(_skill_banner, "scale", Vector2.ONE, 0.18).set_trans(Tween.TRANS_BACK)
	tw.chain().tween_interval(0.6)
	tw.chain().tween_property(_skill_banner, "modulate:a", 0.0, 0.25)


# ------------------------------------------------------------------ result
func _finish() -> void:
	if _finished:
		return
	_finished = true
	Engine.time_scale = 1.0
	var victory: bool = sim.result == "victory"
	for uid in arena.units:
		var u: Dictionary = arena.units[uid]
		if u.alive and ((u.side == 0) == victory):
			u.node.rotation.y = 0.0
			Models.play(u.node, "cheer")
	if victory:
		Sfx.music("victory", false)
	if _external():
		_external_result(victory)
		return
	await _claim(victory)


func _external_result(victory: bool) -> void:
	var p: Dictionary = Router.params
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.45)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui.add_child(dim)
	var panel := UI.solid_panel(Color("#ffe1a0") if victory else Color("#ff9b9b"))
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(900, 0)
	panel.position = Vector2(-450, -330)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 20)
	var head := String(p.get("result_title", "ПОБЕДА" if victory else "ПОРАЖЕНИЕ"))
	v.add_child(_result_head(victory, head, 76, not p.has("result_title")))
	for line in p.get("lines", []):
		var l := UI.label(String(line), 32, UI.TEXT)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(l)
	var rw: Dictionary = p.get("rewards", {})
	if not rw.is_empty():
		var row := UI.rewards_row(rw, 36)
		row.alignment = BoxContainer.ALIGNMENT_CENTER
		v.add_child(row)
	v.add_child(_stats_block({"rewards": rw, "progress": p.get("lines", [])}))
	var back := UI.button("Назад", "primary", 360)
	back.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	back.pressed.connect(func(): Router.goto(Router.MAIN, {"screen": String(p.get("back", "home")), "params": p.get("back_params", {})}))
	v.add_child(back)
	panel.add_child(v)
	_ui.add_child(panel)


func _claim(victory: bool) -> void:
	var r := await Api.post_json("/campaign/%s/complete" % node_code, {"battle_id": battle_id}, claim_key)
	if not r.ok:
		_result_panel(victory, {}, r)
		return
	Game.set_wallet(r.data.get("wallet", {}))
	Game.campaign["next_node"] = r.data.get("next_node")
	if r.data.has("level"):
		Game.profile["level"] = int(r.data.level)
		Game.profile["exp"] = int(r.data.exp)
		Game.profile_changed.emit()
	if victory and r.data.get("first_clear", false):
		var cleared: Array = Game.campaign.get("cleared", [])
		cleared.append(node_code)
		Game.campaign["cleared"] = cleared
	Game.refresh_afk()
	_result_panel(victory, r.data.get("rewards", {}), r)


func _result_panel(victory: bool, rewards: Dictionary, r: Dictionary) -> void:
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.45)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_ui.add_child(dim)
	var panel := UI.glass_panel(Color("#ffe1a0") if victory else Color("#ff9b9b"))
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(900, 0)
	panel.position = Vector2(-450, -520)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 22)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_child(_result_head(victory, "ПОБЕДА" if victory else "ПОРАЖЕНИЕ", 88, true))
	var dur := UI.label("Бой длился %.1f с" % float(sim.get("duration", 0.0)), 28, UI.MUTED)
	dur.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(dur)
	if victory:
		var rw := UI.rewards_row(rewards, 40)
		rw.alignment = BoxContainer.ALIGNMENT_CENTER
		v.add_child(rw)
		if r.ok and r.data.get("first_clear", false):
			var fc := UI.label("Первое прохождение!", 34, UI.GOLD, true)
			fc.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			v.add_child(fc)
			# large reward (first clear) gets the expressive effect; regular rewards stay compact
			rw.ready.connect(func(): UI.celebrate(rw), CONNECT_ONE_SHOT)
	else:
		var tip := UI.label("Повысьте уровень героев, улучшите Кузницу или смените формацию.\nОтряд не теряется — можно сразу повторить.", 30, UI.TEXT)
		tip.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		tip.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(tip)
	if not r.ok and r.get("status", 0) == 0:
		var retry := UI.button("Повторить получение", "primary")
		retry.pressed.connect(func(): dim.queue_free(); panel.queue_free(); _claim(victory))
		v.add_child(retry)
	var extra := {"rewards": rewards}
	if r.ok:
		extra["exp_gained"] = r.data.get("exp_gained", 0)
		extra["level"] = r.data.get("level", Game.profile.get("level", 1))
		extra["level_up"] = r.data.get("level_up", false)
		var cp: Dictionary = r.data.get("campaign_progress", {})
		if not cp.is_empty():
			extra["progress"] = ["Поход: пройдено %d из %d этапов" % [int(cp.cleared), int(cp.total)]]
		if r.data.get("level_up", false):
			var lu := UI.label("Новый уровень хранителя: %d!" % int(r.data.level), 32, UI.GOLD, true)
			lu.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			v.add_child(lu)
			lu.ready.connect(func(): UI.celebrate(lu), CONNECT_ONE_SHOT)
	v.add_child(_stats_block(extra))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 20)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	var again := UI.button("Ещё раз", "glass", 260)
	again.pressed.connect(func(): Router.goto(Router.BATTLE, {"node_code": node_code, "node": node_info, "replay": true}))
	row.add_child(again)
	var next_code = Game.campaign.get("next_node")
	if victory and next_code and next_code != node_code:
		var nb := UI.button("Далее", "primary", 260)
		nb.pressed.connect(func(): Router.goto(Router.MAIN, {"screen": "campaign"}))
		row.add_child(nb)
	var home := UI.button("На главную", "glass", 300)
	home.pressed.connect(_back)
	row.add_child(home)
	v.add_child(row)
	panel.add_child(v)
	_ui.add_child(panel)
	panel.scale = Vector2(0.85, 0.85)
	panel.pivot_offset = Vector2(450, 300)
	panel.create_tween().tween_property(panel, "scale", Vector2.ONE, 0.25).set_trans(Tween.TRANS_BACK)


func _back() -> void:
	Router.goto(Router.MAIN, {"screen": "home"})



# ------------------------------------------------------------------ battle statistics (from the server event log)
func _battle_stats() -> Dictionary:
	var out := {}
	for u in sim.units:
		out[String(u.uid)] = {"name": String(u.name), "side": int(u.side), "code": String(u.code), "dealt": 0, "taken": 0, "healed": 0}
	for ev in sim.events:
		if ev.type in ["pos", "summon", "despawn"]:
			continue
		var actor := String(ev.get("actor", ""))
		for t in ev.get("targets", []):
			var tid := String(t.get("uid", t.get("target", "")))
			if t.has("dmg"):
				if out.has(actor):
					out[actor].dealt += int(t.dmg)
				if out.has(tid):
					out[tid].taken += int(t.dmg)
			if t.has("heal") and out.has(actor):
				out[actor].healed += int(t.heal)
	return out


## Expandable statistics block: contribution of each hero, damage dealt/taken, healing, survival, duration.
func _stats_block(extra := {}) -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", UI.SP.xs)
	var toggle := UI.button("Статистика боя ▾", "glass", 0, 72)
	toggle.add_theme_font_size_override("font_size", 26)
	box.add_child(toggle)
	var body := VBoxContainer.new()
	body.visible = false
	body.add_theme_constant_override("separation", 4)
	# 1. rewards · 4. experience & level-ups · 6. activity progress (from the server response)
	var rw: Dictionary = extra.get("rewards", {})
	if not rw.is_empty():
		var rr := HBoxContainer.new()
		rr.add_child(UI.label("Награды:", 22, UI.MUTED, true))
		rr.add_child(UI.rewards_row(rw, 24))
		body.add_child(rr)
	if int(extra.get("exp_gained", 0)) > 0:
		body.add_child(UI.label("Опыт игрока: +%d · уровень %d%s" % [int(extra.exp_gained), int(extra.get("level", 1)),
			" — новый уровень!" if extra.get("level_up", false) else ""], 22, UI.GOLD if extra.get("level_up", false) else UI.TEXT, true))
	for line in extra.get("progress", []):
		body.add_child(UI.label(String(line), 22, UI.TEXT))
	var st := _battle_stats()
	var alive: Array = sim.get("survivors", [])
	var mine: Array = []
	for uid in st:
		if st[uid].side == 0:
			mine.append(uid)
	mine.sort_custom(func(a, b): return st[a].dealt > st[b].dealt)
	var total := 0
	for uid in mine:
		total += int(st[uid].dealt)
	var head := HBoxContainer.new()
	for c in [["Герой", 260], ["Урон", 150], ["Получено", 150], ["Лечение", 140]]:
		var l := UI.label(String(c[0]), 22, UI.MUTED, true)
		l.custom_minimum_size = Vector2(int(c[1]), 0)
		head.add_child(l)
	body.add_child(head)
	for uid in mine:
		var r: Dictionary = st[uid]
		var row := HBoxContainer.new()
		var nm := UI.label(("" if uid in alive else "✝ ") + r.name, 24, UI.TEXT if uid in alive else UI.MUTED, true)
		nm.custom_minimum_size = Vector2(260, 0)
		nm.clip_text = true
		row.add_child(nm)
		for val in [r.dealt, r.taken, r.healed]:
			var l := UI.label(Game.fmt(int(val)), 24, UI.GOLD if val == r.dealt else UI.TEXT)
			l.custom_minimum_size = Vector2(150, 0)
			row.add_child(l)
		body.add_child(row)
		body.add_child(UI.progress(float(r.dealt), max(1.0, float(total)), "%d%% урона" % int(100.0 * r.dealt / max(1, total)), UI.TEAL, 16))
	body.add_child(UI.label("Длительность: %.1f с · выжили: %d из %d" % [float(sim.get("duration", 0.0)),
		mine.filter(func(u): return u in alive).size(), mine.size()], 22, UI.MUTED))
	box.add_child(body)
	toggle.pressed.connect(func():
		body.visible = not body.visible
		toggle.text = "Статистика боя ▴" if body.visible else "Статистика боя ▾")
	return box


## Result heading: the admin-panel banner (ui/battle/victory.png / defeat.png, 1024×256) when uploaded,
## otherwise the text title. Custom titles (raids, arena) always stay text.
func _result_head(victory: bool, text: String, size: int, allow_art: bool) -> Control:
	var tex := UI.art("ui/battle/%s.png" % ("victory" if victory else "defeat")) if allow_art else null
	if tex:
		var r := TextureRect.new()
		r.texture = tex
		r.custom_minimum_size = Vector2(820, 205)
		r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		r.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		return r
	var t := UI.title(text, size)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	return t
