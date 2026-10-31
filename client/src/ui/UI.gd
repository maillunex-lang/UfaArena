class_name UI
extends RefCounted
## «Liquid Glass Fantasy» UI kit: glass panels, gilded buttons, labels, chips, bars.

const FONT_REG := preload("res://assets/third_party/fonts/Philosopher-Regular.ttf")
const FONT_BOLD := preload("res://assets/third_party/fonts/Philosopher-Bold.ttf")
const GLASS_SHADER := preload("res://src/ui/glass.gdshader")

const GOLD := Color("#f4cf7a")
const GOLD_DARK := Color("#9a6b22")
const INK := Color("#0d1424")
const TEXT := Color("#f5f1e6")
const MUTED := Color("#d3dcea")
const ACCENT := Color("#7fd4ff")

static var _theme: Theme


static func theme() -> Theme:
	if _theme:
		return _theme
	var t := Theme.new()
	t.default_font = FONT_REG
	t.default_font_size = 34
	t.set_color("font_color", "Label", TEXT)
	t.set_color("font_outline_color", "Label", Color(0.02, 0.03, 0.07, 0.9))
	t.set_constant("outline_size", "Label", 8)
	t.set_color("font_outline_color", "Button", Color(0.02, 0.03, 0.07, 0.85))
	t.set_constant("outline_size", "Button", 7)
	t.set_color("font_outline_color", "CheckButton", Color(0.02, 0.03, 0.07, 0.85))
	t.set_constant("outline_size", "CheckButton", 6)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(1, 1, 1, 0.06)
	sb.set_corner_radius_all(18)
	t.set_stylebox("panel", "PanelContainer", StyleBoxEmpty.new())
	var le_n := _flat(Color(0.02, 0.03, 0.07, 0.55), Color(1, 1, 1, 0.35), 18, 2)
	var le_f := _flat(Color(0.02, 0.03, 0.07, 0.65), GOLD, 18, 2)
	for st in [le_n, le_f]:
		st.content_margin_left = 22
		st.content_margin_right = 22
	t.set_stylebox("normal", "LineEdit", le_n)
	t.set_stylebox("focus", "LineEdit", le_f)
	t.set_color("font_placeholder_color", "LineEdit", Color(1, 1, 1, 0.55))
	t.set_color("font_color", "LineEdit", TEXT)
	t.set_stylebox("slider", "HSlider", _flat(Color(0, 0, 0, 0.45), Color(1, 1, 1, 0.35), 10, 2))
	t.set_stylebox("grabber_area", "HSlider", _flat(GOLD, Color.TRANSPARENT, 10, 0))
	t.set_stylebox("grabber_area_highlight", "HSlider", _flat(GOLD.lightened(0.2), Color.TRANSPARENT, 10, 0))
	var grab := Image.create(44, 44, false, Image.FORMAT_RGBA8)
	grab.fill(Color(0, 0, 0, 0))
	for x in 44:
		for y in 44:
			var d := Vector2(x - 21.5, y - 21.5).length()
			if d < 20:
				grab.set_pixel(x, y, Color("#fff1c2") if d < 16 else Color("#9a6b22"))
	var gt := ImageTexture.create_from_image(grab)
	t.set_icon("grabber", "HSlider", gt)
	t.set_icon("grabber_highlight", "HSlider", gt)
	t.set_stylebox("scroll", "VScrollBar", StyleBoxEmpty.new())
	t.set_stylebox("grabber", "VScrollBar", _flat(Color(1, 1, 1, 0.25), Color.TRANSPARENT, 6, 0))
	t.set_stylebox("grabber_highlight", "VScrollBar", _flat(Color(1, 1, 1, 0.4), Color.TRANSPARENT, 6, 0))
	_theme = t
	return t


static func _flat(bg: Color, border: Color, radius: int, bw: int) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.border_color = border
	s.set_border_width_all(bw)
	s.set_corner_radius_all(radius)
	s.anti_aliasing = true
	s.corner_detail = 10
	return s


static func glass_style(tint := Color("#bfe3ff"), radius := 34) -> StyleBoxFlat:
	# dark smoky fill (also the fallback look when the blur shader is off)
	var fill := Color(0.05, 0.08, 0.14).lerp(tint, 0.18)
	# with the blur shader the fill alpha must stay low (shader reads high alpha as border)
	var s := _flat(Color(fill.r, fill.g, fill.b, 0.16 if Gfx.setting("blur") else 0.68), Color(1, 1, 1, 0.55), radius, 3)
	s.border_color = Color(tint.lightened(0.5), 0.75)
	s.shadow_color = Color(0, 0, 0, 0.28)
	s.shadow_size = 18
	s.shadow_offset = Vector2(0, 8)
	s.content_margin_left = 30
	s.content_margin_right = 30
	s.content_margin_top = 22
	s.content_margin_bottom = 22
	return s


static func glass_panel(tint := Color("#bfe3ff"), radius := 34) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", glass_style(tint, radius))
	apply_glass(p, tint)
	return p


## Opaque dark panel for overlays that sit on top of busy UI (hero card, pickers).
static func solid_panel(tint := Color("#bfe3ff"), radius := 34) -> PanelContainer:
	var p := PanelContainer.new()
	var st := glass_style(tint, radius)
	var fill := Color(0.05, 0.07, 0.12).lerp(tint, 0.10)
	st.bg_color = Color(fill.r, fill.g, fill.b, 0.96)
	p.add_theme_stylebox_override("panel", st)
	return p


static func apply_glass(c: CanvasItem, tint := Color("#bfe3ff")) -> void:
	if not Gfx.setting("blur"):
		return
	var m := ShaderMaterial.new()
	m.shader = GLASS_SHADER
	m.set_shader_parameter("tint", tint)
	c.material = m


static func label(text: String, size := 34, color := TEXT, bold := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", maxi(size, 26))  # phone readability floor
	l.add_theme_color_override("font_color", color)
	if bold:
		l.add_theme_font_override("font", FONT_BOLD)
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return l


## Turns on word wrap for long labels stacked in VBoxes under `root` (they get the column width),
## so bigger fonts never push a screen wider than the phone.
static func autowrap_tree(root: Node) -> void:
	for c in root.get_children():
		if c is Label and c.autowrap_mode == TextServer.AUTOWRAP_OFF and c.get_parent() is VBoxContainer \
				and c.text.length() > 16:
			c.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		autowrap_tree(c)


## Keeps autowrap_tree applied as content is added later (async renders).
static func keep_wrapped(root: Container) -> void:
	root.sort_children.connect(func(): autowrap_tree(root))


static func title(text: String, size := 52) -> Label:
	var l := label(text, size, GOLD, true)
	l.add_theme_constant_override("outline_size", 10)
	l.add_theme_color_override("font_outline_color", Color(0.15, 0.08, 0.0, 0.85))
	return l


static func button(text: String, kind := "glass", min_w := 0, h := 104) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(min_w, h)
	b.add_theme_font_override("font", FONT_BOLD)
	b.add_theme_font_size_override("font_size", 36)
	b.focus_mode = Control.FOCUS_NONE
	var normal: StyleBoxFlat
	match kind:
		"primary":
			normal = _flat(Color("#e7b453"), Color("#fff1c2"), 28, 3)
			normal.bg_color = Color("#d9a23f")
			b.add_theme_color_override("font_color", Color("#2b1600"))
			b.add_theme_color_override("font_hover_color", Color("#2b1600"))
			b.add_theme_color_override("font_pressed_color", Color("#2b1600"))
		"danger":
			normal = _flat(Color("#b6474a"), Color("#ffb3a8"), 28, 3)
		"dim":
			normal = _flat(Color(0.04, 0.05, 0.09, 0.45), Color(1, 1, 1, 0.25), 28, 2)
			b.add_theme_color_override("font_color", MUTED)
		_:
			normal = _flat(Color(0.10, 0.17, 0.30, 0.74), Color(1, 1, 1, 0.6), 28, 3)
	normal.shadow_color = Color(0, 0, 0, 0.3)
	normal.shadow_size = 10
	normal.shadow_offset = Vector2(0, 5)
	normal.content_margin_left = 26
	normal.content_margin_right = 26
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = normal.bg_color.lightened(0.12)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = normal.bg_color.darkened(0.15)
	pressed.shadow_size = 3
	var disabled := normal.duplicate() as StyleBoxFlat
	disabled.bg_color = Color(0.3, 0.32, 0.38, 0.6)
	disabled.border_color = Color(1, 1, 1, 0.2)
	b.add_theme_stylebox_override("normal", normal)
	b.add_theme_stylebox_override("hover", hover)
	b.add_theme_stylebox_override("pressed", pressed)
	b.add_theme_stylebox_override("disabled", disabled)
	b.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	b.add_theme_color_override("font_disabled_color", Color(1, 1, 1, 0.72))
	b.pressed.connect(func(): Sfx.play("click"))
	b.button_down.connect(func(): b.pivot_offset = b.size / 2; b.create_tween().tween_property(b, "scale", Vector2(0.96, 0.96), 0.06))
	b.button_up.connect(func(): b.create_tween().tween_property(b, "scale", Vector2.ONE, 0.1))
	return b


static func icon_button(kind: String, caption: String, badge := false) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(150, 168)
	b.focus_mode = Control.FOCUS_NONE
	for st in ["normal", "hover", "pressed", "focus"]:
		b.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	var v := VBoxContainer.new()
	v.set_anchors_preset(Control.PRESET_FULL_RECT)
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	var bubble := PanelContainer.new()
	bubble.add_theme_stylebox_override("panel", _round_glass())
	bubble.custom_minimum_size = Vector2(112, 112)
	bubble.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	bubble.mouse_filter = Control.MOUSE_FILTER_IGNORE
	apply_glass(bubble)
	var ic := GameIcon.new()
	ic.kind = kind
	ic.custom_minimum_size = Vector2(76, 76)
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bubble.add_child(ic)
	v.add_child(bubble)
	var l := label(caption, 26, TEXT, true)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(l)
	b.add_child(v)
	if badge:
		var dot := Panel.new()
		dot.add_theme_stylebox_override("panel", _flat(Color("#ff5a4f"), Color.WHITE, 16, 3))
		dot.size = Vector2(32, 32)
		dot.position = Vector2(108, 6)
		dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
		dot.name = "Badge"
		b.add_child(dot)
	b.pressed.connect(func(): Sfx.play("open"))
	return b


static func _round_glass() -> StyleBoxFlat:
	var s := _flat(Color(0.75, 0.88, 1.0, 0.18), Color(1, 1, 1, 0.7), 56, 3)
	s.shadow_color = Color(0, 0, 0, 0.3)
	s.shadow_size = 12
	s.content_margin_left = 18
	s.content_margin_right = 18
	s.content_margin_top = 18
	s.content_margin_bottom = 18
	return s


static func chip(kind: String, value: String) -> PanelContainer:
	var p := PanelContainer.new()
	var s := _flat(Color(0.05, 0.08, 0.16, 0.55), Color(1, 1, 1, 0.35), 30, 2)
	s.content_margin_left = 10
	s.content_margin_right = 22
	s.content_margin_top = 4
	s.content_margin_bottom = 4
	p.add_theme_stylebox_override("panel", s)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	var ic := GameIcon.new()
	ic.kind = kind
	ic.custom_minimum_size = Vector2(52, 52)
	h.add_child(ic)
	var l := label(value, 32, TEXT, true)
	l.name = "Value"
	h.add_child(l)
	p.add_child(h)
	return p


static func rewards_row(rw: Dictionary, size := 30) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 18)
	for k in rw:
		if int(rw[k]) <= 0:
			continue
		var ic := GameIcon.new()
		ic.kind = k
		ic.custom_minimum_size = Vector2(size + 14, size + 14)
		h.add_child(ic)
		h.add_child(label(Game.fmt(rw[k]), size, TEXT, true))
	return h


static func bar(value: float, max_v: float, color: Color, h := 18, w := 0) -> ProgressBar:
	var pb := ProgressBar.new()
	pb.max_value = max(max_v, 1.0)
	pb.value = value
	pb.show_percentage = false
	pb.custom_minimum_size = Vector2(w, h)
	pb.add_theme_stylebox_override("background", _flat(Color(0, 0, 0, 0.5), Color(1, 1, 1, 0.25), h / 2, 1))
	pb.add_theme_stylebox_override("fill", _flat(color, Color.TRANSPARENT, h / 2, 0))
	return pb


static func spacer(h := 20) -> Control:
	var c := Control.new()
	c.custom_minimum_size = Vector2(0, h)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


static func expand() -> Control:
	var c := Control.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return c


static func stars(n: int, size := 26) -> Label:
	return label("★".repeat(n) if n > 0 else "", size, GOLD, true)


static func scroll(child: Control) -> ScrollContainer:
	var s := ScrollContainer.new()
	s.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	s.size_flags_vertical = Control.SIZE_EXPAND_FILL
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	child.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.add_child(child)
	return s
