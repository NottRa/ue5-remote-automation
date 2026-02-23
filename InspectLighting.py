"""
Inspect lighting actors in the current level.
Run in UE Editor: Tools > Execute Python Script
"""
import unreal

EL = unreal.EditorLevelLibrary
actors = EL.get_all_level_actors()

unreal.log("=" * 60)
unreal.log(f"  LEVEL LIGHTING INSPECTION - {len(actors)} actors")
unreal.log("=" * 60)

for actor in actors:
    cls_name = actor.get_class().get_name()
    label = actor.get_actor_label()
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()

    # Only inspect lighting-related actors
    keywords = ["light", "sky", "fog", "atmosphere", "cloud", "post", "sun", "volume"]
    if not any(k in cls_name.lower() or k in label.lower() for k in keywords):
        continue

    unreal.log("")
    unreal.log(f"--- {label} ({cls_name}) ---")
    unreal.log(f"  Location: ({loc.x:.1f}, {loc.y:.1f}, {loc.z:.1f})")
    unreal.log(f"  Rotation: (Pitch={rot.pitch:.1f}, Yaw={rot.yaw:.1f}, Roll={rot.roll:.1f})")

    # DirectionalLight
    if "DirectionalLight" in cls_name:
        try:
            lc = actor.light_component
            for prop in ["intensity", "light_color", "temperature", "use_temperature",
                         "cast_shadows", "atmosphere_sun_light", "used_as_atmosphere_sun_light",
                         "atmosphere_sun_light_index", "volumetric_scattering_intensity",
                         "indirect_lighting_intensity", "cast_cloud_shadows",
                         "cloud_shadow_strength", "light_source_angle"]:
                try:
                    val = lc.get_editor_property(prop)
                    unreal.log(f"  {prop} = {val}")
                except:
                    pass
        except Exception as e:
            unreal.log_warning(f"  DirectionalLight error: {e}")

    # SkyLight
    elif "SkyLight" in cls_name:
        try:
            lc = actor.light_component
            for prop in ["intensity", "real_time_capture", "source_type",
                         "lower_hemisphere_is_solid_color", "lower_hemisphere_color",
                         "cloud_ambient_occlusion", "cloud_ambient_occlusion_strength",
                         "volumetric_scattering_intensity", "indirect_lighting_intensity"]:
                try:
                    val = lc.get_editor_property(prop)
                    unreal.log(f"  {prop} = {val}")
                except:
                    pass
        except Exception as e:
            unreal.log_warning(f"  SkyLight error: {e}")

    # SkyAtmosphere
    elif "SkyAtmosphere" in cls_name:
        try:
            comp = actor.get_component_by_class(unreal.SkyAtmosphereComponent)
            if comp:
                for prop in ["rayleigh_scattering", "rayleigh_exponential_distribution",
                             "mie_scattering", "mie_absorption", "mie_exponential_distribution",
                             "mie_anisotropy", "ground_albedo", "multi_scattering_factor",
                             "transform_mode"]:
                    try:
                        val = comp.get_editor_property(prop)
                        unreal.log(f"  {prop} = {val}")
                    except:
                        pass
        except Exception as e:
            unreal.log_warning(f"  SkyAtmosphere error: {e}")

    # VolumetricCloud
    elif "VolumetricCloud" in cls_name:
        try:
            comp = actor.get_component_by_class(unreal.VolumetricCloudComponent)
            if comp:
                for prop in ["layer_bottom_altitude", "layer_height", "tracing_start_max_distance",
                             "tracing_max_distance", "planet_radius",
                             "ground_albedo", "material", "stop_tracing_transmittance_threshold",
                             "shadow_tracing_distance", "shadow_reflection_sample_count_scale"]:
                    try:
                        val = comp.get_editor_property(prop)
                        unreal.log(f"  {prop} = {val}")
                    except:
                        pass
        except Exception as e:
            unreal.log_warning(f"  VolumetricCloud error: {e}")

    # ExponentialHeightFog
    elif "ExponentialHeightFog" in cls_name or "Fog" in cls_name:
        try:
            comp = actor.component
            for prop in ["fog_density", "fog_height_falloff", "fog_max_opacity",
                         "start_distance", "fog_cutoff_distance",
                         "fog_inscattering_color", "fog_inscattering_luminance",
                         "directional_inscattering_color", "directional_inscattering_luminance",
                         "directional_inscattering_exponent", "directional_inscattering_start_distance",
                         "volumetric_fog", "volumetric_fog_scattering_distribution",
                         "volumetric_fog_albedo", "volumetric_fog_extinction_scale",
                         "volumetric_fog_distance", "volumetric_fog_start_distance",
                         "volumetric_fog_near_fade_in_distance",
                         "second_fog_data_enabled"]:
                try:
                    val = comp.get_editor_property(prop)
                    unreal.log(f"  {prop} = {val}")
                except:
                    pass
        except Exception as e:
            unreal.log_warning(f"  Fog error: {e}")

    # PostProcessVolume
    elif "PostProcess" in cls_name:
        try:
            for prop in ["blend_radius", "blend_weight", "priority",
                         "unbound"]:
                try:
                    val = actor.get_editor_property(prop)
                    unreal.log(f"  {prop} = {val}")
                except:
                    pass
            # Settings
            try:
                settings = actor.settings
                for prop in ["bloom_intensity", "auto_exposure_method",
                             "auto_exposure_min_brightness", "auto_exposure_max_brightness",
                             "vignette_intensity", "color_saturation",
                             "scene_color_tint", "ambient_occlusion_intensity"]:
                    try:
                        val = settings.get_editor_property(prop)
                        unreal.log(f"  settings.{prop} = {val}")
                    except:
                        pass
            except:
                pass
        except Exception as e:
            unreal.log_warning(f"  PostProcess error: {e}")

unreal.log("")
unreal.log("=" * 60)
unreal.log("  INSPECTION COMPLETE")
unreal.log("=" * 60)
