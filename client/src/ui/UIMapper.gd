extends Node
## Interface map for the admin panel: visits every screen, collects its buttons and texts (caption + position) and a
## screenshot, and uploads them (only a player marked as «картограф» in the admin panel may upload). The admin then
## edits any button of any screen on the real picture. Dev mode: `out_dir` saves the files locally instead.

signal finished(count: int)

const SCREENS := ["home", "heroes", "formation", "summon", "campaign", "caravan", "quests", "mail", "shop", "chat",
	"friends", "guild", "raids", "arena", "tournaments", "events", "rankings", "world", "more", "profile", "inventory",
	"settings"]
const UIOverrides := preload("res://src/ui/UIOverrides.gd")

var main: Node
var out_dir := ""


func run() -> void:
	var n := 0
	for s in SCREENS:
		if not main.SCREENS.has(s):
			continue
		main.open(s)
		await get_tree().create_timer(2.6, true, false, true).timeout
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.resize(540, int(540.0 * img.get_height() / img.get_width()), Image.INTERPOLATE_BILINEAR)
		var jpg := img.save_jpg_to_buffer(0.72)
		await _send(s, collect(main.screen, null), jpg)
		if s == "home":  # the shell around all screens (top bar)
			await _send("main", collect(main.ui, main.content), jpg)
		n += 1
		if out_dir == "":
			Router.toast("Карта интерфейса: %d из %d" % [n, SCREENS.size()])
	main.open("settings")
	finished.emit(n)


func collect(root: Node, skip: Node) -> Array:
	var vp := get_viewport().get_visible_rect().size
	var out := {}
	var order := []
	_walk(root, skip, vp, out, order)
	var arr := []
	for k in order:
		arr.append(out[k])
	return arr


func _walk(n: Node, skip: Node, vp: Vector2, out: Dictionary, order: Array) -> void:
	for c in n.get_children():
		if c == skip:
			continue
		var kind := "button" if c is Button else ("label" if c is Label else "")
		if kind != "" and (c as Control).is_visible_in_tree():
			var key := UIOverrides.key_of(c)
			var r := (c as Control).get_global_rect()
			if key != "" and r.size.x >= 4 and r.size.y >= 4 and r.end.y > 0 and r.position.y < vp.y:
				var id := kind + "|" + key
				if out.has(id):
					out[id].count += 1
				else:
					var text: String = (c as Button).text if c is Button else (c as Label).text
					if text.strip_edges() == "" and c is Button:
						var l := UIOverrides.first_label(c)
						text = l.text if l else (c as Button).tooltip_text
					out[id] = {"key": key, "kind": kind, "text": text.left(120), "count": 1,
						"rect": [r.position.x / vp.x, r.position.y / vp.y, r.size.x / vp.x, r.size.y / vp.y]}
					order.append(id)
		if not (c is Button):  # texts inside a button belong to the button
			_walk(c, skip, vp, out, order)


func _send(screen: String, elements: Array, jpg: PackedByteArray) -> void:
	if out_dir != "":
		var f := FileAccess.open(out_dir + "/" + screen + ".json", FileAccess.WRITE)
		f.store_string(JSON.stringify({"screen": screen, "elements": elements, "at": Time.get_datetime_string_from_system(true),
			"by": "bundled", "client": Config.CLIENT_VERSION}))
		f.close()
		var g := FileAccess.open(out_dir + "/" + screen + ".jpg", FileAccess.WRITE)
		g.store_buffer(jpg)
		g.close()
		print("UIMAP: ", screen, " ", elements.size())
		return
	await Api.post_json("/client/ui-map", {"screen": screen, "elements": elements,
		"image_b64": Marshalls.raw_to_base64(jpg), "client": Config.CLIENT_VERSION})
