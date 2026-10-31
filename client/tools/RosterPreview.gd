extends Node3D
## Lineup of the HERO FORGE roster + summons (visual check of looks, scale and palettes).
const CODES := ["arslan_kara", "bai_tash", "safariy", "ai_tulgan", "yurek", "sumbel", "ak_bure", "tan_chechek",
	"vargat", "morai", "zarkhan", "ur_kaan", "root_guardian", "dragon_echo_small", "dragon_echo"]
func _ready() -> void:
	Hex.environment(self)
	Hex.sun(self)
	for i in CODES.size():
		var a := Models.spawn(CODES[i])
		var row := i / 5
		a.position = Vector3((i % 5) * 2.4 - 4.8, 0, row * 3.2 - 3.2)
		add_child(a)
		var l := Label3D.new()
		l.text = CODES[i]
		l.font_size = 40
		l.pixel_size = 0.006
		l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		l.position = a.position + Vector3(0, -0.15, 0.9)
		add_child(l)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(20, 14)
	ground.mesh = pm
	add_child(ground)
	var cam := Camera3D.new()
	cam.position = Vector3(0, 7.5, 12)
	add_child(cam)
	cam.look_at(Vector3(0, 0.8, 0))
	cam.fov = 50
	cam.current = true
