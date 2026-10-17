"""
import_pumpkin_ual.py
Imports CC0 assets from E:/UnrealProject/_SourceAssets into the project:
  - LOWHO Pumpkin Monster (free pack, FBX): each of the 3 monsters as its own
    skeletal mesh WITH its own skeleton -> /Game/Characters/PumpkinMonster/<Name>
    (skeletons are deliberately not shared; proportions differ a lot)
  - LOWHO props (Jack_O_Lantern_01, Pumpkin_01) -> /Game/Props/Halloween/PumpkinMonster
  - Quaternius Universal Animation Library [Standard] (Unreal FBX: mannequin,
    rig and all clips) -> /Game/Animations/Quaternius/UAL1
  - Quaternius Universal Animation Library 2 [Standard] (Unreal glb: mannequin,
    rig and all clips) -> /Game/Animations/Quaternius/UAL2

The monsters' and the UAL1 FBX's armature root bone carries scale 100; that
scale is baked into the bone translations after import (see bake_armature_scale)
because the IK Retargeter does not support scaled bones.

Quaternius setup notes followed: no skeleton assigned on import, Use T0 As Ref
Pose off (keeps the T-pose for retargeting), bake bones at 30 Hz, snap to the
closest frame, and the clips are switched from ACL to the default (non-ACL)
bone compression afterwards because ACL adds jitter on these animations.

Only writes into the destination folders above. A group whose destination
folder already contains assets is skipped, so nothing existing is overwritten.
To redo a group, delete its folder first.

Run headless (editor must be closed):
    UnrealEditor-Cmd.exe "E:/UnrealProject/ScareLabirint/ScareLabirint.uproject"
        -run=pythonscript -script="E:/UnrealProject/ScareLabirint/import_pumpkin_ual.py"
Every line this script logs starts with [PumpkinImport].
"""
import os
import shutil
import unreal

SOURCE_ROOT = "E:/UnrealProject/_SourceAssets"
PUMPKIN = SOURCE_ROOT + "/LOWHO_PumpkinMonster/Pumpkin_Monster_Free/FBX"
UAL1_FILE = SOURCE_ROOT + "/Quaternius_UAL1/Animation Library[Standard]/Unreal Engine/AL_Standard.fbx"
UAL2_FILE = SOURCE_ROOT + "/Quaternius_UAL2/Universal Animation Library 2 [Standard]/Unreal-Godot/UAL2_Standard.glb"

MONSTERS = ["Pumpkin_Monster_01", "Pumpkin_Monster_02", "Pumpkin_Monster_03"]
MONSTER_ROOT = "/Game/Characters/PumpkinMonster"
PROP_FILES = [PUMPKIN + f"/Props/{name}.fbx" for name in ("Jack_O_Lantern_01", "Pumpkin_01")]
PROPS_DEST = "/Game/Props/Halloween/PumpkinMonster"
UAL1_DEST = "/Game/Animations/Quaternius/UAL1"
UAL2_DEST = "/Game/Animations/Quaternius/UAL2"

# Engine default Interchange stacks (BaseEngine.ini, InterchangeProjectSettings
# PerTranslatorPipelines for the FBX and glTF translators).
FBX_ASSETS_PIPELINE = "/Interchange/Pipelines/DefaultFBXOBJAssetsPipeline"
GLTF_ASSETS_PIPELINE = "/Interchange/Pipelines/DefaultGLTFAssetsPipeline"
GLTF_MATERIAL_PIPELINE = "/Interchange/Pipelines/DefaultGLTFPipeline"
DEFAULT_BONE_COMPRESSION = "/Engine/Animation/DefaultAnimBoneCompressionSettings"

TAG = "[PumpkinImport]"


def log(msg):
    unreal.log(f"{TAG} {msg}")


def warn(msg):
    unreal.log_warning(f"{TAG} {msg}")


def error(msg):
    unreal.log_error(f"{TAG} {msg}")


def existing_assets(folder):
    if not unreal.EditorAssetLibrary.does_directory_exist(folder):
        return []
    return unreal.EditorAssetLibrary.list_assets(folder, recursive=True)


def make_task(source_file, dest_path, options=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", source_file)
    task.set_editor_property("destination_path", dest_path)
    task.set_editor_property("automated", True)   # no dialogs
    task.set_editor_property("save", True)
    # Safe: a destination is only imported into when it was empty, so this can
    # only ever replace assets created earlier in this same run.
    task.set_editor_property("replace_existing", True)
    if options is not None:
        task.set_editor_property("options", options)
    return task


def configured_stack(pipeline_paths, animations):
    """Pipeline stack built from the engine's default pipelines with our settings.

    Interchange duplicates every pipeline at import time, so the settings are
    changed on the loaded engine pipeline only for the duration of the import
    (the returned restore() puts them back) and that engine asset is never saved.
    animations=True: import clips at 30 Hz snapped to the closest frame.
    animations=False: mesh + skeleton only.
    Returns (stack_override, restore_fn).
    """
    pipelines = [unreal.load_asset(p) for p in pipeline_paths]
    if any(p is None for p in pipelines):
        raise RuntimeError(f"Could not load Interchange pipelines {pipeline_paths}")
    assets_pipeline = pipelines[0]
    mesh_pipeline = assets_pipeline.get_editor_property("mesh_pipeline")
    anim_pipeline = assets_pipeline.get_editor_property("animation_pipeline")
    common = assets_pipeline.get_editor_property("common_skeletal_meshes_and_animations_properties")

    wanted = [
        (mesh_pipeline, "import_skeletal_meshes", True),
        (mesh_pipeline, "combine_skeletal_meshes_behavior", unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON),
        (common, "import_only_animations", False),
        (common, "skeleton", None),
        (common, "use_t0_as_ref_pose", False),
        (anim_pipeline, "import_animations", animations),
    ]
    if animations:
        wanted += [
            (anim_pipeline, "import_bone_tracks", True),
            (anim_pipeline, "use30_hz_to_bake_bone_animation", True),
            (anim_pipeline, "frame_alignment", unreal.InterchangeFrameAlignment.SNAP_TO_CLOSEST),
        ]
    original = [(obj, name, obj.get_editor_property(name)) for obj, name, _ in wanted]
    for obj, name, value in wanted:
        obj.set_editor_property(name, value)
    log("Pipeline settings: " + ", ".join(f"{name}={value}" for _, name, value in wanted))

    stack = unreal.InterchangePipelineStackOverride()
    for p in pipelines:
        stack.add_pipeline(p)

    def restore():
        for obj, name, value in original:
            obj.set_editor_property(name, value)

    return stack, restore


def run_tasks(tasks):
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    ok = True
    for task in tasks:
        name = os.path.basename(task.get_editor_property("filename"))
        imported = list(task.get_editor_property("imported_object_paths") or [])
        if imported:
            log(f"OK   {name}: {len(imported)} object(s)")
        else:
            error(f"FAIL {name}: nothing imported")
            ok = False
    return ok


def summarize(folder):
    by_class = {}
    for path in existing_assets(folder):
        data = unreal.EditorAssetLibrary.find_asset_data(path)
        cls = str(data.asset_class_path.asset_name)
        by_class.setdefault(cls, []).append(str(data.package_name))
    log(f"Contents of {folder}:")
    for cls in sorted(by_class):
        names = sorted(by_class[cls])
        log(f"  {cls} x{len(names)}: " + ", ".join(n.rsplit("/", 1)[1] for n in names))
    return by_class


def import_skeletal(source_file, dest, pipelines, animations):
    """Imports one file as a single skeletal mesh with its own new skeleton."""
    label = os.path.basename(source_file)
    if existing_assets(dest):
        warn(f"{dest} already has assets; skipping {label} (delete the folder to redo it).")
        return None
    stack, restore = configured_stack(pipelines, animations)
    try:
        log(f"Importing {label} -> {dest} ...")
        run_tasks([make_task(source_file, dest, stack)])
    finally:
        restore()
    unreal.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=True, recursive=True)

    found = summarize(dest)
    meshes = found.get("SkeletalMesh", [])
    skeletons = found.get("Skeleton", [])
    anims = found.get("AnimSequence", [])
    log(f"{label}: SkeletalMesh={len(meshes)}, Skeleton={len(skeletons)}, AnimSequence={len(anims)}")
    if len(meshes) != 1 or len(skeletons) != 1:
        error(f"{label}: expected exactly 1 SkeletalMesh and 1 Skeleton.")
        return False

    mesh = unreal.load_asset(meshes[0])
    skeleton = mesh.get_editor_property("skeleton")
    log(f"{label}: mesh {meshes[0]} uses skeleton {skeleton.get_path_name()}")
    mismatched = [p for p in anims if unreal.load_asset(p).get_editor_property("skeleton") != skeleton]
    for path in mismatched:
        error(f"Animation on a different skeleton: {path}")
    return not mismatched


def bake_armature_scale(mesh_path):
    """Moves the Blender armature's scale out of the root bone.

    The LOWHO FBXs come in with the armature as root bone at scale 100 and every
    other bone offset in metres. The IK Retargeter strips bone scale (it assumes
    none), which collapses retargeted animation, so the scale is baked into the
    bone translations: root scale -> 1, every other local translation x scale.
    World-space bone transforms and the mesh are unchanged.

    A transform-only edit is not pushed to the Skeleton asset, so a leaf bone is
    renamed in the first commit and renamed back in a second one; each rename
    makes the Skeleton rebuild its bone tree from the mesh.
    """
    mesh = unreal.load_asset(mesh_path)
    modifier = unreal.SkeletonModifier()
    modifier.set_skeletal_mesh(mesh)
    names = list(modifier.get_all_bone_names())
    root = names[0]
    scale = modifier.get_bone_transform(root, False).scale3d
    if scale.is_near_equal(unreal.Vector(1, 1, 1), 1e-4):
        log(f"{mesh.get_name()}: root bone {root} has no scale; nothing to bake")
        return True
    if not (abs(scale.x - scale.y) < 1e-4 and abs(scale.x - scale.z) < 1e-4):
        error(f"{mesh.get_name()}: root bone {root} has non-uniform scale {scale}; not baking")
        return False

    transforms = []
    for name in names:
        local = modifier.get_bone_transform(name, False)
        if name == root:
            transforms.append(unreal.Transform(local.translation, local.rotation.rotator(), unreal.Vector(1, 1, 1)))
        else:
            transforms.append(unreal.Transform(local.translation * scale.x, local.rotation.rotator(), local.scale3d))
    leaf = next(n for n in reversed(names) if not modifier.get_children_names(n, False))
    temp = f"{leaf}__bake"
    ok = (modifier.set_bones_transforms(names, transforms, False)
          and modifier.rename_bone(leaf, temp)
          and modifier.commit_skeleton_to_skeletal_mesh())
    restore = unreal.SkeletonModifier()
    restore.set_skeletal_mesh(mesh)
    ok = ok and restore.rename_bone(temp, leaf) and restore.commit_skeleton_to_skeletal_mesh()

    check = unreal.SkeletonModifier()
    check.set_skeletal_mesh(mesh)
    skeleton_pose = unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property("skeleton"))
    skeleton_root = unreal.AnimPoseExtensions.get_ref_bone_pose(skeleton_pose, root, unreal.AnimPoseSpaces.LOCAL)
    ok = (ok and [str(n) for n in check.get_all_bone_names()] == [str(n) for n in names]
          and skeleton_root.scale3d.is_near_equal(unreal.Vector(1, 1, 1), 1e-4))
    if not ok:
        error(f"{mesh.get_name()}: baking the armature scale failed")
        return False
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh.get_editor_property("skeleton"))
    log(f"{mesh.get_name()}: baked root bone {root} scale {scale.x:g} into {len(names) - 1} bone translations")
    return True


def use_default_compression(folder):
    """Switches every clip in folder from ACL to the default bone compression."""
    settings = unreal.load_asset(DEFAULT_BONE_COMPRESSION)
    if settings is None:
        warn(f"{DEFAULT_BONE_COMPRESSION} not found; leaving bone compression as imported.")
        return
    changed = 0
    for path in existing_assets(folder):
        data = unreal.EditorAssetLibrary.find_asset_data(path)
        if str(data.asset_class_path.asset_name) != "AnimSequence":
            continue
        anim = unreal.load_asset(path)
        if anim.get_editor_property("bone_compression_settings") != settings:
            anim.set_editor_property("bone_compression_settings", settings)
            changed += 1
    unreal.EditorAssetLibrary.save_directory(folder, only_if_is_dirty=True, recursive=True)
    log(f"{folder}: {changed} clip(s) switched to {DEFAULT_BONE_COMPRESSION}")


def import_props():
    if existing_assets(PROPS_DEST):
        log(f"{PROPS_DEST} already has assets; leaving it untouched.")
        return None
    log(f"Importing {len(PROP_FILES)} prop(s)...")
    run_tasks([make_task(f, PROPS_DEST) for f in PROP_FILES])
    unreal.EditorAssetLibrary.save_directory(PROPS_DEST, only_if_is_dirty=True, recursive=True)
    props = summarize(PROPS_DEST)
    count = len(props.get("StaticMesh", []))
    if count < len(PROP_FILES):
        error(f"Only {count}/{len(PROP_FILES)} prop static meshes imported.")
        return False
    log("Props import finished successfully.")
    return True


def stage_pumpkin_texture():
    """The LOWHO FBXs reference LOWHO.png by the author's absolute D:\\ path or,
    as a fallback, next to the FBX. The pack ships it in Texture/, so copy it
    beside the FBXs; otherwise Interchange creates untextured materials."""
    texture = PUMPKIN + "/../Texture/LOWHO.png"
    for folder in (PUMPKIN + "/Characters", PUMPKIN + "/Props"):
        dest = folder + "/LOWHO.png"
        if not os.path.isfile(dest) and os.path.isfile(texture):
            shutil.copyfile(texture, dest)
            log(f"Copied LOWHO.png next to the FBXs in {folder}")


def main():
    stage_pumpkin_texture()
    monster_files = {name: f"{PUMPKIN}/Characters/{name}.fbx" for name in MONSTERS}
    missing = [f for f in list(monster_files.values()) + PROP_FILES + [UAL1_FILE, UAL2_FILE]
               if not os.path.isfile(f)]
    if missing:
        for f in missing:
            error(f"Source file not found: {f}")
        return

    for name, path in monster_files.items():
        if import_skeletal(path, f"{MONSTER_ROOT}/{name}", [FBX_ASSETS_PIPELINE], animations=False):
            bake_armature_scale(f"{MONSTER_ROOT}/{name}/{name}")
    import_props()

    ual1 = import_skeletal(UAL1_FILE, UAL1_DEST, [FBX_ASSETS_PIPELINE], animations=True)
    if ual1:
        # Quaternius' Unreal FBX has the same scale-100 armature root ("Rig");
        # the clips keep their own tracks, so they play back unchanged.
        bake_armature_scale(f"{UAL1_DEST}/AL_Standard")
    if ual1 is not None:
        use_default_compression(UAL1_DEST)
    if import_skeletal(UAL2_FILE, UAL2_DEST, [GLTF_ASSETS_PIPELINE, GLTF_MATERIAL_PIPELINE], animations=True) is not None:
        use_default_compression(UAL2_DEST)
    log("Done.")


main()
