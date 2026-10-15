"""
import_kaykit.py
Imports CC0 KayKit assets from E:/UnrealProject/_SourceAssets into the project:
  - KayKit Adventurers "Knight" as ONE combined skeletal mesh (+ skeleton, its
    76 animations on that skeleton, material, texture) -> /Game/Characters/KayKit
  - KayKit Halloween Bits pumpkins / jack-o'-lanterns (static meshes)
    -> /Game/Props/Halloween

Neither pack ships FBX (both are the glTF distributions), so glTF is used and
Unreal's Interchange glTF pipeline stack does the import. For the Knight, the
stack is passed explicitly with "Combine Skeletal Meshes" set to
"Combine All That Use Same Skeleton"; the pumpkins use the default settings.

Only writes into the destination folders above. A group whose destination
folder already contains assets is skipped, so nothing existing is overwritten.
To redo a group, delete its folder first.

Run headless (editor must be closed):
    UnrealEditor-Cmd.exe "E:/UnrealProject/ScareLabirint/ScareLabirint.uproject"
        -run=pythonscript -script="E:/UnrealProject/ScareLabirint/import_kaykit.py"
Every line this script logs starts with [KayKitImport].
"""
import os
import unreal

SOURCE_ROOT = "E:/UnrealProject/_SourceAssets"
ADVENTURERS = SOURCE_ROOT + ("/KayKit_Adventurers/KayKit-Character-Pack-Adventures-1.0-main"
                             "/addons/kaykit_character_pack_adventures/Characters/gltf")
HALLOWEEN = SOURCE_ROOT + ("/KayKit_HalloweenBits/KayKit-Halloween-Bits-1.0-main"
                           "/addons/kaykit_halloween_bits/Assets/gltf")

CHARACTER_FILE = ADVENTURERS + "/Knight.glb"
CHARACTER_DEST = "/Game/Characters/KayKit"

PUMPKIN_FILES = [HALLOWEEN + f"/{name}.gltf" for name in (
    "pumpkin_orange",
    "pumpkin_orange_small",
    "pumpkin_orange_jackolantern",
    "pumpkin_yellow",
    "pumpkin_yellow_small",
    "pumpkin_yellow_jackolantern",
)]
PROPS_DEST = "/Game/Props/Halloween"

# The engine's default Interchange pipeline stack for glTF (see BaseEngine.ini,
# InterchangeProjectSettings PerTranslatorPipelines for InterchangeGLTFTranslator).
GLTF_ASSETS_PIPELINE = "/Interchange/Pipelines/DefaultGLTFAssetsPipeline"
GLTF_MATERIAL_PIPELINE = "/Interchange/Pipelines/DefaultGLTFPipeline"

TAG = "[KayKitImport]"


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


def combined_character_stack():
    """glTF pipeline stack with Combine Skeletal Meshes = BySkeleton.

    Interchange duplicates every pipeline at import time, so the setting is
    changed on the loaded engine pipeline only for the duration of the import
    (restore_combine() puts it back) and that engine asset is never saved.
    Returns (stack_override, restore_fn).
    """
    assets_pipeline = unreal.load_asset(GLTF_ASSETS_PIPELINE)
    material_pipeline = unreal.load_asset(GLTF_MATERIAL_PIPELINE)
    if assets_pipeline is None or material_pipeline is None:
        raise RuntimeError("Could not load the engine's default glTF Interchange pipelines")

    mesh_pipeline = assets_pipeline.get_editor_property("mesh_pipeline")
    anim_pipeline = assets_pipeline.get_editor_property("animation_pipeline")
    common = assets_pipeline.get_editor_property("common_skeletal_meshes_and_animations_properties")

    original = {
        (mesh_pipeline, "combine_skeletal_meshes_behavior"): mesh_pipeline.get_editor_property("combine_skeletal_meshes_behavior"),
        (anim_pipeline, "import_animations"): anim_pipeline.get_editor_property("import_animations"),
        (common, "import_only_animations"): common.get_editor_property("import_only_animations"),
    }
    log("Default glTF pipeline settings: " + ", ".join(f"{name}={value}" for (_, name), value in original.items()))

    mesh_pipeline.set_editor_property("combine_skeletal_meshes_behavior",
                                      unreal.InterchangeCombineSkeletalMeshesBehavior.BY_SKELETON)
    anim_pipeline.set_editor_property("import_animations", True)
    common.set_editor_property("import_only_animations", False)
    log("Knight import uses: combine_skeletal_meshes_behavior=BY_SKELETON, import_animations=True")

    stack = unreal.InterchangePipelineStackOverride()
    stack.add_pipeline(assets_pipeline)
    stack.add_pipeline(material_pipeline)

    def restore():
        for (obj, name), value in original.items():
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
        preview = ", ".join(names[:8]) + (f", ... (+{len(names) - 8} more)" if len(names) > 8 else "")
        log(f"  {cls} x{len(names)}: {preview}")
    return by_class


def import_character():
    if existing_assets(CHARACTER_DEST):
        warn(f"{CHARACTER_DEST} already has assets; skipping Knight import (delete the folder to redo it).")
        return None
    stack, restore = combined_character_stack()
    try:
        log("Importing Knight.glb as a combined skeletal mesh...")
        run_tasks([make_task(CHARACTER_FILE, CHARACTER_DEST, stack)])
    finally:
        restore()
    unreal.EditorAssetLibrary.save_directory(CHARACTER_DEST, only_if_is_dirty=True, recursive=True)

    found = summarize(CHARACTER_DEST)
    meshes = found.get("SkeletalMesh", [])
    skeletons = found.get("Skeleton", [])
    anims = found.get("AnimSequence", [])
    log(f"Character summary: SkeletalMesh={len(meshes)}, Skeleton={len(skeletons)}, AnimSequence={len(anims)}")

    # Verify every animation targets the combined mesh's skeleton.
    if len(meshes) == 1 and len(skeletons) == 1:
        mesh = unreal.load_asset(meshes[0])
        mesh_skeleton = mesh.get_editor_property("skeleton")
        mismatched = []
        for path in anims:
            anim = unreal.load_asset(path)
            if anim.get_editor_property("skeleton") != mesh_skeleton:
                mismatched.append(path)
        log(f"Skeletal mesh {meshes[0]} uses skeleton {mesh_skeleton.get_path_name()}; "
            f"{len(anims) - len(mismatched)}/{len(anims)} animations use the same skeleton")
        for path in mismatched:
            error(f"Animation on a different skeleton: {path}")
        if not mismatched and anims:
            log("Character import finished successfully.")
            return True
    else:
        error("Expected exactly 1 SkeletalMesh and 1 Skeleton after combining.")
    return False


def import_props():
    if existing_assets(PROPS_DEST):
        log(f"{PROPS_DEST} already has assets; leaving it untouched.")
        return None
    log(f"Importing {len(PUMPKIN_FILES)} pumpkin prop(s)...")
    run_tasks([make_task(f, PROPS_DEST) for f in PUMPKIN_FILES])
    unreal.EditorAssetLibrary.save_directory(PROPS_DEST, only_if_is_dirty=True, recursive=True)
    props = summarize(PROPS_DEST)
    count = len(props.get("StaticMesh", []))
    if count < len(PUMPKIN_FILES):
        error(f"Only {count}/{len(PUMPKIN_FILES)} pumpkin static meshes imported.")
        return False
    log("Props import finished successfully.")
    return True


def main():
    missing = [f for f in [CHARACTER_FILE] + PUMPKIN_FILES if not os.path.isfile(f)]
    if missing:
        for f in missing:
            error(f"Source file not found: {f}")
        return
    import_character()
    import_props()


main()
