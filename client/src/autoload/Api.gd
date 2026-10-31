extends Node
## Network layer: JSON over HTTPS, bearer auth with transparent refresh, retries with
## exponential backoff that REUSE the same Idempotency-Key (so a retried reward
## claim can never be applied twice), and an offline signal for the UI.

signal offline_changed(is_offline: bool)
signal session_lost

const SESSION_PATH := "user://session.cfg"
const TIMEOUT_S := 12.0
const MAX_RETRIES := 3

var access_token := ""
var refresh_token := ""
var user_id := ""
var is_offline := false
var _refreshing := false


func _ready() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SESSION_PATH) == OK:
		refresh_token = cfg.get_value("auth", "refresh_token", "")
		user_id = cfg.get_value("auth", "user_id", "")


func has_session() -> bool:
	return refresh_token != ""


func _save_session() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("auth", "refresh_token", refresh_token)
	cfg.set_value("auth", "user_id", user_id)
	cfg.save(SESSION_PATH)


func clear_session() -> void:
	access_token = ""
	refresh_token = ""
	user_id = ""
	_save_session()


func _apply_tokens(data: Dictionary) -> void:
	access_token = data.get("access_token", "")
	refresh_token = data.get("refresh_token", refresh_token)
	user_id = data.get("user_id", user_id)
	_save_session()


static func new_key() -> String:
	var c := Crypto.new()
	return c.generate_random_bytes(16).hex_encode()


# --------------------------------------------------------------------- auth
## Restores the stored session. Without one returns code "need_login": Boot then asks the
## player to start a new guest game or to sign in by email (never silently replaces an account).
func login() -> Dictionary:
	if refresh_token != "":
		var r := await refresh()
		if r.ok:
			return r
		if r.status != 401:
			return r  # offline or server error: keep the stored session for later
	return {"ok": false, "status": 401, "code": "need_login", "message": "Нужен вход", "data": {}}


func login_guest() -> Dictionary:
	var device := OS.get_unique_id()
	if device.length() < 8:
		device = "dev-" + new_key()
	var g := await _raw("POST", "/api/v1/auth/guest", {"device_id": device.sha256_text().substr(0, 40),
		"client_version": Config.CLIENT_VERSION}, {}, true)
	if g.ok:
		_apply_tokens(g.data)
	return g


func login_email(email: String, password: String) -> Dictionary:
	var r := await _raw("POST", "/api/v1/auth/login", {"email": email.strip_edges().to_lower(),
		"password": password}, {}, true)
	if r.ok:
		_apply_tokens(r.data)
	return r


func refresh() -> Dictionary:
	var r := await _raw("POST", "/api/v1/auth/refresh", {"refresh_token": refresh_token}, {}, true)
	if r.ok:
		_apply_tokens(r.data)
	elif r.status == 401:
		clear_session()
	return r


# --------------------------------------------------------------------- public API
func get_json(path: String) -> Dictionary:
	return await call_api("GET", path, null, false)


## idempotent: false | true (fresh key for this call) | String (caller-owned key, reuse across user retries)
func post_json(path: String, body: Variant = {}, idempotent: Variant = false) -> Dictionary:
	return await call_api("POST", path, body, idempotent)


func call_api(method: String, path: String, body: Variant, idempotent: Variant) -> Dictionary:
	var headers := {}
	if idempotent is String and idempotent != "":
		headers["Idempotency-Key"] = idempotent
	elif idempotent is bool and idempotent:
		headers["Idempotency-Key"] = new_key()  # generated once, reused by every retry below
	var r := await _with_auth(method, "/api/v1" + path, body, headers)
	return r


func _with_auth(method: String, path: String, body: Variant, headers: Dictionary) -> Dictionary:
	if access_token == "" and refresh_token != "":
		await refresh()
	headers["Authorization"] = "Bearer " + access_token
	var r := await _raw(method, path, body, headers, false)
	if r.status == 401 and r.code in ["token_expired", "token_invalid", "session_revoked"]:
		var rr := await refresh()
		if not rr.ok:
			if rr.status == 401:
				session_lost.emit()
			return r
		headers["Authorization"] = "Bearer " + access_token
		r = await _raw(method, path, body, headers, false)
	return r


func _raw(method: String, path: String, body: Variant, headers: Dictionary, quiet: bool) -> Dictionary:
	var attempt := 0
	var result := {}
	while true:
		result = await _once(method, path, body, headers)
		if result.status != 0 and result.status < 500:
			break
		attempt += 1
		if attempt > MAX_RETRIES:
			break
		await get_tree().create_timer(0.6 * pow(2.0, attempt - 1)).timeout
	var offline_now: bool = result.status == 0
	if offline_now != is_offline and not quiet:
		is_offline = offline_now
		offline_changed.emit(is_offline)
	elif not offline_now and is_offline:
		is_offline = false
		offline_changed.emit(false)
	return result


func _once(method: String, path: String, body: Variant, headers: Dictionary) -> Dictionary:
	var req := HTTPRequest.new()
	req.timeout = TIMEOUT_S
	req.use_threads = true
	add_child(req)
	var h := PackedStringArray(["Content-Type: application/json", "Accept: application/json",
		"User-Agent: URALIA-Godot/" + Config.CLIENT_VERSION])
	for k in headers:
		h.append("%s: %s" % [k, headers[k]])
	var m := HTTPClient.METHOD_GET if method == "GET" else HTTPClient.METHOD_POST
	var payload := "" if body == null else JSON.stringify(body)
	var err := req.request(Config.server_url + path, h, m, payload)
	if err != OK:
		req.queue_free()
		return {"ok": false, "status": 0, "code": "network", "message": "Нет соединения", "data": {}}
	var res: Array = await req.request_completed
	req.queue_free()
	var status: int = res[1]
	if res[0] != HTTPRequest.RESULT_SUCCESS:
		return {"ok": false, "status": 0, "code": "network", "message": "Нет соединения с сервером", "data": {}}
	var text: String = (res[3] as PackedByteArray).get_string_from_utf8()
	var data: Variant = JSON.parse_string(text) if text != "" else {}
	if data == null:
		data = {"raw": text}
	if status >= 200 and status < 300:
		return {"ok": true, "status": status, "code": "", "message": "", "data": data}
	var detail: Variant = data.get("detail", {}) if data is Dictionary else {}
	var code := ""
	var msg := "Ошибка сервера (%d)" % status
	if detail is Dictionary:
		code = detail.get("code", "")
		msg = detail.get("message", msg)
	return {"ok": false, "status": status, "code": code, "message": msg, "data": data}


func get_raw_bytes(path: String) -> PackedByteArray:
	var req := HTTPRequest.new()
	req.timeout = TIMEOUT_S
	add_child(req)
	var err := req.request(Config.server_url + path)
	if err != OK:
		req.queue_free()
		return PackedByteArray()
	var res: Array = await req.request_completed
	req.queue_free()
	if res[0] != HTTPRequest.RESULT_SUCCESS or res[1] != 200:
		return PackedByteArray()
	return res[3]
