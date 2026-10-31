class_name Downloader
extends RefCounted
## Resumable chunked downloader: fetches `Range: bytes=a-b` slices and appends them to a
## `.part` file, so an interrupted download continues from where it stopped (even after
## an app restart). Verifies size and streaming SHA-256 before the atomic rename.

const CHUNK := 512 * 1024
const MAX_RETRIES := 5

var host: Node
var cancelled := false


func _init(owner_node: Node) -> void:
	host = owner_node


## Returns {ok, error, resumed_from}
func fetch(url: String, dest: String, size: int, sha256: String, on_progress: Callable) -> Dictionary:
	if FileAccess.file_exists(dest) and sha_file(dest) == sha256:
		on_progress.call(size)
		return {"ok": true, "resumed_from": size, "cached": true}
	var part := dest + ".part"
	var have := 0
	if FileAccess.file_exists(part):
		var pf := FileAccess.open(part, FileAccess.READ)
		have = int(pf.get_length())
		pf.close()
		if have > size:
			DirAccess.remove_absolute(part)
			have = 0
	var resumed_from := have
	on_progress.call(have)
	var retries := 0
	while have < size:
		if cancelled:
			return {"ok": false, "error": "cancelled", "resumed_from": resumed_from}
		var last := mini(have + CHUNK, size) - 1
		var res := await _get_range(url, have, last)
		if not res.ok:
			retries += 1
			if retries > MAX_RETRIES:
				return {"ok": false, "error": "network", "resumed_from": resumed_from}
			await host.get_tree().create_timer(0.5 * pow(2.0, retries - 1), true, false, true).timeout
			continue
		retries = 0
		var body: PackedByteArray = res.body
		if res.status == 200:
			# server ignored Range: it sent the whole file
			if body.size() != size:
				return {"ok": false, "error": "bad_length", "resumed_from": resumed_from}
			_write(part, body, false)
			have = size
		else:
			_write(part, body, true)
			have += body.size()
		on_progress.call(have)
	var digest := sha_file(part)
	if digest != sha256:
		DirAccess.remove_absolute(part)
		return {"ok": false, "error": "hash_mismatch", "resumed_from": resumed_from}
	if FileAccess.file_exists(dest):
		DirAccess.remove_absolute(dest)
	DirAccess.rename_absolute(part, dest)
	return {"ok": true, "resumed_from": resumed_from}


func _get_range(url: String, first: int, last: int) -> Dictionary:
	var req := HTTPRequest.new()
	req.timeout = 20.0
	req.use_threads = true
	host.add_child(req)
	var err := req.request(url, PackedStringArray(["Range: bytes=%d-%d" % [first, last],
		"User-Agent: URALIA-Godot/" + Config.CLIENT_VERSION]))
	if err != OK:
		req.queue_free()
		return {"ok": false}
	var r: Array = await req.request_completed
	req.queue_free()
	if r[0] != HTTPRequest.RESULT_SUCCESS or not (int(r[1]) in [200, 206]):
		return {"ok": false, "status": r[1]}
	return {"ok": true, "status": int(r[1]), "body": r[3]}


func _write(path: String, data: PackedByteArray, append: bool) -> void:
	var f: FileAccess
	if append and FileAccess.file_exists(path):
		f = FileAccess.open(path, FileAccess.READ_WRITE)
		f.seek_end()
	else:
		f = FileAccess.open(path, FileAccess.WRITE)
	f.store_buffer(data)
	f.close()


static func sha_file(path: String) -> String:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return ""
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	while f.get_position() < f.get_length():
		ctx.update(f.get_buffer(256 * 1024))
	f.close()
	return ctx.finish().hex_encode()
