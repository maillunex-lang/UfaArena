extends Node
## Uralia Update System — client (autoload `Content`).
##
## check()          fetch + verify the signed manifest (RSA-SHA256 over manifest_raw)
## sync(required)   download packages (resumable, free-space check, SHA-256) into the blob cache
## apply_pending()  validate archives and atomically switch the active set (state.json via tmp+rename);
##                  keeps the previous set for rollback; reports the result to the server
## start_background() downloads optional packages while the player plays; they are applied
##                  at the next safe point (Main -> home screen)
##
## Packages are ZIPs of data only (glb/png/jpg/webp/ogg/json/txt). Nothing is executed:
## models load through GLTFDocument, images through Image, audio through AudioStreamOggVorbis.
## Later packages in dependency order override files of earlier ones (e.g. looks/gulnaz.json).

signal state_changed(state: String, info: String)
signal progress(done: int, total: int)
signal activated(manifest_version: int)
signal pending_ready(manifest_version: int)

const ROOT := "user://content/"
const BLOBS := ROOT + "blobs/"
const STATE := ROOT + "state.json"
const ALLOWED := ["json", "glb", "png", "jpg", "jpeg", "webp", "ogg", "txt", "md"]
const SPACE_MARGIN := 32 * 1024 * 1024
const POLL_INTERVAL_S := 15 * 60

var state := "idle"
var manifest := {}
var active := {}    # {manifest_version, channel, packages: [{package_id, version, sha256, kind, title}]}
var previous := {}
var pending := {}
var kill_switch := false
var client_update_required := false
var background_enabled := true
var last_error := ""
var _readers := {}  # package_id -> ZIPReader
var _index := {}    # file path -> package_id (last wins)
var _gltf_cache := {}
var _tex_cache := {}
var _dl: Downloader
var _bg_running := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	DirAccess.make_dir_recursive_absolute(BLOBS)
	_load_state()
	_mount(active)
	var t := Timer.new()
	t.wait_time = POLL_INTERVAL_S
	t.autostart = true
	t.timeout.connect(func(): if Game.loaded: poll_now())
	add_child(t)


## Re-checks the manifest during play and fetches new content in the background.
func poll_now() -> Dictionary:
	if state == "downloading" or state == "checking":
		return {"ok": false, "status": "busy"}
	var c := await check()
	if c.ok and c.status == "ok" and not up_to_date():
		await start_background()
	return c


# ------------------------------------------------------------------ persistence
func _load_state() -> void:
	if not FileAccess.file_exists(STATE):
		return
	var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(STATE))
	if d is Dictionary:
		active = d.get("active", {})
		previous = d.get("previous", {})
		pending = d.get("pending", {})
		background_enabled = d.get("background_enabled", true)


func _save_state() -> void:
	var tmp := STATE + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	f.store_string(JSON.stringify({"active": active, "previous": previous, "pending": pending,
		"background_enabled": background_enabled}))
	f.close()
	DirAccess.rename_absolute(tmp, STATE)  # atomic switch


func _blob(sha: String) -> String:
	return BLOBS + sha + ".zip"


func _set_state(s: String, info := "") -> void:
	state = s
	state_changed.emit(s, info)


# ------------------------------------------------------------------ manifest
func check() -> Dictionary:
	_set_state("checking")
	var q := "/api/v1/content/manifest?channel=%s&platform=%s&client_version=%s" % [
		Config.CHANNEL, Config.PLATFORM, Config.CLIENT_VERSION]
	var r := await Api._raw("GET", q, null, {}, true)
	if not r.ok:
		_set_state("offline")
		return {"ok": false, "status": "offline", "message": r.message}
	var raw: String = r.data.get("manifest_raw", "")
	var pem := Config.public_key_pem()
	if pem == "" and Config.CHANNEL == "dev":
		pem = (await Api.get_raw_bytes("/api/v1/content/public-key")).get_string_from_utf8()  # DEV ONLY (TOFU)
	if not verify_signature(raw, r.data.get("signature", ""), pem):
		_set_state("error", "signature")
		return {"ok": false, "status": "signature_invalid", "message": "Подпись манифеста не прошла проверку"}
	manifest = JSON.parse_string(raw)
	client_update_required = r.data.get("client_update_required", false)
	kill_switch = manifest.get("kill_switch", false)
	if kill_switch:
		# Remote kill switch: stop delivering and fall back to built-in content.
		if not active.is_empty():
			previous = active
			active = {}
			_save_state()
			_mount(active)
			await _report("kill_switch", {})
			activated.emit(0)
		_set_state("disabled", "kill_switch")
		return {"ok": true, "status": "kill_switch"}
	if client_update_required:
		_set_state("error", "client_update_required")
		return {"ok": false, "status": "client_update_required", "message": "Требуется обновить приложение"}
	_set_state("ready")
	return {"ok": true, "status": "ok", "missing_required": missing(true), "missing_optional": missing(false)}


static func verify_signature(raw: String, signature_b64: String, pem: String) -> bool:
	if raw == "" or signature_b64 == "" or pem == "":
		return false
	var key := CryptoKey.new()
	if key.load_from_string(pem, true) != OK:
		return false
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(raw.to_utf8_buffer())
	return Crypto.new().verify(HashingContext.HASH_SHA256, ctx.finish(), Marshalls.base64_to_raw(signature_b64), key)


func up_to_date() -> bool:
	return not manifest.is_empty() and int(active.get("manifest_version", -1)) == int(manifest.version) \
		and active.get("channel", "") == manifest.channel


static func _ver(v: String) -> Array:
	var out := []
	for x in v.split("."):
		out.append(int(x))
	return out


## Packages this client can use: skips ones needing a newer client (and anything depending on them).
func usable_packages() -> Array:
	var ok_ids := {}
	var out := []
	for p in manifest.get("packages", []):  # server sends dependency order
		var fits: bool = _ver(String(p.get("min_client_version", "0.1.0"))) <= _ver(Config.CLIENT_VERSION)
		for d in p.get("dependencies", []):
			fits = fits and ok_ids.has(d)
		if fits:
			ok_ids[p.package_id] = true
			out.append(p)
	return out


## Usable packages not yet in the blob cache (required ones or all).
func missing(required_only: bool) -> Array:
	var out := []
	for p in usable_packages():
		if required_only and not p.get("required", false):
			continue
		if not FileAccess.file_exists(_blob(p.sha256)):
			out.append(p)
	return out


func bytes_to_download(pkgs: Array) -> int:
	var n := 0
	for p in pkgs:
		n += int(p.size)
	return n


# ------------------------------------------------------------------ download
func sync(required_only: bool) -> Dictionary:
	if manifest.is_empty() or kill_switch:
		return {"ok": false, "status": "no_manifest"}
	var pkgs := missing(required_only)
	var total := bytes_to_download(pkgs)
	var free := DirAccess.open("user://").get_space_left()
	if total > 0 and free > 0 and free < total + SPACE_MARGIN:
		last_error = "no_space"
		_set_state("error", "no_space")
		await _report("no_space", {"need": total, "free": free})
		return {"ok": false, "status": "no_space", "message": "Недостаточно места: нужно %.1f МБ" % (total / 1048576.0)}
	_set_state("downloading")
	_dl = Downloader.new(self)
	var done_before := 0
	var resumed := 0
	for p in pkgs:
		var base := done_before
		var url: String = p.url if String(p.url).begins_with("http") else Config.server_url + String(p.url)
		var res := await _dl.fetch(url, _blob(p.sha256), int(p.size), String(p.sha256),
			func(n: int): progress.emit(base + n, total))
		resumed += int(res.get("resumed_from", 0))
		if not res.ok:
			last_error = res.error
			_set_state("error", res.error)
			if res.error == "hash_mismatch":
				await _report("hash_mismatch", {"package": p.package_id})
			return {"ok": false, "status": res.error, "message": "Загрузка прервана: %s" % res.error}
		done_before += int(p.size)
	# everything the manifest needs is cached -> stage it as pending
	if missing(false).is_empty():
		pending = _set_from_manifest()
		_save_state()
		pending_ready.emit(int(manifest.version))
	_set_state("ready")
	return {"ok": true, "status": "ok", "downloaded": total, "resumed_bytes": resumed}


func _set_from_manifest() -> Dictionary:
	var pk := []
	for p in usable_packages():
		pk.append({"package_id": p.package_id, "version": int(p.version), "sha256": p.sha256, "kind": p.kind,
			"title": p.get("title", p.package_id)})
	return {"manifest_version": int(manifest.version), "channel": manifest.channel, "packages": pk}


func start_background() -> void:
	if _bg_running or not background_enabled or manifest.is_empty() or kill_switch:
		return
	if up_to_date() and pending.is_empty():
		return
	_bg_running = true
	var r := await sync(false)
	_bg_running = false
	if not r.ok and r.status != "cancelled":
		Router.toast("Фоновая загрузка контента приостановлена — продолжим позже", true)


# ------------------------------------------------------------------ activation / rollback
func has_pending() -> bool:
	return not pending.is_empty() and int(pending.get("manifest_version", -1)) != int(active.get("manifest_version", -2))


## Validates every archive, then atomically makes `pending` active. On failure keeps the
## current set (automatic rollback) and reports it.
func apply_pending() -> bool:
	if not has_pending():
		pending = {}
		return false
	for p in pending.packages:
		var err := _validate_zip(_blob(p.sha256), p.package_id, int(p.version))
		if err != "":
			var bad_sha := String(p.sha256)
			DirAccess.remove_absolute(_blob(bad_sha))
			pending = {}
			_save_state()
			await _report("rolled_back", {"package": p.package_id, "error": err})
			Router.toast("Пакет %s отклонён (%s) — оставлена прежняя версия" % [p.package_id, err], true)
			return false
	previous = active
	active = pending
	pending = {}
	_save_state()
	_mount(active)
	_gc()
	await _report("ok", {})
	activated.emit(int(active.manifest_version))
	return true


func rollback() -> bool:
	if previous.is_empty():
		return false
	for p in previous.get("packages", []):
		if not FileAccess.file_exists(_blob(p.sha256)):
			return false
	var cur := active
	active = previous
	previous = cur
	_save_state()
	_mount(active)
	await _report("rolled_back", {"manual": true})
	activated.emit(int(active.get("manifest_version", 0)))
	return true


func set_background(on: bool) -> void:
	background_enabled = on
	_save_state()


func _report(status: String, details: Dictionary) -> void:
	if Api.access_token == "" and Api.refresh_token == "":
		return
	var seen := {}
	var src := active if status == "ok" else pending if not pending.is_empty() else active
	for p in src.get("packages", []):
		seen[p.package_id] = p.sha256
	await Api.post_json("/content/verify-install", {"manifest_version": int(manifest.get("version", src.get("manifest_version", 0))),
		"channel": Config.CHANNEL, "status": status, "packages": seen if status == "ok" else {}, "details": details})


func _validate_zip(path: String, package_id: String, version: int) -> String:
	var z := ZIPReader.new()
	if z.open(path) != OK:
		return "zip"
	var files := z.get_files()
	if not files.has("package.json"):
		z.close()
		return "no_package_json"
	for f in files:
		if f.ends_with("/"):
			continue
		if f.begins_with("/") or f.contains("..") or f.contains("\\") or not (f.get_extension().to_lower() in ALLOWED):
			z.close()
			return "forbidden_file:" + f
	var meta: Variant = JSON.parse_string(z.read_file("package.json").get_string_from_utf8())
	z.close()
	if not (meta is Dictionary) or meta.get("package_id", "") != package_id or int(meta.get("version", 0)) != version:
		return "meta_mismatch"
	return ""


func _mount(set_: Dictionary) -> void:
	for r in _readers.values():
		(r as ZIPReader).close()
	_readers.clear()
	_index.clear()
	_gltf_cache.clear()
	_tex_cache.clear()
	for p in set_.get("packages", []):
		var z := ZIPReader.new()
		if z.open(_blob(p.sha256)) != OK:
			continue
		_readers[p.package_id] = z
		for f in z.get_files():
			_index[f] = p.package_id


func _gc() -> void:
	var keep := {}
	for s in [active, previous, pending]:
		for p in s.get("packages", []):
			keep[p.sha256 + ".zip"] = true
	for f in DirAccess.get_files_at(BLOBS):
		if f.ends_with(".zip") and not keep.has(f):
			DirAccess.remove_absolute(BLOBS + f)


# ------------------------------------------------------------------ asset access
func has(path: String) -> bool:
	return _index.has(path)


func list(prefix: String) -> Array:
	var out := []
	for f in _index:
		if String(f).begins_with(prefix):
			out.append(f)
	return out


func bytes(path: String) -> PackedByteArray:
	if not _index.has(path):
		return PackedByteArray()
	return (_readers[_index[path]] as ZIPReader).read_file(path)


func json(path: String) -> Variant:
	if not has(path):
		return null
	return JSON.parse_string(bytes(path).get_string_from_utf8())


func texture(path: String) -> Texture2D:
	if _tex_cache.has(path):
		return _tex_cache[path]
	if not has(path):
		return null
	var img := Image.new()
	var b := bytes(path)
	var err := ERR_FILE_UNRECOGNIZED
	# by file signature, not extension: the admin panel stores JPEG uploads under the slot's .png name
	if b.size() > 3 and b[0] == 0x89 and b[1] == 0x50:
		err = img.load_png_from_buffer(b)
	elif b.size() > 3 and b[0] == 0xFF and b[1] == 0xD8:
		err = img.load_jpg_from_buffer(b)
	elif b.size() > 12 and b.slice(8, 12).get_string_from_ascii() == "WEBP":
		err = img.load_webp_from_buffer(b)
	if err != OK:
		return null
	var t := ImageTexture.create_from_image(img)
	_tex_cache[path] = t
	return t


func audio(path: String) -> AudioStream:
	if not has(path) or path.get_extension().to_lower() != "ogg":
		return null
	return AudioStreamOggVorbis.load_from_buffer(bytes(path))


## Instantiates a glTF binary model from a package (runtime import, no code execution).
func model(path: String) -> Node3D:
	if not has(path):
		return null
	var st: GLTFState = _gltf_cache.get(path)
	var doc := GLTFDocument.new()
	if st == null:
		st = GLTFState.new()
		if doc.append_from_buffer(bytes(path), "", st) != OK:
			return null
		_gltf_cache[path] = st
	return doc.generate_scene(st) as Node3D


func summary() -> String:
	if kill_switch:
		return "Контент-обновления отключены (kill switch)"
	var v := int(active.get("manifest_version", 0))
	var names := []
	for p in active.get("packages", []):
		names.append("%s v%d" % [p.package_id, int(p.version)])
	return "Манифест v%d (%s): %s" % [v, Config.CHANNEL, ", ".join(names) if names.size() > 0 else "только встроенный контент"]


## Settings → «Очистить кэш»: drops decoded package textures (decoded again on demand).
func clear_texture_cache() -> int:
	var n := _tex_cache.size()
	_tex_cache.clear()
	return n
