@tool
class_name GameIcon
extends Control
## Resolution-independent vector icons (original artwork drawn in code):
## currencies + navigation. Ornaments echo Bashkir «кустым»/tulip motifs.

@export var kind := "gold":
	set(v):
		kind = v
		queue_redraw()


func _ready() -> void:
	resized.connect(queue_redraw)


func _draw() -> void:
	var s: float = min(size.x, size.y)
	var c := size / 2.0
	var r := s * 0.46
	match kind:
		"gold": _coin(c, r, Color("#ffd35c"), Color("#b87914"))
		"crystals": _gem(c, r, Color("#7fe3ff"), Color("#2a7fd4"))
		"summon_essence": _orb(c, r, Color("#d59bff"), Color("#5b2aa8"))
		"ancient_seals": _seal(c, r)
		"guild_marks": _shield(c, r, Color("#9fd18b"), Color("#3a6e2e"))
		"nature_essence": _leaf(c, r)
		"campaign": _flag(c, r)
		"heroes": _helmet(c, r)
		"fortress": _castle(c, r)
		"summon": _star(c, r, Color("#ffe08a"), Color("#c46cff"))
		"modes": _swords(c, r)
		"quests": _scroll(c, r)
		"mail": _envelope(c, r)
		"settings": _gear(c, r)
		"afk": _chest(c, r)
		"events": _star(c, r, Color("#ffb38a"), Color("#ff6a6a"))
		"friends": _people(c, r)
		"chat": _chat_bubble(c, r)
		"guild": _shield(c, r, Color("#a8c8ff"), Color("#2b4f8f"))
		"shop": _bag(c, r)
		"arena": _swords(c, r)
		"profile": _people(c, r)
		"lock": _lock(c, r)
		"stone_sky": _em_stone_sky(c, r)
		"living_kurai": _em_living_kurai(c, r)
		"ashen_reach": _em_ashen_reach(c, r)
		"shulgan": _em_shulgan(c, r)
		_: draw_circle(c, r, Color.WHITE)


func _ring(c: Vector2, r: float, col: Color, w: float) -> void:
	draw_arc(c, r, 0, TAU, 48, col, w, true)


func _coin(c: Vector2, r: float, a: Color, b: Color) -> void:
	draw_circle(c + Vector2(0, r * 0.08), r, b.darkened(0.3))
	draw_circle(c, r, b)
	draw_circle(c, r * 0.86, a)
	_ring(c, r * 0.68, b, r * 0.08)
	_tulip(c, r * 0.5, b)
	draw_circle(c + Vector2(-r * 0.35, -r * 0.4), r * 0.14, Color(1, 1, 1, 0.6))


func _tulip(c: Vector2, r: float, col: Color) -> void:
	var pts := PackedVector2Array([c + Vector2(0, -r), c + Vector2(r * 0.55, -r * 0.2), c + Vector2(r * 0.25, r * 0.7),
		c + Vector2(0, r * 0.35), c + Vector2(-r * 0.25, r * 0.7), c + Vector2(-r * 0.55, -r * 0.2)])
	draw_colored_polygon(pts, col)


func _gem(c: Vector2, r: float, a: Color, b: Color) -> void:
	var top := PackedVector2Array([c + Vector2(-r * 0.9, -r * 0.25), c + Vector2(-r * 0.45, -r * 0.8),
		c + Vector2(r * 0.45, -r * 0.8), c + Vector2(r * 0.9, -r * 0.25)])
	var full := PackedVector2Array([top[0], top[1], top[2], top[3], c + Vector2(0, r * 0.95)])
	draw_colored_polygon(full, b)
	draw_colored_polygon(PackedVector2Array([top[0], top[1], top[2], top[3]]), a)
	draw_colored_polygon(PackedVector2Array([top[0], c + Vector2(0, r * 0.95), c + Vector2(-r * 0.2, -r * 0.25)]),
		a.lerp(b, 0.4))
	draw_polyline(PackedVector2Array([top[0], top[1], top[2], top[3], c + Vector2(0, r * 0.95), top[0]]),
		Color(1, 1, 1, 0.8), r * 0.06, true)
	draw_circle(c + Vector2(-r * 0.25, -r * 0.55), r * 0.1, Color(1, 1, 1, 0.9))


func _orb(c: Vector2, r: float, a: Color, b: Color) -> void:
	for i in 5:
		draw_circle(c, r * (1.0 - i * 0.12), Color(a.r, a.g, a.b, 0.12 + i * 0.05))
	draw_circle(c, r * 0.62, b)
	draw_circle(c, r * 0.5, a)
	draw_arc(c, r * 0.32, 0.3, 3.6, 24, Color.WHITE, r * 0.08, true)
	draw_circle(c + Vector2(-r * 0.2, -r * 0.22), r * 0.1, Color(1, 1, 1, 0.9))


func _seal(c: Vector2, r: float) -> void:
	var pts := PackedVector2Array()
	for i in 16:
		var ang := TAU * i / 16.0
		pts.append(c + Vector2.from_angle(ang) * (r if i % 2 == 0 else r * 0.86))
	draw_colored_polygon(pts, Color("#b8463c"))
	draw_circle(c, r * 0.66, Color("#d9634f"))
	_ring(c, r * 0.5, Color("#ffd9a0"), r * 0.07)
	draw_line(c + Vector2(0, -r * 0.35), c + Vector2(0, r * 0.35), Color("#ffd9a0"), r * 0.09)
	draw_line(c + Vector2(-r * 0.25, -r * 0.1), c + Vector2(r * 0.25, -r * 0.1), Color("#ffd9a0"), r * 0.09)


func _shield(c: Vector2, r: float, a: Color, b: Color) -> void:
	var pts := PackedVector2Array([c + Vector2(-r * 0.8, -r * 0.8), c + Vector2(r * 0.8, -r * 0.8),
		c + Vector2(r * 0.75, r * 0.1), c + Vector2(0, r * 0.95), c + Vector2(-r * 0.75, r * 0.1)])
	draw_colored_polygon(pts, b)
	var inner := PackedVector2Array()
	for p in pts:
		inner.append(c + (p - c) * 0.78)
	draw_colored_polygon(inner, a)
	_tulip(c + Vector2(0, -r * 0.05), r * 0.38, b)


func _leaf(c: Vector2, r: float) -> void:
	var pts := PackedVector2Array()
	for i in 25:
		var t := float(i) / 24.0
		var ang := lerpf(-PI / 2, PI * 1.5, t)
		var w := sin(t * PI)
		pts.append(c + Vector2(cos(ang) * r * 0.62 * w, sin(ang) * r * 0.95))
	draw_colored_polygon(pts, Color("#4fc46a"))
	draw_line(c + Vector2(0, -r * 0.8), c + Vector2(0, r * 0.95), Color("#c9ffb8"), r * 0.08)
	for k in [-0.35, 0.0, 0.35]:
		draw_line(c + Vector2(0, r * k), c + Vector2(r * 0.35, r * (k - 0.25)), Color("#c9ffb8"), r * 0.06)
		draw_line(c + Vector2(0, r * k), c + Vector2(-r * 0.35, r * (k - 0.25)), Color("#c9ffb8"), r * 0.06)


func _flag(c: Vector2, r: float) -> void:
	draw_line(c + Vector2(-r * 0.6, -r * 0.9), c + Vector2(-r * 0.6, r * 0.95), Color("#f3e3c0"), r * 0.12)
	var pts := PackedVector2Array([c + Vector2(-r * 0.55, -r * 0.85), c + Vector2(r * 0.85, -r * 0.6),
		c + Vector2(r * 0.5, -r * 0.3), c + Vector2(r * 0.85, 0), c + Vector2(-r * 0.55, 0)])
	draw_colored_polygon(pts, Color("#3c8fe0"))
	draw_colored_polygon(PackedVector2Array([c + Vector2(-r * 0.55, -r * 0.4), c + Vector2(r * 0.62, -r * 0.4),
		c + Vector2(r * 0.72, -r * 0.2), c + Vector2(-r * 0.55, -r * 0.2)]), Color("#ffffff"))
	draw_circle(c + Vector2(r * 0.1, -r * 0.3), r * 0.11, Color("#ffd35c"))
	draw_colored_polygon(PackedVector2Array([c + Vector2(-r * 0.55, -r * 0.2), c + Vector2(r * 0.72, -r * 0.2),
		c + Vector2(r * 0.85, 0), c + Vector2(-r * 0.55, 0)]), Color("#3fa95a"))


func _helmet(c: Vector2, r: float) -> void:
	draw_circle(c + Vector2(0, r * 0.1), r * 0.75, Color("#c9d4e6"))
	draw_rect(Rect2(c + Vector2(-r * 0.8, r * 0.1), Vector2(r * 1.6, r * 0.75)), Color("#c9d4e6"))
	draw_rect(Rect2(c + Vector2(-r * 0.55, r * 0.05), Vector2(r * 1.1, r * 0.18)), Color("#33405a"))
	draw_rect(Rect2(c + Vector2(-r * 0.08, r * 0.05), Vector2(r * 0.16, r * 0.7)), Color("#33405a"))
	draw_colored_polygon(PackedVector2Array([c + Vector2(0, -r), c + Vector2(r * 0.18, -r * 0.55),
		c + Vector2(-r * 0.18, -r * 0.55)]), Color("#e05a4f"))


func _castle(c: Vector2, r: float) -> void:
	var stone := Color("#d8cdb8")
	draw_rect(Rect2(c + Vector2(-r * 0.85, -r * 0.2), Vector2(r * 1.7, r * 1.1)), stone)
	for x in [-0.85, -0.3, 0.3]:
		draw_rect(Rect2(c + Vector2(r * x, -r * 0.4), Vector2(r * 0.3, r * 0.22)), stone)
	draw_rect(Rect2(c + Vector2(-r * 0.25, -r * 0.85), Vector2(r * 0.5, r * 0.7)), stone.darkened(0.08))
	draw_colored_polygon(PackedVector2Array([c + Vector2(-r * 0.32, -r * 0.82), c + Vector2(0, -r * 1.1),
		c + Vector2(r * 0.32, -r * 0.82)]), Color("#3c8fe0"))
	draw_rect(Rect2(c + Vector2(-r * 0.2, r * 0.35), Vector2(r * 0.4, r * 0.55)), Color("#5b3a22"))


func _star(c: Vector2, r: float, a: Color, b: Color) -> void:
	for i in 4:
		draw_circle(c, r * (1.0 - i * 0.15), Color(b.r, b.g, b.b, 0.12))
	var pts := PackedVector2Array()
	for i in 10:
		var ang := -PI / 2 + TAU * i / 10.0
		pts.append(c + Vector2.from_angle(ang) * (r * 0.9 if i % 2 == 0 else r * 0.38))
	draw_colored_polygon(pts, a)
	draw_polyline(pts + PackedVector2Array([pts[0]]), Color.WHITE, r * 0.05, true)


func _swords(c: Vector2, r: float) -> void:
	for sgn in [-1.0, 1.0]:
		var a := c + Vector2(-r * 0.75 * sgn, r * 0.75)
		var b := c + Vector2(r * 0.7 * sgn, -r * 0.8)
		draw_line(a, b, Color("#e7eef8"), r * 0.16)
		var g := a.lerp(b, 0.25)
		var perp := (b - a).normalized().orthogonal() * r * 0.28
		draw_line(g - perp, g + perp, Color("#ffd35c"), r * 0.13)
		draw_circle(a, r * 0.1, Color("#ffd35c"))


func _scroll(c: Vector2, r: float) -> void:
	draw_rect(Rect2(c + Vector2(-r * 0.6, -r * 0.75), Vector2(r * 1.2, r * 1.5)), Color("#f1dfb4"))
	draw_circle(c + Vector2(-r * 0.6, -r * 0.75), r * 0.16, Color("#c9a86a"))
	draw_circle(c + Vector2(r * 0.6, -r * 0.75), r * 0.16, Color("#c9a86a"))
	draw_circle(c + Vector2(-r * 0.6, r * 0.75), r * 0.16, Color("#c9a86a"))
	draw_circle(c + Vector2(r * 0.6, r * 0.75), r * 0.16, Color("#c9a86a"))
	for i in 4:
		draw_line(c + Vector2(-r * 0.38, -r * 0.4 + i * r * 0.27), c + Vector2(r * 0.38, -r * 0.4 + i * r * 0.27),
			Color("#8a6a3a"), r * 0.07)


func _envelope(c: Vector2, r: float) -> void:
	var rect := Rect2(c + Vector2(-r * 0.85, -r * 0.55), Vector2(r * 1.7, r * 1.15))
	draw_rect(rect, Color("#f4efe4"))
	draw_colored_polygon(PackedVector2Array([rect.position, rect.position + Vector2(rect.size.x, 0),
		c + Vector2(0, r * 0.15)]), Color("#d8cfbd"))
	draw_circle(c + Vector2(0, r * 0.12), r * 0.18, Color("#c9463c"))


func _gear(c: Vector2, r: float) -> void:
	var pts := PackedVector2Array()
	for i in 32:
		var ang := TAU * i / 32.0
		pts.append(c + Vector2.from_angle(ang) * (r * 0.9 if (i / 2) % 2 == 0 else r * 0.7))
	draw_colored_polygon(pts, Color("#c9d4e6"))
	draw_circle(c, r * 0.3, Color("#33405a"))


func _chest(c: Vector2, r: float) -> void:
	draw_rect(Rect2(c + Vector2(-r * 0.85, -r * 0.1), Vector2(r * 1.7, r * 0.85)), Color("#8a5326"))
	draw_circle(c + Vector2(0, -r * 0.1), r * 0.85, Color("#a8652e"), true)
	draw_rect(Rect2(c + Vector2(-r * 0.9, -r * 0.15), Vector2(r * 1.8, r * 0.16)), Color("#ffd35c"))
	draw_rect(Rect2(c + Vector2(-r * 0.15, -r * 0.2), Vector2(r * 0.3, r * 0.4)), Color("#ffd35c"))
	draw_rect(Rect2(c + Vector2(-r * 1.0, r * 0.72), Vector2(r * 2.0, r * 0.2)), Color(0, 0, 0, 0))
	for i in 3:
		draw_circle(c + Vector2(-r * 0.4 + i * r * 0.4, -r * 0.6), r * 0.12, Color(1, 0.95, 0.6, 0.9))


func _people(c: Vector2, r: float) -> void:
	draw_circle(c + Vector2(-r * 0.35, -r * 0.3), r * 0.28, Color("#c9d4e6"))
	draw_circle(c + Vector2(r * 0.35, -r * 0.35), r * 0.3, Color("#f1dfb4"))
	draw_circle(c + Vector2(-r * 0.35, r * 0.55), r * 0.5, Color("#c9d4e6"))
	draw_circle(c + Vector2(r * 0.35, r * 0.55), r * 0.55, Color("#f1dfb4"))


func _bag(c: Vector2, r: float) -> void:
	draw_circle(c + Vector2(0, r * 0.25), r * 0.7, Color("#c98a3c"))
	draw_rect(Rect2(c + Vector2(-r * 0.3, -r * 0.65), Vector2(r * 0.6, r * 0.35)), Color("#a8652e"))
	_tulip(c + Vector2(0, r * 0.3), r * 0.32, Color("#ffd35c"))


func _lock(c: Vector2, r: float) -> void:
	draw_arc(c + Vector2(0, -r * 0.2), r * 0.42, PI, TAU, 24, Color("#c9d4e6"), r * 0.16, true)
	draw_rect(Rect2(c + Vector2(-r * 0.6, -r * 0.2), Vector2(r * 1.2, r * 0.95)), Color("#c9d4e6"))
	draw_circle(c + Vector2(0, r * 0.25), r * 0.14, Color("#33405a"))


# ------------------------------------------------------------------ faction emblems (original vector art)
func _medallion(c: Vector2, r: float, rim: Color, fill: Color) -> void:
	var pts := PackedVector2Array()
	for i in 6:
		pts.append(c + Vector2.from_angle(-PI / 2 + TAU * i / 6.0) * r)
	draw_colored_polygon(pts, rim)
	var inner := PackedVector2Array()
	for p in pts:
		inner.append(c + (p - c) * 0.84)
	draw_colored_polygon(inner, fill)


## Каменное Небо: twin peaks under a star, geometric mountain ornament, graphite / turquoise / amber
func _em_stone_sky(c: Vector2, r: float) -> void:
	_medallion(c, r, Color("#e0a64a"), Color("#2e3338"))
	draw_colored_polygon(PackedVector2Array([c + Vector2(-r * 0.62, r * 0.42), c + Vector2(-r * 0.18, -r * 0.3),
		c + Vector2(r * 0.05, r * 0.05), c + Vector2(r * 0.25, -r * 0.45), c + Vector2(r * 0.66, r * 0.42)]), Color("#5a6672"))
	draw_colored_polygon(PackedVector2Array([c + Vector2(-r * 0.18, -r * 0.3), c + Vector2(-r * 0.05, -r * 0.1),
		c + Vector2(-r * 0.3, -r * 0.1)]), Color("#d8e2e6"))
	draw_colored_polygon(PackedVector2Array([c + Vector2(r * 0.25, -r * 0.45), c + Vector2(r * 0.4, -r * 0.2),
		c + Vector2(r * 0.12, -r * 0.2)]), Color("#d8e2e6"))
	draw_line(c + Vector2(-r * 0.55, r * 0.5), c + Vector2(r * 0.55, r * 0.5), Color("#5fb8b0"), r * 0.09)
	_star4(c + Vector2(0, -r * 0.62), r * 0.17, Color("#5fb8b0"))


## Живой Курай: kurai flute crossed by a sprouting leaf, moss green / ochre / amber
func _em_living_kurai(c: Vector2, r: float) -> void:
	_medallion(c, r, Color("#d6a24e"), Color("#2c3d22"))
	draw_line(c + Vector2(-r * 0.15, r * 0.62), c + Vector2(r * 0.18, -r * 0.62), Color("#c9a26a"), r * 0.16)
	for k in [-0.25, 0.0, 0.25]:
		draw_circle(c + Vector2(r * 0.015 + r * k * -0.26, r * k * -2.0 * 0.5), r * 0.05, Color("#5a3d1e"))
	var leaf := PackedVector2Array()
	for i in 17:
		var t := float(i) / 16.0
		var w := sin(t * PI) * r * 0.24
		var p := Vector2(lerpf(-r * 0.55, r * 0.15, t), lerpf(r * 0.2, -r * 0.35, t))
		leaf.append(c + p + Vector2(0.6, 0.8) * w)
	for i in range(16, -1, -1):
		var t := float(i) / 16.0
		var w := sin(t * PI) * r * 0.24
		var p := Vector2(lerpf(-r * 0.55, r * 0.15, t), lerpf(r * 0.2, -r * 0.35, t))
		leaf.append(c + p - Vector2(0.6, 0.8) * w)
	draw_colored_polygon(leaf, Color("#7cb860"))
	draw_circle(c + Vector2(r * 0.4, -r * 0.42), r * 0.1, Color("#f2c46a"))


## Пепельный Предел: obsidian shard split by an amber rift, ash / burgundy / violet
func _em_ashen_reach(c: Vector2, r: float) -> void:
	_medallion(c, r, Color("#7a2536"), Color("#16141a"))
	var shard := PackedVector2Array([c + Vector2(0, -r * 0.7), c + Vector2(r * 0.38, -r * 0.05),
		c + Vector2(r * 0.12, r * 0.68), c + Vector2(-r * 0.3, r * 0.3), c + Vector2(-r * 0.36, -r * 0.2)])
	draw_colored_polygon(shard, Color("#4b3a5c"))
	draw_polyline(PackedVector2Array([c + Vector2(-r * 0.05, -r * 0.62), c + Vector2(r * 0.08, -r * 0.2),
		c + Vector2(-r * 0.08, r * 0.05), c + Vector2(r * 0.06, r * 0.55)]), Color("#e3a33c"), r * 0.08, true)
	draw_circle(c + Vector2(-r * 0.5, -r * 0.5), r * 0.06, Color("#a35bc9"))
	draw_circle(c + Vector2(r * 0.5, r * 0.45), r * 0.05, Color("#a35bc9"))


func _em_shulgan(c: Vector2, r: float) -> void:
	_medallion(c, r, Color("#5b2aa8"), Color("#1a1024"))
	draw_circle(c, r * 0.35, Color("#d9d2e6"))
	draw_circle(c + Vector2(-r * 0.12, -r * 0.03), r * 0.08, Color("#1a1024"))
	draw_circle(c + Vector2(r * 0.12, -r * 0.03), r * 0.08, Color("#1a1024"))


func _star4(c: Vector2, r: float, col: Color) -> void:
	draw_colored_polygon(PackedVector2Array([c + Vector2(0, -r), c + Vector2(r * 0.3, -r * 0.3), c + Vector2(r, 0),
		c + Vector2(r * 0.3, r * 0.3), c + Vector2(0, r), c + Vector2(-r * 0.3, r * 0.3), c + Vector2(-r, 0),
		c + Vector2(-r * 0.3, -r * 0.3)]), col)


func _chat_bubble(c: Vector2, r: float) -> void:
	var rect := Rect2(c.x - r * 0.95, c.y - r * 0.75, r * 1.9, r * 1.25)
	draw_rect(rect, Color("#2b4f8f"), true)
	draw_rect(rect.grow(-r * 0.08), Color("#bfe3ff"), true)
	draw_colored_polygon(PackedVector2Array([Vector2(c.x - r * 0.45, c.y + r * 0.45), Vector2(c.x - r * 0.1, c.y + r * 0.45),
		Vector2(c.x - r * 0.55, c.y + r * 0.95)]), Color("#bfe3ff"))
	for i in 3:
		draw_circle(Vector2(c.x - r * 0.5 + i * r * 0.5, c.y - r * 0.12), r * 0.13, Color("#2b4f8f"))
