extends Control
## Short story dialogue with rendered 3D->2D hero portraits. `await play(lines)`.
## lines: [{speaker: hero_code | npc | "narrator", text: String}]
##   {"choice": id}        — server-validated decision point (options from /story/state, POST /story/choice)
##   {"if": {flag: value}} — line shown only when the story flag has this value

signal _advance

var _portrait: TextureRect
var _name: Label
var _text: Label
var _typing := false
var _skipped := false
var _in_choice := false
var _hint: Label
var _choice_box: VBoxContainer
var _skip: Button
## Story characters of season 1 «Пробуждение» (docs/lore/URALIA_FACTIONS_AND_CHARACTERS.md).
const NPC := {"ancient": "Голос", "ilsur": "Ильсур", "aisylu": "Айсылу", "timer": "Тимер", "bayras": "Байрас",
	"kahym": "Хранитель Кахым"}


func _init() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.35)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)
	var panel := UI.glass_panel(Color("#d7c6ff"))
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 30
	panel.offset_right = -30
	panel.offset_top = -560
	panel.offset_bottom = -260
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(panel)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 26)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(h)
	_portrait = TextureRect.new()
	_portrait.custom_minimum_size = Vector2(240, 240)
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	h.add_child(_portrait)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	h.add_child(v)
	_name = UI.label("", 40, UI.GOLD, true)
	v.add_child(_name)
	_text = UI.label("", 34)
	_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_text.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	v.add_child(_text)
	var foot := HBoxContainer.new()
	foot.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var hint := UI.label("Коснитесь, чтобы продолжить ▸", 26, UI.MUTED)
	_hint = hint
	hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	foot.add_child(hint)
	v.add_child(foot)
	_choice_box = VBoxContainer.new()
	_choice_box.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_choice_box.offset_left = 60
	_choice_box.offset_right = -60
	_choice_box.offset_bottom = -580
	_choice_box.offset_top = -580
	_choice_box.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_choice_box.add_theme_constant_override("separation", 12)
	_choice_box.visible = false
	add_child(_choice_box)
	# Onboarding must be skippable: one tap ends the whole story (it stops at a decision the player has not made).
	var skip := UI.button("Пропустить", "dim", 0, 72)
	skip.add_theme_font_size_override("font_size", 26)
	skip.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)  # right above the dialogue panel
	skip.offset_left = -300
	skip.offset_right = -30
	skip.offset_top = -650
	skip.offset_bottom = -578
	skip.pressed.connect(skip_all)
	add_child(skip)
	_skip = skip


## Ends the dialogue immediately (also used by automated UI tests).
func skip_all() -> void:
	_skipped = true
	_typing = false
	_advance.emit()


func play(lines: Array) -> void:
	for line in lines:
		if line.has("choice"):
			var cid := String(line.choice)
			if Game.story_made.has(cid) or not Game.story_choices.has(cid):
				continue  # already decided (replay) or unknown on this server
			_skipped = false  # skipping stops at an open decision
			await _ask(Game.story_choices[cid])
			continue
		if not _visible_line(line):
			continue
		if _skipped:
			continue
		var sp: String = line.get("speaker", "narrator")
		_text.add_theme_color_override("font_color", UI.TEXT)
		if sp == "narrator":
			_name.text = "Летописец"
			_portrait.texture = UI.art("ui/story/narrator.png")  # admin-panel portrait
		elif NPC.has(sp):
			# story characters who are not (yet) collectible heroes; portraits come from the admin panel
			_name.text = String(NPC[sp])
			_portrait.texture = UI.art("ui/story/%s.png" % sp)
			if sp == "ancient":  # the Voice of the Ancient: violet, no face unless an image is uploaded
				_text.add_theme_color_override("font_color", Color("#d6b8ff"))
		else:
			_name.text = String(Game.catalog_hero(sp).get("name", "Летописец"))
			_portrait.texture = await Models.portrait(sp)
		_name.add_theme_color_override("font_color", Color("#c9a8ff") if sp == "ancient" else UI.GOLD)
		_portrait.visible = _portrait.texture != null  # no empty frame until a portrait is uploaded
		if _skipped:
			break
		_text.text = line.get("text", "")
		_text.visible_ratio = 0.0
		_typing = true
		var tw := create_tween()
		tw.tween_property(_text, "visible_ratio", 1.0, clampf(_text.text.length() * 0.025, 0.4, 2.0))
		tw.tween_callback(func(): _typing = false)
		await _advance
	queue_free()


func _visible_line(line: Dictionary) -> bool:
	var cond: Dictionary = line.get("if", {})
	for k in cond:
		if String(Game.story_flags.get(k, "")) != String(cond[k]):
			return false
	return true


## Decision point: options above the dialogue; the server records the choice before the story continues
## (nothing is confirmed locally, brief §28.1).
func _ask(c: Dictionary) -> void:
	_in_choice = true
	_name.text = String(c.get("title", "Решение"))
	_name.add_theme_color_override("font_color", UI.GOLD)
	_portrait.visible = false
	_text.add_theme_color_override("font_color", UI.TEXT)
	_text.text = String(c.get("prompt", ""))
	_text.visible_ratio = 1.0
	_hint.text = "Выберите — решение нельзя будет изменить"
	for b in _choice_box.get_children():
		b.queue_free()
	var done := [false]
	for o in c.get("options", []):
		var b := UI.button(String(o.text), "glass", 0, 96)
		b.add_theme_font_size_override("font_size", 30)
		var key: String = o.key
		b.pressed.connect(func():
			for x in _choice_box.get_children():
				(x as Button).disabled = true
			UI.set_loading(b, true)
			var r := await Api.post_json("/story/choice", {"choice_id": String(c.id), "option": key}, true)
			if not is_instance_valid(b):
				return
			UI.set_loading(b, false)
			if not r.ok:
				Router.error(r)
				for x in _choice_box.get_children():
					(x as Button).disabled = false
				return
			Game.apply_story(r.data)
			done[0] = true
			_advance.emit())
		_choice_box.add_child(b)
	_choice_box.visible = true
	_skip.visible = false  # a decision cannot be skipped
	while not done[0]:
		await _advance
	_choice_box.visible = false
	_skip.visible = true
	_hint.text = "Коснитесь, чтобы продолжить ▸"
	_in_choice = false


func _gui_input(event: InputEvent) -> void:
	var pressed: bool = (event is InputEventMouseButton and event.pressed) or (event is InputEventScreenTouch and event.pressed)
	if not pressed:
		return
	accept_event()
	if _in_choice:
		return  # a decision needs a button, not a tap
	if _typing:
		_text.visible_ratio = 1.0
		_typing = false
	else:
		Sfx.play("click")
		_advance.emit()
