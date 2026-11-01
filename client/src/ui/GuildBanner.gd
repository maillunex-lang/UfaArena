extends Control
## Guild banner (знамя): gold rod with finials, cloth with a swallowtail, gold trim and an emblem silhouette.
## An uploaded image at art/guild/banner_<emblem>.png (admin panel) replaces the drawing.

const COLORS := {"wolf": Color("#1d5c5a"), "bear": Color("#8e2420"), "eagle": Color("#1f3f8a"), "tree": Color("#5b2a86"),
	"horse": Color("#245e2a"), "stone": Color("#4a5260")}
var emblem := "wolf":
	set(v):
		emblem = v
		queue_redraw()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _draw() -> void:
	var art := UI.art("guild/banner_%s.png" % emblem)
	if art:
		draw_texture_rect(art, Rect2(Vector2.ZERO, size), false)
		return
	var w := size.x
	var h := size.y
	var gold := Color("#e6b452")
	var dark := Color("#6e4a12")
	# rod with finials
	draw_rect(Rect2(Vector2(w * 0.06, h * 0.04), Vector2(w * 0.88, h * 0.035)), gold)
	for x in [w * 0.06, w * 0.94]:
		draw_circle(Vector2(x, h * 0.058), w * 0.05, gold)
	_diamond(Vector2(w * 0.5, h * 0.035), w * 0.07, gold)
	# cloth with swallowtail
	var cloth := PackedVector2Array([Vector2(w * 0.14, h * 0.08), Vector2(w * 0.86, h * 0.08), Vector2(w * 0.86, h * 0.86),
		Vector2(w * 0.5, h * 0.74), Vector2(w * 0.14, h * 0.86)])
	draw_colored_polygon(cloth, COLORS.get(emblem, COLORS.wolf))
	draw_polyline(cloth + PackedVector2Array([cloth[0]]), gold, max(2.0, w * 0.035), true)
	var inner := PackedVector2Array([Vector2(w * 0.21, h * 0.12), Vector2(w * 0.79, h * 0.12), Vector2(w * 0.79, h * 0.79),
		Vector2(w * 0.5, h * 0.69), Vector2(w * 0.21, h * 0.79)])
	draw_polyline(inner + PackedVector2Array([inner[0]]), Color(gold, 0.45), max(1.0, w * 0.012), true)
	_diamond(Vector2(w * 0.5, h * 0.7), w * 0.06, Color("#38e0d0"))
	_emblem(Vector2(w * 0.5, h * 0.4), w * 0.24, Color("#f6dfa0"), dark)


func _diamond(c: Vector2, s: float, col: Color) -> void:
	draw_colored_polygon(PackedVector2Array([c + Vector2(0, -s), c + Vector2(s, 0), c + Vector2(0, s), c + Vector2(-s, 0)]), col)


func _emblem(c: Vector2, r: float, col: Color, edge: Color) -> void:
	var p := PackedVector2Array()
	match emblem:
		"wolf":
			p = PackedVector2Array([c + Vector2(-0.8, -0.9) * r, c + Vector2(-0.35, -0.35) * r, c + Vector2(0.35, -0.35) * r,
				c + Vector2(0.8, -0.9) * r, c + Vector2(0.75, 0.1) * r, c + Vector2(0.25, 0.9) * r, c + Vector2(-0.25, 0.9) * r,
				c + Vector2(-0.75, 0.1) * r])
		"bear":
			draw_circle(c + Vector2(-0.6, -0.6) * r, r * 0.3, col)
			draw_circle(c + Vector2(0.6, -0.6) * r, r * 0.3, col)
			draw_circle(c, r * 0.8, col)
			draw_circle(c + Vector2(0, 0.25) * r, r * 0.3, edge)
			return
		"eagle":
			p = PackedVector2Array([c + Vector2(0, -0.9) * r, c + Vector2(0.25, -0.3) * r, c + Vector2(1.0, -0.6) * r,
				c + Vector2(0.6, 0.2) * r, c + Vector2(0.2, 0.2) * r, c + Vector2(0.35, 0.9) * r, c + Vector2(0, 0.6) * r,
				c + Vector2(-0.35, 0.9) * r, c + Vector2(-0.2, 0.2) * r, c + Vector2(-0.6, 0.2) * r, c + Vector2(-1.0, -0.6) * r,
				c + Vector2(-0.25, -0.3) * r])
		"tree":
			draw_rect(Rect2(c + Vector2(-0.12, 0.1) * r, Vector2(0.24, 0.85) * r), col)
			for o in [Vector2(0, -0.45), Vector2(-0.45, -0.1), Vector2(0.45, -0.1), Vector2(-0.25, -0.65), Vector2(0.25, -0.65)]:
				draw_circle(c + o * r, r * 0.35, col)
			return
		"horse":
			p = PackedVector2Array([c + Vector2(-0.2, -0.95) * r, c + Vector2(0.15, -0.7) * r, c + Vector2(0.7, -0.2) * r,
				c + Vector2(0.75, 0.15) * r, c + Vector2(0.45, 0.2) * r, c + Vector2(0.1, -0.05) * r, c + Vector2(0.2, 0.9) * r,
				c + Vector2(-0.6, 0.9) * r, c + Vector2(-0.5, -0.3) * r])
		_:
			p = PackedVector2Array([c + Vector2(-0.95, 0.8) * r, c + Vector2(-0.3, -0.6) * r, c + Vector2(0, -0.1) * r,
				c + Vector2(0.35, -0.9) * r, c + Vector2(0.95, 0.8) * r])
	draw_colored_polygon(p, col)
	draw_polyline(p + PackedVector2Array([p[0]]), edge, max(1.5, r * 0.06), true)
