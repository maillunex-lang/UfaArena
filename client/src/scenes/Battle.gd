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
	_speeds = Game.profile.get("battle_speeds", [1, 2])
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


func _start() -> void:
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
	_timer_lbl = UI.label("1:30", 28, UI.MUTED)
	tv.add_child(_timer_lbl)
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
		var nm := UI.label(String(u.name), 22, UI.TEXT, true)
		nm.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(nm)
		card.add_child(v)
		row.add_child(card)
		_cards[u.uid] = {"hp": hp, "en": en, "root": card}


func _load_portrait(tr: TextureRect, code: String) -> void:
	tr.texture = await Models.portrait(code, 192)


func _toggle_speed() -> void:
	var i := _speeds.find(_speed)
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
			_apply_targets(arena.units[imp.ev.actor], imp.ev.targets, imp.ev.type == "skill")
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
	var actor: Dictionary = arena.units.get(ev.actor, {})
	if actor.is_empty() or not actor.alive:
		return
	if ev.type == "pos":
		actor.target_pos = arena.sim_pos(float(ev.x), float(ev.z))
		return
	# attack / skill
	var is_skill: bool = ev.type == "skill"
	var cls := String(actor.data.get("class", ""))
	var ranged := cls in ["ranger", "mage", "healer"]
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
	var alen := Models.play(actor.node, "skill" if is_skill else "attack", 0.08)
	Models.queue_idle(actor.node)
	actor.busy_until = _clock + minf(alen, 1.2)
	actor.moving = false
	if is_skill:
		_banner(String(ev.get("name", "")), actor.side == 0)
		Sfx.play("spell" if ranged else "swing3")
		arena.burst(arena.chest(ev.actor), Color(1, 0.9, 0.5), 30, 2.5, true)
		if targets.size() > 1:
			arena.shake(0.25)
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
		if ev.type == "pos":
			continue
		for t in ev.targets:
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


func _banner(text: String, ally: bool) -> void:
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
	await _claim(victory)


func _claim(victory: bool) -> void:
	var r := await Api.post_json("/campaign/%s/complete" % node_code, {"battle_id": battle_id}, claim_key)
	if not r.ok:
		_result_panel(victory, {}, r)
		return
	Game.set_wallet(r.data.get("wallet", {}))
	Game.campaign["next_node"] = r.data.get("next_node")
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
	panel.position = Vector2(-450, -380)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 22)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	var t := UI.title("ПОБЕДА" if victory else "ПОРАЖЕНИЕ", 88)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(t)
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
	else:
		var tip := UI.label("Повысьте уровень героев, улучшите Кузницу или смените формацию.\nОтряд не теряется — можно сразу повторить.", 30, UI.TEXT)
		tip.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		tip.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(tip)
	if not r.ok and r.get("status", 0) == 0:
		var retry := UI.button("Повторить получение", "primary")
		retry.pressed.connect(func(): dim.queue_free(); panel.queue_free(); _claim(victory))
		v.add_child(retry)
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
	var home := UI.button("В крепость", "glass", 300)
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
