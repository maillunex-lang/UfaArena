extends Node3D
## Offline preview of the battle stage (no server): units at formation / contact positions.
func _ready() -> void:
	var a: Node3D = load("res://src/world/Arena.gd").new()
	add_child(a)
	a.build(OS.get_environment("PREVIEW_TERRITORY") if OS.get_environment("PREVIEW_TERRITORY") != "" else "nature", false)
	var team := ["azamat", "burebai", "gulnaz", "zulfiya", "ramil"]
	var foes := ["e_warrior", "e_minion", "e_mage", "e_rogue", "e_mage"]
	var pos := {0: Vector2(-1.0, -0.9), 1: Vector2(-1.0, 0.9), 2: Vector2(-4.4, -1.8), 3: Vector2(-4.6, 0.0), 4: Vector2(-4.4, 1.8)}
	for i in 5:
		var p: Vector2 = pos[i]
		a.add_unit({"uid": "p%d" % i, "side": 0, "slot": i, "code": team[i], "level": 5, "rarity": 3, "hp": 100, "max_hp": 100, "x": p.x, "z": p.y})
		a.add_unit({"uid": "e%d" % i, "side": 1, "slot": i, "code": foes[i], "level": 5, "rarity": 2, "hp": 70, "max_hp": 100, "x": -p.x, "z": p.y})
