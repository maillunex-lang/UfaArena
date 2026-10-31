extends Node
## Adaptive graphics: auto-detects a quality tier and applies render scale, MSAA,
## shadows, glass blur and particle density. Users can override in Settings.

signal quality_changed(tier: String)

const TIERS := {
	"low": {"scale": 0.67, "msaa": Viewport.MSAA_DISABLED, "shadows": false, "blur": false, "particles": 0.35, "fps": 30},
	"medium": {"scale": 0.85, "msaa": Viewport.MSAA_2X, "shadows": true, "blur": true, "particles": 0.7, "fps": 60},
	"high": {"scale": 1.0, "msaa": Viewport.MSAA_4X, "shadows": true, "blur": true, "particles": 1.0, "fps": 60},
}

var tier := "medium"


func _ready() -> void:
	apply()


func detect() -> String:
	var cores := OS.get_processor_count()
	var adapter := RenderingServer.get_video_adapter_name().to_lower()
	if cores <= 4 or adapter.contains("mali-4") or adapter.contains("adreno (tm) 3"):
		return "low"
	if cores >= 8 and (adapter.contains("adreno (tm) 7") or adapter.contains("mali-g7") or OS.get_name() != "Android"):
		return "high"
	return "medium"


func apply() -> void:
	var q: String = Config.settings.get("graphics_quality", "auto")
	tier = detect() if q == "auto" else q
	var t: Dictionary = TIERS[tier]
	var vp := get_viewport()
	vp.scaling_3d_scale = t.scale
	vp.msaa_3d = t.msaa
	Engine.max_fps = t.fps
	quality_changed.emit(tier)


func setting(key: String) -> Variant:
	return TIERS[tier][key]


func setup_light(light: DirectionalLight3D) -> void:
	light.shadow_enabled = setting("shadows")
