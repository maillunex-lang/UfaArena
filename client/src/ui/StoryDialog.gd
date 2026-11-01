extends Control
## Short story dialogue with rendered 3D->2D hero portraits. `await play(lines)`.
## lines: [{speaker: hero_code | "narrator", text: String}]

signal _advance

var _portrait: TextureRect
var _name: Label
var _text: Label
var _typing := false
var _skipped := false


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
	hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	foot.add_child(hint)
	v.add_child(foot)
	# Onboarding must be skippable: one tap ends the whole story.
	var skip := UI.button("Пропустить", "dim", 0, 72)
	skip.add_theme_font_size_override("font_size", 26)
	skip.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)  # right above the dialogue panel
	skip.offset_left = -300
	skip.offset_right = -30
	skip.offset_top = -650
	skip.offset_bottom = -578
	skip.pressed.connect(skip_all)
	add_child(skip)


## Ends the dialogue immediately (also used by automated UI tests).
func skip_all() -> void:
	_skipped = true
	_typing = false
	_advance.emit()


func play(lines: Array) -> void:
	for line in lines:
		if _skipped:
			break
		var sp: String = line.get("speaker", "narrator")
		var hero := Game.catalog_hero(sp)
		_name.text = hero.get("name", "Летописец") if sp != "narrator" else "Летописец"
		_portrait.texture = null
		if sp != "narrator":
			_portrait.texture = await Models.portrait(sp)
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


func _gui_input(event: InputEvent) -> void:
	var pressed: bool = (event is InputEventMouseButton and event.pressed) or (event is InputEventScreenTouch and event.pressed)
	if not pressed:
		return
	accept_event()
	if _typing:
		_text.visible_ratio = 1.0
		_typing = false
	else:
		Sfx.play("click")
		_advance.emit()
