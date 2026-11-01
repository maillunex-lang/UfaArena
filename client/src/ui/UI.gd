class_name UI
extends RefCounted
## URALIA design system — the single source of UI tokens and components.
## Palette «Night Turquoise + Ancient Gold», Premium Dark Glass surfaces (no blur by default: performance),
## Manrope for interface text, Philosopher for large headings. See docs/ui/design-system.md.

const FONT_REG := preload("res://assets/third_party/fonts/Manrope-500.ttf")
const FONT_BOLD := preload("res://assets/third_party/fonts/Manrope-700.ttf")
const FONT_TITLE := preload("res://assets/third_party/fonts/Philosopher-Bold.ttf")
const GLASS_SHADER := preload("res://src/ui/glass.gdshader")

# ---- colour tokens (system roles) ----
const BG := Color("#0b1215")           # app background (graphite)
const SURFACE := Color("#121c21")      # cards
const SURFACE_2 := Color("#182830")    # raised elements / secondary buttons
const LINE := Color("#2c4549")         # dividers, idle borders
const TEAL := Color("#3fd0c3")         # active state, secondary accent
const TEAL_DEEP := Color("#15605a")
const GOLD := Color("#efcf86")         # champagne gold: headings, values, primary accents
const GOLD_DARK := Color("#a37a2c")    # antique gold: borders, pressed primary
const INK := Color("#1d1405")          # text on gold
const TEXT := Color("#eef2f0")
const MUTED := Color("#a9bab7")
const ACCENT := TEAL
const DANGER := Color("#e0604f")
const WARNING := Color("#e8a33d")
const SUCCESS := Color("#5fc98a")
const RARITY := {1: Color("#9aa4a8"), 2: Color("#6fcf7c"), 3: Color("#58a6ff"), 4: Color("#b77cff"), 5: Color("#f2c14e"), 6: Color("#ff6f61")}
# ---- spacing / radius / type scale ----
const SP := {"xs": 6, "s": 10, "m": 16, "l": 24, "xl": 32}
const R := {"s": 12, "m": 18, "l": 24, "pill": 60}
const FS := {"caption": 24, "body": 28, "body_l": 31, "h3": 34, "h2": 40, "h1": 50}

static var _theme: Theme


static func theme() -> Theme:
	if _theme:
		return _theme
	var t := Theme.new()
	# Symbols (⚔ ★ ✓ ▸ …) and chat emoji: bundled Noto subsets first (the Web build has no system fonts),
	# then the device fonts for anything else (full colour emoji on Android).
	var sys := SystemFont.new()
	sys.font_names = PackedStringArray(["Noto Color Emoji", "Apple Color Emoji", "Segoe UI Emoji", "Noto Sans Symbols", "Roboto"])
	var fb: Array[Font] = []
	for path in ["res://assets/third_party/fonts/NotoSansSymbols2-subset.woff", "res://assets/third_party/fonts/NotoSansSymbols-subset.woff",
			"res://assets/third_party/fonts/NotoSansMath-subset.woff", "res://assets/third_party/fonts/NotoEmoji-subset.woff"]:
		if ResourceLoader.exists(path):
			fb.append(load(path))
	fb.append(sys)
	for f in [FONT_REG, FONT_BOLD, FONT_TITLE]:
		if f.fallbacks.is_empty():
			f.fallbacks = fb
	t.default_font = FONT_REG
	t.default_font_size = 30
	t.set_color("font_color", "Label", TEXT)
	# light outline only: surfaces are dark and opaque enough for clean text
	t.set_color("font_outline_color", "Label", Color(0, 0, 0, 0.55))
	t.set_constant("outline_size", "Label", 4 if not high_contrast() else 6)
	t.set_color("font_outline_color", "Button", Color(0, 0, 0, 0.35))
	t.set_constant("outline_size", "Button", 2)
	t.set_color("font_color", "CheckButton", TEXT)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(1, 1, 1, 0.06)
	sb.set_corner_radius_all(18)
	t.set_stylebox("panel", "PanelContainer", StyleBoxEmpty.new())
	var le_n := _flat(Color(BG, 0.9), LINE, R.s, 2)
	var le_f := _flat(Color(BG, 0.95), GOLD_DARK, R.s, 2)
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


static func high_contrast() -> bool:
	return bool(Config.settings.get("high_contrast", false))


static func reduce_motion() -> bool:
	return bool(Config.settings.get("reduce_motion", false))


static func colorblind() -> bool:
	return bool(Config.settings.get("colorblind", false))


## Status colours: in colour-blind mode red/green become orange/blue (distinguishable for protan/deutan).
static func ok_color() -> Color:
	return Color("#4ea3ff") if colorblind() else SUCCESS


static func bad_color() -> Color:
	return Color("#ff9d2e") if colorblind() else DANGER


## Labelled on/off switch row (large touch target, readable state): [text ........ (o  )]
static func toggle_row(text: String, on: bool, cb: Callable) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", SP.m)
	row.custom_minimum_size.y = 76
	var l := label(text, FS.body, TEXT)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	row.add_child(l)
	var b := Button.new()
	b.custom_minimum_size = Vector2(118, 62)
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	b.toggle_mode = true
	b.button_pressed = on
	b.tooltip_text = text
	var knob := Panel.new()
	knob.add_theme_stylebox_override("panel", _flat(Color("#f4f1e8"), Color(0, 0, 0, 0.25), 25, 1))
	knob.size = Vector2(50, 50)
	knob.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(knob)
	var paint := func(state: bool):
		var sb := _flat(TEAL_DEEP if state else Color(0.16, 0.19, 0.21), Color(GOLD, 0.7) if state else Color(1, 1, 1, 0.25), 31, 2)
		for st in ["normal", "hover", "pressed", "hover_pressed", "focus"]:
			b.add_theme_stylebox_override(st, sb)
		knob.position = Vector2(62 if state else 6, 6)
	paint.call(on)
	b.toggled.connect(func(state: bool): paint.call(state); Sfx.play("click"); vibrate(); cb.call(state))
	row.add_child(b)
	# tapping the caption toggles too
	l.mouse_filter = Control.MOUSE_FILTER_STOP
	l.gui_input.connect(func(e: InputEvent):
		if (e is InputEventMouseButton and e.pressed and e.button_index == MOUSE_BUTTON_LEFT) or (e is InputEventScreenTouch and e.pressed):
			b.button_pressed = not b.button_pressed)
	return row


## Short haptic tick on taps (Android/iOS only; respects the setting).
static func vibrate(ms := 12) -> void:
	if bool(Config.settings.get("vibration", true)) and (OS.has_feature("android") or OS.has_feature("ios")):
		Input.vibrate_handheld(ms)


## Premium Dark Glass: opaque-enough graphite surface, thin gold border, soft shadow. `tint` nudges the border hue.
static func glass_style(tint := Color("#bfe3ff"), radius := 24) -> StyleBoxFlat:
	var alpha := 0.97 if high_contrast() else (0.86 if not Gfx.setting("blur") else 0.2)
	var s := _flat(Color(SURFACE, alpha), Color(GOLD_DARK.lerp(tint, 0.25), 0.75), mini(radius, R.l), 2)
	s.shadow_color = Color(0, 0, 0, 0.35)
	s.shadow_size = 14
	s.shadow_offset = Vector2(0, 6)
	s.content_margin_left = SP.l
	s.content_margin_right = SP.l
	s.content_margin_top = SP.m + 2
	s.content_margin_bottom = SP.m + 2
	return s


static func glass_panel(tint := Color("#bfe3ff"), radius := 24) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", glass_style(tint, radius))
	apply_glass(p, tint)
	return p


## Opaque panel for overlays (modals, context panels).
static func solid_panel(tint := Color("#bfe3ff"), radius := 24) -> PanelContainer:
	var p := PanelContainer.new()
	var st := glass_style(tint, radius)
	st.bg_color = Color(SURFACE.lerp(BG, 0.3), 0.985)
	p.add_theme_stylebox_override("panel", st)
	return p


## Blur shader only on the high preset and only where callers ask for it (one per screen at most).
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
	l.add_theme_font_size_override("font_size", maxi(size, 24))  # phone readability floor
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


## Art uploaded in the web admin panel arrives as a content package; every slot lives at art/<path>.
static func art(path: String) -> Texture2D:
	return Content.texture("art/" + path) if Content.has("art/" + path) else null


## Violet "ИИ" badge: AI personas are always labelled in social UI.
static func ai_badge() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := _flat(Color("#6a3fb5"), Color("#d6b8ff"), 10, 2)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	p.add_theme_stylebox_override("panel", sb)
	p.add_child(label("ИИ", 22, Color.WHITE, true))
	p.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	p.tooltip_text = "Виртуальный персонаж (ИИ)"
	return p


static func presence_color(p: String) -> Color:
	return {"online": Color("#5ee38a"), "recent": Color("#f4cf7a")}.get(p, Color(0.6, 0.62, 0.68))


static func presence_text(p: String) -> String:
	return {"online": "в сети", "recent": "был недавно", "hidden": "статус скрыт"}.get(p, "не в сети")


## ISO UTC timestamp -> local "dd.MM HH:mm" (or "HH:mm" for today).
static func local_time(iso: String) -> String:
	if iso.length() < 19:
		return ""
	var unix := Time.get_unix_time_from_datetime_string(iso.substr(0, 19))
	unix += Time.get_time_zone_from_system().get("bias", 0) * 60
	var d := Time.get_datetime_dict_from_unix_time(int(unix))
	var now := Time.get_datetime_dict_from_system()
	if d.day == now.day and d.month == now.month:
		return "%02d:%02d" % [d.hour, d.minute]
	return "%02d.%02d %02d:%02d" % [d.day, d.month, d.hour, d.minute]


static func title(text: String, size := 52) -> Label:
	var l := label(text, size, GOLD, false)
	l.add_theme_font_override("font", FONT_TITLE)
	l.add_theme_constant_override("outline_size", 6)
	l.add_theme_color_override("font_outline_color", Color(0.1, 0.06, 0.0, 0.8))
	return l


## Buttons: primary (gold, important), glass/secondary (neutral), accent (teal, active choice), danger, dim (inactive).
## States: normal, hover, pressed (scale), focus, disabled; set_loading() for async actions.
static func button(text: String, kind := "glass", min_w := 0, h := 96) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(min_w, h)
	b.add_theme_font_override("font", FONT_BOLD)
	b.add_theme_font_size_override("font_size", 30)
	b.focus_mode = Control.FOCUS_NONE
	var normal: StyleBoxFlat
	var fc := TEXT
	match kind:
		"primary":
			normal = _flat(Color("#d9ab52"), Color("#f6dc9c"), R.m, 2)
			fc = INK
		"accent":
			normal = _flat(TEAL_DEEP, TEAL, R.m, 2)
		"danger":
			normal = _flat(Color("#7a2a22"), DANGER, R.m, 2)
		"dim":
			normal = _flat(Color(SURFACE, 0.8), Color(LINE, 0.7), R.m, 1)
			fc = MUTED
		_:
			normal = _flat(SURFACE_2, Color(GOLD_DARK, 0.7), R.m, 2)
	for k in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		b.add_theme_color_override(k, fc)
	normal.shadow_color = Color(0, 0, 0, 0.3)
	normal.shadow_size = 6
	normal.shadow_offset = Vector2(0, 3)
	normal.content_margin_left = SP.l
	normal.content_margin_right = SP.l
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = normal.bg_color.lightened(0.08)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = normal.bg_color.darkened(0.15)
	pressed.shadow_size = 1
	var disabled := _flat(Color(SURFACE, 0.7), Color(LINE, 0.5), R.m, 1)
	disabled.content_margin_left = SP.l
	disabled.content_margin_right = SP.l
	var focus := _flat(Color.TRANSPARENT, TEAL, R.m, 2)
	focus.draw_center = false
	b.add_theme_stylebox_override("normal", normal)
	b.add_theme_stylebox_override("hover", hover)
	b.add_theme_stylebox_override("pressed", pressed)
	b.add_theme_stylebox_override("disabled", disabled)
	b.add_theme_stylebox_override("focus", focus)
	b.add_theme_color_override("font_disabled_color", Color(MUTED, 0.6))
	b.pressed.connect(func(): Sfx.play("click"); vibrate())
	if not reduce_motion():
		b.button_down.connect(func(): b.pivot_offset = b.size / 2; b.create_tween().tween_property(b, "scale", Vector2(0.97, 0.97), 0.05))
		b.button_up.connect(func(): b.create_tween().tween_property(b, "scale", Vector2.ONE, 0.08))
	return b


## Loading state: disables the button and shows an animated ellipsis until set_loading(b, false).
static func set_loading(b: Button, on: bool) -> void:
	if not is_instance_valid(b):
		return
	if on:
		if not b.has_meta("label"):
			b.set_meta("label", b.text)
		b.disabled = true
		b.text = "…"
	else:
		b.disabled = false
		if b.has_meta("label"):
			b.text = String(b.get_meta("label"))
			b.remove_meta("label")


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
	var s := _flat(Color(SURFACE_2, 0.95), Color(GOLD_DARK, 0.8), 56, 2)
	s.shadow_color = Color(0, 0, 0, 0.3)
	s.shadow_size = 12
	s.content_margin_left = 18
	s.content_margin_right = 18
	s.content_margin_top = 18
	s.content_margin_bottom = 18
	return s


static func chip(kind: String, value: String) -> PanelContainer:
	var p := PanelContainer.new()
	var s := _flat(Color(BG, 0.82), Color(GOLD_DARK, 0.6), 30, 2)
	s.content_margin_left = 8
	s.content_margin_right = 18
	s.content_margin_top = 4
	s.content_margin_bottom = 4
	p.add_theme_stylebox_override("panel", s)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)
	var ic := GameIcon.new()
	ic.kind = kind
	ic.custom_minimum_size = Vector2(46, 46)
	h.add_child(ic)
	var l := label(value, 28, TEXT, true)
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
	pb.add_theme_stylebox_override("background", _flat(Color(BG, 0.9), Color(LINE, 0.8), h / 2, 1))
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



# ====================================================================== components
## Card: the base surface for list items and dashboard blocks.
static func card(border := Color(0, 0, 0, 0), pad := SP.m) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := _flat(Color(SURFACE, 0.94), border if border.a > 0 else Color(LINE, 0.9), R.m, 1 if border.a == 0 else 2)
	sb.content_margin_left = pad + 4
	sb.content_margin_right = pad + 4
	sb.content_margin_top = pad
	sb.content_margin_bottom = pad
	p.add_theme_stylebox_override("panel", sb)
	return p


## Section header: title + optional action link on the right.
static func section(text: String, action := "", cb := Callable()) -> HBoxContainer:
	var h := HBoxContainer.new()
	var t := label(text, FS.h3, GOLD, true)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(t)
	if action != "" and cb.is_valid():
		var b := Button.new()
		b.text = action + " ›"
		b.flat = true
		b.focus_mode = Control.FOCUS_NONE
		b.add_theme_font_override("font", FONT_BOLD)
		b.add_theme_font_size_override("font_size", FS.body)
		b.add_theme_color_override("font_color", TEAL)
		b.pressed.connect(cb)
		h.add_child(b)
	return h


## Tabs: equal-width segmented control. Returns the row; cb(key) on change.
static func tabs(items: Array, current: String, cb: Callable, h := 80) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", SP.xs)
	for it in items:
		var key: String = it[0]
		var b := button(String(it[1]), "accent" if key == current else "glass", 0, h)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.add_theme_font_size_override("font_size", FS.caption + 2)
		b.pressed.connect(func(): cb.call(key))
		row.add_child(b)
	return row


## Progress with a centred caption.
static func progress(value: float, max_v: float, caption := "", color := TEAL, h := 30) -> Control:
	var box := Control.new()
	box.custom_minimum_size = Vector2(0, h)
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var pb := bar(value, max_v, color, h)
	pb.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.add_child(pb)
	if caption != "":
		var l := label(caption, FS.caption - 2, Color.WHITE, true)
		l.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		box.add_child(l)
	return box


## Small numeric badge (notifications).
static func badge(n: int) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := _flat(DANGER, Color.WHITE, 16, 2)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	p.add_theme_stylebox_override("panel", sb)
	p.add_child(label(str(n) if n < 100 else "99+", 20, Color.WHITE, true))
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	p.visible = n > 0
	return p


## Rarity tag in the rarity colour.
static func rarity_tag(rarity: int, text: String) -> PanelContainer:
	var p := PanelContainer.new()
	var c: Color = RARITY.get(rarity, MUTED)
	var sb := _flat(Color(c, 0.18), c, 10, 1)
	sb.content_margin_left = 8
	sb.content_margin_right = 8
	p.add_theme_stylebox_override("panel", sb)
	# colour-blind mode: rarity is also encoded as a star count, not only by colour
	p.add_child(label(("★%d " % rarity if colorblind() else "") + text, 22, c, true))
	return p


## Empty / error / locked states: icon, message and an optional action.
static func state(kind: String, text: String, action := "", cb := Callable()) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", SP.m)
	var ic := GameIcon.new()
	ic.kind = {"empty": "quests", "error": "settings", "offline": "settings", "locked": "lock"}.get(kind, "quests")
	ic.custom_minimum_size = Vector2(96, 96)
	ic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	ic.modulate = Color(1, 1, 1, 0.75)
	v.add_child(ic)
	var l := label(text, FS.body, MUTED if kind != "error" else DANGER)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(l)
	if action != "" and cb.is_valid():
		var b := button(action, "glass", 320, 84)
		b.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		b.pressed.connect(cb)
		v.add_child(b)
	return v


## Skeleton placeholder rows shown while a screen loads its data.
static func skeleton(rows := 3, h := 110) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", SP.m)
	for i in rows:
		var p := Panel.new()
		p.custom_minimum_size = Vector2(0, h)
		p.add_theme_stylebox_override("panel", _flat(Color(SURFACE_2, 0.7), Color.TRANSPARENT, R.m, 0))
		v.add_child(p)
		if not reduce_motion():
			var tw := p.create_tween().set_loops()
			tw.tween_property(p, "modulate:a", 0.45, 0.6).set_delay(i * 0.08)
			tw.tween_property(p, "modulate:a", 1.0, 0.6)
	return v


## Smart confirmation (irreversible actions, large spends, purchases). cb runs only on OK.
static func confirm(parent: Node, title_text: String, body: String, ok_text: String, cb: Callable, danger := false) -> void:
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.6)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(dim)
	var p := solid_panel(Color("#ffe1a0"))
	p.anchor_left = 0.5
	p.anchor_right = 0.5
	p.anchor_top = 0.5
	p.anchor_bottom = 0.5
	p.offset_left = -440
	p.offset_right = 440
	p.offset_top = -220
	p.offset_bottom = 220
	p.grow_horizontal = Control.GROW_DIRECTION_BOTH
	p.grow_vertical = Control.GROW_DIRECTION_BOTH
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", SP.l)
	var t := title(title_text, FS.h2)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(t)
	var l := label(body, FS.body)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(l)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", SP.m)
	var cancel := button("Отмена", "glass", 0, 88)
	cancel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cancel.pressed.connect(root.queue_free)
	row.add_child(cancel)
	var ok := button(ok_text, "danger" if danger else "primary", 0, 88)
	ok.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ok.pressed.connect(func(): root.queue_free(); cb.call())
	row.add_child(ok)
	v.add_child(row)
	p.add_child(v)
	root.add_child(p)
	parent.add_child(root)
	pop_in(p)


## Short, predictable entrance animation (skipped with reduced motion).
static func pop_in(c: Control) -> void:
	if reduce_motion() or not is_instance_valid(c):
		return
	c.modulate.a = 0.0
	var tw := c.create_tween()
	tw.tween_property(c, "modulate:a", 1.0, 0.16)


## Icon + caption tile for grouped menus ("Ещё", "Мир").
static func tile(icon: String, caption: String, sub := "", locked := false, badge_n := 0) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(0, 168)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.focus_mode = Control.FOCUS_NONE
	var sb := _flat(Color(SURFACE, 0.95), Color(LINE, 0.9) if locked else Color(GOLD_DARK, 0.6), R.m, 1 if locked else 2)
	var sbh := sb.duplicate() as StyleBoxFlat
	sbh.border_color = GOLD
	var sbp := sb.duplicate() as StyleBoxFlat
	sbp.bg_color = SURFACE_2
	b.add_theme_stylebox_override("normal", sb)
	b.add_theme_stylebox_override("hover", sbh)
	b.add_theme_stylebox_override("pressed", sbp)
	b.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	var v := VBoxContainer.new()
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_theme_constant_override("separation", 4)
	var ic := GameIcon.new()
	ic.kind = "lock" if locked else icon
	ic.custom_minimum_size = Vector2(64, 64)
	ic.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(ic)
	var l := label(caption, FS.body - 2, MUTED if locked else TEXT, true)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	v.add_child(l)
	if sub != "":
		var s2 := label(sub, 20, MUTED)
		s2.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		s2.mouse_filter = Control.MOUSE_FILTER_IGNORE
		v.add_child(s2)
	b.add_child(v)
	if badge_n > 0:
		var bd := badge(badge_n)
		bd.position = Vector2(12, 10)
		b.add_child(bd)
	b.pressed.connect(func(): Sfx.play("open"))
	return b
