"""
TuneLighting.py - Configure directional light for god rays, SkyLight for
ambient bounce, and add a PostProcessVolume for eerie color grading.

Run via:  python ue_bridge.py --file Extras/TuneLighting.py
  or:    Tools > Execute Python Script > this file
"""
import unreal

EL = unreal.EditorLevelLibrary
actors = EL.get_all_level_actors()

# ============================================================
#  FIND EXISTING LIGHTING ACTORS
# ============================================================
dir_light = None
sky_light = None
fog_actor = None
sky_atmo = None
pp_volume = None

for actor in actors:
    cls = actor.get_class().get_name()
    label = actor.get_actor_label()
    if "DirectionalLight" in cls:
        dir_light = actor
    elif "SkyLight" in cls:
        sky_light = actor
    elif "ExponentialHeightFog" in cls:
        fog_actor = actor
    elif "SkyAtmosphere" in cls:
        sky_atmo = actor
    elif "PostProcessVolume" in cls:
        pp_volume = actor

# ============================================================
#  1) DIRECTIONAL LIGHT - GOD RAYS CONFIGURATION
# ============================================================
unreal.log("")
unreal.log("=" * 60)
unreal.log("  TUNING DIRECTIONAL LIGHT FOR GOD RAYS")
unreal.log("=" * 60)

if dir_light:
    # Low sun angle: pitch ~ -25 degrees gives long shafts through canopy
    # Yaw ~ -160 for side-lighting that reveals depth
    dir_light.set_actor_rotation(unreal.Rotator(-25.0, -160.0, 0.0), False)
    unreal.log(f"  Rotation set: Pitch=-25, Yaw=-160 (low angled sun)")

    lc = dir_light.light_component
    props = {
        # Core light settings
        "intensity": 8.0,                          # Lux - moderate for forest
        "light_color": unreal.Color(255, 235, 200, 255),  # Warm golden
        "use_temperature": True,
        "temperature": 5200.0,                     # Slightly warm daylight

        # Atmospheric / god ray settings
        "atmosphere_sun_light": True,
        "atmosphere_sun_light_index": 0,           # Primary sun
        "volumetric_scattering_intensity": 3.0,    # KEY: drives god ray visibility
        "light_source_angle": 1.5,                 # Slightly soft for natural look

        # Shadow settings for tree canopy shafts
        "cast_shadows": True,
        "indirect_lighting_intensity": 1.2,

        # Cloud interaction
        "cast_cloud_shadows": True,
        "cloud_shadow_strength": 0.3,
    }
    for prop, val in props.items():
        try:
            lc.set_editor_property(prop, val)
            unreal.log(f"  {prop} = {val}")
        except Exception as e:
            unreal.log_warning(f"  Could not set {prop}: {e}")
else:
    unreal.log_warning("  DirectionalLight not found!")

# ============================================================
#  2) SKYLIGHT - FOREST AMBIENT BOUNCE
# ============================================================
unreal.log("")
unreal.log("=" * 60)
unreal.log("  TUNING SKYLIGHT FOR FOREST BOUNCE")
unreal.log("=" * 60)

if sky_light:
    slc = sky_light.light_component
    sky_props = {
        "intensity": 2.5,                          # Subtle ambient fill
        "volumetric_scattering_intensity": 0.5,    # Some scatter from sky
        "indirect_lighting_intensity": 1.0,
        "real_time_capture": True,                  # Update from sky atmosphere
        "lower_hemisphere_is_solid_color": True,
        "lower_hemisphere_color": unreal.LinearColor(0.02, 0.04, 0.02, 1.0),  # Dark green ground bounce
    }
    for prop, val in sky_props.items():
        try:
            slc.set_editor_property(prop, val)
            unreal.log(f"  {prop} = {val}")
        except Exception as e:
            unreal.log_warning(f"  Could not set {prop}: {e}")
else:
    unreal.log_warning("  SkyLight not found!")

# ============================================================
#  3) ENHANCE VOLUMETRIC FOG FOR GOD RAY INTERACTION
# ============================================================
unreal.log("")
unreal.log("=" * 60)
unreal.log("  ENHANCING VOLUMETRIC FOG FOR GOD RAYS")
unreal.log("=" * 60)

if fog_actor:
    fc = fog_actor.component
    fog_props = {
        # Base fog - keep subtle for forest
        "fog_density": 0.015,
        "fog_height_falloff": 0.12,
        "fog_max_opacity": 0.6,
        "start_distance": 200.0,
        "fog_cutoff_distance": 0.0,                # No cutoff

        # Inscattering color - slightly warm/amber for light shafts
        "fog_inscattering_color": unreal.LinearColor(0.08, 0.06, 0.04, 1.0),

        # Directional inscattering - brightens fog in sun direction (god rays)
        "directional_inscattering_exponent": 8.0,
        "directional_inscattering_start_distance": 100.0,
        "directional_inscattering_color": unreal.LinearColor(0.6, 0.45, 0.25, 1.0),

        # Volumetric fog - ESSENTIAL for visible light shafts
        "volumetric_fog": True,
        "volumetric_fog_scattering_distribution": 0.85,   # Forward scattering (god ray directionality)
        "volumetric_fog_albedo": unreal.Color(230, 220, 200, 255),
        "volumetric_fog_extinction_scale": 1.5,
        "volumetric_fog_distance": 12000.0,
        "volumetric_fog_start_distance": 0.0,
        "volumetric_fog_near_fade_in_distance": 0.0,
    }
    for prop, val in fog_props.items():
        try:
            fc.set_editor_property(prop, val)
            unreal.log(f"  {prop} = {val}")
        except Exception as e:
            unreal.log_warning(f"  Could not set {prop}: {e}")
else:
    unreal.log_warning("  ExponentialHeightFog not found!")

# ============================================================
#  4) POST-PROCESS VOLUME - EERIE COLOR GRADING
# ============================================================
unreal.log("")
unreal.log("=" * 60)
unreal.log("  ADDING POST-PROCESS VOLUME")
unreal.log("=" * 60)

if pp_volume is None:
    pp_volume = EL.spawn_actor_from_class(
        unreal.PostProcessVolume, unreal.Vector(0, 3000, 0))
    if pp_volume:
        pp_volume.set_actor_label("PP_EerieGrade")
        unreal.log("  Spawned new PostProcessVolume")

if pp_volume:
    # Make it unbound (affects entire level)
    pp_volume.set_editor_property("unbound", True)
    pp_volume.set_editor_property("blend_weight", 1.0)
    pp_volume.set_editor_property("priority", 0.0)

    settings = pp_volume.settings

    # --- Bloom ---
    try:
        settings.set_editor_property("override_bloom_intensity", True)
        settings.set_editor_property("bloom_intensity", 0.8)
    except Exception as e:
        unreal.log_warning(f"  Bloom: {e}")

    try:
        settings.set_editor_property("override_bloom_threshold", True)
        settings.set_editor_property("bloom_threshold", 1.0)
    except Exception as e:
        unreal.log_warning(f"  BloomThreshold: {e}")

    # --- Auto Exposure (keep dark mood) ---
    try:
        settings.set_editor_property("override_auto_exposure_method", True)
        settings.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    except Exception as e:
        unreal.log_warning(f"  AutoExposureMethod: {e}")

    try:
        settings.set_editor_property("override_auto_exposure_bias", True)
        settings.set_editor_property("auto_exposure_bias", -0.5)
    except Exception as e:
        unreal.log_warning(f"  AutoExposureBias: {e}")

    # --- Color Grading: desaturate slightly, push shadows cool/green ---
    try:
        settings.set_editor_property("override_color_saturation", True)
        # Slightly desaturated for eerie mood (global)
        settings.set_editor_property("color_saturation",
            unreal.Vector4(0.85, 0.85, 0.85, 1.0))
    except Exception as e:
        unreal.log_warning(f"  ColorSaturation: {e}")

    try:
        settings.set_editor_property("override_color_contrast", True)
        # Slightly higher contrast
        settings.set_editor_property("color_contrast",
            unreal.Vector4(1.1, 1.1, 1.1, 1.0))
    except Exception as e:
        unreal.log_warning(f"  ColorContrast: {e}")

    try:
        settings.set_editor_property("override_color_gain", True)
        # Very slight green/teal tint to highlights
        settings.set_editor_property("color_gain",
            unreal.Vector4(0.95, 1.0, 0.97, 1.0))
    except Exception as e:
        unreal.log_warning(f"  ColorGain: {e}")

    try:
        settings.set_editor_property("override_color_offset", True)
        # Push shadows slightly blue-green
        settings.set_editor_property("color_offset",
            unreal.Vector4(-0.01, 0.005, 0.01, 0.0))
    except Exception as e:
        unreal.log_warning(f"  ColorOffset: {e}")

    try:
        settings.set_editor_property("override_scene_color_tint", True)
        settings.set_editor_property("scene_color_tint",
            unreal.LinearColor(1.0, 0.98, 0.95, 1.0))
    except Exception as e:
        unreal.log_warning(f"  SceneColorTint: {e}")

    # --- Vignette (subtle darkness at edges) ---
    try:
        settings.set_editor_property("override_vignette_intensity", True)
        settings.set_editor_property("vignette_intensity", 0.5)
    except Exception as e:
        unreal.log_warning(f"  Vignette: {e}")

    # --- Ambient Occlusion ---
    try:
        settings.set_editor_property("override_ambient_occlusion_intensity", True)
        settings.set_editor_property("ambient_occlusion_intensity", 0.6)
    except Exception as e:
        unreal.log_warning(f"  AO: {e}")

    try:
        settings.set_editor_property("override_ambient_occlusion_radius", True)
        settings.set_editor_property("ambient_occlusion_radius", 200.0)
    except Exception as e:
        unreal.log_warning(f"  AORadius: {e}")

    # --- Film grain (very subtle for cinematic feel) ---
    try:
        settings.set_editor_property("override_film_grain_intensity", True)
        settings.set_editor_property("film_grain_intensity", 0.03)
    except Exception as e:
        unreal.log_warning(f"  FilmGrain: {e}")

    unreal.log("  PostProcessVolume configured:")
    unreal.log("    - Bloom: 0.8 intensity")
    unreal.log("    - Manual exposure, bias -0.5 (dark mood)")
    unreal.log("    - Desaturated 15%, boosted contrast")
    unreal.log("    - Cool green shadows / warm highlights")
    unreal.log("    - Vignette: 0.5")
    unreal.log("    - AO: 0.6 intensity, 200 radius")
    unreal.log("    - Film grain: 0.03")
else:
    unreal.log_warning("  Could not create PostProcessVolume!")

# ============================================================
#  MOVE PP VOLUME INTO LIGHTING FOLDER
# ============================================================
if pp_volume:
    try:
        pp_volume.set_folder_path("Lighting")
        unreal.log("  Moved PP_EerieGrade into Lighting folder")
    except:
        pass

# ============================================================
#  SUMMARY
# ============================================================
unreal.log("")
unreal.log("=" * 60)
unreal.log("  LIGHTING TUNING COMPLETE")
unreal.log("=" * 60)
unreal.log("  DirectionalLight: low angle (-25 pitch), golden warm,")
unreal.log("    volumetric scattering 3.0 for visible god rays")
unreal.log("  SkyLight: subtle fill with green ground bounce")
unreal.log("  Fog: volumetric enabled, forward scattering 0.85,")
unreal.log("    warm directional inscattering for light shaft color")
unreal.log("  PostProcess: desaturated, high contrast, cool shadows,")
unreal.log("    vignette, manual exposure for consistent dark mood")
unreal.log("=" * 60)
