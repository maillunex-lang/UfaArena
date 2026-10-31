class_name ContentUpdater
extends RefCounted
## Uralia Update System — client loader (first slice).
## 1) fetch manifest, 2) verify RSA-SHA256 signature over manifest_raw with the public key,
## 3) honour kill switch / minimum client version, 4) download packages, check size + SHA-256,
## 5) atomic activation (write to .tmp then rename), keep previous version for rollback,
## 6) report install status to the server. Packages are data only — never executed.

const ROOT := "user://content/"


static func run() -> Dictionary:
	var r := await Api._raw("GET", "/api/v1/content/manifest?channel=%s&platform=%s&client_version=%s" % [
		Config.CHANNEL, Config.PLATFORM, Config.CLIENT_VERSION], null, {}, true)
	if not r.ok:
		return {"ok": false, "status": "offline", "message": r.message}
	var raw: String = r.data.get("manifest_raw", "")
	var sig: String = r.data.get("signature", "")
	var pem := Config.public_key_pem()
	var pinned := pem != ""
	if pem == "" and Config.CHANNEL == "dev":
		# DEV ONLY: trust-on-first-use of the server key. Beta/stable builds ship a pinned key.
		var k := await Api.get_raw_bytes("/api/v1/content/public-key")
		pem = k.get_string_from_utf8()
	if not verify(raw, sig, pem):
		return {"ok": false, "status": "signature_invalid", "message": "Подпись манифеста не прошла проверку"}
	var manifest: Dictionary = JSON.parse_string(raw)
	if manifest.get("kill_switch", false):
		return {"ok": false, "status": "kill_switch", "message": "Обновления контента временно отключены"}
	if r.data.get("client_update_required", false):
		return {"ok": false, "status": "client_update_required", "message": "Требуется обновить приложение"}
	var seen := {}
	for pkg in manifest.get("packages", []):
		var res := await _install(pkg)
		seen[pkg.package_id] = res.sha256
		if not res.ok:
			await Api.post_json("/content/verify-install", {"manifest_version": int(manifest.version),
				"channel": Config.CHANNEL, "status": "hash_mismatch", "packages": seen})
			return {"ok": false, "status": "hash_mismatch", "message": "Пакет %s повреждён" % pkg.package_id}
	return {"ok": true, "status": "ok", "manifest": manifest, "pinned_key": pinned, "packages": seen}


static func verify(raw: String, signature_b64: String, pem: String) -> bool:
	if raw == "" or signature_b64 == "" or pem == "":
		return false
	var key := CryptoKey.new()
	if key.load_from_string(pem, true) != OK:
		return false
	var hash := raw.to_utf8_buffer()
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(hash)
	var digest := ctx.finish()
	return Crypto.new().verify(HashingContext.HASH_SHA256, digest, Marshalls.base64_to_raw(signature_b64), key)


static func _install(pkg: Dictionary) -> Dictionary:
	var dir := ROOT + String(pkg.package_id) + "/"
	DirAccess.make_dir_recursive_absolute(dir)
	var final_path := dir + "%d.bin" % int(pkg.version)
	if FileAccess.file_exists(final_path):
		var existing := FileAccess.get_file_as_bytes(final_path)
		if _sha(existing) == pkg.sha256:
			return {"ok": true, "sha256": pkg.sha256, "cached": true}
	var data := await Api.get_raw_bytes(String(pkg.url))
	var digest := _sha(data)
	if data.size() != int(pkg.size) or digest != String(pkg.sha256):
		return {"ok": false, "sha256": digest}
	var tmp := final_path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	f.store_buffer(data)
	f.close()
	DirAccess.rename_absolute(tmp, final_path)  # atomic activation
	var active := ConfigFile.new()
	active.load(ROOT + "active.cfg")
	active.set_value(pkg.package_id, "previous", active.get_value(pkg.package_id, "current", 0))
	active.set_value(pkg.package_id, "current", int(pkg.version))
	active.save(ROOT + "active.cfg")
	return {"ok": true, "sha256": digest, "cached": false}


static func _sha(data: PackedByteArray) -> String:
	var ctx := HashingContext.new()
	ctx.start(HashingContext.HASH_SHA256)
	ctx.update(data)
	return ctx.finish().hex_encode()


## Roll a package back to the previously active version (kept on disk).
static func rollback(package_id: String) -> bool:
	var active := ConfigFile.new()
	if active.load(ROOT + "active.cfg") != OK:
		return false
	var prev: int = active.get_value(package_id, "previous", 0)
	if prev <= 0 or not FileAccess.file_exists(ROOT + package_id + "/%d.bin" % prev):
		return false
	active.set_value(package_id, "current", prev)
	active.save(ROOT + "active.cfg")
	return true
