# UE5 Scene Building Knowledge Base

## Coordinate System
- Left-handed: X=Forward, Y=Right, Z=Up
- Units: centimeters
- Rotator: (Pitch, Yaw, Roll) in degrees
- Pitch = look up/down, Yaw = turn left/right, Roll = tilt sideways

## Preferred APIs (UE5.7)
- **EditorActorSubsystem** (use this, not deprecated EditorLevelLibrary):
  ```python
  subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
  actor = subsys.spawn_actor_from_class(cls, location)
  actors = subsys.get_all_level_actors()
  subsys.destroy_actor(actor)
  ```
- **ScopedEditorTransaction** for undo support (mandatory for all mutations):
  ```python
  with unreal.ScopedEditorTransaction('description') as t:
      actor.set_actor_location(new_loc, False, False)
  ```
- **EditorAssetLibrary** for loading assets:
  ```python
  mesh = unreal.EditorAssetLibrary.load_asset('/Game/Path/To/Asset')
  ```

## Common Operations
- **Line trace**: `unreal.SystemLibrary.line_trace_single(world, start, end, trace_type, False, [], draw_debug, True)` — returns (bool, FHitResult) in UE5.7
- **Actor bounds**: `actor.get_actor_bounds(False)` → (origin_Vector, extent_Vector)
- **Set transform**: `actor.set_actor_location()`, `actor.set_actor_rotation()`, `actor.set_actor_scale3d()`
- **Folder organization**: `actor.set_folder_path('Agent_Placed/zone_name')`

## SceneCapture2D
- Capture source: `SCS_FINAL_TONE_CURVE_HDR` (tone-mapped, works with RGBA8)
- Exposure: Scene uses manual exposure bias -0.5; capture component needs +3.0 override
- Render target format: `RTF_RGBA8` for PNG export
- `export_render_target()` does NOT add file extension — must rename after export
- Lumen overrides on capture component:
  ```python
  pp.set_editor_property('override_dynamic_global_illumination_method', True)
  pp.set_editor_property('dynamic_global_illumination_method', DynamicGlobalIlluminationMethod.LUMEN)
  ```

## Megaplant Tree Species (SkeletalMesh)
| Species | Variants | Path Prefix |
|---------|----------|-------------|
| Beech   | A, B     | /Game/Megaplant_Library/Tree_European_Beech/ |
| Maple   | A, B     | /Game/Megaplant_Library/Tree_Norway_Maple/ |
| Alder   | A, B     | /Game/Megaplant_Library/Tree_Black_Alder/ |
| Aspen   | A, B     | /Game/Megaplant_Library/Tree_European_Aspen/ |
| Hazel   | A, B     | /Game/Megaplant_Library/Tree_Common_Hazel/ |

- Trees are **SkeletalMeshActor** (not StaticMesh)
- Set mesh: `comp.set_skinned_asset_and_update(mesh)` (UE5.7)
- Rocks are StaticMesh: `/Game/Megaplant_Library/Mossy_Rocks/Mossy_Rocks_tjmudcfda_High`

## Known UE5.7 Property Name Differences
- `enable_volumetric_fog` (not `volumetric_fog`)
- `fog_inscattering_luminance` (not `fog_inscattering_color`)
- `lower_hemisphere_is_black` (not `lower_hemisphere_is_solid_color`)
- `directional_inscattering_luminance` (not `directional_inscattering_color`)

## VRAM Budget (RTX 3060 Ti, 8GB)
- UE5.7 + Lumen + Nanite: 6-7.5GB typical
- SceneCapture2D at 960x540: ~200-500MB additional
- Use software Lumen (not hardware RT) to avoid BVH memory overhead
- Monitor with `stat RHI` in console

## Composition Rules for Forest Scenes
- Layer hierarchy: terrain → ground_cover → low_vegetation (0-50cm) → mid_vegetation (50-300cm) → canopy_support (300-1500cm) → canopy (1500-3000cm+) → atmosphere
- Never place in uniform grids — use asymmetric fractal patterns
- Primary clusters: 3-7 trees, secondary: 2-4, tertiary: 1-2 singles
- Minimum 3 tree species per zone
- Full 360° random yaw, scale 0.75-1.25x, ±5° random lean
- Edge transitions: 500-2000cm gradual, never hard borders
- Rocks: partially buried (-3 to -10cm Z offset)

## TCP Bridge Protocol
- Port: 127.0.0.1:9876
- Send: `python_code\n__END__\n`
- Receive: `{"success": bool, "output": str, "error": str}`
- Structured return data: `unreal.log('AGENT_JSON:' + json.dumps(data))`
- Execution context globals: `{unreal, __builtins__, __name__: "__remote__"}`
