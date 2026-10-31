extends Node
## Battle: asks the server to validate + simulate, then replays the authoritative event
## log on the isometric arena. Rewards are claimed with a battle-scoped idempotency key.

const ArenaScript := preload("res://src/world/Arena.gd")
const DialogScript := preload("res://src/ui/StoryDialog.gd")

var arena: Node3D
var node_code := ""
var node_info := {}
var battle_id := ""
var sim := {}
var claim_key := ""
var _ui: Control
var _round_lbl: Label
var _speed_btn: Button
var _skill_banner: Label
var _skipping := false
var _finished := false
var _speed := 1


func _ready() -> void:
	node_code = Router.params.get("node_code", "1-1")
	node_info = Router.params.get("node", {})
	claim_key = Api.new_key()
	_speed = int(Config.settings.get("battle_speed", 1))
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
	await _intro()
	await _play()


func _build_hud() -> void:
	var top := HBoxContainer.new()
	top.set_anchors_preset(Control.PRESET_TOP_WIDE)
	top.offset_top = 70
	top.offset_left = 36
	top.offset_right = -36
	top.add_theme_constant_override("separation", 18)
	_ui.add_child(top)
	var title := UI.glass_panel()
	var tv := VBoxContainer.new()
	tv.add_child(UI.label("%s  %s" % [node_info.get("code", ""), node_info.get("name", "")], 34, UI.GOLD, true))
	_round_lbl = UI.label("Раунд 1", 28, UI.MUTED)
	tv.add_child(_round_lbl)
	title.add_child(tv)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(title)
	_speed_btn = UI.button("x%d" % _speed, "glass", 130)
	_speed_btn.pressed.connect(_toggle_speed)
	top.add_child(_speed_btn)
	var skip := UI.button("Пропуск", "glass", 200)
	skip.pressed.connect(func(): _skipping = true)
	top.add_child(skip)
	_skill_banner = UI.title("", 64)
	_skill_banner.set_anchors_preset(Control.PRESET_CENTER)
	_skill_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_skill_banner.custom_minimum_size = Vector2(1000, 100)
	_skill_banner.position = Vector2(-500, -520)
	_skill_banner.modulate.a = 0
	_ui.add_child(_skill_banner)
	Engine.time_scale = _speed


func _toggle_speed() -> void:
	_speed = _speed % 3 + 1
	_speed_btn.text = "x%d" % _speed
	Engine.time_scale = _speed
	Config.settings.battle_speed = _speed
	Config.save()


func _intro() -> void:
	Sfx.play("unsheathe")
	for uid in arena.units:
		var u: Dictionary = arena.units[uid]
		if u.side == 1:
			Models.play(u.node, "spawn" if String(u.data.code).begins_with("e_") else "idle")
			Models.queue_idle(u.node)
	if node_info.get("is_boss", false):
		Sfx.play("boss")
		arena.shake(0.5)
	await get_tree().create_timer(0.9).timeout


func _play() -> void:
	var current_round := 0
	for ev in sim.events:
		if _skipping:
			break
		if int(ev.round) != current_round:
			current_round = int(ev.round)
			_round_lbl.text = "Раунд %d / 15" % current_round
		await _play_event(ev)
	if _skipping:
		_apply_final_state()
	await get_tree().create_timer(0.5).timeout
	_finish()


func _apply_final_state() -> void:
	# Fast-forward: apply every remaining event's resulting HP instantly.
	for ev in sim.events:
		for t in ev.targets:
			if arena.units.has(t.uid):
				var u: Dictionary = arena.units[t.uid]
				u.hp = int(t.hp)
				u.shield = int(t.get("shield", 0)) if t.has("shield") else 0
				if t.get("killed", false) and u.alive:
					u.alive = false
					Models.play(u.node, "death")
					u.bar.visible = false
					u.ring.visible = false
				arena.set_bar(t.uid)


func _color_for(actor: Dictionary) -> Color:
	match String(actor.data.get("class", "")):
		"mage":
			return Color(0.65, 0.45, 1.0) if actor.side == 0 else Color(0.6, 0.2, 0.9)
		"healer":
			return Color(0.5, 1.0, 0.6)
		"ranger":
			return Color(1.0, 0.85, 0.45)
	return Color(1.0, 0.6, 0.3)


func _play_event(ev: Dictionary) -> void:
	var actor: Dictionary = arena.units.get(ev.actor, {})
	if actor.is_empty() or not actor.alive:
		return
	if ev.type == "stunned":
		arena.float_text(arena.chest(ev.actor), "Оглушён", Color(1, 0.9, 0.4))
		arena.stun_mark(ev.actor, false)
		await get_tree().create_timer(0.35).timeout
		return
	actor.energy = int(ev.get("energy", 0))
	arena.set_bar(ev.actor)
	var is_skill: bool = ev.type == "skill"
	var cls := String(actor.data.get("class", ""))
	var ranged := cls in ["ranger", "mage", "healer"]
	var targets: Array = ev.targets
	var first_uid: String = targets[0].uid if targets.size() > 0 else ""
	if is_skill:
		_banner(String(ev.get("name", "")), actor.side == 0)
		Sfx.play("spell" if ranged else "swing3")
		arena.burst(arena.chest(ev.actor), Color(1, 0.9, 0.5), 30, 2.5, true)
	# face the (first) target
	if first_uid != "" and arena.units.has(first_uid):
		var tp: Vector3 = arena.units[first_uid].node.position
		var dir: Vector3 = tp - actor.node.position
		if dir.length() > 0.1 and arena.units[first_uid].side != actor.side:
			actor.node.rotation.y = atan2(dir.x, dir.z)
	var heal_like: bool = targets.size() > 0 and (targets[0].has("heal") or (targets[0].has("shield") and not targets[0].has("dmg")))
	if not ranged and not heal_like and first_uid != "" and arena.units.has(first_uid) and targets.size() == 1:
		# melee: dash in, strike, return
		var tp2: Vector3 = arena.units[first_uid].node.position
		var stop: Vector3 = tp2 + (actor.node.position - tp2).normalized() * 1.25
		Models.play(actor.node, "run", 0.1)
		var tw := create_tween()
		tw.tween_property(actor.node, "position", stop, 0.28)
		await tw.finished
		var alen := Models.play(actor.node, "skill" if is_skill else "attack", 0.08)
		Sfx.play("swing" if randi() % 2 == 0 else "swing2")
		await get_tree().create_timer(min(alen * 0.45, 0.45)).timeout
		_apply_targets(actor, targets, is_skill)
		await get_tree().create_timer(min(alen * 0.4, 0.35)).timeout
		Models.play(actor.node, "run", 0.1)
		var back := create_tween()
		back.tween_property(actor.node, "position", actor.home, 0.25)
		await back.finished
		actor.node.rotation.y = PI if actor.side == 1 else 0.0
		Models.play(actor.node, "idle", 0.2)
	else:
		var alen2 := Models.play(actor.node, "skill" if is_skill else "attack", 0.1)
		await get_tree().create_timer(min(alen2 * 0.4, 0.4)).timeout
		var col := _color_for(actor)
		if heal_like:
			Sfx.play("heal")
		elif targets.size() > 1:
			Sfx.play("magic")
			var center := Vector3.ZERO
			for t in targets:
				center += arena.units[t.uid].node.position
			center /= targets.size()
			arena.shockwave(center, col, 4.5)
			arena.shake(0.3)
		else:
			Sfx.play("magic" if cls == "mage" else "swing")
			if first_uid != "":
				arena.projectile(arena.chest(ev.actor), arena.chest(first_uid), col)
				await get_tree().create_timer(0.35).timeout
		_apply_targets(actor, targets, is_skill)
		await get_tree().create_timer(0.3).timeout
		Models.queue_idle(actor.node)
		if heal_like or targets.size() > 1:
			actor.node.rotation.y = PI if actor.side == 1 else 0.0


func _apply_targets(actor: Dictionary, targets: Array, is_skill: bool) -> void:
	for t in targets:
		if not arena.units.has(t.uid):
			continue
		var u: Dictionary = arena.units[t.uid]
		var pos: Vector3 = arena.chest(t.uid)
		if t.has("dmg"):
			var crit: bool = t.get("crit", false)
			var txt := str(int(t.dmg))
			if int(t.get("absorbed", 0)) > 0:
				txt += " (щит)"
			arena.float_text(pos, txt + ("!" if crit else ""), Color(1, 0.85, 0.3) if crit else Color(1, 1, 1), crit or is_skill)
			arena.burst(pos, Color(1, 0.55, 0.25) if actor.side == 0 else Color(0.75, 0.35, 1.0), 16 if not crit else 28, 4.0)
			u.hp = int(t.hp)
			u.shield = max(0, int(u.shield) - int(t.get("absorbed", 0)))
			u.energy = min(100, int(u.energy) + 8)
			if u.shield <= 0:
				arena.shield_bubble(t.uid, false)
			if t.get("stunned", false):
				arena.stun_mark(t.uid, true)
			if t.get("killed", false):
				u.alive = false
				Models.play(u.node, "death", 0.1)
				Sfx.play("enemy_die" if u.side == 1 else "back")
				arena.burst(pos, Color(0.7, 0.4, 1.0) if u.side == 1 else Color(0.8, 0.9, 1.0), 30, 2.0, true)
				u.bar.visible = false
				u.ring.visible = false
				var tw: Tween = u.node.create_tween()
				tw.tween_interval(1.2)
				tw.tween_property(u.node, "position:y", -0.6, 0.6)
			else:
				Models.play(u.node, "hit", 0.05)
				Models.queue_idle(u.node)
		if t.has("heal"):
			u.hp = int(t.hp)
			arena.float_text(pos, "+%d" % int(t.heal), Color(0.5, 1.0, 0.55), is_skill)
			arena.burst(u.node.position + Vector3(0, 0.2, 0), Color(0.45, 1.0, 0.55), 26, 2.2, true)
		if t.has("shield"):
			u.shield = int(t.shield)
			arena.shield_bubble(t.uid, true)
			if not t.has("dmg"):
				arena.float_text(pos, "Щит", Color(0.6, 0.85, 1.0))
		arena.set_bar(t.uid)


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


func _finish() -> void:
	if _finished:
		return
	_finished = true
	Engine.time_scale = 1.0
	var victory: bool = sim.result == "victory"
	for uid in arena.units:
		var u: Dictionary = arena.units[uid]
		if u.alive and ((u.side == 0) == victory):
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
	if victory:
		var sub := UI.label("Награды выданы сервером" if r.ok else "Не удалось получить награду", 30, UI.MUTED)
		sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(sub)
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
