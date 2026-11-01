extends Control

## Procedural "dark fantasy" frame: deep teal fill, double gold border, corner diamonds and an optional crest.
## If a texture exists at `texture_path` (artist asset), it is drawn as a 9-slice instead.

@export var fill := Color(0.035, 0.09, 0.105, 0.97)
@export var fill_top := Color(0.06, 0.15, 0.17, 0.97)
@export var gold := Color("#d8a94a")
@export var gold_light := Color("#ffe3a1")
@export var radius := 14.0
@export var crest := false
@export var corners := true
@export var inner := true
var texture_path := ""
var margin := 40


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)
	var tex: Texture2D = null
	if texture_path != "":
		tex = UI.art(texture_path.replace("res://assets/", ""))
		if tex == null and ResourceLoader.exists(texture_path):
			tex = load(texture_path)
	if tex:
		var np := NinePatchRect.new()
		np.texture = tex
		np.patch_margin_left = margin
		np.patch_margin_right = margin
		np.patch_margin_top = margin
		np.patch_margin_bottom = margin
		np.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		np.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(np)


func _draw() -> void:
	if get_child_count() > 0:
		return
	var r := Rect2(Vector2.ZERO, size)
	var sb := StyleBoxFlat.new()
	sb.bg_color = fill
	sb.set_corner_radius_all(int(radius))
	sb.border_color = gold
	sb.set_border_width_all(3)
	sb.anti_aliasing = true
	draw_style_box(sb, r)
	# lighter band at the top: a cheap vertical gradient
	var top := StyleBoxFlat.new()
	top.bg_color = Color(fill_top.r, fill_top.g, fill_top.b, 0.55)
	top.corner_radius_top_left = int(radius)
	top.corner_radius_top_right = int(radius)
	draw_style_box(top, Rect2(Vector2(3, 3), Vector2(size.x - 6, min(size.y * 0.35, 220))))
	if inner and size.x > 40 and size.y > 40:
		var ib := StyleBoxFlat.new()
		ib.draw_center = false
		ib.border_color = Color(gold, 0.45)
		ib.set_border_width_all(1)
		ib.set_corner_radius_all(int(max(2.0, radius - 6)))
		draw_style_box(ib, r.grow(-8))
	if corners:
		for p in [Vector2(10, 10), Vector2(size.x - 10, 10), Vector2(10, size.y - 10), Vector2(size.x - 10, size.y - 10)]:
			_diamond(p, 11)
	if crest:
		_diamond(Vector2(size.x / 2, 0), 16)
		draw_line(Vector2(size.x / 2 - 90, 1), Vector2(size.x / 2 + 90, 1), gold_light, 2.0, true)


func _diamond(c: Vector2, s: float) -> void:
	var pts := PackedVector2Array([c + Vector2(0, -s), c + Vector2(s, 0), c + Vector2(0, s), c + Vector2(-s, 0)])
	draw_colored_polygon(pts, gold)
	var pts2 := PackedVector2Array([c + Vector2(0, -s * 0.5), c + Vector2(s * 0.5, 0), c + Vector2(0, s * 0.5), c + Vector2(-s * 0.5, 0)])
	draw_colored_polygon(pts2, Color("#38e0d0"))
