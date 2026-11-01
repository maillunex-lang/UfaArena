extends Control
## World map (brief §10: map + catalogue): campaign regions placed at their real locations in the Southern Urals,
## connected in story order. Node colour = state (locked / in progress / completed), ring = world-event status
## (liberated / scorched). Tap a region → its campaign chapter. Background: admin slot ui/world_map.png (1024×768).

signal region_pressed(index: int)

## Approximate geographic placement (0..1, north up) of each region code.
const POS := {"r1_shikhany": Vector2(0.43, 0.55), "r2_iremel": Vector2(0.74, 0.42), "r3_shulgantash": Vector2(0.58, 0.70),
	"r4_nugush": Vector2(0.38, 0.72), "r5_yangantau": Vector2(0.64, 0.22), "r6_ufa_plateau": Vector2(0.40, 0.25),
	"r7_zilair": Vector2(0.60, 0.89)}

var regions: Array = []
var _rects: Array = []


func _init() -> void:
	custom_minimum_size = Vector2(0, 640)
	mouse_filter = Control.MOUSE_FILTER_STOP
	resized.connect(queue_redraw)


func set_regions(r: Array) -> void:
	regions = r
	queue_redraw()


func _pos(i: int) -> Vector2:
	var code := String(regions[i].get("code", ""))
	var p: Vector2 = POS.get(code, Vector2(0.15 + 0.7 * float(i) / maxf(1, regions.size() - 1), 0.5))
	return Vector2(p.x * size.x, p.y * size.y)


func _draw() -> void:
	var rect := Rect2(Vector2.ZERO, size)
	var bg := UI.art("ui/world_map.png")
	if bg:
		draw_texture_rect(bg, rect, false)
	else:
		draw_rect(rect, Color("#0f2328"))
		# stylised terrain: Ural ridge (east), Agidel / Belaya river, steppe south
		for k in 11:  # mountain peaks of the Ural ridge along the east
			var y := size.y * (0.06 + k * 0.088)
			var x := size.x * (0.74 + 0.05 * sin(k * 1.7))
			var hgt := size.y * (0.07 + 0.025 * fmod(k * 0.37, 1.0))
			var wdt := size.x * 0.07
			draw_colored_polygon(PackedVector2Array([Vector2(x - wdt, y + hgt * 0.5), Vector2(x, y - hgt * 0.5), Vector2(x + wdt, y + hgt * 0.5)]),
				Color(0.32, 0.42, 0.46, 0.55))
			draw_colored_polygon(PackedVector2Array([Vector2(x - wdt * 0.25, y - hgt * 0.25), Vector2(x, y - hgt * 0.5), Vector2(x + wdt * 0.25, y - hgt * 0.25)]),
				Color(0.85, 0.9, 0.92, 0.5))
		draw_rect(Rect2(0, size.y * 0.86, size.x, size.y * 0.14), Color(0.55, 0.5, 0.3, 0.12))  # steppe in the south
		var river := PackedVector2Array([Vector2(size.x * 0.62, size.y * 0.95), Vector2(size.x * 0.52, size.y * 0.75),
			Vector2(size.x * 0.47, size.y * 0.58), Vector2(size.x * 0.44, size.y * 0.40), Vector2(size.x * 0.36, size.y * 0.18),
			Vector2(size.x * 0.30, size.y * 0.02)])
		draw_polyline(river, Color(0.25, 0.7, 0.75, 0.55), 6.0, true)
		draw_rect(rect, Color(UI.GOLD_DARK, 0.6), false, 3.0)
	if regions.is_empty():
		return
	_rects.clear()
	for i in range(regions.size() - 1):
		var done: bool = _cleared(i) >= regions[i].nodes.size() and regions[i].nodes.size() > 0
		draw_dashed_line(_pos(i), _pos(i + 1), Color(UI.GOLD, 0.8) if done else Color(1, 1, 1, 0.3), 4.0, 14.0, true)
	var font := UI.FONT_BOLD
	for i in regions.size():
		var reg: Dictionary = regions[i]
		var p := _pos(i)
		var n: int = reg.nodes.size()
		var open: bool = n > 0 and bool(reg.nodes[0].unlocked)
		var done := _cleared(i)
		var col := UI.GOLD if (n > 0 and done >= n) else (UI.TEAL if open else Color(0.4, 0.45, 0.48))
		var st = reg.get("world_status")
		if st:
			draw_arc(p, 40, 0, TAU, 40, UI.ok_color() if st == "liberated" else UI.bad_color(), 6, true)
		draw_circle(p, 30, Color(UI.BG, 0.9))
		draw_arc(p, 30, 0, TAU, 40, col, 5, true)
		if n > 0 and open:
			draw_arc(p, 22, -PI / 2, -PI / 2 + TAU * float(done) / n, 32, col, 8, true)
		var num := str(i + 1)
		draw_string(font, p + Vector2(-9 if num.length() == 1 else -16, 11), num, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, UI.TEXT)
		var label := String(reg.name)
		var w := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 24).x
		var lp := p + Vector2(-w / 2, 64)
		lp.x = clampf(lp.x, 6, size.x - w - 6)
		draw_rect(Rect2(lp + Vector2(-6, -24), Vector2(w + 12, 32)), Color(0, 0, 0, 0.55))
		draw_string(font, lp, label, HORIZONTAL_ALIGNMENT_LEFT, -1, 24, UI.TEXT if open else UI.MUTED)
		_rects.append(Rect2(p - Vector2(48, 48), Vector2(96, 120)))


func _cleared(i: int) -> int:
	var c := 0
	for nd in regions[i].nodes:
		c += int(nd.cleared)
	return c


func _gui_input(e: InputEvent) -> void:
	var pressed: bool = (e is InputEventMouseButton and e.pressed and e.button_index == MOUSE_BUTTON_LEFT) or (e is InputEventScreenTouch and e.pressed)
	if not pressed:
		return
	for i in _rects.size():
		if (_rects[i] as Rect2).has_point(e.position):
			var reg: Dictionary = regions[i]
			if reg.nodes.size() > 0 and bool(reg.nodes[0].unlocked):
				Sfx.play("click")
				region_pressed.emit(i)
			else:
				Router.toast("Регион «%s» откроется после прохождения предыдущей главы" % reg.name)
			accept_event()
			return
