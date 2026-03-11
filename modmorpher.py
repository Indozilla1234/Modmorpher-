import os
import re
import json
import uuid
import zipfile
import shutil
from typing import Optional, Tuple, Dict, Set, List

# Pillow used for icon cropping/resizing. If missing, script warns and copies icons unmodified.
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# javalang provides proper Java AST parsing
# Required dependency: pip install javalang
try:
    import javalang
except ImportError:
    raise ImportError(
        "This script requires the 'javalang' package.\n"
        "Install it with:\n"
        "    pip install javalang"
    )

JAVALANG_AVAILABLE = True


class JavaAST:
    """
    Wraps javalang to parse a Java source file into an AST once, then provides
    targeted query helpers used throughout ModMorpher.

    Falls back to returning None / empty results if javalang is unavailable or
    if the source cannot be parsed (e.g. incomplete stub files, Lombok annotations).
    All callers must handle None returns and use their own regex fallback.
    """

    def __init__(self, source: str):
        self._src = source
        self._tree: Optional[object] = None  # javalang CompilationUnit or None
        self._parsed = False

    def _parse(self):
        if self._parsed:
            return
        self._parsed = True
        if not JAVALANG_AVAILABLE:
            return
        try:
            self._tree = javalang.parse.parse(self._src)
        except Exception:
            self._tree = None

    # ── Class / type declarations ──────────────────────────────────────────

    def get_class_declarations(self) -> List:
        """Return all ClassDeclaration nodes in the compilation unit."""
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            results.append(node)
        return results

    def primary_class_name(self) -> Optional[str]:
        """Return the name of the first public (or first) top-level class."""
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            return node.name
        for _, node in self._tree.filter(javalang.tree.InterfaceDeclaration):
            return node.name
        for _, node in self._tree.filter(javalang.tree.EnumDeclaration):
            return node.name
        return None

    def superclass_name(self, cls_name: Optional[str] = None) -> Optional[str]:
        """Return the direct superclass name of the given class (or primary class)."""
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if cls_name and node.name != cls_name:
                continue
            if node.extends and hasattr(node.extends, 'name'):
                return node.extends.name
        return None

    def implemented_interfaces(self, cls_name: Optional[str] = None) -> List[str]:
        """Return list of implemented interface names for the given class."""
        self._parse()
        if not self._tree:
            return []
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if cls_name and node.name != cls_name:
                continue
            if node.implements:
                return [i.name for i in node.implements if hasattr(i, 'name')]
        return []

    def class_extends(self, target_name: str, cls_name: Optional[str] = None) -> bool:
        """Return True if any class declaration extends target_name."""
        self._parse()
        if not self._tree:
            return False
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if cls_name and node.name != cls_name:
                continue
            if node.extends and hasattr(node.extends, 'name'):
                if node.extends.name == target_name:
                    return True
        return False

    def all_class_extends(self) -> List[Tuple[str, str]]:
        """Return list of (child_class_name, parent_class_name) for all class decls."""
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if node.extends and hasattr(node.extends, 'name'):
                results.append((node.name, node.extends.name))
        return results

    # ── Annotation queries ─────────────────────────────────────────────────

    def annotation_value(self, annotation_name: str) -> Optional[str]:
        """
        Return the string value of a type-level annotation like @Mod("modid").
        Returns None if not found.
        """
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.ClassDeclaration):
            if not node.annotations:
                continue
            for ann in node.annotations:
                if ann.name == annotation_name:
                    # @Mod("value") — single string element
                    if ann.element and hasattr(ann.element, 'value'):
                        v = ann.element.value
                        return v.strip('"').strip("'") if isinstance(v, str) else str(v)
        return None

    # ── Field / variable declarations ──────────────────────────────────────

    def field_string_values(self, field_names: Set[str]) -> Dict[str, str]:
        """
        Find field declarations matching any name in field_names and return
        {field_name: string_literal_value} for those initialised with a string literal.
        """
        self._parse()
        if not self._tree:
            return {}
        results = {}
        for _, node in self._tree.filter(javalang.tree.FieldDeclaration):
            for decl in node.declarators:
                if decl.name in field_names and decl.initializer:
                    init = decl.initializer
                    if isinstance(init, javalang.tree.Literal) and init.value:
                        val = init.value.strip('"').strip("'")
                        results[decl.name] = val
        return results

    def all_string_literals(self) -> List[str]:
        """Return every string literal value in the file."""
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.Literal):
            if node.value and node.value.startswith('"'):
                results.append(node.value.strip('"'))
        return results

    # ── Method / invocation queries ────────────────────────────────────────

    def method_names(self) -> Set[str]:
        """Return the set of all method names declared in the file."""
        self._parse()
        if not self._tree:
            return set()
        names = set()
        for _, node in self._tree.filter(javalang.tree.MethodDeclaration):
            names.add(node.name)
        return names

    def invocations_of(self, method_name: str) -> List:
        """Return all MethodInvocation nodes where the method name matches."""
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.MethodInvocation):
            if node.member == method_name:
                results.append(node)
        return results

    def object_creations_of(self, class_name: str) -> List:
        """Return all ClassCreator nodes where the type matches class_name."""
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassCreator):
            if hasattr(node.type, 'name') and node.type.name == class_name:
                results.append(node)
        return results

    def all_object_creation_types(self) -> List[str]:
        """Return the class name for every 'new Foo(...)' in the file."""
        self._parse()
        if not self._tree:
            return []
        results = []
        for _, node in self._tree.filter(javalang.tree.ClassCreator):
            if hasattr(node.type, 'name'):
                results.append(node.type.name)
        return results

    # ── Method-body extraction ─────────────────────────────────────────────

    def method_body_source(self, method_name: str) -> Optional[str]:
        """
        Return a substring of the source that contains the body of the first
        method named method_name.  Uses position info if available, otherwise
        falls back to a simple brace-scan from the method's start position.
        """
        self._parse()
        if not self._tree:
            return None
        for _, node in self._tree.filter(javalang.tree.MethodDeclaration):
            if node.name != method_name:
                continue
            if node.position:
                # Slice from the method's line; find opening brace
                lines = self._src.splitlines()
                start_line = node.position.line - 1  # 0-indexed
                snippet = "\n".join(lines[start_line:start_line + 200])
                brace_open = snippet.find('{')
                if brace_open == -1:
                    return snippet
                depth, i = 0, brace_open
                while i < len(snippet):
                    if snippet[i] == '{':
                        depth += 1
                    elif snippet[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return snippet[brace_open:i + 1]
                    i += 1
                return snippet[brace_open:]
        return None

    # ── instanceof checks ──────────────────────────────────────────────────

    def instanceof_types(self) -> Set[str]:
        """Return all type names used in instanceof expressions."""
        self._parse()
        if not self._tree:
            return set()
        types = set()
        for _, node in self._tree.filter(javalang.tree.BinaryOperation):
            if node.operator == 'instanceof' and hasattr(node.operandr, 'name'):
                types.add(node.operandr.name)
        # javalang models instanceof differently across versions; also check MemberReference
        for _, node in self._tree.filter(javalang.tree.MethodInvocation):
            pass  # covered by BinaryOperation above
        return types

    # ── Generic-argument stripping ─────────────────────────────────────────

    @staticmethod
    def strip_generics(name: str) -> str:
        """Remove generic type parameters: 'Foo<Bar>' -> 'Foo'."""
        idx = name.find('<')
        return name[:idx].strip() if idx != -1 else name.strip()

    # ── First string argument helper ───────────────────────────────────────

    @staticmethod
    def first_string_arg(invocation_node) -> Optional[str]:
        """
        Given a MethodInvocation or ClassCreator node, return the value of the
        first string-literal argument, or None.
        """
        args = getattr(invocation_node, 'arguments', None) or []
        for arg in args:
            if isinstance(arg, javalang.tree.Literal) and arg.value and arg.value.startswith('"'):
                return arg.value.strip('"')
        return None

# === CONFIG ===
OUTPUT_DIR = "Bedrock_Pack"
BP_FOLDER = os.path.join(OUTPUT_DIR, "bp")
RP_FOLDER = os.path.join(OUTPUT_DIR, "rp")

# Primary (modern) format for BP/RP entity/item/block files
BP_RP_FORMAT_VERSION = "1.21.0"
# Legacy formats required for some Bedrock subsystems (render controllers, animations, sounds)
RP_LEGACY_RENDER_FORMAT = "1.10.0"
RP_LEGACY_ANIM_FORMAT = "1.10.0"

# Valid pack icon sizes (validator accepts these)
VALID_ICON_SIZES = [2, 4, 8, 16, 32, 64, 128, 256]

JAVA_GOAL_PRIORITIES = {
    "FloatGoal": 0, "SwimGoal": 0, "BreatheAirGoal": 0,
    "NearestAttackableTargetGoal": 1, "NearestAttackableTargetExpiringGoal": 1,
    "ToggleableNearestAttackableTargetGoal": 1, "NonTamedTargetGoal": 1,
    "DefendVillageTargetGoal": 1, "HurtByTargetGoal": 2,
    "OwnerHurtByTargetGoal": 2, "OwnerHurtTargetGoal": 2, "ResetAngerGoal": 2,
    "MeleeAttackGoal": 3, "OcelotAttackGoal": 3, "CreeperSwellGoal": 3,
    "RangedAttackGoal": 3, "RangedBowAttackGoal": 3, "RangedCrossbowAttackGoal": 3,
    "LeapAtTargetGoal": 4, "MoveTowardsTargetGoal": 4,
    "AvoidEntityGoal": 5, "PanicGoal": 5, "RunAroundLikeCrazyGoal": 5,
    "FleeSunGoal": 5, "RestrictSunGoal": 5,
    "OpenDoorGoal": 6, "InteractDoorGoal": 6, "BreakDoorGoal": 6,
    "BreakBlockGoal": 6, "UseItemGoal": 6,
    "FollowOwnerGoal": 7, "FollowParentGoal": 7, "FollowMobGoal": 7,
    "FollowBoatGoal": 7, "FollowSchoolLeaderGoal": 7, "LlamaFollowCaravanGoal": 7,
    "LandOnOwnersShoulderGoal": 7, "MoveToBlockGoal": 7,
    "MoveTowardsRestrictionGoal": 7, "MoveThroughVillageGoal": 7,
    "MoveThroughVillageAtNightGoal": 7, "MoveTowardsRaidGoal": 7,
    "ReturnToVillageGoal": 7, "PatrolVillageGoal": 7, "FindWaterGoal": 7,
    "SitWhenOrderedToGoal": 7, "SitGoal": 7,
    "BreedGoal": 8, "TemptGoal": 8, "EatGrassGoal": 8, "BegGoal": 8,
    "TradeWithPlayerGoal": 8, "LookAtCustomerGoal": 8, "ShowVillagerFlowerGoal": 8,
    "TriggerSkeletonTrapGoal": 8, "DolphinJumpGoal": 8, "JumpGoal": 8,
    "CatLieOnBedGoal": 8, "CatSitOnBlockGoal": 8,
    "WaterAvoidingRandomStrollGoal": 8, "RandomWalkingGoal": 8,
    "RandomSwimmingGoal": 8, "RandomStrollGoal": 8,
    "LookAtGoal": 9, "LookAtPlayerGoal": 9, "LookAtWithoutMovingGoal": 9,
    "LookRandomlyGoal": 10, "RandomLookAroundGoal": 10,
}

# Collected sound definitions from JAR assets (merged and written to rp/sounds.json)
COLLECTED_SOUND_DEFS: Dict[str, dict] = {}

# Maps Bedrock entity identifier -> sounds.json entry (RP root sounds.json,
# distinct from sound_definitions.json).  Written by generate_sounds_registry().
_ENTITY_SOUND_EVENTS: Dict[str, dict] = {}

# -------------------------
# Helpers
# -------------------------
def ensure_dirs():
    rp_subs = [
        "textures",
        "textures/blocks",
        "textures/items",
        "textures/entity",
        "sound",
        "sounds",  # for sound_definitions.json
        "models",
        "animations",
        "items",
        "entity",  # singular 'entity' folder required by Bedrock
        "render_controllers",
        "geometry",
        "lang",
        "assets",
        "misc",
        "biome_modifiers"
    ]
    bp_subs = [
        "entities",
        "items",
        "blocks",
        "functions",
        "scripts",
        "animations",
        "data",
        "recipes",
        "loot_tables"
    ]
    for folder, subs in [(RP_FOLDER, rp_subs), (BP_FOLDER, bp_subs)]:
        os.makedirs(folder, exist_ok=True)
        for s in subs:
            os.makedirs(os.path.join(folder, s), exist_ok=True)

def create_manifest(pack_name: str, pack_type: str):
    return {
        "format_version": 2,
        "header": {
            "name": pack_name,
            "description": f"{pack_name} converted pack",
            "uuid": str(uuid.uuid4()),
            "version": [1, 0, 0],
            "min_engine_version": [1, 21, 0]
        },
        "modules": [
            {
                "type": "resources" if pack_type == "RP" else "data",
                "uuid": str(uuid.uuid4()),
                "version": [1, 0, 0]
            }
        ]
    }

def write_manifest_for(folder: str, pack_name: str, pack_type: str):
    path = os.path.join(folder, "manifest.json")
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(create_manifest(pack_name, pack_type), f, indent=4)

def sanitize_identifier(name: Optional[str]) -> str:
    """Lowercase, replace whitespace with underscore, allow a-z0-9_. only, collapse underscores/dots."""
    if not name:
        return ""
    s = str(name).strip().lower()
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^a-z0-9_\.]', '_', s)
    s = re.sub(r'_+', '_', s)
    s = re.sub(r'\.+', '.', s)
    s = s.strip('._')
    return s

def sanitize_filename_keep_ext(filename: str) -> str:
    """Lowercase basename, replace spaces and hyphens with underscores, keep extension."""
    base, ext = os.path.splitext(filename)
    base_s = base.lower()
    base_s = re.sub(r'[\s\-]+', '_', base_s)  # spaces and hyphens -> underscores
    base_s = re.sub(r'[^a-z0-9_\.]', '_', base_s)
    base_s = re.sub(r'_+', '_', base_s)
    base_s = base_s.strip('._')
    ext_s = ext.lower()
    return base_s + ext_s

def build_geometry_id(namespace: Optional[str], name: str) -> str:
    n = sanitize_identifier(name)
    if namespace:
        ns = sanitize_identifier(namespace)
        if ns:
            return f"geometry.{ns}.{n}"
    return f"geometry.{n}"

def safe_write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

def find_jar_file(search_dir=".") -> Optional[str]:
    # Skip auxiliary JARs (sources, javadoc, api, slim, dev classifiers)
    SKIP_SUFFIXES = ("-sources.jar", "-javadoc.jar", "-api.jar", "-slim.jar", "-dev.jar")
    candidates = []
    for f in os.listdir(search_dir):
        if not f.endswith(".jar"):
            continue
        if any(f.lower().endswith(s) for s in SKIP_SUFFIXES):
            print(f"[jar] Skipping auxiliary JAR: {f}")
            continue
        candidates.append(os.path.join(search_dir, f))
    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"[jar] WARNING: Multiple JAR files found: {[os.path.basename(c) for c in candidates]}")
        print(f"[jar] Using: {os.path.basename(candidates[0])} — move others out of this directory if wrong.")
    return candidates[0]

def detect_loader_from_jar(jar_path: str) -> str:
    """
    Detect the mod loader type from a JAR file by inspecting META-INF.
    Returns one of: 'neoforge', 'forge', 'fabric', 'quilt', or 'unknown'.
    """
    try:
        with zipfile.ZipFile(jar_path, 'r') as jar:
            names_lower = [n.lower() for n in jar.namelist()]
            if any("meta-inf/neoforge.mods.toml" in n for n in names_lower):
                return "neoforge"
            if any("meta-inf/mods.toml" in n for n in names_lower):
                return "forge"
            if any("fabric.mod.json" in n for n in names_lower):
                return "fabric"
            if any("quilt.mod.json" in n for n in names_lower):
                return "quilt"
    except Exception:
        pass
    return "unknown"


    """
    Extract the first file that ends with 'logo.png' (case-insensitive).
    Returns path to the extracted file inside a temporary extraction folder, or None if not found.
    """
    temp_dir = ".temp_logo_extract"
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file in jar.namelist():
            if file.lower().endswith("logo.png"):
                jar.extract(file, temp_dir)
                return os.path.join(temp_dir, file)
    return None

def sanitize_path_parts(path_str: str) -> List[str]:
    """Sanitize each part of a path but keep the final filename extension using sanitize_filename_keep_ext."""
    parts = path_str.replace("\\", "/").split("/")
    if not parts:
        return []
    sanitized = []
    for p in parts[:-1]:
        sanitized.append(sanitize_identifier(p) or "_")
    sanitized.append(sanitize_filename_keep_ext(parts[-1]))
    return sanitized

# -------------------------
# Asset copying (sanitizing filenames) with improved JSON heuristics
# -------------------------
def _normalize_texture_subfolder(token: str) -> str:
    token = token.lower()
    if token in ("block", "blocks", "blockstate", "blockstates"):
        return "blocks"
    if token in ("item", "items"):
        return "items"
    if token in ("entity", "entities", "mob", "mobs"):
        return "entity"
    return token

def _read_json_from_jar(jar, file_path: str) -> Optional[dict]:
    try:
        with jar.open(file_path) as fh:
            raw = fh.read().decode('utf-8')
            return json.loads(raw)
    except Exception:
        return None

def copy_assets_from_jar(jar_path: str, resource_pack: str):
    """
    Copy assets from JAR into resource_pack (RP_FOLDER), with heuristics to route JSON files
    into the correct locations and to collect sound definitions for a merged sounds.json.
    """
    global COLLECTED_SOUND_DEFS
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file in jar.namelist():
            normalized = file.replace("\\", "/")
            lower_file = normalized.lower()
            try:
                # TEXTURES (assets/.../textures/...)
                if lower_file.endswith(".png") and "/textures/" in lower_file:
                    parts = normalized.split('/')
                    try:
                        idx = [p.lower() for p in parts].index("textures")
                        after = parts[idx + 1:]
                    except ValueError:
                        after = parts[-1:]
                    if after:
                        first = after[0].lower()
                        category = _normalize_texture_subfolder(first)
                        if len(after) > 1:
                            dest_dir = os.path.join(resource_pack, "textures", category, *[sanitize_identifier(p) for p in after[1:-1]])
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_name = sanitize_filename_keep_ext(after[-1])
                            dest = os.path.join(dest_dir, dest_name)
                        else:
                            dest_dir = os.path.join(resource_pack, "textures", category)
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_name = sanitize_filename_keep_ext(after[0])
                            dest = os.path.join(dest_dir, dest_name)
                    else:
                        dest = os.path.join(resource_pack, "textures", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue

                # other PNGs (fallback)
                if lower_file.endswith(".png"):
                    dest = os.path.join(resource_pack, "textures", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue

                # OGG sounds -> always copy into rp/sounds/
                # sanitize_filename_keep_ext converts hyphens to underscores,
                # keeping the on-disk name in sync with the sanitized key in sound_definitions.json
                if lower_file.endswith(".ogg"):
                    dest = os.path.join(resource_pack, "sound", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue

                # Geometry files -> geometry + models
                if lower_file.endswith(".geo.json") or lower_file.endswith(".geo"):
                    dest_geo = os.path.join(resource_pack, "geometry", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest_geo), exist_ok=True)
                    with jar.open(file) as src_file, open(dest_geo, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    dest_model = os.path.join(resource_pack, "models", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest_model), exist_ok=True)
                    with jar.open(file) as src_file, open(dest_model, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue

                # models -> RP/models (and attempt GeckoLib conversion for vanilla models)
                if (lower_file.endswith(".json") and "/models/" in lower_file) or lower_file.endswith(".geo.json"):
                    dest = os.path.join(resource_pack, "models", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    # Also attempt conversion to GeckoLib geometry for non-GeckoLib mods
                    if lower_file.endswith(".json") and "/models/" in lower_file and not lower_file.endswith(".geo.json"):
                        try_convert_model_from_jar(jar, file, resource_pack)
                    continue

                # animations -> RP/animations
                if lower_file.endswith(".json") and "/animations/" in lower_file:
                    dest = os.path.join(resource_pack, "animations", sanitize_filename_keep_ext(os.path.basename(file)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with jar.open(file) as src_file, open(dest, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
                    continue

                # JSON routing heuristics (try to parse & route sensibly)
                if lower_file.endswith(".json"):
                    # Catch any sounds.json / sound_definitions JSON anywhere in the JAR -> merge and discard
                    if os.path.basename(lower_file) in ("sounds.json", "sound_definitions.json") or                        (os.path.basename(lower_file).startswith("sounds") and lower_file.endswith(".json") and "/sounds/" in lower_file):
                        j = _read_json_from_jar(jar, file)
                        if isinstance(j, dict):
                            defs = j.get("sound_definitions", j) if isinstance(j.get("sound_definitions"), dict) else j
                            for k, v in defs.items():
                                if not isinstance(v, dict):
                                    continue
                                bare_k = k.split(":")[-1]
                                clean_k = sanitize_sound_key(bare_k)
                                if clean_k not in COLLECTED_SOUND_DEFS:
                                    cleaned = _sanitize_sound_def(v)
                                    if not cleaned.get("sounds"):
                                        cleaned["sounds"] = [{"name": f"sound/{clean_k}"}]
                                    COLLECTED_SOUND_DEFS[clean_k] = cleaned
                        continue
                    # if file is from /data/ -> go to BP preserving subpath
                    if "/data/" in lower_file:
                        sub = normalized.split("/data/", 1)[1]
                        parts = sanitize_path_parts(sub)
                        dest = os.path.join(BP_FOLDER, *parts)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with jar.open(file) as src_file, open(dest, "wb") as out_file:
                            shutil.copyfileobj(src_file, out_file)
                        continue

                    # if it's under assets/ try to route by subfolder
                    if "/assets/" in lower_file:
                        sub = normalized.split("/assets/", 1)[1]
                        parts_raw = sub.split("/")
                        # drop top-level modid if present
                        sub_after = "/".join(parts_raw[1:]) if len(parts_raw) > 1 else sub
                        lower_after = sub_after.lower()

                        # SOUND JSONS inside assets/.../sounds/ or any file named sounds*.json -> merge into collected sound defs
                        if "/sounds/" in lower_after or os.path.basename(lower_after).startswith("sounds") or os.path.basename(lower_after) == "sounds.json":
                            j = _read_json_from_jar(jar, file)
                            if isinstance(j, dict):
                                # if it is already a "sound_definitions" root, merge the sub-dict if present
                                defs = j.get("sound_definitions", j) if isinstance(j.get("sound_definitions"), dict) else j
                                for k, v in defs.items():
                                    if not isinstance(v, dict):
                                        continue
                                    # strip namespace prefix (e.g. "the_one_who_watches:scream_1" -> "scream_1")
                                    bare_k = k.split(":")[-1]
                                    clean_k = sanitize_sound_key(bare_k)
                                    # only add if not already present (ogg scanner takes priority)
                                    if clean_k not in COLLECTED_SOUND_DEFS:
                                        cleaned = _sanitize_sound_def(v)
                                        # if the imported def has no sounds list, generate one
                                        if not cleaned.get("sounds"):
                                            cleaned["sounds"] = [{"name": f"sound/{clean_k}"}]
                                        COLLECTED_SOUND_DEFS[clean_k] = cleaned
                            # do not copy sound JSON fragments to rp/misc
                            continue

                        # LANG files
                        if "/lang/" in lower_after or lower_after.startswith("lang"):
                            if "/lang/" in lower_after:
                                after = sub_after.split("/lang/", 1)[1]
                            else:
                                after = os.path.basename(sub_after)
                            dest = os.path.join(resource_pack, "lang", sanitize_filename_keep_ext(os.path.basename(after)))
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with jar.open(file) as src_file, open(dest, "wb") as out_file:
                                shutil.copyfileobj(src_file, out_file)
                            continue

                        # TEXTURES handled earlier, MODELS handled earlier

                        # Skip Java-only asset types that have no Bedrock equivalent
                        fname_base = os.path.basename(lower_after)
                        # Java block/item model JSONs (not Bedrock models) -> discard
                        if any(seg in lower_after for seg in ("/blockstates/", "/models/block/", "/models/item/")):
                            continue
                        # Java tool/item type JSONs (axe, shovel, sword etc.) -> discard
                        if fname_base in ("axe.json", "shovel.json", "sword.json", "pickaxe.json",
                                          "hoe.json", "bow.json", "crossbow.json", "trident.json"):
                            continue
                        # Biome modifier JSONs -> discard (Forge/NeoForge server-side, no Bedrock equivalent)
                        if "biome_modifier" in fname_base or "biome_modifier" in lower_after:
                            continue
                        # NeoForge-specific data-gen folders with no Bedrock equivalent -> discard
                        # e.g. data/<modid>/neoforge/biome_modifiers/, data/<modid>/neoforge/global_loot_modifiers/
                        if "/neoforge/" in lower_after:
                            continue
                        # Java recipe JSONs -> route to bp/recipes (handled by process_recipes_from_jar)
                        # but if they land here discard to avoid misc pollution
                        if "/recipes/" in lower_after or fname_base.endswith("_recipe.json") or fname_base.endswith("_recipes.json"):
                            continue
                        # Lang files named en_us.json etc -> rp/lang
                        if re.match(r"[a-z]{2}_[a-z]{2}\.json$", fname_base):
                            dest = os.path.join(resource_pack, "lang", sanitize_filename_keep_ext(fname_base))
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with jar.open(file) as src_file, open(dest, "wb") as out_file:
                                shutil.copyfileobj(src_file, out_file)
                            continue
                        # fallback for other assets: try parse and route by content
                        j = _read_json_from_jar(jar, file)
                        if isinstance(j, dict):
                            # item JSON -> rp/items (if it looks like a client item)
                            if "minecraft:item" in j or ("item" in j and isinstance(j.get("item"), dict)):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                # normalize extension to .item.json for clarity
                                if not destname.endswith(".item.json"):
                                    destname = os.path.splitext(destname)[0] + ".item.json"
                                dest = os.path.join(resource_pack, "items", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            # block JSON -> bp/blocks
                            if "minecraft:block" in j or ("block" in j and isinstance(j.get("block"), dict)):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(BP_FOLDER, "blocks", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            # client_entity -> rp/entity
                            if "minecraft:client_entity" in j or "minecraft:entity" in j:
                                destname = sanitize_identifier(os.path.splitext(os.path.basename(file))[0]) + ".entity.json"
                                dest = os.path.join(resource_pack, "entity", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            # recipe-like -> bp/recipes
                            if "recipe" in os.path.basename(file).lower() or "recipe" in lower_after or                                "recipes" in j or any("ingredient" in str(k).lower() for k in j.keys()):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(BP_FOLDER, "recipes", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            # biome modifiers -> BP/data (Forge/NeoForge server-side, not a Bedrock RP asset)
                            if "biome_modifier" in os.path.basename(file).lower() or                                "biome_modifier" in lower_after or                                any("biome" in str(k).lower() for k in j.keys()):
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(BP_FOLDER, "data", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue
                            # locale mapping -> rp/lang (heuristic: many string values)
                            if all(isinstance(v, str) for v in j.values()) and len(j) > 10:
                                destname = sanitize_filename_keep_ext(os.path.basename(file))
                                dest = os.path.join(resource_pack, "lang", destname)
                                os.makedirs(os.path.dirname(dest), exist_ok=True)
                                with open(dest, "w", encoding="utf-8") as fh:
                                    json.dump(j, fh, indent=2)
                                continue

                        # If we still couldn't route it, discard silently
                        # (Java-only assets like tool JSONs, block states, etc. have no Bedrock equivalent)
                        continue

                    # If not under assets or data, also discard
                    continue

                # else skip unknown file types
                continue

            except Exception as ex:
                print(f"[asset copy error] {file} -> {ex}")

# -------------------------
# Vanilla Java model -> GeckoLib geometry converter
# Handles non-GeckoLib MCreator mods (pre-GeckoLib era and vanilla renderer mods)
# -------------------------
def convert_vanilla_model_to_geckolib(classic: dict, model_name: str = "model") -> dict:
    """
    Convert a vanilla Minecraft block/entity model JSON to GeckoLib .geo.json format.
    Works on any Blockbench-exported or MCreator-generated vanilla model.
    """
    bones = []

    elements = classic.get("elements", [])
    groups   = classic.get("groups", [])
    tex_size = classic.get("texture_size", [16, 16])

    def extract_uv(element: dict):
        faces = element.get("faces", {})
        north = faces.get("north", {}).get("uv", [0, 0, 16, 16])
        return [north[0], north[1]]

    def convert_rotation(rot: dict) -> dict:
        axis  = rot.get("axis", "x")
        angle = rot.get("angle", 0)
        return {
            "x": angle if axis == "x" else 0,
            "y": angle if axis == "y" else 0,
            "z": angle if axis == "z" else 0,
        }

    def element_to_cube(el: dict) -> dict:
        from_pos = el["from"]
        to_pos   = el["to"]
        cube = {
            "origin": [from_pos[0] - 8, from_pos[1], from_pos[2] - 8],
            "size":   [to_pos[0] - from_pos[0], to_pos[1] - from_pos[1], to_pos[2] - from_pos[2]],
            "uv":     extract_uv(el),
        }
        if "rotation" in el:
            cube["rotation"] = convert_rotation(el["rotation"])
        return cube

    def process_group(group):
        if isinstance(group, int):
            return  # bare element index at top level — handled below
        bone = {
            "name":   group.get("name", "bone"),
            "pivot":  [group["origin"][0] - 8, group["origin"][1], group["origin"][2] - 8],
            "cubes":  [],
        }
        for child in group.get("children", []):
            if isinstance(child, int) and child < len(elements):
                bone["cubes"].append(element_to_cube(elements[child]))
            elif isinstance(child, dict):
                process_group(child)  # nested groups become sibling bones
        bones.append(bone)

    if groups:
        for group in groups:
            process_group(group)
    else:
        # No groups — wrap everything in a single root bone
        root = {"name": "root", "pivot": [0, 0, 0], "cubes": []}
        for el in elements:
            root["cubes"].append(element_to_cube(el))
        bones.append(root)

    return {
        "format_version": "1.12.0",
        "minecraft:geometry": [
            {
                "description": {
                    "identifier":            f"geometry.{model_name}",
                    "texture_width":         tex_size[0],
                    "texture_height":        tex_size[1],
                    "visible_bounds_width":  2,
                    "visible_bounds_height": 2,
                    "visible_bounds_offset": [0, 1, 0],
                },
                "bones": bones,
            }
        ],
    }


def try_convert_model_from_jar(jar, file_path: str, resource_pack: str) -> bool:
    """
    Try to read a vanilla model JSON from the JAR, convert it to GeckoLib geometry,
    and write it to RP/geometry/. Returns True if conversion succeeded.
    """
    try:
        with jar.open(file_path) as fh:
            data = json.loads(fh.read().decode("utf-8"))
    except Exception:
        return False

    # Must have elements to be a geometry model (not a blockstate or item override)
    if "elements" not in data and "groups" not in data:
        return False

    model_name = sanitize_identifier(os.path.splitext(os.path.basename(file_path))[0])
    try:
        geckolib_data = convert_vanilla_model_to_geckolib(data, model_name)
    except Exception as e:
        print(f"[model-convert] Failed to convert {file_path}: {e}")
        return False

    out_path = os.path.join(resource_pack, "geometry", f"{model_name}.geo.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    safe_write_json(out_path, geckolib_data)
    print(f"[model-convert] Converted vanilla model -> GeckoLib: {file_path} -> {out_path}")
    return True


def copy_geckolib_animations_from_jar(jar_path: str, resource_pack: str):
    with zipfile.ZipFile(jar_path, 'r') as jar:
        for file in jar.namelist():
            lower = file.lower()
            if ("animation" in lower and lower.endswith(".json")) or ("/animations/" in lower and lower.endswith(".json")):
                dest_name = sanitize_filename_keep_ext(os.path.basename(file))
                dest = os.path.join(resource_pack, "animations", dest_name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with jar.open(file) as src_file, open(dest, "wb") as out_file:
                    shutil.copyfileobj(src_file, out_file)
                print(f"Copied animation file from JAR: {file} -> {dest}")

# -------------------------
# Texture registry generation
# -------------------------
def rp_texture_exists(texture_path_without_ext: str) -> bool:
    # texture_path_without_ext is like 'entity/toww_reborn' or 'toww_reborn'
    variants = [
        os.path.join(RP_FOLDER, "textures", texture_path_without_ext + ".png"),
        os.path.join(RP_FOLDER, "textures", texture_path_without_ext, os.path.basename(texture_path_without_ext) + ".png"),
        os.path.join(RP_FOLDER, "textures", os.path.basename(texture_path_without_ext) + ".png")
    ]
    for p in variants:
        if os.path.exists(p):
            return True
    return False

def resolve_texture_reference(namespace: str, texture_hint: Optional[str], kind_hint: str, fallback_name: Optional[str] = None) -> str:
    """
    Return a namespaced reference WITHOUT .png suffix.
    Examples: 'modmorpher:entity/toww_reborn' or 'modmorpher:toww_reborn'
    """
    ns = sanitize_identifier(namespace) or "converted"
    if texture_hint:
        candidate = texture_hint.split(":")[-1]
        candidate = candidate.replace(".png", "")
        candidate = candidate.strip("/")
        # try with kind_hint prefix
        probe = f"{kind_hint}/{candidate}"
        if rp_texture_exists(probe):
            return f"{ns}:{probe}"
        if rp_texture_exists(candidate):
            return f"{ns}:{candidate}"
        # fall back to sanitized candidate
        cand_s = sanitize_identifier(candidate)
        return f"{ns}:{kind_hint}/{cand_s}"
    if fallback_name:
        probe = f"{kind_hint}/{fallback_name}"
        if rp_texture_exists(probe):
            return f"{ns}:{probe}"
        if rp_texture_exists(fallback_name):
            return f"{ns}:{fallback_name}"
        return f"{ns}:{kind_hint}/{sanitize_identifier(fallback_name)}"
    return f"{ns}:{kind_hint}/{sanitize_identifier(fallback_name or 'missing_texture')}"

def texture_ref_to_rp_path(texture_ref: Optional[str], default_kind: str = "entity") -> str:
    """
    Convert namespaced ref like 'mod:entity/toww_reborn' -> 'entity/toww_reborn'
    Note: KEEP NO .png suffix here (client_entity expects no extension).
    """
    if not texture_ref:
        return f"{default_kind}/missing_texture"
    path = texture_ref.split(":", 1)[-1]
    # strip any leading 'textures/' so RP client-entity JSONs reference 'entity/...' rather than 'textures/entity/...'
    if path.startswith("textures/"):
        path = path[len("textures/"):]
    return path

def generate_texture_registry(pack_name: str):
    item_textures: Dict[str, Dict[str, str]] = {}
    block_textures: Dict[str, Dict[str, str]] = {}

    items_dir = os.path.join(RP_FOLDER, "textures", "items")
    blocks_dir = os.path.join(RP_FOLDER, "textures", "blocks")

    if os.path.isdir(items_dir):
        for root, _, files in os.walk(items_dir):
            for file in files:
                if file.lower().endswith(".png"):
                    rel_dir = os.path.relpath(root, os.path.join(RP_FOLDER, "textures", "items"))
                    name = os.path.splitext(file)[0]
                    if rel_dir != ".":
                        key = os.path.join(rel_dir, name).replace("\\", "/")
                    else:
                        key = name
                    item_textures[key] = {"textures": f"textures/items/{key}"}

    if os.path.isdir(blocks_dir):
        for root, _, files in os.walk(blocks_dir):
            for file in files:
                if file.lower().endswith(".png"):
                    rel_dir = os.path.relpath(root, os.path.join(RP_FOLDER, "textures", "blocks"))
                    name = os.path.splitext(file)[0]
                    if rel_dir != ".":
                        key = os.path.join(rel_dir, name).replace("\\", "/")
                    else:
                        key = name
                    block_textures[key] = {"textures": f"textures/blocks/{key}"}

    item_registry = {
        "resource_pack_name": pack_name,
        "texture_name": "atlas.items",
        "texture_data": item_textures
    }
    item_path = os.path.join(RP_FOLDER, "textures", "item_texture.json")
    safe_write_json(item_path, item_registry)

    terrain_registry = {
        "resource_pack_name": pack_name,
        "texture_name": "atlas.terrain",
        "texture_data": block_textures
    }
    terrain_path = os.path.join(RP_FOLDER, "textures", "terrain_texture.json")
    safe_write_json(terrain_path, terrain_registry)
    print("Generated texture atlases (item_texture.json and terrain_texture.json).")

# -------------------------
# Geometry & animation normalization
# -------------------------
def normalize_geometry_file_identifiers():
    geom_dir = os.path.join(RP_FOLDER, "geometry")
    if not os.path.isdir(geom_dir):
        return
    for fname in os.listdir(geom_dir):
        if not (fname.lower().endswith(".geo.json") or fname.lower().endswith(".geo")):
            continue
        path = os.path.join(geom_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            try:
                txt = open(path, "r", encoding="utf-8", errors="ignore").read()
                m = re.search(r'"identifier"\s*:\s*["\']([^"\']+)["\']', txt)
                if not m:
                    continue
                orig = m.group(1)
                if orig.startswith("geometry."):
                    tail = orig.split(".", 1)[1]
                    newidf = "geometry." + sanitize_identifier(tail)
                else:
                    newidf = "geometry." + sanitize_identifier(orig)
                txt2 = txt.replace(m.group(0), f'"identifier": "{newidf}"')
                with open(path, "w", encoding="utf-8") as fh2:
                    fh2.write(txt2)
                print(f"[geom-normalize] Rewrote identifier in {path}: {orig} -> {newidf}")
            except Exception:
                continue
            continue

        def set_identifiers(obj):
            changed = False
            if isinstance(obj, dict):
                for k, v in list(obj.items()):
                    if k == "identifier" and isinstance(v, str):
                        orig = v
                        if orig.startswith("geometry."):
                            tail = orig.split(".", 1)[1]
                            newidf = "geometry." + sanitize_identifier(tail)
                        else:
                            newidf = "geometry." + sanitize_identifier(orig)
                        obj[k] = newidf
                        changed = True
                    else:
                        ch = set_identifiers(v)
                        changed = changed or ch
            elif isinstance(obj, list):
                for item in obj:
                    ch = set_identifiers(item)
                    changed = changed or ch
            return changed

        changed = set_identifiers(data)
        if changed:
            safe_write_json(path, data)
            print(f"[geom-normalize] Normalized identifiers in {path}")

def fix_animation_format_versions():
    """Fix any animation files with format_version 1.8.0 -> 1.10.0."""
    for folder in [os.path.join(RP_FOLDER, "animations"), os.path.join(BP_FOLDER, "animations")]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(folder, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("format_version") == "1.8.0":
                    data["format_version"] = "1.10.0"
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    print(f"[anim] Fixed format_version 1.8.0->1.10.0 in {fname}")
            except Exception:
                pass

def sanitize_animation_keys_in_files():
    anim_dir = os.path.join(RP_FOLDER, "animations")
    if not os.path.isdir(anim_dir):
        return
    for fname in os.listdir(anim_dir):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(anim_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        anims = data.get("animations")
        if not isinstance(anims, dict):
            continue
        new_anims = {}
        changed = False
        for k, v in anims.items():
            new_key = canonicalize_animation_id(k)
            if not new_key:
                new_key = k  # don't destroy a key we can't sanitize
            if new_key != k or new_key in new_anims:
                changed = True
            if new_key in new_anims:
                # Prefer first-seen key to avoid silently replacing earlier animation bodies.
                continue
            new_anims[new_key] = v
        if changed:
            data["animations"] = new_anims
            safe_write_json(path, data)
            print(f"[anim-normalize] Normalized animation keys in {path}")

def canonicalize_animation_id(raw: str, namespace: Optional[str] = None, entity_name: Optional[str] = None) -> str:
    """
    Normalize an animation identifier to Bedrock-style:
      animation.<namespace>.<entity>.<motion>

    Rejects anything whose final segment does not contain a recognised motion
    keyword -- prevents class names and random string literals becoming IDs.
    """
    MOTION_KEYWORDS = {
        "idle", "stand", "pose", "float",
        "walk", "walking",
        "run", "running", "chase", "sprint",
        "attack", "strike", "bite", "swipe", "slam", "lunge", "claw",
        "hurt", "hit", "flinch", "pain",
        "death", "die", "dying", "dead",
        "sit", "sitting", "crouch", "lay",
        "swim", "swimming",
        "fly", "flying", "hover", "glide",
        "sleep", "sleeping", "rest",
        "spawn", "appear", "emerge", "summon",
        "open", "close", "blink", "tail", "wing", "flap",
    }

    if raw is None:
        return ""
    s = str(raw).strip().strip('"')
    s = s.strip("'")
    if not s:
        return ""

    s = s.replace("\\", "/")
    s = re.sub(r'\.json$', '', s, flags=re.I)
    if s.lower().startswith("animations/"):
        s = s.split("/", 1)[1]
    s = s.replace("/", ".")

    ns = sanitize_identifier(namespace) if namespace else ""
    ent = sanitize_identifier(entity_name) if entity_name else ""

    if s.startswith("animation."):
        tail = s[len("animation."):]
        parts = [sanitize_identifier(p) for p in tail.split(".")]
        parts = [p for p in parts if p]
        if not parts:
            return ""
        last = parts[-1].lower()
        if not any(kw in last for kw in MOTION_KEYWORDS):
            return ""
        return "animation." + ".".join(parts)

    bare = sanitize_identifier(s)
    if not bare:
        return ""
    if not any(kw in bare.lower() for kw in MOTION_KEYWORDS):
        return ""

    if ns and ent:
        if bare.startswith(f"{ns}.{ent}."):
            return f"animation.{bare}"
        if bare.startswith(f"{ent}."):
            return f"animation.{ns}.{bare}"
        return f"animation.{ns}.{ent}.{bare}"
    if ns:
        if bare.startswith(f"{ns}."):
            return f"animation.{bare}"
        return f"animation.{ns}.{bare}"
    return f"animation.{bare}"

def load_geometry_identifiers() -> Tuple[Dict[str, str], Dict[Tuple[Optional[str], Optional[str]], str]]:
    map_by_file = {}
    map_by_ns_name = {}
    geom_dir = os.path.join(RP_FOLDER, "geometry")
    if not os.path.isdir(geom_dir):
        return map_by_file, map_by_ns_name
    for fname in os.listdir(geom_dir):
        if not (fname.lower().endswith(".geo.json") or fname.lower().endswith(".geo")):
            continue
        path = os.path.join(geom_dir, fname)
        identifier = None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            try:
                txt = open(path, "r", encoding="utf-8", errors="ignore").read()
                m = re.search(r'"identifier"\s*:\s*["\']([^"\']+)["\']', txt)
                identifier = m.group(1) if m else None
            except Exception:
                identifier = None
        else:
            def find_identifier(obj):
                if isinstance(obj, dict):
                    if "identifier" in obj and isinstance(obj["identifier"], str):
                        return obj["identifier"]
                    for v in obj.values():
                        res = find_identifier(v)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = find_identifier(item)
                        if res:
                            return res
                return None
            identifier = find_identifier(data)
        basename = os.path.splitext(os.path.splitext(fname)[0])[0]
        basename_norm = sanitize_identifier(basename) or basename.lower()
        if identifier:
            map_by_file[basename_norm] = identifier
            parts = identifier.split(".")
            if len(parts) >= 3 and parts[0] == "geometry":
                ns = parts[1]
                name = ".".join(parts[2:])
                map_by_ns_name[(sanitize_identifier(ns), sanitize_identifier(name))] = identifier
                map_by_ns_name[(None, sanitize_identifier(name))] = identifier
            elif len(parts) >= 2 and parts[0] == "geometry":
                name = ".".join(parts[1:])
                map_by_ns_name[(None, sanitize_identifier(name))] = identifier
        else:
            map_by_file[basename_norm] = build_geometry_id(None, basename_norm)
    return map_by_file, map_by_ns_name

def load_animation_keys() -> Dict[str, Set[str]]:
    anim_dir = os.path.join(RP_FOLDER, "animations")
    result: Dict[str, Set[str]] = {}
    if not os.path.isdir(anim_dir):
        return result
    for fname in os.listdir(anim_dir):
        if not fname.lower().endswith(".json"):
            continue
        path = os.path.join(anim_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        keys: Set[str] = set()
        if isinstance(data, dict):
            anims = data.get("animations") or {}
            if isinstance(anims, dict):
                for k in anims.keys():
                    keys.add(k)
        result[os.path.splitext(fname)[0].lower()] = keys
    return result

# -------------------------
# Java -> GeckoLib mapping (unchanged logic)
# -------------------------
def read_all_java_files(root_dir=".") -> Dict[str, str]:
    java_files = {}
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.endswith(".java"):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        java_files[path] = fh.read()
                except Exception:
                    continue
    return java_files

def extract_class_name(java_code: str) -> Optional[str]:
    # Try javalang AST first for accurate parsing
    ast = JavaAST(java_code)
    name = ast.primary_class_name()
    if name:
        return name
    # Regex fallback for unparseable sources
    m = re.search(r'\b(public\s+)?(class|interface|enum)\s+([A-Z][A-Za-z0-9_]*)', java_code)
    if m:
        return m.group(3)
    return None

def find_model_geometry_in_code(java_code: str) -> Optional[Tuple[Optional[str], str]]:
    """
    Extract the geometry model namespace and name from a GeckoLib model class.
    Uses javalang AST for accurate argument extraction; falls back to regex.
    """
    ast = JavaAST(java_code)
    ast._parse()

    if ast._tree is not None:
        # new ResourceLocation("ns", "path/to/file.geo.json") — two-arg form
        for node in ast.object_creations_of('ResourceLocation'):
            args = getattr(node, 'arguments', []) or []
            ns_val, path_val = None, None
            if len(args) >= 2:
                if isinstance(args[0], javalang.tree.Literal):
                    ns_val = args[0].value.strip('"').strip("'")
                if isinstance(args[1], javalang.tree.Literal):
                    path_val = args[1].value.strip('"').strip("'")
            elif len(args) == 1:
                if isinstance(args[0], javalang.tree.Literal):
                    raw = args[0].value.strip('"').strip("'")
                    if ':' in raw:
                        ns_val, path_val = raw.split(':', 1)
                    else:
                        path_val = raw
            if path_val and ('geo/' in path_val or path_val.endswith('.geo.json') or path_val.endswith('.geo')):
                base = os.path.basename(path_val)
                name = re.sub(r'\.geo(\.json)?$', '', base, flags=re.IGNORECASE)
                return (ns_val.lower() if ns_val else None, sanitize_identifier(name))

        # Scan every string literal for embedded .geo paths
        for lit in ast.all_string_literals():
            if 'geo/' in lit or lit.endswith('.geo.json') or lit.endswith('.geo'):
                ns, path = (lit.split(':', 1) if ':' in lit else (None, lit))
                base = os.path.basename(path)
                name = re.sub(r'\.geo(\.json)?$', '', base, flags=re.IGNORECASE)
                return (ns.lower() if ns else None, sanitize_identifier(name))

    # ── regex fallback ─────────────────────────────────────────────────────
    m = re.search(r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_\-]+)["\']\s*,\s*["\']([^"\']*?geo/[^"\']*?\.geo(?:\.json)?)["\']\s*\)', java_code, re.IGNORECASE)
    if m:
        ns = m.group(1).lower()
        base = os.path.basename(m.group(2))
        name = re.sub(r'\.geo(\.json)?$', '', base, flags=re.IGNORECASE)
        return (ns, sanitize_identifier(name))
    m2 = re.search(r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_\-]+:[^"\']*?geo/[^"\']*?\.geo(?:\.json)?)["\']\s*\)', java_code, re.IGNORECASE)
    if m2:
        raw = m2.group(1)
        ns, path = (raw.split(':', 1) if ':' in raw else (None, raw))
        name = re.sub(r'\.geo(\.json)?$', '', os.path.basename(path), flags=re.IGNORECASE)
        return (ns.lower() if ns else None, sanitize_identifier(name))
    m3 = re.search(r'["\']([a-z0-9_\-:\/]*?geo\/[a-z0-9_\-]+(?:\.geo(?:\.json)?)?)["\']', java_code, re.IGNORECASE)
    if m3:
        raw = m3.group(1)
        ns, path = (raw.split(':', 1) if ':' in raw else (None, raw))
        name = re.sub(r'\.geo(\.json)?$', '', os.path.basename(path), flags=re.IGNORECASE)
        return (ns.lower() if ns else None, sanitize_identifier(name))
    m5 = re.search(r'["\']([a-z0-9_\-:\/]+\.geo(?:\.json)?)["\']', java_code, re.IGNORECASE)
    if m5:
        raw = m5.group(1)
        ns, path = (raw.split(':', 1) if ':' in raw else (None, raw))
        name = re.sub(r'\.geo(\.json)?$', '', os.path.basename(path), flags=re.IGNORECASE)
        return (ns.lower() if ns else None, sanitize_identifier(name))
    return None

def build_geckolib_mappings(java_root="."):
    java_files = read_all_java_files(java_root)
    class_to_path: Dict[str, str] = {}
    class_code_map: Dict[str, str] = {}
    for path, code in java_files.items():
        cls = extract_class_name(code)
        if cls:
            class_to_path[cls] = path
            class_code_map[cls] = code

    model_map: Dict[str, Tuple[Optional[str], str]] = {}
    renderer_model: Dict[str, str] = {}
    renderer_entity: Dict[str, str] = {}

    for path, code in class_code_map.items():
        geom = find_model_geometry_in_code(code)
        if geom:
            model_map[path] = geom

    for cls, code in class_code_map.items():
        ast = JavaAST(code)
        ast._parse()

        # Detect GeoEntityRenderer<EntityType> via AST superclass generic arg
        if ast._tree is not None:
            for cls_decl in ast.get_class_declarations():
                if cls_decl.extends and hasattr(cls_decl.extends, 'name'):
                    if cls_decl.extends.name == 'GeoEntityRenderer':
                        args = getattr(cls_decl.extends, 'arguments', None) or []
                        if args:
                            arg = args[0]
                            ent = JavaAST.strip_generics(
                                arg.type.name if hasattr(arg, 'type') and hasattr(arg.type, 'name')
                                else (arg.name if hasattr(arg, 'name') else '')
                            )
                            if ent:
                                renderer_entity[cls] = ent
            # Find model instantiations: new XModel(...)
            for ctype in ast.all_object_creation_types():
                if ctype in class_code_map and ('Model' in ctype or ctype in model_map):
                    renderer_model[cls] = ctype
                    break
        else:
            # regex fallback
            m = re.search(r'extends\s+GeoEntityRenderer\s*<\s*([A-Za-z0-9_<>.,\s]+)\s*>', code)
            if m:
                ent = re.sub(r'<.*?>', '', m.group(1).split(",")[0]).strip()
                if ent:
                    renderer_entity[cls] = ent
            model_candidates = set(re.findall(r'new\s+([A-Z][A-Za-z0-9_]*)\s*\(', code))
            for cand in model_candidates:
                if cand in class_code_map and ('Model' in cand or cand in model_map):
                    renderer_model[cls] = cand
                    break

        if cls not in renderer_model:
            # Last-resort: look for ModelVar = new ModelVar( patterns
            m2 = re.search(r'([A-Z][A-Za-z0-9_]*Model)\s+[a-zA-Z0-9_]+\s*=\s*new\s+([A-Z][A-Za-z0-9_]*Model)\s*\(', code)
            if m2:
                renderer_model[cls] = m2.group(1)

    entity_to_geometry: Dict[str, Tuple[Optional[str], str]] = {}
    entity_to_model: Dict[str, str] = {}

    for renderer_cls, model_cls in renderer_model.items():
        geom = model_map.get(model_cls)
        ent = renderer_entity.get(renderer_cls)
        if ent and geom:
            entity_to_geometry[ent] = geom
            entity_to_model[ent] = model_cls

    for renderer_cls, code in class_code_map.items():
        if renderer_cls not in renderer_model:
            # super(context, new ModelClass()) pattern
            ast = JavaAST(code)
            ast._parse()
            found_model = None
            if ast._tree is not None:
                # Look for super(...) call that contains a new ModelXxx()
                for ctype in ast.all_object_creation_types():
                    if ctype in model_map:
                        found_model = ctype
                        break
            else:
                m = re.search(r'super\s*\(\s*[^\)]*new\s+([A-Z][A-Za-z0-9_]*)\s*\(', code)
                if m:
                    found_model = m.group(1)
            if found_model and found_model in model_map:
                renderer_model[renderer_cls] = found_model

        if renderer_cls in renderer_model and renderer_cls not in renderer_entity:
            ast2 = JavaAST(code)
            ast2._parse()
            if ast2._tree is not None:
                for cls_decl in ast2.get_class_declarations():
                    if cls_decl.extends and cls_decl.extends.name == 'GeoEntityRenderer':
                        args = getattr(cls_decl.extends, 'arguments', None) or []
                        if args:
                            arg = args[0]
                            ent = JavaAST.strip_generics(
                                arg.type.name if hasattr(arg, 'type') and hasattr(arg.type, 'name')
                                else (arg.name if hasattr(arg, 'name') else '')
                            )
                            if ent:
                                renderer_entity[renderer_cls] = ent
            else:
                m2 = re.search(r'extends\s+GeoEntityRenderer\s*<\s*([A-Za-z0-9_<>.,\s]+)\s*>', code)
                if m2:
                    ent = re.sub(r'<.*?>', '', m2.group(1).split(",")[0]).strip()
                    if ent:
                        renderer_entity[renderer_cls] = ent

    for renderer_cls, model_cls in renderer_model.items():
        ent = renderer_entity.get(renderer_cls)
        geom = model_map.get(model_cls)
        if ent and geom:
            entity_to_geometry[ent] = geom
            entity_to_model[ent] = model_cls

    return {
        "class_code_map": class_code_map,
        "class_to_path": class_to_path,
        "model_map": model_map,
        "renderer_model": renderer_model,
        "renderer_entity": renderer_entity,
        "entity_to_geometry": entity_to_geometry,
        "entity_to_model": entity_to_model
    }

# -------------------------
# Java parsing helpers, extractors, and converters
# (most logic reused from earlier working script — kept intact)
# -------------------------
def extract_attributes_from_java(java_code: str):
    # This is the exact physical order from the code you provided:
    # 1. f_22279_ (0.3)
    # 2. f_22276_ (1024.0)
    # 3. f_22284_ (100.0)
    # 4. f_22281_ (9.0)
    # 5. f_22277_ (2048.0)
    # 6. f_22278_ (1000.0)
    
    ORDER_MAPPING = [
        "movement_speed",      # Slot 1
        "follow_range",        # Slot 2
        "health",              # Slot 3
        "knockback_resistance",# Slot 4
        "armor",               # Slot 5
        "attack_damage"        # Slot 6
    ]

    # Find the specific block for attributes to avoid picking up 
    # numbers from procedures or animations elsewhere in the file.
    block_match = re.search(r'public static Builder createAttributes\(\) \{(.*?)\}', java_code, re.DOTALL)
    if not block_match:
        return {"error": "Could not find createAttributes block"}

    attribute_block = block_match.group(1)

    # Extract every number passed as the second argument in the .m_22268_ or .add calls
    # Matches: , 0.3) or , 1024.0)
    values = re.findall(r',\s*([-+]?[0-9]*\.?[0-9]+[DdFfLl]?)', attribute_block)

    results = {}
    for i, val_str in enumerate(values):
        if i < len(ORDER_MAPPING):
            # Clean Java suffixes (D, f, L) and convert to float
            clean_val = float(re.sub(r'[DdFfLl]', '', val_str))
            results[ORDER_MAPPING[i]] = clean_val

    return results

# Example usage with your provided code:
# attributes = extract_attributes_by_physical_order(your_java_string)
# print(attributes)
def extract_animations_from_java(java_code: str, namespace: Optional[str] = None, entity_name: Optional[str] = None):
    """
    Extract animation IDs referenced in Java entity/renderer code.
    Uses javalang to find method-invocation string arguments; falls back to regex.

    Only collects strings that are plausibly real animation identifiers:
      - Already start with "animation." (GeckoLib / Bedrock style)
      - Contain a motion keyword in the last segment (idle, walk, attack, etc.)
      - Come from an addAnimation() / .then() call site  (trusted regardless of name)
    Bare short words picked up from random string literals are REJECTED — they
    produce garbage like "animation.ns.entity.empty" or "animation.ns.entity.procedure".
    """
    animations = set()

    # All recognised motion-category keywords (must appear in the LAST segment of the ID)
    MOTION_KEYWORDS = {
        "idle", "stand", "pose", "float",
        "walk", "walking",
        "run", "running", "chase", "sprint",
        "attack", "strike", "bite", "swipe", "slam", "lunge", "claw",
        "hurt", "hit", "flinch", "pain",
        "death", "die", "dying", "dead",
        "sit", "sitting", "crouch", "lay",
        "swim", "swimming",
        "fly", "flying", "hover", "glide",
        "sleep", "sleeping", "rest",
        "spawn", "appear", "emerge", "summon",
        "open", "close", "blink", "tail", "wing", "flap",
    }

    def _looks_like_anim_id(s: str) -> bool:
        """Return True only if s looks like a real animation identifier."""
        if not s:
            return False
        # Explicit Bedrock/GeckoLib animation prefix — always valid
        if s.startswith("animation."):
            tail = s[len("animation."):]
            last_seg = tail.split(".")[-1].lower()
            # Accept if the last segment matches a motion keyword
            return any(kw in last_seg for kw in MOTION_KEYWORDS)
        # A path string like "animations/toww_idle.json"
        if "animations/" in s.lower():
            stem = re.sub(r'\.json$', '', s.split("/")[-1], flags=re.I).lower()
            return any(kw in stem for kw in MOTION_KEYWORDS)
        return False

    def _add(raw: str, trusted: bool = False):
        """
        Add raw string as an animation ID.
        trusted=True: came from an explicit addAnimation/then call, so we accept it
                      even if it doesn't match a motion keyword (it will get categorised
                      into "other" by _categorise_animations).
        trusted=False: came from a broad scan; must pass the motion-keyword filter.
        """
        s = str(raw).strip().strip('"').strip("'")
        if not s or len(s) < 3:
            return
        if not trusted and not _looks_like_anim_id(s):
            return
        anim_id = canonicalize_animation_id(s, namespace, entity_name)
        if anim_id:
            animations.add(anim_id)

    ast = JavaAST(java_code)
    ast._parse()

    if ast._tree is not None:
        # addAnimation("anim.name") / .then("anim.name")  — trusted call sites
        for inv in ast.invocations_of('addAnimation') + ast.invocations_of('then'):
            s = JavaAST.first_string_arg(inv)
            if s:
                _add(s, trusted=True)

        # Scan string literals — only accepted if they pass the motion-keyword filter
        for lit in ast.all_string_literals():
            _add(lit, trusted=False)

        # Field declarations like: private static final String ANIMATION_IDLE = "idle";
        # or: RawAnimation WALK = RawAnimation.begin().then("animation.ns.entity.walk", ...)
        for _, node in ast._tree.filter(javalang.tree.FieldDeclaration):
            for decl in node.declarators:
                if re.match(r'(?:ANIMATION|ANIM)[_A-Z0-9]*', decl.name, re.I):
                    if decl.initializer and isinstance(decl.initializer, javalang.tree.Literal):
                        val = decl.initializer.value.strip('"').strip("'")
                        _add(val, trusted=False)   # still require motion keyword
    else:
        # Regex fallback
        for m in re.finditer(r'addAnimation\(\s*["\']+([^"\']+)["\']+', java_code):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'animation\.([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)', java_code):
            _add("animation." + m.group(1), trusted=False)
        for m in re.finditer(r'\.then\s*\(\s*["\']+([^"\']+)["\']+', java_code):
            _add(m.group(1), trusted=True)
        for m in re.finditer(r'animations/([^"\'\.]+)\.json', java_code, re.I):
            _add(m.group(1), trusted=False)
        for m in re.finditer(r'(?:ANIMATION|ANIM)[_A-Z0-9]*\s*=\s*["\']+([^"\']+)["\']+', java_code):
            _add(m.group(1), trusted=False)

    return animations

# -------------------------
# Vanilla goal names that the Bedrock converter knows how to handle.
# Used as the termination condition for the custom-goal inheritance walk.
# -------------------------
VANILLA_GOALS: Set[str] = {
    "FloatGoal", "SwimGoal", "BreatheAirGoal",
    "NearestAttackableTargetGoal", "NearestAttackableTargetExpiringGoal",
    "ToggleableNearestAttackableTargetGoal", "NonTamedTargetGoal",
    "DefendVillageTargetGoal", "HurtByTargetGoal",
    "OwnerHurtByTargetGoal", "OwnerHurtTargetGoal", "ResetAngerGoal",
    "MeleeAttackGoal", "OcelotAttackGoal", "CreeperSwellGoal",
    "RangedAttackGoal", "RangedBowAttackGoal", "RangedCrossbowAttackGoal",
    "LeapAtTargetGoal", "MoveTowardsTargetGoal",
    "AvoidEntityGoal", "PanicGoal", "RunAroundLikeCrazyGoal",
    "FleeSunGoal", "RestrictSunGoal",
    "OpenDoorGoal", "InteractDoorGoal", "BreakDoorGoal",
    "BreakBlockGoal", "UseItemGoal",
    "FollowOwnerGoal", "FollowParentGoal", "FollowMobGoal",
    "FollowBoatGoal", "FollowSchoolLeaderGoal", "LlamaFollowCaravanGoal",
    "LandOnOwnersShoulderGoal", "MoveToBlockGoal",
    "MoveTowardsRestrictionGoal", "MoveThroughVillageGoal",
    "MoveThroughVillageAtNightGoal", "MoveTowardsRaidGoal",
    "ReturnToVillageGoal", "PatrolVillageGoal", "FindWaterGoal",
    "SitWhenOrderedToGoal", "SitGoal",
    "BreedGoal", "TemptGoal", "EatGrassGoal", "BegGoal",
    "TradeWithPlayerGoal", "LookAtCustomerGoal", "ShowVillagerFlowerGoal",
    "TriggerSkeletonTrapGoal", "DolphinJumpGoal", "JumpGoal",
    "CatLieOnBedGoal", "CatSitOnBlockGoal",
    "WaterAvoidingRandomStrollGoal", "RandomWalkingGoal",
    "RandomSwimmingGoal", "RandomStrollGoal",
    "LookAtGoal", "LookAtPlayerGoal", "LookAtWithoutMovingGoal",
    "LookRandomlyGoal", "RandomLookAroundGoal",
}

# ── EC4: MCP / Bukkit / Spigot / Paper mapped goal name aliases ──
# These are the same vanilla goals under different mapping sets.
# Maps foreign name -> canonical vanilla name in VANILLA_GOALS.
GOAL_NAME_ALIASES: Dict[str, str] = {
    # Spigot/Bukkit PathfinderGoal* names (CraftBukkit mappings)
    "PathfinderGoalFloat":                    "FloatGoal",
    "PathfinderGoalSwimming":                 "SwimGoal",
    "PathfinderGoalMeleeAttack":              "MeleeAttackGoal",
    "PathfinderGoalBowShoot":                 "RangedBowAttackGoal",
    "PathfinderGoalArrowAttack":              "RangedAttackGoal",
    "PathfinderGoalCrossbowAttack":           "RangedCrossbowAttackGoal",
    "PathfinderGoalLeapAtTarget":             "LeapAtTargetGoal",
    "PathfinderGoalMoveTowardsTarget":        "MoveTowardsTargetGoal",
    "PathfinderGoalAvoidEntity":              "AvoidEntityGoal",
    "PathfinderGoalPanic":                    "PanicGoal",
    "PathfinderGoalOpenDoor":                 "OpenDoorGoal",
    "PathfinderGoalBreakDoor":                "BreakDoorGoal",
    "PathfinderGoalFollowOwner":              "FollowOwnerGoal",
    "PathfinderGoalFollowParent":             "FollowParentGoal",
    "PathfinderGoalFollowMob":                "FollowMobGoal",
    "PathfinderGoalMoveToBlock":              "MoveToBlockGoal",
    "PathfinderGoalRestrictSun":              "RestrictSunGoal",
    "PathfinderGoalFleeSun":                  "FleeSunGoal",
    "PathfinderGoalWaterJumping":             "DolphinJumpGoal",
    "PathfinderGoalBreed":                    "BreedGoal",
    "PathfinderGoalTempt":                    "TemptGoal",
    "PathfinderGoalEatTile":                  "EatGrassGoal",
    "PathfinderGoalBeg":                      "BegGoal",
    "PathfinderGoalTradeWithPlayer":          "TradeWithPlayerGoal",
    "PathfinderGoalLookAtPlayer":             "LookAtPlayerGoal",
    "PathfinderGoalLookAtTradingPlayer":      "LookAtCustomerGoal",
    "PathfinderGoalRandomLookaround":         "RandomLookAroundGoal",
    "PathfinderGoalRandomStroll":             "RandomStrollGoal",
    "PathfinderGoalRandomSwim":               "RandomSwimmingGoal",
    "PathfinderGoalWaterAvoidingRandomStroll":"WaterAvoidingRandomStrollGoal",
    "PathfinderGoalSit":                      "SitGoal",
    "PathfinderGoalHurtByTarget":             "HurtByTargetGoal",
    "PathfinderGoalNearestAttackableTarget":  "NearestAttackableTargetGoal",
    "PathfinderGoalDefendVillage":            "DefendVillageTargetGoal",
    "PathfinderGoalOwnerHurtByTarget":        "OwnerHurtByTargetGoal",
    "PathfinderGoalOwnerHurtTarget":          "OwnerHurtTargetGoal",
    # Older Forge/MCP obfuscated intermediary names
    "EntityAIFloat":           "FloatGoal",
    "EntityAISwimming":        "SwimGoal",
    "EntityAIAttackMelee":     "MeleeAttackGoal",
    "EntityAIAttackRanged":    "RangedAttackGoal",
    "EntityAIAttackRangedBow": "RangedBowAttackGoal",
    "EntityAILeapAtTarget":    "LeapAtTargetGoal",
    "EntityAIAvoidEntity":     "AvoidEntityGoal",
    "EntityAIPanic":           "PanicGoal",
    "EntityAIOpenDoor":        "OpenDoorGoal",
    "EntityAIFollowOwner":     "FollowOwnerGoal",
    "EntityAIFollowParent":    "FollowParentGoal",
    "EntityAIFollowMob":       "FollowMobGoal",
    "EntityAIBreed":           "BreedGoal",
    "EntityAITempt":           "TemptGoal",
    "EntityAIEatGrass":        "EatGrassGoal",
    "EntityAIWatchClosest":    "LookAtPlayerGoal",
    "EntityAILookIdle":        "RandomLookAroundGoal",
    "EntityAIWander":          "RandomStrollGoal",
    "EntityAIHurtByTarget":    "HurtByTargetGoal",
    "EntityAINearestAttackableTarget": "NearestAttackableTargetGoal",
    "EntityAISit":             "SitGoal",
}

# Module-level cache: built once per run by build_goal_inheritance_map()
# Maps custom class name -> direct parent class name (as written in `extends`)
_GOAL_PARENT_MAP: Dict[str, str] = {}
_GOAL_MAP_BUILT: bool = False

# Module-level: maps entity class name -> all java source code for that class
# Populated during prescan; used for super.registerGoals() resolution.
_ENTITY_SOURCE_MAP: Dict[str, str] = {}


def _strip_generics(name: str) -> str:
    """Remove generic type parameters. Delegates to JavaAST.strip_generics."""
    return JavaAST.strip_generics(name)


def build_goal_inheritance_map(java_files: Dict[str, str]) -> None:
    """
    Scan every Java file and record `class X extends Y` relationships
    for any class whose name ends with "Goal" or whose parent is already
    a known goal class.  Uses javalang AST for accurate class hierarchy
    extraction; falls back to regex for unparseable files.

    Also populates _ENTITY_SOURCE_MAP for super.registerGoals() resolution.
    Call once (during prescan) before entity conversion begins.
    """
    global _GOAL_PARENT_MAP, _GOAL_MAP_BUILT, _ENTITY_SOURCE_MAP

    raw: Dict[str, str] = {}
    entity_src: Dict[str, str] = {}

    for _path, code in java_files.items():
        ast = JavaAST(code)
        ast._parse()

        if ast._tree is not None:
            # Populate entity source map from AST class declarations
            for cls_decl in ast.get_class_declarations():
                entity_src[cls_decl.name] = code

            # Walk all class->extends relationships
            for child, parent in ast.all_class_extends():
                child  = JavaAST.strip_generics(child)
                parent = JavaAST.strip_generics(parent)
                if (child.endswith("Goal") or parent.endswith("Goal")
                        or parent in VANILLA_GOALS or child in VANILLA_GOALS
                        or parent in GOAL_NAME_ALIASES or child in GOAL_NAME_ALIASES):
                    raw[child] = GOAL_NAME_ALIASES.get(parent, parent)
        else:
            # regex fallback
            m_cls = re.search(r'\bclass\s+([A-Za-z0-9_]+)', code)
            if m_cls:
                entity_src[m_cls.group(1)] = code
            for m in re.finditer(
                r'\bclass\s+([A-Za-z0-9_]+)\s*(?:<[^>]*>)?\s+extends\s+([A-Za-z0-9_]+)\s*(?:<[^>]*>)?',
                code
            ):
                child  = _strip_generics(m.group(1))
                parent = _strip_generics(m.group(2))
                if (child.endswith("Goal") or parent.endswith("Goal")
                        or parent in VANILLA_GOALS or child in VANILLA_GOALS
                        or parent in GOAL_NAME_ALIASES or child in GOAL_NAME_ALIASES):
                    raw[child] = GOAL_NAME_ALIASES.get(parent, parent)

    _GOAL_PARENT_MAP = raw
    _ENTITY_SOURCE_MAP = entity_src
    _GOAL_MAP_BUILT = True

    custom_count = sum(1 for c in raw if c not in VANILLA_GOALS)
    print(f"[goal-map] Built inheritance map: {len(raw)} entries "
          f"({custom_count} custom, {len(raw) - custom_count} vanilla)")


def resolve_custom_goal(custom_class: str, visited: Optional[Set[str]] = None) -> Optional[str]:
    """
    Walk the goal inheritance chain starting from `custom_class` until we
    either reach a known vanilla goal or exhaust the chain.

    Returns the vanilla goal name if found, or None if the chain cannot be
    resolved (e.g. the class extends Goal/TargetGoal directly with no
    recognisable vanilla mapping).

    `visited` guards against infinite loops from circular inheritance
    (which is invalid Java, but defensive programming doesn't hurt).
    """
    if visited is None:
        visited = set()

    if custom_class in visited:
        return None  # cycle guard
    visited.add(custom_class)

    # Direct alias hit (MCP/Bukkit name used as the goal itself)
    if custom_class in GOAL_NAME_ALIASES:
        resolved = GOAL_NAME_ALIASES[custom_class]
        print(f"[goal-resolve] {custom_class} -> {resolved} (alias)")
        return resolved

    # Already vanilla — return directly
    if custom_class in VANILLA_GOALS:
        return custom_class

    parent = _GOAL_PARENT_MAP.get(custom_class)
    if not parent:
        return None  # unknown parent — dead end

    if parent in VANILLA_GOALS:
        print(f"[goal-resolve] {custom_class} -> {parent} (vanilla)")
        return parent

    # Parent is another custom goal — recurse
    print(f"[goal-resolve] {custom_class} -> {parent} (custom, descending...)")
    return resolve_custom_goal(parent, visited)


def _collect_super_goals(entity_class: str,
                         java_files: Dict[str, str],
                         visited: Optional[Set[str]] = None) -> List[str]:
    """
    EC5: If an entity class calls super.registerGoals(), walk up the entity
    inheritance chain and collect goals from all ancestor registerGoals()
    methods, stopping at Mob/PathfinderMob/Animal/Monster etc.

    Uses javalang AST for class hierarchy; falls back to regex.
    """
    if visited is None:
        visited = set()
    if entity_class in visited:
        return []
    visited.add(entity_class)

    BASE_ENTITY_CLASSES = {
        "Mob", "PathfinderMob", "Animal", "Monster", "AmbientCreature",
        "WaterAnimal", "AbstractFish", "Creature", "AbstractVillager",
        "TamableAnimal", "AbstractGolem", "AbstractSkeleton",
        "AbstractZombie", "Slime", "Ghast", "FlyingMob",
    }

    # Find source for this entity class
    src = _ENTITY_SOURCE_MAP.get(entity_class)
    if not src:
        for _path, code in java_files.items():
            ast_check = JavaAST(code)
            ast_check._parse()
            if ast_check._tree is not None:
                if any(d.name == entity_class for d in ast_check.get_class_declarations()):
                    src = code
                    break
            elif re.search(rf'\bclass\s+{re.escape(entity_class)}\b', code):
                src = code
                break
    if not src:
        return []

    # Find the parent class
    parent_entity = None
    ast_src = JavaAST(src)
    ast_src._parse()
    if ast_src._tree is not None:
        parent_entity = ast_src.superclass_name(entity_class)
        if parent_entity:
            parent_entity = JavaAST.strip_generics(parent_entity)
    else:
        parent_m = re.search(
            r'\bclass\s+' + re.escape(entity_class) + r'\s*(?:<[^>]*>)?\s+extends\s+([A-Za-z0-9_]+)',
            src
        )
        if parent_m:
            parent_entity = parent_m.group(1)

    if not parent_entity or parent_entity in BASE_ENTITY_CLASSES:
        return []

    # Find parent source
    parent_src = _ENTITY_SOURCE_MAP.get(parent_entity)
    if not parent_src:
        for _path, code in java_files.items():
            ast_check = JavaAST(code)
            ast_check._parse()
            if ast_check._tree is not None:
                if any(d.name == parent_entity for d in ast_check.get_class_declarations()):
                    parent_src = code
                    break
            elif re.search(rf'\bclass\s+{re.escape(parent_entity)}\b', code):
                parent_src = code
                break
    if not parent_src:
        return []

    inherited: List[str] = []
    inherited.extend(extract_ai_goals_from_java(parent_src))

    # Check if parent also calls super.registerGoals()
    parent_ast = JavaAST(parent_src)
    parent_ast._parse()
    calls_super = False
    if parent_ast._tree is not None:
        for _, inv in parent_ast._tree.filter(javalang.tree.MethodInvocation):
            if inv.member == 'registerGoals' and getattr(inv, 'qualifier', '') == 'super':
                calls_super = True
                break
    else:
        calls_super = bool(re.search(r'\bsuper\s*\.\s*registerGoals\s*\(\s*\)', parent_src))

    if calls_super:
        inherited.extend(_collect_super_goals(parent_entity, java_files, visited))

    return inherited


def extract_ai_goals_from_java(java_code: str,
                                extra_java_files: Optional[Dict[str, str]] = None):
    """
    Extract all AI goals used by an entity class and return a list of
    resolved vanilla goal names suitable for Bedrock conversion.

    Uses javalang AST for accurate new-expression and addGoal() detection;
    falls back to regex for files that cannot be parsed.

    Steps:
      1. Direct vanilla goal instantiations (`new MeleeAttackGoal(...)`)
      2. Direct alias instantiations (MCP/Bukkit/Spigot mapped names)
      3. addGoal() calls with vanilla or alias goal names
      4. Custom goal classes resolved via inheritance chain
      5. super.registerGoals() — goals inherited from parent entity classes
      6. Legacy extend_map back-compat check
    """
    if not _GOAL_MAP_BUILT:
        build_goal_inheritance_map(extra_java_files or {"<inline>": java_code})

    java_files_ref = extra_java_files or {}
    ai_goals: List[str] = []

    def _add(goal: str):
        if goal and goal not in ai_goals:
            ai_goals.append(goal)

    ast = JavaAST(java_code)
    ast._parse()

    if ast._tree is not None:
        # Collect all instantiated class names in the file
        all_new_types = [JavaAST.strip_generics(t) for t in ast.all_object_creation_types()]

        # ── Step 1 & 2: Direct vanilla and alias instantiations ──
        for ctype in all_new_types:
            if ctype in VANILLA_GOALS:
                _add(ctype)
            elif ctype in GOAL_NAME_ALIASES:
                _add(GOAL_NAME_ALIASES[ctype])

        # ── Step 3: addGoal(priority, new XGoal(...)) ──
        for inv in ast.invocations_of('addGoal'):
            args = getattr(inv, 'arguments', []) or []
            if len(args) >= 2:
                goal_arg = args[1]
                if isinstance(goal_arg, javalang.tree.ClassCreator):
                    cls_name = JavaAST.strip_generics(goal_arg.type.name)
                    if cls_name in VANILLA_GOALS:
                        _add(cls_name)
                    elif cls_name in GOAL_NAME_ALIASES:
                        _add(GOAL_NAME_ALIASES[cls_name])

        # ── Step 4: Custom goal resolution ──
        custom_instantiated: Set[str] = set()
        for ctype in all_new_types:
            if ctype not in VANILLA_GOALS and ctype not in GOAL_NAME_ALIASES and ctype.endswith('Goal'):
                custom_instantiated.add(ctype)

        for custom_cls in sorted(custom_instantiated):
            # Register any local inner-class definition
            for child, parent in ast.all_class_extends():
                if child == custom_cls:
                    local_parent = GOAL_NAME_ALIASES.get(parent, parent)
                    if custom_cls not in _GOAL_PARENT_MAP:
                        _GOAL_PARENT_MAP[custom_cls] = local_parent
            resolved = resolve_custom_goal(custom_cls)
            if resolved:
                if resolved not in ai_goals:
                    print(f"[goal-resolve] Custom goal '{custom_cls}' resolved -> '{resolved}'")
                _add(resolved)
            else:
                print(f"[goal-resolve] Custom goal '{custom_cls}' could not be resolved to a vanilla goal")

        # ── Step 5: super.registerGoals() ──
        calls_super_register = any(
            inv.member == 'registerGoals'
            for _, inv in ast._tree.filter(javalang.tree.MethodInvocation)
            if getattr(inv, 'qualifier', '') in ('', 'super')
        ) if ast._tree else False
        # Also check for explicit super.registerGoals() via qualifier
        for _, inv in ast._tree.filter(javalang.tree.MethodInvocation):
            if inv.member == 'registerGoals' and getattr(inv, 'qualifier', '') == 'super':
                calls_super_register = True
                break
        if calls_super_register:
            entity_cls = ast.primary_class_name()
            if entity_cls:
                inherited = _collect_super_goals(entity_cls, java_files_ref)
                for g in inherited:
                    _add(g)
                if inherited:
                    print(f"[goal-resolve] Inherited {len(inherited)} goal(s) via "
                          f"super.registerGoals() for {entity_cls}: {inherited}")

    else:
        # ── regex fallback ──────────────────────────────────────────────────
        for goal_name in VANILLA_GOALS:
            if re.search(rf'\bnew\s+{re.escape(goal_name)}\s*[(<]', java_code):
                _add(goal_name)
        for alias, canonical in GOAL_NAME_ALIASES.items():
            if re.search(rf'\bnew\s+{re.escape(alias)}\s*[(<]', java_code):
                _add(canonical)
        for m in re.finditer(
            r'(?:goalSelector|targetSelector)?\s*\.?\s*addGoal\s*\(\s*\d+\s*,\s*new\s+([A-Za-z0-9_]+)\s*[(<]',
            java_code, re.DOTALL
        ):
            cls_name = _strip_generics(m.group(1))
            if cls_name in VANILLA_GOALS:
                _add(cls_name)
            elif cls_name in GOAL_NAME_ALIASES:
                _add(GOAL_NAME_ALIASES[cls_name])
        custom_instantiated = set()
        for m in re.finditer(r'\bnew\s+([A-Za-z0-9_]+Goal)\s*[(<]', java_code):
            cls_name = _strip_generics(m.group(1))
            if cls_name not in VANILLA_GOALS and cls_name not in GOAL_NAME_ALIASES:
                custom_instantiated.add(cls_name)
        for custom_cls in sorted(custom_instantiated):
            local_m = re.search(
                rf'\bclass\s+{re.escape(custom_cls)}\s*(?:<[^>]*>)?\s+extends\s+([A-Za-z0-9_]+)\s*(?:<[^>]*>)?',
                java_code
            )
            if local_m:
                local_parent = GOAL_NAME_ALIASES.get(_strip_generics(local_m.group(1)), _strip_generics(local_m.group(1)))
                if custom_cls not in _GOAL_PARENT_MAP:
                    _GOAL_PARENT_MAP[custom_cls] = local_parent
            resolved = resolve_custom_goal(custom_cls)
            if resolved:
                if resolved not in ai_goals:
                    print(f"[goal-resolve] Custom goal '{custom_cls}' resolved -> '{resolved}'")
                _add(resolved)
            else:
                print(f"[goal-resolve] Custom goal '{custom_cls}' could not be resolved to a vanilla goal")
        if re.search(r'\bsuper\s*\.\s*registerGoals\s*\(\s*\)', java_code):
            cls_m = re.search(r'\bclass\s+([A-Za-z0-9_]+)', java_code)
            if cls_m:
                entity_cls = cls_m.group(1)
                inherited = _collect_super_goals(entity_cls, java_files_ref)
                for g in inherited:
                    _add(g)
                if inherited:
                    print(f"[goal-resolve] Inherited {len(inherited)} goal(s) via "
                          f"super.registerGoals() for {entity_cls}: {inherited}")

    # ── Step 6: Legacy extend_map back-compat ──────────────────────────────
    LEGACY_EXTEND_MAP = {
        "MeleeAttackGoal", "RangedAttackGoal",
        "NearestAttackableTargetGoal", "HurtByTargetGoal",
        "AvoidEntityGoal", "PanicGoal", "FollowOwnerGoal",
    }
    ast2 = JavaAST(java_code)
    ast2._parse()
    for base in LEGACY_EXTEND_MAP:
        if ast2._tree is not None:
            for child, parent in ast2.all_class_extends():
                if parent == base:
                    if base not in ai_goals and child in [JavaAST.strip_generics(t) for t in ast2.all_object_creation_types()]:
                        _add(base)
        else:
            custom = re.search(rf'\bclass\s+(\w+)\s*(?:<[^>]*>)?\s+extends\s+{re.escape(base)}', java_code)
            if custom:
                if base not in ai_goals and re.search(rf'\bnew\s+{re.escape(custom.group(1))}\s*[(<]', java_code):
                    _add(base)

    return ai_goals

def extract_damage_immunities_from_java(java_code: str):
    immunities = set()
    class_checks = {
        "AbstractArrow": "projectile",
        "Player": "player",
        "ThrownPotion": "potion",
        "AreaEffectCloud": "area_effect_cloud",
    }
    for cls, cause in class_checks.items():
        if re.search(rf'instanceof\s+{cls}', java_code):
            immunities.add(cause)
    if re.search(r'm_19385_\(\)\.equals\(["\']trident["\']\)', java_code) or re.search(r'equals\(["\']trident["\']\)', java_code):
        immunities.add("projectile")
    if re.search(r'm_19385_\(\)\.equals\(["\']witherSkull["\']\)', java_code) or re.search(r'witherskull', java_code, re.I):
        immunities.add("projectile")
    if re.search(r'DamageSource\.f_19315_', java_code) or re.search(r'FIRE', java_code, re.I):
        immunities.add("fire")
    if re.search(r'DamageSource\.f_19314_', java_code) or re.search(r'Drown', java_code, re.I):
        immunities.add("drown")
    if re.search(r'DamageSource\.f_19312_', java_code) or re.search(r'Fall', java_code, re.I):
        immunities.add("fall")
    if re.search(r'witherskull', java_code, re.I) or re.search(r'WITHER', java_code, re.I):
        immunities.add("magic")
    if re.search(r'explosion', java_code, re.I):
        immunities.add("explosion")
    if re.search(r'isMagic\(', java_code) or re.search(r'm_19372_\(\)', java_code):
        immunities.add("magic")
    found_classes = re.findall(r'instanceof\s+([A-Z][A-Za-z0-9_]*)', java_code)
    fallback_map = {
        "AbstractArrow": "projectile", "Arrow": "projectile",
        "SpectralArrow": "projectile", "Trident": "projectile",
        "ShulkerBullet": "projectile", "FireworkRocketEntity": "projectile",
        "Player": "player", "ServerPlayer": "player",
        "ThrownPotion": "potion", "ThrownSplashPotion": "potion",
        "AreaEffectCloud": "area_effect_cloud", "Entity": None
    }
    for cls in found_classes:
        if cls in fallback_map and fallback_map[cls]:
            immunities.add(fallback_map[cls])
    if re.search(r'isInvulnerableTo\s*\([^)]*\)\s*\{[^}]*return\s+true', java_code, re.DOTALL):
        immunities.add("all")
    return sorted(immunities)

def detect_dynamic_bounding_procedure(java_code: str) -> Optional[str]:
    m = re.search(r'([A-Za-z0-9_]+)BoundingBoxScaleProcedure', java_code)
    if m:
        return m.group(0)
    m2 = re.search(r'([A-Za-z0-9_]+Procedure)\.execute', java_code)
    if m2:
        return m2.group(1)
    return None

def detect_despawn_ticks(java_code: str) -> Optional[int]:
    # Only match patterns that have clear despawn/remove context
    m = re.search(r'==\s*([0-9]{1,5})\)\s*{[^}]*remove\(', java_code)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    # Additional safe patterns: tickCount/age checks paired with discard/remove
    m2 = re.search(r'(?:tickCount|age|lifeTicks?)\s*[>]=?\s*([0-9]{1,5})[^;{]*(?:discard|remove|kill)\s*\(', java_code)
    if m2:
        try:
            val = int(m2.group(1))
            if 1 <= val <= 24000:  # 0–20 mins at 20tps
                return val
        except Exception:
            pass
    return None

# -------------------------
# RP writer helpers (correct wiring)
# -------------------------
def write_render_controller(entity_basename: str, namespace: str, geometry_identifier: str, uv_anim: Optional[Dict] = None) -> str:
    eb = sanitize_identifier(entity_basename)
    ns = sanitize_identifier(namespace)
    if geometry_identifier.startswith("geometry."):
        geom_tail = geometry_identifier.split(".", 1)[1]
        geom_ident = "geometry." + sanitize_identifier(geom_tail)
    else:
        geom_ident = "geometry." + sanitize_identifier(geometry_identifier)
    controller_id = f"controller.render.{ns}.{eb}"
    # Use legacy render format and reference texture shortname for textures (client_entity maps default -> path)
    controller = {
        "format_version": RP_LEGACY_RENDER_FORMAT,
        "render_controllers": {
            controller_id: {
                "geometry": geom_ident,
                # textures must reference the short-name (client_entity defines "default")
                "textures": ["texture.default"],
                # materials should be a list of mapping objects
                "materials": [
                    {"*": "Material.default"}
                ],
                # uv_anim required by validator — include even if empty
                "uv_anim": {}
            }
        }
    }
    # If caller provided uv_anim content, merge it (override empty)
    if uv_anim:
        controller["render_controllers"][controller_id]["uv_anim"] = uv_anim

    out_path = os.path.join(RP_FOLDER, "render_controllers", f"{eb}.render_controllers.json")
    safe_write_json(out_path, controller)
    print(f"Wrote render controller: {out_path}")
    return controller_id

def write_rp_entity_json(entity_basename: str, namespace: str, texture_ref: str, geometry_identifier: str, animation_key: Optional[str], controller_id: str):
    """
    Write the initial RP client_entity JSON.  Animations and animation_controllers
    are NOT written here — patch_rp_entity_with_controller() handles those after
    the full animation set is known, using the correct Bedrock shortname wiring.
    """
    eb = sanitize_identifier(entity_basename)
    ns = sanitize_identifier(namespace)
    texture_path = texture_ref_to_rp_path(texture_ref, default_kind="entity")
    if not texture_path.startswith("textures/"):
        texture_path_with_prefix = f"textures/{texture_path}"
    else:
        texture_path_with_prefix = texture_path

    if geometry_identifier.startswith("geometry."):
        geom_tail = geometry_identifier.split(".", 1)[1]
        geom_ident = "geometry." + sanitize_identifier(geom_tail)
    else:
        geom_ident = "geometry." + sanitize_identifier(geometry_identifier)

    description = {
        "identifier": f"{ns}:{eb}",
        "textures": {"default": texture_path_with_prefix},
        "geometry": {"default": geom_ident},
        "render_controllers": [controller_id],
        "materials": {"default": "entity_alphatest"}
        # animations, animation_controllers, and scripts.animate are added by
        # patch_rp_entity_with_controller() once the full animation set is known.
    }
    client_entity = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:client_entity": {"description": description}
    }
    out_path = os.path.join(RP_FOLDER, "entity", f"{eb}.entity.json")
    safe_write_json(out_path, client_entity)
    print(f"[rp_entity] Wrote {out_path}")

# -------------------------
# Block & Item conversion (unchanged)
# -------------------------
def extract_block_properties_from_java(java_code: str):
    props = {
        "destroy_time": None,
        "explosion_resistance": None,
        "material": None,
        "texture_hint": None,
        "loot_table": None
    }
    m = re.search(r'\.strength\(\s*([0-9]+(?:\.[0-9]+)?)(?:\s*,\s*([0-9]+(?:\.[0-9]+)?))?\s*\)', java_code)
    if m:
        try:
            props["destroy_time"] = float(m.group(1))
        except Exception:
            pass
        if m.group(2):
            try:
                props["explosion_resistance"] = float(m.group(2))
            except Exception:
                pass
    m2 = re.search(r'(?:explosionResistance|explosion_resistance|explosionResistant)\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)', java_code)
    if m2:
        try:
            props["explosion_resistance"] = float(m2.group(1))
        except Exception:
            pass
    m3 = re.search(r'Material\.([A-Z_]+)', java_code)
    if m3:
        props["material"] = m3.group(1).lower()
    m4 = re.search(r'setRegistryName\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
    if m4:
        props["texture_hint"] = m4.group(1).split(":")[-1]
    else:
        m5 = re.search(r'new\s+ResourceLocation\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
        if m5:
            props["texture_hint"] = m5.group(1).split(":")[-1]
    m6 = re.search(r'getLootTable\(\)\s*.*?["\']([a-z0-9_:-]+)["\']', java_code, re.I)
    if m6:
        props["loot_table"] = m6.group(1)
    m7 = re.search(r'lootTable\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
    if m7:
        props["loot_table"] = m7.group(1)
    return props

def convert_java_block_to_bedrock(java_path: str, namespace: str):
    try:
        with open(java_path, 'r', encoding='utf-8', errors='ignore') as f:
            java_code = f.read()
    except Exception as e:
        print(f"❌ Failed to read block java {java_path}: {e}")
        return
    block_basename = os.path.splitext(os.path.basename(java_path))[0]
    block_id = f"{sanitize_identifier(namespace)}:{sanitize_identifier(block_basename)}"
    props = extract_block_properties_from_java(java_code)
    block_json = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:block": {
            "description": {
                "identifier": block_id,
                "is_experimental": False,
                "register_to_creative_menu": True
            },
            "components": {}
        }
    }
    comps = block_json["minecraft:block"]["components"]
    comps["minecraft:destroy_time"] = props.get("destroy_time") if props.get("destroy_time") is not None else 1.5
    comps["minecraft:explosion_resistance"] = props.get("explosion_resistance") if props.get("explosion_resistance") is not None else 6.0
    texture_ref = resolve_texture_reference(namespace, props.get("texture_hint"), "blocks", fallback_name=sanitize_identifier(block_basename))
    comps["minecraft:material_instances"] = {"*": {"texture": texture_ref, "render_method": "opaque"}}
    if props.get("loot_table"):
        comps["minecraft:loot"] = {"table": props["loot_table"]}
    else:
        comps["minecraft:loot"] = {"table": f"loot_tables/blocks/{sanitize_identifier(block_basename)}.json"}
    comps["_converter_metadata"] = {"source_java_file": os.path.basename(java_path), "parsed_props": props}
    out_path = os.path.join(BP_FOLDER, "blocks", f"{sanitize_identifier(block_basename)}.json")
    safe_write_json(out_path, block_json)
    print(f"Converted block {java_path} -> {out_path}")

def extract_item_properties_from_java(java_code: str):
    props = {
        "max_stack_size": None,
        "durability": None,
        "texture_hint": None,
        "creative_tab": None,
        "registry_name": None
    }
    m = re.search(r'\.stacksTo\(\s*([0-9]+)\s*\)', java_code)
    if m:
        try:
            props["max_stack_size"] = int(m.group(1))
        except Exception:
            pass
    m2 = re.search(r'(?:maxStackSize|setMaxStackSize)\s*[=:]?\s*([0-9]+)', java_code)
    if m2 and props["max_stack_size"] is None:
        try:
            props["max_stack_size"] = int(m2.group(1))
        except Exception:
            pass
    m3 = re.search(r'(?:defaultMaxDamage|maxDamage|setMaxDamage)\(\s*([0-9]+)\s*\)', java_code)
    if m3:
        try:
            props["durability"] = int(m3.group(1))
        except Exception:
            pass
    m4 = re.search(r'setRegistryName\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
    if m4:
        props["registry_name"] = m4.group(1)
        props["texture_hint"] = m4.group(1).split(":")[-1]
    else:
        m5 = re.search(r'new\s+ResourceLocation\(\s*["\']([a-z0-9_:-]+)["\']', java_code, re.I)
        if m5:
            props["registry_name"] = m5.group(1)
            props["texture_hint"] = m5.group(1).split(":")[-1]
    m6 = re.search(r'ItemGroup\.([A-Z0-9_]+)', java_code)
    if m6:
        props["creative_tab"] = m6.group(1).lower()
    return props

def convert_java_item_to_bedrock(java_path: str, namespace: str):
    try:
        with open(java_path, 'r', encoding='utf-8', errors='ignore') as f:
            java_code = f.read()
    except Exception as e:
        print(f"❌ Failed to read item java {java_path}: {e}")
        return
    item_basename = os.path.splitext(os.path.basename(java_path))[0]
    item_id = f"{sanitize_identifier(namespace)}:{sanitize_identifier(item_basename)}"
    props = extract_item_properties_from_java(java_code)
    bp_item = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:item": {
            "description": {"identifier": item_id, "register_to_creative_menu": True},
            "components": {}
        }
    }
    comps = bp_item["minecraft:item"]["components"]
    comps["minecraft:max_stack_size"] = props.get("max_stack_size") if props.get("max_stack_size") is not None else 64
    if props.get("durability") is not None:
        comps["minecraft:durability"] = {"max_durability": props["durability"]}
    comps["_converter_metadata"] = {"source_java_file": os.path.basename(java_path), "parsed_props": props}
    out_bp = os.path.join(BP_FOLDER, "items", f"{sanitize_identifier(item_basename)}.json")
    safe_write_json(out_bp, bp_item)
    print(f"Converted item (BP) {java_path} -> {out_bp}")
    texture_ref = resolve_texture_reference(namespace, props.get("texture_hint"), "items", fallback_name=sanitize_identifier(item_basename))
    rp_item = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:item": {
            "description": {"identifier": item_id, "category": props.get("creative_tab") or "misc"},
            "components": {"minecraft:icon": texture_ref}
        }
    }
    out_rp = os.path.join(RP_FOLDER, "items", f"{sanitize_identifier(item_basename)}.item.json")
    safe_write_json(out_rp, rp_item)
    print(f"Converted item (RP) {java_path} -> {out_rp}")

# -------------------------
# Entity detection & conversion (unchanged logic)
# -------------------------
NON_ENTITY_KEYWORDS = [
    "renderer", "render", "model", "procedure", "tickupdate", "factory",
    "packet", "handler", "provider", "command", "ui", "screen", "container",
    "event", "client", "server", "loader", "registry", "setup",
    "capability", "config", "network", "message", "gui", "recipe",
    "serializer", "codec", "datafixer", "loot", "structure"
]
ENTITY_OVERRIDE_KEYWORDS = ["entity", "mob", "monster", "creature", "animal", "boss", "npc"]

_ENTITY_SUPERCLASSES = {
    # Vanilla / shared
    'Entity', 'Mob', 'Monster', 'Animal', 'PathfinderMob', 'TamableAnimal',
    'TameableAnimal', 'CreatureEntity', 'LivingEntity', 'MobEntity',
    'WaterAnimal', 'AmbientCreature', 'FlyingMob', 'AbstractGolem',
    'AbstractVillager', 'AbstractPiglin', 'AbstractSkeleton',
    'Projectile', 'AbstractArrow',
    # NeoForge-specific base classes
    'NeoForgeEntity', 'NeoForgeMob',
    # Common shared mob patterns
    'AbstractNeutralMob', 'AbstractHurtingProjectile', 'FireworkRocketEntity',
    'ThrowableProjectile', 'ThrowableItemProjectile',
}
_ENTITY_METHOD_NAMES = {
    'registerGoals', 'defineSynchedData', 'createAttributes',
    'getAddEntityPacket', 'getDefaultAttributes', 'createMobAttributes',
    'createNavigation', 'createBodyControl', 'createMonsterAttributes',
    'createAnimalAttributes', 'createLivingAttributes',
    # NeoForge-specific hooks
    'initializeClient', 'onAddedToWorld', 'onRemovedFromWorld',
}

def is_likely_entity(java_code: str, filename: str) -> bool:
    fname = os.path.basename(filename).lower()
    has_override = any(k in fname for k in ENTITY_OVERRIDE_KEYWORDS)
    if not has_override:
        for k in NON_ENTITY_KEYWORDS:
            if k in fname:
                return False

    cls = extract_class_name(java_code) or ""
    if cls.lower().endswith("entity"):
        return True

    # Try AST-based detection first
    ast = JavaAST(java_code)
    ast._parse()
    if ast._tree is not None:
        # Check superclass
        for child, parent in ast.all_class_extends():
            if JavaAST.strip_generics(parent) in _ENTITY_SUPERCLASSES:
                return True
        # Check for entity-specific method declarations
        if ast.method_names() & _ENTITY_METHOD_NAMES:
            return True
        # Check for EntityType.Builder usage in object creations
        for ctype in ast.all_object_creation_types():
            if 'Entity' in ctype or 'Mob' in ctype:
                return True
        return False

    # Regex fallback
    if re.search(r'extends\s+(?:[A-Za-z0-9_<>.,\s]*\b(?:Entity|Mob|Monster|Animal|PathfinderMob|TamableAnimal|TameableAnimal|CreatureEntity|LivingEntity|MobEntity|WaterAnimal|AmbientCreature|FlyingMob|AbstractGolem|AbstractVillager|AbstractPiglin|AbstractSkeleton|Projectile|AbstractArrow|AbstractNeutralMob|ThrowableProjectile|ThrowableItemProjectile)\b)', java_code):
        return True
    entity_methods = [
        r'\bregisterGoals\s*\(', r'\bdefineSynchedData\s*\(',
        r'\bcreateAttributes\s*\(', r'\bgetAddEntityPacket\s*\(',
        r'\bgetDefaultAttributes\s*\(', r'\bcreateMobAttributes\s*\(',
        r'\bcreateNavigation\s*\(', r'\bcreateBodyControl\s*\(',
        r'EntityType\.Builder\.of', r'\bcreateMonsterAttributes\s*\(',
        r'\bcreateAnimalAttributes\s*\(', r'\bcreatelivingAttributes\s*\(',
        # NeoForge-specific patterns
        r'\binitializeClient\s*\(',
        r'net\.neoforged\.[a-z.]+Entity',
        r'@EventBusSubscriber\b.*?Bus\.MOD',
    ]
    for pat in entity_methods:
        if re.search(pat, java_code):
            return True
    return False

def extract_entity_texture_hint(java_code: str, entity_basename: Optional[str] = None) -> Optional[str]:
    m = re.search(r'TEXTURE[^\n\r]*?["\']([A-Za-z0-9_:/\-\.]+)["\']', java_code)
    if m:
        candidate = m.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    m2 = re.search(r'setTexture\(\s*["\']([A-Za-z0-9_:/\-\.]+)["\']', java_code)
    if m2:
        candidate = m2.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    m3 = re.search(r'new\s+ResourceLocation\s*\(\s*["\']([a-z0-9_:-]+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)', java_code, re.IGNORECASE)
    if m3:
        ns = m3.group(1)
        path = m3.group(2)
        candidate = f"{ns}:{path}"
        if is_probable_texture(candidate, entity_basename):
            return candidate
    m4 = re.search(r'new\s+ResourceLocation\(\s*["\']([a-z0-9_:-]+)["\']\s*\)', java_code, re.IGNORECASE)
    if m4:
        candidate = m4.group(1)
        if is_probable_texture(candidate, entity_basename):
            return candidate
    return None

def is_probable_texture(candidate: Optional[str], entity_basename: Optional[str] = None) -> bool:
    if not candidate:
        return False
    candidate = str(candidate)
    if "textures/" in candidate.lower() or candidate.lower().endswith(".png"):
        return True
    if re.search(r'(blocks|items|entity|textures)[\/:]', candidate, re.I):
        return True
    name = candidate.split(":")[-1].replace(".png", "")
    probes = [f"entity/{name}", f"items/{name}", f"blocks/{name}", f"{name}"]
    for p in probes:
        if rp_texture_exists(p):
            return True
    sound_indicators = ["sound", "sounds", "whisper", "sfx", "ambient", "step", "attack", "wraith", "growl", "roar"]
    if any(k in candidate.lower() for k in sound_indicators) and not "/" in candidate:
        return False
    if ":" in candidate and "/" in candidate:
        return True
    if entity_basename and entity_basename.lower() in candidate.lower():
        return True
    return False

def convert_java_to_bedrock(java_path: str, entity_identifier: str, gecko_maps: dict, geom_file_map: dict, geom_ns_map: dict, anim_key_map: dict, stats: dict):
    try:
        with open(java_path, 'r', encoding='utf-8', errors='ignore') as f:
            java_code = f.read()
    except Exception as e:
        print(f"❌ Failed to read {java_path}: {e}")
        stats["errors"].append(f"read:{java_path}:{e}")
        return

    if not is_likely_entity(java_code, java_path):
        stats["skipped_files"].append(java_path)
        return

    parts = entity_identifier.split(":")
    namespace = sanitize_identifier(parts[0]) if parts else "converted"
    entity_name = sanitize_identifier(parts[1]) if len(parts) > 1 else sanitize_identifier("entity")
    clean_identifier = f"{namespace}:{entity_name}"

    ai_goals = extract_ai_goals_from_java(java_code)
    animations = extract_animations_from_java(java_code, namespace, entity_name)
    attributes = extract_attributes_from_java(java_code)
    immunities = extract_damage_immunities_from_java(java_code)
    bounding_proc = detect_dynamic_bounding_procedure(java_code)
    despawn_ticks = detect_despawn_ticks(java_code)

    collision_w, collision_h = 0.6, 1.8
    if bounding_proc:
        collision_w, collision_h = 2.5, 3.0
    m_dims = re.search(r'EntityDimensions\.(?:scalable|fixed)\s*\(\s*([0-9.]+)\s*,\s*([0-9.]+)', java_code)
    if m_dims:
        collision_w, collision_h = float(m_dims.group(1)), float(m_dims.group(2))
    else:
        m_dims2 = re.search(r'getDimensions[^{]*\{[^}]*\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)', java_code, re.DOTALL)
        if m_dims2:
            collision_w, collision_h = float(m_dims2.group(1)), float(m_dims2.group(2))

    bedrock_entity = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:entity": {
            "description": {"identifier": clean_identifier, "is_spawnable": True, "is_experimental": False},
            "components": {
                "minecraft:type_family": {"family": ["mob", namespace]},
                "minecraft:physics": {"has_gravity": True, "has_collision": True},
                "minecraft:collision_box": {"width": collision_w, "height": collision_h},
                "minecraft:health": {"value": int(attributes.get("health", 20)), "max": int(attributes.get("health", 20))},
                "minecraft:movement": {"value": attributes.get("movement_speed", 0.3)},
                "minecraft:navigation.walk": {"can_path_over_water": False, "avoid_water": True, "can_pass_doors": True},
                "minecraft:movement.basic": {},
                "minecraft:jump.static": {},
                "minecraft:behavior.float": {"priority": 0}
            },
            "events": {}
        }
    }

    if attributes.get("attack_damage", 0) > 0:
        bedrock_entity["minecraft:entity"]["components"]["minecraft:attack"] = {"damage": int(attributes["attack_damage"])}

    armor_value = float(attributes.get("armor", 0.0))
    damage_triggers = []
    if armor_value and armor_value != 0.0:
        # Java armor uses a 0-30 scale (full diamond = 20, max = 30).
        # Each armor point reduces damage by ~4%, capped at ~80% reduction.
        # Formula: reduction = armor / (armor + 4*(damage/toughness+8)), approximated here.
        # Simple approximation: each point = ~3.5% reduction, capped at 80%.
        reduction = min(0.80, armor_value * 0.035)
        multiplier = max(0.20, 1.0 - reduction)
        damage_triggers.append({"cause": "all", "damage_multiplier": round(multiplier, 4), "description": "converted_armor_java_scale"})
    for cause in immunities:
        if cause == "all":
            continue
        damage_triggers.append({"cause": cause, "damage_multiplier": 0.001, "description": f"converted_immunity_{cause}"})
    damage_triggers.append({"cause": "entity_attack", "deals_damage": True})
    bedrock_entity["minecraft:entity"]["components"]["minecraft:damage_sensor"] = {"triggers": damage_triggers}

    behaviors = {}
    move_speed = attributes.get("movement_speed", 0.3)
    follow_range = attributes.get("follow_range", 16.0)

    for goal in ai_goals:
        priority = JAVA_GOAL_PRIORITIES.get(goal, 10)

        # ── Targeting ──
        if goal == "NearestAttackableTargetGoal":
            behaviors["minecraft:behavior.nearest_attackable_target"] = {
                "priority": priority,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": int(follow_range)}],
                "must_see": False,
                "reselect_targets": True
            }
        elif goal == "HurtByTargetGoal":
            behaviors["minecraft:behavior.hurt_by_target"] = {
                "priority": priority,
                "alert_same_type": False
            }
        elif goal in ("OwnerHurtByTargetGoal", "OwnerHurtTargetGoal"):
            behaviors["minecraft:behavior.owner_hurt_by_target"] = {"priority": priority}

        # ── Combat ──
        elif goal == "MeleeAttackGoal":
            behaviors["minecraft:behavior.melee_attack"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 2.0),
                "track_target": True,
                "require_complete_path": False
            }
        elif goal in ("RangedAttackGoal", "RangedBowAttackGoal"):
            behaviors["minecraft:behavior.ranged_attack"] = {
                "priority": priority,
                "attack_interval_min": 1.0,
                "attack_interval_max": 3.0,
                "attack_radius": min(follow_range, 15.0),
                "speed_multiplier": max(1.0, move_speed * 1.5)
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:shooter"] = {
                "def": "minecraft:arrow"
            }
        elif goal == "LeapAtTargetGoal":
            behaviors["minecraft:behavior.leap_at_target"] = {
                "priority": priority,
                "yd": 0.4
            }

        # ── Avoidance / flee ──
        elif goal == "AvoidEntityGoal":
            behaviors["minecraft:behavior.avoid_mob_type"] = {
                "priority": priority,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": 6.0}],
                "walk_speed_multiplier": max(1.0, move_speed * 1.2),
                "sprint_speed_multiplier": max(1.2, move_speed * 2.0)
            }
        elif goal == "PanicGoal":
            behaviors["minecraft:behavior.panic"] = {
                "priority": priority,
                "speed_multiplier": max(1.25, move_speed * 2.5)
            }
        elif goal == "RunAroundLikeCrazyGoal":
            behaviors["minecraft:behavior.run_around_like_crazy"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 2.0)
            }

        # ── Doors ──
        elif goal == "OpenDoorGoal":
            behaviors["minecraft:behavior.open_door"] = {
                "priority": priority,
                "close_door_after": True
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_open_doors"] = True
        elif goal == "BreakDoorGoal":
            behaviors["minecraft:behavior.break_door"] = {
                "priority": priority
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_break_doors"] = True

        # ── Following ──
        elif goal == "FollowOwnerGoal":
            behaviors["minecraft:behavior.follow_owner"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.5),
                "start_distance": 10.0,
                "stop_distance": 2.0
            }
        elif goal == "FollowParentGoal":
            behaviors["minecraft:behavior.follow_parent"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.1)
            }
        elif goal == "FollowMobGoal":
            behaviors["minecraft:behavior.follow_mob"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.1),
                "stop_distance": 3.0,
                "search_range": int(follow_range)
            }

        # ── Tamed / social ──
        elif goal == "SitWhenOrderedToGoal":
            behaviors["minecraft:behavior.sit"] = {"priority": priority}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:is_tamed"] = {}
        elif goal == "BreedGoal":
            behaviors["minecraft:behavior.breed"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.0)
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:breedable"] = {
                "require_tame": False,
                "breeds_with": []
            }
        elif goal == "TemptGoal":
            behaviors["minecraft:behavior.tempt"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.25),
                "within_radius": 6.0,
                "can_tempt_while_leashed": False
            }

        # ── Movement ──
        elif goal == "FloatGoal":
            behaviors["minecraft:behavior.float"] = {"priority": priority}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "WaterAvoidingRandomStrollGoal":
            behaviors["minecraft:behavior.random_stroll"] = {
                "priority": priority,
                "speed_multiplier": move_speed,
                "xz_dist": 10,
                "y_dist": 7
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["avoid_water"] = True
        elif goal == "RandomSwimmingGoal":
            behaviors["minecraft:behavior.random_swimming"] = {
                "priority": priority,
                "speed_multiplier": max(1.0, move_speed * 1.5),
                "xz_dist": 30,
                "y_dist": 15
            }
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "RandomStrollGoal":
            behaviors["minecraft:behavior.random_stroll"] = {
                "priority": priority,
                "speed_multiplier": move_speed
            }

        # ── Look ──
        elif goal == "LookAtPlayerGoal":
            behaviors["minecraft:behavior.look_at_player"] = {
                "priority": priority,
                "look_distance": follow_range / 2.0,
                "probability": 0.02
            }
        elif goal == "RandomLookAroundGoal":
            behaviors["minecraft:behavior.random_look_around"] = {"priority": priority}

        # ── Float / swim extras ──
        elif goal == "SwimGoal":
            behaviors["minecraft:behavior.float"] = {"priority": priority}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "BreatheAirGoal":
            behaviors["minecraft:behavior.move_to_water"] = {"priority": priority, "search_range": 8, "search_height": 4}

        # ── Extra targeting ──
        elif goal in ("NearestAttackableTargetExpiringGoal", "ToggleableNearestAttackableTargetGoal"):
            behaviors.setdefault("minecraft:behavior.nearest_attackable_target", {
                "priority": priority, "must_see": False, "reselect_targets": True,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": int(follow_range)}]
            })
        elif goal == "NonTamedTargetGoal":
            behaviors["minecraft:behavior.nearest_attackable_target"] = {
                "priority": priority, "must_see": True,
                "entity_types": [{"filters": {"all_of": [
                    {"test": "is_family", "subject": "other", "value": "player"},
                    {"test": "is_owner", "subject": "other", "operator": "!=", "value": True}
                ]}, "max_dist": int(follow_range)}]
            }
        elif goal == "DefendVillageTargetGoal":
            behaviors["minecraft:behavior.nearest_attackable_target"] = {
                "priority": priority, "must_see": False,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "monster"}, "max_dist": int(follow_range)}]
            }
        elif goal == "ResetAngerGoal":
            bedrock_entity["minecraft:entity"]["components"].setdefault("minecraft:anger_level", {"max_anger": 20, "anger_decrement_interval": 1.0})

        # ── Combat extras ──
        elif goal == "OcelotAttackGoal":
            behaviors["minecraft:behavior.melee_attack"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 2.0), "track_target": True, "require_complete_path": False}
        elif goal == "CreeperSwellGoal":
            behaviors["minecraft:behavior.swell"] = {"priority": priority}
        elif goal == "RangedCrossbowAttackGoal":
            behaviors["minecraft:behavior.ranged_attack"] = {"priority": priority, "attack_interval_min": 1.0, "attack_interval_max": 3.0, "attack_radius": min(follow_range, 15.0), "speed_multiplier": max(1.0, move_speed * 1.5)}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:shooter"] = {"def": "minecraft:arrow"}
        elif goal == "MoveTowardsTargetGoal":
            behaviors["minecraft:behavior.move_towards_target"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.5), "within": int(follow_range)}

        # ── Sun avoidance ──
        elif goal == "FleeSunGoal":
            behaviors["minecraft:behavior.move_outdoors"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.2), "timeout_cooldown": 8.0}
        elif goal == "RestrictSunGoal":
            behaviors["minecraft:behavior.restrict_sun"] = {"priority": priority}

        # ── Door / block interaction ──
        elif goal == "InteractDoorGoal":
            behaviors["minecraft:behavior.open_door"] = {"priority": priority, "close_door_after": True}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_open_doors"] = True
        elif goal == "BreakBlockGoal":
            behaviors["minecraft:behavior.break_door"] = {"priority": priority}
        elif goal == "UseItemGoal":
            pass  # highly context-specific, no generic Bedrock equivalent

        # ── Navigation / village ──
        elif goal in ("MoveThroughVillageGoal", "MoveThroughVillageAtNightGoal", "ReturnToVillageGoal", "PatrolVillageGoal", "MoveTowardsRaidGoal"):
            behaviors["minecraft:behavior.move_through_village"] = {"priority": priority, "speed_multiplier": move_speed, "only_at_night": goal == "MoveThroughVillageAtNightGoal"}
        elif goal == "MoveTowardsRestrictionGoal":
            behaviors["minecraft:behavior.move_towards_restriction"] = {"priority": priority, "speed_multiplier": move_speed}
        elif goal == "MoveToBlockGoal":
            behaviors["minecraft:behavior.move_to_block"] = {"priority": priority, "speed_multiplier": move_speed, "search_range": 8, "search_height": 4, "goal_radius": 1.0}
        elif goal == "FindWaterGoal":
            behaviors["minecraft:behavior.move_to_water"] = {"priority": priority, "search_range": 8, "search_height": 4}
            bedrock_entity["minecraft:entity"]["components"]["minecraft:navigation.walk"]["can_swim"] = True
        elif goal == "RandomWalkingGoal":
            behaviors["minecraft:behavior.random_stroll"] = {"priority": priority, "speed_multiplier": move_speed}

        # ── Following extras ──
        elif goal == "FollowBoatGoal":
            behaviors["minecraft:behavior.follow_mob"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.2), "stop_distance": 3.0, "search_range": int(follow_range)}
        elif goal == "FollowSchoolLeaderGoal":
            behaviors["minecraft:behavior.follow_mob"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.1), "stop_distance": 2.0, "search_range": int(follow_range)}
        elif goal == "LlamaFollowCaravanGoal":
            behaviors["minecraft:behavior.follow_caravan"] = {"priority": priority, "speed_multiplier": max(1.0, move_speed * 1.2)}
        elif goal == "LandOnOwnersShoulderGoal":
            behaviors.setdefault("minecraft:behavior.float", {"priority": 0})

        # ── Social / misc ──
        elif goal == "SitGoal":
            behaviors["minecraft:behavior.sit"] = {"priority": priority}
        elif goal == "EatGrassGoal":
            behaviors["minecraft:behavior.eat_block"] = {"priority": priority, "eat_and_replace_block_pairs": [{"eat_block": "grass", "replace_block": "dirt"}], "success_chance": "0.05", "time_until_eat": 1.8}
        elif goal == "BegGoal":
            behaviors["minecraft:behavior.beg"] = {"priority": priority, "look_distance": 8.0, "look_time": 40}
        elif goal == "TradeWithPlayerGoal":
            behaviors["minecraft:behavior.trade_with_player"] = {"priority": priority}
        elif goal == "LookAtCustomerGoal":
            behaviors["minecraft:behavior.look_at_trading_player"] = {"priority": priority}
        elif goal == "ShowVillagerFlowerGoal":
            behaviors["minecraft:behavior.offer_flower"] = {"priority": priority}
        elif goal == "TriggerSkeletonTrapGoal":
            behaviors["minecraft:behavior.summon_entity"] = {"priority": priority, "summon_choices": [{"min_activation_range": 0, "max_activation_range": 16, "summon_cap": 4, "summon_cap_radius": 8.0, "weight": 10, "entity_type": "minecraft:skeleton_horse"}]}
        elif goal == "DolphinJumpGoal":
            behaviors["minecraft:behavior.jump_for_food"] = {"priority": priority}
        elif goal == "JumpGoal":
            behaviors["minecraft:behavior.jump_to_block"] = {"priority": priority, "search_width": 8, "search_height": 4, "minimum_path_length": 2}
        elif goal == "CatLieOnBedGoal":
            behaviors["minecraft:behavior.sleep"] = {"priority": priority, "sleep_collider_height": 0.3, "sleep_collider_width": 1.0, "sleep_y_offset": 0.6, "timeout_cooldown": 10.0}
        elif goal == "CatSitOnBlockGoal":
            behaviors["minecraft:behavior.move_to_block"] = {"priority": priority, "speed_multiplier": move_speed, "search_range": 8, "search_height": 4, "goal_radius": 1.0}

        # ── Look extras ──
        elif goal == "LookAtGoal":
            behaviors["minecraft:behavior.look_at_entity"] = {"priority": priority, "look_distance": follow_range / 2.0, "probability": 0.02}
        elif goal == "LookAtWithoutMovingGoal":
            behaviors["minecraft:behavior.look_at_player"] = {"priority": priority, "look_distance": follow_range / 2.0, "probability": 0.02}
        elif goal == "LookRandomlyGoal":
            behaviors["minecraft:behavior.random_look_around"] = {"priority": priority}

    # Always ensure float behavior exists if not already set by FloatGoal
    if "minecraft:behavior.float" not in behaviors:
        behaviors["minecraft:behavior.float"] = {"priority": 0}

    if behaviors:
        bedrock_entity["minecraft:entity"]["components"].update(behaviors)

    # ── Extra components based on detected goals ──
    # Tamed entities need is_tamed and tameable
    if any(g in ai_goals for g in ("SitWhenOrderedToGoal", "FollowOwnerGoal", "OwnerHurtByTargetGoal", "OwnerHurtTargetGoal")):
        bedrock_entity["minecraft:entity"]["components"].setdefault("minecraft:tameable", {
            "probability": 0.33,
            "tame_items": "bone",
            "tame_event": {"event": "minecraft:on_tame", "target": "self"}
        })
        bedrock_entity["minecraft:entity"]["components"].setdefault("minecraft:is_tamed", {})

    # Smart navigation based on entity type
    comps = bedrock_entity["minecraft:entity"]["components"]
    is_flyer = bool(
        re.search(r'extends\s+(?:FlyingMob|Ghast|Phantom|Bee|Parrot|AbstractFlyingEntity)', java_code, re.I) or
        re.search(r'FlyingMoveControl|setNoGravity\s*\(\s*true', java_code)
    )
    is_swimmer = bool(
        re.search(r'extends\s+(?:WaterAnimal|Squid|Dolphin|TropicalFish|AbstractFish)', java_code, re.I) or
        "RandomSwimmingGoal" in ai_goals or "FindWaterGoal" in ai_goals
    )
    is_climber = bool(re.search(r'canClimb\(\)|onClimbable|Spider|CaveSpider', java_code, re.I))
    if is_flyer and not is_swimmer:
        comps.pop("minecraft:navigation.walk", None)
        comps["minecraft:navigation.fly"] = {"can_path_over_water": True}
        comps["minecraft:movement.fly"] = {}
        comps.pop("minecraft:jump.static", None)
        comps["minecraft:can_fly"] = {}
    elif is_swimmer:
        comps["minecraft:navigation.walk"]["can_swim"] = True
        comps.setdefault("minecraft:navigation.swim", {"can_path_over_water": True})
        comps["minecraft:underwater_movement"] = {"value": round(attributes.get("movement_speed", 0.3) * 0.85, 4)}
    if is_climber:
        comps["minecraft:navigation.climb"] = {}

    # ── Entity events, component groups, effects, equipment ──
    generate_entity_events(bedrock_entity, ai_goals, java_code, namespace, clean_identifier, attributes)

    if despawn_ticks is not None and despawn_ticks <= 600:
        bedrock_entity["minecraft:entity"]["components"]["minecraft:timer"] = {
            "looping": False,
            "time": round(despawn_ticks / 20.0, 2),
            "time_down_event": {"event": "minecraft:entity_spawned"}
        }

    metadata = {
        "source_java_file": os.path.basename(java_path),
        "raw_attributes": attributes,
        "animations_extracted": sorted(list(animations)),
        "immunities_detected": immunities,
        "dynamic_bounding_box_procedure": bounding_proc,
        "despawn_after_ticks": despawn_ticks
    }
    bedrock_entity["minecraft:entity"]["components"]["_converter_metadata"] = metadata

    # --- Animation JSON creation (BP + RP) ---
    def should_loop(anim_name: str) -> bool:
        n = anim_name.lower()
        if any(k in n for k in ["idle", "chase", "walk", "run", "pose", "sit", "hover"]):
            return True
        if any(k in n for k in ["attack", "hit", "strike", "death", "slam", "bite"]):
            return False
        return True

    # Bedrock animations are RP-side only — BP entities never reference animation files.
    # We only write to RP/animations/. Stubs are skipped if GeckoLib-exported files
    # are already present (they will be found by anim_key_map from copy_geckolib_animations_from_jar).
    anim_json = {"format_version": RP_LEGACY_ANIM_FORMAT, "animations": {}}
    primary_animation_key = None
    if animations:
        for anim in sorted(animations):
            loop = should_loop(anim)
            length = 1.0 if loop else 0.5
            anim_json["animations"][anim] = {"loop": loop, "animation_length": length}
        primary_animation_key = sorted(animations)[0]
    else:
        base_id = f"animation.{namespace}.{entity_name}"
        idle_id = f"{base_id}.idle"
        anim_json["animations"][idle_id] = {"loop": True, "animation_length": 1.0}
        anim_json["animations"][f"{base_id}.walk"] = {"loop": True, "animation_length": 0.5}
        anim_json["animations"][f"{base_id}.run"] = {"loop": True, "animation_length": 0.4}
        anim_json["animations"][f"{base_id}.attack"] = {"loop": False, "animation_length": 0.5}
        primary_animation_key = idle_id

    entity_basename = sanitize_identifier(os.path.splitext(os.path.basename(java_path))[0])
    # Only write RP animations — skip if a real GeckoLib animation file already exists there
    anim_json_path_rp = os.path.join(RP_FOLDER, "animations", f"{entity_basename}.animation.json")
    if not os.path.exists(anim_json_path_rp):
        safe_write_json(anim_json_path_rp, anim_json)
        print(f"[anim] Wrote stub RP animation JSON: {anim_json_path_rp}")
    else:
        print(f"[anim] Skipped stub write — GeckoLib animation already present: {anim_json_path_rp}")

    entity_json_path = os.path.join(BP_FOLDER, "entities", f"{entity_basename}.json")
    safe_write_json(entity_json_path, bedrock_entity)
    print(f"Converted (BP entity) {java_path} -> {entity_json_path}")
    stats["converted_entities_bp"].append(entity_json_path)

    # --- RP client entity generation only if geometry resolvable ---
    texture_hint = extract_entity_texture_hint(java_code, entity_basename)
    texture_ref = resolve_texture_reference(namespace, texture_hint, "entity", fallback_name=entity_basename)

    # geckolib mapping attempts
    entity_class_simple = os.path.splitext(os.path.basename(java_path))[0]
    geom_tuple = None
    geom_tuple = gecko_maps.get("entity_to_geometry", {}).get(entity_class_simple)
    if not geom_tuple:
        for k, v in gecko_maps.get("entity_to_geometry", {}).items():
            if k.lower() == entity_class_simple.lower() or k.lower().endswith(entity_class_simple.lower()) or entity_class_simple.lower().endswith(k.lower()):
                geom_tuple = v
                break
    if not geom_tuple:
        model_cls = gecko_maps.get("entity_to_model", {}).get(entity_class_simple)
        if model_cls:
            geom_tuple = gecko_maps.get("model_map", {}).get(model_cls)
    if not geom_tuple:
        for model_cls, geom in gecko_maps.get("model_map", {}).items():
            if entity_basename.lower() in model_cls.lower() or entity_basename.lower() in geom[1].lower():
                geom_tuple = geom
                break
    if not geom_tuple:
        geom_tuple = find_model_geometry_in_code(java_code)

    geom_identifier = None
    if geom_tuple:
        ns_hint, geom_name = geom_tuple
        ns_hint_clean = sanitize_identifier(ns_hint) if ns_hint else None
        geom_name_clean = sanitize_identifier(geom_name) if geom_name else None
        key = (ns_hint_clean, geom_name_clean)
        if key in geom_ns_map:
            geom_identifier = geom_ns_map[key]
        else:
            key2 = (namespace.lower(), geom_name_clean)
            if key2 in geom_ns_map:
                geom_identifier = geom_ns_map[key2]
            else:
                if geom_name_clean in geom_file_map:
                    geom_identifier = geom_file_map[geom_name_clean]
                else:
                    for (ns_k, name_k), ident in geom_ns_map.items():
                        if name_k and geom_name_clean and name_k.endswith(geom_name_clean):
                            geom_identifier = ident
                            break

    if not geom_identifier:
        if entity_basename.lower() in geom_file_map:
            geom_identifier = geom_file_map[entity_basename.lower()]

    if not geom_identifier:
        stats["missing_geometry"].append((java_path, entity_basename))
        print(f"[skip-rp] No geometry found for entity {entity_basename} (java:{java_path}). BP entity written but RP client entity skipped to avoid broken links.")
        return

    # finalize animation key selection
    chosen_animation_key = None
    if primary_animation_key:
        candidate = canonicalize_animation_id(primary_animation_key, namespace, entity_name)
        found = False
        for keys in anim_key_map.values():
            if candidate in keys:
                chosen_animation_key = candidate
                found = True
                break
        if not found:
            for keys in anim_key_map.values():
                for k in keys:
                    if entity_basename.lower() in k.lower() or (geom_tuple and geom_tuple[1].lower() in k.lower()):
                        chosen_animation_key = k
                        found = True
                        break
                if found:
                    break
        if not found and candidate:
            # Use freshly generated key even if preloaded anim_key_map doesn't include it yet.
            chosen_animation_key = candidate
        if chosen_animation_key:
            chosen_animation_key = canonicalize_animation_id(chosen_animation_key, namespace, entity_name)

    # --- Animation controller (must happen BEFORE RP entity write so we can wire it in) ---
    anim_controller_id = None
    if animations:
        anim_controller_id = generate_animation_controller(
            clean_identifier, animations, namespace,
            ai_goals=ai_goals, java_code=java_code
        )

    # --- Write RP client entity + render controller ---
    controller_id = write_render_controller(entity_basename.lower(), namespace.lower(), geom_identifier, uv_anim=None)
    write_rp_entity_json(entity_basename.lower(), namespace.lower(), texture_ref, geom_identifier, chosen_animation_key, controller_id)
    stats["converted_entities_rp"].append(os.path.join(RP_FOLDER, "entity", f"{entity_basename}.entity.json"))

    # --- Wire all animations + animation controller into RP entity ---
    patch_rp_entity_with_controller(entity_basename.lower(), animations, anim_controller_id, namespace)

    # --- Spawn rules ---
    generate_spawn_rules(clean_identifier, java_code, namespace)

    # --- Particles ---
    extract_and_generate_particles(java_code, clean_identifier, namespace)

    # --- Trading table (if entity trades with player) ---
    if "TradeWithPlayerGoal" in ai_goals:
        generate_trading_table(clean_identifier, java_code, namespace)

# -------------------------
# Icon helper: crop & resize to valid pack size
# -------------------------
def choose_icon_size_for(width: int, height: int) -> int:
    # choose the largest valid size <= min(width,height); if none, choose the smallest valid size
    m = min(width, height)
    valid_under = [s for s in VALID_ICON_SIZES if s <= m]
    if valid_under:
        return max(valid_under)
    return VALID_ICON_SIZES[0]

def ensure_and_fix_pack_icon(src_path: str, dest_path: str):
    """
    Ensure pack icon is square and one of VALID_ICON_SIZES.
    If PIL is available it will center-crop and resize to the largest valid size <= min(dim).
    If PIL is not available, the file will be copied but a warning will be printed.
    """
    if not os.path.exists(src_path):
        print(f"[icon] source icon not found: {src_path}")
        return False
    if not PIL_AVAILABLE:
        print("⚠ Pillow (PIL) not installed — pack_icon.png will be copied unmodified. To auto-fix sizing run: pip install pillow")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(src_path, dest_path)
        return False

    try:
        with Image.open(src_path) as im:
            w, h = im.size
            # center crop to square
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            right = left + side
            bottom = top + side
            im_cropped = im.crop((left, top, right, bottom))
            target_size = choose_icon_size_for(side, side)
            if (im_cropped.size[0], im_cropped.size[1]) != (target_size, target_size):
                im_resized = im_cropped.resize((target_size, target_size), Image.LANCZOS)
            else:
                im_resized = im_cropped
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            im_resized.save(dest_path, format="PNG")
            print(f"[icon] Wrote pack_icon.png with size {target_size}x{target_size} to {dest_path}")
            return True
    except Exception as e:
        print(f"[icon] Failed to process icon (PIL): {e}. Copying without transform.")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(src_path, dest_path)
        return False

# -------------------------
# Sounds registry writer (top-level mapping)
# -------------------------
def sanitize_sound_key(k: str) -> str:
    """
    Sanitize a sound ID key:
     - lowercase
     - replace occurrences of '-s' with '_s' (explicit request)
     - replace remaining '-' with '_'
     - collapse whitespace to underscores, remove invalid chars except dot
    """
    if not k:
        return ""
    s = str(k).lower()
    # explicit '-s' -> '_s' first (covers patterns like 'scream-something' -> 'scream_something' where ' -s ' existed)
    s = s.replace('-s', '_s')
    # replace remaining dashes with underscores
    s = s.replace('-', '_')
    s = re.sub(r'\s+', '_', s)
    # allow dots for namespace.separators, keep a-z0-9 and underscores and dots
    s = re.sub(r'[^a-z0-9_\.]', '_', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('._')
    return s

def _normalize_sound_name(name: str) -> str:
    """
    Normalize a sound name to the form Bedrock expects in sound_definitions.json:
    - strip any namespace prefix (e.g. "mod:scream_1" -> "scream_1")
    - strip file extension
    - sanitize hyphens/spaces to underscores
    - prepend "sound/" folder prefix (ogg files live in rp/sound/)
    """
    # strip namespace
    name = name.split(":")[-1]
    # strip leading sounds/ or sound/ folder if already present
    for prefix in ("sounds/", "sound/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # strip extension
    if "." in os.path.basename(name):
        name = name.rsplit(".", 1)[0]
    # sanitize
    name = sanitize_sound_key(name)
    # prepend correct folder
    return f"sound/{name}"

def _sanitize_sound_def(v) -> dict:
    """
    Clean a sound definition dict so all 'name' values are normalized
    to the form 'sound/<sanitized_stem>' with no namespace or extension.
    """
    if not isinstance(v, dict):
        return v
    result = dict(v)
    if "sounds" in result and isinstance(result["sounds"], list):
        cleaned = []
        for entry in result["sounds"]:
            if isinstance(entry, str):
                cleaned.append(_normalize_sound_name(entry))
            elif isinstance(entry, dict):
                e = dict(entry)
                if "name" in e and isinstance(e["name"], str):
                    e["name"] = _normalize_sound_name(e["name"])
                cleaned.append(e)
            else:
                cleaned.append(entry)
        result["sounds"] = cleaned
    return result

def generate_sounds_registry(mod_name: str):
    """
    Writes two sound files required by Bedrock:

    1. RP/sounds/sound_definitions.json
       Maps event_id -> { "sounds": [file paths] }
       This is the low-level file lookup table.

    2. RP/sounds.json  (root of RP)
       Maps entity identifier -> { "events": { slot: "event_id" } }
       This is what tells Bedrock which sound_definition event to fire for
       each entity lifecycle slot (ambient, hurt, death, step, etc.).
       Without this file entities are completely silent regardless of what
       is in sound_definitions.json.
    """
    global COLLECTED_SOUND_DEFS
    sounds_dir = os.path.join(RP_FOLDER, "sound")  # .ogg files live here

    # Scan .ogg files on disk; add stubs for any not already defined by JAR extraction
    if os.path.isdir(sounds_dir):
        for root, _, files in os.walk(sounds_dir):
            for f in files:
                if not f.lower().endswith(".ogg"):
                    continue
                stem = os.path.splitext(f)[0]
                sanitized_key = sanitize_sound_key(stem)
                if sanitized_key not in COLLECTED_SOUND_DEFS:
                    COLLECTED_SOUND_DEFS[sanitized_key] = {"sounds": [{"name": f"sound/{sanitized_key}"}]}

    # ── 1. sound_definitions.json ──────────────────────────────────────────
    if COLLECTED_SOUND_DEFS:
        final_defs: Dict[str, dict] = {}
        collisions = 0
        for raw_k, v in COLLECTED_SOUND_DEFS.items():
            new_k = sanitize_sound_key(raw_k)
            v = _sanitize_sound_def(v)
            if new_k in final_defs:
                collisions += 1
                fallback_k = f"{sanitize_sound_key(mod_name)}.{new_k}"
                if fallback_k in final_defs:
                    i = 2
                    while f"{fallback_k}_{i}" in final_defs:
                        i += 1
                    fallback_k = f"{fallback_k}_{i}"
                final_defs[fallback_k] = v
            else:
                final_defs[new_k] = v

        out_path = os.path.join(RP_FOLDER, "sounds", "sound_definitions.json")
        safe_write_json(out_path, {
            "format_version": "1.14.0",
            "sound_definitions": final_defs
        })
        print(f"[sounds] Wrote sound_definitions.json: {len(final_defs)} entries, {collisions} collision(s) resolved")
    else:
        print("[sounds] No sound definitions collected; skipping sound_definitions.json")

    # ── 2. sounds.json (entity sound events) ──────────────────────────────
    if _ENTITY_SOUND_EVENTS:
        # Bedrock sounds.json format:
        # {
        #   "entity.namespace:name": {
        #     "events": { "ambient": "event_id", "hurt": "event_id", ... },
        #     "pitch": [0.8, 1.2],
        #     "volume": 1.0
        #   }
        # }
        # The outer key MUST start with "entity." to be recognised.
        sounds_json: dict = {}
        for entity_id, entry in _ENTITY_SOUND_EVENTS.items():
            # Convert "namespace:name" -> "entity.namespace:name"
            outer_key = entity_id if entity_id.startswith("entity.") else f"entity.{entity_id}"
            sounds_json[outer_key] = entry

        out_path = os.path.join(RP_FOLDER, "sounds.json")
        safe_write_json(out_path, sounds_json)
        print(f"[sounds] Wrote sounds.json: {len(sounds_json)} entity sound entr{'y' if len(sounds_json)==1 else 'ies'}")
    else:
        print("[sounds] No entity sound events detected; skipping sounds.json")

JAVA_MOB_EFFECT_MAP = {
    "MOVEMENT_SPEED": "speed", "MOVEMENT_SLOWDOWN": "slowness",
    "DIG_SPEED": "haste", "DIG_SLOWDOWN": "mining_fatigue",
    "DAMAGE_BOOST": "strength", "HEAL": "instant_health",
    "HARM": "instant_damage", "JUMP": "jump_boost",
    "CONFUSION": "nausea", "REGENERATION": "regeneration",
    "DAMAGE_RESISTANCE": "resistance", "FIRE_RESISTANCE": "fire_resistance",
    "WATER_BREATHING": "water_breathing", "INVISIBILITY": "invisibility",
    "BLINDNESS": "blindness", "NIGHT_VISION": "night_vision",
    "HUNGER": "hunger", "WEAKNESS": "weakness", "POISON": "poison",
    "WITHER": "wither", "HEALTH_BOOST": "health_boost",
    "ABSORPTION": "absorption", "SATURATION": "saturation",
    "GLOWING": "glowing", "LEVITATION": "levitation",
    "LUCK": "luck", "UNLUCK": "unluck", "SLOW_FALLING": "slow_falling",
    "CONDUIT_POWER": "conduit_power", "DOLPHINS_GRACE": "dolphins_grace",
    "BAD_OMEN": "bad_omen", "HERO_OF_THE_VILLAGE": "village_hero",
    "DARKNESS": "darkness",
}

# =========================================================
# MOB EFFECTS EXTRACTION
# =========================================================
def extract_mob_effects_from_java(java_code: str) -> list:
    """Extract MobEffectInstance usages from Java code and map to Bedrock effects."""
    effects = []
    # Match: new MobEffectInstance(MobEffects.POISON, duration, amplifier)
    for m in re.finditer(
        r'new\s+MobEffectInstance\s*\(\s*MobEffects\.([A-Z_]+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?',
        java_code):
        java_name = m.group(1)
        duration_ticks = int(m.group(2))
        amplifier = int(m.group(3)) if m.group(3) else 0
        bedrock_name = JAVA_MOB_EFFECT_MAP.get(java_name)
        if bedrock_name:
            effects.append({
                "effect": bedrock_name,
                "duration": duration_ticks / 20.0,  # ticks -> seconds
                "amplifier": amplifier,
                "ambient": False,
                "visible": True
            })
    return effects



# =========================================================
# ENTITY SOUND EXTRACTION + COMPONENT GENERATION
# =========================================================

# Maps Java SoundEvents.XXX constants -> Bedrock sound event keys
JAVA_SOUND_EVENT_MAP = {
    # Generic mob sounds
    "ENTITY_GENERIC_AMBIENT":      "ambient",
    "ENTITY_GENERIC_DEATH":        "death",
    "ENTITY_GENERIC_HURT":         "hurt",
    "ENTITY_GENERIC_STEP":         "step",
    "ENTITY_GENERIC_SPLASH":       "splash",
    "ENTITY_GENERIC_SWIM":         "swim",
    "ENTITY_GENERIC_BIG_FALL":     "fall.big",
    "ENTITY_GENERIC_SMALL_FALL":   "fall.small",
    "ENTITY_GENERIC_DRINK":        "drink",
    "ENTITY_GENERIC_EAT":          "eat",
    "ENTITY_GENERIC_EXPLODE":      "explode",
    "ENTITY_GENERIC_ATTACK":       "attack",
    # Specific mob sounds (common patterns)
    "ENTITY_ZOMBIE_AMBIENT":       "ambient",
    "ENTITY_ZOMBIE_DEATH":         "death",
    "ENTITY_ZOMBIE_HURT":          "hurt",
    "ENTITY_SKELETON_AMBIENT":     "ambient",
    "ENTITY_SKELETON_DEATH":       "death",
    "ENTITY_SKELETON_HURT":        "hurt",
    "ENTITY_CREEPER_PRIMED":       "ambient",
    "ENTITY_WOLF_AMBIENT":         "ambient",
    "ENTITY_WOLF_DEATH":           "death",
    "ENTITY_WOLF_HURT":            "hurt",
    "ENTITY_CAT_AMBIENT":          "ambient",
    "ENTITY_PLAYER_ATTACK_STRONG": "attack",
    "ENTITY_PLAYER_HURT":          "hurt",
    "ENTITY_PLAYER_DEATH":         "death",
    "ENTITY_ENDERMAN_AMBIENT":     "ambient",
    "ENTITY_ENDERMAN_DEATH":       "death",
    "ENTITY_ENDERMAN_HURT":        "hurt",
    "ENTITY_ENDERMAN_STARE":       "ambient.stare",
    "ENTITY_WARDEN_AMBIENT":       "ambient",
    "ENTITY_WARDEN_DEATH":         "death",
    "ENTITY_WARDEN_HURT":          "hurt",
    "ENTITY_WARDEN_ROAR":          "roar",
}

# Maps method name -> Bedrock sound component key
JAVA_SOUND_METHOD_MAP = {
    "getAmbientSound":  "ambient",
    "ambientSound":     "ambient",
    "getDeathSound":    "death",
    "deathSound":       "death",
    "getHurtSound":     "hurt",
    "hurtSound":        "hurt",
    "getStepSound":     "step",
    "stepSound":        "step",
    "getSwimSound":     "swim",
    "swimSound":        "swim",
    "getSplashSound":   "splash",
    "splashSound":      "splash",
}

def _best_sound_key(raw_id: str, namespace: str) -> str:
    """
    Given a raw Java sound ID like 'theonewhowatches.entity.toww.ambient'
    or 'entity.toww_hunting.ambient', return the sanitized sound_definitions key.
    """
    raw_id = raw_id.strip().strip('"').strip("'")
    # Already namespaced  e.g. "toww:entity.hunting.ambient"
    if ":" in raw_id:
        raw_id = raw_id.split(":", 1)[1]
    return sanitize_sound_key(raw_id)


def extract_entity_sounds_from_java(java_code: str, entity_name: str, namespace: str) -> dict:
    """
    Parse Java entity source and return a dict of:
      { "ambient": "sound_key", "death": "sound_key", "hurt": "sound_key", ... }
    covering all sound slots we can detect.
    """
    sounds = {}

    # ── Pattern 1: return SoundEvents.XXX in getXxxSound() methods ──
    # e.g.  protected SoundEvent getAmbientSound() { return SoundEvents.ENTITY_GENERIC_AMBIENT; }
    for method, slot in JAVA_SOUND_METHOD_MAP.items():
        pat = rf'{method}\s*\([^)]*\)\s*\{{[^}}]*?(?:return\s+)?(?:SoundEvents\.|ModSounds\.|Sounds\.)([A-Z0-9_]+)'
        m = re.search(pat, java_code, re.DOTALL)
        if m and slot not in sounds:
            java_const = m.group(1)
            # Check if it maps to a known generic
            bedrock_slot = JAVA_SOUND_EVENT_MAP.get(java_const)
            if bedrock_slot:
                # Use a mod-specific key like namespace.entity_name.ambient
                sounds[slot] = f"{namespace}.{entity_name}.{slot}"
            else:
                # Use the constant directly as a key
                sounds[slot] = sanitize_sound_key(java_const.lower())

    # ── Pattern 2: return SoundEvent registered with ResourceLocation ──
    # e.g.  return ModSounds.TOWW_AMBIENT.get()  or  return AMBIENT_SOUND
    for method, slot in JAVA_SOUND_METHOD_MAP.items():
        if slot in sounds:
            continue
        pat = rf'{method}\s*\([^)]*\)\s*\{{[^}}]*?return\s+([A-Za-z_][A-Za-z0-9_.]*(?:\.get\(\))?)'
        m = re.search(pat, java_code, re.DOTALL)
        if m:
            ref = m.group(1).rstrip(")").rstrip("(").rstrip(".get")
            ref_lower = sanitize_sound_key(ref.split(".")[-1])
            if len(ref_lower) > 2 and ref_lower not in ("null", "super", "this"):
                sounds[slot] = f"{namespace}.{ref_lower}"

    # ── Pattern 3: playSound(SoundEvents.XXX, ...) calls ──
    # Map known call patterns to slots
    PLAY_SLOT_HINTS = {
        "ambient": ("ambient", "idle", "random"),
        "hurt":    ("hurt", "pain", "damage"),
        "death":   ("death", "die"),
        "attack":  ("attack", "strike", "hit"),
        "step":    ("step", "footstep", "walk"),
    }
    for m in re.finditer(
        r'playSound\s*\([^,)]*,\s*(?:SoundEvents\.|ModSounds\.|Sounds\.)([A-Z0-9_]+)',
        java_code
    ):
        java_const = m.group(1)
        # Try to infer slot from constant name
        for slot, hints in PLAY_SLOT_HINTS.items():
            if slot in sounds:
                continue
            if any(h in java_const.lower() for h in hints):
                sounds[slot] = f"{namespace}.{entity_name}.{slot}"
                break

    # ── Pattern 4: ResourceLocation("namespace", "entity.name.ambient") style ──
    for m in re.finditer(
        r'new\s+ResourceLocation\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
        java_code
    ):
        sound_path = m.group(2).lower()
        for slot in ("ambient", "death", "hurt", "step", "attack", "swim", "splash"):
            if slot in sounds:
                continue
            if slot in sound_path:
                key = sanitize_sound_key(f"{m.group(1)}.{sound_path}")
                sounds[slot] = key
                break

    # ── Pattern 5: String literal sound IDs in registration ──
    # e.g.  SoundEvent.createVariableRangeEvent(new ResourceLocation("toww", "entity.hunting.ambient"))
    for m in re.finditer(
        r'["\']([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,})["\']',
        java_code
    ):
        path = m.group(1)
        # Must look like a sound path: at least 3 segments, contains entity/ambient/hurt/death
        parts = path.split(".")
        if len(parts) < 2:
            continue
        for slot in ("ambient", "death", "hurt", "step", "attack", "swim", "splash"):
            if slot in sounds:
                continue
            if parts[-1] == slot or (len(parts) >= 2 and parts[-2] == slot):
                sounds[slot] = sanitize_sound_key(path)
                break

    return sounds


def apply_entity_sounds(bedrock_entity: dict, sounds: dict, namespace: str,
                        entity_name: str):
    """
    Wire detected sounds into both the BP entity and the RP sounds registries.

    Bedrock sound architecture:
      - RP/sounds.json  maps entity identifier -> { "events": { slot: "event_id" } }
        This tells the engine which sound_definition event to play for each slot.
      - RP/sounds/sound_definitions.json  maps event_id -> { "sounds": [file paths] }
        This tells the engine which .ogg files to actually play.
      - BP entity gets minecraft:ambient_sound_interval for the ambient slot only.
        All other slots (hurt/death/step/attack/swim/splash) are driven purely by
        the RP sounds.json entry — the BP entity needs NO sound components for them.

    The correct sounds.json format (RP root) is:
      {
        "entity.namespace:entity_name": {
          "events": { "ambient": "mod.entity.name.ambient", "hurt": "...", ... },
          "pitch": [0.8, 1.2],
          "volume": 1.0
        }
      }
    """
    if not sounds:
        return

    components = bedrock_entity["minecraft:entity"]["components"]
    entity_id = bedrock_entity["minecraft:entity"]["description"]["identifier"]  # "ns:name"

    # ── Ambient interval component (BP only) ──────────────────────────────
    # This drives the timing of ambient calls; the actual sound is looked up
    # via sounds.json at runtime.
    if "ambient" in sounds:
        components["minecraft:ambient_sound_interval"] = {
            "value": 8.0,
            "range": 4.0,
            "event_name": sounds["ambient"]
        }

    # ── Queue entity sound entry for RP/sounds.json ───────────────────────
    # Slot -> Bedrock event key mapping (these are the keys Bedrock recognises
    # inside the "events" block of sounds.json).
    SLOT_TO_BEDROCK_EVENT = {
        "ambient": "ambient",
        "hurt":    "hurt",
        "death":   "death",
        "step":    "step",
        "attack":  "attack",
        "swim":    "swim",
        "splash":  "splash",
    }
    events_block = {}
    for slot, event_key in SLOT_TO_BEDROCK_EVENT.items():
        if slot in sounds:
            events_block[event_key] = sounds[slot]

    if events_block:
        # Store in global registry; written out by generate_sounds_registry()
        _ENTITY_SOUND_EVENTS[entity_id] = {
            "events": events_block,
            "pitch": [0.8, 1.2],
            "volume": 1.0
        }

    # ── Ensure sound_definitions stubs for every event we reference ───────
    for slot, sound_key in sounds.items():
        if sound_key not in COLLECTED_SOUND_DEFS:
            # Plausible file path: sound/<sanitized_event_key> — matches what
            # copy_assets_from_jar deposits .ogg files as.
            file_stem = sound_key.replace(".", "_")
            file_path = f"sound/{file_stem}"
            COLLECTED_SOUND_DEFS[sound_key] = {
                "sounds": [{"name": file_path}],
                "__stub__": True
            }
            print(f"  [sounds] Stub entry created: {sound_key} -> {file_path}")

# =========================================================
# ENTITY EQUIPMENT EXTRACTION
# =========================================================
JAVA_SLOT_TO_BEDROCK = {
    "HEAD": "slot.armor.head",
    "CHEST": "slot.armor.chest",
    "LEGS": "slot.armor.legs",
    "FEET": "slot.armor.feet",
    "MAINHAND": "slot.weapon.mainhand",
    "OFFHAND": "slot.weapon.offhand",
}

def extract_equipment_from_java(java_code: str, namespace: str) -> Optional[dict]:
    """Extract default equipment (armor, weapons) from Java entity code."""
    equipment = {}
    # populateDefaultEquipmentSlots / setItemSlot patterns
    for m in re.finditer(
        r'(?:setItemSlot|setEquipment|set)\s*\(\s*EquipmentSlot\.([A-Z]+)\s*,\s*new\s+ItemStack\s*\(\s*(?:Items\.)?([A-Za-z_]+)',
        java_code):
        slot = JAVA_SLOT_TO_BEDROCK.get(m.group(1))
        item = sanitize_identifier(m.group(2).lower())
        if slot:
            if not item.startswith("minecraft:"):
                item = f"minecraft:{item}"
            equipment[slot] = {"item": item, "drop_chance": 0.085}
    if not equipment:
        return None
    return {"table": f"loot_tables/equipment/{namespace}_equipment.json", "slot_drop_chance": list(equipment.values())}


# =========================================================
# ENTITY EVENTS + COMPONENT GROUPS
# =========================================================
def generate_entity_events(bedrock_entity: dict, ai_goals: list, java_code: str,
                           namespace: str, entity_id: str, attributes: dict):
    """
    Build component_groups and events for common entity state transitions:
    taming, anger, death loot, on_hurt effects, equipment.
    Modifies bedrock_entity in-place.
    """
    components = bedrock_entity["minecraft:entity"]["components"]
    events = bedrock_entity["minecraft:entity"]["events"]
    component_groups = {}
    ns_prefix = entity_id.split(":")[0] if ":" in entity_id else namespace

    # ── Taming ──
    taming_goals = ("SitWhenOrderedToGoal", "FollowOwnerGoal", "OwnerHurtByTargetGoal", "OwnerHurtTargetGoal")
    if any(g in ai_goals for g in taming_goals):
        component_groups[f"{ns_prefix}:tamed"] = {
            "minecraft:is_tamed": {},
            "minecraft:behavior.follow_owner": {
                "priority": 7,
                "speed_multiplier": 1.2,
                "start_distance": 10.0,
                "stop_distance": 2.0
            }
        }
        component_groups[f"{ns_prefix}:wild"] = {
            "minecraft:behavior.nearest_attackable_target": components.get(
                "minecraft:behavior.nearest_attackable_target",
                {"priority": 1, "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": 16}]}
            )
        }
        events["minecraft:on_tame"] = {
            "add": {"component_groups": [f"{ns_prefix}:tamed"]},
            "remove": {"component_groups": [f"{ns_prefix}:wild"]}
        }
        events["minecraft:on_untame"] = {
            "add": {"component_groups": [f"{ns_prefix}:wild"]},
            "remove": {"component_groups": [f"{ns_prefix}:tamed"]}
        }

    # ── Anger (ResetAngerGoal / neutral mobs) ──
    if "ResetAngerGoal" in ai_goals or "HurtByTargetGoal" in ai_goals:
        component_groups[f"{ns_prefix}:angry"] = {
            "minecraft:behavior.nearest_attackable_target": {
                "priority": 1,
                "entity_types": [{"filters": {"test": "is_family", "subject": "other", "value": "player"}, "max_dist": int(attributes.get("follow_range", 16))}],
                "must_see": False,
                "reselect_targets": True
            }
        }
        component_groups[f"{ns_prefix}:calm"] = {
            "minecraft:behavior.random_stroll": {"priority": 8, "speed_multiplier": attributes.get("movement_speed", 0.3)}
        }
        events["minecraft:on_anger"] = {
            "add": {"component_groups": [f"{ns_prefix}:angry"]},
            "remove": {"component_groups": [f"{ns_prefix}:calm"]}
        }
        events["minecraft:on_calm"] = {
            "add": {"component_groups": [f"{ns_prefix}:calm"]},
            "remove": {"component_groups": [f"{ns_prefix}:angry"]}
        }

    # ── Death ──
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    loot_path = f"loot_tables/entities/{safe_name}.json"
    if os.path.exists(os.path.join(BP_FOLDER, loot_path)):
        components["minecraft:loot"] = {"table": loot_path}
    component_groups[f"{ns_prefix}:dead"] = {"minecraft:despawn": {}}
    events["minecraft:on_death"] = {
        "add": {"component_groups": [f"{ns_prefix}:dead"]}
    }

    # ── On hurt effects ──
    mob_effects = extract_mob_effects_from_java(java_code)
    if mob_effects:
        component_groups[f"{ns_prefix}:hurt_effects"] = {
            "minecraft:mob_effect": {"effect": mob_effects[0]["effect"],
                                     "duration": mob_effects[0]["duration"],
                                     "amplifier": mob_effects[0]["amplifier"]}
        }
        events["minecraft:on_hurt"] = {
            "add": {"component_groups": [f"{ns_prefix}:hurt_effects"]}
        }
        # Also add as direct component if entity applies effect on attack
        if re.search(r'addEffect|hurt\(.+MobEffects', java_code, re.I):
            components["minecraft:attack_effect"] = {
                "effect": mob_effects[0]["effect"],
                "duration": mob_effects[0]["duration"],
                "amplifier": mob_effects[0]["amplifier"]
            }

    # ── Sounds ──
    entity_name_short = entity_id.split(":")[-1] if ":" in entity_id else entity_id
    detected_sounds = extract_entity_sounds_from_java(java_code, entity_name_short, namespace)
    apply_entity_sounds(bedrock_entity, detected_sounds, namespace, entity_name_short)

    # ── Equipment ──
    equip = extract_equipment_from_java(java_code, namespace)
    if equip:
        components["minecraft:equipment"] = equip

    # ── Knockback resistance ──
    kr = attributes.get("knockback_resistance", 0.0)
    if kr > 0:
        components["minecraft:knockback_resistance"] = {"value": min(1.0, kr)}

    # ── Apply component groups ──
    if component_groups:
        bedrock_entity["minecraft:entity"]["component_groups"] = component_groups


# =========================================================
# SPAWN RULES
# =========================================================
JAVA_BIOME_TO_BEDROCK = {
    "plains": "plains", "desert": "desert", "forest": "forest",
    "taiga": "taiga", "swamp": "swamp", "jungle": "jungle",
    "savanna": "savanna", "badlands": "mesa", "snowy": "frozen",
    "mountains": "extreme_hills", "birch_forest": "birch",
    "dark_forest": "roofed_forest", "mushroom": "mushroom_island",
    "beach": "beach", "ocean": "ocean", "deep_ocean": "deep_ocean",
    "river": "river", "nether": "nether", "end": "the_end",
    "basalt_deltas": "basalt_deltas", "crimson_forest": "crimson_forest",
    "warped_forest": "warped_forest", "soul_sand_valley": "soulsand_valley",
    "meadow": "meadow", "grove": "grove", "snowy_slopes": "snowy_slopes",
    "jagged_peaks": "jagged_peaks", "frozen_peaks": "frozen_peaks",
    "stony_peaks": "stony_peaks", "lush_caves": "lush_caves",
    "dripstone_caves": "dripstone_caves", "deep_dark": "deep_dark",
    "mangrove_swamp": "mangrove_swamp", "cherry_grove": "cherry_grove",
    "overworld": "overworld", "underground": "underground",
}

def extract_spawn_data_from_java(java_code: str) -> dict:
    """Extract spawn biome, light level, weight, group size from Java entity code."""
    data = {
        "biomes": [],
        "min_light": 0,
        "max_light": 15,
        "min_count": 1,
        "max_count": 4,
        "weight": 10,
        "surface": True,
        "underground": False,
    }
    # Biome tags / SpawnPlacement biome categories
    biome_matches = re.findall(
        r'(?:BiomeDictionary|BiomeCategory|Tags\.Biomes|BIOMES?)[\.\s]+([A-Z_a-z]+)',
        java_code)
    biome_matches += re.findall(r'BiomeTags\.(?:IS_)?([A-Z_]+)', java_code)
    biome_matches += re.findall(r'TagKey[^"]*["\']([a-z_:]+)["\']', java_code)
    for b in biome_matches:
        bl = b.lower()
        for k, v in JAVA_BIOME_TO_BEDROCK.items():
            if k in bl or bl in k:
                if v not in data["biomes"]:
                    data["biomes"].append(v)
    if not data["biomes"]:
        if re.search(r'NETHER|nether', java_code, re.I): data["biomes"] = ["nether"]
        elif re.search(r'THE_END|the_end', java_code, re.I): data["biomes"] = ["the_end"]
        else: data["biomes"] = ["overworld"]
    if re.search(r'MobCategory\.NETHER|DimensionType\.NETHER', java_code): data["biomes"] = ["nether"]
    if re.search(r'MobCategory\.END|DimensionType\.END', java_code): data["biomes"] = ["the_end"]
    # Spawn weight
    for wpat in [r'SpawnEntry[^(]*\(\s*(\d+)', r'weight\s*[=:]\s*(\d+)', r'\.weight\s*\(\s*(\d+)\s*\)']:
        m = re.search(wpat, java_code, re.I)
        if m:
            data["weight"] = int(m.group(1)); break
    # Group size
    m = re.search(r'SpawnEntry[^(]*\([^,]+,\s*(\d+)\s*,\s*(\d+)', java_code)
    if m:
        data["min_count"] = int(m.group(1))
        data["max_count"] = int(m.group(2))
    # Light levels
    m = re.search(r'(?:light|lightLevel|maxLight)\s*[=<>]+\s*(\d+)', java_code, re.I)
    if m:
        data["max_light"] = int(m.group(1))
    # Underground / nether / surface hints
    if re.search(r'IN_WATER|water', java_code, re.I):
        data["surface"] = False
    if re.search(r'UNDERGROUND|underground|cave|Cave', java_code):
        data["underground"] = True
        data["surface"] = False
    return data

def generate_spawn_rules(entity_id: str, java_code: str, namespace: str):
    """Write bp/spawn_rules/<entity>.json for a Bedrock entity."""
    spawn_data = extract_spawn_data_from_java(java_code)
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    out_path = os.path.join(BP_FOLDER, "spawn_rules", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    conditions = []
    for biome in spawn_data["biomes"]:
        condition = {
            "minecraft:spawns_on_surface": {} if spawn_data["surface"] else None,
            "minecraft:spawns_underground": {} if spawn_data["underground"] else None,
            "minecraft:brightness_filter": {
                "min": spawn_data["min_light"],
                "max": spawn_data["max_light"],
                "adjust_for_weather": False
            },
            "minecraft:biome_filter": {"test": "has_biome_tag", "operator": "==", "value": biome},
            "minecraft:herd": {
                "min_size": spawn_data["min_count"],
                "max_size": spawn_data["max_count"]
            },
            "minecraft:weight": {"default": spawn_data["weight"]}
        }
        # Remove None values
        condition = {k: v for k, v in condition.items() if v is not None}
        conditions.append(condition)

    doc = {
        "format_version": "1.12.0",
        "minecraft:spawn_rules": {
            "description": {"identifier": entity_id, "population_control": "monster"},
            "conditions": conditions
        }
    }
    safe_write_json(out_path, doc)
    print(f"[spawn_rules] Wrote {out_path}")


# =========================================================
# LOOT TABLES
# =========================================================
JAVA_LOOT_ITEM_MAP = {
    "minecraft:bone": "minecraft:bone",
    "minecraft:rotten_flesh": "minecraft:rotten_flesh",
    "minecraft:string": "minecraft:string",
    "minecraft:arrow": "minecraft:arrow",
    "minecraft:blaze_rod": "minecraft:blaze_rod",
    "minecraft:gunpowder": "minecraft:gunpowder",
    "minecraft:ender_pearl": "minecraft:ender_pearl",
    "minecraft:leather": "minecraft:leather",
    "minecraft:feather": "minecraft:feather",
    "minecraft:experience_bottle": "minecraft:experience_bottle",
    "minecraft:coal": "minecraft:coal",
    "minecraft:iron_ingot": "minecraft:iron_ingot",
    "minecraft:gold_ingot": "minecraft:gold_ingot",
    "minecraft:diamond": "minecraft:diamond",
    "minecraft:emerald": "minecraft:emerald",
    "minecraft:beef": "minecraft:beef",
    "minecraft:cooked_beef": "minecraft:cooked_beef",
    "minecraft:porkchop": "minecraft:porkchop",
    "minecraft:cooked_porkchop": "minecraft:cooked_porkchop",
    "minecraft:chicken": "minecraft:chicken",
    "minecraft:cooked_chicken": "minecraft:cooked_chicken",
    "minecraft:mutton": "minecraft:mutton",
    "minecraft:cooked_mutton": "minecraft:cooked_mutton",
}

def convert_java_loot_table(java_loot: dict, namespace: str) -> dict:
    """Convert a Java loot table dict to Bedrock format."""
    pools = []
    for pool in java_loot.get("pools", []):
        rolls = pool.get("rolls", 1)
        if isinstance(rolls, dict):
            roll_val = {"min": rolls.get("min", 1), "max": rolls.get("max", 1)}
        else:
            roll_val = int(rolls)
        entries = []
        for entry in pool.get("entries", []):
            etype = entry.get("type", "")
            if "empty" in etype:
                continue
            if "item" in etype:
                item_name = entry.get("name", "")
                if ":" in item_name:
                    ns, item = item_name.split(":", 1)
                    if ns != "minecraft":
                        item_name = f"{namespace}:{sanitize_identifier(item)}"
                    else:
                        item_name = JAVA_LOOT_ITEM_MAP.get(item_name, item_name)
                bedrock_entry = {
                    "type": "item",
                    "name": item_name,
                    "weight": entry.get("weight", 1)
                }
                # Convert functions (count, enchant, etc.)
                functions = []
                for func in entry.get("functions", []):
                    fname = func.get("function", "")
                    if "count" in fname or "set_count" in fname:
                        count = func.get("count", 1)
                        if isinstance(count, dict):
                            functions.append({
                                "function": "set_count",
                                "count": {"min": count.get("min", 1), "max": count.get("max", 1)}
                            })
                        else:
                            functions.append({"function": "set_count", "count": int(count)})
                    elif "looting" in fname or "enchant_with_levels" in fname:
                        functions.append({
                            "function": "looting_enchant",
                            "count": {"min": 0, "max": 1}
                        })
                if functions:
                    bedrock_entry["functions"] = functions
                entries.append(bedrock_entry)
            elif "loot_table" in etype or "alternatives" in etype:
                # nested table reference - flatten with empty entry
                entries.append({"type": "item", "name": "minecraft:air", "weight": 1})
        if entries:
            pools.append({"rolls": roll_val, "entries": entries})
    return {"pools": pools}

def process_loot_tables_from_jar(jar_path: str, namespace: str):
    """Extract and convert all loot tables from JAR."""
    out_base = os.path.join(BP_FOLDER, "loot_tables", "entities")
    os.makedirs(out_base, exist_ok=True)
    count = 0
    with zipfile.ZipFile(jar_path, "r") as jar:
        for name in jar.namelist():
            lower = name.lower()
            if "loot_table" not in lower and "loot_tables" not in lower:
                continue
            if not lower.endswith(".json"):
                continue
            try:
                with jar.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                bedrock = convert_java_loot_table(data, namespace)
                if not bedrock.get("pools"):
                    continue
                fname = sanitize_filename_keep_ext(os.path.basename(name))
                out_path = os.path.join(out_base, fname)
                safe_write_json(out_path, bedrock)
                count += 1
            except Exception as e:
                print(f"[loot] Failed to convert {name}: {e}")
    print(f"[loot] Converted {count} loot tables -> {out_base}")


# =========================================================
# TRADING TABLES
# =========================================================
def generate_trading_table(entity_id: str, java_code: str, namespace: str):
    """Generate a stub Bedrock trading table for entities with TradeWithPlayerGoal."""
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    out_path = os.path.join(BP_FOLDER, "trading", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Try to extract trade items from Java code
    trade_items = re.findall(
        r'new\s+MerchantOffer[^;]+new\s+ItemStack\(([^)]+)\)', java_code)

    tiers = []
    if trade_items:
        trades = []
        for item_ref in trade_items[:6]:  # cap at 6 trades
            item_name = sanitize_identifier(item_ref.split(".")[-1].split(",")[0].lower())
            trades.append({
                "wants": [{"item": f"minecraft:emerald", "quantity": 1}],
                "gives": [{"item": f"{namespace}:{item_name}", "quantity": 1}],
                "trader_exp": 1, "max_uses": 12, "reward_exp": True
            })
        tiers.append({"total_exp_required": 0, "groups": [{"num_to_select": len(trades), "trades": trades}]})
    else:
        # Stub tier
        tiers.append({
            "total_exp_required": 0,
            "groups": [{"num_to_select": 1, "trades": [
                {"wants": [{"item": "minecraft:emerald", "quantity": 1}],
                 "gives": [{"item": f"{namespace}:item", "quantity": 1}],
                 "trader_exp": 1, "max_uses": 12, "reward_exp": True}
            ]}]
        })

    doc = {"tiers": tiers}
    safe_write_json(out_path, doc)
    print(f"[trading] Wrote {out_path}")


# =========================================================
# ITEM TAGS
# =========================================================
JAVA_TAG_TO_BEDROCK_GROUP = {
    "forge:ores": "ore",
    "forge:ingots": "ingot",
    "forge:gems": "gem",
    "forge:dusts": "dust",
    "forge:nuggets": "nugget",
    "forge:rods": "stick",
    "forge:plates": "plate",
    "forge:tools": "tool",
    "forge:weapons": "weapon",
    "forge:armor": "armor",
    "forge:food": "food",
    "forge:seeds": "seeds",
    "forge:crops": "crop",
    "forge:bones": "misc",
    "forge:string": "misc",
    "forge:feathers": "misc",
    # NeoForge uses the same tag paths but under the "neoforge" namespace
    "neoforge:ores": "ore",
    "neoforge:ingots": "ingot",
    "neoforge:gems": "gem",
    "neoforge:dusts": "dust",
    "neoforge:nuggets": "nugget",
    "neoforge:rods": "stick",
    "neoforge:plates": "plate",
    "neoforge:tools": "tool",
    "neoforge:weapons": "weapon",
    "neoforge:armor": "armor",
    "neoforge:food": "food",
    "neoforge:seeds": "seeds",
    "neoforge:crops": "crop",
    "neoforge:bones": "misc",
    "neoforge:string": "misc",
    "neoforge:feathers": "misc",
    "minecraft:logs": "log",
    "minecraft:planks": "planks",
    "minecraft:slabs": "slab",
    "minecraft:stairs": "stair",
    "minecraft:doors": "door",
    "minecraft:leaves": "leaves",
    "minecraft:saplings": "sapling",
    "minecraft:flowers": "flower",
    "minecraft:wool": "wool",
    "minecraft:swords": "weapon",
    "minecraft:axes": "tool",
    "minecraft:pickaxes": "tool",
    "minecraft:shovels": "tool",
    "minecraft:hoes": "tool",
    "minecraft:helmets": "armor",
    "minecraft:chestplates": "armor",
    "minecraft:leggings": "armor",
    "minecraft:boots": "armor",
    "minecraft:coals": "misc",
    "minecraft:arrows": "misc",
}

def extract_item_tags_from_jar(jar_path: str, namespace: str):
    """Extract item tags from JAR and write Bedrock item_catalog entries."""
    out_dir = os.path.join(BP_FOLDER, "item_catalog")
    os.makedirs(out_dir, exist_ok=True)
    catalog = {"format_version": "1.21.0", "minecraft:item_catalog": {"description": {"identifier": f"{namespace}:catalog"}, "groups": []}}
    groups: Dict[str, list] = {}

    with zipfile.ZipFile(jar_path, "r") as jar:
        for name in jar.namelist():
            lower = name.lower()
            if "/tags/items/" not in lower or not lower.endswith(".json"):
                continue
            try:
                with jar.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                tag_name = os.path.splitext(os.path.basename(name))[0]
                # find bedrock group
                group = None
                for java_tag, bedrock_group in JAVA_TAG_TO_BEDROCK_GROUP.items():
                    if tag_name in java_tag or java_tag.split(":")[-1] in tag_name:
                        group = bedrock_group
                        break
                if not group:
                    group = sanitize_identifier(tag_name)
                if group not in groups:
                    groups[group] = []
                for value in data.get("values", []):
                    if isinstance(value, str) and ":" in value:
                        ns, item = value.split(":", 1)
                        if ns != "minecraft":
                            item_id = f"{namespace}:{sanitize_identifier(item)}"
                        else:
                            item_id = value
                        if item_id not in groups[group]:
                            groups[group].append(item_id)
            except Exception as e:
                print(f"[tags] Failed to parse {name}: {e}")

    for group_name, items in groups.items():
        if items:
            catalog["minecraft:item_catalog"]["groups"].append({
                "group_name": group_name,
                "items": items
            })

    if catalog["minecraft:item_catalog"]["groups"]:
        out_path = os.path.join(out_dir, f"{namespace}_catalog.json")
        safe_write_json(out_path, catalog)
        print(f"[tags] Wrote item catalog with {len(groups)} groups -> {out_path}")


# =========================================================
# TEXTURE LOOKUP HELPER
# =========================================================
def find_best_texture_match(safe_name: str, subfolder: str) -> str:
    """
    Try to find the best matching texture filename on disk for a given
    class-derived safe_name. Looks in RP_FOLDER/textures/<subfolder>/.
    Strategy:
      1. Exact match (safe_name)
      2. Fuzzy: find the texture whose name has the most characters in common
         with safe_name (using longest common subsequence length as score)
    Returns the stem (no extension) of the best match, or safe_name if nothing found.
    """
    tex_dir = os.path.join(RP_FOLDER, "textures", subfolder)
    if not os.path.isdir(tex_dir):
        return safe_name

    candidates = []
    for fname in os.listdir(tex_dir):
        if fname.lower().endswith(".png"):
            candidates.append(os.path.splitext(fname)[0])

    if not candidates:
        return safe_name

    # Exact match
    if safe_name in candidates:
        return safe_name

    # Try stripping common suffixes from safe_name to get a base
    base = safe_name
    for suffix in ("block", "item", "entity", "mob", "_block", "_item", "_entity", "_mob"):
        if base.endswith(suffix):
            base = base[:-len(suffix)].strip("_")
            break

    if base in candidates:
        return base

    # Score by token overlap (split on underscores)
    name_tokens = set(safe_name.split("_"))
    base_tokens = set(base.split("_"))

    best = safe_name
    best_score = 0
    for c in candidates:
        c_tokens = set(c.split("_"))
        # score = shared tokens between candidate and both safe_name and base
        score = len(c_tokens & name_tokens) + len(c_tokens & base_tokens)
        if score > best_score:
            best_score = score
            best = c

    if best_score > 0:
        return best
    return safe_name


# =========================================================
# BLOCK CONVERSION (Bedrock-aware)
# =========================================================
JAVA_BLOCK_MATERIAL_MAP = {
    "WOOD": "wood", "STONE": "stone", "METAL": "metal", "SAND": "sand",
    "GLASS": "glass", "CLOTH": "wool", "PLANT": "plant", "DIRT": "dirt",
    "GRASS": "dirt", "ICE": "ice", "LEAVES": "leaves", "WEB": "web",
    "SPONGE": "sponge", "WATER": "water", "LAVA": "lava",
    "FIRE": "decoration", "DECORATION": "decoration",
}

def convert_java_block_full(java_code: str, java_path: str, namespace: str):
    """Full block conversion with Bedrock-correct structure."""
    cls = extract_class_name(java_code) or os.path.splitext(os.path.basename(java_path))[0]
    safe_name = sanitize_identifier(cls)
    block_id = f"{namespace}:{safe_name}"

    # Extract material
    mat_match = re.search(r'Material\.([A-Z_]+)', java_code)
    material = JAVA_BLOCK_MATERIAL_MAP.get(mat_match.group(1) if mat_match else "", "stone")

    # Hardness / resistance
    hardness = 2.0
    m = re.search(r'(?:hardness|destroyTime|strength)\s*\(?\s*([0-9.]+)', java_code, re.I)
    if m:
        hardness = float(m.group(1))
    resistance = hardness * 3.0
    m2 = re.search(r'(?:resistance|explosionResistance)\s*\(?\s*([0-9.]+)', java_code, re.I)
    if m2:
        resistance = float(m2.group(1))

    # Light emission
    light_emission = 0
    m3 = re.search(r'(?:lightLevel|lightEmission|light)\s*[=({]+\s*([0-9]+)', java_code, re.I)
    if m3:
        light_emission = min(15, int(m3.group(1)))

    # Friction (slipperiness)
    friction = 0.6
    m4 = re.search(r'(?:slipperiness|friction)\s*[=({]+\s*([0-9.]+)', java_code, re.I)
    if m4:
        friction = float(m4.group(1))

    doc = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:block": {
            "description": {
                "identifier": block_id,
                "menu_category": {"category": "construction"}
            },
            "components": {
                "minecraft:material_instances": {
                    "*": {"texture": find_best_texture_match(safe_name, "blocks"), "render_method": "opaque"}
                },
                "minecraft:destructible_by_mining": {"seconds_to_destroy": hardness},
                "minecraft:destructible_by_explosion": {"explosion_resistance": resistance},
                "minecraft:friction": friction,
                "minecraft:light_emission": light_emission,
                "minecraft:geometry": f"geometry.{safe_name}",
            }
        }
    }

    # Log-type blocks
    if "log" in safe_name or "pillar" in safe_name.lower():
        doc["minecraft:block"]["components"]["minecraft:geometry"] = "geometry.log"

    # Block states from Java BlockStateProperties
    states = {}
    permutations = []
    if re.search(r'BlockStateProperties\.FACING|DirectionProperty', java_code, re.I):
        states["facing"] = ["north", "south", "east", "west", "up", "down"]
        for d in ["north", "south", "east", "west"]:
            permutations.append({
                "condition": f'query.block_property("{namespace}:facing") == "{d}"',
                "components": {"minecraft:transformation": {"rotation": [0, {"north":0,"south":180,"east":90,"west":270}[d], 0]}}
            })
    if re.search(r'BlockStateProperties\.POWERED|BooleanProperty.*power', java_code, re.I):
        states["powered"] = [False, True]
        permutations.append({
            "condition": f'query.block_property("{namespace}:powered") == true',
            "components": {"minecraft:light_emission": min(15, light_emission + 8)}
        })
    if re.search(r'BlockStateProperties\.WATERLOGGED', java_code, re.I):
        states["waterlogged"] = [False, True]
    if re.search(r'BlockStateProperties\.OPEN|BooleanProperty.*open', java_code, re.I):
        states["open"] = [False, True]
    if re.search(r'BlockStateProperties\.LIT|BooleanProperty.*lit', java_code, re.I):
        states["lit"] = [False, True]
        permutations.append({
            "condition": f'query.block_property("{namespace}:lit") == true',
            "components": {"minecraft:light_emission": 15}
        })
    if re.search(r'IntegerProperty.*age|BlockStateProperties\.AGE', java_code, re.I):
        m_age = re.search(r'IntegerProperty\.create\("[^"]+",\s*\d+,\s*(\d+)', java_code)
        max_age = int(m_age.group(1)) if m_age else 7
        states["age"] = list(range(max_age + 1))

    if states:
        ns_states = {f"{namespace}:{k}": v for k, v in states.items()}
        doc["minecraft:block"]["description"]["states"] = ns_states
    if permutations:
        doc["minecraft:block"]["permutations"] = permutations

    out_path = os.path.join(BP_FOLDER, "blocks", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    safe_write_json(out_path, doc)
    print(f"[block] Wrote {out_path}")


# =========================================================
# ITEM CONVERSION (Bedrock-aware)
# =========================================================
def convert_java_item_full(java_code: str, java_path: str, namespace: str):
    """Full item conversion with Bedrock-correct components."""
    cls = extract_class_name(java_code) or os.path.splitext(os.path.basename(java_path))[0]
    safe_name = sanitize_identifier(cls)
    item_id = f"{namespace}:{safe_name}"

    # Max stack size
    max_stack = 64
    m = re.search(r'(?:maxStackSize|stacksTo)\s*\(?\s*(\d+)', java_code, re.I)
    if m:
        max_stack = int(m.group(1))

    # Durability
    durability = 0
    m2 = re.search(r'(?:maxDamage|durability|defaultDurability)\s*\(?\s*(\d+)', java_code, re.I)
    if m2:
        durability = int(m2.group(1))

    components = {
        "minecraft:icon": {"texture": find_best_texture_match(safe_name, "items")},
        "minecraft:max_stack_size": max_stack,
    }

    if durability > 0:
        components["minecraft:durability"] = {"max_durability": durability}

    # Food items
    is_food = bool(re.search(r'FoodProperties|\.food\(|nutrition|saturation|isFood|extends\s+ItemFood|extends\s+BowlFoodItem', java_code, re.I))
    if is_food:
        nutrition = 4
        saturation = 0.3
        m3 = re.search(r'nutrition\s*\(?\s*(\d+)', java_code, re.I)
        if m3:
            nutrition = int(m3.group(1))
        m4 = re.search(r'saturation(?:Modifier)?\s*\(?\s*([0-9.]+)', java_code, re.I)
        if m4:
            saturation = float(m4.group(1))
        components["minecraft:food"] = {
            "nutrition": nutrition,
            "saturation_modifier": saturation,
            "can_always_eat": bool(re.search(r'alwaysEat|canAlwaysEat', java_code, re.I))
        }
        components["minecraft:use_animation"] = "eat"
        components["minecraft:use_duration"] = 32

    # Armor
    armor_slot = None
    if re.search(r'ArmorItem|EquipmentSlot\.HEAD', java_code, re.I):
        armor_slot = "slot.armor.head"
    elif re.search(r'EquipmentSlot\.CHEST', java_code, re.I):
        armor_slot = "slot.armor.chest"
    elif re.search(r'EquipmentSlot\.LEGS', java_code, re.I):
        armor_slot = "slot.armor.legs"
    elif re.search(r'EquipmentSlot\.FEET', java_code, re.I):
        armor_slot = "slot.armor.feet"
    if armor_slot:
        components["minecraft:wearable"] = {"protection": 3, "slot": armor_slot}

    # Weapon / sword
    if re.search(r'SwordItem|TieredItem|extends.*Sword', java_code, re.I):
        atk = 4.0
        m5 = re.search(r'attackDamage\s*[=+]+\s*([0-9.]+)', java_code, re.I)
        if m5:
            atk = float(m5.group(1))
        components["minecraft:damage"] = int(atk)
        components["minecraft:hand_equipped"] = True

    doc = {
        "format_version": BP_RP_FORMAT_VERSION,
        "minecraft:item": {
            "description": {
                "identifier": item_id,
                "menu_category": {"category": "items"}
            },
            "components": components
        }
    }
    # Enchantability
    enchant_value = 0
    if re.search(r'EnchantmentCategory|getEnchantmentValue|enchantmentValue|enchantable', java_code, re.I):
        m_ench = re.search(r'(?:enchantmentValue|getEnchantmentValue)\s*\(\s*\)\s*\{\s*return\s*(\d+)', java_code, re.I)
        enchant_value = int(m_ench.group(1)) if m_ench else 10
    if enchant_value > 0:
        # Detect slot: weapon, armor, tool, or all
        ench_slot = "all"
        if re.search(r'SwordItem|AxeItem|weapon', java_code, re.I):
            ench_slot = "weapon"
        elif re.search(r'ArmorItem|BootsItem|HelmItem|armor', java_code, re.I):
            ench_slot = "armor"
        elif re.search(r'PickaxeItem|ShovelItem|HoeItem|tool', java_code, re.I):
            ench_slot = "tool"
        components["minecraft:enchantable"] = {"value": enchant_value, "slot": ench_slot}

    # Glint (enchanted appearance)
    if re.search(r'isFoil|hasGlint|isEnchanted', java_code, re.I):
        components["minecraft:glint"] = True

    out_path = os.path.join(BP_FOLDER, "items", f"{safe_name}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    safe_write_json(out_path, doc)
    print(f"[item] Wrote {out_path}")


# =========================================================
# PARTICLE STUBS
# =========================================================
JAVA_PARTICLE_MAP = {
    "explosion": "minecraft:explosion_particle",
    "flame": "minecraft:basic_flame_particle",
    "smoke": "minecraft:basic_smoke_particle",
    "portal": "minecraft:portal_particle",
    "crit": "minecraft:critical_hit_emitter",
    "enchant": "minecraft:enchanting_table_particle",
    "heart": "minecraft:heart_particle",
    "angry": "minecraft:villager_angry_particle",
    "happy": "minecraft:villager_happy_particle",
    "splash": "minecraft:water_splash_particle",
    "bubble": "minecraft:bubble_particle",
    "redstone": "minecraft:redstone_wire_dust_particle",
    "dust": "minecraft:redstone_wire_dust_particle",
    "block_crack": "minecraft:falling_dust_sand_particle",
    "item_crack": "minecraft:basic_crit_particle",
    "snowball": "minecraft:snowball_particle",
    "totem": "minecraft:totem_particle",
    "soul": "minecraft:soul_particle",
}

def extract_and_generate_particles(java_code: str, entity_id: str, namespace: str):
    """Detect Java particle usage and write stub Bedrock particle JSONs."""
    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    found = set()
    for pattern, bedrock_ref in JAVA_PARTICLE_MAP.items():
        if re.search(pattern, java_code, re.I):
            found.add((pattern, bedrock_ref))
    if not found:
        return
    out_dir = os.path.join(RP_FOLDER, "particles")
    os.makedirs(out_dir, exist_ok=True)
    for java_name, bedrock_ref in found:
        particle_id = f"{namespace}:{safe_name}_{java_name}"
        doc = {
            "format_version": "1.10.0",
            "particle_effect": {
                "description": {
                    "identifier": particle_id,
                    "basic_render_parameters": {
                        "material": "particles_alpha",
                        "texture": "textures/particle/particles"
                    }
                },
                "components": {
                    "minecraft:emitter_rate_instant": {"num_particles": 8},
                    "minecraft:emitter_lifetime_once": {"active_time": 0.5},
                    "minecraft:particle_initial_speed": 1.0,
                    "minecraft:particle_lifetime_expression": {"max_lifetime": 0.5},
                    "minecraft:particle_appearance_billboard": {
                        "size": [0.1, 0.1],
                        "facing_camera_type": "lookat_xyz",
                        "uv": {"texture_width": 128, "texture_height": 128, "uv": [0, 0], "uv_size": [8, 8]}
                    }
                },
                "_note": f"stub converted from Java particle: {java_name} (original ref: {bedrock_ref})"
            }
        }
        out_path = os.path.join(out_dir, f"{safe_name}_{java_name}.json")
        safe_write_json(out_path, doc)
    print(f"[particles] Wrote {len(found)} particle stubs for {entity_id}")


# =========================================================
# LANG FILE CONVERSION
# =========================================================
def convert_lang_files():
    """Convert Java en_us.json / .lang files in rp/lang/ to Bedrock .lang format."""
    lang_dir = os.path.join(RP_FOLDER, "lang")
    if not os.path.isdir(lang_dir):
        return
    for fname in os.listdir(lang_dir):
        fpath = os.path.join(lang_dir, fname)
        if fname.endswith(".json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                lang_name = os.path.splitext(fname)[0]
                # Normalize: en_us -> en_US
                parts = lang_name.split("_")
                if len(parts) == 2:
                    lang_name = f"{parts[0]}_{parts[1].upper()}"
                out_path = os.path.join(lang_dir, f"{lang_name}.lang")
                lines = []
                for k, v in data.items():
                    # Java lang keys use . separators, Bedrock uses . too - just write as-is
                    safe_v = str(v).replace("\n", "\\n")
                    lines.append(f"{k}={safe_v}")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                os.remove(fpath)
                print(f"[lang] Converted {fname} -> {lang_name}.lang ({len(lines)} entries)")
            except Exception as e:
                print(f"[lang] Failed to convert {fname}: {e}")


# =========================================================
# RECIPE CONVERSION
# =========================================================
JAVA_RECIPE_ITEM_MAP = {
    "minecraft:crafting_table": "minecraft:crafting_table",
    "minecraft:furnace": "minecraft:furnace",
    "minecraft:smithing_table": "minecraft:smithing_table",
}

def convert_java_recipe(recipe_data: dict, namespace: str) -> Optional[dict]:
    """Convert a single Java recipe dict to Bedrock format."""
    rtype = recipe_data.get("type", "")
    if "crafting_shaped" in rtype:
        pattern = recipe_data.get("pattern", [])
        key_map = recipe_data.get("key", {})
        result = recipe_data.get("result", {})
        result_item = result.get("item", result) if isinstance(result, dict) else result
        if ":" in str(result_item):
            ns, itm = str(result_item).split(":", 1)
            if ns != "minecraft":
                result_item = f"{namespace}:{sanitize_identifier(itm)}"
        count = result.get("count", 1) if isinstance(result, dict) else 1

        bedrock_key = {}
        for char, ingredient in key_map.items():
            item = ingredient.get("item", "") if isinstance(ingredient, dict) else ingredient
            if isinstance(item, list):
                item = item[0].get("item", "") if item else ""
            bedrock_key[char] = {"item": item}

        return {
            "format_version": "1.21.0",
            "minecraft:recipe_shaped": {
                "description": {"identifier": f"{namespace}:{sanitize_identifier(str(result_item).split(':')[-1])}_shaped"},
                "tags": ["crafting_table"],
                "pattern": pattern,
                "key": bedrock_key,
                "result": {"item": result_item, "count": count}
            }
        }
    elif "crafting_shapeless" in rtype:
        ingredients = recipe_data.get("ingredients", [])
        result = recipe_data.get("result", {})
        result_item = result.get("item", result) if isinstance(result, dict) else result
        if ":" in str(result_item):
            ns, itm = str(result_item).split(":", 1)
            if ns != "minecraft":
                result_item = f"{namespace}:{sanitize_identifier(itm)}"
        count = result.get("count", 1) if isinstance(result, dict) else 1

        bedrock_ingredients = []
        for ing in ingredients:
            item = ing.get("item", "") if isinstance(ing, dict) else ing
            if isinstance(item, list):
                item = item[0].get("item", "") if item else ""
            bedrock_ingredients.append({"item": item})

        return {
            "format_version": "1.21.0",
            "minecraft:recipe_shapeless": {
                "description": {"identifier": f"{namespace}:{sanitize_identifier(str(result_item).split(':')[-1])}_shapeless"},
                "tags": ["crafting_table"],
                "ingredients": bedrock_ingredients,
                "result": {"item": result_item, "count": count}
            }
        }
    elif "smelting" in rtype or "smoking" in rtype or "blasting" in rtype:
        ingredient = recipe_data.get("ingredient", {})
        item = ingredient.get("item", "") if isinstance(ingredient, dict) else ingredient
        result = recipe_data.get("result", "")
        if ":" in str(result):
            ns, itm = str(result).split(":", 1)
            if ns != "minecraft":
                result = f"{namespace}:{sanitize_identifier(itm)}"
        cook_time = recipe_data.get("cookingtime", 200) / 20  # ticks -> seconds
        return {
            "format_version": "1.21.0",
            "minecraft:recipe_furnace": {
                "description": {"identifier": f"{namespace}:{sanitize_identifier(str(result).split(':')[-1])}_furnace"},
                "tags": ["furnace", "smoker", "blast_furnace"],
                "input": {"item": item},
                "output": str(result)
            }
        }
    return None

def process_recipes_from_jar(jar_path: str, namespace: str):
    """Extract and convert all recipes from JAR."""
    out_base = os.path.join(BP_FOLDER, "recipes")
    os.makedirs(out_base, exist_ok=True)
    count = 0
    with zipfile.ZipFile(jar_path, "r") as jar:
        for name in jar.namelist():
            lower = name.lower()
            if "/recipes/" not in lower or not lower.endswith(".json"):
                continue
            try:
                with jar.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                bedrock = convert_java_recipe(data, namespace)
                if not bedrock:
                    continue
                fname = sanitize_filename_keep_ext(os.path.basename(name))
                out_path = os.path.join(out_base, fname)
                safe_write_json(out_path, bedrock)
                count += 1
            except Exception as e:
                print(f"[recipe] Failed to convert {name}: {e}")
    print(f"[recipe] Converted {count} recipes -> {out_base}")


# =========================================================
# ANIMATION CONTROLLER GENERATION
# =========================================================
def _categorise_animations(animations: set) -> dict:
    """Sort a set of animation IDs into semantic buckets."""
    buckets = {
        "idle":    [], "walk":   [], "run":    [], "attack": [],
        "hurt":    [], "death":  [], "sit":    [], "swim":   [],
        "fly":     [], "sleep":  [], "spawn":  [], "other":  [],
    }
    KEYWORDS = {
        "idle":   ("idle", "stand", "pose", "float"),
        "walk":   ("walk",),
        "run":    ("run", "chase", "sprint"),
        "attack": ("attack", "strike", "bite", "swipe", "slam", "lunge", "claw"),
        "hurt":   ("hurt", "hit", "flinch", "pain"),
        "death":  ("death", "die", "dying", "dead"),
        "sit":    ("sit", "sitting", "crouch", "lay"),
        "swim":   ("swim", "swimming"),
        "fly":    ("fly", "flying", "hover", "glide"),
        "sleep":  ("sleep", "sleeping", "rest"),
        "spawn":  ("spawn", "appear", "emerge", "summon"),
    }
    for anim in animations:
        a = anim.lower()
        placed = False
        for bucket, keys in KEYWORDS.items():
            if any(k in a for k in keys):
                buckets[bucket].append(anim)
                placed = True
                break
        if not placed:
            buckets["other"].append(anim)
    return buckets


def generate_animation_controller(entity_id: str, animations: set, namespace: str,
                                   ai_goals: list = None, java_code: str = "") -> Optional[str]:
    """
    Generate a full Bedrock animation controller for an entity.
    Returns the controller ID string so the RP entity JSON can reference it.
    """
    if not animations:
        return None

    safe_name = sanitize_identifier(entity_id.split(":")[-1])
    controller_id = f"controller.animation.{namespace}.{safe_name}"
    buckets = _categorise_animations(animations)
    ai_goals = ai_goals or []

    # Determine which states we actually have content for
    has_walk   = bool(buckets["walk"] or buckets["run"])
    has_attack = bool(buckets["attack"])
    has_hurt   = bool(buckets["hurt"])
    has_death  = bool(buckets["death"])
    has_sit    = bool(buckets["sit"])
    has_swim   = bool(buckets["swim"])
    has_fly    = bool(buckets["fly"])
    has_sleep  = bool(buckets["sleep"])
    has_spawn  = bool(buckets["spawn"])

    # Pick best anim per bucket (first match wins)
    def pick(bucket): return buckets[bucket][0] if buckets[bucket] else None
    idle_anim   = pick("idle")
    walk_anim   = pick("walk") or pick("run")
    run_anim    = pick("run") or walk_anim
    attack_anim = pick("attack")
    hurt_anim   = pick("hurt")
    death_anim  = pick("death")
    sit_anim    = pick("sit")
    swim_anim   = pick("swim")
    fly_anim    = pick("fly")
    sleep_anim  = pick("sleep")
    spawn_anim  = pick("spawn")

    # Fallback: if no idle, use first animation
    if not idle_anim:
        idle_anim = sorted(animations)[0]

    states = {}

    # ── spawn state (plays once then moves to default) ──
    if has_spawn:
        states["spawn"] = {
            "animations": [spawn_anim],
            "transitions": [{"default": f"query.anim_time >= 1.0"}]
        }

    # ── default / idle state ──
    default_transitions = []
    if has_spawn:
        pass  # spawn state is initial, not default
    if has_walk:
        default_transitions.append({"moving": "query.modified_move_speed > 0.1"})
    if has_attack:
        default_transitions.append({"attacking": "query.is_attacking"})
    if has_hurt:
        default_transitions.append({"hurt": "query.is_hurt"})
    if has_death:
        default_transitions.append({"death": "query.health <= 0"})
    if has_sit and "SitWhenOrderedToGoal" in ai_goals:
        default_transitions.append({"sitting": "query.is_sitting"})
    if has_sleep:
        default_transitions.append({"sleeping": "query.is_sleeping"})

    default_state = {"animations": [idle_anim]}
    if default_transitions:
        default_state["transitions"] = default_transitions
    states["default"] = default_state

    # ── moving state ──
    if has_walk:
        moving_anim = run_anim if run_anim else walk_anim
        # blend walk/run based on speed if both exist
        if buckets["walk"] and buckets["run"]:
            moving_anims = [
                {walk_anim: "1.0 - math.min(query.modified_move_speed / 0.3, 1.0)"},
                {run_anim:  "math.min(query.modified_move_speed / 0.3, 1.0)"}
            ]
        else:
            moving_anims = [moving_anim]
        moving_transitions = [{"default": "query.modified_move_speed <= 0.1"}]
        if has_attack:
            moving_transitions.append({"attacking": "query.is_attacking"})
        if has_death:
            moving_transitions.append({"death": "query.health <= 0"})
        states["moving"] = {
            "animations": moving_anims,
            "transitions": moving_transitions
        }

    # ── attacking state ──
    if has_attack:
        attack_transitions = [{"default": "!query.is_attacking"}]
        if has_death:
            attack_transitions.append({"death": "query.health <= 0"})
        states["attacking"] = {
            "animations": [attack_anim],
            "transitions": attack_transitions
        }

    # ── hurt state (quick, then back to default) ──
    if has_hurt:
        states["hurt"] = {
            "animations": [hurt_anim],
            "transitions": [
                {"death": "query.health <= 0"},
                {"default": f"query.anim_time >= 0.3"}
            ]
        }

    # ── death state (terminal — no transitions out) ──
    if has_death:
        states["death"] = {
            "animations": [death_anim],
            "transitions": []
        }

    # ── sitting state ──
    if has_sit:
        states["sitting"] = {
            "animations": [sit_anim],
            "transitions": [{"default": "!query.is_sitting"}]
        }

    # ── swimming state ──
    if has_swim:
        swim_transitions = [{"default": "!query.is_in_water"}]
        if has_attack:
            swim_transitions.insert(0, {"attacking": "query.is_attacking"})
        states["swimming"] = {
            "animations": [swim_anim],
            "transitions": swim_transitions
        }
        # Add swim transition from default and moving
        if "default" in states and "transitions" in states["default"]:
            states["default"]["transitions"].insert(0, {"swimming": "query.is_in_water"})
        if "moving" in states:
            states["moving"]["transitions"].insert(0, {"swimming": "query.is_in_water"})

    # ── flying state ──
    if has_fly:
        states["flying"] = {
            "animations": [fly_anim],
            "transitions": [{"default": "query.is_on_ground"}]
        }
        if "default" in states and "transitions" in states["default"]:
            states["default"]["transitions"].insert(0, {"flying": "!query.is_on_ground"})

    # ── sleeping state ──
    if has_sleep:
        states["sleeping"] = {
            "animations": [sleep_anim],
            "transitions": [{"default": "!query.is_sleeping"}]
        }

    # ── remaining uncategorised animations as passive blend states ──
    for anim in buckets["other"]:
        state_name = sanitize_identifier(anim.split(".")[-1])
        if state_name not in states and state_name != "default":
            # Add as always-blended onto default (ambient animations like tails, ears)
            if "animations" in states.get("default", {}):
                if isinstance(states["default"]["animations"], list):
                    states["default"]["animations"].append(anim)

    initial = "spawn" if has_spawn else "default"

    doc = {
        "format_version": "1.10.0",
        "animation_controllers": {
            controller_id: {
                "initial_state": initial,
                "states": states
            }
        }
    }

    out_dir = os.path.join(RP_FOLDER, "animation_controllers")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{safe_name}.animation_controllers.json")
    safe_write_json(out_path, doc)
    print(f"[anim_ctrl] Wrote {out_path} ({len(states)} states)")
    return controller_id

# =========================================================
# RP ENTITY ANIMATION WIRING
# =========================================================
def patch_rp_entity_with_controller(entity_basename: str, animations: set,
                                     controller_id: Optional[str], namespace: str):
    """
    After RP entity JSON is written, re-open it and wire in:
    - All animation keys under description.animations (shortname -> full_id)
    - The animation controller mapped as a shortname in description.animations
    - description.animation_controllers as a list of shortname strings
    - description.scripts.animate listing what to run each frame

    Bedrock RP entity animation wiring rules:
      - description.animations     { "shortname": "animation.full.id" }
        -- also add the controller here: { "ctrl": "controller.animation.ns.name" }
      - description.animation_controllers  ["ctrl"]   <-- shortnames only!
      - description.scripts.animate  ["ctrl", "idle"]
    """
    rp_path = os.path.join(RP_FOLDER, "entity", f"{entity_basename}.entity.json")
    if not os.path.exists(rp_path):
        return
    try:
        with open(rp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return

    desc = data.get("minecraft:client_entity", {}).get("description", {})
    if not desc:
        return

    buckets = _categorise_animations(animations)

    # Build shortname -> full_animation_id map
    anim_map: Dict[str, str] = {}

    def add_anim(key: str, anim_id: str):
        if anim_id and anim_id not in anim_map.values():
            anim_map[key] = anim_id

    for b_name in ("idle", "walk", "run", "attack", "hurt", "death",
                   "sit", "swim", "fly", "sleep", "spawn"):
        if buckets[b_name]:
            add_anim(b_name, buckets[b_name][0])
    for i, anim in enumerate(buckets["other"]):
        add_anim(f"anim_{i}", anim)

    if anim_map:
        desc["animations"] = anim_map

    animate_list = []

    if controller_id:
        # Add controller to the animations map with a shortname so the engine can resolve it
        ctrl_short = "ctrl"
        if "animations" not in desc:
            desc["animations"] = {}
        desc["animations"][ctrl_short] = controller_id

        # animation_controllers must be a list of SHORTNAMES from desc.animations
        desc["animation_controllers"] = [ctrl_short]

        # scripts.animate: controller drives state; optionally layer idle on top
        animate_list = [ctrl_short]
        if "idle" in anim_map:
            animate_list.append({"idle": "query.is_alive"})
        desc["scripts"] = {"animate": animate_list}

    elif anim_map:
        # No controller — animate everything that loops passively
        passive = []
        for short, full_id in anim_map.items():
            loop_names = ("idle", "walk", "run", "swim", "fly")
            if any(n in short for n in loop_names):
                passive.append({short: "query.is_alive"})
            else:
                passive.append(short)
        desc["scripts"] = {"animate": passive or list(anim_map.keys())}

    try:
        with open(rp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[anim_wire] Patched {os.path.basename(rp_path)}: "
              f"{len(anim_map)} anim(s)"
              f"{', controller wired as ' + repr('ctrl') if controller_id else ''}")
    except Exception as e:
        print(f"[anim_wire] Failed to patch {rp_path}: {e}")


# =========================================================
# POST-CONVERSION VALIDATION PASS
# =========================================================
def run_validation_pass() -> list:
    """
    Check that all referenced textures, geometries, and animations
    actually exist on disk. Returns list of warning strings.
    """
    warnings = []

    # Collect all texture files on disk
    tex_dir = os.path.join(RP_FOLDER, "textures")
    tex_on_disk = set()
    if os.path.isdir(tex_dir):
        for root, _, files in os.walk(tex_dir):
            for f in files:
                if f.lower().endswith(".png"):
                    rel = os.path.relpath(os.path.join(root, f), RP_FOLDER).replace("\\", "/")
                    tex_on_disk.add(rel)
                    tex_on_disk.add(os.path.splitext(rel)[0])

    # Collect all geometry files on disk
    geo_dir = os.path.join(RP_FOLDER, "geometry")
    geo_on_disk = set()
    if os.path.isdir(geo_dir):
        for f in os.listdir(geo_dir):
            geo_on_disk.add(os.path.splitext(f)[0].lower())

    # Collect all animation files on disk
    anim_dir = os.path.join(RP_FOLDER, "animations")
    anim_on_disk = set()
    if os.path.isdir(anim_dir):
        for f in os.listdir(anim_dir):
            anim_on_disk.add(os.path.splitext(f)[0].lower())

    # Check each RP entity JSON
    entity_dir = os.path.join(RP_FOLDER, "entity")
    if os.path.isdir(entity_dir):
        for fname in os.listdir(entity_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(entity_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                desc = data.get("minecraft:client_entity", {}).get("description", {})

                # Check textures
                for tex_key, tex_path in desc.get("textures", {}).items():
                    full = tex_path if tex_path.startswith("textures/") else f"textures/{tex_path}"
                    if full not in tex_on_disk and tex_path not in tex_on_disk:
                        warnings.append(f"[WARN] Missing texture '{tex_path}' referenced in {fname}")

                # Check geometry
                for geo_key, geo_id in desc.get("geometry", {}).items():
                    # Build a normalised version of the full geometry tail for matching.
                    # geo_id is like "geometry.mymod.myentity" — strip the "geometry." prefix
                    # and check whether any on-disk geo file contains this identifier.
                    if geo_id.startswith("geometry."):
                        geo_tail = sanitize_identifier(geo_id[len("geometry."):])
                    else:
                        geo_tail = sanitize_identifier(geo_id)
                    # Check against full tail and also just the last segment (entity name)
                    geo_last = geo_tail.split(".")[-1] if "." in geo_tail else geo_tail
                    if (geo_tail not in geo_on_disk and geo_last not in geo_on_disk):
                        warnings.append(f"[WARN] Geometry '{geo_id}' referenced in {fname} - no matching .geo.json found")

                # Check animations
                for anim_key, anim_id in desc.get("animations", {}).items():
                    anim_base = sanitize_identifier(anim_id.split(".")[-2]) if "." in anim_id else anim_id
                    # soft check - animation could be in any file
                    # just warn if no animation files at all
                    if not anim_on_disk:
                        warnings.append(f"[WARN] Animation '{anim_id}' referenced in {fname} but no animation files found")
                        break

            except Exception as e:
                warnings.append(f"[WARN] Could not parse {fname}: {e}")

    # Check BP entities reference existing loot tables
    bp_entity_dir = os.path.join(BP_FOLDER, "entities")
    if os.path.isdir(bp_entity_dir):
        for fname in os.listdir(bp_entity_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(bp_entity_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                comps = data.get("minecraft:entity", {}).get("components", {})
                loot = comps.get("minecraft:loot", {}).get("table", "")
                if loot:
                    loot_full = os.path.join(BP_FOLDER, loot)
                    if not os.path.exists(loot_full):
                        warnings.append(f"[WARN] Loot table '{loot}' referenced in {fname} does not exist")
            except Exception:
                pass

    return warnings



# =========================================================
# CROSS-FILE REGISTRY PRE-SCAN
# =========================================================

ENTITY_REGISTRY: Dict[str, str] = {}
ATTRS_REGISTRY:  Dict[str, dict] = {}
SOUND_CONST_MAP: Dict[str, str] = {}


def detect_mod_id(java_files: dict) -> str:
    """
    Detect the mod ID from Java source files or manifest files.
    Supports Forge (mods.toml), NeoForge (neoforge.mods.toml), and Fabric (fabric.mod.json).
    Uses javalang to read @Mod annotation value; falls back to regex.
    """
    for path, code in java_files.items():
        ast = JavaAST(code)
        ast._parse()
        if ast._tree is not None:
            # @Mod("modid") — used by both Forge and NeoForge
            val = ast.annotation_value('Mod')
            if val and re.match(r'^[a-z0-9_-]+$', val):
                return sanitize_identifier(val)
            # MOD_ID / MODID field string literals (common NeoForge/Forge pattern)
            vals = ast.field_string_values({'MOD_ID', 'MODID', 'MOD_ID_STR', 'ID'})
            for _, v in vals.items():
                if v and re.match(r'^[a-z0-9_-]+$', v):
                    return sanitize_identifier(v)
        else:
            # regex fallback
            m = re.search(r'@Mod\s*\(\s*["\'\']([a-z0-9_-]+)["\'\']', code)
            if m:
                return sanitize_identifier(m.group(1))
            # NeoForge often stores the ID as: public static final String MOD_ID = "mymod";
            m = re.search(r'(?:MOD_ID|MODID|MOD_ID_STR|ID)\s*=\s*["\']([a-z0-9_-]+)["\']', code)
            if m:
                return sanitize_identifier(m.group(1))

    # Check manifest files (not Java, keep regex)
    for root, _, files in os.walk("."):
        for f in files:
            # NeoForge: META-INF/neoforge.mods.toml (takes priority over legacy mods.toml)
            if f == "neoforge.mods.toml":
                try:
                    c = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                    m = re.search(r'modId\s*=\s*["\']([a-z0-9_-]+)["\']', c)
                    if m:
                        print(f"[detect_mod_id] Found NeoForge mod ID in {f}: {m.group(1)!r}")
                        return sanitize_identifier(m.group(1))
                except Exception:
                    pass
            # Forge legacy: META-INF/mods.toml
            if f == "mods.toml":
                try:
                    c = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                    m = re.search(r'modId\s*=\s*["\']([a-z0-9_-]+)["\']', c)
                    if m:
                        return sanitize_identifier(m.group(1))
                except Exception:
                    pass
            # Fabric: fabric.mod.json
            if f == "fabric.mod.json":
                try:
                    data = json.load(open(os.path.join(root, f), encoding="utf-8"))
                    if "id" in data:
                        return sanitize_identifier(data["id"])
                except Exception:
                    pass
    return ""


def build_entity_registry(java_files: dict, namespace: str) -> dict:
    """
    Build a mapping of Java entity class name -> Bedrock entity identifier.
    Supports Forge, NeoForge, and Fabric registration patterns.
    Uses javalang AST to find DeferredRegister, EntityType.Builder, and
    setRegistryName patterns; falls back to regex for unparseable files.

    NeoForge differences vs Forge:
      - Uses net.neoforged.* imports instead of net.minecraftforge.*
      - DeferredRegister.create(Registries.ENTITY_TYPE, MOD_ID) instead of
        DeferredRegister.create(ForgeRegistries.ENTITY_TYPES, MOD_ID)
      - RegistryObject replaced by DeferredHolder<EntityType<?>, EntityType<X>>
      - @EventBusSubscriber(modid=MOD_ID, bus=Bus.MOD) still common
    """
    registry = {}
    for path, code in java_files.items():
        ast = JavaAST(code)
        ast._parse()

        if ast._tree is not None:
            # Scan all .register("name", ...) invocations for EntityType registrations
            for inv in ast.invocations_of('register'):
                args = getattr(inv, 'arguments', []) or []
                if not args:
                    continue
                # First arg should be the registry name string
                if isinstance(args[0], javalang.tree.Literal):
                    reg_name = args[0].value.strip('"').strip("'")
                    if not re.match(r'^[a-z0-9_]+$', reg_name):
                        continue
                    # Look for ClassName::new in remaining args (method references)
                    for arg in args[1:]:
                        if isinstance(arg, javalang.tree.MethodReference):
                            cls_ref = getattr(arg.expression, 'member', None) or getattr(arg.expression, 'name', None)
                            if cls_ref and cls_ref not in ('super', 'this') and len(cls_ref) > 2:
                                registry[cls_ref] = f"{namespace}:{reg_name}"

            # setRegistryName("id") on the class itself (Forge legacy)
            cls_name = ast.primary_class_name()
            if cls_name:
                for inv in ast.invocations_of('setRegistryName'):
                    raw = JavaAST.first_string_arg(inv)
                    if raw:
                        registry[cls_name] = raw if ':' in raw else f"{namespace}:{raw}"
                        break

        # ── regex patterns covering both Forge and NeoForge ──────────────────

        # Forge: RegistryObject<EntityType<MyEntity>> ENTITY = REGISTER.register("name", ...)
        for m in re.finditer(
            r'RegistryObject<EntityType<([A-Za-z0-9_]+)>>\s+\w+\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_]+)["\']',
            code):
            registry[m.group(1)] = f"{namespace}:{m.group(2)}"

        # NeoForge: DeferredHolder<EntityType<?>, EntityType<MyEntity>> or
        #           Supplier<EntityType<MyEntity>> ENTITY = REGISTER.register("name", ...)
        for m in re.finditer(
            r'(?:DeferredHolder|DeferredEntity|Supplier)<[^>]*EntityType<([A-Za-z0-9_]+)>[^>]*>\s+\w+\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_]+)["\']',
            code):
            registry[m.group(1)] = f"{namespace}:{m.group(2)}"

        # NeoForge: var ENTITY = REGISTER.register("name", () -> EntityType.Builder.of(MyEntity::new, ...).build(...))
        for m in re.finditer(
            r'\.register\s*\(\s*["\']([a-z0-9_]+)["\']\s*,[^;]*?([A-Za-z0-9_]+)::new',
            code, re.DOTALL):
            cls = m.group(2)
            if cls not in ("super", "this") and len(cls) > 2:
                registry[cls] = f"{namespace}:{m.group(1)}"

        # EntityType.Builder pattern (both Forge and NeoForge)
        for m in re.finditer(
            r'EntityType\.Builder[^;]*\.of\s*\(\s*([A-Za-z0-9_]+)::new[^;]*\.build\s*\(\s*["\']([a-z0-9_]+)["\']',
            code, re.DOTALL):
            registry[m.group(1)] = f"{namespace}:{m.group(2)}"

        cls_name = extract_class_name(code)
        if cls_name:
            m = re.search(r'setRegistryName\s*\(\s*["\']([a-z0-9_:-]+)["\']', code)
            if m:
                raw = m.group(1)
                registry[cls_name] = raw if ":" in raw else f"{namespace}:{raw}"
    return registry


def build_attributes_registry(java_files: dict) -> dict:
    attrs_reg = {}
    defaults = {"health":20.0,"attack_damage":3.0,"movement_speed":0.3,
                "follow_range":16.0,"knockback_resistance":0.0,"armor":0.0}
    for path, code in java_files.items():
        fname = os.path.basename(path).lower()
        if not (any(k in fname for k in ("attribute","stats","properties")) or
                re.search(r'(?:createAttributes|getDefaultAttributes|createMobAttributes)', code)):
            continue
        cls_name = extract_class_name(code)
        if not cls_name: continue
        attrs = extract_attributes_from_java(code)
        if any(attrs.get(k) != defaults.get(k) for k in defaults):
            attrs_reg[cls_name] = attrs
    return attrs_reg


def build_sound_registry_from_java(java_files: dict, namespace: str) -> dict:
    sound_map = {}
    for path, code in java_files.items():
        fname = os.path.basename(path).lower()
        if not (any(k in fname for k in ("sound","sounds","sfx","audio")) or
                ("SoundEvent" in code and "register" in code)):
            continue
        # Forge: RegistryObject<SoundEvent>
        for m in re.finditer(
            r'(?:RegistryObject<SoundEvent>|SoundEvent)\s+([A-Z_0-9]+)\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_.]+)["\']',
            code):
            sound_map[m.group(1)] = sanitize_sound_key(f"{namespace}.{m.group(2)}")
        # NeoForge: DeferredHolder<SoundEvent, SoundEvent> or Supplier<SoundEvent>
        for m in re.finditer(
            r'(?:DeferredHolder<SoundEvent[^>]*>|Supplier<SoundEvent>)\s+([A-Z_0-9]+)\s*=\s*\w+\.register\s*\(\s*["\']([a-z0-9_.]+)["\']',
            code):
            sound_map[m.group(1)] = sanitize_sound_key(f"{namespace}.{m.group(2)}")
        for m in re.finditer(
            r'([A-Z_0-9]{3,})\s*=\s*(?:SoundEvent\.create[^(]*|Registry\.register[^(]*)\([^)]*["\']([a-z0-9_.:-]+)["\']',
            code):
            sid = m.group(2)
            if ":" in sid: sid = sid.split(":",1)[1]
            sound_map[m.group(1)] = sanitize_sound_key(f"{namespace}.{sid}")
    return sound_map


def run_prescan(java_files: dict, namespace: str) -> str:
    global ENTITY_REGISTRY, ATTRS_REGISTRY, SOUND_CONST_MAP
    detected = detect_mod_id(java_files)
    ns = detected or namespace
    ENTITY_REGISTRY = build_entity_registry(java_files, ns)
    ATTRS_REGISTRY  = build_attributes_registry(java_files)
    SOUND_CONST_MAP = build_sound_registry_from_java(java_files, ns)
    # Build the cross-file goal inheritance map so custom goals can be
    # resolved to their vanilla ancestors during entity conversion.
    build_goal_inheritance_map(java_files)
    print(f"[prescan] mod_id={ns!r} | entities={len(ENTITY_REGISTRY)} | "
          f"attr_classes={len(ATTRS_REGISTRY)} | sounds={len(SOUND_CONST_MAP)}")
    for cls, eid in list(ENTITY_REGISTRY.items())[:6]:
        print(f"  {cls} -> {eid}")
    return ns


# =========================================================
# STRUCTURE CONVERSION
# Java .nbt -> Bedrock .mcstructure + feature_rules + features
# =========================================================

# ── Java block name -> Bedrock block name remapping ──
# Covers the most common blocks. Unknown blocks fall back to air.
JAVA_TO_BEDROCK_BLOCK = {
    # Air / basic
    "minecraft:air": "minecraft:air",
    "minecraft:cave_air": "minecraft:air",
    "minecraft:void_air": "minecraft:air",
    # Stone family
    "minecraft:stone": "minecraft:stone",
    "minecraft:granite": "minecraft:stone",
    "minecraft:polished_granite": "minecraft:stone",
    "minecraft:diorite": "minecraft:stone",
    "minecraft:polished_diorite": "minecraft:stone",
    "minecraft:andesite": "minecraft:stone",
    "minecraft:polished_andesite": "minecraft:stone",
    "minecraft:cobblestone": "minecraft:cobblestone",
    "minecraft:mossy_cobblestone": "minecraft:mossy_cobblestone",
    "minecraft:stone_bricks": "minecraft:stonebrick",
    "minecraft:mossy_stone_bricks": "minecraft:stonebrick",
    "minecraft:cracked_stone_bricks": "minecraft:stonebrick",
    "minecraft:chiseled_stone_bricks": "minecraft:stonebrick",
    "minecraft:infested_stone": "minecraft:stone",
    "minecraft:gravel": "minecraft:gravel",
    "minecraft:sand": "minecraft:sand",
    "minecraft:red_sand": "minecraft:sand",
    "minecraft:sandstone": "minecraft:sandstone",
    "minecraft:smooth_sandstone": "minecraft:sandstone",
    "minecraft:chiseled_sandstone": "minecraft:sandstone",
    "minecraft:red_sandstone": "minecraft:red_sandstone",
    # Dirt / grass
    "minecraft:dirt": "minecraft:dirt",
    "minecraft:coarse_dirt": "minecraft:dirt",
    "minecraft:podzol": "minecraft:podzol",
    "minecraft:grass_block": "minecraft:grass",
    "minecraft:mycelium": "minecraft:mycelium",
    # Wood
    "minecraft:oak_log": "minecraft:log",
    "minecraft:spruce_log": "minecraft:log",
    "minecraft:birch_log": "minecraft:log",
    "minecraft:jungle_log": "minecraft:log",
    "minecraft:acacia_log": "minecraft:log2",
    "minecraft:dark_oak_log": "minecraft:log2",
    "minecraft:oak_planks": "minecraft:planks",
    "minecraft:spruce_planks": "minecraft:planks",
    "minecraft:birch_planks": "minecraft:planks",
    "minecraft:jungle_planks": "minecraft:planks",
    "minecraft:acacia_planks": "minecraft:planks",
    "minecraft:dark_oak_planks": "minecraft:planks",
    "minecraft:oak_leaves": "minecraft:leaves",
    "minecraft:spruce_leaves": "minecraft:leaves",
    "minecraft:birch_leaves": "minecraft:leaves",
    "minecraft:jungle_leaves": "minecraft:leaves",
    "minecraft:acacia_leaves": "minecraft:leaves2",
    "minecraft:dark_oak_leaves": "minecraft:leaves2",
    # Ore
    "minecraft:coal_ore": "minecraft:coal_ore",
    "minecraft:iron_ore": "minecraft:iron_ore",
    "minecraft:gold_ore": "minecraft:gold_ore",
    "minecraft:diamond_ore": "minecraft:diamond_ore",
    "minecraft:emerald_ore": "minecraft:emerald_ore",
    "minecraft:lapis_ore": "minecraft:lapis_ore",
    "minecraft:redstone_ore": "minecraft:redstone_ore",
    "minecraft:nether_quartz_ore": "minecraft:quartz_ore",
    # Bricks
    "minecraft:bricks": "minecraft:brick_block",
    "minecraft:nether_bricks": "minecraft:nether_brick",
    "minecraft:red_nether_bricks": "minecraft:red_nether_brick",
    # Misc
    "minecraft:obsidian": "minecraft:obsidian",
    "minecraft:bedrock": "minecraft:bedrock",
    "minecraft:water": "minecraft:water",
    "minecraft:lava": "minecraft:lava",
    "minecraft:glass": "minecraft:glass",
    "minecraft:glowstone": "minecraft:glowstone",
    "minecraft:netherrack": "minecraft:netherrack",
    "minecraft:soul_sand": "minecraft:soul_sand",
    "minecraft:soul_soil": "minecraft:soul_sand",
    "minecraft:magma_block": "minecraft:magma",
    "minecraft:ice": "minecraft:ice",
    "minecraft:packed_ice": "minecraft:packed_ice",
    "minecraft:snow_block": "minecraft:snow",
    "minecraft:clay": "minecraft:clay",
    "minecraft:terracotta": "minecraft:hardened_clay",
    "minecraft:white_terracotta": "minecraft:stained_hardened_clay",
    "minecraft:chest": "minecraft:chest",
    "minecraft:trapped_chest": "minecraft:trapped_chest",
    "minecraft:crafting_table": "minecraft:crafting_table",
    "minecraft:furnace": "minecraft:furnace",
    "minecraft:bookshelf": "minecraft:bookshelf",
    "minecraft:spawner": "minecraft:mob_spawner",
    "minecraft:tnt": "minecraft:tnt",
    "minecraft:torch": "minecraft:torch",
    "minecraft:wall_torch": "minecraft:torch",
    "minecraft:ladder": "minecraft:ladder",
    "minecraft:iron_bars": "minecraft:iron_bars",
    "minecraft:glass_pane": "minecraft:glass_pane",
    "minecraft:vine": "minecraft:vine",
    "minecraft:cobweb": "minecraft:web",
    "minecraft:hay_block": "minecraft:hay_block",
    "minecraft:sponge": "minecraft:sponge",
    "minecraft:prismarine": "minecraft:prismarine",
    "minecraft:sea_lantern": "minecraft:sea_lantern",
    "minecraft:dark_prismarine": "minecraft:prismarine",
    "minecraft:prismarine_bricks": "minecraft:prismarine",
    "minecraft:purpur_block": "minecraft:purpur_block",
    "minecraft:purpur_pillar": "minecraft:purpur_block",
    "minecraft:end_stone": "minecraft:end_stone",
    "minecraft:end_stone_bricks": "minecraft:end_bricks",
    "minecraft:end_rod": "minecraft:end_rod",
    "minecraft:shulker_box": "minecraft:undyed_shulker_box",
    "minecraft:barrel": "minecraft:barrel",
    "minecraft:campfire": "minecraft:campfire",
    "minecraft:lantern": "minecraft:lantern",
    "minecraft:soul_lantern": "minecraft:soul_lantern",
    "minecraft:beehive": "minecraft:beehive",
    "minecraft:bee_nest": "minecraft:bee_nest",
    "minecraft:honey_block": "minecraft:honey_block",
    "minecraft:honeycomb_block": "minecraft:honeycomb_block",
    "minecraft:target": "minecraft:target",
    "minecraft:ancient_debris": "minecraft:ancient_debris",
    "minecraft:nether_gold_ore": "minecraft:nether_gold_ore",
    "minecraft:crimson_nylium": "minecraft:crimson_nylium",
    "minecraft:warped_nylium": "minecraft:warped_nylium",
    "minecraft:crimson_stem": "minecraft:crimson_stem",
    "minecraft:warped_stem": "minecraft:warped_stem",
    "minecraft:shroomlight": "minecraft:shroomlight",
    "minecraft:blackstone": "minecraft:blackstone",
    "minecraft:gilded_blackstone": "minecraft:gilded_blackstone",
    "minecraft:crying_obsidian": "minecraft:crying_obsidian",
    "minecraft:respawn_anchor": "minecraft:respawn_anchor",
    "minecraft:calcite": "minecraft:calcite",
    "minecraft:tuff": "minecraft:tuff",
    "minecraft:amethyst_block": "minecraft:amethyst_block",
    "minecraft:budding_amethyst": "minecraft:budding_amethyst",
    "minecraft:deepslate": "minecraft:deepslate",
    "minecraft:cobbled_deepslate": "minecraft:cobbled_deepslate",
    "minecraft:deepslate_bricks": "minecraft:deepslate_bricks",
    "minecraft:deepslate_tiles": "minecraft:deepslate_tiles",
    "minecraft:reinforced_deepslate": "minecraft:reinforced_deepslate",
    "minecraft:mud": "minecraft:mud",
    "minecraft:packed_mud": "minecraft:packed_mud",
    "minecraft:mud_bricks": "minecraft:mud_bricks",
    "minecraft:mangrove_log": "minecraft:mangrove_log",
    "minecraft:mangrove_planks": "minecraft:mangrove_planks",
    "minecraft:cherry_log": "minecraft:cherry_log",
    "minecraft:cherry_planks": "minecraft:cherry_planks",
    "minecraft:bamboo_block": "minecraft:bamboo_block",
}

# ── Pure-stdlib NBT reader (big-endian Java format) ──

import struct as _struct
import gzip as _gzip
import io as _io

NBT_END       = 0
NBT_BYTE      = 1
NBT_SHORT     = 2
NBT_INT       = 3
NBT_LONG      = 4
NBT_FLOAT     = 5
NBT_DOUBLE    = 6
NBT_BYTE_ARRAY= 7
NBT_STRING    = 8
NBT_LIST      = 9
NBT_COMPOUND  = 10
NBT_INT_ARRAY = 11
NBT_LONG_ARRAY= 12


def _nbt_read_tag(buf: _io.BytesIO, tag_type: int):
    if tag_type == NBT_BYTE:
        return _struct.unpack(">b", buf.read(1))[0]
    elif tag_type == NBT_SHORT:
        return _struct.unpack(">h", buf.read(2))[0]
    elif tag_type == NBT_INT:
        return _struct.unpack(">i", buf.read(4))[0]
    elif tag_type == NBT_LONG:
        return _struct.unpack(">q", buf.read(8))[0]
    elif tag_type == NBT_FLOAT:
        return _struct.unpack(">f", buf.read(4))[0]
    elif tag_type == NBT_DOUBLE:
        return _struct.unpack(">d", buf.read(8))[0]
    elif tag_type == NBT_BYTE_ARRAY:
        length = _struct.unpack(">i", buf.read(4))[0]
        return list(_struct.unpack(f">{length}b", buf.read(length)))
    elif tag_type == NBT_STRING:
        length = _struct.unpack(">H", buf.read(2))[0]
        return buf.read(length).decode("utf-8", errors="replace")
    elif tag_type == NBT_LIST:
        elem_type = _struct.unpack(">b", buf.read(1))[0]
        length = _struct.unpack(">i", buf.read(4))[0]
        return [_nbt_read_tag(buf, elem_type) for _ in range(length)]
    elif tag_type == NBT_COMPOUND:
        d = {}
        while True:
            t = _struct.unpack(">b", buf.read(1))[0]
            if t == NBT_END:
                break
            name_len = _struct.unpack(">H", buf.read(2))[0]
            name = buf.read(name_len).decode("utf-8", errors="replace")
            d[name] = _nbt_read_tag(buf, t)
        return d
    elif tag_type == NBT_INT_ARRAY:
        length = _struct.unpack(">i", buf.read(4))[0]
        return list(_struct.unpack(f">{length}i", buf.read(length * 4)))
    elif tag_type == NBT_LONG_ARRAY:
        length = _struct.unpack(">i", buf.read(4))[0]
        return list(_struct.unpack(f">{length}q", buf.read(length * 8)))
    else:
        raise ValueError(f"Unknown NBT tag type: {tag_type}")


def read_java_nbt(data: bytes) -> dict:
    """Parse gzipped big-endian Java NBT, return as Python dict."""
    try:
        data = _gzip.decompress(data)
    except Exception:
        pass  # might not be compressed
    buf = _io.BytesIO(data)
    root_type = _struct.unpack(">b", buf.read(1))[0]
    name_len  = _struct.unpack(">H", buf.read(2))[0]
    buf.read(name_len)  # skip root name
    return _nbt_read_tag(buf, root_type)


# ── Pure-stdlib NBT writer (little-endian Bedrock format) ──

def _nbt_write_tag(buf: _io.BytesIO, tag_type: int, value):
    if tag_type == NBT_BYTE:
        buf.write(_struct.pack("<b", int(value)))
    elif tag_type == NBT_SHORT:
        buf.write(_struct.pack("<h", int(value)))
    elif tag_type == NBT_INT:
        buf.write(_struct.pack("<i", int(value)))
    elif tag_type == NBT_LONG:
        buf.write(_struct.pack("<q", int(value)))
    elif tag_type == NBT_FLOAT:
        buf.write(_struct.pack("<f", float(value)))
    elif tag_type == NBT_DOUBLE:
        buf.write(_struct.pack("<d", float(value)))
    elif tag_type == NBT_BYTE_ARRAY:
        buf.write(_struct.pack("<i", len(value)))
        buf.write(_struct.pack(f"<{len(value)}b", *value))
    elif tag_type == NBT_STRING:
        encoded = str(value).encode("utf-8")
        buf.write(_struct.pack("<H", len(encoded)))
        buf.write(encoded)
    elif tag_type == NBT_LIST:
        if not value:
            buf.write(_struct.pack("<b", NBT_END))
            buf.write(_struct.pack("<i", 0))
        else:
            # For list elements, int -> NBT_INT (not INT_ARRAY)
            first = value[0]
            if isinstance(first, bool):   elem_type = NBT_BYTE
            elif isinstance(first, int):  elem_type = NBT_INT
            elif isinstance(first, float):elem_type = NBT_FLOAT
            elif isinstance(first, str):  elem_type = NBT_STRING
            elif isinstance(first, dict): elem_type = NBT_COMPOUND
            elif isinstance(first, list): elem_type = NBT_LIST
            else:                         elem_type = NBT_STRING
            buf.write(_struct.pack("<b", elem_type))
            buf.write(_struct.pack("<i", len(value)))
            for item in value:
                _nbt_write_tag(buf, elem_type, item)
    elif tag_type == NBT_COMPOUND:
        for k, v in value.items():
            t = _infer_nbt_type(v)
            buf.write(_struct.pack("<b", t))
            enc_k = k.encode("utf-8")
            buf.write(_struct.pack("<H", len(enc_k)))
            buf.write(enc_k)
            _nbt_write_tag(buf, t, v)
        buf.write(_struct.pack("<b", NBT_END))
    elif tag_type == NBT_INT_ARRAY:
        buf.write(_struct.pack("<i", len(value)))
        buf.write(_struct.pack(f"<{len(value)}i", *value))
    elif tag_type == NBT_LONG_ARRAY:
        buf.write(_struct.pack("<i", len(value)))
        buf.write(_struct.pack(f"<{len(value)}q", *value))


def _infer_nbt_type(value) -> int:
    if isinstance(value, bool):  return NBT_BYTE
    if isinstance(value, int):   return NBT_INT
    if isinstance(value, float): return NBT_FLOAT
    if isinstance(value, str):   return NBT_STRING
    if isinstance(value, dict):  return NBT_COMPOUND
    if isinstance(value, list):
        if not value:            return NBT_LIST
        first = value[0]
        if isinstance(first, bool):  return NBT_LIST   # bool before int
        if isinstance(first, int):   return NBT_INT_ARRAY
        if isinstance(first, float): return NBT_LIST
        if isinstance(first, dict):  return NBT_LIST
        if isinstance(first, list):  return NBT_LIST
        return NBT_LIST
    return NBT_STRING


def write_bedrock_nbt(root_name: str, compound: dict) -> bytes:
    """Serialise as little-endian Bedrock NBT (not gzipped)."""
    buf = _io.BytesIO()
    buf.write(_struct.pack("<b", NBT_COMPOUND))
    enc = root_name.encode("utf-8")
    buf.write(_struct.pack("<H", len(enc)))
    buf.write(enc)
    _nbt_write_tag(buf, NBT_COMPOUND, compound)
    return buf.getvalue()


# ── Java .nbt -> Bedrock .mcstructure conversion ──

def _remap_block_name(java_name: str, namespace: str) -> str:
    """Map a Java block name to its Bedrock equivalent."""
    if not java_name:
        return "minecraft:air"
    # Mod blocks: keep as-is using target namespace
    if ":" in java_name:
        ns, name = java_name.split(":", 1)
        if ns == "minecraft":
            return JAVA_TO_BEDROCK_BLOCK.get(java_name, "minecraft:air")
        else:
            # Mod block: remap namespace to target
            return f"{namespace}:{sanitize_identifier(name)}"
    return JAVA_TO_BEDROCK_BLOCK.get(f"minecraft:{java_name}", f"minecraft:{java_name}")


def _convert_block_state(java_state: dict, bedrock_name: str) -> dict:
    """
    Convert Java block state properties to Bedrock states.
    Many properties have the same name; others need mapping.
    """
    if not java_state:
        return {}
    bedrock_states = {}
    PROP_MAP = {
        "facing":        "minecraft:facing_direction",
        "half":          None,  # top/bottom slabs handled separately
        "waterlogged":   None,  # drop - Bedrock handles differently
        "powered":       "powered_bit",
        "open":          "open_bit",
        "lit":           "lit",
        "persistent":    "persistent_bit",
        "snowy":         None,  # cosmetic only
        "axis":          "pillar_axis",
        "type":          None,  # slab type
        "shape":         None,  # stairs shape
        "age":           "age",
        "level":         "liquid_depth",
        "layers":        "height",
        "distance":      None,
        "occupied":      None,
        "part":          None,
        "in_wall":       None,
        "attached":      None,
        "disarmed":      None,
        "hinge":         None,
        "delay":         "output_lit_bit",
        "locked":        None,
    }
    for k, v in java_state.items():
        bedrock_key = PROP_MAP.get(k, k)
        if bedrock_key is None:
            continue
        # Convert bool strings
        if v == "true":  v = 1
        elif v == "false": v = 0
        # Convert facing
        elif k == "facing":
            v = {"north": 2, "south": 3, "west": 4, "east": 5,
                 "up": 1, "down": 0}.get(v, 0)
            bedrock_key = "facing_direction"
        elif k == "axis":
            v = {"x": 1, "y": 0, "z": 2}.get(v, 0)
            bedrock_key = "pillar_axis"
        try:
            v = int(v)
        except (ValueError, TypeError):
            pass
        bedrock_states[bedrock_key] = v
    return bedrock_states


def convert_java_nbt_to_mcstructure(nbt_data: dict, namespace: str) -> dict:
    """
    Convert a parsed Java structure NBT dict to a Bedrock mcstructure dict.

    Java .nbt format:
      size:[x,y,z], palette:[{Name, Properties}], blocks:[{state, pos, nbt}], entities:[...]

    Bedrock .mcstructure format:
      format_version:1, size:[x,y,z], structure_world_origin:[0,0,0],
      structure:{block_indices:[[layer0],[layer1]], entities:[], palette:{default:{block_palette:[], block_position_data:{}}}}

    Key differences:
      - Bedrock flat index is YZX order: idx = x + z*sx + y*sx*sz
      - block_indices use -1 for "no block" (air/empty)
      - block states have different property names
      - block_position_data holds block entity NBT keyed by flat index string
    """
    size = nbt_data.get("size", [1, 1, 1])
    sx, sy, sz = int(size[0]), int(size[1]), int(size[2])
    total = sx * sy * sz

    BEDROCK_BLOCK_VERSION = 17959425  # 1.18.10.1

    # ── Build palette: java index -> bedrock palette index ──
    java_palette = nbt_data.get("palette", [])
    bedrock_palette = []
    dedup_map  = {}  # (name, states_tuple) -> bedrock_palette_index
    java_to_bp = {}  # java palette index -> bedrock palette index

    # Always put air at index 0
    air_key = ("minecraft:air", ())
    dedup_map[air_key] = 0
    bedrock_palette.append({"name": "minecraft:air", "states": {}, "version": BEDROCK_BLOCK_VERSION})

    for i, entry in enumerate(java_palette):
        java_name = entry.get("Name", "minecraft:air")
        java_props = entry.get("Properties", {})
        bedrock_name = _remap_block_name(java_name, namespace)
        bedrock_states = _convert_block_state(java_props, bedrock_name)
        key = (bedrock_name, tuple(sorted(bedrock_states.items())))
        if key not in dedup_map:
            dedup_map[key] = len(bedrock_palette)
            bedrock_palette.append({
                "name": bedrock_name,
                "states": bedrock_states,
                "version": BEDROCK_BLOCK_VERSION
            })
        java_to_bp[i] = dedup_map[key]

    # Water palette index (for waterlogged blocks)
    water_key = ("minecraft:water", ())
    if water_key not in dedup_map:
        dedup_map[water_key] = len(bedrock_palette)
        bedrock_palette.append({"name": "minecraft:water", "states": {"liquid_depth": 0}, "version": BEDROCK_BLOCK_VERSION})
    water_idx = dedup_map[water_key]

    # ── Build block index arrays (YZX order) ──
    # Bedrock flat index: x + z*sx + y*sx*sz
    layer0 = [-1] * total
    layer1 = [-1] * total
    block_position_data = {}  # str(flat_idx) -> block entity compound

    for block in nbt_data.get("blocks", []):
        pos = block.get("pos", [0, 0, 0])
        state_idx = int(block.get("state", 0))
        x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
        if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
            continue

        flat_idx = x + z * sx + y * sx * sz  # YZX order
        bedrock_idx = java_to_bp.get(state_idx, 0)
        layer0[flat_idx] = bedrock_idx

        # Waterlogged -> put water in layer 1
        java_entry = java_palette[state_idx] if state_idx < len(java_palette) else {}
        if java_entry.get("Properties", {}).get("waterlogged") == "true":
            layer1[flat_idx] = water_idx

        # Block entity NBT (chests, spawners, signs, etc.)
        block_nbt = block.get("nbt")
        if block_nbt and isinstance(block_nbt, dict):
            converted_be = _convert_block_entity_nbt(block_nbt, namespace)
            if converted_be:
                block_position_data[str(flat_idx)] = {"block_entity_data": converted_be}

    # ── Convert entities ──
    bedrock_entities = []
    for i, ent in enumerate(nbt_data.get("entities", [])):
        try:
            pos = ent.get("pos", [0.0, 0.0, 0.0])
            ent_nbt = ent.get("nbt", {})
            entity_id = ent_nbt.get("id", "")
            if not entity_id:
                continue
            # Remap Java entity id to Bedrock
            if ":" not in entity_id:
                entity_id = f"minecraft:{entity_id.lower()}"
            else:
                ns_e, name_e = entity_id.split(":", 1)
                if ns_e != "minecraft":
                    entity_id = f"{namespace}:{sanitize_identifier(name_e)}"
            bedrock_entities.append({
                "identifier": entity_id,
                "Pos": [float(p) for p in pos],
                "UniqueID": -(i + 1),
                "Tags": [],
            })
        except Exception:
            pass

    return {
        "format_version": 1,
        "size": [sx, sy, sz],
        "structure_world_origin": [0, 0, 0],
        "structure": {
            "block_indices": [layer0, layer1],
            "entities": bedrock_entities,
            "palette": {
                "default": {
                    "block_palette": bedrock_palette,
                    "block_position_data": block_position_data
                }
            }
        }
    }


def _convert_block_entity_nbt(java_nbt: dict, namespace: str) -> Optional[dict]:
    """
    Convert Java block entity NBT to Bedrock format.
    Handles: chests (items), spawners (entity id), signs (text), banners.
    Returns None if nothing useful to convert.
    """
    be_id = java_nbt.get("id", "")
    if not be_id:
        return None

    # Normalise ID
    if ":" in be_id:
        be_id = be_id.split(":", 1)[1]
    be_id = be_id.lower()

    result = {"id": be_id, "isMovable": 1}

    # ── Chest / barrel / shulker box: convert item stacks ──
    if be_id in ("chest", "trapped_chest", "barrel", "shulker_box", "hopper", "dropper", "dispenser"):
        items = java_nbt.get("Items", [])
        bedrock_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id", "minecraft:air")
            if ":" in item_id:
                ns_i, name_i = item_id.split(":", 1)
                if ns_i != "minecraft":
                    item_id = f"{namespace}:{sanitize_identifier(name_i)}"
            bedrock_items.append({
                "Count": item.get("Count", 1),
                "Damage": 0,
                "Name": item_id,
                "Slot": item.get("Slot", 0),
                "WasPickedUp": 0,
            })
        if bedrock_items:
            result["Items"] = bedrock_items

    # ── Mob spawner: convert entity type ──
    elif be_id == "mob_spawner":
        spawn_data = java_nbt.get("SpawnData", {})
        entity_id = spawn_data.get("entity", {}).get("id", "") or java_nbt.get("EntityId", "")
        if not entity_id:
            entity_id = "minecraft:pig"
        if ":" not in entity_id:
            entity_id = f"minecraft:{entity_id.lower()}"
        result["EntityIdentifier"] = entity_id
        result["Delay"] = java_nbt.get("Delay", 20)
        result["MaxNearbyEntities"] = java_nbt.get("MaxNearbyEntities", 6)
        result["MaxSpawnDelay"] = java_nbt.get("MaxSpawnDelay", 800)
        result["MinSpawnDelay"] = java_nbt.get("MinSpawnDelay", 200)
        result["RequiredPlayerRange"] = java_nbt.get("RequiredPlayerRange", 16)
        result["SpawnCount"] = java_nbt.get("SpawnCount", 4)
        result["SpawnRange"] = java_nbt.get("SpawnRange", 4)

    # ── Sign: convert text (JSON -> plain) ──
    elif be_id in ("sign", "hanging_sign"):
        import json as _json
        for side in ("front_text", "back_text", "Text1", "Text2", "Text3", "Text4"):
            val = java_nbt.get(side, "")
            if isinstance(val, dict):
                messages = val.get("messages", [])
                lines = []
                for msg in messages:
                    try:
                        parsed = _json.loads(msg)
                        text = parsed.get("text", "") if isinstance(parsed, dict) else str(parsed)
                    except Exception:
                        text = str(msg).strip('"')
                    lines.append(text)
                result["Text"] = "\n".join(lines)
                break
            elif isinstance(val, str) and val:
                try:
                    parsed = _json.loads(val)
                    result[side] = parsed.get("text", val) if isinstance(parsed, dict) else val
                except Exception:
                    result[side] = val

    # ── Furnace / smoker / blast furnace ──
    elif be_id in ("furnace", "smoker", "blast_furnace"):
        result["BurnTime"] = java_nbt.get("BurnTime", 0)
        result["CookTime"] = java_nbt.get("CookTime", 0)
        result["CookTimeTotal"] = java_nbt.get("CookTimeTotal", 200)

    return result if len(result) > 2 else None


# ── Extract structure metadata from Java worldgen JSONs and Java code ──

def extract_structure_metadata_from_java(java_code: str, namespace: str) -> dict:
    """
    Extract structure placement metadata from a StructureFeature Java file.
    Returns dict with: biomes, step, spacing, separation, salt, start_height
    """
    meta = {
        "biomes": ["overworld"],
        "step": "surface_pass",
        "spacing": 32,
        "separation": 8,
        "salt": 0,
        "start_height": 64,
        "terrain_adaptation": "beard_thin",
    }

    # Biome tags
    biome_matches = re.findall(
        r'(?:BiomeTags|Tags\.Biomes|BiomeDictionary)[^.(]*\.([A-Z_]+)', java_code)
    for b in biome_matches:
        bl = b.lower().replace("is_", "").replace("has_", "")
        for k, v in JAVA_BIOME_TO_BEDROCK.items():
            if k in bl:
                if v not in meta["biomes"]:
                    meta["biomes"].append(v)

    # Spacing / separation / salt from StructureSettings or StructurePlacementData
    m = re.search(r'spacing\s*[=,]\s*(\d+)', java_code)
    if m: meta["spacing"] = int(m.group(1))
    m = re.search(r'separation\s*[=,]\s*(\d+)', java_code)
    if m: meta["separation"] = int(m.group(1))
    m = re.search(r'salt\s*[=,]\s*(\d+)', java_code)
    if m: meta["salt"] = int(m.group(1))

    # Dimension / step hints
    if re.search(r'NETHER|nether', java_code, re.I): meta["biomes"] = ["nether"]; meta["step"] = "surface_pass"
    if re.search(r'THE_END|the_end', java_code, re.I): meta["biomes"] = ["the_end"]
    if re.search(r'GenerationStep\.Decoration\.UNDERGROUND', java_code): meta["step"] = "underground_pass"
    if re.search(r'GenerationStep\.Decoration\.VEGETAL', java_code): meta["step"] = "surface_pass"

    # Start height
    m = re.search(r'startHeight[^;]*?(-?\d+)', java_code)
    if m: meta["start_height"] = int(m.group(1))

    return meta


def generate_feature_json(structure_name: str, namespace: str) -> dict:
    """Generate a Bedrock structure_template_feature JSON."""
    full_id = f"{namespace}:{structure_name}"
    return {
        "format_version": "1.13.0",
        "minecraft:structure_template_feature": {
            "description": {
                "identifier": f"{namespace}:{structure_name}_feature"
            },
            "structure_name": full_id,
            "adjustment_radius": 4,
            "facing_direction": "random",
            "constraints": {
                "unburied": {},
                "block_intersection": {
                    "block_allowlist": [
                        "minecraft:air",
                        "minecraft:grass",
                        "minecraft:dirt",
                        "minecraft:stone"
                    ]
                }
            }
        }
    }


def generate_feature_rule_json(structure_name: str, namespace: str, meta: dict) -> dict:
    """Generate a Bedrock feature_rules JSON for structure placement."""
    biome_filters = []
    for biome in meta.get("biomes", ["overworld"]):
        biome_filters.append({
            "test": "has_biome_tag",
            "operator": "==",
            "value": biome
        })

    # Convert spacing to scatter_chance (rough approximation)
    spacing = meta.get("spacing", 32)
    chance = max(0.01, min(1.0, round(1.0 / max(1, spacing / 8), 3)))

    return {
        "format_version": "1.13.0",
        "minecraft:feature_rules": {
            "description": {
                "identifier": f"{namespace}:{structure_name}_feature_rule",
                "places_feature": f"{namespace}:{structure_name}_feature"
            },
            "conditions": {
                "placement_pass": meta.get("step", "surface_pass"),
                "minecraft:biome_filter": biome_filters if len(biome_filters) > 1 else biome_filters[0] if biome_filters else {"test": "has_biome_tag", "value": "overworld"}
            },
            "distribution": {
                "iterations": 1,
                "scatter_chance": str(chance),
                "x": {"distribution": "uniform", "extent": [0, 16]},
                "y": meta.get("start_height", 64),
                "z": {"distribution": "uniform", "extent": [0, 16]}
            }
        }
    }


def process_structures_from_jar(jar_path: str, namespace: str, java_files: dict = None):
    """
    Main structure processor:
    1. Extract .nbt files from JAR -> convert to .mcstructure
    2. For each structure, generate feature + feature_rule JSONs
    3. Scan Java code for structure metadata to inform placement
    """
    if not jar_path or not os.path.exists(jar_path):
        return

    java_files = java_files or {}
    structures_processed = 0
    features_written = 0

    # Dirs
    mcstructure_dir = os.path.join(BP_FOLDER, "structures")
    features_dir    = os.path.join(BP_FOLDER, "features")
    feat_rules_dir  = os.path.join(BP_FOLDER, "feature_rules")
    os.makedirs(mcstructure_dir, exist_ok=True)
    os.makedirs(features_dir, exist_ok=True)
    os.makedirs(feat_rules_dir, exist_ok=True)

    # Build a map of structure_name -> java metadata from all Java files
    structure_meta_map = {}
    for path, code in java_files.items():
        if re.search(r'extends\s+(?:Structure|StructureFeature|JigsawStructure)', code):
            cls = extract_class_name(code) or os.path.splitext(os.path.basename(path))[0]
            structure_meta_map[cls] = extract_structure_metadata_from_java(code, namespace)

    # Also read worldgen/structure JSON files from JAR
    worldgen_metas = {}
    try:
        with zipfile.ZipFile(jar_path, "r") as jar:
            for file in jar.namelist():
                lower = file.lower()

                # ── .nbt structure files ──
                if lower.endswith(".nbt") and "/structures/" in lower:
                    try:
                        with jar.open(file) as f:
                            nbt_raw = f.read()
                        nbt_data = read_java_nbt(nbt_raw)
                        # Derive structure name from path
                        # e.g. data/toww/structures/campsite/main.nbt -> toww/campsite_main
                        after = lower.split("/structures/", 1)[1]
                        stem = os.path.splitext(after)[0].replace("/", "_").replace("\\", "_")
                        safe_stem = sanitize_identifier(stem)

                        # Convert to mcstructure
                        mcstructure = convert_java_nbt_to_mcstructure(nbt_data, namespace)
                        mcstructure_nbt = write_bedrock_nbt("", mcstructure)
                        out_path = os.path.join(mcstructure_dir, f"{safe_stem}.mcstructure")
                        with open(out_path, "wb") as out_f:
                            out_f.write(mcstructure_nbt)
                        print(f"[structure] Converted {os.path.basename(file)} -> {safe_stem}.mcstructure "
                              f"({mcstructure['size']})")

                        # Generate feature + feature_rule
                        # Try to find matching Java metadata
                        meta = {"biomes": ["overworld"], "step": "surface_pass",
                                "spacing": 32, "separation": 8, "start_height": 64}
                        for cls_name, cls_meta in structure_meta_map.items():
                            if sanitize_identifier(cls_name.lower().replace("structure","")) in safe_stem:
                                meta = cls_meta
                                break

                        feat_json = generate_feature_json(safe_stem, namespace)
                        safe_write_json(os.path.join(features_dir, f"{safe_stem}_feature.json"), feat_json)

                        rule_json = generate_feature_rule_json(safe_stem, namespace, meta)
                        safe_write_json(os.path.join(feat_rules_dir, f"{safe_stem}_feature_rule.json"), rule_json)

                        structures_processed += 1
                        features_written += 1
                    except Exception as e:
                        print(f"[structure] ⚠ Failed to convert {file}: {e}")

                # ── worldgen/structure/*.json ──
                elif "/worldgen/structure/" in lower and lower.endswith(".json"):
                    try:
                        with jar.open(file) as f:
                            wg_data = json.load(f)
                        # Extract biome tag from JSON if present
                        stem = os.path.splitext(os.path.basename(file))[0]
                        safe_stem = sanitize_identifier(stem)
                        biome_tag = wg_data.get("biomes", "")
                        if isinstance(biome_tag, str) and ":" in biome_tag:
                            biome_tag = biome_tag.split(":")[1]
                        worldgen_metas[safe_stem] = {
                            "raw": wg_data,
                            "biome_hint": biome_tag
                        }
                    except Exception:
                        pass

                # ── worldgen/template_pool/*.json ──
                elif "/worldgen/template_pool/" in lower and lower.endswith(".json"):
                    # Write as a reference doc — Jigsaw pools don't directly translate
                    try:
                        with jar.open(file) as f:
                            pool_data = json.load(f)
                        safe_stem = sanitize_identifier(os.path.splitext(os.path.basename(file))[0])
                        ref_path = os.path.join(BP_FOLDER, "structures", f"_pool_{safe_stem}.json")
                        with open(ref_path, "w", encoding="utf-8") as out_f:
                            json.dump({
                                "__note": "Jigsaw template pool - manual conversion required",
                                "__source": file,
                                "data": pool_data
                            }, out_f, indent=2)
                    except Exception:
                        pass

    except Exception as e:
        print(f"[structure] ⚠ JAR read error: {e}")

    print(f"[structure] Processed {structures_processed} structure(s), "
          f"wrote {features_written} feature+rule pair(s)")


# -------------------------
# Logo extraction from JAR
# -------------------------
def extract_logo_from_jar(jar_path: str) -> Optional[str]:
    """
    Extract pack logo/icon from JAR file.
    Searches for common icon file names in the root and META-INF directories.
    Returns the path to the extracted icon file, or None if not found.
    """
    if not jar_path or not os.path.exists(jar_path):
        return None
    
    icon_candidates = [
        "pack.png", "icon.png", "logo.png", "pack_icon.png",
        "META-INF/pack.png", "META-INF/icon.png", "META-INF/logo.png"
    ]
    
    try:
        with zipfile.ZipFile(jar_path, "r") as jar:
            for candidate in icon_candidates:
                try:
                    with jar.open(candidate) as f:
                        icon_data = f.read()
                    # Extract to temporary location
                    temp_dir = ".temp_logo_extract"
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, "pack_icon.png")
                    with open(temp_path, "wb") as out:
                        out.write(icon_data)
                    print(f"[icon] Extracted {candidate} from JAR")
                    return temp_path
                except KeyError:
                    continue
    except Exception as e:
        print(f"[icon] Failed to extract icon from JAR: {e}")
    
    return None


# -------------------------
# Loader / version validation
# -------------------------

# Minimum MC version supported per loader (as tuple for comparison)
LOADER_MIN_VERSIONS: Dict[str, tuple] = {
    "forge":    (1, 3),   # 1.3+  (not recommended below 1.12)
    "neoforge": (1, 20),  # NeoForge only exists from 1.20.1 onward
    "fabric":   None,     # Unsupported - warn and abort
    "quilt":    None,     # Unsupported - warn and abort
}

# NeoForge did not exist before 1.20.1
NEOFORGE_MIN_VERSION = (1, 20, 1)


def detect_mc_version_from_jar(jar_path: str) -> Optional[tuple]:
    """
    Attempt to detect the Minecraft version from a JAR file.
    Checks META-INF/mods.toml, META-INF/neoforge.mods.toml, or version string
    embedded in the JAR filename itself (e.g. mymod-1.20.4-2.0.jar).
    Returns a version tuple like (1, 20, 4) or None if not detected.
    """
    toml_candidates = ["META-INF/neoforge.mods.toml", "META-INF/mods.toml"]
    try:
        with zipfile.ZipFile(jar_path, "r") as jar:
            names_lower = {n.lower(): n for n in jar.namelist()}
            for candidate in toml_candidates:
                real_name = names_lower.get(candidate.lower())
                if not real_name:
                    continue
                try:
                    with jar.open(real_name) as f:
                        content_toml = f.read().decode("utf-8", errors="ignore")
                    for pat in [
                        r'loaderVersion\s*=\s*["\'\']?\[?([0-9]+\.[0-9]+(?:\.[0-9]+)?)',
                        r'(?:dependencies\.minecraft|minecraft\.version)\s*=\s*["\'\']([0-9]+\.[0-9]+(?:\.[0-9]+)?)',
                        r'\[dependencies\.[^\]]+\]\s*[^\[]*?versionRange\s*=\s*["\'\']?\[([0-9]+\.[0-9]+(?:\.[0-9]+)?)',
                    ]:
                        m = re.search(pat, content_toml, re.IGNORECASE)
                        if m:
                            parts = tuple(int(x) for x in m.group(1).split("."))
                            return parts
                except Exception:
                    continue
    except Exception:
        pass

    fname = os.path.basename(jar_path)
    m = re.search(r'[_\-](1\.[0-9]+(?:\.[0-9]+)?)[_\-]', fname)
    if m:
        parts = tuple(int(x) for x in m.group(1).split("."))
        return parts

    return None


def validate_loader_support(loader: str, mc_version: Optional[tuple]) -> bool:
    """
    Validate that the detected loader (and optionally MC version) is supported.
    Prints informative warnings/errors and returns False if the pipeline should abort.
    """
    UNSUPPORTED_LOADERS = {"fabric", "quilt"}

    if loader in UNSUPPORTED_LOADERS:
        print(f"\n\u274c Unsupported mod loader detected: {loader.upper()}")
        print(  "   ModMorpher currently supports Forge and NeoForge (MCreator) mods only.")
        print(  "   Fabric and Quilt mods use a fundamentally different architecture")
        print(  "   and are not yet supported.\n")
        return False

    if loader == "unknown":
        print("\n\u26a0  Could not detect mod loader from JAR.")
        print(  "   Proceeding anyway, but results may be incomplete.")
        return True

    if loader == "neoforge":
        if mc_version is not None and mc_version < NEOFORGE_MIN_VERSION:
            print(f"\n\u274c NeoForge does not exist for Minecraft {'.'.join(str(x) for x in mc_version)}.")
            print(  "   NeoForge was introduced in Minecraft 1.20.1.")
            print(  "   If your mod targets an earlier version, it uses Forge, not NeoForge.")
            return False
        version_str = '.'.join(str(x) for x in mc_version) if mc_version else "unknown"
        print(f"[loader] \u2713 NeoForge mod detected (MC {version_str}) -- full support enabled.")
        if mc_version is None:
            print("   \u26a0  Could not detect MC version from JAR; assuming 1.20.1+.")
        return True

    if loader == "forge":
        if mc_version is not None:
            version_str = '.'.join(str(x) for x in mc_version)
            if mc_version >= (1, 18):
                print(f"[loader] \u2713 Forge mod detected (MC {version_str}) -- best results expected.")
            elif mc_version >= (1, 12):
                print(f"[loader] \u26a0  Forge mod detected (MC {version_str}) -- manual work may be needed.")
            else:
                print(f"[loader] \u26a0  Forge mod detected (MC {version_str}) -- NOT RECOMMENDED. "
                      "Very old versions may produce incomplete output.")
        else:
            print("[loader] \u2713 Forge mod detected (MC version unknown).")
        return True

    print(f"[loader] \u26a0  Unknown loader '{loader}' -- proceeding with best-effort conversion.")
    return True


# -------------------------
# Main pipeline
# -------------------------
def run_pipeline():
    jar_path = find_jar_file(".")
    if jar_path:
        jar_base_raw = os.path.splitext(os.path.basename(jar_path))[0]
        print(f"Found JAR: {jar_path} (using '{jar_base_raw}' as pack name and namespace)")
    else:
        jar_base_raw = os.path.split(os.getcwd())[-1]
        print("❌ No .jar file found. Continuing without JAR asset copying. Using current folder name as pack name/namespace")

    # display name (for manifests) and namespace identifier
    pack_display_name = jar_base_raw
    namespace = sanitize_identifier(jar_base_raw) or "converted"

    ensure_dirs()

    if jar_path:
        jar_loader = detect_loader_from_jar(jar_path)
        mc_version = detect_mc_version_from_jar(jar_path)
        if not validate_loader_support(jar_loader, mc_version):
            print("\nAborting pipeline due to unsupported loader. See above for details.")
            return
        copy_assets_from_jar(jar_path, RP_FOLDER)
        copy_geckolib_animations_from_jar(jar_path, RP_FOLDER)
        logo = extract_logo_from_jar(jar_path)
        if logo:
            try:
                # Place logo -> pack_icon.png into BP and RP using the resizing helper
                dest_bp = os.path.join(BP_FOLDER, "pack_icon.png")
                dest_rp = os.path.join(RP_FOLDER, "pack_icon.png")
                tmp_fixed_dir = os.path.join(".temp_icon_fixed")
                tmp_fixed = os.path.join(tmp_fixed_dir, "pack_icon.png")
                ok = ensure_and_fix_pack_icon(logo, tmp_fixed)
                if ok or os.path.exists(tmp_fixed):
                    os.makedirs(os.path.dirname(dest_bp), exist_ok=True)
                    os.makedirs(os.path.dirname(dest_rp), exist_ok=True)
                    shutil.copy(tmp_fixed, dest_bp)
                    shutil.copy(tmp_fixed, dest_rp)
                    print(f"✓ Extracted, fixed, and copied pack_icon.png to BP and RP.")
                else:
                    # fallback: copy unmodified (warning printed by ensure helper)
                    shutil.copy(logo, dest_bp)
                    shutil.copy(logo, dest_rp)
                    print(f"✓ Copied pack icon without resizing (PIL not available).")
                shutil.rmtree(".temp_logo_extract", ignore_errors=True)
                shutil.rmtree(tmp_fixed_dir, ignore_errors=True)
            except Exception as e:
                print(f"⚠ Failed to copy pack icon: {e}")

    # Normalize existent RP files (geometry/animations) so identifiers are safe and consistent
    normalize_geometry_file_identifiers()
    sanitize_animation_keys_in_files()
    fix_animation_format_versions()

    gecko_maps = build_geckolib_mappings(".")
    geom_file_map, geom_ns_map = load_geometry_identifiers()
    anim_key_map = load_animation_keys()

    stats = {
        "converted_entities_bp": [],
        "converted_entities_rp": [],
        "skipped_files": [],
        "missing_geometry": [],
        "errors": [],
        "converted_items": [],
        "converted_blocks": []
    }

    java_files = read_all_java_files(".")

    # Pre-scan all files to build cross-file registries
    detected_mod_id = run_prescan(java_files, namespace)
    if detected_mod_id and detected_mod_id != namespace:
        print(f"[prescan] Using detected mod_id '{detected_mod_id}' as namespace (was '{namespace}')")
        namespace = detected_mod_id

    for path, code in java_files.items():
        fname = os.path.basename(path)
        lname = fname.lower()
        try:
            is_item = lname.endswith("item.java") or (("_item" in lname) or ("item" in lname and lname.count("item") == 1 and not lname.endswith("model.java")))
            is_block = lname.endswith("block.java") or ("block" in lname and "model" not in lname)
            # Guard: don't treat a file as an entity if it already looks like an item or block,
            # since item/block classes often extend base classes that trip is_likely_entity.
            entity_candidate = is_likely_entity(code, path) and not (is_item or is_block)

            if is_item:
                convert_java_item_full(code, path, namespace)
                stats["converted_items"].append(path)
            if is_block:
                convert_java_block_full(code, path, namespace)
                stats["converted_blocks"].append(path)
            if entity_candidate:
                cls = extract_class_name(code) or os.path.splitext(fname)[0]
                # Priority: prescan registry > setRegistryName > class name
                if cls and cls in ENTITY_REGISTRY:
                    entity_identifier = ENTITY_REGISTRY[cls]
                else:
                    m = re.search(r'setRegistryName\s*\(\s*["\']([a-z0-9_:-]+)["\']', code, re.I)
                    if m:
                        raw = m.group(1)
                        entity_identifier = raw if ":" in raw else f"{namespace}:{raw}"
                    else:
                        entity_identifier = f"{namespace}:{sanitize_identifier(cls)}"
                convert_java_to_bedrock(path, entity_identifier, gecko_maps, geom_file_map, geom_ns_map, anim_key_map, stats)
        except Exception as e:
            print(f"Error processing {path}: {e}")
            stats["errors"].append(f"{path}:{e}")

    generate_texture_registry(pack_display_name)
    generate_sounds_registry(namespace)

    if jar_path:
        process_loot_tables_from_jar(jar_path, namespace)
        process_recipes_from_jar(jar_path, namespace)
        extract_item_tags_from_jar(jar_path, namespace)
        process_structures_from_jar(jar_path, namespace, java_files=java_files)

    convert_lang_files()

    write_manifest_for(BP_FOLDER, pack_display_name, "BP")
    write_manifest_for(RP_FOLDER, pack_display_name, "RP")

    # Summary
    print("\n--- Conversion summary ---")
    print(f"BP entities written: {len(stats['converted_entities_bp'])}")
    print(f"RP entities written: {len(stats['converted_entities_rp'])}")
    print(f"Items converted: {len(stats['converted_items'])}")
    print(f"Blocks converted: {len(stats['converted_blocks'])}")
    loot_dir = os.path.join(BP_FOLDER, "loot_tables", "entities")
    loot_count = len(os.listdir(loot_dir)) if os.path.isdir(loot_dir) else 0
    print(f"Loot tables converted: {loot_count}")
    recipe_dir = os.path.join(BP_FOLDER, "recipes")
    recipe_count = len(os.listdir(recipe_dir)) if os.path.isdir(recipe_dir) else 0
    print(f"Recipes converted: {recipe_count}")
    spawn_dir = os.path.join(BP_FOLDER, "spawn_rules")
    spawn_count = len(os.listdir(spawn_dir)) if os.path.isdir(spawn_dir) else 0
    print(f"Spawn rules generated: {spawn_count}")
    struct_dir = os.path.join(BP_FOLDER, "structures")
    struct_count = len([f for f in os.listdir(struct_dir) if f.endswith(".mcstructure")]) if os.path.isdir(struct_dir) else 0
    feat_count = len(os.listdir(os.path.join(BP_FOLDER, "features"))) if os.path.isdir(os.path.join(BP_FOLDER, "features")) else 0
    if struct_count:
        print(f"Structures converted: {struct_count} .mcstructure + {feat_count} feature/rule JSONs")
    print(f"Files skipped (likely non-entity helpers): {len(stats['skipped_files'])}")
    if stats['missing_geometry']:
        print(f"Entities skipped for RP (missing geometry): {len(stats['missing_geometry'])}")
        for j, ent in stats['missing_geometry'][:20]:
            print(f" - {ent}  (java: {j})")
    if stats['errors']:
        print(f"Errors encountered: {len(stats['errors'])}")
        for e in stats['errors'][:10]:
            print(" -", e)
    # Validation pass
    validation_warnings = run_validation_pass()
    if validation_warnings:
        print(f"\n--- Validation warnings ({len(validation_warnings)}) ---")
        for w in validation_warnings:
            print(w)
    else:
        print("\n✓ Validation passed - no missing references found")
        print("Zipping Finished Addon!")
        shutil.make_archive("Bedrock_Pack", "zip", "Bedrock_Pack")
        shutil.move("Bedrock_Pack.zip", "Bedrock_Pack.mcaddon")
    print("--- done ---\n")
    shutil.make_archive("Bedrock_Pack", "zip", "Bedrock_Pack")
    shutil.move("Bedrock_Pack.zip", "Bedrock_Pack.mcaddon")

if __name__ == "__main__":
    run_pipeline()