"""
retarget_pumpkin.py
Retargets Quaternius Universal Animation Library clips onto the three LOWHO
pumpkin monsters with Unreal's IK Retargeter (run import_pumpkin_ual.py first).

  - Source IK Rigs (auto-generated retarget definition + auto FBIK, as the
    Quaternius rig uses UE mannequin bone names):
        /Game/Animations/Quaternius/UAL1/IK_UAL1, /Game/Animations/Quaternius/UAL2/IK_UAL2
  - Target IK Rig per monster, /Game/Characters/PumpkinMonster/<Name>/Retarget/IK_<Name>.
    The monsters use a Blender Rigify metarig, which has no auto-characterization
    template (the auto characterizer matches it loosely and builds overlapping
    spine/neck/head chains), so the chains are defined here with the same standard chain names
    the auto definition uses (Spine, Neck, Head, LeftArm, ...) so that chains map
    by exact name. A Full Body IK solver drives the hand/foot goals.
  - One IK Retargeter per monster and library,
        /Game/Characters/PumpkinMonster/<Name>/Retarget/RTG_UAL1_to_<Name> (and UAL2)
    using the default op stack and a chain-to-chain auto-aligned target pose.
  - Retargeted clips -> /Game/Characters/PumpkinMonster/<Name>/Anims

Only writes into the Retarget/ and Anims/ folders above and the two IK_UAL*
assets. A monster whose Anims/ folder already has assets is skipped. To redo a
monster, delete its Retarget/ and Anims/ folders first.

Run headless (editor must be closed):
    UnrealEditor-Cmd.exe "E:/UnrealProject/ScareLabirint/ScareLabirint.uproject"
        -run=pythonscript -script="E:/UnrealProject/ScareLabirint/retarget_pumpkin.py"
Every line this script logs starts with [PumpkinRetarget].
"""
import unreal

MONSTERS = ["Pumpkin_Monster_01", "Pumpkin_Monster_02", "Pumpkin_Monster_03"]
MONSTER_ROOT = "/Game/Characters/PumpkinMonster"

# name -> (folder, skeletal mesh, imported clip prefix, clips to retarget)
LIBRARIES = {
    "UAL1": ("/Game/Animations/Quaternius/UAL1",
             "/Game/Animations/Quaternius/UAL1/AL_Standard",
             "AL_StandardRig_",
             ["Idle_Loop", "Walk_Loop", "Jog_Fwd_Loop", "Sprint_Loop"]),
    "UAL2": ("/Game/Animations/Quaternius/UAL2",
             "/Game/Animations/Quaternius/UAL2/UAL2_Standard/SkeletalMeshes/UAL2_Standard",
             "UAL2_Standard",
             ["Zombie_Idle_Loop", "Zombie_Walk_Fwd_Loop", "Zombie_Scratch"]),
}

# Rigify metarig (Blender '.' became '_' on import): chain -> (start, end, goal)
MONSTER_RETARGET_ROOT = "spine"
MONSTER_CHAINS = {
    "Spine": ("spine_001", "spine_003", None),
    "Neck": ("spine_004", "spine_005", None),
    "Head": ("spine_006", "spine_006", None),
    "LeftClavicle": ("shoulder_L", "shoulder_L", None),
    "LeftArm": ("upper_arm_L", "hand_L", "LeftHandIK"),
    "RightClavicle": ("shoulder_R", "shoulder_R", None),
    "RightArm": ("upper_arm_R", "hand_R", "RightHandIK"),
    "LeftLeg": ("thigh_L", "foot_L", "LeftFootIK"),
    "LeftFoot": ("toe_L", "toe_L", None),
    "RightLeg": ("thigh_R", "foot_R", "RightFootIK"),
    "RightFoot": ("toe_R", "toe_R", None),
}

# Fallback for the Quaternius rig if the auto-generated definition is unavailable.
QUATERNIUS_RETARGET_ROOT = "pelvis"
QUATERNIUS_CHAINS = {
    "Spine": ("spine_01", "spine_03", None),
    "Neck": ("neck_01", "neck_01", None),
    "Head": ("Head", "Head", None),
    "LeftClavicle": ("clavicle_l", "clavicle_l", None),
    "LeftArm": ("upperarm_l", "hand_l", "LeftHandIK"),
    "RightClavicle": ("clavicle_r", "clavicle_r", None),
    "RightArm": ("upperarm_r", "hand_r", "RightHandIK"),
    "LeftLeg": ("thigh_l", "foot_l", "LeftFootIK"),
    "LeftFoot": ("ball_l", "ball_l", None),
    "RightLeg": ("thigh_r", "foot_r", "RightFootIK"),
    "RightFoot": ("ball_r", "ball_r", None),
}

FBIK_SOLVER = "/Script/IKRig.IKRigFullBodyIKSolver"
DEFAULT_BONE_COMPRESSION = "/Engine/Animation/DefaultAnimBoneCompressionSettings"
SOURCE = unreal.RetargetSourceOrTarget.SOURCE
TARGET = unreal.RetargetSourceOrTarget.TARGET

TAG = "[PumpkinRetarget]"


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


def load_or_create(folder, name, cls, factory):
    path = f"{folder}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path), False
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)
    if asset is None:
        raise RuntimeError(f"Could not create {path}")
    return asset, True


def log_chains(label, controller):
    # FBoneChain's fields are not exposed to Python; read them via the controller.
    names = [str(c.get_editor_property("chain_name")) if hasattr(c, "get_editor_property") else str(c)
             for c in controller.get_retarget_chains()]
    parts = []
    for name in names:
        goal = str(controller.get_retarget_chain_goal(name))
        parts.append(f"{name}[{controller.get_retarget_chain_start_bone(name)}->"
                     f"{controller.get_retarget_chain_end_bone(name)}{'' if goal == 'None' else ' goal ' + goal}]")
    log(f"{label}: retarget root={controller.get_retarget_root()}, solvers={controller.get_num_solvers()}, "
        f"{len(names)} chain(s): " + ", ".join(parts))


def define_chains(controller, root, chains):
    """Manual retarget definition: root, chains with goals, one FBIK solver."""
    controller.set_retarget_root(root)
    solver = controller.add_solver(FBIK_SOLVER)
    if solver < 0:
        raise RuntimeError("Could not add the Full Body IK solver")
    controller.set_start_bone(root, solver)
    for chain, (start, end, goal) in chains.items():
        goal_name = "None"
        if goal:
            goal_name = controller.add_new_goal(goal, end)
            controller.connect_goal_to_solver(goal_name, solver)
        controller.add_retarget_chain(chain, start, end, goal_name)


def source_ik_rig(lib):
    folder, mesh_path, _, _ = LIBRARIES[lib]
    rig, created = load_or_create(folder, f"IK_{lib}", unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    controller = unreal.IKRigController.get_controller(rig)
    if created:
        controller.set_skeletal_mesh(unreal.load_asset(mesh_path))
        if controller.apply_auto_generated_retarget_definition():
            log(f"IK_{lib}: auto-generated retarget definition applied")
            if not controller.apply_auto_fbik():
                warn(f"IK_{lib}: auto FBIK failed; adding a Full Body IK solver manually")
                define_chains(controller, QUATERNIUS_RETARGET_ROOT, {})
        else:
            warn(f"IK_{lib}: no auto-generated retarget definition; using the manual Quaternius chains")
            define_chains(controller, QUATERNIUS_RETARGET_ROOT, QUATERNIUS_CHAINS)
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
    log_chains(f"IK_{lib}", controller)
    return rig


def monster_ik_rig(monster, mesh):
    folder = f"{MONSTER_ROOT}/{monster}/Retarget"
    rig, created = load_or_create(folder, f"IK_{monster}", unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    controller = unreal.IKRigController.get_controller(rig)
    if created:
        controller.set_skeletal_mesh(mesh)
        # Not auto-generated on purpose: the auto characterizer loosely matches
        # the Rigify metarig to a generic template and produces overlapping
        # chains (Spine spine_001->spine_006 also covering Neck and Head).
        define_chains(controller, MONSTER_RETARGET_ROOT, MONSTER_CHAINS)
        unreal.EditorAssetLibrary.save_loaded_asset(rig)
    log_chains(f"IK_{monster}", controller)
    return rig


def retargeter(monster, lib, source_rig, target_rig):
    folder = f"{MONSTER_ROOT}/{monster}/Retarget"
    rtg, created = load_or_create(folder, f"RTG_{lib}_to_{monster}", unreal.IKRetargeter, unreal.IKRetargetFactory())
    controller = unreal.IKRetargeterController.get_controller(rtg)
    if created:
        controller.set_ik_rig(SOURCE, source_rig)
        controller.set_ik_rig(TARGET, target_rig)
        controller.add_default_ops()
        controller.assign_ik_rig_to_all_ops(SOURCE, source_rig)
        controller.assign_ik_rig_to_all_ops(TARGET, target_rig)
        controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
        # Both rigs are T-posed, but bone directions differ slightly; align the
        # monster's chains to the Quaternius chains in a dedicated retarget pose.
        pose = controller.create_retarget_pose("AutoAligned", TARGET)
        controller.set_current_retarget_pose(pose, TARGET)
        controller.auto_align_all_bones(TARGET, unreal.RetargetAutoAlignMethod.CHAIN_TO_CHAIN)
        unreal.EditorAssetLibrary.save_loaded_asset(rtg)
    ops = [str(controller.get_op_name(i)) for i in range(controller.get_num_retarget_ops())]
    mapped = [f"{chain}<-{controller.get_source_chain(chain)}" for chain in MONSTER_CHAINS]
    log(f"RTG_{lib}_to_{monster}: ops={ops}; chains {', '.join(mapped)}")
    unmapped = [chain for chain in MONSTER_CHAINS if str(controller.get_source_chain(chain)) == "None"]
    for chain in unmapped:
        warn(f"RTG_{lib}_to_{monster}: target chain {chain} has no source chain")
    return rtg


def clip_assets(lib):
    folder, _, prefix, clips = LIBRARIES[lib]
    found = {}
    for path in existing_assets(folder):
        data = unreal.EditorAssetLibrary.find_asset_data(path)
        if str(data.asset_class_path.asset_name) == "AnimSequence":
            found[str(data.asset_name)] = data
    result = []
    for clip in clips:
        data = found.get(prefix + clip)
        if data is None:
            error(f"{lib}: clip {prefix + clip} not found in {folder}")
        else:
            result.append(data)
    return result


def retarget_clips(monster, mesh, lib, rtg):
    _, source_mesh, prefix, _ = LIBRARIES[lib]
    inputs = unreal.IKRetargetBatchOperationInputs()
    inputs.set_editor_property("assets_to_retarget", clip_assets(lib))
    inputs.set_editor_property("source_mesh", unreal.load_asset(source_mesh))
    inputs.set_editor_property("target_mesh", mesh)
    inputs.set_editor_property("ik_retarget_asset", rtg)
    inputs.set_editor_property("search", prefix)
    inputs.set_editor_property("replace", "")
    inputs.set_editor_property("target_path", f"{MONSTER_ROOT}/{monster}/Anims")
    inputs.set_editor_property("use_source_path", False)
    inputs.set_editor_property("include_referenced_assets", False)
    inputs.set_editor_property("overwrite_existing_files", False)
    results = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    return [str(r.package_name) for r in results]


def finish_anims(monster, mesh):
    """Default (non-ACL) bone compression and a skeleton check on every result."""
    folder = f"{MONSTER_ROOT}/{monster}/Anims"
    settings = unreal.load_asset(DEFAULT_BONE_COMPRESSION)
    skeleton = mesh.get_editor_property("skeleton")
    names = []
    for path in existing_assets(folder):
        anim = unreal.load_asset(path)
        if not isinstance(anim, unreal.AnimSequence):
            warn(f"Unexpected non-animation asset in {folder}: {path}")
            continue
        if anim.get_editor_property("skeleton") != skeleton:
            error(f"{path} is not on {skeleton.get_path_name()}")
        if settings and anim.get_editor_property("bone_compression_settings") != settings:
            anim.set_editor_property("bone_compression_settings", settings)
        names.append(f"{anim.get_name()} ({anim.get_play_length():.2f}s)")
    unreal.EditorAssetLibrary.save_directory(folder, only_if_is_dirty=True, recursive=True)
    log(f"{monster}/Anims: {len(names)} clip(s): " + ", ".join(sorted(names)))
    return names


def main():
    source_rigs = {lib: source_ik_rig(lib) for lib in LIBRARIES}
    expected = sum(len(clips) for _, _, _, clips in LIBRARIES.values())
    for monster in MONSTERS:
        anims_folder = f"{MONSTER_ROOT}/{monster}/Anims"
        if existing_assets(anims_folder):
            warn(f"{anims_folder} already has assets; skipping {monster} (delete Retarget/ and Anims/ to redo it).")
            continue
        mesh = unreal.load_asset(f"{MONSTER_ROOT}/{monster}/{monster}")
        target_rig = monster_ik_rig(monster, mesh)
        for lib, source_rig in source_rigs.items():
            rtg = retargeter(monster, lib, source_rig, target_rig)
            created = retarget_clips(monster, mesh, lib, rtg)
            log(f"{monster} <- {lib}: {len(created)} asset(s) created")
        unreal.EditorAssetLibrary.save_directory(f"{MONSTER_ROOT}/{monster}", only_if_is_dirty=True, recursive=True)
        names = finish_anims(monster, mesh)
        if len(names) != expected:
            error(f"{monster}: expected {expected} retargeted clips, found {len(names)}")
    log("Done.")


main()
